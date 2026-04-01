"""Trading fee calculation utilities.

Revolut X fee schedule (as of 2025):
  - LIMIT orders (maker): 0%       — no fee when providing liquidity
  - MARKET orders (taker): 0.09%   — fee charged when taking liquidity

The fee rates are loaded from 1Password (MAKER_FEE_PCT / TAKER_FEE_PCT in the
environment-specific config item) so users can update them without a code change
if Revolut modifies its fee schedule.  The published defaults are used when the
keys are absent from the vault.

``MAKER_FEE_PCT`` and ``TAKER_FEE_PCT`` are exported as module-level Decimal
constants that reflect the *default* published fee schedule.  They are provided
for backwards compatibility (existing tests and other code that imports them
directly).  ``calculate_fee()`` always uses the live ``settings`` values so
that 1Password overrides are respected at runtime.
"""

from decimal import Decimal

from src.models.domain import OrderType

# Default fee rates — match the published Revolut X fee schedule.
# These constants are exported for use in tests and documentation.
# At runtime, calculate_fee() reads the live values from settings so that
# 1Password overrides take effect without restarting Python.
MAKER_FEE_PCT: Decimal = Decimal("0")
TAKER_FEE_PCT: Decimal = Decimal("0.0009")


def calculate_fee(order_value: Decimal, order_type: OrderType) -> Decimal:
    """Calculate the trading fee for a filled order.

    LIMIT orders use the maker rate (default 0%). MARKET orders use the taker
    rate (default 0.09%).  Both rates are loaded from 1Password at startup so
    they can be updated without changing code.

    Args:
        order_value: The total value of the order (price * quantity).
        order_type: The order type (LIMIT or MARKET).

    Returns:
        The fee amount as a Decimal. Always non-negative.
    """
    # Lazy import avoids circular dependency (config → onepassword → fees would
    # create a cycle; lazy import defers until first call after settings is ready).
    from src.config import settings

    if order_type == OrderType.LIMIT:
        rate = Decimal(str(settings.maker_fee_pct))
    else:
        rate = Decimal(str(settings.taker_fee_pct))
    return order_value * rate
