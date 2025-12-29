"""Database persistence layer using SQLAlchemy.

Supports SQLite (default) with easy migration to PostgreSQL.
"""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import desc, func
from sqlalchemy.exc import SQLAlchemyError

from src.data.models import Order, PortfolioSnapshot
from src.models.db_models import (
    BacktestRunDB,
    LogEntryDB,
    PortfolioSnapshotDB,
    SessionDB,
    TradeDB,
    create_db_engine,
    get_session_factory,
    init_database,
)
from src.utils.db_encryption import DatabaseEncryption


class DatabasePersistence:
    """Database-based persistence for trading data using SQLAlchemy."""

    def __init__(self, database_url: str = "sqlite:///data/trading.db"):
        """Initialize database persistence.

        Args:
            database_url: Database connection string
                - SQLite: "sqlite:///data/trading.db" (default)
                - PostgreSQL: "postgresql://user:password@localhost/trading"
        """
        # Ensure data directory exists for SQLite
        if database_url.startswith("sqlite:///"):
            db_path = Path(database_url.replace("sqlite:///", ""))
            db_path.parent.mkdir(parents=True, exist_ok=True)

        self.database_url = database_url
        self.engine = create_db_engine(database_url)
        self.Session = get_session_factory(self.engine)

        # Initialize schema
        init_database(self.engine)

        # Initialize encryption for sensitive fields
        self.encryption = DatabaseEncryption()

        logger.info(f"Database persistence initialized: {database_url}")
        if self.encryption.is_enabled:
            logger.info("✓ Database field encryption enabled")

    def save_portfolio_snapshot(
        self,
        snapshot: PortfolioSnapshot,
        strategy: str,
        risk_level: str,
        trading_mode: str,
    ) -> None:
        """Save a single portfolio snapshot to database.

        Args:
            snapshot: Portfolio snapshot to save
            strategy: Trading strategy name
            risk_level: Risk level setting
            trading_mode: Trading mode (paper/live)
        """
        session = self.Session()
        try:
            # Encrypt sensitive text fields
            encrypted_strategy = self.encryption.encrypt(strategy)
            encrypted_risk_level = self.encryption.encrypt(risk_level)
            encrypted_trading_mode = self.encryption.encrypt(trading_mode)

            db_snapshot = PortfolioSnapshotDB(
                timestamp=snapshot.timestamp,
                total_value=float(snapshot.total_value),
                cash_balance=float(snapshot.cash_balance),
                positions_value=float(snapshot.positions_value),
                unrealized_pnl=float(snapshot.unrealized_pnl),
                realized_pnl=float(snapshot.realized_pnl),
                total_pnl=float(snapshot.total_pnl),
                daily_pnl=float(snapshot.daily_pnl),
                num_positions=snapshot.num_positions,
                strategy=encrypted_strategy,
                risk_level=encrypted_risk_level,
                trading_mode=encrypted_trading_mode,
            )

            session.add(db_snapshot)
            session.commit()
            logger.debug(f"Saved portfolio snapshot: {snapshot.total_value}")

        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Failed to save portfolio snapshot: {e}")
        finally:
            session.close()

    def save_portfolio_snapshots_bulk(
        self, snapshots: list[PortfolioSnapshot], metadata: dict[str, Any]
    ) -> None:
        """Save multiple snapshots in bulk (more efficient).

        Args:
            snapshots: List of portfolio snapshots
            metadata: Session metadata (strategy, risk_level, etc.)
        """
        if not snapshots:
            return

        session = self.Session()
        try:
            # Encrypt metadata once for all snapshots
            encrypted_strategy = self.encryption.encrypt(metadata.get("strategy", ""))
            encrypted_risk_level = self.encryption.encrypt(metadata.get("risk_level", ""))
            encrypted_trading_mode = self.encryption.encrypt(metadata.get("trading_mode", ""))

            db_snapshots = [
                PortfolioSnapshotDB(
                    timestamp=s.timestamp,
                    total_value=float(s.total_value),
                    cash_balance=float(s.cash_balance),
                    positions_value=float(s.positions_value),
                    unrealized_pnl=float(s.unrealized_pnl),
                    realized_pnl=float(s.realized_pnl),
                    total_pnl=float(s.total_pnl),
                    daily_pnl=float(s.daily_pnl),
                    num_positions=s.num_positions,
                    strategy=encrypted_strategy,
                    risk_level=encrypted_risk_level,
                    trading_mode=encrypted_trading_mode,
                )
                for s in snapshots
            ]

            session.bulk_save_objects(db_snapshots)
            session.commit()
            logger.debug(f"Saved {len(snapshots)} portfolio snapshots in bulk")

        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Failed to save snapshots in bulk: {e}")
        finally:
            session.close()

    def load_portfolio_snapshots(
        self, since: datetime | None = None, limit: int = 1000
    ) -> list[dict[str, Any]]:
        """Load portfolio snapshots from database.

        Args:
            since: Load snapshots since this datetime (default: last 1000)
            limit: Maximum number of snapshots to load

        Returns:
            List of snapshot dictionaries
        """
        session = self.Session()
        try:
            query = session.query(PortfolioSnapshotDB).order_by(desc(PortfolioSnapshotDB.timestamp))

            if since:
                query = query.filter(PortfolioSnapshotDB.timestamp >= since)

            snapshots = query.limit(limit).all()

            results = [
                {
                    "timestamp": s.timestamp.isoformat(),
                    "total_value": str(s.total_value),
                    "cash_balance": str(s.cash_balance),
                    "positions_value": str(s.positions_value),
                    "unrealized_pnl": str(s.unrealized_pnl),
                    "realized_pnl": str(s.realized_pnl),
                    "total_pnl": str(s.total_pnl),
                    "daily_pnl": str(s.daily_pnl),
                    "num_positions": s.num_positions,
                    "strategy": self.encryption.decrypt(s.strategy) if s.strategy else None,
                    "risk_level": self.encryption.decrypt(s.risk_level) if s.risk_level else None,
                }
                for s in reversed(snapshots)  # Chronological order
            ]

            logger.info(f"Loaded {len(results)} portfolio snapshots from database")
            return results

        except SQLAlchemyError as e:
            logger.error(f"Failed to load portfolio snapshots: {e}")
            return []
        finally:
            session.close()

    def save_trade(self, order: Order) -> None:
        """Save a completed trade to database.

        Args:
            order: Completed order to save
        """
        session = self.Session()
        try:
            # Encrypt strategy field
            encrypted_strategy = self.encryption.encrypt(order.strategy) if order.strategy else None

            db_trade = TradeDB(
                order_id=order.order_id or f"order_{datetime.now(UTC).timestamp()}",
                symbol=order.symbol,
                side=order.side.value,
                order_type=order.order_type.value,
                quantity=float(order.quantity),
                price=float(order.price) if order.price else 0.0,
                filled_quantity=float(order.filled_quantity),
                status=order.status.value,
                strategy=encrypted_strategy,
                created_at=order.created_at,
                filled_at=datetime.now(UTC) if order.status.value == "FILLED" else None,
            )

            session.add(db_trade)
            session.commit()
            logger.debug(f"Saved trade: {order.symbol} {order.side} {order.quantity}")

        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Failed to save trade: {e}")
        finally:
            session.close()

    def load_trade_history(
        self, since: datetime | None = None, symbol: str | None = None, limit: int = 1000
    ) -> list[dict[str, Any]]:
        """Load trade history from database.

        Args:
            since: Load trades since this datetime
            symbol: Filter by symbol (optional)
            limit: Maximum number of trades to load

        Returns:
            List of trade dictionaries
        """
        session = self.Session()
        try:
            query = session.query(TradeDB).order_by(desc(TradeDB.created_at))

            if since:
                query = query.filter(TradeDB.created_at >= since)

            if symbol:
                query = query.filter(TradeDB.symbol == symbol)

            trades = query.limit(limit).all()

            results = [
                {
                    "order_id": t.order_id,
                    "symbol": t.symbol,
                    "side": t.side,
                    "order_type": t.order_type,
                    "quantity": str(t.quantity),
                    "price": str(t.price),
                    "filled_quantity": str(t.filled_quantity),
                    "status": t.status,
                    "strategy": self.encryption.decrypt(t.strategy) if t.strategy else None,
                    "created_at": t.created_at.isoformat(),
                }
                for t in reversed(trades)  # Chronological order
            ]

            logger.info(f"Loaded {len(results)} trades from database")
            return results

        except SQLAlchemyError as e:
            logger.error(f"Failed to load trade history: {e}")
            return []
        finally:
            session.close()

    def create_session(
        self,
        strategy: str,
        risk_level: str,
        trading_mode: str,
        trading_pairs: list[str],
        initial_balance: Decimal,
    ) -> int:
        """Create a new trading session record.

        Args:
            strategy: Trading strategy name
            risk_level: Risk level setting
            trading_mode: Trading mode (paper/live)
            trading_pairs: List of trading pairs
            initial_balance: Starting balance

        Returns:
            Session ID
        """
        session = self.Session()
        try:
            # Encrypt sensitive text fields
            encrypted_strategy = self.encryption.encrypt(strategy)
            encrypted_risk_level = self.encryption.encrypt(risk_level)
            encrypted_trading_mode = self.encryption.encrypt(trading_mode)
            encrypted_trading_pairs = self.encryption.encrypt(json.dumps(trading_pairs))

            db_session = SessionDB(
                started_at=datetime.now(UTC),
                strategy=encrypted_strategy,
                risk_level=encrypted_risk_level,
                trading_mode=encrypted_trading_mode,
                trading_pairs=encrypted_trading_pairs,
                initial_balance=float(initial_balance),
                status="ACTIVE",
            )

            session.add(db_session)
            session.commit()
            session_id = db_session.id

            logger.info(f"Created trading session: {session_id}")
            return session_id

        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Failed to create session: {e}")
            return -1
        finally:
            session.close()

    def end_session(
        self, session_id: int, final_balance: Decimal, total_pnl: Decimal, total_trades: int
    ) -> None:
        """End a trading session.

        Args:
            session_id: Session ID to end
            final_balance: Final account balance
            total_pnl: Total profit/loss
            total_trades: Total number of trades executed
        """
        session = self.Session()
        try:
            db_session = session.query(SessionDB).filter_by(id=session_id).first()

            if db_session:
                db_session.ended_at = datetime.now(UTC)
                db_session.final_balance = float(final_balance)
                db_session.total_pnl = float(total_pnl)
                db_session.total_trades = total_trades
                db_session.status = "STOPPED"

                session.commit()
                logger.info(f"Ended trading session: {session_id}")

        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Failed to end session: {e}")
        finally:
            session.close()

    def get_analytics(self, days: int = 30) -> dict[str, Any]:
        """Get trading analytics for the specified period.

        Args:
            days: Number of days to analyze

        Returns:
            Dictionary with analytics data
        """
        session = self.Session()
        try:
            since = datetime.now(UTC) - timedelta(days=days)

            # Portfolio performance
            snapshots = (
                session.query(PortfolioSnapshotDB)
                .filter(PortfolioSnapshotDB.timestamp >= since)
                .order_by(PortfolioSnapshotDB.timestamp)
                .all()
            )

            # Trade statistics
            total_trades = (
                session.query(func.count(TradeDB.id)).filter(TradeDB.created_at >= since).scalar()
            )

            winning_trades = (
                session.query(func.count(TradeDB.id))
                .filter(TradeDB.created_at >= since, TradeDB.pnl > 0)
                .scalar()
            )

            total_pnl = (
                session.query(func.sum(TradeDB.pnl)).filter(TradeDB.created_at >= since).scalar()
            )

            analytics = {
                "period_days": days,
                "total_snapshots": len(snapshots),
                "total_trades": total_trades or 0,
                "winning_trades": winning_trades or 0,
                "total_pnl": float(total_pnl) if total_pnl else 0.0,
                "win_rate": (winning_trades / total_trades * 100) if total_trades else 0.0,
            }

            if snapshots:
                analytics["initial_value"] = float(snapshots[0].total_value)
                analytics["final_value"] = float(snapshots[-1].total_value)
                analytics["return_pct"] = (
                    (analytics["final_value"] - analytics["initial_value"])
                    / analytics["initial_value"]
                    * 100
                )

            return analytics

        except SQLAlchemyError as e:
            logger.error(f"Failed to get analytics: {e}")
            return {}
        finally:
            session.close()

    def save_backtest_run(
        self,
        strategy: str,
        risk_level: str,
        symbols: list[str],
        days: int,
        interval: str,
        initial_capital: float,
        results: dict[str, Any],
        equity_curve_file: str | None = None,
        trades_file: str | None = None,
    ) -> int:
        """Save backtest run results to database.

        Args:
            strategy: Strategy name
            risk_level: Risk level used
            symbols: List of trading symbols
            days: Number of days tested
            interval: Candle interval
            initial_capital: Starting capital
            results: Backtest results dictionary
            equity_curve_file: Path to equity curve JSON
            trades_file: Path to trades JSON

        Returns:
            Backtest run ID
        """
        session = self.Session()
        try:
            # Encrypt sensitive text fields
            encrypted_strategy = self.encryption.encrypt(strategy)
            encrypted_risk_level = self.encryption.encrypt(risk_level)
            encrypted_symbols = self.encryption.encrypt(json.dumps(symbols))

            backtest_run = BacktestRunDB(
                run_at=datetime.now(UTC),
                strategy=encrypted_strategy,
                risk_level=encrypted_risk_level,
                symbols=encrypted_symbols,
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
                equity_curve_file=equity_curve_file,
                trades_file=trades_file,
            )

            session.add(backtest_run)
            session.commit()
            run_id = backtest_run.id

            logger.info(
                f"Saved backtest run: {run_id} ({strategy}, return={results['return_pct']:.2f}%)"
            )
            return run_id

        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Failed to save backtest run: {e}")
            return -1
        finally:
            session.close()

    def load_backtest_runs(
        self, strategy: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Load backtest run history.

        Args:
            strategy: Filter by strategy (optional)
            limit: Maximum number of runs to load

        Returns:
            List of backtest run dictionaries
        """
        session = self.Session()
        try:
            query = session.query(BacktestRunDB).order_by(desc(BacktestRunDB.run_at))

            if strategy:
                # Filter requires encrypted value for comparison
                encrypted_strategy = self.encryption.encrypt(strategy)
                query = query.filter(BacktestRunDB.strategy == encrypted_strategy)

            runs = query.limit(limit).all()

            results = [
                {
                    "id": r.id,
                    "run_at": r.run_at.isoformat(),
                    "strategy": self.encryption.decrypt(r.strategy) if r.strategy else None,
                    "risk_level": self.encryption.decrypt(r.risk_level) if r.risk_level else None,
                    "symbols": json.loads(
                        self.encryption.decrypt(r.symbols) if r.symbols else "[]"
                    ),
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
                    "equity_curve_file": r.equity_curve_file,
                    "trades_file": r.trades_file,
                }
                for r in runs
            ]

            logger.info(f"Loaded {len(results)} backtest runs from database")
            return results

        except SQLAlchemyError as e:
            logger.error(f"Failed to load backtest runs: {e}")
            return []
        finally:
            session.close()

    def get_backtest_analytics(self) -> dict[str, Any]:
        """Get analytics across all backtest runs.

        Returns:
            Dictionary with backtest analytics
        """
        session = self.Session()
        try:
            total_runs = session.query(func.count(BacktestRunDB.id)).scalar()

            profitable_runs = (
                session.query(func.count(BacktestRunDB.id))
                .filter(BacktestRunDB.return_pct > 0)
                .scalar()
            )

            avg_return = session.query(func.avg(BacktestRunDB.return_pct)).scalar()

            best_run = session.query(BacktestRunDB).order_by(desc(BacktestRunDB.return_pct)).first()

            analytics = {
                "total_runs": total_runs or 0,
                "profitable_runs": profitable_runs or 0,
                "avg_return_pct": float(avg_return) if avg_return else 0.0,
                "success_rate": (profitable_runs / total_runs * 100) if total_runs else 0.0,
            }

            if best_run:
                analytics["best_run"] = {
                    "id": best_run.id,
                    "strategy": self.encryption.decrypt(best_run.strategy)
                    if best_run.strategy
                    else None,
                    "return_pct": best_run.return_pct,
                    "total_trades": best_run.total_trades,
                    "win_rate": best_run.win_rate,
                }

            return analytics

        except SQLAlchemyError as e:
            logger.error(f"Failed to get backtest analytics: {e}")
            return {}
        finally:
            session.close()

    def save_log_entry(
        self, level: str, message: str, module: str | None = None, session_id: int | None = None
    ) -> None:
        """Save a log entry to database (optional, for critical events).

        Args:
            level: Log level (INFO, WARNING, ERROR, CRITICAL)
            message: Log message
            module: Module name
            session_id: Associated session ID
        """
        session = self.Session()
        try:
            # Encrypt module and message fields (may contain sensitive info)
            encrypted_module = self.encryption.encrypt(module) if module else None
            encrypted_message = self.encryption.encrypt(message)

            log_entry = LogEntryDB(
                timestamp=datetime.now(UTC),
                level=level,
                module=encrypted_module,
                message=encrypted_message,
                session_id=session_id,
            )

            session.add(log_entry)
            session.commit()

        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Failed to save log entry: {e}")
        finally:
            session.close()

    def load_log_entries(
        self, level: str | None = None, since: datetime | None = None, limit: int = 1000
    ) -> list[dict[str, Any]]:
        """Load log entries from database.

        Args:
            level: Filter by log level (optional)
            since: Load logs since this datetime
            limit: Maximum number of entries to load

        Returns:
            List of log entry dictionaries
        """
        session = self.Session()
        try:
            query = session.query(LogEntryDB).order_by(desc(LogEntryDB.timestamp))

            if level:
                query = query.filter(LogEntryDB.level == level)

            if since:
                query = query.filter(LogEntryDB.timestamp >= since)

            entries = query.limit(limit).all()

            results = [
                {
                    "id": e.id,
                    "timestamp": e.timestamp.isoformat(),
                    "level": e.level,
                    "module": self.encryption.decrypt(e.module) if e.module else None,
                    "message": self.encryption.decrypt(e.message) if e.message else "",
                    "session_id": e.session_id,
                }
                for e in entries
            ]

            return results

        except SQLAlchemyError as e:
            logger.error(f"Failed to load log entries: {e}")
            return []
        finally:
            session.close()
