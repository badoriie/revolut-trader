from collections import deque
from decimal import Decimal
from typing import Any

from loguru import logger

from src.models.domain import MarketData, OrderSide, Position, Signal
from src.strategies.base_strategy import BaseStrategy
from src.utils.indicators import RSI


class BreakoutStrategy(BaseStrategy):
    """
    Breakout Trading Strategy: Identifies and trades price breakouts above or
    below the recent price range.

    Detects when price moves decisively beyond its recent consolidation range,
    which typically signals the start of a strong directional move. Uses RSI to
    avoid entering breakouts in already-exhausted markets (overbought/oversold).

    Entry logic:
    - BUY  when price > rolling_high × (1 + breakout_threshold) AND RSI < overbought
    - SELL when price < rolling_low  × (1 − breakout_threshold) AND RSI > oversold

    Signal strength scales with how far the price has moved beyond the breakout
    level, ranging from 0.5 (at the threshold) up to 1.0 (well past the threshold).
    """

    def __init__(
        self,
        lookback_period: int = 20,
        breakout_threshold: float = 0.002,  # 0.2 % beyond the range to confirm breakout
        rsi_period: int = 14,
        rsi_overbought: float = 75.0,
        rsi_oversold: float = 25.0,
    ):
        """Initialise the Breakout strategy.

        Args:
            lookback_period:      Number of price samples that define the recent range.
            breakout_threshold:   Fractional distance the price must exceed the range
                                  boundary to confirm a breakout (default 0.2 %).
            rsi_period:           RSI look-back period (default 14).
            rsi_overbought:       RSI level above which an upward breakout is blocked
                                  (market is already exhausted upward).
            rsi_oversold:         RSI level below which a downward breakout is blocked
                                  (market is already exhausted downward).
        """
        super().__init__("Breakout")
        self.lookback_period = lookback_period
        self.breakout_threshold = Decimal(str(breakout_threshold))
        self.rsi_period = rsi_period
        self.rsi_overbought = Decimal(str(rsi_overbought))
        self.rsi_oversold = Decimal(str(rsi_oversold))

        # Per-symbol state
        self.price_history: dict[str, deque[Decimal]] = {}
        self.rsi_indicator: dict[str, RSI] = {}

    async def analyze(
        self,
        symbol: str,
        market_data: MarketData,
        positions: list[Position],
        portfolio_value: Decimal,
    ) -> Signal | None:
        """Generate breakout signals when price moves decisively outside the recent range.

        Args:
            symbol:          Trading pair symbol (e.g. "BTC-EUR").
            market_data:     Current OHLCV and order book snapshot.
            positions:       Open positions for this symbol.
            portfolio_value: Total portfolio value (for context, not used in sizing here).

        Returns:
            Signal if a breakout is detected, None otherwise.
        """

        # Initialise per-symbol state on first call
        if symbol not in self.price_history:
            self.price_history[symbol] = deque(maxlen=self.lookback_period)
            self.rsi_indicator[symbol] = RSI(self.rsi_period)

        current_price = market_data.last
        rsi = self.rsi_indicator[symbol].update(current_price)

        # Need a full prior-history window AND a warmed-up RSI before producing signals.
        # We check length BEFORE appending so that rolling_high/low are computed from the
        # *established* range — the current bar is the breakout candidate, not part of the range.
        if (
            len(self.price_history[symbol]) < self.lookback_period
            or not self.rsi_indicator[symbol].is_ready
        ):
            self.price_history[symbol].append(current_price)
            logger.debug(
                f"{symbol}: Breakout strategy warming up "
                f"({len(self.price_history[symbol])}/{self.lookback_period} prices, "
                f"RSI ready={self.rsi_indicator[symbol].is_ready})"
            )
            return None

        # Compute range from the established window (prior bars only)
        prices = list(self.price_history[symbol])
        rolling_high = max(prices)
        rolling_low = min(prices)

        # Now slide the window forward to include the current bar
        self.price_history[symbol].append(current_price)

        # Breakout levels: price must exceed the range by at least the threshold
        breakout_high = rolling_high * (Decimal("1") + self.breakout_threshold)
        breakout_low = rolling_low * (Decimal("1") - self.breakout_threshold)

        # Find existing position for this symbol
        existing_position = None
        for pos in positions:
            if pos.symbol == symbol:
                existing_position = pos
                break

        signal_type = "HOLD"
        strength = 0.0
        reason = ""

        if current_price > breakout_high and rsi < self.rsi_overbought:
            if not existing_position or existing_position.side == OrderSide.SELL:
                signal_type = "BUY"
                # Strength: 0.5 right at the breakout level, scales toward 1.0
                # as price extends further beyond it.
                excess = (current_price - breakout_high) / breakout_high
                strength = min(
                    1.0,
                    0.5 + 0.5 * float(excess) / float(self.breakout_threshold),
                )
                reason = (
                    f"Upward breakout: {current_price:.2f} > rolling high {rolling_high:.2f} "
                    f"(+{self.breakout_threshold:.2%} buffer), RSI {rsi:.1f}"
                )

        elif current_price < breakout_low and rsi > self.rsi_oversold:
            if not existing_position or existing_position.side == OrderSide.BUY:
                signal_type = "SELL"
                excess = (breakout_low - current_price) / breakout_low
                strength = min(
                    1.0,
                    0.5 + 0.5 * float(excess) / float(self.breakout_threshold),
                )
                reason = (
                    f"Downward breakout: {current_price:.2f} < rolling low {rolling_low:.2f} "
                    f"(-{self.breakout_threshold:.2%} buffer), RSI {rsi:.1f}"
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
                "rolling_high": float(rolling_high),
                "rolling_low": float(rolling_low),
                "breakout_high": float(breakout_high),
                "breakout_low": float(breakout_low),
                "rsi": float(rsi),
                "current_price": float(current_price),
            },
        )

    def get_parameters(self) -> dict[str, Any]:
        """Return strategy parameters for logging and monitoring."""
        return {
            "strategy": self.name,
            "lookback_period": self.lookback_period,
            "breakout_threshold": float(self.breakout_threshold),
            "rsi_period": self.rsi_period,
            "rsi_overbought": float(self.rsi_overbought),
            "rsi_oversold": float(self.rsi_oversold),
        }
