"""Persistence facade for the trading bot.

All data is stored exclusively in the encrypted SQLite database.
The JSON backup layer has been removed — plaintext JSON files on disk are
less secure than the application-level encrypted database fields, and
SQLite with WAL mode is sufficiently reliable for production use.

On-demand exports (CSV / JSON) are available via ``export_to_csv()``.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from loguru import logger

from src.models.domain import Order, PortfolioSnapshot
from src.utils.db_persistence import DatabasePersistence


class HybridPersistence:
    """Persistence facade backed exclusively by the encrypted SQLite database.

    Keeps the same public interface as the old hybrid layer so that
    ``TradingBot`` requires no changes.
    """

    def __init__(self) -> None:
        self.db = DatabasePersistence()
        self.current_session_id: int | None = None
        logger.info("Persistence initialised (encrypted SQLite)")

    # ---------------------------------------------------------------------------
    # Session lifecycle
    # ---------------------------------------------------------------------------

    def start_session(
        self,
        strategy: str,
        risk_level: str,
        trading_mode: str,
        trading_pairs: list[str],
        initial_balance: Decimal,
    ) -> None:
        """Create a new trading session record in the database.

        Args:
            strategy: Strategy name (e.g. ``"momentum"``).
            risk_level: Risk level label (e.g. ``"moderate"``).
            trading_mode: Execution mode (``"paper"`` or ``"live"``).
            trading_pairs: Instruments being traded (encrypted at rest).
            initial_balance: Starting account balance.
        """
        self.current_session_id = self.db.create_session(
            strategy=strategy,
            risk_level=risk_level,
            trading_mode=trading_mode,
            trading_pairs=trading_pairs,
            initial_balance=initial_balance,
        )
        logger.info(f"Trading session started: {self.current_session_id}")

    def end_session(self, final_balance: Decimal, total_pnl: Decimal, total_trades: int) -> None:
        """Close the current trading session and record final metrics.

        Args:
            final_balance: Account balance at shutdown.
            total_pnl: Net profit/loss for the session.
            total_trades: Total orders executed.
        """
        if self.current_session_id is None:
            return
        self.db.end_session(
            session_id=self.current_session_id,
            final_balance=final_balance,
            total_pnl=total_pnl,
            total_trades=total_trades,
        )
        logger.info(f"Trading session ended: {self.current_session_id}")

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
        """Persist a single portfolio snapshot to the database.

        Args:
            snapshot: Snapshot to persist.
            strategy: Active strategy name.
            risk_level: Active risk level.
            trading_mode: Active trading mode.
        """
        self.db.save_portfolio_snapshot(snapshot, strategy, risk_level, trading_mode)

    def save_portfolio_snapshots_bulk(
        self, snapshots: list[PortfolioSnapshot], metadata: dict[str, Any]
    ) -> None:
        """Persist multiple snapshots in a single database transaction.

        Args:
            snapshots: Snapshots to persist.
            metadata: Dict with optional keys ``strategy``, ``risk_level``,
                      ``trading_mode``.
        """
        if not snapshots:
            return
        self.db.save_portfolio_snapshots_bulk(snapshots, metadata)

    def load_portfolio_snapshots(
        self, since: datetime | None = None, limit: int = 1000
    ) -> list[dict[str, Any]]:
        """Load portfolio snapshots from the database in chronological order.

        Args:
            since: Inclusive UTC lower bound on timestamp.
            limit: Maximum rows to return.

        Returns:
            List of snapshot dicts.
        """
        return self.db.load_portfolio_snapshots(since, limit)

    # ---------------------------------------------------------------------------
    # Trades
    # ---------------------------------------------------------------------------

    def save_trade(self, order: Order) -> None:
        """Persist a completed order as a trade record.

        Args:
            order: Filled or cancelled order to persist.
        """
        self.db.save_trade(order)

    def load_trade_history(
        self,
        since: datetime | None = None,
        symbol: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Load trade history from the database in chronological order.

        Args:
            since: Inclusive UTC lower bound on ``created_at``.
            symbol: Optional exact-match symbol filter.
            limit: Maximum rows to return.

        Returns:
            List of trade dicts.
        """
        return self.db.load_trade_history(since, symbol, limit)

    # ---------------------------------------------------------------------------
    # Analytics
    # ---------------------------------------------------------------------------

    def get_analytics(self, days: int = 30) -> dict[str, Any]:
        """Compute rolling trading analytics over the last *days* calendar days.

        Args:
            days: Look-back window in calendar days.

        Returns:
            Analytics dict from the database layer.
        """
        return self.db.get_analytics(days)

    # ---------------------------------------------------------------------------
    # Export
    # ---------------------------------------------------------------------------

    def export_to_csv(self, output_dir: Path = Path("data/exports")) -> None:
        """Export all trades and portfolio snapshots to dated CSV files.

        The export reads directly from the database, so no separate backup
        file is needed.  Files are written to *output_dir* and named with
        today's date (``trades_YYYYMMDD.csv``, ``snapshots_YYYYMMDD.csv``).

        Args:
            output_dir: Directory to write CSV files into (created if absent).
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.now(UTC).strftime("%Y%m%d")

        try:
            trades = self.db.load_trade_history(limit=100_000)
            trades_file = output_dir / f"trades_{today}.csv"
            with open(trades_file, "w", newline="") as f:
                if trades:
                    writer = csv.DictWriter(f, fieldnames=trades[0].keys())
                    writer.writeheader()
                    writer.writerows(trades)
            logger.info(f"Exported {len(trades)} trades → {trades_file}")

            snapshots = self.db.load_portfolio_snapshots(limit=100_000)
            snapshots_file = output_dir / f"snapshots_{today}.csv"
            with open(snapshots_file, "w", newline="") as f:
                if snapshots:
                    writer = csv.DictWriter(f, fieldnames=snapshots[0].keys())
                    writer.writeheader()
                    writer.writerows(snapshots)
            logger.info(f"Exported {len(snapshots)} snapshots → {snapshots_file}")

        except Exception as e:
            logger.error(f"CSV export failed: {e}")
