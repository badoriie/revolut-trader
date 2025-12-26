from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

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
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    opened_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def update_price(self, new_price: Decimal):
        """Update current price and calculate unrealized PnL."""
        self.current_price = new_price
        self.updated_at = datetime.utcnow()

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

    order_id: Optional[str] = None
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    price: Optional[Decimal] = None
    filled_quantity: Decimal = Decimal("0")
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    strategy: Optional[str] = None


class Trade(BaseModel):
    """Trade execution model."""

    trade_id: str
    order_id: str
    symbol: str
    side: OrderSide
    quantity: Decimal
    price: Decimal
    commission: Decimal = Decimal("0")
    executed_at: datetime = Field(default_factory=datetime.utcnow)


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
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict = Field(default_factory=dict)


class PortfolioSnapshot(BaseModel):
    """Portfolio state snapshot."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    total_value: Decimal
    cash_balance: Decimal
    positions_value: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    total_pnl: Decimal
    daily_pnl: Decimal
    num_positions: int
