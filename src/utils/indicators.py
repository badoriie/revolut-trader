"""Technical indicators with optimized implementations."""

from decimal import Decimal


class EMA:
    """Exponential Moving Average - O(1) update instead of O(n).

    EMA gives more weight to recent prices and updates incrementally,
    making it much faster than Simple Moving Average (SMA).
    """

    def __init__(self, period: int):
        """Initialize EMA calculator.

        Args:
            period: Number of periods (e.g., 10 for 10-period EMA)
        """
        self.period = period
        self.multiplier = Decimal(2) / Decimal(period + 1)
        self.ema: Decimal | None = None
        self._warmup_prices: list[Decimal] = []
        self._warmup_complete = False

    def update(self, price: Decimal) -> Decimal:
        """Update EMA with new price (O(1) operation).

        Args:
            price: New price to add

        Returns:
            Current EMA value
        """
        if not self._warmup_complete:
            # Collect initial prices for warm-up
            self._warmup_prices.append(price)

            if len(self._warmup_prices) >= self.period:
                # Initialize with SMA of warm-up period
                self.ema = sum(self._warmup_prices) / Decimal(len(self._warmup_prices))
                self._warmup_complete = True
                self._warmup_prices.clear()  # Free memory
            else:
                # Return current average during warm-up
                return sum(self._warmup_prices) / Decimal(len(self._warmup_prices))

        # Standard EMA calculation: EMA = Price * k + EMA(previous) * (1 - k)
        # where k = 2 / (period + 1)
        self.ema = (price * self.multiplier) + (self.ema * (Decimal(1) - self.multiplier))

        return self.ema

    @property
    def value(self) -> Decimal | None:
        """Get current EMA value without updating."""
        return self.ema

    @property
    def is_ready(self) -> bool:
        """Check if EMA has enough data to be reliable."""
        return self._warmup_complete

    def reset(self):
        """Reset the EMA calculator."""
        self.ema = None
        self._warmup_prices.clear()
        self._warmup_complete = False


class RSI:
    """Relative Strength Index with optimized calculation.

    Uses Wilder's smoothing method with exponential moving averages
    for O(1) updates instead of recalculating from scratch.
    """

    def __init__(self, period: int = 14):
        """Initialize RSI calculator.

        Args:
            period: Number of periods for RSI calculation (default: 14)
        """
        self.period = period
        self.prev_price: Decimal | None = None
        self.avg_gain: Decimal | None = None
        self.avg_loss: Decimal | None = None
        self._warmup_gains: list[Decimal] = []
        self._warmup_losses: list[Decimal] = []
        self._warmup_complete = False

    def update(self, price: Decimal) -> Decimal:
        """Update RSI with new price (O(1) operation).

        Args:
            price: New price to add

        Returns:
            Current RSI value (0-100)
        """
        # Need at least 2 prices to calculate change
        if self.prev_price is None:
            self.prev_price = price
            return Decimal("50")  # Neutral RSI during initialization

        # Calculate price change
        change = price - self.prev_price
        gain = max(change, Decimal("0"))
        loss = max(-change, Decimal("0"))

        if not self._warmup_complete:
            # Collect initial gains/losses for warm-up
            self._warmup_gains.append(gain)
            self._warmup_losses.append(loss)

            if len(self._warmup_gains) >= self.period:
                # Initialize with simple averages
                self.avg_gain = sum(self._warmup_gains) / Decimal(self.period)
                self.avg_loss = sum(self._warmup_losses) / Decimal(self.period)
                self._warmup_complete = True
                self._warmup_gains.clear()
                self._warmup_losses.clear()
            else:
                # Return neutral during warm-up
                self.prev_price = price
                return Decimal("50")

        # Wilder's smoothing: avg = (prev_avg * (period - 1) + current) / period
        self.avg_gain = (self.avg_gain * Decimal(self.period - 1) + gain) / Decimal(self.period)
        self.avg_loss = (self.avg_loss * Decimal(self.period - 1) + loss) / Decimal(self.period)

        # Calculate RS and RSI
        if self.avg_loss == 0:
            rsi = Decimal("100")
        else:
            rs = self.avg_gain / self.avg_loss
            rsi = Decimal("100") - (Decimal("100") / (Decimal("1") + rs))

        self.prev_price = price
        return rsi

    @property
    def value(self) -> Decimal | None:
        """Get current RSI value without updating."""
        if not self._warmup_complete or self.avg_loss is None:
            return None

        if self.avg_loss == 0:
            return Decimal("100")

        rs = self.avg_gain / self.avg_loss
        return Decimal("100") - (Decimal("100") / (Decimal("1") + rs))

    @property
    def is_ready(self) -> bool:
        """Check if RSI has enough data to be reliable."""
        return self._warmup_complete

    def reset(self):
        """Reset the RSI calculator."""
        self.prev_price = None
        self.avg_gain = None
        self.avg_loss = None
        self._warmup_gains.clear()
        self._warmup_losses.clear()
        self._warmup_complete = False
