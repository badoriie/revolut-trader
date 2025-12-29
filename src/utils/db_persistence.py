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
    PortfolioSnapshotDB,
    SessionDB,
    TradeDB,
    create_db_engine,
    get_session_factory,
    init_database,
)


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

        logger.info(f"Database persistence initialized: {database_url}")

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
                strategy=strategy,
                risk_level=risk_level,
                trading_mode=trading_mode,
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
                    strategy=metadata.get("strategy"),
                    risk_level=metadata.get("risk_level"),
                    trading_mode=metadata.get("trading_mode"),
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
                    "strategy": s.strategy,
                    "risk_level": s.risk_level,
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
            db_trade = TradeDB(
                order_id=order.order_id or f"order_{datetime.now(UTC).timestamp()}",
                symbol=order.symbol,
                side=order.side.value,
                order_type=order.order_type.value,
                quantity=float(order.quantity),
                price=float(order.price) if order.price else 0.0,
                filled_quantity=float(order.filled_quantity),
                status=order.status.value,
                strategy=order.strategy,
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
                    "strategy": t.strategy,
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
            db_session = SessionDB(
                started_at=datetime.now(UTC),
                strategy=strategy,
                risk_level=risk_level,
                trading_mode=trading_mode,
                trading_pairs=json.dumps(trading_pairs),
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
