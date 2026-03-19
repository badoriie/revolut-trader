from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class Position(BaseModel):
    """Trading position model."""

    symbol: str
    side: OrderSide
    quantity: Decimal
    entry_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    opened_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def update_price(self, new_price: Decimal) -> None:
        """Update current price and calculate unrealized PnL."""
        self.current_price = new_price
        self.updated_at = datetime.now(UTC)

        if self.side == OrderSide.BUY:
            self.unrealized_pnl = (new_price - self.entry_price) * self.quantity
        else:
            self.unrealized_pnl = (self.entry_price - new_price) * self.quantity

    def should_close(self) -> tuple[bool, str]:
        """Check if position should be closed based on stop loss or take profit."""
        if self.stop_loss and self.current_price <= self.stop_loss:
            return True, "stop_loss"

        if self.take_profit and self.current_price >= self.take_profit:
            return True, "take_profit"

        return False, ""


class Order(BaseModel):
    """Order model."""

    order_id: str | None = None
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    price: Decimal | None = None
    filled_quantity: Decimal = Decimal("0")
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    strategy: str | None = None


class Trade(BaseModel):
    """Trade execution model."""

    trade_id: str
    order_id: str
    symbol: str
    side: OrderSide
    quantity: Decimal
    price: Decimal
    commission: Decimal = Decimal("0")
    executed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MarketData(BaseModel):
    """Market data snapshot."""

    symbol: str
    timestamp: datetime
    bid: Decimal
    ask: Decimal
    last: Decimal
    volume_24h: Decimal
    high_24h: Decimal
    low_24h: Decimal


class Signal(BaseModel):
    """Trading signal from strategy."""

    symbol: str
    strategy: str
    signal_type: str  # "BUY", "SELL", "HOLD"
    strength: float = Field(ge=0.0, le=1.0)
    price: Decimal
    reason: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class PortfolioSnapshot(BaseModel):
    """Portfolio state snapshot."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    total_value: Decimal
    cash_balance: Decimal
    positions_value: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    total_pnl: Decimal
    daily_pnl: Decimal
    num_positions: int


# API Response Models for validation


class OrderBookEntry(BaseModel):
    """Single order book entry (bid or ask)."""

    p: str  # Price
    q: str  # Quantity

    @property
    def price(self) -> Decimal:
        return Decimal(self.p)

    @property
    def quantity(self) -> Decimal:
        return Decimal(self.q)


class OrderBookData(BaseModel):
    """Order book data structure."""

    asks: list[OrderBookEntry] = Field(default_factory=list)
    bids: list[OrderBookEntry] = Field(default_factory=list)


class OrderBookResponse(BaseModel):
    """Revolut X API order book response."""

    data: OrderBookData


class BalanceData(BaseModel):
    """Balance data structure."""

    availableBalance: str
    totalBalance: str | None = None
    currency: str = "USD"

    @property
    def available(self) -> Decimal:
        return Decimal(self.availableBalance)

    @property
    def total(self) -> Decimal:
        if self.totalBalance:
            return Decimal(self.totalBalance)
        return self.available


class BalanceResponse(BaseModel):
    """Revolut X API balance response."""

    data: BalanceData | None = None
    # Direct response format (no data wrapper)
    availableBalance: str | None = None
    totalBalance: str | None = None
    currency: str | None = None


class CandleData(BaseModel):
    """Historical candle data."""

    start: int  # Timestamp
    open: str | float  # Open price (API may return string or float)
    high: str | float  # High price
    low: str | float  # Low price
    close: str | float  # Close price
    volume: str | float  # Volume

    @property
    def timestamp(self) -> int:
        return self.start

    @property
    def open_price(self) -> Decimal:
        return Decimal(str(self.open))

    @property
    def high_price(self) -> Decimal:
        return Decimal(str(self.high))

    @property
    def low_price(self) -> Decimal:
        return Decimal(str(self.low))

    @property
    def close_price(self) -> Decimal:
        return Decimal(str(self.close))

    @property
    def volume_decimal(self) -> Decimal:
        return Decimal(str(self.volume))


class CandleResponse(BaseModel):
    """Revolut X API candle response."""

    data: list[CandleData] = Field(default_factory=list)


class OrderCreationData(BaseModel):
    """Order creation response data."""

    orderId: str
    status: str
    symbol: str
    side: str
    quantity: str
    price: str | None = None


class OrderCreationResponse(BaseModel):
    """Revolut X API order creation response."""

    data: OrderCreationData
