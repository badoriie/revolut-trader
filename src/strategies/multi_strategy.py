from decimal import Decimal
from typing import Any

from loguru import logger

from src.data.models import MarketData, Position, Signal
from src.strategies.base_strategy import BaseStrategy
from src.strategies.market_making import MarketMakingStrategy
from src.strategies.mean_reversion import MeanReversionStrategy
from src.strategies.momentum import MomentumStrategy


class MultiStrategy(BaseStrategy):
    """
    Multi-Strategy: Combines multiple strategies with weighted voting.
    """

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        min_consensus: float = 0.6,  # 60% agreement required
    ):
        super().__init__("Multi-Strategy")

        # Default equal weights
        self.weights = weights or {
            "market_making": 0.3,
            "momentum": 0.4,
            "mean_reversion": 0.3,
        }

        self.min_consensus = min_consensus

        # Initialize sub-strategies
        self.strategies: dict[str, BaseStrategy] = {
            "market_making": MarketMakingStrategy(),
            "momentum": MomentumStrategy(),
            "mean_reversion": MeanReversionStrategy(),
        }

        # Validate weights sum to 1.0
        total_weight = sum(self.weights.values())
        if abs(total_weight - 1.0) > 0.01:
            logger.warning(f"Weights sum to {total_weight}, normalizing to 1.0")
            self.weights = {k: v / total_weight for k, v in self.weights.items()}

    async def analyze(
        self,
        symbol: str,
        market_data: MarketData,
        positions: list[Position],
        portfolio_value: Decimal,
    ) -> Signal | None:
        """Generate consensus signal from multiple strategies."""

        signals: dict[str, Signal] = {}

        # Get signals from all sub-strategies
        for strategy_name, strategy in self.strategies.items():
            if not strategy.is_active:
                continue

            signal = await strategy.analyze(symbol, market_data, positions, portfolio_value)
            if signal:
                signals[strategy_name] = signal

        # No signals from any strategy
        if not signals:
            return None

        # Calculate weighted consensus
        buy_score = Decimal("0")
        sell_score = Decimal("0")

        for strategy_name, signal in signals.items():
            weight = Decimal(str(self.weights.get(strategy_name, 0)))
            strength = Decimal(str(signal.strength))
            weighted_strength = weight * strength

            if signal.signal_type == "BUY":
                buy_score += weighted_strength
            elif signal.signal_type == "SELL":
                sell_score += weighted_strength

        # Determine consensus signal
        total_score = buy_score + sell_score

        if total_score < Decimal(str(self.min_consensus)):
            logger.debug(
                f"{symbol}: Consensus score {total_score:.2f} below threshold {self.min_consensus}"
            )
            return None

        if buy_score > sell_score:
            signal_type = "BUY"
            consensus_strength = float(buy_score)
        elif sell_score > buy_score:
            signal_type = "SELL"
            consensus_strength = float(sell_score)
        else:
            return None  # Tie, no action

        # Build consensus reason
        signal_reasons = [f"{name}: {sig.reason}" for name, sig in signals.items()]
        reason = f"Consensus {signal_type} ({consensus_strength:.2%}): " + " | ".join(
            signal_reasons
        )

        return Signal(
            symbol=symbol,
            strategy=self.name,
            signal_type=signal_type,
            strength=consensus_strength,
            price=market_data.last,
            reason=reason,
            metadata={
                "buy_score": float(buy_score),
                "sell_score": float(sell_score),
                "total_score": float(total_score),
                "contributing_strategies": list(signals.keys()),
                "weights": self.weights,
            },
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "strategy": self.name,
            "weights": self.weights,
            "min_consensus": self.min_consensus,
            "active_strategies": [
                name for name, strat in self.strategies.items() if strat.is_active
            ],
        }

    def set_strategy_weight(self, strategy_name: str, weight: float) -> None:
        """Update weight for a specific strategy."""
        if strategy_name in self.weights:
            self.weights[strategy_name] = weight
            # Renormalize
            total = sum(self.weights.values())
            self.weights = {k: v / total for k, v in self.weights.items()}
            logger.info(f"Updated weights: {self.weights}")

    def activate_strategy(self, strategy_name: str) -> None:
        """Activate a sub-strategy."""
        if strategy_name in self.strategies:
            self.strategies[strategy_name].activate()
            logger.info(f"Activated {strategy_name}")

    def deactivate_strategy(self, strategy_name: str) -> None:
        """Deactivate a sub-strategy."""
        if strategy_name in self.strategies:
            self.strategies[strategy_name].deactivate()
            logger.info(f"Deactivated {strategy_name}")
