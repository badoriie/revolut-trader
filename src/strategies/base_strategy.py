from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any

from src.data.models import MarketData, Position, Signal


class BaseStrategy(ABC):
    """Base class for all trading strategies."""

    def __init__(self, name: str):
        self.name = name
        self.is_active = True

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
        pass

    @abstractmethod
    def get_parameters(self) -> dict[str, Any]:
        """Return strategy parameters for logging and monitoring."""
        pass

    def activate(self) -> None:
        """Activate the strategy."""
        self.is_active = True

    def deactivate(self) -> None:
        """Deactivate the strategy."""
        self.is_active = False
