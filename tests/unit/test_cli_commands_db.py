"""Tests for cli/commands/db.py."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_db():
    """Create a mock DatabasePersistence."""
    db = MagicMock()
    db.load_portfolio_snapshots.return_value = []
    db.load_trade_history.return_value = []
    db.get_analytics.return_value = {}
    db.load_backtest_runs.return_value = []
    db.get_backtest_analytics.return_value = {}
    return db


class TestShowAnalytics:
    """Tests for show_analytics."""

    def test_no_data(self, mock_db, capsys) -> None:
        """Prints message when no analytics available."""
        from cli.commands.db import show_analytics

        with patch("cli.commands.db.DatabasePersistence", return_value=mock_db):
            show_analytics()

        assert "No analytics data available" in capsys.readouterr().out

    def test_with_basic_analytics(self, mock_db, capsys) -> None:
        """Prints analytics summary."""
        from cli.commands.db import show_analytics

        mock_db.get_analytics.return_value = {
            "total_snapshots": 10,
            "total_trades": 5,
            "winning_trades": 3,
            "win_rate": 60.0,
            "total_pnl": 250.50,
        }

        with patch("cli.commands.db.DatabasePersistence", return_value=mock_db):
            show_analytics(days=7)

        out = capsys.readouterr().out
        assert "60.0%" in out
        assert "250.50" in out

    def test_with_capital_fields(self, mock_db, capsys) -> None:
        """Prints initial/final value and return when present."""
        from cli.commands.db import show_analytics

        mock_db.get_analytics.return_value = {
            "total_snapshots": 5,
            "total_trades": 2,
            "winning_trades": 1,
            "win_rate": 50.0,
            "total_pnl": 100.0,
            "initial_value": 1000.0,
            "final_value": 1100.0,
            "return_pct": 10.0,
        }

        with patch("cli.commands.db.DatabasePersistence", return_value=mock_db):
            show_analytics()

        out = capsys.readouterr().out
        assert "1000.00" in out
        assert "1100.00" in out
        assert "10.00%" in out


class TestExportData:
    """Tests for export_data."""

    def test_export_with_no_data(self, mock_db, capsys, tmp_path) -> None:
        """Export completes with 0 files when DB is empty."""
        from cli.commands.db import export_data

        with patch("cli.commands.db.DatabasePersistence", return_value=mock_db):
            export_data(output_dir=str(tmp_path))

        assert "0 files created" in capsys.readouterr().out

    def test_export_with_snapshots_and_trades(self, mock_db, capsys, tmp_path) -> None:
        """Writes JSON files for snapshots and trades."""
        from cli.commands.db import export_data

        mock_db.load_portfolio_snapshots.return_value = [
            {"timestamp": "2026-04-01", "total_value": "1000", "total_pnl": "0"}
        ]
        mock_db.load_trade_history.return_value = [
            {"symbol": "BTC-USD", "side": "buy", "quantity": "0.1", "price": "50000"}
        ]
        mock_db.get_analytics.return_value = {"total_trades": 1}

        with patch("cli.commands.db.DatabasePersistence", return_value=mock_db):
            export_data(output_dir=str(tmp_path))

        out = capsys.readouterr().out
        assert "snapshots" in out
        assert "trades" in out
        assert "3 files created" in out


class TestExportCsv:
    """Tests for export_csv."""

    def test_calls_export_to_csv(self, mock_db, capsys) -> None:
        """Delegates to DatabasePersistence.export_to_csv."""
        from cli.commands.db import export_csv

        with patch("cli.commands.db.DatabasePersistence", return_value=mock_db):
            export_csv()

        mock_db.export_to_csv.assert_called_once()
        assert "CSV export complete" in capsys.readouterr().out


class TestShowStats:
    """Tests for show_stats."""

    def test_empty_db(self, mock_db, capsys) -> None:
        """Shows zero counts when DB is empty."""
        from cli.commands.db import show_stats

        with patch("cli.commands.db.DatabasePersistence", return_value=mock_db):
            show_stats()

        out = capsys.readouterr().out
        assert "0" in out

    def test_with_snapshots_and_trades(self, mock_db, capsys) -> None:
        """Displays latest snapshot and trade details."""
        from cli.commands.db import show_stats

        mock_db.load_portfolio_snapshots.return_value = [
            {"timestamp": "2026-04-01", "total_value": "1000", "total_pnl": "50"}
        ]
        mock_db.load_trade_history.return_value = [
            {"symbol": "BTC-USD", "side": "buy", "quantity": "0.01", "price": "50000"}
        ]

        with patch("cli.commands.db.DatabasePersistence", return_value=mock_db):
            show_stats()

        out = capsys.readouterr().out
        assert "BTC-USD" in out
        assert "1000" in out


class TestShowBacktestResults:
    """Tests for show_backtest_results."""

    def test_no_results(self, mock_db, capsys) -> None:
        """Prints message when no backtest results found."""
        from cli.commands.db import show_backtest_results

        with patch("cli.commands.db.DatabasePersistence", return_value=mock_db):
            show_backtest_results()

        assert "No backtest results found" in capsys.readouterr().out

    def test_with_results(self, mock_db, capsys) -> None:
        """Displays run details and analytics."""
        from cli.commands.db import show_backtest_results

        mock_db.load_backtest_runs.return_value = [
            {
                "id": 1,
                "run_at": "2026-04-01",
                "strategy": "momentum",
                "risk_level": "moderate",
                "symbols": ["BTC-USD"],
                "days": 30,
                "return_pct": 5.5,
                "total_trades": 10,
                "win_rate": 60.0,
                "max_drawdown": 2.5,
                "profit_factor": 1.8,
            }
        ]
        mock_db.get_backtest_analytics.return_value = {
            "total_runs": 1,
            "profitable_runs": 1,
            "success_rate": 100.0,
            "avg_return_pct": 5.5,
            "best_run": {
                "id": 1,
                "strategy": "momentum",
                "return_pct": 5.5,
                "win_rate": 60.0,
            },
        }

        with patch("cli.commands.db.DatabasePersistence", return_value=mock_db):
            show_backtest_results()

        out = capsys.readouterr().out
        assert "momentum" in out
        assert "5.50%" in out
        assert "Best Run" in out

    def test_with_results_no_profit_factor(self, mock_db, capsys) -> None:
        """Handles runs with profit_factor=None."""
        from cli.commands.db import show_backtest_results

        mock_db.load_backtest_runs.return_value = [
            {
                "id": 2,
                "run_at": "2026-04-01",
                "strategy": "breakout",
                "risk_level": "conservative",
                "symbols": ["ETH-USD"],
                "days": 7,
                "return_pct": -1.0,
                "total_trades": 3,
                "win_rate": 33.3,
                "max_drawdown": 5.0,
                "profit_factor": None,
            }
        ]

        with patch("cli.commands.db.DatabasePersistence", return_value=mock_db):
            show_backtest_results()

        assert "breakout" in capsys.readouterr().out


class TestDbMain:
    """Tests for the main() dispatcher."""

    def _run_main(self, argv):
        from cli.commands.db import main

        with patch.object(sys, "argv", argv):
            main()

    def test_no_args_exits_1(self) -> None:
        """No subcommand exits with code 1."""
        with pytest.raises(SystemExit) as exc_info:
            self._run_main(["db"])
        assert exc_info.value.code == 1

    def test_stats_command(self, mock_db, capsys) -> None:
        """stats subcommand calls show_stats."""
        with (
            patch.object(sys, "argv", ["db", "stats"]),
            patch("cli.commands.db.DatabasePersistence", return_value=mock_db),
        ):
            from cli.commands.db import main

            main()

    def test_analytics_command_default_days(self, mock_db, capsys) -> None:
        """analytics subcommand uses default 30 days."""
        with (
            patch.object(sys, "argv", ["db", "analytics"]),
            patch("cli.commands.db.DatabasePersistence", return_value=mock_db),
        ):
            from cli.commands.db import main

            main()
        mock_db.get_analytics.assert_called_with(days=30)

    def test_analytics_command_custom_days(self, mock_db, capsys) -> None:
        """analytics subcommand passes custom days."""
        with (
            patch.object(sys, "argv", ["db", "analytics", "7"]),
            patch("cli.commands.db.DatabasePersistence", return_value=mock_db),
        ):
            from cli.commands.db import main

            main()
        mock_db.get_analytics.assert_called_with(days=7)

    def test_backtests_command(self, mock_db) -> None:
        """backtests subcommand calls show_backtest_results."""
        with (
            patch.object(sys, "argv", ["db", "backtests"]),
            patch("cli.commands.db.DatabasePersistence", return_value=mock_db),
        ):
            from cli.commands.db import main

            main()

    def test_backtests_custom_limit(self, mock_db) -> None:
        """backtests subcommand passes custom limit."""
        with (
            patch.object(sys, "argv", ["db", "backtests", "5"]),
            patch("cli.commands.db.DatabasePersistence", return_value=mock_db),
        ):
            from cli.commands.db import main

            main()
        mock_db.load_backtest_runs.assert_called_with(limit=5)

    def test_export_command(self, mock_db, tmp_path) -> None:
        """export subcommand writes to specified dir."""
        out_dir = str(tmp_path / "exports")
        with (
            patch.object(sys, "argv", ["db", "export", out_dir]),
            patch("cli.commands.db.DatabasePersistence", return_value=mock_db),
        ):
            from cli.commands.db import main

            main()

    def test_export_csv_command(self, mock_db) -> None:
        """export-csv subcommand calls export_to_csv."""
        with (
            patch.object(sys, "argv", ["db", "export-csv"]),
            patch("cli.commands.db.DatabasePersistence", return_value=mock_db),
        ):
            from cli.commands.db import main

            main()
        mock_db.export_to_csv.assert_called_once()

    def test_unknown_command_exits_1(self) -> None:
        """Unknown subcommand exits with code 1."""
        with pytest.raises(SystemExit) as exc_info:
            self._run_main(["db", "unknown"])
        assert exc_info.value.code == 1

    def test_exception_in_command_exits_1(self, mock_db) -> None:
        """Exception from a command exits with code 1."""
        from cli.commands.db import main

        mock_db.load_portfolio_snapshots.side_effect = RuntimeError("db error")
        with (
            patch.object(sys, "argv", ["db", "stats"]),
            patch("cli.commands.db.DatabasePersistence", return_value=mock_db),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 1
