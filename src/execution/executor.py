import asyncio
from decimal import Decimal

from loguru import logger

from src.api.client import RevolutAPIClient
from src.api.mock_client import MockRevolutAPIClient
from src.config import TradingMode, settings
from src.models.domain import (
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    ShutdownSummary,
    Signal,
)
from src.risk_management.risk_manager import RiskManager
from src.utils.fees import calculate_fee

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


_DEFAULT_MIN_SIGNAL_STRENGTH: float = 0.5
_DEFAULT_ORDER_TYPE: OrderType = OrderType.LIMIT


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

        # SAFETY: Never sell a symbol the bot did not open a position in.
        # The Revolut API fills sells from total account holdings — a stray SELL
        # would liquidate the user's pre-existing crypto, not just bot-bought crypto.
        if signal.signal_type == "SELL" and signal.symbol not in self.positions:
            logger.warning(
                f"SELL signal for {signal.symbol} rejected: bot has no open position "
                "for this symbol. Pre-existing crypto is protected."
            )
            rejected = Order(
                symbol=signal.symbol,
                side=OrderSide.SELL,
                order_type=OrderType.LIMIT,
                quantity=Decimal("0"),
                price=signal.price,
                strategy=signal.strategy,
            )
            rejected.status = OrderStatus.REJECTED
            return rejected

        # Normalise display names (e.g. "Market Making", "Multi-Strategy") to the
        # snake_case keys used in the strategy config dicts.  This bridges the gap
        # between BaseStrategy.name (human-readable) and the dict keys.
        strategy_key = signal.strategy.lower().replace(" ", "_").replace("-", "_")

        # Signal strength filter — skip signals below the strategy's confidence floor.
        _scfg = settings.strategy_configs.get(strategy_key)
        min_strength = _scfg.min_signal_strength if _scfg else _DEFAULT_MIN_SIGNAL_STRENGTH
        if float(signal.strength) < min_strength:
            logger.debug(
                f"Signal filtered: {signal.strategy} strength {float(signal.strength):.2f} "
                f"< threshold {min_strength:.2f} for {signal.symbol}"
            )
            return None

        side = OrderSide.BUY if signal.signal_type == "BUY" else OrderSide.SELL

        quantity = self.risk_manager.calculate_position_size(
            portfolio_value=portfolio_value,
            price=signal.price,
            signal_strength=signal.strength,
        )

        order_type = OrderType(_scfg.order_type.upper()) if _scfg else _DEFAULT_ORDER_TYPE

        order = Order(
            symbol=signal.symbol,
            side=side,
            order_type=order_type,
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

    async def _execute_paper_order(self, order: Order) -> Order:  # NOSONAR
        """Simulate an order fill in paper trading mode.

        Sets order status to FILLED, fills quantity, and calculates trading
        commission so that downstream P&L and cash accounting include fees.
        """
        logger.info(
            f"[PAPER] Executing order: {order.symbol} {order.side} {order.quantity} @ {order.price}"
        )
        import uuid

        order.order_id = (
            f"paper_{order.symbol}_{int(order.created_at.timestamp())}_{uuid.uuid4().hex[:8]}"
        )
        order.status = OrderStatus.FILLED
        order.filled_quantity = order.quantity
        if order.price is not None:
            order_value = order.price * order.filled_quantity
            order.commission = calculate_fee(order_value, order.order_type)
        logger.info(f"[PAPER] Order filled: {order.order_id} | Fee: {order.commission:.4f}")
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

            if order.status == OrderStatus.FILLED:
                # MARKET orders often fill immediately.  Set filled_quantity and
                # calculate commission so accounting matches the paper path exactly.
                order.filled_quantity = order.quantity
                if order.price is not None:
                    order_value = order.price * order.filled_quantity
                    order.commission = calculate_fee(order_value, order.order_type)
            else:
                # Order is pending/working — fill details not yet available.
                order.filled_quantity = Decimal("0")
                # Only track non-terminal orders for shutdown cancellation.
                if order.order_id:
                    async with self._order_lock:
                        self.open_orders[order.order_id] = order

            logger.info(f"[LIVE] Order placed: {order.order_id}, status: {order.status}")
            return order

        except Exception as e:
            logger.error(f"Failed to execute live order: {e}")
            order.status = OrderStatus.REJECTED
            return order

    async def _attempt_limit_close(self, close_order: Order, timeout_secs: int) -> Order:
        """Try to close a position with a LIMIT order; fall back to MARKET on timeout.

        In paper mode the limit fills immediately (0% fee). In live mode the order
        is polled every 2 seconds; if unfilled after timeout_secs it is cancelled
        and a MARKET order is placed instead.

        Args:
            close_order:  Pre-built LIMIT Order with side, quantity, and price set.
            timeout_secs: Seconds before giving up and falling back to MARKET.

        Returns:
            The filled Order (either the original limit or the market fallback).
        """
        if self.trading_mode == TradingMode.PAPER:
            await self._execute_paper_order(close_order)
            return close_order

        await self._execute_live_order(close_order)
        if close_order.status == OrderStatus.FILLED:
            return close_order

        deadline = asyncio.get_event_loop().time() + timeout_secs
        while asyncio.get_event_loop().time() < deadline and close_order.order_id:
            await asyncio.sleep(2)
            try:
                order_data = await self.api_client.get_order(close_order.order_id)
                state = order_data.get("state", "").lower()
                new_status = _API_STATE_MAP.get(state, OrderStatus.PENDING)
                if new_status == OrderStatus.FILLED:
                    close_order.status = OrderStatus.FILLED
                    close_order.filled_quantity = close_order.quantity
                    if close_order.price is not None:
                        order_value = close_order.price * close_order.filled_quantity
                        close_order.commission = calculate_fee(order_value, close_order.order_type)
                    return close_order
                if new_status in (OrderStatus.CANCELLED, OrderStatus.REJECTED):
                    break
            except Exception as exc:
                logger.warning(f"Error polling limit close order {close_order.order_id}: {exc}")

        # Timeout or non-fillable state: cancel the limit and place a market order.
        if close_order.order_id and close_order.status not in (
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
        ):
            try:
                await self.api_client.cancel_order(close_order.order_id)
                async with self._order_lock:
                    self.open_orders.pop(close_order.order_id, None)
                logger.info(
                    f"Limit close timed out after {timeout_secs}s for {close_order.symbol}; "
                    "falling back to MARKET"
                )
            except Exception as exc:
                logger.warning(
                    f"Could not cancel timed-out limit close {close_order.order_id}: {exc}"
                )

        market_order = Order(
            symbol=close_order.symbol,
            side=close_order.side,
            order_type=OrderType.MARKET,
            quantity=close_order.quantity,
            price=close_order.price,
            strategy=close_order.strategy,
        )
        await self._execute_live_order(market_order)
        return market_order

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
                        # Full close: realised PnL equals unrealized at close price minus fee.
                        gross_pnl = position.unrealized_pnl
                        realized_pnl = gross_pnl - order.commission
                        order.realized_pnl = realized_pnl
                        position.realized_pnl += realized_pnl
                        logger.info(
                            f"Position closed: {symbol} | "
                            f"Gross P&L: {gross_pnl:.4f} | "
                            f"Fee: {order.commission:.4f} | "
                            f"Net P&L: {realized_pnl:.4f}"
                        )
                        del self.positions[symbol]
                    else:
                        # Partial reduce: PnL direction depends on the position side.
                        if position.side == OrderSide.BUY:
                            realized_pnl = (
                                order.price - position.entry_price
                            ) * order.filled_quantity - order.commission
                        else:  # SELL (short) — profit when price falls
                            realized_pnl = (
                                position.entry_price - order.price
                            ) * order.filled_quantity - order.commission
                        order.realized_pnl = realized_pnl
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
                    strategy=order.strategy,
                )
                self.positions[symbol] = position

                logger.info(
                    f"New position opened: {symbol} {order.side} {order.filled_quantity} "
                    f"@ {order.price}, SL: {stop_loss}, TP: {take_profit}"
                )

    async def update_market_prices(self, symbol: str, current_price: Decimal) -> Order | None:
        """Update the position price and trigger a close order if SL/TP is hit.

        The position lock is held only while updating the price and checking the
        trigger condition.  The closing order is placed *after* releasing the lock
        to avoid a deadlock with ``_update_positions`` (which also acquires the lock).

        Returns:
            The filled close Order if a SL/TP was triggered and the position was
            closed, or ``None`` if no close occurred.  The caller is responsible for
            calling ``bot._process_filled_order`` on the returned order so that the
            cash balance and trade history are updated correctly.
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
            return await self._close_position(symbol, current_price, close_reason)
        return None

    async def _close_position(self, symbol: str, price: Decimal, reason: str) -> Order | None:
        """Close an open position, using a LIMIT order for take-profit if configured.

        Stop-loss closes always use MARKET for immediate execution. Take-profit
        closes use LIMIT when the strategy has use_limit_close=True, saving the
        0.09% taker fee. The limit falls back to MARKET after close_limit_timeout_secs.

        Args:
            symbol: Trading pair to close.
            price:  Current market price (used as the order price).
            reason: Human-readable reason for the close (e.g. "stop_loss").

        Returns:
            The executed close Order, or None if the position was already removed.
        """
        async with self._position_lock:
            if symbol not in self.positions:
                return None
            position = self.positions[symbol]

        logger.info(f"Closing position {symbol} due to {reason} at {price}")

        close_side = OrderSide.SELL if position.side == OrderSide.BUY else OrderSide.BUY

        # Use LIMIT for take-profit when the strategy opts in; always MARKET for stop-loss.
        use_limit = False
        timeout_secs = 30
        if reason == "take_profit" and position.strategy:
            strategy_key = position.strategy.lower().replace(" ", "_").replace("-", "_")
            _scfg = settings.strategy_configs.get(strategy_key)
            if _scfg and _scfg.use_limit_close:
                use_limit = True
                timeout_secs = _scfg.close_limit_timeout_secs

        close_order = Order(
            symbol=symbol,
            side=close_side,
            order_type=OrderType.LIMIT if use_limit else OrderType.MARKET,
            quantity=position.quantity,
            price=price,
            strategy=f"close_{reason}",
        )

        if use_limit:
            close_order = await self._attempt_limit_close(close_order, timeout_secs)
        elif self.trading_mode == TradingMode.PAPER:
            await self._execute_paper_order(close_order)
        else:
            await self._execute_live_order(close_order)

        if close_order.status == OrderStatus.FILLED:
            await self._update_positions(close_order)

        return close_order

    async def _shutdown_cancel_orders(self) -> tuple[int, list[str]]:
        """Phase 1 of graceful shutdown: cancel all pending/open orders.

        In LIVE mode the exchange API is called to cancel server-side orders.
        In PAPER mode the in-memory dict is cleared without an API call.

        Returns:
            Tuple of (orders_cancelled, errors).
        """
        errors: list[str] = []
        async with self._order_lock:
            orders_cancelled = len(self.open_orders)

        if orders_cancelled > 0:
            if self.trading_mode == TradingMode.LIVE:
                try:
                    await self.api_client.cancel_all_orders()
                    logger.info(f"Cancelled {orders_cancelled} open orders via API")
                except Exception as exc:
                    error_msg = f"Failed to cancel orders: {exc}"
                    logger.error(error_msg)
                    errors.append(error_msg)

            async with self._order_lock:
                self.open_orders.clear()

        return orders_cancelled, errors

    async def _shutdown_close_one(
        self,
        symbol: str,
        position: Position,
        trailing_stop_pct: Decimal | None,
        max_wait: int,
    ) -> tuple[Order | None, bool]:
        """Close a single position during graceful shutdown.

        Losing positions (unrealized_pnl < 0) and positions when no trailing stop
        is configured are closed immediately.  Profitable/breakeven positions with
        a trailing stop configured are closed via ``_wait_and_close_profitable``.

        Args:
            symbol:            Trading pair to close.
            position:          The position snapshot to close.
            trailing_stop_pct: Trailing stop percentage, or None for immediate close.
            max_wait:          Hard timeout for the trailing stop wait.

        Returns:
            Tuple of (close_order, used_trailing_stop).
        """
        if position.unrealized_pnl < Decimal("0") or trailing_stop_pct is None:
            close_order = await self._close_position_for_shutdown(symbol, position)
            return close_order, False
        close_order = await self._wait_and_close_profitable(
            symbol, position, trailing_stop_pct, max_wait
        )
        return close_order, True

    async def graceful_shutdown(
        self,
        trailing_stop_pct: Decimal | None = None,
        max_wait_seconds: int | None = None,
    ) -> ShutdownSummary:
        """Cancel all orders and close ALL positions on shutdown.

        Shutdown procedure:
          1. Cancel all pending/open orders (they will be unmonitored).
          2. Close positions with ``unrealized_pnl < 0`` immediately via market orders.
          3. Close positions with ``unrealized_pnl >= 0`` via trailing stop (smart exit)
             or immediately if ``trailing_stop_pct`` is None.

        Guarantee: ``self.positions`` is empty when this method returns.

        Args:
            trailing_stop_pct: Trailing stop as a percentage (e.g. ``Decimal("0.5")``
                for 0.5%).  If None, profitable positions are closed immediately.
            max_wait_seconds:  Hard timeout before force-closing a profitable
                position whose trailing stop has not yet triggered.  If None,
                the system default of 120 s is used.

        Returns:
            ShutdownSummary describing what happened during shutdown.
        """
        effective_max_wait = max_wait_seconds if max_wait_seconds is not None else 120

        orders_cancelled, errors = await self._shutdown_cancel_orders()
        filled_close_orders: list[Order] = []

        async with self._position_lock:
            position_snapshot: list[tuple[str, Position]] = list(self.positions.items())

        positions_evaluated = len(position_snapshot)
        positions_closed = 0
        positions_trailing_stopped = 0
        closed_positions_pnl = Decimal("0")
        trailing_stopped_pnl = Decimal("0")

        for symbol, position in position_snapshot:
            try:
                close_order, used_trailing = await self._shutdown_close_one(
                    symbol, position, trailing_stop_pct, effective_max_wait
                )
                if close_order and close_order.status == OrderStatus.FILLED:
                    filled_close_orders.append(close_order)
                positions_closed += 1
                fee = close_order.commission if close_order else Decimal("0")
                net_pnl = position.unrealized_pnl - fee
                if used_trailing:
                    positions_trailing_stopped += 1
                    trailing_stopped_pnl += net_pnl
                    logger.info(
                        f"Closed profitable position {symbol} | "
                        f"Gross P&L: {position.unrealized_pnl:.4f} | "
                        f"Fee: {fee:.4f} | "
                        f"Net P&L: {net_pnl:.4f}"
                    )
                else:
                    closed_positions_pnl += net_pnl
                    logger.info(
                        f"Closed position {symbol} | "
                        f"Gross P&L: {position.unrealized_pnl:.4f} | "
                        f"Fee: {fee:.4f} | "
                        f"Net P&L: {net_pnl:.4f}"
                    )
            except Exception as exc:
                error_msg = f"Failed to close position {symbol}: {exc}"
                logger.error(error_msg)
                errors.append(error_msg)

        logger.info(
            f"Graceful shutdown complete: {orders_cancelled} orders cancelled, "
            f"{positions_closed}/{positions_evaluated} positions closed"
        )

        return ShutdownSummary(
            orders_cancelled=orders_cancelled,
            positions_evaluated=positions_evaluated,
            positions_closed=positions_closed,
            positions_trailing_stopped=positions_trailing_stopped,
            closed_positions_pnl=closed_positions_pnl,
            trailing_stopped_pnl=trailing_stopped_pnl,
            filled_close_orders=filled_close_orders,
            errors=errors,
        )

    def _update_long_trailing_stop(
        self,
        symbol: str,
        current_price: Decimal,
        high_watermark: Decimal,
        trailing_stop_price: Decimal,
        stop_multiplier: Decimal,
    ) -> tuple[Decimal, Decimal, bool]:
        """Update trailing stop state for a long (BUY) position.

        Args:
            symbol:             Trading pair label (for log messages).
            current_price:      Latest market price.
            high_watermark:     Highest price seen since tracking started.
            trailing_stop_price: Current stop level.
            stop_multiplier:    1 - stop_pct/100 (e.g. 0.995 for 0.5%).

        Returns:
            Tuple of (high_watermark, trailing_stop_price, triggered).
        """
        if current_price > high_watermark:
            high_watermark = current_price
            trailing_stop_price = high_watermark * stop_multiplier
            logger.debug(f"Trailing stop updated for {symbol}: {trailing_stop_price}")
        triggered = current_price <= trailing_stop_price
        if triggered:
            logger.info(
                f"Trailing stop triggered for {symbol} at {current_price} "
                f"(stop={trailing_stop_price})"
            )
        return high_watermark, trailing_stop_price, triggered

    def _update_short_trailing_stop(
        self,
        symbol: str,
        current_price: Decimal,
        low_watermark: Decimal,
        trailing_stop_price: Decimal,
        stop_multiplier: Decimal,
    ) -> tuple[Decimal, Decimal, bool]:
        """Update trailing stop state for a short (SELL) position.

        For a short, the stop rises as the price falls.  The stop triggers
        when the price bounces back up above the watermark + stop%.

        Args:
            symbol:             Trading pair label (for log messages).
            current_price:      Latest market price.
            low_watermark:      Lowest price seen since tracking started.
            trailing_stop_price: Current stop level.
            stop_multiplier:    1 - stop_pct/100 (e.g. 0.995 for 0.5%).

        Returns:
            Tuple of (low_watermark, trailing_stop_price, triggered).
        """
        if current_price < low_watermark:
            low_watermark = current_price
            trailing_stop_price = low_watermark * (Decimal("2") - stop_multiplier)
        triggered = current_price >= trailing_stop_price
        if triggered:
            logger.info(
                f"Trailing stop triggered for {symbol} at {current_price} "
                f"(stop={trailing_stop_price})"
            )
        return low_watermark, trailing_stop_price, triggered

    async def _execute_market_close_order(
        self,
        symbol: str,
        position: Position,
        price: Decimal,
        strategy_label: str,
    ) -> Order:
        """Build and execute a market close order, then update position tracking.

        Shared by both the trailing-stop and immediate shutdown paths.  Patches
        ``filled_quantity`` for live orders that come back with zero before the
        fill-poll cycle has run.

        Args:
            symbol:         Trading pair to close.
            position:       The position being closed.
            price:          Market price to use for the order.
            strategy_label: Strategy tag recorded on the Order (e.g.
                            ``"close_graceful_shutdown"``).

        Returns:
            The executed close Order.
        """
        close_side = OrderSide.SELL if position.side == OrderSide.BUY else OrderSide.BUY
        close_order = Order(
            symbol=symbol,
            side=close_side,
            order_type=OrderType.MARKET,
            quantity=position.quantity,
            price=price,
            strategy=strategy_label,
        )
        if self.trading_mode == TradingMode.PAPER:
            await self._execute_paper_order(close_order)
        else:
            await self._execute_live_order(close_order)
        if close_order.status == OrderStatus.FILLED:
            # Live orders come back with filled_quantity=0 (not yet polled).
            # For shutdown close orders we treat the full quantity as filled so
            # _update_positions correctly removes the position from the dict.
            if close_order.filled_quantity == Decimal("0"):
                close_order.filled_quantity = close_order.quantity
            await self._update_positions(close_order)
        return close_order

    async def _wait_and_close_profitable(
        self,
        symbol: str,
        position: Position,
        trailing_stop_pct: Decimal,
        max_wait_seconds: int,
        poll_interval_seconds: int = 2,
    ) -> Order | None:
        """Wait for the best exit price on a profitable position using a trailing stop.

        The trailing stop starts ``trailing_stop_pct``% below the current price and
        follows the price upward.  The position is closed when the price falls back
        to the trailing stop level, or when ``max_wait_seconds`` expires.

        Args:
            symbol:               Trading pair to close.
            position:             The profitable position to manage.
            trailing_stop_pct:    How far (in %) below the high-watermark to set the stop.
            max_wait_seconds:     Hard timeout; force-close if stop never triggers.
            poll_interval_seconds: How often to poll the market price.

        Returns:
            The filled close Order.
        """
        import time

        stop_multiplier = Decimal("1") - trailing_stop_pct / Decimal("100")

        high_watermark = position.current_price
        low_watermark = position.current_price
        if position.side == OrderSide.BUY:
            trailing_stop_price = high_watermark * stop_multiplier
        else:
            # Short position: profitable when price falls.  Trailing stop rises.
            trailing_stop_price = low_watermark * (Decimal("2") - stop_multiplier)

        logger.info(
            f"Trailing stop shutdown for {symbol}: "
            f"PnL={position.unrealized_pnl}, "
            f"stop={trailing_stop_pct}%, "
            f"max_wait={max_wait_seconds}s"
        )

        start = time.monotonic()
        current_price = position.current_price

        while True:
            elapsed = time.monotonic() - start
            if elapsed >= max_wait_seconds:
                logger.info(f"Shutdown timeout reached for {symbol}, force-closing at market")
                break

            try:
                ticker = await self.api_client.get_ticker(symbol)
                current_price = Decimal(str(ticker.get("last", str(position.current_price))))
            except Exception as exc:
                logger.warning(f"Failed to get ticker for {symbol} during shutdown: {exc}")
                break

            if position.side == OrderSide.BUY:
                high_watermark, trailing_stop_price, triggered = self._update_long_trailing_stop(
                    symbol, current_price, high_watermark, trailing_stop_price, stop_multiplier
                )
            else:
                low_watermark, trailing_stop_price, triggered = self._update_short_trailing_stop(
                    symbol, current_price, low_watermark, trailing_stop_price, stop_multiplier
                )

            if triggered:
                break

            await asyncio.sleep(poll_interval_seconds)

        # Update position price to the latest known market price before closing
        position.update_price(current_price)

        return await self._execute_market_close_order(
            symbol, position, current_price, "close_trailing_stop_shutdown"
        )

    async def _close_position_for_shutdown(self, symbol: str, position: Position) -> Order | None:
        """Build and execute a market close order during graceful shutdown.

        Similar to ``_close_position`` but returns the close order so the bot
        can update its cash balance, and uses ``"graceful_shutdown"`` as the
        close reason.

        Args:
            symbol:   Trading pair to close.
            position: The position being closed (read-only snapshot).

        Returns:
            The filled close Order, or None if the position was already gone.
        """
        # Re-check under lock — position may have been removed concurrently
        async with self._position_lock:
            if symbol not in self.positions:
                return None

        return await self._execute_market_close_order(
            symbol, position, position.current_price, "close_graceful_shutdown"
        )

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
