"""Unit tests for analytics_report pure computational functions.

These tests cover the financial math utilities and the rule-based suggestions
engine in ``cli/analytics_report.py``.  No database, no matplotlib, no I/O.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cli.utils.analytics_report import (
    compute_daily_returns,
    compute_max_drawdown,
    compute_profit_factor,
    compute_sharpe_ratio,
    compute_sortino_ratio,
    generate_suggestions,
)

# ---------------------------------------------------------------------------
# compute_daily_returns
# ---------------------------------------------------------------------------


class TestComputeDailyReturns:
    def test_empty_returns_empty(self):
        assert compute_daily_returns([]) == []

    def test_single_value_returns_empty(self):
        assert compute_daily_returns([10000.0]) == []

    def test_flat_series_returns_all_zeros(self):
        result = compute_daily_returns([100.0, 100.0, 100.0])
        assert all(r == pytest.approx(0.0) for r in result)
        assert len(result) == 2

    def test_positive_growth(self):
        result = compute_daily_returns([100.0, 110.0])
        assert result == [pytest.approx(0.10)]

    def test_negative_growth(self):
        result = compute_daily_returns([100.0, 90.0])
        assert result == [pytest.approx(-0.10)]

    def test_length_is_n_minus_1(self):
        values = [100.0, 101.0, 102.0, 103.0]
        assert len(compute_daily_returns(values)) == 3


# ---------------------------------------------------------------------------
# compute_sharpe_ratio
# ---------------------------------------------------------------------------


class TestComputeSharpeRatio:
    def test_empty_returns_zero(self):
        assert compute_sharpe_ratio([]) == 0.0

    def test_zero_std_returns_zero(self):
        # All identical returns → std = 0 → no meaningful Sharpe
        assert compute_sharpe_ratio([0.01, 0.01, 0.01]) == 0.0

    def test_positive_sharpe(self):
        # Consistent positive returns → positive Sharpe
        returns = [0.01] * 50 + [0.005] * 50  # noisy but positive
        sharpe = compute_sharpe_ratio(returns)
        assert sharpe > 0.0

    def test_negative_sharpe(self):
        # Consistent negative returns → negative Sharpe
        returns = [-0.01] * 100
        # std = 0 here so returns 0 — use mixed negatives
        returns = [-0.02, -0.01, -0.03, -0.01, -0.02] * 10
        sharpe = compute_sharpe_ratio(returns)
        assert sharpe < 0.0

    def test_annualised_scaling(self):
        # Daily mean≈0.01, daily std≈small → Sharpe should be very large
        import random

        random.seed(42)
        noisy = [0.01 + random.uniform(-0.0001, 0.0001) for _ in range(252)]
        sharpe = compute_sharpe_ratio(noisy)
        # Rough sanity: mean ≈ 0.01, std ≈ small → sharpe should be very large
        assert sharpe > 10.0


# ---------------------------------------------------------------------------
# compute_sortino_ratio
# ---------------------------------------------------------------------------


class TestComputeSortinoRatio:
    def test_empty_returns_zero(self):
        assert compute_sortino_ratio([]) == 0.0

    def test_no_negative_returns_returns_zero(self):
        # No downside deviation → Sortino undefined → returns 0
        assert compute_sortino_ratio([0.01, 0.02, 0.03]) == 0.0

    def test_positive_sortino_with_some_negatives(self):
        returns = [0.02, 0.01, -0.005, 0.03, -0.002]
        sortino = compute_sortino_ratio(returns)
        assert sortino > 0.0

    def test_all_negative_is_negative(self):
        returns = [-0.01, -0.02, -0.015, -0.005]
        sortino = compute_sortino_ratio(returns)
        assert sortino < 0.0


# ---------------------------------------------------------------------------
# compute_max_drawdown
# ---------------------------------------------------------------------------


class TestComputeMaxDrawdown:
    def test_empty_returns_zero(self):
        assert compute_max_drawdown([]) == 0.0

    def test_single_value_returns_zero(self):
        assert compute_max_drawdown([10000.0]) == 0.0

    def test_monotone_growth_returns_zero(self):
        assert compute_max_drawdown([100.0, 110.0, 120.0]) == pytest.approx(0.0)

    def test_50_percent_drawdown(self):
        result = compute_max_drawdown([100.0, 50.0])
        assert result == pytest.approx(50.0)

    def test_drawdown_after_peak(self):
        # Peak at 200, drops to 100 → 50% drawdown
        values = [100.0, 150.0, 200.0, 150.0, 100.0]
        result = compute_max_drawdown(values)
        assert result == pytest.approx(50.0)

    def test_partial_recovery_uses_worst_trough(self):
        # Peak 200 → drops to 80 (60% dd) → recovers to 150 → drops to 100 (33% dd from new peak)
        values = [100.0, 200.0, 80.0, 150.0, 100.0]
        result = compute_max_drawdown(values)
        assert result == pytest.approx(60.0)


# ---------------------------------------------------------------------------
# compute_profit_factor
# ---------------------------------------------------------------------------


class TestComputeProfitFactor:
    def test_empty_returns_zero(self):
        assert compute_profit_factor([]) == 0.0

    def test_no_losses_returns_zero(self):
        # If denominator is 0 (no losing trades) return 0 to signal undefined
        assert compute_profit_factor([100.0, 50.0, 200.0]) == 0.0

    def test_no_wins_returns_zero(self):
        assert compute_profit_factor([-50.0, -30.0]) == 0.0

    def test_basic_ratio(self):
        # Total wins = 300, total losses = 100 → profit factor = 3.0
        result = compute_profit_factor([100.0, 200.0, -100.0])
        assert result == pytest.approx(3.0)

    def test_balanced(self):
        result = compute_profit_factor([100.0, -100.0])
        assert result == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# generate_suggestions
# ---------------------------------------------------------------------------


class TestGenerateSuggestions:
    def _base_metrics(self, **overrides) -> dict:
        base = {
            "total_trades": 20,
            "win_rate": 55.0,
            "total_pnl": 500.0,
            "total_fees": 50.0,
            "max_drawdown_pct": 8.0,
            "sharpe_ratio": 1.2,
            "profit_factor": 1.8,
        }
        base.update(overrides)
        return base

    def test_returns_list(self):
        result = generate_suggestions(self._base_metrics(), [], {})
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_low_win_rate_triggers_suggestion(self):
        metrics = self._base_metrics(win_rate=35.0)
        suggestions = generate_suggestions(metrics, [], {})
        assert any("win rate" in s.lower() for s in suggestions)

    def test_healthy_win_rate_no_win_rate_suggestion(self):
        metrics = self._base_metrics(win_rate=55.0)
        suggestions = generate_suggestions(metrics, [], {})
        assert not any("win rate" in s.lower() for s in suggestions)

    def test_high_fee_drag_triggers_suggestion(self):
        # fees = 200, pnl = 500 → 40% fee drag
        metrics = self._base_metrics(total_fees=200.0, total_pnl=500.0)
        suggestions = generate_suggestions(metrics, [], {})
        assert any("fee" in s.lower() or "limit order" in s.lower() for s in suggestions)

    def test_high_drawdown_triggers_suggestion(self):
        metrics = self._base_metrics(max_drawdown_pct=25.0)
        suggestions = generate_suggestions(metrics, [], {})
        assert any("drawdown" in s.lower() or "risk" in s.lower() for s in suggestions)

    def test_negative_sharpe_triggers_suggestion(self):
        metrics = self._base_metrics(sharpe_ratio=-0.5)
        suggestions = generate_suggestions(metrics, [], {})
        assert any("sharpe" in s.lower() for s in suggestions)

    def test_low_profit_factor_triggers_suggestion(self):
        metrics = self._base_metrics(profit_factor=0.8)
        suggestions = generate_suggestions(metrics, [], {})
        assert any("profit factor" in s.lower() or "loss" in s.lower() for s in suggestions)

    def test_losing_symbol_triggers_suggestion(self):
        symbol_analytics = [
            {"symbol": "XRP-EUR", "total_trades": 10, "total_pnl": -200.0, "win_rate": 20.0}
        ]
        suggestions = generate_suggestions(self._base_metrics(), symbol_analytics, {})
        assert any("XRP-EUR" in s for s in suggestions)

    def test_winning_symbol_no_removal_suggestion(self):
        symbol_analytics = [
            {"symbol": "BTC-EUR", "total_trades": 10, "total_pnl": 500.0, "win_rate": 70.0}
        ]
        suggestions = generate_suggestions(self._base_metrics(), symbol_analytics, {})
        assert not any("removing" in s.lower() for s in suggestions)

    def test_best_backtest_mentioned(self):
        backtest_analytics = {
            "best_run": {"strategy": "breakout", "return_pct": 15.0, "win_rate": 62.0}
        }
        suggestions = generate_suggestions(self._base_metrics(), [], backtest_analytics)
        assert any("breakout" in s.lower() for s in suggestions)

    def test_too_few_trades_skips_win_rate_suggestion(self):
        # With < 10 trades, don't make strong win-rate recommendations
        metrics = self._base_metrics(total_trades=3, win_rate=20.0)
        suggestions = generate_suggestions(metrics, [], {})
        assert not any("win rate" in s.lower() for s in suggestions)

    def test_no_data_returns_no_data_message(self):
        metrics = {"total_trades": 0}
        suggestions = generate_suggestions(metrics, [], {})
        assert len(suggestions) >= 1
        assert any("no" in s.lower() or "data" in s.lower() for s in suggestions)


# ---------------------------------------------------------------------------
# Telegram integration tests
# ---------------------------------------------------------------------------


class TestTelegramIntegration:
    """Test telegram notification integration in generate_report."""

    def _setup_mock_db(self, mock_db_cls):
        """Configure mock database with minimal valid return values."""
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.get_analytics.return_value = {
            "total_trades": 100,
            "win_rate": 60.0,
            "total_pnl": 500.0,
            "total_fees": 10.0,
            "return_pct": 5.0,
        }
        mock_db.get_symbol_analytics.return_value = []
        mock_db.get_strategy_live_analytics.return_value = []
        mock_db.get_portfolio_value_series.return_value = [
            {"total_value": 10000.0, "timestamp": "2026-01-01 00:00:00"},
            {"total_value": 10500.0, "timestamp": "2026-01-02 00:00:00"},
        ]
        mock_db.get_backtest_analytics.return_value = {}
        mock_db.load_backtest_runs.return_value = []
        mock_db.load_trade_history.return_value = [{"pnl": 50.0}, {"pnl": -20.0}]
        return mock_db

    @patch("cli.utils.analytics_report._generate_pdf", return_value=None)
    @patch("cli.utils.analytics_report.DatabasePersistence")
    @patch("cli.utils.analytics_report.TelegramNotifier")
    @patch("cli.utils.analytics_report.settings")
    def test_sends_text_fallback_when_no_pdf(
        self, mock_settings, mock_notifier_cls, mock_db_cls, mock_gen_pdf, tmp_path
    ):
        """When _generate_pdf returns None, falls back to notify_report_ready text message."""
        mock_settings.telegram_bot_token = "test_token"
        mock_settings.telegram_chat_id = "test_chat_id"
        self._setup_mock_db(mock_db_cls)

        mock_notifier = MagicMock()
        mock_notifier.notify_report_ready = AsyncMock()
        mock_notifier_cls.return_value = mock_notifier

        from cli.utils.analytics_report import generate_report

        generate_report(days=30, output_dir=tmp_path)

        mock_notifier_cls.assert_called_once_with(token="test_token", chat_id="test_chat_id")
        mock_notifier.notify_report_ready.assert_awaited_once()
        call_kwargs = mock_notifier.notify_report_ready.call_args.kwargs
        assert call_kwargs["days"] == 30
        assert call_kwargs["total_trades"] == 100
        assert isinstance(call_kwargs["total_pnl"], Decimal)
        assert call_kwargs["win_rate"] == 60.0

    @patch("cli.utils.analytics_report._generate_pdf", return_value=b"%PDF-1.4 test")
    @patch("cli.utils.analytics_report.DatabasePersistence")
    @patch("cli.utils.analytics_report.TelegramNotifier")
    @patch("cli.utils.analytics_report.settings")
    def test_sends_pdf_when_pdf_bytes_available(
        self, mock_settings, mock_notifier_cls, mock_db_cls, mock_gen_pdf, tmp_path
    ):
        """When _generate_pdf returns bytes, send_document is called with the PDF."""
        mock_settings.telegram_bot_token = "test_token"
        mock_settings.telegram_chat_id = "test_chat_id"
        self._setup_mock_db(mock_db_cls)

        mock_notifier = MagicMock()
        mock_notifier.send_document = AsyncMock()
        mock_notifier.notify_report_ready = AsyncMock()
        mock_notifier_cls.return_value = mock_notifier

        from cli.utils.analytics_report import generate_report

        generate_report(days=30, output_dir=tmp_path)

        mock_notifier.send_document.assert_awaited_once()
        call_args = mock_notifier.send_document.call_args
        assert call_args.args[0] == b"%PDF-1.4 test"
        assert call_args.args[1] == "analytics_report.pdf"
        assert "<b>" in call_args.kwargs.get("caption", "")
        # notify_report_ready must NOT be called when PDF is sent
        mock_notifier.notify_report_ready.assert_not_awaited()

    @patch("cli.utils.analytics_report.DatabasePersistence")
    @patch("cli.utils.analytics_report.TelegramNotifier")
    @patch("cli.utils.analytics_report.settings")
    def test_sends_telegram_notification_when_configured(
        self, mock_settings, mock_notifier_cls, mock_db_cls, tmp_path
    ):
        """When telegram is configured, generate_report sends a notification (either PDF or text)."""
        mock_settings.telegram_bot_token = "test_token"
        mock_settings.telegram_chat_id = "test_chat_id"
        self._setup_mock_db(mock_db_cls)

        mock_notifier = MagicMock()
        mock_notifier.send_document = AsyncMock()
        mock_notifier.notify_report_ready = AsyncMock()
        mock_notifier_cls.return_value = mock_notifier

        from cli.utils.analytics_report import generate_report

        generate_report(days=30, output_dir=tmp_path)

        mock_notifier_cls.assert_called_once_with(token="test_token", chat_id="test_chat_id")
        # One of the two methods must have been called
        total_calls = (
            mock_notifier.send_document.await_count + mock_notifier.notify_report_ready.await_count
        )
        assert total_calls == 1

    @patch("cli.utils.analytics_report.DatabasePersistence")
    @patch("cli.utils.analytics_report.TelegramNotifier")
    @patch("cli.utils.analytics_report.settings")
    def test_skips_telegram_when_not_configured(
        self, mock_settings, mock_notifier_cls, mock_db_cls, tmp_path
    ):
        """When telegram is not configured, no notification is sent."""
        # Setup settings without telegram config
        mock_settings.telegram_bot_token = None
        mock_settings.telegram_chat_id = None

        # Setup mock database
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.get_analytics.return_value = {
            "total_trades": 10,
            "win_rate": 50.0,
            "total_pnl": 100.0,
            "total_fees": 5.0,
            "return_pct": 1.0,
        }
        mock_db.get_symbol_analytics.return_value = []
        mock_db.get_strategy_live_analytics.return_value = []
        mock_db.get_portfolio_value_series.return_value = [
            {"total_value": 10000.0, "timestamp": "2026-01-01 00:00:00"}
        ]
        mock_db.get_backtest_analytics.return_value = {}
        mock_db.load_backtest_runs.return_value = []
        mock_db.load_trade_history.return_value = []

        # Import after patching
        from cli.utils.analytics_report import generate_report

        # Run report
        generate_report(days=30, output_dir=tmp_path)

        # Verify notifier was never created
        mock_notifier_cls.assert_not_called()

    @patch("cli.utils.analytics_report.DatabasePersistence")
    @patch("cli.utils.analytics_report.TelegramNotifier")
    @patch("cli.utils.analytics_report.settings")
    def test_telegram_failure_does_not_crash_report(
        self, mock_settings, mock_notifier_cls, mock_db_cls, tmp_path
    ):
        """When telegram notification fails, report generation continues."""
        # Setup settings with telegram config
        mock_settings.telegram_bot_token = "test_token"
        mock_settings.telegram_chat_id = "test_chat_id"

        # Setup mock database
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.get_analytics.return_value = {
            "total_trades": 10,
            "win_rate": 50.0,
            "total_pnl": 100.0,
            "total_fees": 5.0,
            "return_pct": 1.0,
        }
        mock_db.get_symbol_analytics.return_value = []
        mock_db.get_strategy_live_analytics.return_value = []
        mock_db.get_portfolio_value_series.return_value = [
            {"total_value": 10000.0, "timestamp": "2026-01-01 00:00:00"}
        ]
        mock_db.get_backtest_analytics.return_value = {}
        mock_db.load_backtest_runs.return_value = []
        mock_db.load_trade_history.return_value = []

        # Setup mock notifier that raises an error
        mock_notifier = MagicMock()
        mock_notifier.notify_report_ready = AsyncMock(side_effect=Exception("Network error"))
        mock_notifier_cls.return_value = mock_notifier

        # Import after patching
        from cli.utils.analytics_report import generate_report

        # Run report - should not raise
        result = generate_report(days=30, output_dir=tmp_path)

        # Verify report was still generated
        assert result["report_path"]
        assert Path(result["report_path"]).exists()

    @patch("cli.utils.analytics_report._generate_pdf", side_effect=RuntimeError("fpdf2 crash"))
    @patch("cli.utils.analytics_report.DatabasePersistence")
    @patch("cli.utils.analytics_report.TelegramNotifier")
    @patch("cli.utils.analytics_report.settings")
    def test_falls_back_to_text_when_pdf_generation_fails(
        self, mock_settings, mock_notifier_cls, mock_db_cls, mock_gen_pdf, tmp_path
    ):
        """When _generate_pdf raises, falls back to notify_report_ready text message."""
        mock_settings.telegram_bot_token = "test_token"
        mock_settings.telegram_chat_id = "test_chat_id"
        self._setup_mock_db(mock_db_cls)

        mock_notifier = MagicMock()
        mock_notifier.send_document = AsyncMock()
        mock_notifier.notify_report_ready = AsyncMock()
        mock_notifier_cls.return_value = mock_notifier

        from cli.utils.analytics_report import generate_report

        # Must not raise — report generation must succeed even when PDF fails
        result = generate_report(days=30, output_dir=tmp_path)
        assert result["report_path"]

        # PDF was NOT sent (generation failed)
        mock_notifier.send_document.assert_not_awaited()
        # Text fallback WAS sent instead
        mock_notifier.notify_report_ready.assert_awaited_once()

    @patch("cli.utils.analytics_report.DatabasePersistence")
    @patch("cli.utils.analytics_report.TelegramNotifier")
    @patch("cli.utils.analytics_report.settings")
    def test_telegram_disabled_via_parameter(
        self, mock_settings, mock_notifier_cls, mock_db_cls, tmp_path
    ):
        """When send_telegram=False, no notification is sent even if configured."""
        # Setup settings with telegram config
        mock_settings.telegram_bot_token = "test_token"
        mock_settings.telegram_chat_id = "test_chat_id"

        # Setup mock database
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.get_analytics.return_value = {
            "total_trades": 10,
            "win_rate": 50.0,
            "total_pnl": 100.0,
            "total_fees": 5.0,
            "return_pct": 1.0,
        }
        mock_db.get_symbol_analytics.return_value = []
        mock_db.get_strategy_live_analytics.return_value = []
        mock_db.get_portfolio_value_series.return_value = [
            {"total_value": 10000.0, "timestamp": "2026-01-01 00:00:00"}
        ]
        mock_db.get_backtest_analytics.return_value = {}
        mock_db.load_backtest_runs.return_value = []
        mock_db.load_trade_history.return_value = []

        # Import after patching
        from cli.utils.analytics_report import generate_report

        # Run report with send_telegram=False
        generate_report(days=30, output_dir=tmp_path, send_telegram=False)

        # Verify notifier was never created
        mock_notifier_cls.assert_not_called()


# ---------------------------------------------------------------------------
# Phase 1 PDF Functions
# ---------------------------------------------------------------------------


class TestComputeWinLossStreaks:
    """Test win/loss streak calculation."""

    def test_empty_list(self):
        from cli.utils.analytics_report import compute_win_loss_streaks

        result = compute_win_loss_streaks([])
        assert result["longest_win_streak"] == 0
        assert result["longest_loss_streak"] == 0

    def test_all_wins(self):
        from cli.utils.analytics_report import compute_win_loss_streaks

        result = compute_win_loss_streaks([10.0, 5.0, 20.0, 1.0])
        assert result["longest_win_streak"] == 4
        assert result["longest_loss_streak"] == 0

    def test_all_losses(self):
        from cli.utils.analytics_report import compute_win_loss_streaks

        result = compute_win_loss_streaks([-10.0, -5.0, -1.0])
        assert result["longest_win_streak"] == 0
        assert result["longest_loss_streak"] == 3

    def test_mixed_streaks(self):
        from cli.utils.analytics_report import compute_win_loss_streaks

        # Pattern: +++ -- ++++ -
        pnl = [10.0, 5.0, 3.0, -2.0, -1.0, 8.0, 12.0, 15.0, 4.0, -3.0]
        result = compute_win_loss_streaks(pnl)
        assert result["longest_win_streak"] == 4  # positions 5-8
        assert result["longest_loss_streak"] == 2  # positions 3-4

    def test_alternating(self):
        from cli.utils.analytics_report import compute_win_loss_streaks

        pnl = [10.0, -5.0, 8.0, -3.0, 12.0]
        result = compute_win_loss_streaks(pnl)
        assert result["longest_win_streak"] == 1
        assert result["longest_loss_streak"] == 1


class TestComputeRollingVolatility:
    """Test rolling volatility calculation."""

    def test_empty_list(self):
        from cli.utils.analytics_report import compute_rolling_volatility

        result = compute_rolling_volatility([])
        assert result == []

    def test_insufficient_data(self):
        from cli.utils.analytics_report import compute_rolling_volatility

        # Window=20 but only 10 values
        values = [100.0 + i for i in range(10)]
        result = compute_rolling_volatility(values, window=20)
        assert result == []

    def test_flat_values_zero_volatility(self):
        from cli.utils.analytics_report import compute_rolling_volatility

        values = [100.0] * 25
        result = compute_rolling_volatility(values, window=20)
        assert len(result) == 4  # 25-20-1 = 4 (window+1 needed)
        assert all(v == 0.0 for v in result)

    def test_returns_correct_length(self):
        from cli.utils.analytics_report import compute_rolling_volatility

        values = [100.0 + i * 0.1 for i in range(50)]
        result = compute_rolling_volatility(values, window=20)
        assert len(result) == 29  # 50 - 20 - 1

    def test_volatile_period_has_higher_values(self):
        from cli.utils.analytics_report import compute_rolling_volatility

        # Stable then volatile
        stable = [100.0 + i * 0.01 for i in range(25)]  # gentle upward trend
        volatile = [stable[-1] + i * (-1) ** i * 10 for i in range(25)]  # zigzag
        values = stable + volatile
        result = compute_rolling_volatility(values, window=20)
        # Later values should be higher
        if len(result) >= 2:
            assert result[-1] > result[0]


class TestGenerateInsights:
    """Test rule-based insights generation."""

    def test_excellent_performance(self):
        from cli.utils.analytics_report import _generate_insights

        insights = _generate_insights(
            total_pnl=5000.0,
            win_rate=65.0,
            sharpe=2.5,
            max_dd=5.0,
            profit_factor=3.0,
        )
        text = " ".join(insights).lower()
        # Should have positive insights
        assert any(
            word in text for word in ["strong", "excellent", "good", "positive", "profitable"]
        )

    def test_poor_performance_warnings(self):
        from cli.utils.analytics_report import _generate_insights

        insights = _generate_insights(
            total_pnl=-500.0,
            win_rate=35.0,
            sharpe=-0.5,
            max_dd=25.0,
            profit_factor=0.6,
        )
        text = " ".join(insights).lower()
        # Should have warnings
        assert any(
            word in text
            for word in ["low", "high", "poor", "negative", "warning", "weak", "loss", "review"]
        )

    def test_high_fee_drag_indirect(self):
        from cli.utils.analytics_report import _generate_insights

        # Test with mediocre performance (fees would eat into profits)
        insights = _generate_insights(
            total_pnl=400.0,  # After 600 in fees from 1000
            win_rate=50.0,
            sharpe=1.0,
            max_dd=10.0,
            profit_factor=1.5,
        )
        # Should have some insights
        assert len(insights) > 0


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


class TestFmtEur:
    def test_positive(self):
        from cli.utils.analytics_report import _fmt_eur

        assert _fmt_eur(123.456) == "+€123.46"

    def test_negative(self):
        from cli.utils.analytics_report import _fmt_eur

        assert _fmt_eur(-50.0) == "€-50.00"

    def test_zero(self):
        from cli.utils.analytics_report import _fmt_eur

        assert _fmt_eur(0.0) == "+€0.00"


class TestFmtPct:
    def test_positive(self):
        from cli.utils.analytics_report import _fmt_pct

        assert _fmt_pct(5.123) == "+5.12%"

    def test_negative(self):
        from cli.utils.analytics_report import _fmt_pct

        assert _fmt_pct(-3.5) == "-3.50%"

    def test_custom_decimals(self):
        from cli.utils.analytics_report import _fmt_pct

        assert _fmt_pct(1.2345, decimals=1) == "+1.2%"


class TestFormatMetricValue:
    def test_nonzero_formatted(self):
        from cli.utils.analytics_report import _format_metric_value

        assert _format_metric_value(1.5, ".2f") == "1.50"

    def test_zero_returns_fallback(self):
        from cli.utils.analytics_report import _format_metric_value

        assert _format_metric_value(0.0, ".2f") == "N/A"

    def test_custom_fallback(self):
        from cli.utils.analytics_report import _format_metric_value

        assert _format_metric_value(0.0, ".2f", fallback="—") == "—"


# ---------------------------------------------------------------------------
# Drawdown series
# ---------------------------------------------------------------------------


class TestDrawdownSeries:
    def test_empty(self):
        from cli.utils.analytics_report import _drawdown_series

        assert _drawdown_series([]) == []

    def test_monotone_growth(self):
        from cli.utils.analytics_report import _drawdown_series

        result = _drawdown_series([100.0, 110.0, 120.0])
        assert all(v == pytest.approx(0.0) for v in result)

    def test_drawdown_recovery(self):
        from cli.utils.analytics_report import _drawdown_series

        result = _drawdown_series([100.0, 80.0, 100.0])
        assert result[0] == pytest.approx(0.0)
        assert result[1] == pytest.approx(20.0)
        assert result[2] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Performance grid helpers
# ---------------------------------------------------------------------------


class TestBuildPerformanceGrid:
    def test_empty_trades(self):
        from cli.utils.analytics_report import _build_performance_grid

        perf, count = _build_performance_grid([])
        assert len(perf) == 7
        assert all(len(row) == 24 for row in perf)
        assert all(c == 0 for row in count for c in row)

    def test_single_trade(self):
        from cli.utils.analytics_report import _build_performance_grid

        trade = {"pnl": 100.0, "timestamp": "2026-01-05T14:30:00"}  # Monday
        perf, count = _build_performance_grid([trade])
        assert count[0][14] == 1
        assert perf[0][14] == pytest.approx(100.0)

    def test_skips_missing_pnl(self):
        from cli.utils.analytics_report import _build_performance_grid

        trade = {"pnl": None, "timestamp": "2026-01-05T14:30:00"}
        _perf, count = _build_performance_grid([trade])
        assert all(c == 0 for row in count for c in row)

    def test_skips_missing_timestamp(self):
        from cli.utils.analytics_report import _build_performance_grid

        trade = {"pnl": 50.0, "timestamp": None}
        _perf, count = _build_performance_grid([trade])
        assert all(c == 0 for row in count for c in row)


class TestAverageGridCells:
    def test_averages_correctly(self):
        from cli.utils.analytics_report import _average_grid_cells

        perf = [[0.0] * 24 for _ in range(7)]
        count = [[0] * 24 for _ in range(7)]
        perf[0][0] = 300.0
        count[0][0] = 3
        _average_grid_cells(perf, count)
        assert perf[0][0] == pytest.approx(100.0)

    def test_zero_trades_unchanged(self):
        from cli.utils.analytics_report import _average_grid_cells

        perf = [[0.0] * 24 for _ in range(7)]
        count = [[0] * 24 for _ in range(7)]
        _average_grid_cells(perf, count)
        assert all(v == 0.0 for row in perf for v in row)


# ---------------------------------------------------------------------------
# Fetch & compute helpers
# ---------------------------------------------------------------------------


class TestFetchReportData:
    def test_calls_all_db_methods(self):
        from cli.utils.analytics_report import _fetch_report_data

        mock_db = MagicMock()
        mock_db.get_analytics.return_value = {}
        mock_db.get_symbol_analytics.return_value = []
        mock_db.get_strategy_live_analytics.return_value = []
        mock_db.get_portfolio_value_series.return_value = []
        mock_db.get_backtest_analytics.return_value = {}
        mock_db.load_backtest_runs.return_value = []
        mock_db.load_trade_history.return_value = []

        result = _fetch_report_data(mock_db, 30)
        assert len(result) == 7
        mock_db.get_analytics.assert_called_once_with(days=30)
        mock_db.get_symbol_analytics.assert_called_once_with(days=30)
        mock_db.get_strategy_live_analytics.assert_called_once_with(days=30)
        mock_db.get_portfolio_value_series.assert_called_once_with(days=30)
        mock_db.get_backtest_analytics.assert_called_once()
        mock_db.load_backtest_runs.assert_called_once_with(limit=50)
        mock_db.load_trade_history.assert_called_once_with(limit=10_000)


class TestComputeReportMetrics:
    def test_computes_derived_metrics(self):
        from cli.utils.analytics_report import _compute_report_metrics

        analytics = {"total_trades": 10, "win_rate": 60.0, "total_pnl": 500.0}
        portfolio_series = [
            {"total_value": 10000.0},
            {"total_value": 10200.0},
            {"total_value": 10100.0},
            {"total_value": 10500.0},
        ]
        trade_history = [{"pnl": 50.0}, {"pnl": -20.0}, {"pnl": 30.0}]

        metrics = _compute_report_metrics(analytics, portfolio_series, trade_history)
        assert metrics["total_trades"] == 10
        assert "sharpe_ratio" in metrics
        assert "sortino_ratio" in metrics
        assert "max_drawdown_pct" in metrics
        assert "profit_factor" in metrics


# ---------------------------------------------------------------------------
# Markdown builders
# ---------------------------------------------------------------------------


class TestMdSymbolSection:
    def test_empty_returns_empty(self):
        from cli.utils.analytics_report import _md_symbol_section

        assert _md_symbol_section([]) == []

    def test_single_symbol(self):
        from cli.utils.analytics_report import _md_symbol_section

        data = [
            {
                "symbol": "BTC-EUR",
                "total_trades": 10,
                "win_rate": 60.0,
                "total_pnl": 500.0,
                "total_fees": 10.0,
            }
        ]
        lines = _md_symbol_section(data)
        assert any("BTC-EUR" in line for line in lines)
        assert any("Per-Symbol" in line for line in lines)


class TestMdStrategySection:
    def test_empty_returns_empty(self):
        from cli.utils.analytics_report import _md_strategy_section

        assert _md_strategy_section([]) == []

    def test_single_strategy(self):
        from cli.utils.analytics_report import _md_strategy_section

        data = [{"strategy": "momentum", "total_trades": 5, "win_rate": 55.0, "total_pnl": 200.0}]
        lines = _md_strategy_section(data)
        assert any("momentum" in line for line in lines)


class TestMdBacktestSection:
    def test_empty_returns_empty(self):
        from cli.utils.analytics_report import _md_backtest_section

        assert _md_backtest_section({}) == []

    def test_no_runs_returns_empty(self):
        from cli.utils.analytics_report import _md_backtest_section

        assert _md_backtest_section({"total_runs": 0}) == []

    def test_with_runs(self):
        from cli.utils.analytics_report import _md_backtest_section

        data = {
            "total_runs": 5,
            "profitable_runs": 3,
            "success_rate": 60.0,
            "avg_return_pct": 2.5,
            "best_run": {"strategy": "breakout", "return_pct": 15.0, "win_rate": 62.0},
        }
        lines = _md_backtest_section(data)
        assert any("Backtest" in line for line in lines)
        assert any("breakout" in line for line in lines)


class TestMdChartsSection:
    def test_empty_returns_empty(self):
        from cli.utils.analytics_report import _md_charts_section

        assert _md_charts_section([]) == []

    def test_with_chart_paths(self):
        from cli.utils.analytics_report import _md_charts_section

        paths = [Path("data/reports/equity.png"), Path("data/reports/drawdown.png")]
        lines = _md_charts_section(paths)
        assert any("equity" in line for line in lines)
        assert any("Charts" in line for line in lines)


class TestBuildMarkdown:
    def test_full_report(self):
        from cli.utils.analytics_report import _build_markdown

        metrics = {
            "total_trades": 50,
            "win_rate": 55.0,
            "total_pnl": 1000.0,
            "total_fees": 50.0,
            "sharpe_ratio": 1.2,
            "sortino_ratio": 1.5,
            "max_drawdown_pct": 8.0,
            "profit_factor": 2.0,
            "return_pct": 5.0,
            "initial_value": 10000.0,
            "final_value": 10500.0,
        }
        md = _build_markdown(metrics, [], [], {}, ["suggestion1"], [], 30)
        assert "Trading Analytics Report" in md
        assert "30 Days" in md
        assert "suggestion1" in md


# ---------------------------------------------------------------------------
# Terminal print functions
# ---------------------------------------------------------------------------


class TestPrintSymbolTable:
    def test_empty_prints_nothing(self, capsys):
        from cli.utils.analytics_report import _print_symbol_table

        _print_symbol_table([])
        assert capsys.readouterr().out == ""

    def test_prints_table(self, capsys):
        from cli.utils.analytics_report import _print_symbol_table

        data = [
            {
                "symbol": "BTC-EUR",
                "total_trades": 10,
                "win_rate": 60.0,
                "total_pnl": 500.0,
                "total_fees": 10.0,
            }
        ]
        _print_symbol_table(data)
        out = capsys.readouterr().out
        assert "BTC-EUR" in out
        assert "Per-Symbol" in out


class TestPrintStrategyTable:
    def test_empty_prints_nothing(self, capsys):
        from cli.utils.analytics_report import _print_strategy_table

        _print_strategy_table([])
        assert capsys.readouterr().out == ""

    def test_prints_table(self, capsys):
        from cli.utils.analytics_report import _print_strategy_table

        data = [{"strategy": "momentum", "total_trades": 5, "win_rate": 55.0, "total_pnl": 200.0}]
        _print_strategy_table(data)
        out = capsys.readouterr().out
        assert "momentum" in out


class TestPrintBacktestSection:
    def test_empty_prints_nothing(self, capsys):
        from cli.utils.analytics_report import _print_backtest_section

        _print_backtest_section({})
        assert capsys.readouterr().out == ""

    def test_no_runs_prints_nothing(self, capsys):
        from cli.utils.analytics_report import _print_backtest_section

        _print_backtest_section({"total_runs": 0})
        assert capsys.readouterr().out == ""

    def test_prints_section(self, capsys):
        from cli.utils.analytics_report import _print_backtest_section

        data = {
            "total_runs": 5,
            "profitable_runs": 3,
            "success_rate": 60.0,
            "avg_return_pct": 2.5,
            "best_run": {"strategy": "breakout", "return_pct": 15.0},
        }
        _print_backtest_section(data)
        out = capsys.readouterr().out
        assert "Backtest" in out
        assert "breakout" in out


class TestPrintSuggestions:
    def test_prints_suggestions(self, capsys):
        from cli.utils.analytics_report import _print_suggestions

        suggestions = ["Lower risk level", "Use limit orders to reduce fees"]
        _print_suggestions(suggestions, "=" * 62)
        out = capsys.readouterr().out
        assert "Lower risk" in out
        assert "limit orders" in out
        assert "Improvement" in out


# ---------------------------------------------------------------------------
# Main CLI entry point
# ---------------------------------------------------------------------------


class TestMainEntryPoint:
    @patch("cli.utils.analytics_report.generate_report")
    def test_calls_generate_report(self, mock_gen, monkeypatch):
        from cli.utils.analytics_report import main

        monkeypatch.setattr("sys.argv", ["analytics_report.py", "--days", "7"])
        main()
        mock_gen.assert_called_once()
        assert mock_gen.call_args.kwargs["days"] == 7

    @patch("cli.utils.analytics_report.generate_report", side_effect=RuntimeError("DB error"))
    def test_handles_exception(self, mock_gen, monkeypatch):
        from cli.utils.analytics_report import main

        monkeypatch.setattr("sys.argv", ["analytics_report.py"])
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
