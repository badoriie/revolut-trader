from decimal import Decimal
from typing import Any

from loguru import logger

from src.models.domain import MarketData, OrderSide, Position, Signal
from src.strategies.base_strategy import BaseStrategy
from src.utils.indicators import EMA, RSI


class MomentumStrategy(BaseStrategy):
    """
    Momentum Trading Strategy: Follows price trends using moving averages
    and RSI indicator.

    Optimized with O(1) EMA calculations instead of O(n) SMA for 10-100x faster performance.
    """

    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        rsi_period: int = 14,
        rsi_overbought: float = 70.0,
        rsi_oversold: float = 30.0,
    ):
        super().__init__("Momentum")
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.rsi_period = rsi_period
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold

        # Optimized indicators - O(1) updates instead of O(n) recalculation
        self.fast_ema: dict[str, EMA] = {}
        self.slow_ema: dict[str, EMA] = {}
        self.rsi_indicator: dict[str, RSI] = {}

    async def analyze(
        self,
        symbol: str,
        market_data: MarketData,
        positions: list[Position],
        portfolio_value: Decimal,
    ) -> Signal | None:
        """Generate momentum signals based on moving averages and RSI.

        Optimized implementation using O(1) EMA updates instead of O(n) SMA recalculation.
        """

        # Initialize indicators for symbol if needed
        if symbol not in self.fast_ema:
            self.fast_ema[symbol] = EMA(self.fast_period)
            self.slow_ema[symbol] = EMA(self.slow_period)
            self.rsi_indicator[symbol] = RSI(self.rsi_period)

        # Update all indicators with current price (O(1) operation)
        current_price = market_data.last
        fast_ma = self.fast_ema[symbol].update(current_price)
        slow_ma = self.slow_ema[symbol].update(current_price)
        rsi = self.rsi_indicator[symbol].update(current_price)

        # Wait for indicators to warm up
        if not (
            self.fast_ema[symbol].is_ready
            and self.slow_ema[symbol].is_ready
            and self.rsi_indicator[symbol].is_ready
        ):
            logger.debug(f"{symbol}: Indicators warming up...")
            return None

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

        # Bullish: Fast MA crosses above Slow MA and RSI not overbought
        if fast_ma > slow_ma and rsi < self.rsi_overbought:
            if not existing_position or existing_position.side == OrderSide.SELL:
                signal_type = "BUY"
                ma_diff = (fast_ma - slow_ma) / slow_ma
                strength = min(1.0, float(ma_diff) * 10)  # Scale to 0-1
                reason = f"Bullish momentum: Fast MA {fast_ma:.2f} > Slow MA {slow_ma:.2f}, RSI {rsi:.1f}"

        # Bearish: Fast MA crosses below Slow MA and RSI not oversold
        elif fast_ma < slow_ma and rsi > self.rsi_oversold:
            if not existing_position or existing_position.side == OrderSide.BUY:
                signal_type = "SELL"
                ma_diff = (slow_ma - fast_ma) / slow_ma
                strength = min(1.0, float(ma_diff) * 10)
                reason = f"Bearish momentum: Fast MA {fast_ma:.2f} < Slow MA {slow_ma:.2f}, RSI {rsi:.1f}"

        # Exit signals based on RSI extremes
        elif existing_position:
            if existing_position.side == OrderSide.BUY and rsi > self.rsi_overbought:
                signal_type = "SELL"
                strength = 0.8
                reason = f"RSI overbought exit: {rsi:.1f} > {self.rsi_overbought}"
            elif existing_position.side == OrderSide.SELL and rsi < self.rsi_oversold:
                signal_type = "BUY"
                strength = 0.8
                reason = f"RSI oversold exit: {rsi:.1f} < {self.rsi_oversold}"

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
                "fast_ma": float(fast_ma),
                "slow_ma": float(slow_ma),
                "rsi": float(rsi),
                "current_price": float(current_price),
            },
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "strategy": self.name,
            "fast_period": self.fast_period,
            "slow_period": self.slow_period,
            "rsi_period": self.rsi_period,
            "rsi_overbought": self.rsi_overbought,
            "rsi_oversold": self.rsi_oversold,
        }
