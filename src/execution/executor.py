import asyncio
from decimal import Decimal

from loguru import logger

from src.api.client import RevolutAPIClient
from src.api.mock_client import MockRevolutAPIClient
from src.config import TradingMode
from src.models.domain import Order, OrderSide, OrderStatus, OrderType, Position, Signal
from src.risk_management.risk_manager import RiskManager

# Map Revolut API order states to internal OrderStatus values.
# API state strings (lowercase) → internal enum:
#   "new"            = working order (Revolut never sends "open")
#   "pending_new"    = accepted, not yet working
#   "partially_filled" = partially executed
#   "filled"         = fully executed
#   "cancelled"      = cancelled (also tolerate alternate spelling "canceled")
#   "rejected"       = rejected
#   "replaced"       = replaced by another order
# Unknown values default to PENDING rather than crashing.
_API_STATE_MAP: dict[str, OrderStatus] = {
    "new": OrderStatus.OPEN,
    "pending_new": OrderStatus.PENDING,
    "partially_filled": OrderStatus.PARTIALLY_FILLED,
    "filled": OrderStatus.FILLED,
    "cancelled": OrderStatus.CANCELLED,
    "canceled": OrderStatus.CANCELLED,  # tolerate alternate spelling
    "rejected": OrderStatus.REJECTED,
    "replaced": OrderStatus.REPLACED,
}


