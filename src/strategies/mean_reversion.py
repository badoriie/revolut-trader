from collections import deque
from decimal import Decimal
from typing import Any

from loguru import logger

from src.models.domain import MarketData, OrderSide, Position, Signal
from src.strategies.base_strategy import BaseStrategy


class MeanReversionStrategy(BaseStrategy):
    """
    Mean Reversion Strategy: Buys when price is below average,
    sells when above average. Uses Bollinger Bands.

    All tunable parameters (lookback period, standard deviation multiplier,
    minimum deviation) are loaded from the ``revolut-trader-strategy-mean_reversion``
    1Password item at startup so users can calibrate without changing code.
    When a field is absent from 1Password the constructor default is used.
    """

    def __init__(
        self,
        lookback_period: int = 20,
        num_std_dev: float = 2.0,
        min_deviation: float = 0.01,  # 1% minimum deviation to trade
    ):
        super().__init__("Mean Reversion")

        # Load calibration overrides from 1Password (via settings.strategy_configs).
        from src.config import settings

        scfg = settings.strategy_configs.get("mean_reversion")

        self.lookback_period = (
            scfg.lookback_period if scfg and scfg.lookback_period is not None else lookback_period
        )
        self.num_std_dev = Decimal(
            str(scfg.num_std_dev if scfg and scfg.num_std_dev is not None else num_std_dev)
        )
        self.min_deviation = Decimal(
            str(scfg.min_deviation if scfg and scfg.min_deviation is not None else min_deviation)
        )

        # Price history for calculations
        self.price_history: dict[str, deque[Decimal]] = {}

    def _determine_signal(
        self,
        current_price: Decimal,
        mean_price: Decimal,
        upper_band: Decimal,
        lower_band: Decimal,
        deviation: Decimal,
        existing_position: Position | None,
    ) -> tuple[str, float, str]:
        """Determine signal type, strength, and reason from Bollinger Band analysis.

        Args:
            current_price:     Current market price.
            mean_price:        Bollinger Band mean (SMA).
            upper_band:        Upper Bollinger Band.
            lower_band:        Lower Bollinger Band.
            deviation:         Percentage deviation from the mean.
            existing_position: Existing position for this symbol (or ``None``).

        Returns:
            ``(signal_type, strength, reason)`` tuple.
        """
        abs_deviation = abs(deviation)
        sufficient_deviation = abs_deviation >= self.min_deviation
        is_oversold = current_price <= lower_band and sufficient_deviation
        is_overbought = current_price >= upper_band and sufficient_deviation
        can_buy = not existing_position or existing_position.side == OrderSide.SELL
        can_sell = not existing_position or existing_position.side == OrderSide.BUY

        # Price below lower band — oversold, buy signal
        if is_oversold and can_buy:
            strength = min(1.0, 0.5 * abs(float(deviation)) / float(self.min_deviation))
            return (
                "BUY",
                strength,
                f"Price {current_price:.2f} below lower band {lower_band:.2f}, "
                f"deviation {deviation:.2%}",
            )

        # Price above upper band — overbought, sell signal
        if is_overbought and can_sell:
            strength = min(1.0, 0.5 * abs(float(deviation)) / float(self.min_deviation))
            return (
                "SELL",
                strength,
                f"Price {current_price:.2f} above upper band {upper_band:.2f}, "
                f"deviation {deviation:.2%}",
            )

        # Exit signal: price returns to mean
        if (
            existing_position
            and existing_position.side == OrderSide.BUY
            and current_price >= mean_price
        ):
            return (
                "SELL",
                0.7,
                f"Mean reversion exit: Price {current_price:.2f} returned to mean {mean_price:.2f}",
            )
        if (
            existing_position
            and existing_position.side == OrderSide.SELL
            and current_price <= mean_price
        ):
            return (
                "BUY",
                0.7,
                f"Mean reversion exit: Price {current_price:.2f} returned to mean {mean_price:.2f}",
            )

        return "HOLD", 0.0, ""

    async def analyze(
        self,
        symbol: str,
        market_data: MarketData,
        positions: list[Position],
        portfolio_value: Decimal,
    ) -> Signal | None:
        """Generate mean reversion signals using Bollinger Bands."""
        if symbol not in self.price_history:
            self.price_history[symbol] = deque(maxlen=self.lookback_period)

        current_price = market_data.last
        self.price_history[symbol].append(current_price)

        if len(self.price_history[symbol]) < self.lookback_period:
            logger.debug(
                f"{symbol}: Insufficient data {len(self.price_history[symbol])}/{self.lookback_period}"
            )
            return None

        prices = list(self.price_history[symbol])

        mean_price = sum(prices) / Decimal(len(prices))
        variance = sum((p - mean_price) ** 2 for p in prices) / Decimal(len(prices))
        std_dev = variance.sqrt() if variance > 0 else Decimal("0")

        upper_band = mean_price + (self.num_std_dev * std_dev)
        lower_band = mean_price - (self.num_std_dev * std_dev)
        deviation = (current_price - mean_price) / mean_price

        existing_position = next((p for p in positions if p.symbol == symbol), None)
        signal_type, strength, reason = self._determine_signal(
            current_price, mean_price, upper_band, lower_band, deviation, existing_position
        )

        if signal_type == "HOLD":
            return None

        return Signal(
            symbol=symbol,
            strategy=self.name,
            signal_type=signal_type,
            strength=strength,
            price=current_price,
            reason=reason,
            metadata={
                "mean_price": float(mean_price),
                "upper_band": float(upper_band),
                "lower_band": float(lower_band),
                "std_dev": float(std_dev),
                "deviation": float(deviation),
                "current_price": float(current_price),
            },
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "strategy": self.name,
            "lookback_period": self.lookback_period,
            "num_std_dev": float(self.num_std_dev),
            "min_deviation": float(self.min_deviation),
        }
