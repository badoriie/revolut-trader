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
        self.buy_zone = Decimal(str(buy_zone))
        self.sell_zone = Decimal(str(sell_zone))
        self.rsi_period = rsi_period
        self.rsi_confirmation_oversold = Decimal(str(rsi_confirmation_oversold))
        self.rsi_confirmation_overbought = Decimal(str(rsi_confirmation_overbought))
        self.min_range_pct = Decimal(str(min_range_pct))

        # Per-symbol RSI state
        self.rsi_indicator: dict[str, RSI] = {}

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

        # Initialise per-symbol RSI on first call
        if symbol not in self.rsi_indicator:
            self.rsi_indicator[symbol] = RSI(self.rsi_period)

        current_price = market_data.last
        rsi = self.rsi_indicator[symbol].update(current_price)

        # Wait for RSI to warm up
        if not self.rsi_indicator[symbol].is_ready:
            logger.debug(f"{symbol}: Range Reversion RSI warming up...")
            return None

        high_24h = market_data.high_24h
        low_24h = market_data.low_24h
        daily_range = high_24h - low_24h

        # Guard: require a meaningful daily range
        if daily_range <= Decimal("0") or (daily_range / current_price) < self.min_range_pct:
            logger.debug(
                f"{symbol}: Daily range {daily_range / current_price:.2%} "
                f"below min_range_pct {self.min_range_pct:.2%}"
            )
            return None

        # Normalised position: 0.0 = at daily low, 1.0 = at daily high
        range_position = (current_price - low_24h) / daily_range

        # Find existing position
        existing_position = None
        for pos in positions:
            if pos.symbol == symbol:
                existing_position = pos
                break

        signal_type = "HOLD"
        strength = 0.0
        reason = ""

        if range_position <= self.buy_zone and rsi <= self.rsi_confirmation_oversold:
            if not existing_position or existing_position.side == OrderSide.SELL:
                signal_type = "BUY"
                # Depth into buy zone (0 at boundary, 1 at daily low)
                position_score = float(
                    (self.buy_zone - range_position) / self.buy_zone
                    if self.buy_zone > 0
                    else Decimal("0")
                )
                # RSI confirmation intensity (0 at threshold, 1 when RSI → 0)
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

        elif (
            range_position >= self.sell_zone
            and rsi >= self.rsi_confirmation_overbought
            and (not existing_position or existing_position.side == OrderSide.BUY)
        ):
            signal_type = "SELL"
            one = Decimal("1")
            hundred = Decimal("100")
            # Depth into sell zone (0 at boundary, 1 at daily high)
            sell_width = one - self.sell_zone
            position_score = float(
                (range_position - self.sell_zone) / sell_width if sell_width > 0 else Decimal("0")
            )
            # RSI confirmation intensity (0 at threshold, 1 when RSI → 100)
            rsi_width = hundred - self.rsi_confirmation_overbought
            rsi_score = float(
                (rsi - self.rsi_confirmation_overbought) / rsi_width
                if rsi_width > 0
                else Decimal("0")
            )
            strength = min(1.0, max(0.1, (position_score + rsi_score) / 2))
            reason = (
                f"Price at {float(range_position):.0%} of daily range "
                f"({current_price:.2f} near 24h high {high_24h:.2f}), RSI {rsi:.1f}"
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
