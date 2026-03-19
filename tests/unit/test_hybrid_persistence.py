"""Unit tests for HybridPersistence (SQLite + JSON backup layer)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.data.models import Order, OrderSide, OrderStatus, OrderType, PortfolioSnapshot


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
def mock_json():
    j = MagicMock()
    j.load_portfolio_snapshots.return_value = []
    j.load_trade_history.return_value = []
    return j


@pytest.fixture
def hybrid(monkeypatch, mock_db, mock_json):
    monkeypatch.setattr("src.utils.hybrid_persistence.DatabasePersistence", lambda: mock_db)
    monkeypatch.setattr("src.utils.hybrid_persistence.DataPersistence", lambda: mock_json)
    from src.utils.hybrid_persistence import HybridPersistence

    return HybridPersistence(backup_enabled=True), mock_db, mock_json


@pytest.fixture
def hybrid_no_backup(monkeypatch, mock_db):
    monkeypatch.setattr("src.utils.hybrid_persistence.DatabasePersistence", lambda: mock_db)
    from src.utils.hybrid_persistence import HybridPersistence

    return HybridPersistence(backup_enabled=False), mock_db


class TestSession:
    def test_start_session_calls_db(self, hybrid):
        h, db, _ = hybrid
        h.start_session("momentum", "moderate", "paper", ["BTC-EUR"], Decimal("10000"))
        db.create_session.assert_called_once()
        assert h.current_session_id == 42

    def test_end_session_calls_db(self, hybrid):
        h, db, _ = hybrid
        h.current_session_id = 42
        h.end_session(Decimal("10500"), Decimal("500"), 5)
        db.end_session.assert_called_once_with(
            session_id=42,
            final_balance=Decimal("10500"),
            total_pnl=Decimal("500"),
            total_trades=5,
        )

    def test_end_session_without_active_session_is_noop(self, hybrid):
        h, db, _ = hybrid
        h.current_session_id = None
        h.end_session(Decimal("100"), Decimal("0"), 0)
        db.end_session.assert_not_called()


class TestSavePortfolioSnapshot:
    def test_saves_to_db(self, hybrid):
        h, db, _ = hybrid
        s = make_snapshot()
        h.save_portfolio_snapshot(s, "momentum", "moderate", "paper")
        db.save_portfolio_snapshot.assert_called_once()

    def test_no_backup_when_just_backed_up(self, hybrid):
        h, db, json_mock = hybrid
        h.last_backup = datetime.now(UTC)  # Just backed up
        h.save_portfolio_snapshot(make_snapshot(), "m", "c", "p")
        json_mock.save_portfolio_snapshots.assert_not_called()

    def test_backup_triggered_when_stale(self, hybrid):
        h, db, json_mock = hybrid
        h.last_backup = datetime.now(UTC) - timedelta(days=2)
        db.load_portfolio_snapshots.return_value = []
        h.save_portfolio_snapshot(make_snapshot(), "m", "c", "p")
        json_mock.save_portfolio_snapshots.assert_called()


class TestSavePortfolioSnapshotsBulk:
    def test_saves_to_db_and_json(self, hybrid):
        h, db, json_mock = hybrid
        snapshots = [make_snapshot()]
        h.save_portfolio_snapshots_bulk(snapshots, {"strategy": "m"})
        db.save_portfolio_snapshots_bulk.assert_called_once()
        json_mock.save_portfolio_snapshots.assert_called_once()

    def test_empty_list_is_noop(self, hybrid):
        h, db, json_mock = hybrid
        h.save_portfolio_snapshots_bulk([], {})
        db.save_portfolio_snapshots_bulk.assert_not_called()

    def test_no_backup_when_disabled(self, hybrid_no_backup):
        h, db = hybrid_no_backup
        h.save_portfolio_snapshots_bulk([make_snapshot()], {})
        db.save_portfolio_snapshots_bulk.assert_called_once()


class TestLoadPortfolioSnapshots:
    def test_loads_from_db_by_default(self, hybrid):
        h, db, _ = hybrid
        db.load_portfolio_snapshots.return_value = [{"total_value": "10000"}]
        results = h.load_portfolio_snapshots()
        db.load_portfolio_snapshots.assert_called_once()
        assert len(results) == 1

    def test_loads_from_json_when_from_backup(self, hybrid):
        h, db, json_mock = hybrid
        json_mock.load_portfolio_snapshots.return_value = [make_snapshot()]
        results = h.load_portfolio_snapshots(from_backup=True)
        json_mock.load_portfolio_snapshots.assert_called_once()
        assert len(results) == 1
        assert "total_value" in results[0]


class TestSaveTrade:
    def test_saves_to_db_and_json(self, hybrid):
        h, db, json_mock = hybrid
        h.save_trade(make_order())
        db.save_trade.assert_called_once()
        json_mock.save_trade.assert_called_once()

    def test_no_json_backup_when_disabled(self, hybrid_no_backup):
        h, db = hybrid_no_backup
        h.save_trade(make_order())
        db.save_trade.assert_called_once()


class TestLoadTradeHistory:
    def test_loads_from_db_by_default(self, hybrid):
        h, db, _ = hybrid
        db.load_trade_history.return_value = [{"symbol": "BTC-EUR"}]
        results = h.load_trade_history()
        db.load_trade_history.assert_called_once()
        assert len(results) == 1

    def test_loads_from_json_when_from_backup(self, hybrid):
        h, _, json_mock = hybrid
        json_mock.load_trade_history.return_value = [{"symbol": "ETH-EUR"}]
        results = h.load_trade_history(from_backup=True)
        json_mock.load_trade_history.assert_called_once()

    def test_passes_filters_to_db(self, hybrid):
        h, db, _ = hybrid
        since = datetime.now(UTC)
        h.load_trade_history(since=since, symbol="BTC-EUR", limit=10)
        db.load_trade_history.assert_called_once_with(since, "BTC-EUR", 10)


class TestGetAnalytics:
    def test_delegates_to_db(self, hybrid):
        h, db, _ = hybrid
        db.get_analytics.return_value = {"total_trades": 5}
        result = h.get_analytics(days=7)
        db.get_analytics.assert_called_once_with(7)
        assert result["total_trades"] == 5


class TestShouldBackup:
    def test_false_when_backed_up_recently(self, hybrid):
        h, _, _ = hybrid
        h.last_backup = datetime.now(UTC)
        assert h._should_backup() is False

    def test_true_when_day_has_passed(self, hybrid):
        h, _, _ = hybrid
        h.last_backup = datetime.now(UTC) - timedelta(days=2)
        assert h._should_backup() is True


class TestExportToCsv:
    def test_export_creates_csv_files(self, hybrid, tmp_path):
        h, db, _ = hybrid
        db.load_trade_history.return_value = [
            {"symbol": "BTC-EUR", "side": "BUY", "quantity": "0.1",
             "price": "50000", "status": "FILLED", "created_at": "2024-01-01T00:00:00"}
        ]
        db.load_portfolio_snapshots.return_value = [
            {"timestamp": "2024-01-01T00:00:00", "total_value": "10000"}
        ]
        output_dir = tmp_path / "exports"
        h.export_to_csv(output_dir=output_dir)
        csv_files = list(output_dir.glob("*.csv"))
        assert len(csv_files) == 2

    def test_export_handles_empty_data(self, hybrid, tmp_path):
        h, db, _ = hybrid
        db.load_trade_history.return_value = []
        db.load_portfolio_snapshots.return_value = []
        output_dir = tmp_path / "exports"
        h.export_to_csv(output_dir=output_dir)
        # Should not raise
