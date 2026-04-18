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

    All tunable parameters (EMA periods, RSI period, overbought/oversold levels) are
    loaded from the ``revolut-trader-strategy-momentum`` 1Password item at startup so
    users can calibrate without changing code.  When a field is absent from 1Password
    the constructor default is used.
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

        # Load calibration overrides from 1Password (via settings.strategy_configs).
        # Falls back to constructor defaults when the vault field is absent.
        from src.config import settings

        scfg = settings.strategy_configs.get("momentum")

        self.fast_period = (
            scfg.fast_period if scfg and scfg.fast_period is not None else fast_period
        )
        self.slow_period = (
            scfg.slow_period if scfg and scfg.slow_period is not None else slow_period
        )
        self.rsi_period = scfg.rsi_period if scfg and scfg.rsi_period is not None else rsi_period
        self.rsi_overbought = (
            scfg.rsi_overbought if scfg and scfg.rsi_overbought is not None else rsi_overbought
        )
        self.rsi_oversold = (
            scfg.rsi_oversold if scfg and scfg.rsi_oversold is not None else rsi_oversold
        )

        # Optimized indicators - O(1) updates instead of O(n) recalculation
        self.fast_ema: dict[str, EMA] = {}
        self.slow_ema: dict[str, EMA] = {}
        self.rsi_indicator: dict[str, RSI] = {}

        # Cross-event state: True = fast was above slow on the previous bar, None = no prior bar
        self._ema_was_bullish: dict[str, bool | None] = {}

    def _determine_signal(
        self,
        fast_ma: Decimal,
        slow_ma: Decimal,
        rsi: Decimal,
        existing_position: Position | None,
        just_crossed_bullish: bool,
        just_crossed_bearish: bool,
    ) -> tuple[str, float, str]:
        """Determine signal type, strength, and reason from indicator values.

        Entry signals (BUY/SELL via EMA cross) fire only on the bar of the cross.
        Strength starts at 0.5 and scales with the EMA gap — EMA gaps are tiny at
        the exact crossover bar and grow afterward, so a floor of 0.5 is necessary
        to clear the min-signal-strength filter.

        RSI-based exits fire every bar regardless of cross state.

        Args:
            fast_ma:              Fast EMA value.
            slow_ma:              Slow EMA value.
            rsi:                  Current RSI value.
            existing_position:    Existing position for this symbol (or ``None``).
            just_crossed_bullish: True only on the bar fast EMA crossed above slow EMA.
            just_crossed_bearish: True only on the bar fast EMA crossed below slow EMA.

        Returns:
            ``(signal_type, strength, reason)`` tuple.
        """
        can_buy = not existing_position or existing_position.side == OrderSide.SELL
        can_sell = not existing_position or existing_position.side == OrderSide.BUY

        # Entry: fire only on the crossing bar.
        # Strength: 0.5 base (clears default min-strength filter) + EMA gap contribution.
        if just_crossed_bullish and rsi < self.rsi_overbought and can_buy:
            ma_diff = float((fast_ma - slow_ma) / slow_ma)
            # Base 0.7 ensures entry clears the default min-signal-strength of 0.6; EMA gap
            # grows after the cross so the base dominates at crossover time.
            strength = min(1.0, 0.7 + ma_diff * 30)
            return (
                "BUY",
                strength,
                f"Bullish cross: Fast MA {fast_ma:.2f} > Slow MA {slow_ma:.2f}, RSI {rsi:.1f}",
            )

        if just_crossed_bearish and rsi > self.rsi_oversold and can_sell:
            ma_diff = float((slow_ma - fast_ma) / slow_ma)
            strength = min(1.0, 0.7 + ma_diff * 30)
            return (
                "SELL",
                strength,
                f"Bearish cross: Fast MA {fast_ma:.2f} < Slow MA {slow_ma:.2f}, RSI {rsi:.1f}",
            )

        # Exit signals based on RSI extremes — fire every bar, not gated by cross event
        if (
            existing_position
            and existing_position.side == OrderSide.BUY
            and rsi > self.rsi_overbought
        ):
            return "SELL", 0.8, f"RSI overbought exit: {rsi:.1f} > {self.rsi_overbought}"
        if (
            existing_position
            and existing_position.side == OrderSide.SELL
            and rsi < self.rsi_oversold
        ):
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
            self._ema_was_bullish[symbol] = None
            return None

        is_bullish_now = fast_ma > slow_ma
        prev_bullish = self._ema_was_bullish.get(symbol)
        self._ema_was_bullish[symbol] = is_bullish_now

        # Treat the first ready bar (prev=None) the same as a state change so
        # the initial cross isn't silently swallowed by the warmup window.
        just_crossed_bullish = (prev_bullish is not True) and is_bullish_now
        just_crossed_bearish = (prev_bullish is not False) and not is_bullish_now

        existing_position = next((p for p in positions if p.symbol == symbol), None)
        signal_type, strength, reason = self._determine_signal(
            fast_ma,
            slow_ma,
            rsi,
            existing_position,
            just_crossed_bullish=just_crossed_bullish,
            just_crossed_bearish=just_crossed_bearish,
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
