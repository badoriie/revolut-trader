"""Database persistence layer using SQLAlchemy (SQLite).

Design notes
------------
* A ``_session()`` context manager centralises commit/rollback/close so every
  public method is a single ``with self._session() as sess:`` block — no more
  duplicated try/except/finally.
* Sensitive fields are encrypted **at the application layer** before writing:
  - ``SessionDB.trading_pairs`` — reveals which instruments are being traded.
  - ``LogEntryDB.message``     — may contain balances, order details, etc.
  All other fields (strategy, risk_level, trading_mode, symbol names) are
  stored as **plaintext** so they can be used in SQL WHERE / ORDER BY clauses.
* All monetary values are ``Decimal`` — no ``float()`` casts are introduced.
* Bulk inserts use ``add_all()`` (``bulk_save_objects()`` is deprecated).
"""

from __future__ import annotations

import csv
import json
import os
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import case, desc, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.models.db import (
    BacktestRunDB,
    LogEntryDB,
    PortfolioSnapshotDB,
    SessionDB,
    TradeDB,
    create_db_engine,
    get_db_url,
    get_session_factory,
    init_database,
)
from src.models.domain import Order, PortfolioSnapshot
from src.utils.db_encryption import DatabaseEncryption


class DatabasePersistence:
    """Database-backed persistence for all trading data.

    SQLite is the storage engine; SQLAlchemy 2.0 ORM is the access layer.
    Encryption is applied at the application level for genuinely sensitive
    fields only (trading_pairs, log messages).
    """

    def __init__(self) -> None:
        db_url = get_db_url()
        Path(db_url.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_db_engine(db_url)
        self._session_factory = get_session_factory(self.engine)
        init_database(self.engine)
        self.encryption = DatabaseEncryption()
        logger.info(f"Database persistence initialised: {db_url}")
        if self.encryption.is_enabled:
            logger.info("✓ Database field encryption enabled")

    # ---------------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------------

    @contextmanager
    def _session(self) -> Generator[Session, None, None]:
        """Yield a SQLAlchemy session that auto-commits or rolls back.

        Commits on clean exit; rolls back and re-raises ``SQLAlchemyError``
        so callers can catch it (or let it propagate).  Closes the session
        in all cases.
        """
        sess = self._session_factory()
        try:
            yield sess
            sess.commit()
        except SQLAlchemyError as exc:
            sess.rollback()
            logger.error(f"Database error: {exc}")
            raise
        finally:
            sess.close()

    # ---------------------------------------------------------------------------
    # Portfolio snapshots
    # ---------------------------------------------------------------------------

    def save_portfolio_snapshot(
        self,
        snapshot: PortfolioSnapshot,
        strategy: str,
        risk_level: str,
        trading_mode: str,
    ) -> None:
        """Persist a single portfolio snapshot.

        Categorical fields (strategy, risk_level, trading_mode) are stored as
        plaintext — they are not sensitive and must be filterable in SQL.

        Args:
            snapshot: Domain snapshot object to persist.
            strategy: Trading strategy name (e.g. ``"momentum"``).
            risk_level: Risk level label (e.g. ``"moderate"``).
            trading_mode: Execution mode (e.g. ``"paper"`` or ``"live"``).
        """
        try:
            with self._session() as sess:
                sess.add(
                    PortfolioSnapshotDB(
                        timestamp=snapshot.timestamp,
                        total_value=snapshot.total_value,
                        cash_balance=snapshot.cash_balance,
                        positions_value=snapshot.positions_value,
                        unrealized_pnl=snapshot.unrealized_pnl,
                        realized_pnl=snapshot.realized_pnl,
                        total_pnl=snapshot.total_pnl,
                        daily_pnl=snapshot.daily_pnl,
                        num_positions=snapshot.num_positions,
                        strategy=strategy,
                        risk_level=risk_level,
                        trading_mode=trading_mode,
                    )
                )
            logger.debug(f"Saved portfolio snapshot: {snapshot.total_value}")
        except SQLAlchemyError:
            pass  # already logged by _session()

    def save_portfolio_snapshots_bulk(
        self, snapshots: list[PortfolioSnapshot], metadata: dict[str, Any]
    ) -> None:
        """Persist multiple snapshots in a single transaction.

        Args:
            snapshots: Portfolio snapshots to persist.
            metadata: Dict with optional keys ``strategy``, ``risk_level``,
                      and ``trading_mode``.
        """
        if not snapshots:
            return
        strategy = metadata.get("strategy", "")
        risk_level = metadata.get("risk_level", "")
        trading_mode = metadata.get("trading_mode", "")
        try:
            with self._session() as sess:
                sess.add_all(
                    [
                        PortfolioSnapshotDB(
                            timestamp=s.timestamp,
                            total_value=s.total_value,
                            cash_balance=s.cash_balance,
                            positions_value=s.positions_value,
                            unrealized_pnl=s.unrealized_pnl,
                            realized_pnl=s.realized_pnl,
                            total_pnl=s.total_pnl,
                            daily_pnl=s.daily_pnl,
                            num_positions=s.num_positions,
                            strategy=strategy,
                            risk_level=risk_level,
                            trading_mode=trading_mode,
                        )
                        for s in snapshots
                    ]
                )
            logger.debug(f"Saved {len(snapshots)} portfolio snapshots in bulk")
        except SQLAlchemyError:
            pass

    def load_portfolio_snapshots(
        self, since: datetime | None = None, limit: int = 1000
    ) -> list[dict[str, Any]]:
        """Load portfolio snapshots in chronological (ascending) order.

        Args:
            since: Inclusive UTC lower bound on timestamp.
            limit: Maximum rows to return.

        Returns:
            List of snapshot dicts with string-serialised Decimal values.
        """
        try:
            with self._session() as sess:
                query = sess.query(PortfolioSnapshotDB).order_by(PortfolioSnapshotDB.timestamp)
                if since:
                    query = query.filter(PortfolioSnapshotDB.timestamp >= since)
                rows = query.limit(limit).all()
                results = [
                    {
                        "timestamp": r.timestamp.isoformat(),
                        "total_value": str(r.total_value),
                        "cash_balance": str(r.cash_balance),
                        "positions_value": str(r.positions_value),
                        "unrealized_pnl": str(r.unrealized_pnl),
                        "realized_pnl": str(r.realized_pnl),
                        "total_pnl": str(r.total_pnl),
                        "daily_pnl": str(r.daily_pnl),
                        "num_positions": r.num_positions,
                        "strategy": r.strategy,
                        "risk_level": r.risk_level,
                    }
                    for r in rows
                ]
                logger.info(f"Loaded {len(results)} portfolio snapshots")
                return results
        except SQLAlchemyError:
            return []

    # ---------------------------------------------------------------------------
    # Trades
    # ---------------------------------------------------------------------------

    def save_trade(self, order: Order) -> None:
        """Persist a completed order as a trade record.

        The ``strategy`` field is stored as plaintext — it is a label such as
        ``"momentum"`` and is not sensitive.

        Args:
            order: Filled or cancelled Order domain object.
        """
        try:
            with self._session() as sess:
                sess.add(
                    TradeDB(
                        order_id=order.order_id or f"order_{datetime.now(UTC).timestamp()}",
                        symbol=order.symbol,
                        side=order.side.value,
                        order_type=order.order_type.value,
                        quantity=order.quantity,
                        price=order.price if order.price is not None else Decimal(0),
                        filled_quantity=order.filled_quantity,
                        status=order.status.value,
                        strategy=order.strategy,
                        created_at=order.created_at,
                        filled_at=(datetime.now(UTC) if order.status.value == "FILLED" else None),
                        pnl=order.realized_pnl,
                        fee=order.commission if order.commission != Decimal("0") else None,
                    )
                )
            logger.debug(f"Saved trade: {order.symbol} {order.side} {order.quantity}")
        except SQLAlchemyError:
            pass

    def load_trade_history(
        self,
        since: datetime | None = None,
        symbol: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Load trade history in chronological (ascending) order.

        Args:
            since: Inclusive UTC lower bound on ``created_at``.
            symbol: Optional exact-match symbol filter.
            limit: Maximum rows to return.

        Returns:
            List of trade dicts with string-serialised Decimal values.
        """
        try:
            with self._session() as sess:
                query = sess.query(TradeDB).order_by(TradeDB.created_at)
                if since:
                    query = query.filter(TradeDB.created_at >= since)
                if symbol:
                    query = query.filter(TradeDB.symbol == symbol)
                rows = query.limit(limit).all()
                results = [
                    {
                        "order_id": r.order_id,
                        "symbol": r.symbol,
                        "side": r.side,
                        "order_type": r.order_type,
                        "quantity": str(r.quantity),
                        "price": str(r.price),
                        "filled_quantity": str(r.filled_quantity),
                        "status": r.status,
                        "strategy": r.strategy,
                        "created_at": r.created_at.isoformat(),
                        "pnl": str(r.pnl) if r.pnl is not None else None,
                        "fee": str(r.fee) if r.fee is not None else None,
                    }
                    for r in rows
                ]
                logger.info(f"Loaded {len(results)} trades")
                return results
        except SQLAlchemyError:
            return []

    # ---------------------------------------------------------------------------
    # Trading sessions
    # ---------------------------------------------------------------------------

    def create_session(
        self,
        strategy: str,
        risk_level: str,
        trading_mode: str,
        trading_pairs: list[str],
        initial_balance: Decimal,
    ) -> int:
        """Create a new trading session record and return its primary key.

        ``trading_pairs`` is encrypted because it reveals the exact instruments
        the bot is actively trading — potentially sensitive alpha information.
        All other metadata is stored as plaintext for SQL filterability.

        Returns:
            New session primary key, or ``-1`` on failure.
        """
        try:
            with self._session() as sess:
                record = SessionDB(
                    started_at=datetime.now(UTC),
                    strategy=strategy,
                    risk_level=risk_level,
                    trading_mode=trading_mode,
                    trading_pairs=self.encryption.encrypt(json.dumps(trading_pairs)),
                    initial_balance=initial_balance,
                    status="ACTIVE",
                )
                sess.add(record)
                sess.flush()  # populate .id before commit
                session_id: int = record.id  # type: ignore[assignment]
            logger.info(f"Created trading session: {session_id}")
            return session_id
        except SQLAlchemyError:
            return -1

    def end_session(
        self,
        session_id: int,
        final_balance: Decimal,
        total_pnl: Decimal,
        total_trades: int,
    ) -> None:
        """Close a trading session and record final metrics.

        Args:
            session_id: Primary key of the session to close.
            final_balance: Account balance at session end.
            total_pnl: Net profit/loss for the session.
            total_trades: Total number of orders executed.
        """
        try:
            with self._session() as sess:
                record = sess.query(SessionDB).filter_by(id=session_id).first()
                if record:
                    record.ended_at = datetime.now(UTC)
                    record.final_balance = final_balance
                    record.total_pnl = total_pnl
                    record.total_trades = total_trades
                    record.status = "STOPPED"
            logger.info(f"Ended trading session: {session_id}")
        except SQLAlchemyError:
            pass

    # ---------------------------------------------------------------------------
    # Analytics
    # ---------------------------------------------------------------------------

    def get_analytics(self, days: int = 30) -> dict[str, Any]:
        """Compute rolling trading analytics over the last *days* calendar days.

        Returns a dict with keys: ``period_days``, ``total_snapshots``,
        ``total_trades``, ``winning_trades``, ``total_pnl``, ``win_rate``,
        and optionally ``initial_value``, ``final_value``, ``return_pct``.

        Args:
            days: Look-back window in calendar days.

        Returns:
            Analytics dict, or empty dict on database error.
        """
        try:
            with self._session() as sess:
                since = datetime.now(UTC) - timedelta(days=days)
                snapshots = (
                    sess.query(PortfolioSnapshotDB)
                    .filter(PortfolioSnapshotDB.timestamp >= since)
                    .order_by(PortfolioSnapshotDB.timestamp)
                    .all()
                )
                total_trades = (
                    sess.query(func.count(TradeDB.id)).filter(TradeDB.created_at >= since).scalar()
                )
                winning_trades = (
                    sess.query(func.count(TradeDB.id))
                    .filter(TradeDB.created_at >= since, TradeDB.pnl > 0)
                    .scalar()
                )
                losing_trades = (
                    sess.query(func.count(TradeDB.id))
                    .filter(TradeDB.created_at >= since, TradeDB.pnl < 0)
                    .scalar()
                )
                total_pnl = (
                    sess.query(func.sum(TradeDB.pnl)).filter(TradeDB.created_at >= since).scalar()
                )
                total_fees = (
                    sess.query(func.sum(TradeDB.fee)).filter(TradeDB.created_at >= since).scalar()
                )
                analytics: dict[str, Any] = {
                    "period_days": days,
                    "total_snapshots": len(snapshots),
                    "total_trades": total_trades or 0,
                    "winning_trades": winning_trades or 0,
                    "losing_trades": losing_trades or 0,
                    "total_pnl": float(total_pnl) if total_pnl else 0.0,
                    "total_fees": float(total_fees) if total_fees else 0.0,
                    "win_rate": ((winning_trades / total_trades * 100) if total_trades else 0.0),
                }
                if snapshots:
                    analytics["initial_value"] = float(snapshots[0].total_value)
                    analytics["final_value"] = float(snapshots[-1].total_value)
                    if analytics["initial_value"]:
                        analytics["return_pct"] = (
                            (analytics["final_value"] - analytics["initial_value"])
                            / analytics["initial_value"]
                            * 100
                        )
                return analytics
        except SQLAlchemyError:
            return {}

    def get_symbol_analytics(self, days: int = 30) -> list[dict[str, Any]]:
        """Per-symbol trade breakdown: counts, win rate, and P&L over the last *days* days.

        Only trades that have a recorded P&L (i.e. closing/reducing trades) are
        included so that open BUY legs don't distort win-rate figures.

        Args:
            days: Look-back window in calendar days.

        Returns:
            List of symbol dicts sorted by total P&L (descending), or ``[]`` on error.
        """
        try:
            since = datetime.now(UTC) - timedelta(days=days)
            with self._session() as sess:
                rows = (
                    sess.query(
                        TradeDB.symbol,
                        func.count(TradeDB.id).label("total_trades"),
                        func.sum(case((TradeDB.pnl > 0, 1), else_=0)).label("winning"),
                        func.sum(case((TradeDB.pnl < 0, 1), else_=0)).label("losing"),
                        func.sum(TradeDB.pnl).label("total_pnl"),
                        func.avg(TradeDB.pnl).label("avg_pnl"),
                        func.sum(TradeDB.fee).label("total_fees"),
                    )
                    .filter(TradeDB.created_at >= since, TradeDB.pnl.isnot(None))
                    .group_by(TradeDB.symbol)
                    .order_by(desc(func.sum(TradeDB.pnl)))
                    .all()
                )
                return [
                    {
                        "symbol": r.symbol,
                        "total_trades": r.total_trades,
                        "winning": int(r.winning or 0),
                        "losing": int(r.losing or 0),
                        "win_rate": float(r.winning / r.total_trades * 100)
                        if r.total_trades
                        else 0.0,
                        "total_pnl": float(r.total_pnl) if r.total_pnl is not None else 0.0,
                        "avg_pnl": float(r.avg_pnl) if r.avg_pnl is not None else 0.0,
                        "total_fees": float(r.total_fees) if r.total_fees is not None else 0.0,
                    }
                    for r in rows
                ]
        except SQLAlchemyError:
            return []

    def get_strategy_live_analytics(self, days: int = 30) -> list[dict[str, Any]]:
        """Per-strategy trade breakdown from live/paper trades over the last *days* days.

        Mirrors ``get_symbol_analytics`` but groups by strategy instead of symbol.
        Only trades with a recorded P&L are included.

        Args:
            days: Look-back window in calendar days.

        Returns:
            List of strategy dicts sorted by total P&L (descending), or ``[]`` on error.
        """
        try:
            since = datetime.now(UTC) - timedelta(days=days)
            with self._session() as sess:
                rows = (
                    sess.query(
                        TradeDB.strategy,
                        func.count(TradeDB.id).label("total_trades"),
                        func.sum(case((TradeDB.pnl > 0, 1), else_=0)).label("winning"),
                        func.sum(case((TradeDB.pnl < 0, 1), else_=0)).label("losing"),
                        func.sum(TradeDB.pnl).label("total_pnl"),
                        func.avg(TradeDB.pnl).label("avg_pnl"),
                        func.sum(TradeDB.fee).label("total_fees"),
                    )
                    .filter(TradeDB.created_at >= since, TradeDB.pnl.isnot(None))
                    .group_by(TradeDB.strategy)
                    .order_by(desc(func.sum(TradeDB.pnl)))
                    .all()
                )
                return [
                    {
                        "strategy": r.strategy or "unknown",
                        "total_trades": r.total_trades,
                        "winning": int(r.winning or 0),
                        "losing": int(r.losing or 0),
                        "win_rate": float(r.winning / r.total_trades * 100)
                        if r.total_trades
                        else 0.0,
                        "total_pnl": float(r.total_pnl) if r.total_pnl is not None else 0.0,
                        "avg_pnl": float(r.avg_pnl) if r.avg_pnl is not None else 0.0,
                        "total_fees": float(r.total_fees) if r.total_fees is not None else 0.0,
                    }
                    for r in rows
                ]
        except SQLAlchemyError:
            return []

    def get_portfolio_value_series(
        self, days: int = 90, limit: int = 10_000
    ) -> list[dict[str, Any]]:
        """Return a time-ordered series of portfolio values for charting and Sharpe computation.

        Unlike ``load_portfolio_snapshots``, this method returns only the fields
        needed for financial analytics — timestamp, total_value, total_pnl, and
        cash_balance — and converts values to ``float`` for downstream numerical
        libraries.

        Args:
            days: Look-back window in calendar days.
            limit: Maximum number of rows to return (applied after the date filter).

        Returns:
            List of dicts with keys ``timestamp`` (ISO string), ``total_value``,
            ``total_pnl``, ``cash_balance``, all as ``float``, or ``[]`` on error.
        """
        try:
            since = datetime.now(UTC) - timedelta(days=days)
            with self._session() as sess:
                rows = (
                    sess.query(PortfolioSnapshotDB)
                    .filter(PortfolioSnapshotDB.timestamp >= since)
                    .order_by(PortfolioSnapshotDB.timestamp)
                    .limit(limit)
                    .all()
                )
                return [
                    {
                        "timestamp": r.timestamp.isoformat(),
                        "total_value": float(r.total_value),
                        "total_pnl": float(r.total_pnl),
                        "cash_balance": float(r.cash_balance),
                    }
                    for r in rows
                ]
        except SQLAlchemyError:
            return []

    # ---------------------------------------------------------------------------
    # Backtest runs
    # ---------------------------------------------------------------------------

    def save_backtest_run(
        self,
        strategy: str,
        risk_level: str,
        symbols: list[str],
        days: int,
        interval: str,
        initial_capital: Decimal | float,
        results: dict[str, Any],
    ) -> int:
        """Persist a completed backtest run and return its primary key.

        ``symbols`` is stored as a **plaintext** JSON array — trading symbol
        names are public market identifiers and need not be encrypted.

        Args:
            strategy: Strategy name used for the run.
            risk_level: Risk level label.
            symbols: List of traded symbols (e.g. ``["BTC-EUR"]``).
            days: Historical window in days.
            interval: Candle interval string (e.g. ``"60"``).
            initial_capital: Starting capital (Decimal preferred).
            results: Dict from ``BacktestResults`` with keys: ``final_capital``,
                     ``total_pnl``, ``return_pct``, ``total_trades``,
                     ``winning_trades``, ``losing_trades``, ``win_rate``,
                     ``max_drawdown``, and optionally ``profit_factor`` /
                     ``sharpe_ratio``.

        Returns:
            New backtest run primary key, or ``-1`` on failure.
        """
        try:
            with self._session() as sess:
                record = BacktestRunDB(
                    run_at=datetime.now(UTC),
                    strategy=strategy,
                    risk_level=risk_level,
                    symbols=json.dumps(symbols),
                    days=days,
                    interval=interval,
                    initial_capital=initial_capital,
                    final_capital=results["final_capital"],
                    total_pnl=results["total_pnl"],
                    return_pct=results["return_pct"],
                    total_trades=results["total_trades"],
                    winning_trades=results["winning_trades"],
                    losing_trades=results["losing_trades"],
                    win_rate=results["win_rate"],
                    profit_factor=results.get("profit_factor"),
                    max_drawdown=results["max_drawdown"],
                    sharpe_ratio=results.get("sharpe_ratio"),
                )
                sess.add(record)
                sess.flush()
                run_id: int = record.id  # type: ignore[assignment]
            logger.info(
                f"Saved backtest run: {run_id} ({strategy}, return={results['return_pct']:.2f}%)"
            )
            return run_id
        except SQLAlchemyError:
            return -1

    def load_backtest_runs(
        self, strategy: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Load backtest run history in reverse-chronological order.

        Args:
            strategy: Optional exact-match filter on strategy name (plaintext).
            limit: Maximum rows to return.

        Returns:
            List of backtest run dicts.
        """
        try:
            with self._session() as sess:
                query = sess.query(BacktestRunDB).order_by(desc(BacktestRunDB.run_at))
                if strategy:
                    query = query.filter(BacktestRunDB.strategy == strategy)
                rows = query.limit(limit).all()
                return [
                    {
                        "id": r.id,
                        "run_at": r.run_at.isoformat(),
                        "strategy": r.strategy,
                        "risk_level": r.risk_level,
                        "symbols": json.loads(r.symbols) if r.symbols else [],
                        "days": r.days,
                        "interval": r.interval,
                        "initial_capital": r.initial_capital,
                        "final_capital": r.final_capital,
                        "total_pnl": r.total_pnl,
                        "return_pct": r.return_pct,
                        "total_trades": r.total_trades,
                        "winning_trades": r.winning_trades,
                        "losing_trades": r.losing_trades,
                        "win_rate": r.win_rate,
                        "profit_factor": r.profit_factor,
                        "max_drawdown": r.max_drawdown,
                        "sharpe_ratio": r.sharpe_ratio,
                    }
                    for r in rows
                ]
        except SQLAlchemyError:
            return []

    def get_backtest_analytics(self) -> dict[str, Any]:
        """Aggregate analytics across all stored backtest runs.

        Returns a dict with keys: ``total_runs``, ``profitable_runs``,
        ``avg_return_pct``, ``success_rate``, and optionally ``best_run``.
        """
        try:
            with self._session() as sess:
                total_runs = sess.query(func.count(BacktestRunDB.id)).scalar()
                profitable_runs = (
                    sess.query(func.count(BacktestRunDB.id))
                    .filter(BacktestRunDB.return_pct > 0)
                    .scalar()
                )
                avg_return = sess.query(func.avg(BacktestRunDB.return_pct)).scalar()
                best_run = (
                    sess.query(BacktestRunDB).order_by(desc(BacktestRunDB.return_pct)).first()
                )
                analytics: dict[str, Any] = {
                    "total_runs": total_runs or 0,
                    "profitable_runs": profitable_runs or 0,
                    "avg_return_pct": float(avg_return) if avg_return else 0.0,
                    "success_rate": ((profitable_runs / total_runs * 100) if total_runs else 0.0),
                }
                if best_run:
                    analytics["best_run"] = {
                        "id": best_run.id,
                        "strategy": best_run.strategy,
                        "return_pct": best_run.return_pct,
                        "total_trades": best_run.total_trades,
                        "win_rate": best_run.win_rate,
                    }
                return analytics
        except SQLAlchemyError:
            return {}

    # ---------------------------------------------------------------------------
    # Log entries
    # ---------------------------------------------------------------------------

    def save_log_entry(
        self,
        level: str,
        message: str,
        module: str | None = None,
        session_id: int | None = None,
    ) -> None:
        """Persist a critical log event to the database.

        The message body may contain sensitive runtime context (balances,
        symbol names, order details) and is therefore **encrypted**.  The
        ``module`` field is a plain source-code path (e.g. ``"src.bot"``) and
        is stored as plaintext.

        Args:
            level: Severity — ``INFO`` | ``WARNING`` | ``ERROR`` | ``CRITICAL``.
            message: Human-readable event description (encrypted at rest).
            module: Source module path, optional.
            session_id: Foreign key to the active trading session, optional.
        """
        try:
            with self._session() as sess:
                sess.add(
                    LogEntryDB(
                        timestamp=datetime.now(UTC),
                        level=level,
                        module=module,
                        message=self.encryption.encrypt(message),
                        session_id=session_id,
                    )
                )
        except SQLAlchemyError:
            pass

    # ---------------------------------------------------------------------------
    # CSV export
    # ---------------------------------------------------------------------------

    def export_to_csv(self, output_dir: Path | None = None) -> None:
        """Export all trades and portfolio snapshots to dated CSV files.

        Files are written to *output_dir* and named with today's date
        (``trades_YYYYMMDD.csv``, ``snapshots_YYYYMMDD.csv``).

        Args:
            output_dir: Directory to write CSV files into (created if absent).
                        Defaults to ``<data_dir>/exports`` where *data_dir* is
                        resolved from the ``REVT_DATA_DIR`` environment variable
                        or ``~/revt-data``.
        """
        if output_dir is None:
            raw = os.environ.get("REVT_DATA_DIR", "").strip()
            data_dir = Path(raw) if raw else Path.home() / "revt-data"
            output_dir = data_dir / "exports"
        output_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.now(UTC).strftime("%Y%m%d")

        try:
            trades = self.load_trade_history(limit=100_000)
            trades_file = output_dir / f"trades_{today}.csv"
            with open(trades_file, "w", newline="") as f:
                if trades:
                    writer = csv.DictWriter(f, fieldnames=trades[0].keys())
                    writer.writeheader()
                    writer.writerows(trades)
            logger.info(f"Exported {len(trades)} trades → {trades_file}")

            snapshots = self.load_portfolio_snapshots(limit=100_000)
            snapshots_file = output_dir / f"snapshots_{today}.csv"
            with open(snapshots_file, "w", newline="") as f:
                if snapshots:
                    writer = csv.DictWriter(f, fieldnames=snapshots[0].keys())
                    writer.writeheader()
                    writer.writerows(snapshots)
            logger.info(f"Exported {len(snapshots)} snapshots → {snapshots_file}")

        except Exception as e:
            logger.error(f"CSV export failed: {e}")

    def load_log_entries(
        self,
        level: str | None = None,
        since: datetime | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Load log entries in chronological (ascending) order.

        Messages are decrypted before being returned.

        Args:
            level: Optional exact-match filter on severity level.
            since: Inclusive UTC lower bound on timestamp.
            limit: Maximum rows to return.

        Returns:
            List of log entry dicts with decrypted message values.
        """
        try:
            with self._session() as sess:
                query = sess.query(LogEntryDB).order_by(LogEntryDB.timestamp)
                if level:
                    query = query.filter(LogEntryDB.level == level)
                if since:
                    query = query.filter(LogEntryDB.timestamp >= since)
                rows = query.limit(limit).all()
                return [
                    {
                        "id": r.id,
                        "timestamp": r.timestamp.isoformat(),
                        "level": r.level,
                        "module": r.module,
                        "message": self.encryption.decrypt(r.message) if r.message else "",
                        "session_id": r.session_id,
                    }
                    for r in rows
                ]
        except SQLAlchemyError:
            return []
