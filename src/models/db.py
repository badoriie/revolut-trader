"""SQLAlchemy ORM models for SQLite persistence.

Design notes
------------
* Uses SQLAlchemy 2.0 declarative style (``Mapped`` / ``mapped_column``) for
  full static-type-checker support.
* All monetary columns use ``Numeric(precision=20, scale=10)`` so that no
  floating-point rounding errors are introduced when storing Decimal values.
* All timestamp columns are ``DateTime(timezone=True)`` — UTC datetimes are
  stored and retrieved without silent timezone stripping.
* The engine is configured with WAL journal mode, a 30-second busy timeout,
  and foreign-key enforcement — the three most important SQLite pragmas for a
  production application.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    create_engine,
    event,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

# ---------------------------------------------------------------------------
# Declarative base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


# ---------------------------------------------------------------------------
# ORM models
# ---------------------------------------------------------------------------


class PortfolioSnapshotDB(Base):
    """Time-series snapshots of portfolio state captured during live trading."""

    __tablename__ = "portfolio_snapshots"
    __table_args__ = (
        Index("idx_snapshot_timestamp", "timestamp"),
        Index("idx_snapshot_strategy_timestamp", "strategy", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_value: Mapped[float] = mapped_column(Numeric(20, 10), nullable=False)
    cash_balance: Mapped[float] = mapped_column(Numeric(20, 10), nullable=False)
    positions_value: Mapped[float] = mapped_column(Numeric(20, 10), nullable=False)
    unrealized_pnl: Mapped[float | None] = mapped_column(Numeric(20, 10), nullable=True)
    realized_pnl: Mapped[float | None] = mapped_column(Numeric(20, 10), nullable=True)
    total_pnl: Mapped[float] = mapped_column(Numeric(20, 10), nullable=False)
    daily_pnl: Mapped[float | None] = mapped_column(Numeric(20, 10), nullable=True)
    num_positions: Mapped[int] = mapped_column(Integer, nullable=False)
    # Plaintext categorical metadata — not sensitive, needed for SQL filtering
    strategy: Mapped[str | None] = mapped_column(String(50), nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    trading_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<PortfolioSnapshot(ts={self.timestamp}, "
            f"total={self.total_value}, pnl={self.total_pnl})>"
        )


class TradeDB(Base):
    """Individual fill records written after each executed order."""

    __tablename__ = "trades"
    __table_args__ = (
        Index("idx_trade_symbol_created", "symbol", "created_at"),
        Index("idx_trade_created", "created_at"),
        Index("idx_trade_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)  # BUY | SELL
    order_type: Mapped[str] = mapped_column(String(20), nullable=False)  # MARKET | LIMIT
    quantity: Mapped[float] = mapped_column(Numeric(20, 10), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(20, 10), nullable=False)
    filled_quantity: Mapped[float] = mapped_column(Numeric(20, 10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    strategy: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pnl: Mapped[float | None] = mapped_column(Numeric(20, 10), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<Trade(order_id={self.order_id}, symbol={self.symbol}, "
            f"side={self.side}, qty={self.quantity}, price={self.price})>"
        )


class SessionDB(Base):
    """Bot trading session lifecycle records."""

    __tablename__ = "sessions"
    __table_args__ = (Index("idx_session_started", "started_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    strategy: Mapped[str] = mapped_column(String(50), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    trading_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    # Stored as a Fernet-encrypted JSON array (reveals exact trading pairs — sensitive)
    trading_pairs: Mapped[str] = mapped_column(Text, nullable=False)
    initial_balance: Mapped[float] = mapped_column(Numeric(20, 10), nullable=False)
    final_balance: Mapped[Decimal | None] = mapped_column(Numeric(20, 10), nullable=True)
    total_trades: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_pnl: Mapped[Decimal | None] = mapped_column(Numeric(20, 10), nullable=True)
    # ACTIVE | STOPPED | CRASHED
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")

    def __repr__(self) -> str:
        return (
            f"<Session(id={self.id}, started={self.started_at}, "
            f"strategy={self.strategy}, status={self.status})>"
        )


class BacktestRunDB(Base):
    """Configuration and result summary for each backtest run."""

    __tablename__ = "backtest_runs"
    __table_args__ = (
        Index("idx_backtest_run_at", "run_at"),
        Index("idx_backtest_strategy_run_at", "strategy", "run_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    strategy: Mapped[str] = mapped_column(String(50), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    symbols: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array, plaintext
    days: Mapped[int] = mapped_column(Integer, nullable=False)
    interval: Mapped[str] = mapped_column(String(10), nullable=False)
    initial_capital: Mapped[float] = mapped_column(Numeric(20, 10), nullable=False)

    # Results
    final_capital: Mapped[float] = mapped_column(Numeric(20, 10), nullable=False)
    total_pnl: Mapped[float] = mapped_column(Numeric(20, 10), nullable=False)
    return_pct: Mapped[float] = mapped_column(Numeric(20, 10), nullable=False)
    total_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    winning_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    losing_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    win_rate: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    profit_factor: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    max_drawdown: Mapped[float] = mapped_column(Numeric(20, 10), nullable=False)
    sharpe_ratio: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<BacktestRun(id={self.id}, strategy={self.strategy}, "
            f"return={self.return_pct:.2f}%, trades={self.total_trades})>"
        )


class LogEntryDB(Base):
    """Critical event log stored in the database for post-mortem analysis."""

    __tablename__ = "log_entries"
    __table_args__ = (
        Index("idx_log_timestamp", "timestamp"),
        Index("idx_log_level_timestamp", "level", "timestamp"),
        Index("idx_log_session", "session_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    level: Mapped[str] = mapped_column(String(10), nullable=False)  # INFO|WARNING|ERROR|CRITICAL
    module: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Message may contain sensitive context — encrypted at the persistence layer
    message: Mapped[str] = mapped_column(Text, nullable=False)
    session_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"<LogEntry(id={self.id}, level={self.level}, ts={self.timestamp})>"


# ---------------------------------------------------------------------------
# Engine / session factory
# ---------------------------------------------------------------------------


def get_db_url(env: str | None = None) -> str:
    """Return the SQLite URL for the given environment.

    Args:
        env: Environment name (dev, int, prod).  Falls back to
             ``os.environ["ENVIRONMENT"]`` if not provided.

    Returns:
        SQLite URL, e.g. ``"sqlite:///data/dev.db"``.
    """
    if env is None:
        env = os.environ.get("ENVIRONMENT", "dev")
    return f"sqlite:///data/{env}.db"


DB_URL = get_db_url()


def create_db_engine(url: str = DB_URL):
    """Create and configure the SQLite engine.

    Applied pragmas
    ~~~~~~~~~~~~~~~
    * ``journal_mode=WAL`` — allows concurrent reads during writes; essential
      for the bot writing while the CLI reads analytics.
    * ``synchronous=NORMAL`` — safe with WAL; much faster than FULL.
    * ``foreign_keys=ON`` — enforce referential integrity.
    * ``busy_timeout=30000`` — wait up to 30 s before raising a lock error
      instead of failing immediately.
    * ``cache_size=-64000`` — 64 MB page cache for faster repeated queries.
    """
    engine = create_engine(
        url,
        echo=False,
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        for pragma in (
            "PRAGMA journal_mode=WAL",
            "PRAGMA synchronous=NORMAL",
            "PRAGMA foreign_keys=ON",
            "PRAGMA busy_timeout=30000",
            "PRAGMA cache_size=-64000",
        ):
            cursor.execute(pragma)
        cursor.close()

    return engine


def init_database(engine) -> None:
    """Create all tables if they do not already exist (idempotent)."""
    Base.metadata.create_all(engine)

    # Ensure WAL checkpoint runs on first connection so the DB file exists
    with engine.connect() as conn:
        conn.execute(text("PRAGMA wal_checkpoint(PASSIVE)"))


def get_session_factory(engine):
    """Return a configured ``sessionmaker`` bound to *engine*."""
    return sessionmaker(engine)
