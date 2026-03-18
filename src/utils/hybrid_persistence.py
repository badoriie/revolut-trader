"""Hybrid persistence: SQLite (primary) + JSON backup."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from loguru import logger

from src.data.models import Order, PortfolioSnapshot
from src.utils.db_persistence import DatabasePersistence
from src.utils.persistence import DataPersistence


class HybridPersistence:
    """Hybrid persistence using database (primary) and JSON (backup)."""

    def __init__(self, backup_enabled: bool = True):
        self.db = DatabasePersistence()
        self.json = DataPersistence() if backup_enabled else None
        self.backup_enabled = backup_enabled
        self.last_backup = datetime.now(UTC)
        self.current_session_id: int | None = None

        logger.info(f"Hybrid persistence initialized (DB + JSON backup: {backup_enabled})")

    def start_session(
        self,
        strategy: str,
        risk_level: str,
        trading_mode: str,
        trading_pairs: list[str],
        initial_balance: Decimal,
    ) -> None:
        """Start a new trading session.

        Args:
            strategy: Trading strategy name
            risk_level: Risk level setting
            trading_mode: Trading mode (paper/live)
            trading_pairs: List of trading pairs
            initial_balance: Starting balance
        """
        self.current_session_id = self.db.create_session(
            strategy=strategy,
            risk_level=risk_level,
            trading_mode=trading_mode,
            trading_pairs=trading_pairs,
            initial_balance=initial_balance,
        )
        logger.info(f"Started trading session: {self.current_session_id}")

    def end_session(self, final_balance: Decimal, total_pnl: Decimal, total_trades: int) -> None:
        """End the current trading session.

        Args:
            final_balance: Final account balance
            total_pnl: Total profit/loss
            total_trades: Total number of trades executed
        """
        if self.current_session_id:
            self.db.end_session(
                session_id=self.current_session_id,
                final_balance=final_balance,
                total_pnl=total_pnl,
                total_trades=total_trades,
            )
            logger.info(f"Ended trading session: {self.current_session_id}")

    def save_portfolio_snapshot(
        self,
        snapshot: PortfolioSnapshot,
        strategy: str,
        risk_level: str,
        trading_mode: str,
    ) -> None:
        """Save a single portfolio snapshot.

        Primary: Save to database
        Backup: Trigger daily JSON backup if needed

        Args:
            snapshot: Portfolio snapshot to save
            strategy: Trading strategy name
            risk_level: Risk level setting
            trading_mode: Trading mode
        """
        # Primary: Save to database
        self.db.save_portfolio_snapshot(snapshot, strategy, risk_level, trading_mode)

        # Backup: Daily JSON export at midnight
        if self.backup_enabled and self._should_backup():
            self._perform_daily_backup(strategy, risk_level, trading_mode)

    def save_portfolio_snapshots_bulk(
        self, snapshots: list[PortfolioSnapshot], metadata: dict[str, Any]
    ) -> None:
        """Save multiple snapshots efficiently.

        Args:
            snapshots: List of portfolio snapshots
            metadata: Session metadata
        """
        if not snapshots:
            return

        # Primary: Bulk save to database
        self.db.save_portfolio_snapshots_bulk(snapshots, metadata)

        # Backup: Also save to JSON for portability
        if self.backup_enabled and self.json:
            self.json.save_portfolio_snapshots(snapshots)

    def load_portfolio_snapshots(
        self, since: datetime | None = None, limit: int = 1000, from_backup: bool = False
    ) -> list[dict[str, Any]]:
        """Load portfolio snapshots.

        Args:
            since: Load snapshots since this datetime
            limit: Maximum number to load
            from_backup: Load from JSON backup instead of database

        Returns:
            List of snapshot dictionaries
        """
        if from_backup and self.json:
            logger.info("Loading snapshots from JSON backup")
            return [
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
                }
                for s in self.json.load_portfolio_snapshots()
            ]

        # Primary: Load from database
        return self.db.load_portfolio_snapshots(since, limit)

    def save_trade(self, order: Order) -> None:
        """Save a completed trade.

        Primary: Save to database
        Backup: Also append to JSON trade history

        Args:
            order: Completed order to save
        """
        # Primary: Save to database
        self.db.save_trade(order)

        # Backup: Also save to JSON
        if self.backup_enabled and self.json:
            self.json.save_trade(order)

    def load_trade_history(
        self,
        since: datetime | None = None,
        symbol: str | None = None,
        limit: int = 1000,
        from_backup: bool = False,
    ) -> list[dict[str, Any]]:
        """Load trade history.

        Args:
            since: Load trades since this datetime
            symbol: Filter by symbol
            limit: Maximum number to load
            from_backup: Load from JSON backup instead of database

        Returns:
            List of trade dictionaries
        """
        if from_backup and self.json:
            logger.info("Loading trades from JSON backup")
            return self.json.load_trade_history()

        # Primary: Load from database
        return self.db.load_trade_history(since, symbol, limit)

    def get_analytics(self, days: int = 30) -> dict[str, Any]:
        """Get trading analytics from database.

        Args:
            days: Number of days to analyze

        Returns:
            Dictionary with analytics data
        """
        return self.db.get_analytics(days)

    def _should_backup(self) -> bool:
        """Check if daily backup should be performed.

        Returns:
            True if a day has passed since last backup
        """
        now = datetime.now(UTC)
        time_since_backup = now - self.last_backup
        return time_since_backup > timedelta(days=1)

    def _perform_daily_backup(self, strategy: str, risk_level: str, trading_mode: str) -> None:
        """Perform daily JSON backup of database data.

        Args:
            strategy: Current strategy
            risk_level: Current risk level
            trading_mode: Current trading mode
        """
        try:
            if not self.json:
                return

            # Backup last 7 days of snapshots
            since = datetime.now(UTC) - timedelta(days=7)
            snapshots_data = self.db.load_portfolio_snapshots(since=since, limit=10000)

            # Convert back to PortfolioSnapshot objects for JSON persistence
            snapshots = [
                PortfolioSnapshot(
                    timestamp=datetime.fromisoformat(s["timestamp"]),
                    total_value=Decimal(s["total_value"]),
                    cash_balance=Decimal(s["cash_balance"]),
                    positions_value=Decimal(s["positions_value"]),
                    unrealized_pnl=Decimal(s["unrealized_pnl"]),
                    realized_pnl=Decimal(s["realized_pnl"]),
                    total_pnl=Decimal(s["total_pnl"]),
                    daily_pnl=Decimal(s["daily_pnl"]),
                    num_positions=s["num_positions"],
                )
                for s in snapshots_data
            ]

            self.json.save_portfolio_snapshots(snapshots)

            self.last_backup = datetime.now(UTC)
            logger.info(f"Daily backup completed: {len(snapshots)} snapshots saved to JSON")

        except Exception as e:
            logger.error(f"Failed to perform daily backup: {e}")

    def export_to_csv(self, output_dir: Path = Path("data/exports")) -> None:
        """Export trading data to CSV files for analysis.

        Args:
            output_dir: Directory to save CSV exports
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            import csv

            # Export trades
            trades = self.db.load_trade_history(limit=100000)
            trades_file = output_dir / f"trades_{datetime.now(UTC).strftime('%Y%m%d')}.csv"

            with open(trades_file, "w", newline="") as f:
                if trades:
                    writer = csv.DictWriter(f, fieldnames=trades[0].keys())
                    writer.writeheader()
                    writer.writerows(trades)

            logger.info(f"Exported {len(trades)} trades to {trades_file}")

            # Export snapshots
            snapshots = self.db.load_portfolio_snapshots(limit=100000)
            snapshots_file = output_dir / f"snapshots_{datetime.now(UTC).strftime('%Y%m%d')}.csv"

            with open(snapshots_file, "w", newline="") as f:
                if snapshots:
                    writer = csv.DictWriter(f, fieldnames=snapshots[0].keys())
                    writer.writeheader()
                    writer.writerows(snapshots)

            logger.info(f"Exported {len(snapshots)} snapshots to {snapshots_file}")

        except Exception as e:
            logger.error(f"Failed to export to CSV: {e}")
