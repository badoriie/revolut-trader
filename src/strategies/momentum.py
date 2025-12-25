from collections import deque
from decimal import Decimal

from loguru import logger

from src.data.models import MarketData, OrderSide, Position, Signal
from src.strategies.base_strategy import BaseStrategy


class MomentumStrategy(BaseStrategy):
    """
    Momentum Trading Strategy: Follows price trends using moving averages
    and RSI indicator.
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

        # Price history for calculations
        self.price_history: dict[str, deque[Decimal]] = {}

    async def analyze(
        self,
        symbol: str,
        market_data: MarketData,
        positions: list[Position],
        portfolio_value: Decimal,
    ) -> Signal | None:
        """Generate momentum signals based on moving averages and RSI."""

        # Initialize price history for symbol if needed
        if symbol not in self.price_history:
            self.price_history[symbol] = deque(maxlen=max(self.slow_period, self.rsi_period))

        # Add current price to history
        current_price = market_data.last
        self.price_history[symbol].append(current_price)

        # Need enough data for analysis
        if len(self.price_history[symbol]) < self.slow_period:
            logger.debug(
                f"{symbol}: Insufficient data {len(self.price_history[symbol])}/{self.slow_period}"
            )
            return None

        prices = list(self.price_history[symbol])

        # Calculate moving averages
        fast_ma = sum(prices[-self.fast_period :]) / Decimal(self.fast_period)
        slow_ma = sum(prices[-self.slow_period :]) / Decimal(self.slow_period)

        # Calculate RSI
        rsi = self._calculate_rsi(prices[-self.rsi_period :])

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

    def _calculate_rsi(self, prices: list[Decimal]) -> Decimal:
        """Calculate Relative Strength Index."""
        if len(prices) < 2:
            return Decimal("50")

        gains = []
        losses = []

        for i in range(1, len(prices)):
            change = prices[i] - prices[i - 1]
            if change > 0:
                gains.append(change)
                losses.append(Decimal("0"))
            else:
                gains.append(Decimal("0"))
                losses.append(abs(change))

        avg_gain = sum(gains) / Decimal(len(gains)) if gains else Decimal("0")
        avg_loss = sum(losses) / Decimal(len(losses)) if losses else Decimal("0")

        if avg_loss == 0:
            return Decimal("100")

        rs = avg_gain / avg_loss
        rsi = Decimal("100") - (Decimal("100") / (Decimal("1") + rs))

        return rsi

    def get_parameters(self) -> dict:
        return {
            "strategy": self.name,
            "fast_period": self.fast_period,
            "slow_period": self.slow_period,
            "rsi_period": self.rsi_period,
            "rsi_overbought": self.rsi_overbought,
            "rsi_oversold": self.rsi_oversold,
        }
