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
    """

    def __init__(
        self,
        lookback_period: int = 20,
        num_std_dev: float = 2.0,
        min_deviation: float = 0.01,  # 1% minimum deviation to trade
    ):
        super().__init__("Mean Reversion")
        self.lookback_period = lookback_period
        self.num_std_dev = Decimal(str(num_std_dev))
        self.min_deviation = Decimal(str(min_deviation))

        # Price history for calculations
        self.price_history: dict[str, deque[Decimal]] = {}

    async def analyze(
        self,
        symbol: str,
        market_data: MarketData,
        positions: list[Position],
        portfolio_value: Decimal,
    ) -> Signal | None:
        """Generate mean reversion signals using Bollinger Bands."""

        # Initialize price history for symbol if needed
        if symbol not in self.price_history:
            self.price_history[symbol] = deque(maxlen=self.lookback_period)

        # Add current price to history
        current_price = market_data.last
        self.price_history[symbol].append(current_price)

        # Need enough data for analysis
        if len(self.price_history[symbol]) < self.lookback_period:
            logger.debug(
                f"{symbol}: Insufficient data {len(self.price_history[symbol])}/{self.lookback_period}"
            )
            return None

        prices = list(self.price_history[symbol])

        # Calculate Bollinger Bands
        mean_price = sum(prices) / Decimal(len(prices))
        variance = sum((p - mean_price) ** 2 for p in prices) / Decimal(len(prices))
        std_dev = variance.sqrt() if variance > 0 else Decimal("0")

        upper_band = mean_price + (self.num_std_dev * std_dev)
        lower_band = mean_price - (self.num_std_dev * std_dev)

        # Calculate % deviation from mean
        deviation = (current_price - mean_price) / mean_price

        # Check for existing position
        existing_position = None
        for pos in positions:
            if pos.symbol == symbol:
                existing_position = pos
                break

        # Generate signals
        signal_type = "HOLD"
        strength = 0.0
        reason = ""

        # Price below lower band - oversold, buy signal
        if current_price <= lower_band and abs(deviation) >= self.min_deviation:
            if not existing_position or existing_position.side == OrderSide.SELL:
                signal_type = "BUY"
                # Stronger signal the further below the band
                strength = min(1.0, abs(float(deviation)) / float(self.min_deviation))
                reason = (
                    f"Price {current_price:.2f} below lower band {lower_band:.2f}, "
                    f"deviation {deviation:.2%}"
                )

        # Price above upper band - overbought, sell signal
        elif current_price >= upper_band and abs(deviation) >= self.min_deviation:
            if not existing_position or existing_position.side == OrderSide.BUY:
                signal_type = "SELL"
                strength = min(1.0, abs(float(deviation)) / float(self.min_deviation))
                reason = (
                    f"Price {current_price:.2f} above upper band {upper_band:.2f}, "
                    f"deviation {deviation:.2%}"
                )

        # Exit signal: price returns to mean
        elif existing_position:
            # Close long position if price returns near or above mean
            if existing_position.side == OrderSide.BUY and current_price >= mean_price:
                signal_type = "SELL"
                strength = 0.7
                reason = f"Mean reversion exit: Price {current_price:.2f} returned to mean {mean_price:.2f}"

            # Close short position if price returns near or below mean
            elif existing_position.side == OrderSide.SELL and current_price <= mean_price:
                signal_type = "BUY"
                strength = 0.7
                reason = f"Mean reversion exit: Price {current_price:.2f} returned to mean {mean_price:.2f}"

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
