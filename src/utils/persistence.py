"""Data persistence module for portfolio snapshots and trade history."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from loguru import logger

from src.data.models import Order, PortfolioSnapshot


class DataPersistence:
    """Handles saving and loading trading data to/from disk."""

    def __init__(self, data_dir: Path = Path("data")):
        """Initialize data persistence.

        Args:
            data_dir: Directory to store data files (default: ./data)
        """
        self.data_dir = data_dir
        self.snapshots_file = data_dir / "portfolio_snapshots.json"
        self.trades_file = data_dir / "trade_history.json"
        self.session_file = data_dir / "current_session.json"

        # Create data directory if it doesn't exist
        self.data_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Data persistence initialized: {self.data_dir}")

    def save_portfolio_snapshots(self, snapshots: list[PortfolioSnapshot]) -> None:
        """Save portfolio snapshots to disk.

        Args:
            snapshots: List of portfolio snapshots to save
        """
        try:
            data = [self._snapshot_to_dict(s) for s in snapshots]

            with open(self.snapshots_file, "w") as f:
                json.dump(data, f, indent=2)

            logger.debug(f"Saved {len(snapshots)} portfolio snapshots")

        except Exception as e:
            logger.error(f"Failed to save portfolio snapshots: {e}")

    def load_portfolio_snapshots(self) -> list[PortfolioSnapshot]:
        """Load portfolio snapshots from disk.

        Returns:
            List of portfolio snapshots (empty if file doesn't exist or error)
        """
        if not self.snapshots_file.exists():
            logger.info("No existing portfolio snapshots found")
            return []

        try:
            with open(self.snapshots_file) as f:
                data = json.load(f)

            snapshots = [self._dict_to_snapshot(d) for d in data]
            logger.info(f"Loaded {len(snapshots)} portfolio snapshots")
            return snapshots

        except Exception as e:
            logger.error(f"Failed to load portfolio snapshots: {e}")
            return []

    def save_trade(self, order: Order) -> None:
        """Append a completed trade to trade history.

        Args:
            order: Completed order to save
        """
        try:
            # Load existing trades
            trades = self._load_trades_raw()

            # Add new trade
            trades.append(self._order_to_dict(order))

            # Save back to file
            with open(self.trades_file, "w") as f:
                json.dump(trades, f, indent=2)

            logger.debug(f"Saved trade: {order.symbol} {order.side} {order.quantity}")

        except Exception as e:
            logger.error(f"Failed to save trade: {e}")

    def load_trade_history(self) -> list[dict[str, Any]]:
        """Load trade history from disk.

        Returns:
            List of trade dictionaries (empty if file doesn't exist or error)
        """
        if not self.trades_file.exists():
            logger.info("No existing trade history found")
            return []

        try:
            trades = self._load_trades_raw()
            logger.info(f"Loaded {len(trades)} trades from history")
            return trades

        except Exception as e:
            logger.error(f"Failed to load trade history: {e}")
            return []

    def save_session_data(
        self, cash_balance: Decimal, total_pnl: Decimal, metadata: dict[str, Any]
    ) -> None:
        """Save current session data (for bot restarts).

        Args:
            cash_balance: Current cash balance
            total_pnl: Total profit/loss
            metadata: Additional session metadata
        """
        try:
            data = {
                "timestamp": datetime.now(UTC).isoformat(),
                "cash_balance": str(cash_balance),
                "total_pnl": str(total_pnl),
                "metadata": metadata,
            }

            with open(self.session_file, "w") as f:
                json.dump(data, f, indent=2)

            logger.debug("Saved session data")

        except Exception as e:
            logger.error(f"Failed to save session data: {e}")

    def load_session_data(self) -> dict[str, Any] | None:
        """Load session data from disk.

        Returns:
            Session data dictionary or None if doesn't exist
        """
        if not self.session_file.exists():
            logger.info("No existing session data found")
            return None

        try:
            with open(self.session_file) as f:
                data = json.load(f)

            logger.info("Loaded session data")
            return data

        except Exception as e:
            logger.error(f"Failed to load session data: {e}")
            return None

    def clear_session_data(self) -> None:
        """Clear session data file (typically called on clean shutdown)."""
        try:
            if self.session_file.exists():
                self.session_file.unlink()
                logger.info("Cleared session data")
        except Exception as e:
            logger.error(f"Failed to clear session data: {e}")

    def _snapshot_to_dict(self, snapshot: PortfolioSnapshot) -> dict[str, Any]:
        """Convert PortfolioSnapshot to dictionary for JSON serialization."""
        return {
            "timestamp": snapshot.timestamp.isoformat(),
            "total_value": str(snapshot.total_value),
            "cash_balance": str(snapshot.cash_balance),
            "positions_value": str(snapshot.positions_value),
            "unrealized_pnl": str(snapshot.unrealized_pnl),
            "realized_pnl": str(snapshot.realized_pnl),
            "total_pnl": str(snapshot.total_pnl),
            "daily_pnl": str(snapshot.daily_pnl),
            "num_positions": snapshot.num_positions,
        }

    def _dict_to_snapshot(self, data: dict[str, Any]) -> PortfolioSnapshot:
        """Convert dictionary to PortfolioSnapshot."""
        return PortfolioSnapshot(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            total_value=Decimal(data["total_value"]),
            cash_balance=Decimal(data["cash_balance"]),
            positions_value=Decimal(data["positions_value"]),
            unrealized_pnl=Decimal(data["unrealized_pnl"]),
            realized_pnl=Decimal(data["realized_pnl"]),
            total_pnl=Decimal(data["total_pnl"]),
            daily_pnl=Decimal(data["daily_pnl"]),
            num_positions=data["num_positions"],
        )

    def _order_to_dict(self, order: Order) -> dict[str, Any]:
        """Convert Order to dictionary for JSON serialization."""
        return {
            "order_id": order.order_id,
            "symbol": order.symbol,
            "side": order.side.value,
            "order_type": order.order_type.value,
            "quantity": str(order.quantity),
            "price": str(order.price) if order.price else None,
            "filled_quantity": str(order.filled_quantity),
            "status": order.status.value,
            "strategy": order.strategy,
            "created_at": order.created_at.isoformat(),
        }

    def _load_trades_raw(self) -> list[dict[str, Any]]:
        """Load raw trade data from file."""
        if not self.trades_file.exists():
            return []

        with open(self.trades_file) as f:
            return json.load(f)
