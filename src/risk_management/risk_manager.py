"""Risk management system for controlling trading exposure.

All monetary values use ``Decimal`` throughout — never ``float`` — to prevent
rounding errors in financial calculations.
"""

from decimal import Decimal
from typing import TypedDict

from loguru import logger

from src.config import RiskLevel, settings
from src.models.domain import Order, OrderSide, Position


class RiskParams(TypedDict):
    """Typed risk parameters for a given risk level.

    Using a TypedDict instead of a plain dict catches key-name typos at
    type-check time (e.g. ``risk_params["max_position_pct"]`` vs the correct
    ``risk_params["max_position_size_pct"]``).
    """

    max_position_size_pct: float
    max_daily_loss_pct: float
    stop_loss_pct: float
    take_profit_pct: float
    max_open_positions: int


# Risk parameters indexed by level.  Single source of truth — Settings no
# longer duplicates this dict.
_RISK_PARAMS: dict[RiskLevel, RiskParams] = {
    RiskLevel.CONSERVATIVE: {
        "max_position_size_pct": 1.5,
        "max_daily_loss_pct": 3.0,
        "stop_loss_pct": 1.5,
        "take_profit_pct": 2.5,
        "max_open_positions": 3,
    },
    RiskLevel.MODERATE: {
        "max_position_size_pct": 3.0,
        "max_daily_loss_pct": 5.0,
        "stop_loss_pct": 2.5,
        "take_profit_pct": 4.0,
        "max_open_positions": 5,
    },
    RiskLevel.AGGRESSIVE: {
        "max_position_size_pct": 5.0,
        "max_daily_loss_pct": 10.0,
        "stop_loss_pct": 4.0,
        "take_profit_pct": 7.0,
        "max_open_positions": 8,
    },
}


