"""Trading fee calculation utilities.

Revolut X fee schedule (as of 2025):
  - LIMIT orders (maker): 0%       — no fee when providing liquidity
  - MARKET orders (taker): 0.09%   — fee charged when taking liquidity

These constants match the published Revolut X fee schedule and are the
single source of truth used by the executor, bot, and backtest engine.
"""

from decimal import Decimal

from src.models.domain import OrderType

MAKER_FEE_PCT: Decimal = Decimal("0")
TAKER_FEE_PCT: Decimal = Decimal("0.0009")


def calculate_fee(order_value: Decimal, order_type: OrderType) -> Decimal:
    """Calculate the trading fee for a filled order.

    LIMIT orders use the maker rate (0%). MARKET orders use the taker rate (0.09%).

    Args:
        order_value: The total value of the order (price * quantity).
        order_type: The order type (LIMIT or MARKET).

    Returns:
        The fee amount as a Decimal. Always non-negative.
    """
    rate = MAKER_FEE_PCT if order_type == OrderType.LIMIT else TAKER_FEE_PCT
    return order_value * rate
