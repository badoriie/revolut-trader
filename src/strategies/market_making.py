from decimal import Decimal
from typing import Any

from loguru import logger

from src.data.models import MarketData, OrderSide, Position, Signal
from src.strategies.base_strategy import BaseStrategy


class MarketMakingStrategy(BaseStrategy):
    """
    Market Making Strategy: Places limit orders on both sides of the order book
    to profit from the bid-ask spread.
    """

    def __init__(
        self,
        spread_threshold: float = 0.002,  # 0.2% minimum spread
        order_book_depth: int = 5,
        inventory_target: float = 0.5,  # Target 50% long/short balance
    ):
        super().__init__("Market Making")
        self.spread_threshold = Decimal(str(spread_threshold))
        self.order_book_depth = order_book_depth
        self.inventory_target = Decimal(str(inventory_target))

    async def analyze(
        self,
        symbol: str,
        market_data: MarketData,
        positions: list[Position],
        portfolio_value: Decimal,
    ) -> Signal | None:
        """Generate market making signals based on spread and inventory."""

        # Calculate current spread
        spread = (market_data.ask - market_data.bid) / market_data.bid
        mid_price = (market_data.bid + market_data.ask) / 2

        # Check if spread is wide enough to be profitable
        if spread < self.spread_threshold:
            logger.debug(f"{symbol}: Spread {spread:.4f} below threshold {self.spread_threshold}")
            return None

        # Calculate current inventory position
        position_qty = Decimal("0")
        for pos in positions:
            if pos.symbol == symbol:
                if pos.side == OrderSide.BUY:
                    position_qty += pos.quantity
                else:
                    position_qty -= pos.quantity

        # Determine signal based on inventory skew
        # If we have too much inventory, prefer selling
        # If we have too little, prefer buying
        inventory_ratio = abs(position_qty) / (portfolio_value / mid_price)

        if inventory_ratio > self.inventory_target:
            # Too much inventory, prefer selling
            signal_type = "SELL"
            strength = min(1.0, float(inventory_ratio))
            reason = (
                f"Inventory imbalance: {inventory_ratio:.2%} > target {self.inventory_target:.2%}"
            )
        elif inventory_ratio < self.inventory_target * Decimal("0.5"):
            # Too little inventory, prefer buying
            signal_type = "BUY"
            strength = min(1.0, 1.0 - float(inventory_ratio))
            reason = f"Low inventory: {inventory_ratio:.2%} < target {self.inventory_target:.2%}"
        else:
            # Balanced, place both sides
            signal_type = "BUY"  # Default to buy at bid
            strength = 0.5
            reason = f"Balanced inventory, spread profitable: {spread:.4f}"

        return Signal(
            symbol=symbol,
            strategy=self.name,
            signal_type=signal_type,
            strength=strength,
            price=market_data.bid if signal_type == "BUY" else market_data.ask,
            reason=reason,
            metadata={
                "spread": float(spread),
                "bid": float(market_data.bid),
                "ask": float(market_data.ask),
                "inventory_ratio": float(inventory_ratio),
            },
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "strategy": self.name,
            "spread_threshold": float(self.spread_threshold),
            "order_book_depth": self.order_book_depth,
            "inventory_target": float(self.inventory_target),
        }
