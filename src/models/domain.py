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
    CONDITIONAL = "CONDITIONAL"  # Revolut: trigger-based order (was STOP_LOSS)
    TPSL = "TPSL"  # Revolut: take-profit / stop-loss order (was TAKE_PROFIT)


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    REPLACED = "REPLACED"  # Revolut: order replaced by another


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
        """Check if position should be closed based on stop loss or take profit.

        BUY (long): stop loss triggers when price falls to or below the stop level;
                    take profit triggers when price rises to or above the target.
        SELL (short): stop loss triggers when price rises to or above the stop level
                      (the loss side is up for a short); take profit triggers when
                      price falls to or below the target.
        """
        if self.side == OrderSide.BUY:
            if self.stop_loss is not None and self.current_price <= self.stop_loss:
                return True, "stop_loss"
            if self.take_profit is not None and self.current_price >= self.take_profit:
                return True, "take_profit"
        else:  # SELL (short)
            if self.stop_loss is not None and self.current_price >= self.stop_loss:
                return True, "stop_loss"
            if self.take_profit is not None and self.current_price <= self.take_profit:
                return True, "take_profit"

        return False, ""


class Order(BaseModel):
    """Order model.

    Field mapping to Revolut X API:
      order_id          → venue_order_id (system-assigned UUID)
      client_order_id   → client_order_id (caller-assigned UUID sent at creation)
      leaves_quantity   → leaves_quantity (unfilled remainder)
      quote_quantity    → quote_quantity (size in quote currency)
      average_fill_price → average_fill_price (qty-weighted avg execution price)
      reject_reason     → reject_reason (only present when status=REJECTED)
      time_in_force     → time_in_force ("gtc" | "ioc" | "fok")
      execution_instructions → execution_instructions (["allow_taker"] | ["post_only"])
      completed_at      → completed_date (unix ms; mapped to datetime here)
    """

    order_id: str | None = None  # venue_order_id
    client_order_id: str | None = None
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    price: Decimal | None = None
    filled_quantity: Decimal = Decimal("0")
    leaves_quantity: Decimal | None = None
    quote_quantity: Decimal | None = None
    average_fill_price: Decimal | None = None
    status: OrderStatus = OrderStatus.PENDING
    reject_reason: str | None = None
    time_in_force: str | None = None
    execution_instructions: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    strategy: str | None = None
    commission: Decimal = Decimal("0")
    realized_pnl: Decimal | None = None


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


class ShutdownSummary(BaseModel):
    """Summary of actions taken during graceful shutdown.

    Returned by ``OrderExecutor.graceful_shutdown()`` so the bot can log
    what happened and update its cash balance for any closed positions.

    Guarantee: after ``graceful_shutdown()`` returns, ALL bot-opened positions
    are closed.  ``positions_closed`` equals ``positions_evaluated``.

    All monetary fields use ``Decimal`` — never ``float``.
    """

    orders_cancelled: int
    positions_evaluated: int
    positions_closed: int  # always == positions_evaluated after shutdown
    positions_trailing_stopped: int  # subset of positions_closed: closed via trailing stop
    closed_positions_pnl: Decimal = Decimal("0")  # immediate closes (losers)
    trailing_stopped_pnl: Decimal = Decimal("0")  # trailing-stop closes (winners/breakeven)
    filled_close_orders: list["Order"] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


# API Response Models for validation


class OrderBookEntry(BaseModel):
    """Single order book level from the Revolut X API.

    API shape:
      aid  — asset ID (e.g. "BTC")
      anm  — asset name (e.g. "Bitcoin")
      s    — side: "SELL" for asks; "BUY" (authenticated) or "BUYI" (public) for bids
      p    — price as string
      pc   — price currency (e.g. "EUR")
      q    — quantity as string
      qc   — quantity currency (e.g. "BTC")
      no   — number of orders at this level
      ts   — trading system type (e.g. "CLOB")
      pdt  — timestamp (unix ms for authenticated, ISO-8601 string for public)
    """

    p: str  # Price (required)
    q: str  # Quantity (required)
    aid: str | None = None  # Asset ID
    anm: str | None = None  # Asset name
    s: str | None = None  # Side: "SELL" or "BUY"
    pc: str | None = None  # Price currency
    qc: str | None = None  # Quantity currency
    no: str | None = None  # Number of orders at this level
    ts: str | None = None  # Trading system type
    pdt: int | str | None = None  # Timestamp (unix ms or ISO-8601 string)

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
    """Balance data matching the Revolut X API response.

    API shape: {"currency": "BTC", "available": "1.25", "reserved": "0.10", "staked": "0", "total": "1.35"}
    """

    currency: str
    available: str
    reserved: str = "0"
    staked: str = "0"
    total: str

    @property
    def available_decimal(self) -> Decimal:
        """Available balance as Decimal."""
        return Decimal(self.available)

    @property
    def total_decimal(self) -> Decimal:
        """Total balance (available + reserved + staked) as Decimal."""
        return Decimal(self.total)


class BalanceResponse(BaseModel):
    """Revolut X API balance response.

    The API returns a JSON array directly (no wrapper object):
      GET /balances → [BalanceData, ...]
    The API client parses this manually; this model is a typed reference.
    """

    balances: list[BalanceData] = Field(default_factory=list)


class CandleData(BaseModel):
    """Historical candle data.

    API shape (GET /candles/{symbol}):
      All price and volume fields are returned as strings.
    """

    start: int  # Timestamp (Unix epoch ms)
    open: str  # Open price
    high: str  # High price
    low: str  # Low price
    close: str  # Close price
    volume: str  # Volume

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
    """Single item in the order creation response array.

    API shape: {"venue_order_id": "<uuid>", "client_order_id": "<uuid>", "state": "new"}
    """

    venue_order_id: str
    client_order_id: str
    state: str


class OrderCreationResponse(BaseModel):
    """Revolut X API order creation response.

    API returns: {"data": [OrderCreationData]}  (always a single-element list)
    """

    data: list[OrderCreationData]
