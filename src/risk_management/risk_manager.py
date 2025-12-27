from decimal import Decimal

from loguru import logger

from src.config import RiskLevel, settings
from src.data.models import Order, OrderSide, Position


class RiskManager:
    """Risk management system for controlling trading exposure."""

    def __init__(self, risk_level: RiskLevel | None = None, max_order_value_usd: int = 10000):
        self.risk_level = risk_level or settings.risk_level
        self.risk_params = settings.get_risk_parameters()
        self.daily_pnl = Decimal("0")
        self.daily_loss_limit_hit = False

        # Absolute safety limits to prevent catastrophic orders
        self.max_order_value_usd = Decimal(str(max_order_value_usd))
        self.max_quantity_multiplier = Decimal("1000")  # Max 1000x normal position size

        logger.info(f"Risk Manager initialized with {self.risk_level} risk level")
        logger.info(f"Risk parameters: {self.risk_params}")
        logger.info(f"Safety limits: Max order value ${self.max_order_value_usd:,.0f}")

    def can_open_position(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        price: Decimal,
        portfolio_value: Decimal,
        current_positions: list[Position],
    ) -> tuple[bool, str]:
        """Check if a new position can be opened based on risk rules."""

        # Check if daily loss limit is hit
        if self.daily_loss_limit_hit:
            return False, "Daily loss limit reached. Trading suspended."

        # Check number of open positions
        if len(current_positions) >= self.risk_params["max_open_positions"]:
            return False, f"Maximum {self.risk_params['max_open_positions']} positions allowed"

        # Check position size relative to portfolio
        position_value = quantity * price
        position_pct = (position_value / portfolio_value) * 100

        if position_pct > self.risk_params["max_position_size_pct"]:
            return (
                False,
                f"Position size {position_pct:.2f}% exceeds max "
                f"{self.risk_params['max_position_size_pct']}%",
            )

        # Check for concentration risk (too much in one symbol)
        existing_exposure = sum(
            p.quantity * p.current_price for p in current_positions if p.symbol == symbol
        )
        total_exposure = existing_exposure + position_value
        exposure_pct = (total_exposure / portfolio_value) * 100

        if exposure_pct > self.risk_params["max_position_size_pct"] * 2:
            return (
                False,
                f"Total exposure to {symbol} would be {exposure_pct:.2f}%, "
                f"exceeding concentration limit",
            )

        return True, "Position approved"

    def calculate_position_size(
        self, portfolio_value: Decimal, price: Decimal, signal_strength: float = 1.0
    ) -> Decimal:
        """Calculate optimal position size based on portfolio value and signal strength."""
        max_position_value = (
            portfolio_value * Decimal(str(self.risk_params["max_position_size_pct"])) / 100
        )

        # Adjust by signal strength (0.0 to 1.0)
        adjusted_value = max_position_value * Decimal(str(signal_strength))

        # Calculate quantity
        quantity = adjusted_value / price

        # Round to reasonable precision (8 decimal places for crypto)
        return quantity.quantize(Decimal("0.00000001"))

    def validate_order_sanity(
        self, order: Order, current_price: Decimal, portfolio_value: Decimal
    ) -> tuple[bool, str]:
        """Perform sanity checks to prevent catastrophic order mistakes.

        Args:
            order: Order to validate
            current_price: Current market price for the symbol
            portfolio_value: Total portfolio value

        Returns:
            (is_valid, reason) tuple
        """
        # Calculate order value in USD
        order_value = order.quantity * current_price

        # Check 1: Absolute maximum order value
        if order_value > self.max_order_value_usd:
            return (
                False,
                f"Order value ${float(order_value):,.2f} exceeds safety limit "
                f"${float(self.max_order_value_usd):,.2f}",
            )

        # Check 2: Order value cannot exceed entire portfolio
        if order_value > portfolio_value:
            return (
                False,
                f"Order value ${float(order_value):,.2f} exceeds portfolio value "
                f"${float(portfolio_value):,.2f}",
            )

        # Check 3: Quantity sanity check (prevent accidentally adding extra zeros)
        max_reasonable_qty = portfolio_value / current_price * self.max_quantity_multiplier
        if order.quantity > max_reasonable_qty:
            return (
                False,
                f"Order quantity {float(order.quantity):,.8f} is unreasonably large "
                f"(max reasonable: {float(max_reasonable_qty):,.8f})",
            )

        # Check 4: Minimum order value (prevent dust orders)
        min_order_value = Decimal("10")  # $10 minimum
        if order_value < min_order_value:
            return (
                False,
                f"Order value ${float(order_value):,.2f} below minimum ${float(min_order_value):,.2f}",
            )

        return True, "Order passes sanity checks"

    def calculate_stop_loss(
        self, entry_price: Decimal, side: OrderSide, custom_pct: float | None = None
    ) -> Decimal:
        """Calculate stop loss price."""
        stop_pct = custom_pct or self.risk_params["stop_loss_pct"]
        stop_decimal = Decimal(str(stop_pct)) / 100

        if side == OrderSide.BUY:
            stop_price = entry_price * (1 - stop_decimal)
        else:
            stop_price = entry_price * (1 + stop_decimal)

        return stop_price.quantize(Decimal("0.01"))

    def calculate_take_profit(
        self, entry_price: Decimal, side: OrderSide, custom_pct: float | None = None
    ) -> Decimal:
        """Calculate take profit price."""
        tp_pct = custom_pct or self.risk_params["take_profit_pct"]
        tp_decimal = Decimal(str(tp_pct)) / 100

        if side == OrderSide.BUY:
            tp_price = entry_price * (1 + tp_decimal)
        else:
            tp_price = entry_price * (1 - tp_decimal)

        return tp_price.quantize(Decimal("0.01"))

    def update_daily_pnl(self, pnl: Decimal, initial_capital: Decimal) -> None:
        """Update daily PnL and check if loss limit is exceeded."""
        self.daily_pnl = pnl

        loss_limit_pct = Decimal(str(self.risk_params["max_daily_loss_pct"])) / 100
        loss_limit = initial_capital * loss_limit_pct

        if self.daily_pnl <= -loss_limit:
            self.daily_loss_limit_hit = True
            logger.critical(
                f"DAILY LOSS LIMIT HIT: {self.daily_pnl} <= {-loss_limit}. "
                f"Trading suspended for the day."
            )

    def reset_daily_limits(self) -> None:
        """Reset daily limits (should be called at start of new trading day)."""
        self.daily_pnl = Decimal("0")
        self.daily_loss_limit_hit = False
        logger.info("Daily risk limits reset")

    def validate_order(
        self, order: Order, portfolio_value: Decimal, current_positions: list[Position]
    ) -> tuple[bool, str]:
        """Validate an order before execution."""
        if not order.price or not order.quantity:
            return False, "Order must have price and quantity"

        if order.quantity <= 0:
            return False, "Order quantity must be positive"

        return self.can_open_position(
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=order.price,
            portfolio_value=portfolio_value,
            current_positions=current_positions,
        )
