from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any

from src.models.domain import MarketData, Position, Signal
from src.utils.fees import TAKER_FEE_PCT

# Minimum expected move to justify a round-trip (entry + exit) at taker fee rates.
# 3 × (2 × 0.09%) = 0.54%: the move must be at least 3× the round-trip cost.
_FEE_FLOOR: Decimal = TAKER_FEE_PCT * 2 * 3


class BaseStrategy(ABC):
    """Base class for all trading strategies."""

    def __init__(self, name: str):
        self.name = name
        self.is_active = True

    def _above_fee_floor(self, expected_move: Decimal) -> bool:
        """Return True when the expected move is large enough to justify round-trip taker fees.

        Args:
            expected_move: Fractional price move expected (e.g. 0.01 for 1%).

        Returns:
            True if the move ≥ 3× the round-trip taker fee (default 0.54%).
        """
        return expected_move >= _FEE_FLOOR

    @abstractmethod
    async def analyze(
        self,
        symbol: str,
        market_data: MarketData,
        positions: list[Position],
        portfolio_value: Decimal,
    ) -> Signal | None:
        """
        Analyze market data and generate trading signal.

        Args:
            symbol: Trading pair symbol
            market_data: Current market data
            positions: Current open positions
            portfolio_value: Total portfolio value

        Returns:
            Signal object if strategy generates a signal, None otherwise
        """

    @abstractmethod
    def get_parameters(self) -> dict[str, Any]:
        """Return strategy parameters for logging and monitoring."""

    def activate(self) -> None:
        """Activate the strategy."""
        self.is_active = True

    def deactivate(self) -> None:
        """Deactivate the strategy."""
        self.is_active = False
