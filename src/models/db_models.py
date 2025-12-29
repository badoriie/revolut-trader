"""SQLAlchemy database models for trading data persistence.

Uses SQLAlchemy for database abstraction - easy to migrate from SQLite to PostgreSQL.
"""

from datetime import UTC, datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


class PortfolioSnapshotDB(Base):
    """Portfolio snapshot time-series data."""

    __tablename__ = "portfolio_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    total_value = Column(Float, nullable=False)
    cash_balance = Column(Float, nullable=False)
    positions_value = Column(Float, nullable=False)
    unrealized_pnl = Column(Float, nullable=True)
    realized_pnl = Column(Float, nullable=True)
    total_pnl = Column(Float, nullable=False)
    daily_pnl = Column(Float, nullable=True)
    num_positions = Column(Integer, nullable=False)
    strategy = Column(String(50), nullable=True)
    risk_level = Column(String(20), nullable=True)
    trading_mode = Column(String(20), nullable=True)

    __table_args__ = (
        Index("idx_timestamp_desc", timestamp.desc()),
        Index("idx_strategy_timestamp", "strategy", "timestamp"),
    )

    def __repr__(self) -> str:
        return (
            f"<PortfolioSnapshot(timestamp={self.timestamp}, "
            f"total_value={self.total_value}, pnl={self.total_pnl})>"
        )


class TradeDB(Base):
    """Individual trade records."""

    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String(100), unique=True, nullable=False)
    symbol = Column(String(20), nullable=False, index=True)
    side = Column(String(10), nullable=False)  # BUY/SELL
    order_type = Column(String(20), nullable=False)  # MARKET/LIMIT
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    filled_quantity = Column(Float, nullable=False)
    status = Column(String(20), nullable=False)
    strategy = Column(String(50), nullable=True)
    created_at = Column(DateTime, nullable=False, index=True)
    filled_at = Column(DateTime, nullable=True)
    pnl = Column(Float, nullable=True)  # Realized P&L for closed trades

    __table_args__ = (
        Index("idx_symbol_created", "symbol", "created_at"),
        Index("idx_created_desc", created_at.desc()),
        Index("idx_status", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<Trade(order_id={self.order_id}, symbol={self.symbol}, "
            f"side={self.side}, quantity={self.quantity}, price={self.price})>"
        )


class SessionDB(Base):
    """Bot trading session records."""

    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    started_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    ended_at = Column(DateTime, nullable=True)
    strategy = Column(String(50), nullable=False)
    risk_level = Column(String(20), nullable=False)
    trading_mode = Column(String(20), nullable=False)
    trading_pairs = Column(Text, nullable=False)  # JSON array
    initial_balance = Column(Float, nullable=False)
    final_balance = Column(Float, nullable=True)
    total_trades = Column(Integer, default=0)
    total_pnl = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default="ACTIVE")  # ACTIVE/STOPPED/CRASHED

    __table_args__ = (Index("idx_started_desc", started_at.desc()),)

    def __repr__(self) -> str:
        return (
            f"<Session(id={self.id}, started={self.started_at}, "
            f"strategy={self.strategy}, status={self.status})>"
        )


def create_db_engine(database_url: str = "sqlite:///data/trading.db"):
    """Create database engine.

    Args:
        database_url: Database connection string
            - SQLite: "sqlite:///data/trading.db"
            - PostgreSQL: "postgresql://user:password@localhost/trading"
            - PostgreSQL (async): "postgresql+asyncpg://user:password@localhost/trading"

    Returns:
        SQLAlchemy engine
    """
    engine = create_engine(
        database_url,
        echo=False,  # Set to True for SQL query logging
        pool_pre_ping=True,  # Verify connections before using
    )
    return engine


def init_database(engine):
    """Initialize database schema.

    Creates all tables if they don't exist.
    Safe to call multiple times (idempotent).
    """
    Base.metadata.create_all(engine)


def get_session_factory(engine):
    """Create session factory for database operations.

    Returns:
        SQLAlchemy sessionmaker
    """
    return sessionmaker(bind=engine)