class RiskManager:
    """Risk management system for controlling trading exposure."""

    def __init__(self, risk_level: RiskLevel | None = None, max_order_value: int = 10000):
        """Initialise the risk manager.

        Args:
            risk_level: Risk level to use; falls back to ``settings.risk_level``
                if not provided.
            max_order_value: Absolute maximum order value in the base currency
                (e.g. EUR).  Acts as a hard ceiling regardless of portfolio size.
        """
        self.risk_level = risk_level or settings.risk_level
        self.risk_params = self._get_risk_parameters_for_level(self.risk_level)
        self.daily_pnl = Decimal("0")
        self.daily_loss_limit_hit = False

        # Absolute safety ceiling — prevents catastrophically large orders even
        # when the portfolio is large enough to satisfy position-percentage rules.
        self.max_order_value = Decimal(str(max_order_value))
        self.max_quantity_multiplier = Decimal("1000")  # Max 1000x normal position

        currency_symbols = {"EUR": "€", "USD": "$", "GBP": "£"}
        self.currency_symbol = currency_symbols.get(settings.base_currency, settings.base_currency)

        logger.info(f"Risk Manager initialized with {self.risk_level} risk level")
        logger.info(f"Risk parameters: {self.risk_params}")
        logger.info(
            f"Safety limits: Max order value {self.currency_symbol}{self.max_order_value:,.0f}"
        )

    @staticmethod
    def _get_risk_parameters_for_level(risk_level: RiskLevel) -> RiskParams:
        """Return risk parameters for a specific risk level.

        Args:
            risk_level: The risk level to look up.

        Returns:
            Typed ``RiskParams`` dict for the given level.

        Raises:
            ValueError: If ``risk_level`` is not a known ``RiskLevel`` value.
                Fails fast rather than silently falling back, which could mask
                misconfiguration and leave the bot trading at the wrong limits.
        """
        if risk_level not in _RISK_PARAMS:
            raise ValueError(
                f"Unknown risk level: {risk_level!r}. Valid values: {[r.value for r in RiskLevel]}"
            )
        return _RISK_PARAMS[risk_level]

    def get_risk_parameters(self) -> RiskParams:
        """Return the current risk parameters for this RiskManager instance."""
        return self.risk_params.copy()  # type: ignore[return-value]

    def can_open_position(
        self,
        symbol: str,
        quantity: Decimal,
        price: Decimal,
        portfolio_value: Decimal,
        current_positions: list[Position],
    ) -> tuple[bool, str]:
        """Check if a new position can be opened based on risk rules.

        Args:
            symbol: Trading pair symbol (e.g. ``"BTC-EUR"``).
            quantity: Order quantity.
            price: Order price in base currency.
            portfolio_value: Total portfolio value in base currency.
            current_positions: All currently open positions.

        Returns:
            ``(True, "Position approved")`` or ``(False, reason)`` tuple.
        """
        if portfolio_value <= Decimal("0"):
            return False, "Portfolio value must be positive"

        # Daily loss limit suspends all new positions.
        if self.daily_loss_limit_hit:
            return False, "Daily loss limit reached. Trading suspended."

        # Hard cap on number of concurrent positions.
        if len(current_positions) >= self.risk_params["max_open_positions"]:
            return False, f"Maximum {self.risk_params['max_open_positions']} positions allowed"

        # Position size relative to portfolio.
        position_value = quantity * price
        position_pct = (position_value / portfolio_value) * 100

        if position_pct > self.risk_params["max_position_size_pct"]:
            return (
                False,
                f"Position size {position_pct:.2f}% exceeds max "
                f"{self.risk_params['max_position_size_pct']}%",
            )

        # Concentration risk: total exposure to one symbol must not exceed 2× the
        # per-position limit.  This catches cases where many small positions in the
        # same asset create hidden correlation risk.
        existing_exposure = sum(
            p.quantity * p.current_price for p in current_positions if p.symbol == symbol
        )
        total_exposure = existing_exposure + position_value
        exposure_pct = (total_exposure / portfolio_value) * 100
        concentration_limit = self.risk_params["max_position_size_pct"] * 2

        if exposure_pct > concentration_limit:
            return (
                False,
                f"Total exposure to {symbol} would be {exposure_pct:.2f}%, "
                f"exceeding concentration limit of {concentration_limit:.1f}%",
            )

        return True, "Position approved"

    def calculate_position_size(
        self, portfolio_value: Decimal, price: Decimal, signal_strength: float = 1.0
    ) -> Decimal:
        """Calculate optimal position size based on portfolio value and signal strength.

        Args:
            portfolio_value: Total portfolio value in base currency.
            price: Current asset price in base currency.
            signal_strength: Strategy confidence in [0.0, 1.0].  A value of 1.0
                uses the full allowed position size; 0.5 uses half; 0.0 skips.

        Returns:
            Quantity to buy/sell, quantized to 8 decimal places (crypto precision).
        """
        max_position_value = (
            portfolio_value * Decimal(str(self.risk_params["max_position_size_pct"])) / 100
        )
        adjusted_value = max_position_value * Decimal(str(signal_strength))
        quantity = adjusted_value / price
        return quantity.quantize(Decimal("0.00000001"))

    def validate_order_sanity(
        self, order: Order, current_price: Decimal, portfolio_value: Decimal
    ) -> tuple[bool, str]:
        """Perform absolute safety checks to prevent catastrophic order mistakes.

        These checks are independent of portfolio-percentage rules and run even
        when the position-percentage checks would pass (e.g. a small percentage of
        a very large portfolio can still be an enormous absolute amount).

        Checks performed:
        1. Order value ≤ absolute maximum (``max_order_value``).
        2. Order value ≤ total portfolio (no leverage / impossible orders).
        3. Quantity sanity (catches accidental extra zeros — fat-finger protection).
        4. Minimum order value (prevents dust orders where fees exceed value).

        Args:
            order: Order to validate.
            current_price: Current market price for the symbol.
            portfolio_value: Total portfolio value in base currency.

        Returns:
            ``(True, "Order passes sanity checks")`` or ``(False, reason)`` tuple.
        """
        order_value = order.quantity * current_price

        # Check 1: Absolute maximum order value.
        if order_value > self.max_order_value:
            return (
                False,
                f"Order value {self.currency_symbol}{order_value:,.2f} exceeds safety limit "
                f"{self.currency_symbol}{self.max_order_value:,.2f}",
            )

        # Check 2: Order value cannot exceed entire portfolio (no leverage).
        if order_value > portfolio_value:
            return (
                False,
                f"Order value {self.currency_symbol}{order_value:,.2f} exceeds portfolio value "
                f"{self.currency_symbol}{portfolio_value:,.2f}",
            )

        # Check 3: Quantity sanity — catches accidental extra zeros.
        max_reasonable_qty = portfolio_value / current_price * self.max_quantity_multiplier
        if order.quantity > max_reasonable_qty:
            return (
                False,
                f"Order quantity {order.quantity:,.8f} is unreasonably large "
                f"(max reasonable: {max_reasonable_qty:,.8f})",
            )

        # Check 4: Minimum order value — prevents dust orders.
        min_order_value = Decimal("10")
        if order_value < min_order_value:
            return (
                False,
                f"Order value {self.currency_symbol}{order_value:,.2f} below minimum "
                f"{self.currency_symbol}{min_order_value:,.2f}",
            )

        return True, "Order passes sanity checks"

    def calculate_stop_loss(
        self, entry_price: Decimal, side: OrderSide, custom_pct: float | None = None
    ) -> Decimal:
        """Calculate stop loss price.

        Args:
            entry_price: Entry price of the position.
            side: BUY or SELL.
            custom_pct: Override the risk-level stop loss percentage.

        Returns:
            Stop loss price quantized to 2 decimal places.
        """
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
        """Calculate take profit price.

        Args:
            entry_price: Entry price of the position.
            side: BUY or SELL.
            custom_pct: Override the risk-level take profit percentage.

        Returns:
            Take profit price quantized to 2 decimal places.
        """
        tp_pct = custom_pct or self.risk_params["take_profit_pct"]
        tp_decimal = Decimal(str(tp_pct)) / 100

        if side == OrderSide.BUY:
            tp_price = entry_price * (1 + tp_decimal)
        else:
            tp_price = entry_price * (1 - tp_decimal)

        return tp_price.quantize(Decimal("0.01"))

    def update_daily_pnl(self, pnl: Decimal, initial_capital: Decimal) -> None:
        """Update the running daily PnL and suspend trading if the loss limit is hit.

        Args:
            pnl: Current cumulative daily PnL (negative = loss).
            initial_capital: Starting capital for the day, used to compute the
                loss limit in absolute terms.
        """
        self.daily_pnl = pnl

        loss_limit_pct = Decimal(str(self.risk_params["max_daily_loss_pct"])) / 100
        loss_limit = initial_capital * loss_limit_pct

        if self.daily_pnl <= -loss_limit:
            self.daily_loss_limit_hit = True
            logger.critical(
                f"DAILY LOSS LIMIT HIT: {self.daily_pnl} <= {-loss_limit}. "
                "Trading suspended for the day."
            )

    def reset_daily_limits(self) -> None:
        """Reset daily limits — call at the start of each new trading day."""
        self.daily_pnl = Decimal("0")
        self.daily_loss_limit_hit = False
        logger.info("Daily risk limits reset")

    def validate_order(
        self, order: Order, portfolio_value: Decimal, current_positions: list[Position]
    ) -> tuple[bool, str]:
        """Validate an order before execution.

        Runs both absolute sanity checks (``validate_order_sanity``) AND
        position-level risk checks (``can_open_position``).  Both must pass.

        Calling only ``can_open_position`` is NOT sufficient — a tiny percentage
        of a huge portfolio can still be a catastrophically large absolute amount,
        which the sanity checks catch.

        Args:
            order: Order to validate.
            portfolio_value: Total portfolio value in base currency.
            current_positions: All currently open positions.

        Returns:
            ``(True, reason)`` if all checks pass, ``(False, reason)`` otherwise.
        """
        if not order.price or not order.quantity:
            return False, "Order must have price and quantity"

        if order.quantity <= 0:
            return False, "Order quantity must be positive"

        # Absolute safety limits first — these are unconditional hard stops.
        is_sane, sanity_reason = self.validate_order_sanity(order, order.price, portfolio_value)
        if not is_sane:
            return False, sanity_reason

        # Position-level risk rules (daily loss, max positions, size %, concentration).
        return self.can_open_position(
            symbol=order.symbol,
            quantity=order.quantity,
            price=order.price,
            portfolio_value=portfolio_value,
            current_positions=current_positions,
        )
