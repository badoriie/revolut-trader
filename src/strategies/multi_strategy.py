from decimal import Decimal
from typing import Any

from loguru import logger

from src.models.domain import MarketData, Position, Signal
from src.strategies.base_strategy import BaseStrategy
from src.strategies.breakout import BreakoutStrategy
from src.strategies.market_making import MarketMakingStrategy
from src.strategies.mean_reversion import MeanReversionStrategy
from src.strategies.momentum import MomentumStrategy
from src.strategies.range_reversion import RangeReversionStrategy


class MultiStrategy(BaseStrategy):
    """
    Multi-Strategy: Combines multiple strategies with weighted voting.

    Aggregates signals from five complementary sub-strategies:
    - Momentum       (trend-following, highest weight)
    - Breakout       (range-escape entries, strong weight)
    - Market Making  (spread / inventory management)
    - Mean Reversion (Bollinger Band reversion)
    - Range Reversion (intraday 24h-range reversion)

    A consensus signal is produced only when the weighted score of the
    winning direction meets or exceeds ``min_consensus``.

    All tunable parameters (weights, min_consensus) are loaded from the
    ``revolut-trader-strategy-multi_strategy`` 1Password item at startup so
    users can calibrate without changing code.  When a field is absent from
    1Password the constructor default is used.
    """

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        min_consensus: float = 0.6,  # 60% weighted score required
    ):
        super().__init__("Multi-Strategy")

        # Load calibration overrides from 1Password (via settings.strategy_configs).
        from src.config import settings

        scfg = settings.strategy_configs.get("multi_strategy")

        effective_min_consensus = (
            scfg.min_consensus if scfg and scfg.min_consensus is not None else min_consensus
        )
        self.min_consensus = effective_min_consensus

        # Build weights: 1Password overrides constructor argument which overrides defaults.
        default_weights = weights or {
            "momentum": 0.30,
            "breakout": 0.25,
            "market_making": 0.20,
            "mean_reversion": 0.15,
            "range_reversion": 0.10,
        }

        # Apply per-weight overrides from 1Password when present.
        if scfg:
            if scfg.weight_momentum is not None:
                default_weights["momentum"] = scfg.weight_momentum
            if scfg.weight_breakout is not None:
                default_weights["breakout"] = scfg.weight_breakout
            if scfg.weight_market_making is not None:
                default_weights["market_making"] = scfg.weight_market_making
            if scfg.weight_mean_reversion is not None:
                default_weights["mean_reversion"] = scfg.weight_mean_reversion
            if scfg.weight_range_reversion is not None:
                default_weights["range_reversion"] = scfg.weight_range_reversion

        self.weights = default_weights

        # Initialize sub-strategies
        self.strategies: dict[str, BaseStrategy] = {
            "market_making": MarketMakingStrategy(),
            "momentum": MomentumStrategy(),
            "mean_reversion": MeanReversionStrategy(),
            "breakout": BreakoutStrategy(),
            "range_reversion": RangeReversionStrategy(),
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
