from decimal import Decimal
from typing import Any

from loguru import logger

from src.models.domain import MarketData, OrderSide, Position, Signal
from src.strategies.base_strategy import BaseStrategy


class MarketMakingStrategy(BaseStrategy):
    """
    Market Making Strategy: Places limit orders on both sides of the order book
    to profit from the bid-ask spread.

    All tunable parameters (spread threshold, inventory target) are loaded from
    the ``revolut-trader-strategy-market_making`` 1Password item at startup so
    users can calibrate without changing code.  When a field is absent from
    1Password the constructor default is used.
    """

    def __init__(
        self,
        spread_threshold: float = 0.0005,  # 0.05% minimum spread (above Revolut X maker fee)
        order_book_depth: int = 5,
        inventory_target: float = 0.5,  # Target 50% long/short balance
    ):
        super().__init__("Market Making")

        # Load calibration overrides from 1Password (via settings.strategy_configs).
        from src.config import settings

        scfg = settings.strategy_configs.get("market_making")

        effective_spread = (
            scfg.spread_threshold
            if scfg and scfg.spread_threshold is not None
            else spread_threshold
        )
        effective_inventory = (
            scfg.inventory_target
            if scfg and scfg.inventory_target is not None
            else inventory_target
        )

        self.spread_threshold = Decimal(str(effective_spread))
        self.order_book_depth = order_book_depth
        self.inventory_target = Decimal(str(effective_inventory))

    async def analyze(
        self,
        symbol: str,
        market_data: MarketData,
        positions: list[Position],
        portfolio_value: Decimal,
    ) -> Signal | None:
        """Generate market making signals based on spread and inventory.

        Uses a signed inventory ratio so that net-short positions are handled
        correctly: a net short means we should buy to rebalance, not sell more.
        """

        # Calculate current spread
        spread = (market_data.ask - market_data.bid) / market_data.bid
        mid_price = (market_data.bid + market_data.ask) / 2

        # Guard against zero mid price (should never happen in practice)
        if mid_price <= Decimal("0"):
            logger.warning(f"{symbol}: Zero or negative mid price {mid_price}, skipping")
            return None

        # Check if spread is wide enough to be profitable
        if spread < self.spread_threshold:
            logger.info(
                f"{symbol}: Spread {spread:.4f} below threshold {self.spread_threshold} — no signal"
            )
            return None

        # Calculate net inventory: positive = net long, negative = net short
        position_qty = Decimal("0")
        for pos in positions:
            if pos.symbol == symbol:
                if pos.side == OrderSide.BUY:
                    position_qty += pos.quantity
                else:
                    position_qty -= pos.quantity

        # Signed inventory ratio: how much of our theoretical max portfolio qty do we hold?
        # Positive = net long, negative = net short. Range is typically -1 to +1.
        max_base_qty = portfolio_value / mid_price
        signed_ratio = position_qty / max_base_qty

        if signed_ratio > self.inventory_target:
            # Net long above target → prefer selling to rebalance toward neutral
            signal_type = "SELL"
            strength = min(1.0, float(signed_ratio - self.inventory_target))
            reason = (
                f"Excess long inventory: {signed_ratio:.2%} > target {self.inventory_target:.2%}"
            )
        elif signed_ratio < -self.inventory_target:
            # Net short below negative target → prefer buying to rebalance toward neutral
            signal_type = "BUY"
            strength = min(1.0, float(-signed_ratio - self.inventory_target))
            reason = (
                f"Excess short inventory: {signed_ratio:.2%} < target -{self.inventory_target:.2%}"
            )
        elif abs(signed_ratio) < self.inventory_target * Decimal("0.5"):
            # Near-zero inventory → buy at bid to begin market making
            signal_type = "BUY"
            strength = 0.5
            reason = f"Low inventory ({signed_ratio:.2%}), spread profitable: {spread:.4f}"
        else:
            # Balanced inventory → maintain position, buy at bid
            signal_type = "BUY"
            strength = 0.5
            reason = f"Balanced inventory ({signed_ratio:.2%}), spread profitable: {spread:.4f}"

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
                "inventory_ratio": float(signed_ratio),
            },
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "strategy": self.name,
            "spread_threshold": float(self.spread_threshold),
            "order_book_depth": self.order_book_depth,
            "inventory_target": float(self.inventory_target),
        }
