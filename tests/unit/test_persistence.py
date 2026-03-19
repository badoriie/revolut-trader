"""Unit tests for JSON-based DataPersistence."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from src.models.domain import Order, OrderSide, OrderStatus, OrderType, PortfolioSnapshot
from src.utils.persistence import DataPersistence


def make_snapshot(total_value: int = 10000, cash: int = 9000) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        timestamp=datetime.now(UTC),
        total_value=Decimal(str(total_value)),
        cash_balance=Decimal(str(cash)),
        positions_value=Decimal(str(total_value - cash)),
        unrealized_pnl=Decimal("100"),
        realized_pnl=Decimal("50"),
        total_pnl=Decimal("150"),
        daily_pnl=Decimal("20"),
        num_positions=2,
    )


def make_order(symbol: str = "BTC-EUR", with_price: bool = True) -> Order:
    return Order(
        order_id="test-123",
        symbol=symbol,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.1"),
        price=Decimal("50000") if with_price else None,
        status=OrderStatus.FILLED,
        strategy="momentum",
    )


@pytest.fixture
def persistence(tmp_path):
    return DataPersistence(data_dir=tmp_path)


class TestDataPersistenceInit:
    def test_creates_data_directory(self, tmp_path):
        new_dir = tmp_path / "sub" / "data"
        DataPersistence(data_dir=new_dir)
        assert new_dir.exists()

    def test_files_are_set_relative_to_data_dir(self, tmp_path):
        dp = DataPersistence(data_dir=tmp_path)
        assert dp.snapshots_file.parent == tmp_path
        assert dp.trades_file.parent == tmp_path
        assert dp.session_file.parent == tmp_path


class TestPortfolioSnapshots:
    def test_load_empty_when_no_file(self, persistence):
        assert persistence.load_portfolio_snapshots() == []

    def test_save_and_load_single_snapshot(self, persistence):
        s = make_snapshot()
        persistence.save_portfolio_snapshots([s])
        loaded = persistence.load_portfolio_snapshots()
        assert len(loaded) == 1
        assert loaded[0].total_value == s.total_value
        assert loaded[0].cash_balance == s.cash_balance
        assert loaded[0].num_positions == s.num_positions

    def test_save_and_load_multiple_snapshots(self, persistence):
        snapshots = [make_snapshot(10000 + i * 100, 9000) for i in range(5)]
        persistence.save_portfolio_snapshots(snapshots)
        loaded = persistence.load_portfolio_snapshots()
        assert len(loaded) == 5

    def test_save_overwrites_previous_snapshots(self, persistence):
        persistence.save_portfolio_snapshots([make_snapshot(10000)])
        persistence.save_portfolio_snapshots([make_snapshot(20000)])
        loaded = persistence.load_portfolio_snapshots()
        assert len(loaded) == 1
        assert loaded[0].total_value == Decimal("20000")

    def test_snapshot_decimal_precision_preserved(self, persistence):
        s = make_snapshot(10000)
        persistence.save_portfolio_snapshots([s])
        loaded = persistence.load_portfolio_snapshots()
        assert loaded[0].unrealized_pnl == Decimal("100")
        assert loaded[0].realized_pnl == Decimal("50")


class TestTrades:
    def test_load_empty_when_no_file(self, persistence):
        assert persistence.load_trade_history() == []

    def test_save_and_load_single_trade(self, persistence):
        persistence.save_trade(make_order())
        trades = persistence.load_trade_history()
        assert len(trades) == 1
        assert trades[0]["symbol"] == "BTC-EUR"
        assert trades[0]["side"] == "BUY"

    def test_trades_append_on_each_save(self, persistence):
        for _ in range(3):
            persistence.save_trade(make_order())
        trades = persistence.load_trade_history()
        assert len(trades) == 3

    def test_order_without_price_saved_as_none(self, persistence):
        persistence.save_trade(make_order(with_price=False))
        trades = persistence.load_trade_history()
        assert trades[0]["price"] is None

    def test_trade_fields_serialized_correctly(self, persistence):
        order = make_order()
        persistence.save_trade(order)
        trades = persistence.load_trade_history()
        t = trades[0]
        assert t["order_id"] == "test-123"
        assert t["quantity"] == "0.1"
        assert t["status"] == "FILLED"
        assert t["strategy"] == "momentum"

    def test_load_handles_missing_file_gracefully(self, persistence):
        # File doesn't exist, should return empty list
        result = persistence.load_trade_history()
        assert result == []


class TestSessionData:
    def test_load_returns_none_when_no_file(self, persistence):
        assert persistence.load_session_data() is None

    def test_save_and_load_session(self, persistence):
        persistence.save_session_data(
            cash_balance=Decimal("9500"),
            total_pnl=Decimal("-500"),
            metadata={"strategy": "momentum", "pairs": ["BTC-EUR"]},
        )
        data = persistence.load_session_data()
        assert data is not None
        assert data["cash_balance"] == "9500"
        assert data["total_pnl"] == "-500"
        assert data["metadata"]["strategy"] == "momentum"

    def test_session_has_timestamp(self, persistence):
        persistence.save_session_data(Decimal("1000"), Decimal("0"), {})
        data = persistence.load_session_data()
        assert "timestamp" in data

    def test_clear_session_removes_file(self, persistence):
        persistence.save_session_data(Decimal("100"), Decimal("0"), {})
        assert persistence.session_file.exists()
        persistence.clear_session_data()
        assert not persistence.session_file.exists()
        assert persistence.load_session_data() is None

    def test_clear_session_when_no_file_is_noop(self, persistence):
        # Should not raise
        persistence.clear_session_data()


class TestErrorHandling:
    def test_save_snapshots_handles_write_error(self, persistence):
        with patch("builtins.open", side_effect=OSError("disk full")):
            persistence.save_portfolio_snapshots([make_snapshot()])  # Should not raise

    def test_load_snapshots_handles_invalid_json(self, persistence):
        persistence.snapshots_file.write_text("not-valid-json")
        result = persistence.load_portfolio_snapshots()
        assert result == []

    def test_save_trade_handles_write_error(self, persistence):
        with patch("builtins.open", side_effect=OSError("disk full")):
            persistence.save_trade(make_order())  # Should not raise

    def test_load_trades_handles_invalid_json(self, persistence):
        persistence.trades_file.write_text("not-valid-json")
        result = persistence.load_trade_history()
        assert result == []

    def test_save_session_handles_write_error(self, persistence):
        with patch("builtins.open", side_effect=OSError("disk full")):
            persistence.save_session_data(Decimal("100"), Decimal("0"), {})  # Should not raise

    def test_load_session_handles_invalid_json(self, persistence):
        persistence.session_file.write_text("not-valid-json")
        result = persistence.load_session_data()
        assert result is None

    def test_clear_session_handles_error(self, persistence):
        persistence.save_session_data(Decimal("100"), Decimal("0"), {})
        with patch("pathlib.Path.unlink", side_effect=OSError("permission denied")):
            persistence.clear_session_data()  # Should not raise
