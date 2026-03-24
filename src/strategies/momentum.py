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

    def _determine_signal(
        self,
        fast_ma: Decimal,
        slow_ma: Decimal,
        rsi: Decimal,
        existing_position: Position | None,
    ) -> tuple[str, float, str]:
        """Determine signal type, strength, and reason from indicator values.

        Args:
            fast_ma:           Fast EMA value.
            slow_ma:           Slow EMA value.
            rsi:               Current RSI value.
            existing_position: Existing position for this symbol (or ``None``).

        Returns:
            ``(signal_type, strength, reason)`` tuple.
        """
        # Bullish: Fast MA crosses above Slow MA and RSI not overbought
        if fast_ma > slow_ma and rsi < self.rsi_overbought:
            if not existing_position or existing_position.side == OrderSide.SELL:
                ma_diff = (fast_ma - slow_ma) / slow_ma
                return (
                    "BUY",
                    min(1.0, float(ma_diff) * 10),
                    f"Bullish momentum: Fast MA {fast_ma:.2f} > Slow MA {slow_ma:.2f}, RSI {rsi:.1f}",
                )

        # Bearish: Fast MA crosses below Slow MA and RSI not oversold
        elif fast_ma < slow_ma and rsi > self.rsi_oversold:
            if not existing_position or existing_position.side == OrderSide.BUY:
                ma_diff = (slow_ma - fast_ma) / slow_ma
                return (
                    "SELL",
                    min(1.0, float(ma_diff) * 10),
                    f"Bearish momentum: Fast MA {fast_ma:.2f} < Slow MA {slow_ma:.2f}, RSI {rsi:.1f}",
                )

        # Exit signals based on RSI extremes
        elif existing_position:
            if existing_position.side == OrderSide.BUY and rsi > self.rsi_overbought:
                return "SELL", 0.8, f"RSI overbought exit: {rsi:.1f} > {self.rsi_overbought}"
            if existing_position.side == OrderSide.SELL and rsi < self.rsi_oversold:
                return "BUY", 0.8, f"RSI oversold exit: {rsi:.1f} < {self.rsi_oversold}"

        return "HOLD", 0.0, ""

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
        if symbol not in self.fast_ema:
            self.fast_ema[symbol] = EMA(self.fast_period)
            self.slow_ema[symbol] = EMA(self.slow_period)
            self.rsi_indicator[symbol] = RSI(self.rsi_period)

        current_price = market_data.last
        fast_ma = self.fast_ema[symbol].update(current_price)
        slow_ma = self.slow_ema[symbol].update(current_price)
        rsi = self.rsi_indicator[symbol].update(current_price)

        if not (
            self.fast_ema[symbol].is_ready
            and self.slow_ema[symbol].is_ready
            and self.rsi_indicator[symbol].is_ready
        ):
            logger.debug(f"{symbol}: Indicators warming up...")
            return None

        existing_position = next((p for p in positions if p.symbol == symbol), None)
        signal_type, strength, reason = self._determine_signal(
            fast_ma, slow_ma, rsi, existing_position
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
