"""Unit tests for analytics_report pure computational functions.

These tests cover the financial math utilities and the rule-based suggestions
engine in ``cli/analytics_report.py``.  No database, no matplotlib, no I/O.
"""

from __future__ import annotations

import pytest

from cli.analytics_report import (
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
