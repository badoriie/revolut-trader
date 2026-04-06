"""Unit tests for DatabasePersistence (SQLAlchemy + SQLite)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from src.models.domain import Order, OrderSide, OrderStatus, OrderType, PortfolioSnapshot


def make_snapshot(total_value: float = 10000.0) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        timestamp=datetime.now(UTC),
        total_value=Decimal(str(total_value)),
        cash_balance=Decimal("9000"),
        positions_value=Decimal(str(total_value - 9000)),
        unrealized_pnl=Decimal("100"),
        realized_pnl=Decimal("50"),
        total_pnl=Decimal("150"),
        daily_pnl=Decimal("20"),
        num_positions=1,
    )


def make_order(symbol: str = "BTC-EUR") -> Order:
    return Order(
        order_id=f"order-{symbol}",
        symbol=symbol,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.1"),
        price=Decimal("50000"),
        status=OrderStatus.FILLED,
        strategy="momentum",
    )


@pytest.fixture
def db_persistence(tmp_path, monkeypatch):
    db_url = f"sqlite:///{tmp_path}/test.db"
    monkeypatch.setenv("REVT_DATA_DIR", str(tmp_path))
    test_engine = create_engine(db_url)
    monkeypatch.setattr("src.utils.db_persistence.create_db_engine", lambda url=None: test_engine)
    from src.utils.db_persistence import DatabasePersistence

    db = DatabasePersistence()
    yield db
    db.engine.pool.dispose()
    db.engine.dispose()


class TestSaveLoadPortfolioSnapshots:
    def test_load_empty_returns_empty_list(self, db_persistence):
        assert db_persistence.load_portfolio_snapshots() == []

    def test_save_and_load_single_snapshot(self, db_persistence):
        s = make_snapshot()
        db_persistence.save_portfolio_snapshot(s, "momentum", "conservative", "paper")
        results = db_persistence.load_portfolio_snapshots()
        assert len(results) == 1
        assert float(results[0]["total_value"]) == pytest.approx(10000.0)

    def test_load_respects_limit(self, db_persistence):
        for _ in range(5):
            db_persistence.save_portfolio_snapshot(make_snapshot(), "m", "c", "p")
        results = db_persistence.load_portfolio_snapshots(limit=3)
        assert len(results) == 3

    def test_load_with_since_filter(self, db_persistence):
        old = PortfolioSnapshot(
            timestamp=datetime(2020, 1, 1, tzinfo=UTC),
            total_value=Decimal("5000"),
            cash_balance=Decimal("5000"),
            positions_value=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            realized_pnl=Decimal("0"),
            total_pnl=Decimal("0"),
            daily_pnl=Decimal("0"),
            num_positions=0,
        )
        db_persistence.save_portfolio_snapshot(old, "m", "c", "p")
        db_persistence.save_portfolio_snapshot(make_snapshot(), "m", "c", "p")
        since = datetime(2023, 1, 1, tzinfo=UTC)
        results = db_persistence.load_portfolio_snapshots(since=since)
        assert len(results) == 1

    def test_bulk_save_snapshots(self, db_persistence):
        snapshots = [make_snapshot() for _ in range(3)]
        metadata = {"strategy": "m", "risk_level": "c", "trading_mode": "p"}
        db_persistence.save_portfolio_snapshots_bulk(snapshots, metadata)
        results = db_persistence.load_portfolio_snapshots()
        assert len(results) == 3

    def test_bulk_save_empty_list_is_noop(self, db_persistence):
        db_persistence.save_portfolio_snapshots_bulk([], {})
        assert db_persistence.load_portfolio_snapshots() == []


class TestSaveLoadTrades:
    def test_load_empty_returns_empty_list(self, db_persistence):
        assert db_persistence.load_trade_history() == []

    def test_save_and_load_trade(self, db_persistence):
        db_persistence.save_trade(make_order())
        trades = db_persistence.load_trade_history()
        assert len(trades) == 1
        assert trades[0]["symbol"] == "BTC-EUR"

    def test_load_with_symbol_filter(self, db_persistence):
        db_persistence.save_trade(make_order("BTC-EUR"))
        db_persistence.save_trade(make_order("ETH-EUR"))
        results = db_persistence.load_trade_history(symbol="BTC-EUR")
        assert len(results) == 1
        assert results[0]["symbol"] == "BTC-EUR"

    def test_load_with_limit(self, db_persistence):
        for i in range(5):
            db_persistence.save_trade(make_order(f"SYM-{i}"))
        results = db_persistence.load_trade_history(limit=2)
        assert len(results) == 2

    def test_save_trade_without_strategy(self, db_persistence):
        order = Order(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.1"),
            status=OrderStatus.FILLED,
        )
        db_persistence.save_trade(order)
        trades = db_persistence.load_trade_history()
        assert len(trades) == 1

    def test_load_trade_with_since_filter(self, db_persistence):
        db_persistence.save_trade(make_order())
        since = datetime.now(UTC) + timedelta(days=1)
        results = db_persistence.load_trade_history(since=since)
        assert len(results) == 0


class TestSessionManagement:
    def test_create_session_returns_int_id(self, db_persistence):
        session_id = db_persistence.create_session(
            strategy="momentum",
            risk_level="moderate",
            trading_mode="paper",
            trading_pairs=["BTC-EUR", "ETH-EUR"],
            initial_balance=Decimal("10000"),
        )
        assert isinstance(session_id, int)
        assert session_id > 0

    def test_end_session_updates_record(self, db_persistence):
        sid = db_persistence.create_session(
            strategy="m",
            risk_level="c",
            trading_mode="p",
            trading_pairs=["BTC-EUR"],
            initial_balance=Decimal("10000"),
        )
        db_persistence.end_session(
            session_id=sid,
            final_balance=Decimal("10500"),
            total_pnl=Decimal("500"),
            total_trades=3,
        )

    def test_end_nonexistent_session_is_noop(self, db_persistence):
        db_persistence.end_session(
            session_id=9999,
            final_balance=Decimal("100"),
            total_pnl=Decimal("0"),
            total_trades=0,
        )


class TestAnalytics:
    def test_get_analytics_empty_database(self, db_persistence):
        analytics = db_persistence.get_analytics(days=30)
        assert isinstance(analytics, dict)
        assert analytics.get("total_trades", 0) == 0

    def test_get_analytics_with_snapshot(self, db_persistence):
        db_persistence.save_portfolio_snapshot(make_snapshot(), "m", "c", "p")
        analytics = db_persistence.get_analytics(days=30)
        assert analytics.get("total_snapshots", 0) == 1


class TestBacktestRuns:
    def test_save_and_load_backtest_run(self, db_persistence):
        results = {
            "final_capital": 11000.0,
            "total_pnl": 1000.0,
            "return_pct": 10.0,
            "total_trades": 5,
            "winning_trades": 3,
            "losing_trades": 2,
            "win_rate": 60.0,
            "profit_factor": 2.0,
            "max_drawdown": 200.0,
            "sharpe_ratio": 1.5,
        }
        run_id = db_persistence.save_backtest_run(
            strategy="momentum",
            risk_level="moderate",
            symbols=["BTC-EUR"],
            days=30,
            interval="60m",
            initial_capital=10000.0,
            results=results,
        )
        assert run_id > 0
        runs = db_persistence.load_backtest_runs()
        assert len(runs) == 1

    def test_get_backtest_analytics_empty(self, db_persistence):
        analytics = db_persistence.get_backtest_analytics()
        assert analytics.get("total_runs", 0) == 0

    def test_get_backtest_analytics_with_data(self, db_persistence):
        results = {
            "final_capital": 11000.0,
            "total_pnl": 1000.0,
            "return_pct": 10.0,
            "total_trades": 5,
            "winning_trades": 3,
            "losing_trades": 2,
            "win_rate": 60.0,
            "profit_factor": 2.0,
            "max_drawdown": 200.0,
            "sharpe_ratio": 1.5,
        }
        db_persistence.save_backtest_run("m", "c", ["BTC-EUR"], 30, "60m", 10000.0, results)
        analytics = db_persistence.get_backtest_analytics()
        assert analytics.get("total_runs", 0) == 1


class TestLogEntries:
    def test_save_and_load_log_entry(self, db_persistence):
        db_persistence.save_log_entry("ERROR", "Something went wrong", module="executor")
        entries = db_persistence.load_log_entries()
        assert len(entries) == 1
        assert entries[0]["level"] == "ERROR"

    def test_load_log_entries_with_level_filter(self, db_persistence):
        db_persistence.save_log_entry("INFO", "Info message")
        db_persistence.save_log_entry("ERROR", "Error message")
        errors = db_persistence.load_log_entries(level="ERROR")
        assert len(errors) == 1

    def test_load_log_entries_empty(self, db_persistence):
        assert db_persistence.load_log_entries() == []

    def test_save_log_without_module(self, db_persistence):
        db_persistence.save_log_entry("WARNING", "no module")
        entries = db_persistence.load_log_entries()
        assert len(entries) == 1
        assert entries[0]["module"] is None

    def test_load_log_entries_with_since_filter(self, db_persistence):
        db_persistence.save_log_entry("INFO", "old message")
        since = datetime.now(UTC) + timedelta(days=1)
        entries = db_persistence.load_log_entries(since=since)
        assert len(entries) == 0


class TestCsvExport:
    def test_export_creates_csv_files(self, db_persistence, tmp_path):
        db_persistence.save_trade(make_order())
        db_persistence.save_portfolio_snapshot(make_snapshot(), "m", "c", "p")

        export_dir = tmp_path / "exports"
        db_persistence.export_to_csv(output_dir=export_dir)

        csv_files = list(export_dir.glob("*.csv"))
        assert len(csv_files) == 2

    def test_export_empty_db_creates_empty_files(self, db_persistence, tmp_path):
        export_dir = tmp_path / "exports"
        db_persistence.export_to_csv(output_dir=export_dir)
        csv_files = list(export_dir.glob("*.csv"))
        assert len(csv_files) == 2
        # Files exist but contain no data rows
        for f in csv_files:
            assert f.read_text() == ""

    def test_export_handles_exception_gracefully(self, db_persistence, tmp_path):
        with patch.object(db_persistence, "load_trade_history", side_effect=Exception("boom")):
            db_persistence.export_to_csv(output_dir=tmp_path / "exports")
            # Should not raise


class TestSessionContextManagerError:
    """Test the _session() rollback path (except SQLAlchemyError)."""

    def test_session_rolls_back_on_sqlalchemy_error(self, db_persistence):
        """Force a SQLAlchemyError to exercise _session() rollback + re-raise."""
        with pytest.raises(SQLAlchemyError), db_persistence._session() as _sess:
            raise SQLAlchemyError("forced error")

    def test_save_snapshot_swallows_sqlalchemy_error(self, db_persistence):
        with patch.object(db_persistence, "_session", side_effect=SQLAlchemyError("db fail")):
            db_persistence.save_portfolio_snapshot(make_snapshot(), "m", "c", "p")
            # Should not raise

    def test_bulk_save_swallows_sqlalchemy_error(self, db_persistence):
        with patch.object(db_persistence, "_session", side_effect=SQLAlchemyError("db fail")):
            db_persistence.save_portfolio_snapshots_bulk(
                [make_snapshot()], {"strategy": "m", "risk_level": "c", "trading_mode": "p"}
            )

    def test_load_snapshots_returns_empty_on_error(self, db_persistence):
        with patch.object(db_persistence, "_session", side_effect=SQLAlchemyError("db fail")):
            assert db_persistence.load_portfolio_snapshots() == []

    def test_save_trade_swallows_sqlalchemy_error(self, db_persistence):
        with patch.object(db_persistence, "_session", side_effect=SQLAlchemyError("db fail")):
            db_persistence.save_trade(make_order())

    def test_load_trades_returns_empty_on_error(self, db_persistence):
        with patch.object(db_persistence, "_session", side_effect=SQLAlchemyError("db fail")):
            assert db_persistence.load_trade_history() == []

    def test_create_session_returns_neg1_on_error(self, db_persistence):
        with patch.object(db_persistence, "_session", side_effect=SQLAlchemyError("db fail")):
            result = db_persistence.create_session(
                strategy="m",
                risk_level="c",
                trading_mode="p",
                trading_pairs=["BTC-EUR"],
                initial_balance=Decimal("10000"),
            )
            assert result == -1

    def test_end_session_swallows_sqlalchemy_error(self, db_persistence):
        with patch.object(db_persistence, "_session", side_effect=SQLAlchemyError("db fail")):
            db_persistence.end_session(
                session_id=1,
                final_balance=Decimal("100"),
                total_pnl=Decimal("0"),
                total_trades=0,
            )

    def test_get_analytics_returns_empty_on_error(self, db_persistence):
        with patch.object(db_persistence, "_session", side_effect=SQLAlchemyError("db fail")):
            assert db_persistence.get_analytics() == {}

    def test_save_backtest_returns_neg1_on_error(self, db_persistence):
        with patch.object(db_persistence, "_session", side_effect=SQLAlchemyError("db fail")):
            result = db_persistence.save_backtest_run(
                "m",
                "c",
                ["BTC-EUR"],
                30,
                "60m",
                10000.0,
                {
                    "final_capital": 11000,
                    "total_pnl": 1000,
                    "return_pct": 10,
                    "total_trades": 5,
                    "winning_trades": 3,
                    "losing_trades": 2,
                    "win_rate": 60,
                    "max_drawdown": 200,
                },
            )
            assert result == -1

    def test_load_backtest_runs_returns_empty_on_error(self, db_persistence):
        with patch.object(db_persistence, "_session", side_effect=SQLAlchemyError("db fail")):
            assert db_persistence.load_backtest_runs() == []

    def test_get_backtest_analytics_returns_empty_on_error(self, db_persistence):
        with patch.object(db_persistence, "_session", side_effect=SQLAlchemyError("db fail")):
            assert db_persistence.get_backtest_analytics() == {}

    def test_save_log_entry_swallows_sqlalchemy_error(self, db_persistence):
        with patch.object(db_persistence, "_session", side_effect=SQLAlchemyError("db fail")):
            db_persistence.save_log_entry("ERROR", "boom")

    def test_load_log_entries_returns_empty_on_error(self, db_persistence):
        with patch.object(db_persistence, "_session", side_effect=SQLAlchemyError("db fail")):
            assert db_persistence.load_log_entries() == []


# ---------------------------------------------------------------------------
# Environment-aware DB URL
# ---------------------------------------------------------------------------


class TestEnvironmentAwareDbUrl:
    """Tests that the DB URL includes the environment name and data dir."""

    def test_db_url_includes_environment(self, monkeypatch):
        from src.models.db import get_db_url

        monkeypatch.setenv("REVT_DATA_DIR", "/custom/data")
        assert get_db_url("dev") == "sqlite:////custom/data/dev.db"
        assert get_db_url("int") == "sqlite:////custom/data/int.db"
        assert get_db_url("prod") == "sqlite:////custom/data/prod.db"

    def test_db_url_defaults_to_home(self, monkeypatch):
        from pathlib import Path

        from src.models.db import get_db_url

        monkeypatch.delenv("REVT_DATA_DIR", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "int")
        expected = f"sqlite:///{Path.home()}/revt-data/int.db"
        assert get_db_url() == expected

    def test_db_url_uses_custom_data_dir(self, monkeypatch):
        from src.models.db import get_db_url

        monkeypatch.setenv("REVT_DATA_DIR", "/opt/revt-data")
        monkeypatch.setenv("ENVIRONMENT", "prod")
        assert get_db_url() == "sqlite:////opt/revt-data/prod.db"


# ---------------------------------------------------------------------------
# Fee and P&L persistence tests
# ---------------------------------------------------------------------------


def make_order_with_pnl(
    symbol: str = "BTC-EUR",
    realized_pnl: Decimal | None = None,
    commission: Decimal = Decimal("0"),
    order_type: OrderType = OrderType.MARKET,
) -> Order:
    """Create a filled order with optional realized_pnl and commission."""
    order = Order(
        order_id=f"order-fee-{symbol}",
        symbol=symbol,
        side=OrderSide.SELL,
        order_type=order_type,
        quantity=Decimal("0.1"),
        price=Decimal("51000"),
        status=OrderStatus.FILLED,
        strategy="momentum",
        filled_quantity=Decimal("0.1"),
    )
    order.realized_pnl = realized_pnl
    order.commission = commission
    return order


class TestSaveTradeStoresPnlAndFee:
    def test_save_trade_stores_pnl(self, db_persistence):
        """realized_pnl on the order must be saved as pnl in the DB."""
        order = make_order_with_pnl(realized_pnl=Decimal("100.5"))
        db_persistence.save_trade(order)
        trades = db_persistence.load_trade_history()
        assert len(trades) == 1
        assert trades[0]["pnl"] is not None
        assert Decimal(trades[0]["pnl"]) == pytest.approx(Decimal("100.5"))

    def test_save_trade_stores_fee(self, db_persistence):
        """commission on the order must be saved as fee in the DB."""
        fee = Decimal("51000") * Decimal("0.1") * Decimal("0.0009")
        order = make_order_with_pnl(commission=fee)
        db_persistence.save_trade(order)
        trades = db_persistence.load_trade_history()
        assert len(trades) == 1
        assert trades[0]["fee"] is not None
        assert Decimal(trades[0]["fee"]) == pytest.approx(fee)

    def test_save_trade_null_pnl_when_not_set(self, db_persistence):
        """Order without realized_pnl must persist pnl as None."""
        order = make_order_with_pnl(realized_pnl=None, commission=Decimal("0"))
        db_persistence.save_trade(order)
        trades = db_persistence.load_trade_history()
        assert trades[0]["pnl"] is None

    def test_save_trade_null_fee_when_zero(self, db_persistence):
        """Order with commission=0 (LIMIT) must persist fee as None."""
        order = make_order_with_pnl(commission=Decimal("0"), order_type=OrderType.LIMIT)
        db_persistence.save_trade(order)
        trades = db_persistence.load_trade_history()
        assert trades[0]["fee"] is None

    def test_load_trade_history_includes_pnl_key(self, db_persistence):
        """All trade history dicts must include a 'pnl' key."""
        db_persistence.save_trade(make_order())
        trades = db_persistence.load_trade_history()
        assert "pnl" in trades[0]

    def test_load_trade_history_includes_fee_key(self, db_persistence):
        """All trade history dicts must include a 'fee' key."""
        db_persistence.save_trade(make_order())
        trades = db_persistence.load_trade_history()
        assert "fee" in trades[0]


class TestAnalyticsFeeAndLosingTrades:
    def test_analytics_total_fees_key_exists(self, db_persistence):
        """get_analytics() must always return a 'total_fees' key."""
        analytics = db_persistence.get_analytics(days=30)
        assert "total_fees" in analytics

    def test_analytics_losing_trades_key_exists(self, db_persistence):
        """get_analytics() must always return a 'losing_trades' key."""
        analytics = db_persistence.get_analytics(days=30)
        assert "losing_trades" in analytics

    def test_analytics_total_fees_sums_fees(self, db_persistence):
        """total_fees must be the sum of all fee values in the window."""
        fee1 = Decimal("4.59")
        fee2 = Decimal("2.31")
        db_persistence.save_trade(make_order_with_pnl(symbol="BTC-EUR", commission=fee1))
        db_persistence.save_trade(make_order_with_pnl(symbol="ETH-EUR", commission=fee2))
        analytics = db_persistence.get_analytics(days=30)
        assert analytics["total_fees"] == pytest.approx(float(fee1 + fee2), rel=1e-6)

    def test_analytics_losing_trades_counts_negative_pnl(self, db_persistence):
        """losing_trades must count trades with pnl < 0."""
        db_persistence.save_trade(make_order_with_pnl(symbol="BTC-EUR", realized_pnl=Decimal("50")))
        db_persistence.save_trade(
            make_order_with_pnl(symbol="ETH-EUR", realized_pnl=Decimal("-30"))
        )
        analytics = db_persistence.get_analytics(days=30)
        assert analytics["losing_trades"] == 1

    def test_analytics_sums_real_pnl(self, db_persistence):
        """total_pnl must be the sum of all realized_pnl values in the window."""
        pnl1 = Decimal("150")
        pnl2 = Decimal("-50")
        db_persistence.save_trade(make_order_with_pnl(symbol="BTC-EUR", realized_pnl=pnl1))
        db_persistence.save_trade(make_order_with_pnl(symbol="ETH-EUR", realized_pnl=pnl2))
        analytics = db_persistence.get_analytics(days=30)
        assert analytics["total_pnl"] == pytest.approx(float(pnl1 + pnl2), rel=1e-6)

    def test_analytics_total_fees_zero_when_no_trades(self, db_persistence):
        analytics = db_persistence.get_analytics(days=30)
        assert analytics["total_fees"] == 0.0

    def test_analytics_losing_trades_zero_when_no_trades(self, db_persistence):
        analytics = db_persistence.get_analytics(days=30)
        assert analytics["losing_trades"] == 0


class TestSymbolAnalytics:
    def test_empty_returns_empty_list(self, db_persistence):
        assert db_persistence.get_symbol_analytics(days=30) == []

    def test_single_symbol_winning_trade(self, db_persistence):
        db_persistence.save_trade(
            make_order_with_pnl(symbol="BTC-EUR", realized_pnl=Decimal("100"))
        )
        results = db_persistence.get_symbol_analytics(days=30)
        assert len(results) == 1
        assert results[0]["symbol"] == "BTC-EUR"
        assert results[0]["winning"] == 1
        assert results[0]["losing"] == 0
        assert results[0]["win_rate"] == pytest.approx(100.0)
        assert results[0]["total_pnl"] == pytest.approx(100.0)

    def test_multiple_symbols_sorted_by_pnl(self, db_persistence):
        db_persistence.save_trade(make_order_with_pnl(symbol="ETH-EUR", realized_pnl=Decimal("50")))
        db_persistence.save_trade(
            make_order_with_pnl(symbol="BTC-EUR", realized_pnl=Decimal("200"))
        )
        results = db_persistence.get_symbol_analytics(days=30)
        assert results[0]["symbol"] == "BTC-EUR"
        assert results[1]["symbol"] == "ETH-EUR"

    def test_trades_without_pnl_excluded(self, db_persistence):
        db_persistence.save_trade(make_order_with_pnl(symbol="BTC-EUR", realized_pnl=None))
        results = db_persistence.get_symbol_analytics(days=30)
        assert results == []

    def test_win_rate_mixed_results(self, db_persistence):
        win_order = make_order_with_pnl(symbol="BTC-EUR", realized_pnl=Decimal("100"))
        win_order.order_id = "order-win-btc"
        loss_order = make_order_with_pnl(symbol="BTC-EUR", realized_pnl=Decimal("-50"))
        loss_order.order_id = "order-loss-btc"
        db_persistence.save_trade(win_order)
        db_persistence.save_trade(loss_order)
        results = db_persistence.get_symbol_analytics(days=30)
        assert len(results) == 1
        assert results[0]["winning"] == 1
        assert results[0]["losing"] == 1
        assert results[0]["win_rate"] == pytest.approx(50.0)

    def test_returns_empty_on_sqlalchemy_error(self, db_persistence):
        with patch.object(db_persistence, "_session", side_effect=SQLAlchemyError("fail")):
            assert db_persistence.get_symbol_analytics() == []


class TestStrategyLiveAnalytics:
    def test_empty_returns_empty_list(self, db_persistence):
        assert db_persistence.get_strategy_live_analytics(days=30) == []

    def test_single_strategy_aggregated(self, db_persistence):
        db_persistence.save_trade(make_order_with_pnl(symbol="BTC-EUR", realized_pnl=Decimal("80")))
        db_persistence.save_trade(make_order_with_pnl(symbol="ETH-EUR", realized_pnl=Decimal("20")))
        results = db_persistence.get_strategy_live_analytics(days=30)
        assert len(results) == 1
        assert results[0]["strategy"] == "momentum"
        assert results[0]["total_trades"] == 2
        assert results[0]["total_pnl"] == pytest.approx(100.0)

    def test_multiple_strategies_sorted_by_pnl(self, db_persistence):
        order_a = Order(
            order_id="order-strat-a",
            symbol="BTC-EUR",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.1"),
            price=Decimal("51000"),
            status=OrderStatus.FILLED,
            strategy="breakout",
            filled_quantity=Decimal("0.1"),
        )
        order_a.realized_pnl = Decimal("300")
        db_persistence.save_trade(order_a)
        db_persistence.save_trade(make_order_with_pnl(symbol="ETH-EUR", realized_pnl=Decimal("50")))
        results = db_persistence.get_strategy_live_analytics(days=30)
        assert results[0]["strategy"] == "breakout"

    def test_returns_empty_on_sqlalchemy_error(self, db_persistence):
        with patch.object(db_persistence, "_session", side_effect=SQLAlchemyError("fail")):
            assert db_persistence.get_strategy_live_analytics() == []


class TestPortfolioValueSeries:
    def test_empty_returns_empty_list(self, db_persistence):
        assert db_persistence.get_portfolio_value_series(days=30) == []

    def test_returns_float_values(self, db_persistence):
        db_persistence.save_portfolio_snapshot(make_snapshot(10000.0), "m", "c", "p")
        results = db_persistence.get_portfolio_value_series(days=30)
        assert len(results) == 1
        assert isinstance(results[0]["total_value"], float)
        assert results[0]["total_value"] == pytest.approx(10000.0)

    def test_returns_required_keys(self, db_persistence):
        db_persistence.save_portfolio_snapshot(make_snapshot(), "m", "c", "p")
        results = db_persistence.get_portfolio_value_series(days=30)
        keys = results[0].keys()
        assert "timestamp" in keys
        assert "total_value" in keys
        assert "total_pnl" in keys
        assert "cash_balance" in keys

    def test_chronological_order(self, db_persistence):
        for v in [10000.0, 10100.0, 10200.0]:
            db_persistence.save_portfolio_snapshot(make_snapshot(v), "m", "c", "p")
        results = db_persistence.get_portfolio_value_series(days=30)
        values = [r["total_value"] for r in results]
        assert values == sorted(values)

    def test_respects_limit(self, db_persistence):
        for _ in range(10):
            db_persistence.save_portfolio_snapshot(make_snapshot(), "m", "c", "p")
        results = db_persistence.get_portfolio_value_series(days=30, limit=5)
        assert len(results) == 5

    def test_returns_empty_on_sqlalchemy_error(self, db_persistence):
        with patch.object(db_persistence, "_session", side_effect=SQLAlchemyError("fail")):
            assert db_persistence.get_portfolio_value_series() == []
