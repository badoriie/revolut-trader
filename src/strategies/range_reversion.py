from decimal import Decimal
from typing import Any

from loguru import logger

from src.models.domain import MarketData, OrderSide, Position, Signal
from src.strategies.base_strategy import BaseStrategy
from src.utils.indicators import RSI


class RangeReversionStrategy(BaseStrategy):
    """
    Daily Range Reversion Strategy: buys near the 24h low, sells near the 24h high.

    Exploits the mean-reverting tendency of intraday crypto prices.  The 24h high
    and low are read directly from MarketData (no extra API calls required).  RSI
    provides confirmation to avoid entering into a continued trend.

    Entry logic:
    - BUY  when range_position ≤ buy_zone  AND RSI ≤ rsi_confirmation_oversold
    - SELL when range_position ≥ sell_zone AND RSI ≥ rsi_confirmation_overbought

    where range_position = (price − low_24h) / (high_24h − low_24h),
    0.0 = at the daily low, 1.0 = at the daily high.

    Signal strength scales with both depth inside the zone and RSI confirmation
    intensity.  The minimum daily range requirement filters out data anomalies and
    extremely flat, illiquid markets.

    Best suited for ranging (non-trending) markets.  In strongly trending markets,
    consider using Momentum or Breakout instead.

    All tunable parameters are loaded from the ``revolut-trader-strategy-range_reversion``
    1Password item at startup so users can calibrate without changing code.
    When a field is absent from 1Password the constructor default is used.
    """

    def __init__(
        self,
        buy_zone: float = 0.20,
        sell_zone: float = 0.80,
        rsi_period: int = 7,
        rsi_confirmation_oversold: float = 40.0,
        rsi_confirmation_overbought: float = 60.0,
        min_range_pct: float = 0.01,  # Skip if 24h range < 1 % of price
    ):
        """Initialise the Range Reversion strategy.

        Args:
            buy_zone:                    Trade buy signals in the bottom fraction of the
                                         daily range (default 20 %).
            sell_zone:                   Trade sell signals in the top fraction of the
                                         daily range (default 80 %).
            rsi_period:                  RSI look-back period (short period for intraday
                                         responsiveness, default 7).
            rsi_confirmation_oversold:   RSI must be at or below this level to confirm a
                                         buy (default 40 — moderately oversold).
            rsi_confirmation_overbought: RSI must be at or above this level to confirm a
                                         sell (default 60 — moderately overbought).
            min_range_pct:               Minimum daily range as a fraction of the current
                                         price.  Prevents signals in artificially flat
                                         or illiquid markets (default 1 %).
        """
        super().__init__("Range Reversion")

        # Load calibration overrides from 1Password (via settings.strategy_configs).
        from src.config import settings

        scfg = settings.strategy_configs.get("range_reversion")

        self.buy_zone = Decimal(
            str(scfg.buy_zone if scfg and scfg.buy_zone is not None else buy_zone)
        )
        self.sell_zone = Decimal(
            str(scfg.sell_zone if scfg and scfg.sell_zone is not None else sell_zone)
        )
        self.rsi_period = scfg.rsi_period if scfg and scfg.rsi_period is not None else rsi_period
        self.rsi_confirmation_oversold = Decimal(
            str(
                scfg.rsi_confirmation_oversold
                if scfg and scfg.rsi_confirmation_oversold is not None
                else rsi_confirmation_oversold
            )
        )
        self.rsi_confirmation_overbought = Decimal(
            str(
                scfg.rsi_confirmation_overbought
                if scfg and scfg.rsi_confirmation_overbought is not None
                else rsi_confirmation_overbought
            )
        )
        self.min_range_pct = Decimal(
            str(scfg.min_range_pct if scfg and scfg.min_range_pct is not None else min_range_pct)
        )

        # Per-symbol RSI state
        self.rsi_indicator: dict[str, RSI] = {}

    def _compute_buy_signal(
        self,
        range_position: Decimal,
        rsi: Decimal,
        current_price: Decimal,
        low_24h: Decimal,
    ) -> tuple[float, str]:
        """Compute buy signal strength and reason.

        Args:
            range_position: Normalised position within the daily range (0–1).
            rsi:            Current RSI value.
            current_price:  Current market price.
            low_24h:        24-hour low price.

        Returns:
            ``(strength, reason)`` tuple.
        """
        position_score = float(
            (self.buy_zone - range_position) / self.buy_zone if self.buy_zone > 0 else Decimal("0")
        )
        rsi_score = float(
            (self.rsi_confirmation_oversold - rsi) / self.rsi_confirmation_oversold
            if self.rsi_confirmation_oversold > 0
            else Decimal("0")
        )
        strength = min(1.0, max(0.1, (position_score + rsi_score) / 2))
        reason = (
            f"Price at {float(range_position):.0%} of daily range "
            f"({current_price:.2f} near 24h low {low_24h:.2f}), RSI {rsi:.1f}"
        )
        return strength, reason

    def _compute_sell_signal(
        self,
        range_position: Decimal,
        rsi: Decimal,
        current_price: Decimal,
        high_24h: Decimal,
    ) -> tuple[float, str]:
        """Compute sell signal strength and reason.

        Args:
            range_position: Normalised position within the daily range (0–1).
            rsi:            Current RSI value.
            current_price:  Current market price.
            high_24h:       24-hour high price.

        Returns:
            ``(strength, reason)`` tuple.
        """
        one = Decimal("1")
        hundred = Decimal("100")
        sell_width = one - self.sell_zone
        position_score = float(
            (range_position - self.sell_zone) / sell_width if sell_width > 0 else Decimal("0")
        )
        rsi_width = hundred - self.rsi_confirmation_overbought
        rsi_score = float(
            (rsi - self.rsi_confirmation_overbought) / rsi_width if rsi_width > 0 else Decimal("0")
        )
        strength = min(1.0, max(0.1, (position_score + rsi_score) / 2))
        reason = (
            f"Price at {float(range_position):.0%} of daily range "
            f"({current_price:.2f} near 24h high {high_24h:.2f}), RSI {rsi:.1f}"
        )
        return strength, reason

    async def analyze(
        self,
        symbol: str,
        market_data: MarketData,
        positions: list[Position],
        portfolio_value: Decimal,
    ) -> Signal | None:
        """Generate signals based on where the current price sits within the 24h range.

        Args:
            symbol:          Trading pair symbol (e.g. "BTC-EUR").
            market_data:     Current market snapshot — must include high_24h and low_24h.
            positions:       Open positions for this symbol.
            portfolio_value: Total portfolio value (context only).

        Returns:
            Signal if price is in a buy/sell zone with RSI confirmation, None otherwise.
        """
        if symbol not in self.rsi_indicator:
            self.rsi_indicator[symbol] = RSI(self.rsi_period)

        current_price = market_data.last
        rsi = self.rsi_indicator[symbol].update(current_price)

        if not self.rsi_indicator[symbol].is_ready:
            logger.debug(f"{symbol}: Range Reversion RSI warming up...")
            return None

        high_24h = market_data.high_24h
        low_24h = market_data.low_24h
        daily_range = high_24h - low_24h

        if daily_range <= Decimal("0") or (daily_range / current_price) < self.min_range_pct:
            logger.debug(
                f"{symbol}: Daily range {daily_range / current_price:.2%} "
                f"below min_range_pct {self.min_range_pct:.2%}"
            )
            return None

        range_position = (current_price - low_24h) / daily_range
        existing_position = next((p for p in positions if p.symbol == symbol), None)

        signal_type = "HOLD"
        strength = 0.0
        reason = ""

        if range_position <= self.buy_zone and rsi <= self.rsi_confirmation_oversold:
            if not existing_position or existing_position.side == OrderSide.SELL:
                signal_type = "BUY"
                strength, reason = self._compute_buy_signal(
                    range_position, rsi, current_price, low_24h
                )
        elif (
            range_position >= self.sell_zone
            and rsi >= self.rsi_confirmation_overbought
            and (not existing_position or existing_position.side == OrderSide.BUY)
        ):
            signal_type = "SELL"
            strength, reason = self._compute_sell_signal(
                range_position, rsi, current_price, high_24h
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
                "range_position": float(range_position),
                "high_24h": float(high_24h),
                "low_24h": float(low_24h),
                "daily_range": float(daily_range),
                "rsi": float(rsi),
                "buy_zone": float(self.buy_zone),
                "sell_zone": float(self.sell_zone),
            },
        )

    def get_parameters(self) -> dict[str, Any]:
        """Return strategy parameters for logging and monitoring."""
        return {
            "strategy": self.name,
            "buy_zone": float(self.buy_zone),
            "sell_zone": float(self.sell_zone),
            "rsi_period": self.rsi_period,
            "rsi_confirmation_oversold": float(self.rsi_confirmation_oversold),
            "rsi_confirmation_overbought": float(self.rsi_confirmation_overbought),
            "min_range_pct": float(self.min_range_pct),
        }