class OrderExecutor:
    """Handles order execution and position management with thread-safe operations."""

    def __init__(
        self,
        api_client: RevolutAPIClient | MockRevolutAPIClient,
        risk_manager: RiskManager,
        trading_mode: TradingMode,
    ) -> None:
        """Initialise the executor.

        Args:
            api_client:    Revolut API client for live order placement.
            risk_manager:  Risk manager for position sizing and validation.
            trading_mode:  PAPER simulates fills locally; LIVE sends orders to exchange.
        """
        self.api_client = api_client
        self.risk_manager = risk_manager
        self.trading_mode = trading_mode

        # Track positions and orders
        self.positions: dict[str, Position] = {}
        self.open_orders: dict[str, Order] = {}

        # Async locks for concurrent access
        self._position_lock = asyncio.Lock()
        self._order_lock = asyncio.Lock()

        logger.info(f"Order Executor initialized in {trading_mode} mode")

    async def execute_signal(self, signal: Signal, portfolio_value: Decimal) -> Order | None:
        """Execute a trading signal.

        Returns the resulting Order, or None if the signal is a HOLD (no action taken).

        Args:
            signal:          Signal from a strategy.
            portfolio_value: Current total portfolio value used for position sizing and
                             risk checks.
        """
        if signal.signal_type not in ("BUY", "SELL"):
            logger.debug(
                f"Skipping non-actionable signal: {signal.signal_type} for {signal.symbol}"
            )
            return None

        side = OrderSide.BUY if signal.signal_type == "BUY" else OrderSide.SELL

        quantity = self.risk_manager.calculate_position_size(
            portfolio_value=portfolio_value,
            price=signal.price,
            signal_strength=signal.strength,
        )

        order = Order(
            symbol=signal.symbol,
            side=side,
            order_type=OrderType.LIMIT,
            quantity=quantity,
            price=signal.price,
            strategy=signal.strategy,
        )

        # validate_order runs both sanity checks and position-level risk rules.
        is_valid, message = self.risk_manager.validate_order(
            order=order,
            portfolio_value=portfolio_value,
            current_positions=list(self.positions.values()),
        )

        if not is_valid:
            logger.warning(f"Order rejected by risk manager: {message}")
            order.status = OrderStatus.REJECTED
            return order

        if self.trading_mode == TradingMode.PAPER:
            executed_order = await self._execute_paper_order(order)
        else:
            executed_order = await self._execute_live_order(order)

        if executed_order.status == OrderStatus.FILLED:
            await self._update_positions(executed_order)

        return executed_order

    async def _execute_paper_order(self, order: Order) -> Order:
        """Simulate an order fill in paper trading mode."""
        logger.info(
            f"[PAPER] Executing order: {order.symbol} {order.side} {order.quantity} @ {order.price}"
        )
        order.order_id = f"paper_{order.symbol}_{int(order.created_at.timestamp())}"
        order.status = OrderStatus.FILLED
        order.filled_quantity = order.quantity
        logger.info(f"[PAPER] Order filled: {order.order_id}")
        return order

    async def _execute_live_order(self, order: Order) -> Order:
        """Place an order on the live exchange.

        Passes financial values as strings to preserve Decimal precision — the API
        client already wraps them in str() before JSON serialisation.
        """
        try:
            logger.info(
                f"[LIVE] Placing order: {order.symbol} {order.side} "
                f"{order.quantity} @ {order.price}"
            )

            response = await self.api_client.create_order(
                symbol=order.symbol,
                side=order.side.value,
                order_type=order.order_type.value,
                quantity=str(order.quantity),
                price=str(order.price) if order.price else None,
            )

            # Map API response fields (venue_order_id / state) to our domain model.
            order.order_id = response.get("venue_order_id") or None
            order.status = _API_STATE_MAP.get(
                response.get("state", "").lower(), OrderStatus.PENDING
            )
            # filledQty is not returned by create_order; assume 0 until polled.
            order.filled_quantity = Decimal("0")

            if order.order_id:
                async with self._order_lock:
                    self.open_orders[order.order_id] = order

            logger.info(f"[LIVE] Order placed: {order.order_id}, status: {order.status}")
            return order

        except Exception as e:
            logger.error(f"Failed to execute live order: {e}")
            order.status = OrderStatus.REJECTED
            return order

    async def _update_positions(self, order: Order) -> None:
        """Update in-memory position tracking after an order fills (thread-safe).

        For new positions, stop-loss and take-profit are calculated from the risk
        manager so they are always consistent with the current risk level.

        For existing positions on the same side, the average entry price is
        recalculated using a weighted average.  For the opposite side the position
        is either reduced or fully closed and realised PnL is recorded.
        """
        assert order.price is not None, "Cannot update positions for an order without a price"
        async with self._position_lock:
            symbol = order.symbol

            if symbol in self.positions:
                position = self.positions[symbol]

                if position.side == order.side:
                    # Same side — add to position with a weighted-average entry price.
                    total_qty = position.quantity + order.filled_quantity
                    total_cost = (
                        position.entry_price * position.quantity
                        + order.price * order.filled_quantity
                    )
                    position.entry_price = total_cost / total_qty
                    position.quantity = total_qty

                else:
                    # Opposite side — reduce or close position.
                    if order.filled_quantity >= position.quantity:
                        # Full close: realised PnL equals unrealized at close price.
                        realized_pnl = position.unrealized_pnl
                        position.realized_pnl += realized_pnl
                        logger.info(f"Position closed: {symbol}, Realized P&L: {realized_pnl}")
                        del self.positions[symbol]
                    else:
                        # Partial reduce: PnL direction depends on the position side.
                        if position.side == OrderSide.BUY:
                            realized_pnl = (
                                order.price - position.entry_price
                            ) * order.filled_quantity
                        else:  # SELL (short) — profit when price falls
                            realized_pnl = (
                                position.entry_price - order.price
                            ) * order.filled_quantity
                        position.quantity -= order.filled_quantity
                        position.realized_pnl += realized_pnl

            else:
                # New position — set stop-loss and take-profit from risk manager.
                stop_loss = self.risk_manager.calculate_stop_loss(order.price, order.side)
                take_profit = self.risk_manager.calculate_take_profit(order.price, order.side)

                position = Position(
                    symbol=symbol,
                    side=order.side,
                    quantity=order.filled_quantity,
                    entry_price=order.price,
                    current_price=order.price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                )
                self.positions[symbol] = position

                logger.info(
                    f"New position opened: {symbol} {order.side} {order.filled_quantity} "
                    f"@ {order.price}, SL: {stop_loss}, TP: {take_profit}"
                )

    async def update_market_prices(self, symbol: str, current_price: Decimal) -> None:
        """Update the position price and trigger a close order if SL/TP is hit.

        The position lock is held only while updating the price and checking the
        trigger condition.  The closing order is placed *after* releasing the lock
        to avoid a deadlock with ``_update_positions`` (which also acquires the lock).
        """
        should_close = False
        close_reason = ""

        async with self._position_lock:
            if symbol in self.positions:
                position = self.positions[symbol]
                position.update_price(current_price)
                should_close, close_reason = position.should_close()
                if should_close:
                    logger.warning(
                        f"Position {symbol} hit {close_reason} at {current_price}. Closing position."
                    )

        if should_close:
            await self._close_position(symbol, current_price, close_reason)

    async def _close_position(self, symbol: str, price: Decimal, reason: str) -> None:
        """Build and execute a market close order for an open position.

        Args:
            symbol: Trading pair to close.
            price:  Current market price (used as the order price for paper fills).
            reason: Human-readable reason for the close (e.g. "stop_loss").
        """
        async with self._position_lock:
            if symbol not in self.positions:
                return
            position = self.positions[symbol]

        logger.info(f"Closing position {symbol} due to {reason} at {price}")

        close_side = OrderSide.SELL if position.side == OrderSide.BUY else OrderSide.BUY
        close_order = Order(
            symbol=symbol,
            side=close_side,
            order_type=OrderType.MARKET,
            quantity=position.quantity,
            price=price,
            strategy=f"close_{reason}",
        )

        if self.trading_mode == TradingMode.PAPER:
            await self._execute_paper_order(close_order)
        else:
            await self._execute_live_order(close_order)

        if close_order.status == OrderStatus.FILLED:
            await self._update_positions(close_order)

    async def get_portfolio_value(self, cash_balance: Decimal) -> Decimal:
        """Calculate total portfolio value (cash + mark-to-market positions, thread-safe)."""
        async with self._position_lock:
            positions_value = sum(
                pos.quantity * pos.current_price for pos in self.positions.values()
            )
        return cash_balance + positions_value

    def get_positions(self) -> list[Position]:
        """Return a snapshot of all current positions.

        Note: the returned Position objects are mutable; callers should not retain
        references across await points where ``update_market_prices`` may run.
        """
        return list(self.positions.values())

    def get_position(self, symbol: str) -> Position | None:
        """Return the position for *symbol*, or None if no position is open."""
        return self.positions.get(symbol)
