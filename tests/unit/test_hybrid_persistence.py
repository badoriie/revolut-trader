"""Unit tests for HybridPersistence (database-only persistence facade)."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.models.domain import Order, OrderSide, OrderStatus, OrderType, PortfolioSnapshot


def make_snapshot() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        timestamp=datetime.now(UTC),
        total_value=Decimal("10000"),
        cash_balance=Decimal("9000"),
        positions_value=Decimal("1000"),
        unrealized_pnl=Decimal("100"),
        realized_pnl=Decimal("50"),
        total_pnl=Decimal("150"),
        daily_pnl=Decimal("20"),
        num_positions=1,
    )


def make_order() -> Order:
    return Order(
        order_id="order-1",
        symbol="BTC-EUR",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.1"),
        price=Decimal("50000"),
        status=OrderStatus.FILLED,
    )


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.create_session.return_value = 42
    db.load_portfolio_snapshots.return_value = []
    db.load_trade_history.return_value = []
    db.get_analytics.return_value = {"total_trades": 0}
    return db


@pytest.fixture
def persistence(monkeypatch, mock_db):
    monkeypatch.setattr("src.utils.hybrid_persistence.DatabasePersistence", lambda: mock_db)
    from src.utils.hybrid_persistence import HybridPersistence

    return HybridPersistence(), mock_db


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


class TestSession:
    def test_start_session_calls_db(self, persistence):
        h, db = persistence
        h.start_session("momentum", "moderate", "paper", ["BTC-EUR"], Decimal("10000"))
        db.create_session.assert_called_once()
        assert h.current_session_id == 42

    def test_end_session_calls_db(self, persistence):
        h, db = persistence
        h.current_session_id = 42
        h.end_session(Decimal("10500"), Decimal("500"), 5)
        db.end_session.assert_called_once_with(
            session_id=42,
            final_balance=Decimal("10500"),
            total_pnl=Decimal("500"),
            total_trades=5,
        )

    def test_end_session_without_active_session_is_noop(self, persistence):
        h, db = persistence
        h.current_session_id = None
        h.end_session(Decimal("100"), Decimal("0"), 0)
        db.end_session.assert_not_called()


# ---------------------------------------------------------------------------
# Portfolio snapshots
# ---------------------------------------------------------------------------


class TestSavePortfolioSnapshot:
    def test_delegates_to_db(self, persistence):
        h, db = persistence
        s = make_snapshot()
        h.save_portfolio_snapshot(s, "momentum", "moderate", "paper")
        db.save_portfolio_snapshot.assert_called_once_with(s, "momentum", "moderate", "paper")


class TestSavePortfolioSnapshotsBulk:
    def test_delegates_to_db(self, persistence):
        h, db = persistence
        snapshots = [make_snapshot()]
        h.save_portfolio_snapshots_bulk(snapshots, {"strategy": "m"})
        db.save_portfolio_snapshots_bulk.assert_called_once_with(snapshots, {"strategy": "m"})

    def test_empty_list_is_noop(self, persistence):
        h, db = persistence
        h.save_portfolio_snapshots_bulk([], {})
        db.save_portfolio_snapshots_bulk.assert_not_called()


class TestLoadPortfolioSnapshots:
    def test_delegates_to_db(self, persistence):
        h, db = persistence
        db.load_portfolio_snapshots.return_value = [{"total_value": "10000"}]
        results = h.load_portfolio_snapshots()
        db.load_portfolio_snapshots.assert_called_once()
        assert len(results) == 1

    def test_passes_filters_to_db(self, persistence):
        h, db = persistence
        since = datetime.now(UTC)
        h.load_portfolio_snapshots(since=since, limit=50)
        db.load_portfolio_snapshots.assert_called_once_with(since, 50)


# ---------------------------------------------------------------------------
# Trades
# ---------------------------------------------------------------------------


class TestSaveTrade:
    def test_delegates_to_db(self, persistence):
        h, db = persistence
        order = make_order()
        h.save_trade(order)
        db.save_trade.assert_called_once_with(order)


class TestLoadTradeHistory:
    def test_delegates_to_db(self, persistence):
        h, db = persistence
        db.load_trade_history.return_value = [{"symbol": "BTC-EUR"}]
        results = h.load_trade_history()
        db.load_trade_history.assert_called_once()
        assert len(results) == 1

    def test_passes_filters_to_db(self, persistence):
        h, db = persistence
        since = datetime.now(UTC)
        h.load_trade_history(since=since, symbol="BTC-EUR", limit=10)
        db.load_trade_history.assert_called_once_with(since, "BTC-EUR", 10)


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


class TestGetAnalytics:
    def test_delegates_to_db(self, persistence):
        h, db = persistence
        db.get_analytics.return_value = {"total_trades": 5}
        result = h.get_analytics(days=7)
        db.get_analytics.assert_called_once_with(7)
        assert result["total_trades"] == 5


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------


class TestExportToCsv:
    def test_export_creates_csv_files(self, persistence, tmp_path):
        h, db = persistence
        db.load_trade_history.return_value = [
            {
                "symbol": "BTC-EUR",
                "side": "BUY",
                "quantity": "0.1",
                "price": "50000",
                "status": "FILLED",
                "created_at": "2024-01-01T00:00:00",
            }
        ]
        db.load_portfolio_snapshots.return_value = [
            {"timestamp": "2024-01-01T00:00:00", "total_value": "10000"}
        ]
        h.export_to_csv(output_dir=tmp_path / "exports")
        assert len(list((tmp_path / "exports").glob("*.csv"))) == 2

    def test_export_handles_empty_data(self, persistence, tmp_path):
        h, db = persistence
        db.load_trade_history.return_value = []
        db.load_portfolio_snapshots.return_value = []
        h.export_to_csv(output_dir=tmp_path / "exports")
        # Should not raise
