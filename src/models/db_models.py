"""SQLAlchemy database models for trading data persistence (SQLite)."""

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
        Index("idx_portfolio_timestamp_desc", timestamp.desc()),
        Index("idx_portfolio_strategy_timestamp", "strategy", "timestamp"),
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
        Index("idx_trade_symbol_created", "symbol", "created_at"),
        Index("idx_trade_created_desc", created_at.desc()),
        Index("idx_trade_status", "status"),
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

    __table_args__ = (Index("idx_session_started_desc", started_at.desc()),)

    def __repr__(self) -> str:
        return (
            f"<Session(id={self.id}, started={self.started_at}, "
            f"strategy={self.strategy}, status={self.status})>"
        )


class BacktestRunDB(Base):
    """Backtest run records with configuration and results."""

    __tablename__ = "backtest_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    strategy = Column(String(50), nullable=False)
    risk_level = Column(String(20), nullable=False)
    symbols = Column(Text, nullable=False)  # JSON array
    days = Column(Integer, nullable=False)
    interval = Column(String(10), nullable=False)
    initial_capital = Column(Float, nullable=False)

    # Results
    final_capital = Column(Float, nullable=False)
    total_pnl = Column(Float, nullable=False)
    return_pct = Column(Float, nullable=False)
    total_trades = Column(Integer, nullable=False)
    winning_trades = Column(Integer, nullable=False)
    losing_trades = Column(Integer, nullable=False)
    win_rate = Column(Float, nullable=False)
    profit_factor = Column(Float, nullable=True)
    max_drawdown = Column(Float, nullable=False)
    sharpe_ratio = Column(Float, nullable=True)

    # Storage paths (for detailed data)
    equity_curve_file = Column(String(255), nullable=True)  # Path to equity curve JSON
    trades_file = Column(String(255), nullable=True)  # Path to trades JSON

    __table_args__ = (
        Index("idx_backtest_run_at_desc", run_at.desc()),
        Index("idx_backtest_strategy_run_at", "strategy", "run_at"),
        Index("idx_backtest_symbols", "symbols"),
    )

    def __repr__(self) -> str:
        return (
            f"<BacktestRun(id={self.id}, strategy={self.strategy}, "
            f"return={self.return_pct:.2f}%, trades={self.total_trades})>"
        )


class LogEntryDB(Base):
    """Optional log storage in database for critical events."""

    __tablename__ = "log_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    level = Column(String(10), nullable=False)  # INFO, WARNING, ERROR, CRITICAL
    module = Column(String(100), nullable=True)
    message = Column(Text, nullable=False)
    session_id = Column(Integer, nullable=True)  # Link to session if applicable

    __table_args__ = (
        Index("idx_log_timestamp_desc", timestamp.desc()),
        Index("idx_log_level_timestamp", "level", "timestamp"),
        Index("idx_log_session", "session_id"),
    )

    def __repr__(self) -> str:
        return f"<LogEntry(id={self.id}, level={self.level}, timestamp={self.timestamp})>"


DB_URL = "sqlite:///data/trading.db"


def create_db_engine():
    """Create SQLite database engine."""
    return create_engine(DB_URL, echo=False)


def init_database(engine) -> None:
    """Create all tables if they don't exist (idempotent)."""
    Base.metadata.create_all(engine)


def get_session_factory(engine):
    """Create session factory for database operations."""
    return sessionmaker(bind=engine)
