from decimal import Decimal

from loguru import logger

from src.api.client import RevolutAPIClient
from src.config import TradingMode
from src.data.models import Order, OrderSide, OrderStatus, OrderType, Position, Signal
from src.risk_management.risk_manager import RiskManager


class OrderExecutor:
    """Handles order execution and position management."""

    def __init__(
        self,
        api_client: RevolutAPIClient,
        risk_manager: RiskManager,
        trading_mode: TradingMode,
    ):
        self.api_client = api_client
        self.risk_manager = risk_manager
        self.trading_mode = trading_mode

        # Track positions and orders
        self.positions: dict[str, Position] = {}
        self.open_orders: dict[str, Order] = {}

        logger.info(f"Order Executor initialized in {trading_mode} mode")

    async def execute_signal(self, signal: Signal, portfolio_value: Decimal) -> Order | None:
        """Execute a trading signal."""

        # Determine order details from signal
        symbol = signal.symbol
        side = OrderSide.BUY if signal.signal_type == "BUY" else OrderSide.SELL

        # Calculate position size
        quantity = self.risk_manager.calculate_position_size(
            portfolio_value=portfolio_value,
            price=signal.price,
            signal_strength=signal.strength,
        )

        # Create order
        order = Order(
            symbol=symbol,
            side=side,
            order_type=OrderType.LIMIT,
            quantity=quantity,
            price=signal.price,
            strategy=signal.strategy,
        )

        # Validate order with risk manager
        is_valid, message = self.risk_manager.validate_order(
            order=order,
            portfolio_value=portfolio_value,
            current_positions=list(self.positions.values()),
        )

        if not is_valid:
            logger.warning(f"Order rejected by risk manager: {message}")
            order.status = OrderStatus.REJECTED
            return order

        # Execute order
        if self.trading_mode == TradingMode.PAPER:
            executed_order = await self._execute_paper_order(order)
        else:
            executed_order = await self._execute_live_order(order)

        # Update positions if order filled
        if executed_order.status == OrderStatus.FILLED:
            await self._update_positions(executed_order)

        return executed_order

    async def _execute_paper_order(self, order: Order) -> Order:
        """Execute order in paper trading mode (simulated)."""
        logger.info(
            f"[PAPER] Executing order: {order.symbol} {order.side} {order.quantity} @ {order.price}"
        )

        # Simulate order fill
        order.order_id = f"paper_{order.symbol}_{int(order.created_at.timestamp())}"
        order.status = OrderStatus.FILLED
        order.filled_quantity = order.quantity

        logger.info(f"[PAPER] Order filled: {order.order_id}")
        return order

    async def _execute_live_order(self, order: Order) -> Order:
        """Execute order on live exchange."""
        try:
            logger.info(
                f"[LIVE] Placing order: {order.symbol} {order.side} "
                f"{order.quantity} @ {order.price}"
            )

            # Place order via API
            response = await self.api_client.create_order(
                symbol=order.symbol,
                side=order.side.value,
                order_type=order.order_type.value,
                quantity=float(order.quantity),
                price=float(order.price) if order.price else None,
            )

            # Update order with response
            order.order_id = response.get("orderId")
            order.status = OrderStatus(response.get("status", "PENDING"))
            order.filled_quantity = Decimal(str(response.get("filledQty", 0)))

            self.open_orders[order.order_id] = order

            logger.info(f"[LIVE] Order placed: {order.order_id}, status: {order.status}")
            return order

        except Exception as e:
            logger.error(f"Failed to execute live order: {str(e)}")
            order.status = OrderStatus.REJECTED
            return order

    async def _update_positions(self, order: Order):
        """Update position tracking after order execution."""
        symbol = order.symbol

        if symbol in self.positions:
            position = self.positions[symbol]

            # Same side - add to position
            if position.side == order.side:
                total_qty = position.quantity + order.filled_quantity
                total_cost = (
                    position.entry_price * position.quantity + order.price * order.filled_quantity
                )
                position.entry_price = total_cost / total_qty
                position.quantity = total_qty

            # Opposite side - reduce or close position
            else:
                if order.filled_quantity >= position.quantity:
                    # Close position
                    realized_pnl = position.unrealized_pnl
                    position.realized_pnl += realized_pnl
                    logger.info(f"Position closed: {symbol}, Realized P&L: {realized_pnl}")
                    del self.positions[symbol]
                else:
                    # Reduce position
                    position.quantity -= order.filled_quantity
                    realized_pnl = (order.price - position.entry_price) * order.filled_quantity
                    position.realized_pnl += realized_pnl
        else:
            # Create new position
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

    async def update_market_prices(self, symbol: str, current_price: Decimal):
        """Update position with current market price."""
        if symbol in self.positions:
            position = self.positions[symbol]
            position.update_price(current_price)

            # Check if stop loss or take profit hit
            should_close, reason = position.should_close()
            if should_close:
                logger.warning(
                    f"Position {symbol} hit {reason} at {current_price}. Closing position."
                )
                await self._close_position(symbol, current_price, reason)

    async def _close_position(self, symbol: str, price: Decimal, reason: str):
        """Close a position."""
        if symbol not in self.positions:
            return

        position = self.positions[symbol]

        # Create closing order (opposite side)
        close_side = OrderSide.SELL if position.side == OrderSide.BUY else OrderSide.BUY

        close_order = Order(
            symbol=symbol,
            side=close_side,
            order_type=OrderType.MARKET,
            quantity=position.quantity,
            price=price,
            strategy=f"close_{reason}",
        )

        # Execute closing order
        if self.trading_mode == TradingMode.PAPER:
            await self._execute_paper_order(close_order)
        else:
            await self._execute_live_order(close_order)

        # Update position
        await self._update_positions(close_order)

    async def get_portfolio_value(self, cash_balance: Decimal) -> Decimal:
        """Calculate total portfolio value."""
        positions_value = sum(pos.quantity * pos.current_price for pos in self.positions.values())
        return cash_balance + positions_value

    def get_positions(self) -> list[Position]:
        """Get all current positions."""
        return list(self.positions.values())

    def get_position(self, symbol: str) -> Position | None:
        """Get position for a specific symbol."""
        return self.positions.get(symbol)
