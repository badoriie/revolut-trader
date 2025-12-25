from decimal import Decimal
from typing import Dict, List, Optional

from loguru import logger

from src.config import RiskLevel, settings
from src.data.models import Order, OrderSide, Position


class RiskManager:
    """Risk management system for controlling trading exposure."""

    def __init__(self, risk_level: Optional[RiskLevel] = None):
        self.risk_level = risk_level or settings.risk_level
        self.risk_params = settings.get_risk_parameters()
        self.daily_pnl = Decimal("0")
        self.daily_loss_limit_hit = False

        logger.info(f"Risk Manager initialized with {self.risk_level} risk level")
        logger.info(f"Risk parameters: {self.risk_params}")

    def can_open_position(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        price: Decimal,
        portfolio_value: Decimal,
        current_positions: List[Position],
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
            p.quantity * p.current_price
            for p in current_positions
            if p.symbol == symbol
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

    def calculate_stop_loss(
        self, entry_price: Decimal, side: OrderSide, custom_pct: Optional[float] = None
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
        self, entry_price: Decimal, side: OrderSide, custom_pct: Optional[float] = None
    ) -> Decimal:
        """Calculate take profit price."""
        tp_pct = custom_pct or self.risk_params["take_profit_pct"]
        tp_decimal = Decimal(str(tp_pct)) / 100

        if side == OrderSide.BUY:
            tp_price = entry_price * (1 + tp_decimal)
        else:
            tp_price = entry_price * (1 - tp_decimal)

        return tp_price.quantize(Decimal("0.01"))

    def update_daily_pnl(self, pnl: Decimal, initial_capital: Decimal):
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

    def reset_daily_limits(self):
        """Reset daily limits (should be called at start of new trading day)."""
        self.daily_pnl = Decimal("0")
        self.daily_loss_limit_hit = False
        logger.info("Daily risk limits reset")

    def validate_order(
        self, order: Order, portfolio_value: Decimal, current_positions: List[Position]
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
