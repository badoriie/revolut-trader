#!/usr/bin/env python3
"""Comprehensive trading analytics report with charts and improvement suggestions.

Reads live-trading and backtest data from the encrypted database and produces:
  - A detailed terminal report with metrics tables
  - PNG charts saved to the output directory (requires ``matplotlib`` extra)
  - A ``report.md`` markdown file suitable for GitHub Actions job summaries

Usage
-----
    uv run python cli/analytics_report.py [--days N] [--output-dir PATH]

    # GitHub Actions: post the markdown to the job summary
    cat data/reports/report.md >> "$GITHUB_STEP_SUMMARY"

Optional extra dependencies (``uv sync --extra analytics``):
    matplotlib~=3.10   — chart generation
    numpy~=2.2         — faster statistical calculations
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from src.utils.db_persistence import DatabasePersistence

# ---------------------------------------------------------------------------
# Optional heavy deps — gracefully degrade without them
# ---------------------------------------------------------------------------

# Pre-declare so pyright sees these as always bound (chart functions are # pragma: no cover)
plt: Any = None
mticker: Any = None

try:
    import matplotlib  # type: ignore[import-untyped]

    matplotlib.use("Agg")  # non-interactive backend for CI/headless environments
    import matplotlib.pyplot as plt  # type: ignore[import-untyped]
    import matplotlib.ticker as mticker  # type: ignore[import-untyped]

    _HAS_MATPLOTLIB = True
except ImportError:  # pragma: no cover
    _HAS_MATPLOTLIB = False


# ---------------------------------------------------------------------------
# Pure financial math helpers
# ---------------------------------------------------------------------------


def compute_daily_returns(values: list[float]) -> list[float]:
    """Compute period-over-period percentage returns from a value series.

    Args:
        values: Ordered sequence of portfolio values.

    Returns:
        List of fractional returns (e.g. 0.01 = +1%) with length ``len(values) - 1``.
    """
    if len(values) < 2:
        return []
    return [(values[i] - values[i - 1]) / values[i - 1] for i in range(1, len(values))]


def _mean(values: list[float]) -> float:
    """Return the arithmetic mean of *values*, or 0.0 if empty."""
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float], mean: float | None = None) -> float:
    """Return the population standard deviation, or 0.0 if fewer than 2 values."""
    if len(values) < 2:
        return 0.0
    m = mean if mean is not None else _mean(values)
    variance = sum((v - m) ** 2 for v in values) / len(values)
    return math.sqrt(variance)


def compute_sharpe_ratio(daily_returns: list[float], risk_free_rate: float = 0.0) -> float:
    """Annualised Sharpe ratio (assuming 252 trading days per year).

    Returns 0.0 when the return series is empty or has zero volatility (undefined).

    Args:
        daily_returns: List of fractional daily returns.
        risk_free_rate: Daily risk-free rate (default 0.0).

    Returns:
        Annualised Sharpe ratio as a float.
    """
    if not daily_returns:
        return 0.0
    excess = [r - risk_free_rate for r in daily_returns]
    mean = _mean(excess)
    std = _std(excess, mean)
    if std == 0.0:
        return 0.0
    return (mean / std) * math.sqrt(252)


def compute_sortino_ratio(daily_returns: list[float], risk_free_rate: float = 0.0) -> float:
    """Annualised Sortino ratio — penalises only downside deviation.

    Returns 0.0 when the series is empty or there is no downside volatility.

    Args:
        daily_returns: List of fractional daily returns.
        risk_free_rate: Daily risk-free rate (default 0.0).

    Returns:
        Annualised Sortino ratio as a float.
    """
    if not daily_returns:
        return 0.0
    excess = [r - risk_free_rate for r in daily_returns]
    mean = _mean(excess)
    downside = [r for r in excess if r < 0.0]
    if not downside:
        return 0.0
    downside_std = math.sqrt(sum(r**2 for r in downside) / len(downside))
    if downside_std == 0.0:
        return 0.0
    return (mean / downside_std) * math.sqrt(252)


def compute_max_drawdown(values: list[float]) -> float:
    """Maximum peak-to-trough drawdown as a percentage.

    Args:
        values: Ordered sequence of portfolio values.

    Returns:
        Maximum drawdown percentage (e.g. 15.5 means −15.5%), or 0.0 if
        the series is empty or monotonically increasing.
    """
    if len(values) < 2:
        return 0.0
    peak = values[0]
    max_dd = 0.0
    for v in values[1:]:
        if v > peak:
            peak = v
        drawdown = (peak - v) / peak * 100 if peak > 0 else 0.0
        if drawdown > max_dd:
            max_dd = drawdown
    return max_dd


def _drawdown_series(values: list[float]) -> list[float]:
    """Return the drawdown percentage at each point in *values*.

    Args:
        values: Ordered portfolio value series.

    Returns:
        List of drawdown percentages (non-negative, 0 at new highs).
    """
    result: list[float] = []
    peak = values[0] if values else 0.0
    for v in values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100 if peak > 0 else 0.0
        result.append(dd)
    return result


def compute_profit_factor(pnl_values: list[float]) -> float:
    """Ratio of gross wins to gross losses.

    Returns 0.0 when no data is present or gross losses are zero (undefined).

    Args:
        pnl_values: Per-trade P&L values (positive = win, negative = loss).

    Returns:
        Profit factor as a float, or 0.0 when undefined.
    """
    if not pnl_values:
        return 0.0
    gross_wins = sum(v for v in pnl_values if v > 0)
    gross_losses = sum(abs(v) for v in pnl_values if v < 0)
    if gross_losses == 0.0 or gross_wins == 0.0:
        return 0.0
    return gross_wins / gross_losses


# ---------------------------------------------------------------------------
# Suggestions engine
# ---------------------------------------------------------------------------

_MIN_TRADES_FOR_SIGNAL = 10  # below this, avoid strong statistical claims
_HIGH_FEE_RATIO = 0.20  # fees > 20% of gross P&L → flag it
_HIGH_DRAWDOWN = 20.0  # max drawdown > 20% → flag it
_CAUTION_DRAWDOWN = 10.0
_LOW_WIN_RATE = 40.0
_WEAK_SHARPE = 0.5


def generate_suggestions(
    metrics: dict[str, Any],
    symbol_analytics: list[dict[str, Any]],
    backtest_analytics: dict[str, Any],
) -> list[str]:
    """Generate actionable improvement suggestions from trading metrics.

    The rules are intentionally conservative: they only fire when there is
    enough data (>= 10 trades) or an unambiguous signal (negative Sharpe, 0
    total trades, etc.).

    Args:
        metrics: Summary dict from ``get_analytics()`` or computed from value series.
        symbol_analytics: Per-symbol breakdown from ``get_symbol_analytics()``.
        backtest_analytics: Aggregate backtest dict from ``get_backtest_analytics()``.

    Returns:
        Ordered list of human-readable suggestion strings.
    """
    suggestions: list[str] = []

    total_trades = metrics.get("total_trades", 0)
    win_rate = metrics.get("win_rate", 0.0)
    total_pnl = metrics.get("total_pnl", 0.0)
    total_fees = metrics.get("total_fees", 0.0)
    max_dd = metrics.get("max_drawdown_pct", 0.0)
    sharpe = metrics.get("sharpe_ratio")
    profit_factor = metrics.get("profit_factor")

    if total_trades == 0:
        suggestions.append(
            "No trading data found in the selected window. "
            "Run the bot or a backtest first to generate analytics."
        )
        return suggestions

    # --- Win rate ---
    if total_trades >= _MIN_TRADES_FOR_SIGNAL and win_rate < _LOW_WIN_RATE:
        suggestions.append(
            f"Win rate is {win_rate:.1f}% (below {_LOW_WIN_RATE:.0f}%). "
            "Consider raising the minimum signal strength threshold "
            "(STRATEGY_MIN_SIGNAL_STRENGTH) to trade only on high-confidence signals."
        )

    # --- Fee drag ---
    if total_fees > 0 and total_pnl != 0:
        fee_ratio = total_fees / abs(total_pnl)
        if fee_ratio > _HIGH_FEE_RATIO:
            suggestions.append(
                f"Fees represent {fee_ratio * 100:.0f}% of gross P&L (€{total_fees:.2f} fees vs "
                f"€{abs(total_pnl):.2f} P&L). Switch MARKET-order strategies to LIMIT orders "
                "(0% maker fee) where latency allows."
            )

    # --- Drawdown ---
    if max_dd > _HIGH_DRAWDOWN:
        suggestions.append(
            f"Max drawdown is {max_dd:.1f}% (above {_HIGH_DRAWDOWN:.0f}%). "
            "Consider switching to the 'conservative' risk level or reducing INITIAL_CAPITAL "
            "to limit per-trade position sizes."
        )
    elif max_dd > _CAUTION_DRAWDOWN:
        suggestions.append(
            f"Max drawdown is {max_dd:.1f}%. Monitor closely — "
            "sustained trading at this drawdown level may approach uncomfortable territory."
        )

    # --- Sharpe ---
    if sharpe is not None:
        if sharpe < 0:
            suggestions.append(
                f"Sharpe ratio is {sharpe:.2f} (negative). Returns do not compensate for "
                "volatility. Review stop-loss levels and strategy parameters."
            )
        elif sharpe < _WEAK_SHARPE:
            suggestions.append(
                f"Sharpe ratio is {sharpe:.2f} (weak, target > 1.0). Risk-adjusted returns are "
                "below typical benchmarks. Run 'make backtest-compare' to explore alternatives."
            )

    # --- Profit factor ---
    if profit_factor is not None:
        if profit_factor < 1.0:
            suggestions.append(
                f"Profit factor is {profit_factor:.2f} (< 1.0 means total losses exceed total "
                "wins). Review stop-loss levels — losses may be cut too late or winners too early."
            )
        elif profit_factor < 1.3:
            suggestions.append(
                f"Profit factor is {profit_factor:.2f} (marginal). "
                "Aim for > 1.5 for a robust strategy."
            )

    # --- Symbol-level: flag consistently losing pairs (≥ 5 trades) ---
    suggestions.extend(
        f"Symbol {sym['symbol']} has negative P&L "
        f"(€{sym['total_pnl']:.2f} over {sym['total_trades']} trades, "
        f"win rate {sym.get('win_rate', 0):.0f}%). "
        "Consider removing it from TRADING_PAIRS or adjusting its strategy."
        for sym in symbol_analytics
        if sym.get("total_trades", 0) >= 5 and sym.get("total_pnl", 0) < 0
    )

    # --- Best backtest strategy hint ---
    best = backtest_analytics.get("best_run")
    if best:
        suggestions.append(
            f"Best backtest strategy: {best['strategy']} "
            f"(return {best.get('return_pct', 0):.1f}%, win rate {best.get('win_rate', 0):.1f}%). "
            "Use 'make backtest-compare' to explore all strategies."
        )

    if not suggestions:
        suggestions.append(
            "No significant issues detected. Strategy appears healthy — "
            "keep monitoring drawdown and fee drag as trade volume grows."
        )

    return suggestions


# ---------------------------------------------------------------------------
# Chart generators (require matplotlib)
# ---------------------------------------------------------------------------


def _chart_equity_curve(
    series: list[dict[str, Any]], output_dir: Path
) -> Path | None:  # pragma: no cover
    """Save equity curve PNG to *output_dir*."""
    if not _HAS_MATPLOTLIB or not series:
        return None
    timestamps = [s["timestamp"] for s in series]
    values = [s["total_value"] for s in series]

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(timestamps, values, linewidth=1.5, color="#2196F3")
    ax.fill_between(timestamps, min(values), values, alpha=0.1, color="#2196F3")
    ax.set_title("Portfolio Equity Curve", fontsize=14, fontweight="bold")
    ax.set_xlabel("Time")
    ax.set_ylabel("Portfolio Value (EUR)")
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("€%.0f"))
    ax.grid(True, alpha=0.3)
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    path = output_dir / "equity_curve.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def _chart_drawdown(
    series: list[dict[str, Any]], output_dir: Path
) -> Path | None:  # pragma: no cover
    """Save drawdown curve PNG to *output_dir*."""
    if not _HAS_MATPLOTLIB or not series:
        return None
    values = [s["total_value"] for s in series]
    timestamps = [s["timestamp"] for s in series]
    dd_series = _drawdown_series(values)

    fig, ax = plt.subplots(figsize=(12, 4))
    ax.fill_between(timestamps, dd_series, 0, alpha=0.6, color="#F44336")
    ax.plot(timestamps, dd_series, linewidth=1.0, color="#F44336")
    ax.set_title("Drawdown (%)", fontsize=14, fontweight="bold")
    ax.set_xlabel("Time")
    ax.set_ylabel("Drawdown (%)")
    ax.invert_yaxis()
    ax.grid(True, alpha=0.3)
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    path = output_dir / "drawdown.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def _chart_pnl_distribution(
    trades: list[dict[str, Any]], output_dir: Path
) -> Path | None:  # pragma: no cover
    """Save trade P&L distribution histogram PNG to *output_dir*."""
    if not _HAS_MATPLOTLIB or not trades:
        return None
    pnl_values = [float(t["pnl"]) for t in trades if t.get("pnl") is not None]
    if not pnl_values:
        return None

    fig, ax = plt.subplots(figsize=(10, 5))
    wins = [v for v in pnl_values if v >= 0]
    losses = [v for v in pnl_values if v < 0]
    bins = 30
    if wins:
        ax.hist(wins, bins=bins, color="#4CAF50", alpha=0.7, label=f"Wins ({len(wins)})")
    if losses:
        ax.hist(losses, bins=bins, color="#F44336", alpha=0.7, label=f"Losses ({len(losses)})")
    ax.axvline(0, color="black", linewidth=1.0, linestyle="--")
    ax.set_title("Trade P&L Distribution", fontsize=14, fontweight="bold")
    ax.set_xlabel("P&L (EUR)")
    ax.set_ylabel("Trade Count")
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    path = output_dir / "pnl_distribution.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def _chart_symbol_performance(
    symbol_analytics: list[dict[str, Any]], output_dir: Path
) -> Path | None:  # pragma: no cover
    """Save per-symbol P&L bar chart PNG to *output_dir*."""
    if not _HAS_MATPLOTLIB or not symbol_analytics:
        return None
    symbols = [s["symbol"] for s in symbol_analytics]
    pnl = [s["total_pnl"] for s in symbol_analytics]
    colors = ["#4CAF50" if v >= 0 else "#F44336" for v in pnl]

    fig, ax = plt.subplots(figsize=(max(8, len(symbols) * 1.5), 5))
    ax.bar(symbols, pnl, color=colors, edgecolor="white", linewidth=0.5)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("P&L by Symbol", fontsize=14, fontweight="bold")
    ax.set_xlabel("Symbol")
    ax.set_ylabel("Total P&L (EUR)")
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("€%.0f"))
    ax.grid(True, alpha=0.3, axis="y")
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    path = output_dir / "symbol_performance.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def _chart_backtest_comparison(
    backtest_runs: list[dict[str, Any]], output_dir: Path
) -> Path | None:  # pragma: no cover
    """Save backtest strategy return-% comparison bar chart PNG to *output_dir*."""
    if not _HAS_MATPLOTLIB or not backtest_runs:
        return None
    # Take the best run per strategy
    best_by_strategy: dict[str, dict[str, Any]] = {}
    for run in backtest_runs:
        strat = run["strategy"]
        if (
            strat not in best_by_strategy
            or run["return_pct"] > best_by_strategy[strat]["return_pct"]
        ):
            best_by_strategy[strat] = run

    strategies = list(best_by_strategy.keys())
    returns = [best_by_strategy[s]["return_pct"] for s in strategies]
    colors = ["#4CAF50" if r >= 0 else "#F44336" for r in returns]

    fig, ax = plt.subplots(figsize=(max(8, len(strategies) * 1.8), 5))
    ax.bar(strategies, returns, color=colors, edgecolor="white", linewidth=0.5)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("Best Backtest Return by Strategy", fontsize=14, fontweight="bold")
    ax.set_xlabel("Strategy")
    ax.set_ylabel("Return (%)")
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f%%"))
    ax.grid(True, alpha=0.3, axis="y")
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    path = output_dir / "backtest_comparison.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------


def _fmt_eur(value: float) -> str:
    """Format a float as EUR with sign."""
    sign = "+" if value >= 0 else ""
    return f"{sign}€{value:,.2f}"


def _fmt_pct(value: float, decimals: int = 2) -> str:
    """Format a float as a percentage with sign."""
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.{decimals}f}%"


def generate_report(
    days: int = 30,
    output_dir: Path = Path("data/reports"),
    quiet: bool = False,
) -> dict[str, Any]:
    """Run the full analytics pipeline and write output files.

    Fetches data from the encrypted database, computes metrics, generates
    charts (if matplotlib is available), prints a terminal report, and
    writes a ``report.md`` to *output_dir*.

    Args:
        days: Look-back window in calendar days for live-trading metrics.
        output_dir: Directory to write charts and the markdown report into.
        quiet: Suppress terminal output (useful in tests).

    Returns:
        Dict containing all computed metrics, suggestions, and file paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    db = DatabasePersistence()

    # --- Fetch data ---
    analytics = db.get_analytics(days=days)
    symbol_analytics = db.get_symbol_analytics(days=days)
    strategy_analytics = db.get_strategy_live_analytics(days=days)
    portfolio_series = db.get_portfolio_value_series(days=days)
    backtest_analytics = db.get_backtest_analytics()
    backtest_runs = db.load_backtest_runs(limit=50)
    trade_history = db.load_trade_history(limit=10_000)

    # --- Compute derived metrics ---
    values = [s["total_value"] for s in portfolio_series]
    daily_returns = compute_daily_returns(values)
    sharpe = compute_sharpe_ratio(daily_returns)
    sortino = compute_sortino_ratio(daily_returns)
    max_dd = compute_max_drawdown(values)
    pnl_values = [float(t["pnl"]) for t in trade_history if t.get("pnl") is not None]
    profit_factor = compute_profit_factor(pnl_values)

    metrics: dict[str, Any] = {
        **analytics,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "max_drawdown_pct": max_dd,
        "profit_factor": profit_factor,
    }

    # --- Suggestions ---
    suggestions = generate_suggestions(metrics, symbol_analytics, backtest_analytics)

    # --- Generate charts ---
    chart_paths: list[Path] = []
    if _HAS_MATPLOTLIB:  # pragma: no cover
        for fn, arg in [
            (_chart_equity_curve, portfolio_series),
            (_chart_drawdown, portfolio_series),
            (_chart_pnl_distribution, trade_history),
            (_chart_symbol_performance, symbol_analytics),
            (_chart_backtest_comparison, backtest_runs),
        ]:
            path = fn(arg, output_dir)
            if path:
                chart_paths.append(path)

    # --- Terminal report ---
    if not quiet:
        _print_report(
            metrics, symbol_analytics, strategy_analytics, backtest_analytics, suggestions, days
        )

    # --- Markdown report ---
    md = _build_markdown(
        metrics,
        symbol_analytics,
        strategy_analytics,
        backtest_analytics,
        suggestions,
        chart_paths,
        days,
    )
    md_path = output_dir / "report.md"
    md_path.write_text(md)

    if not quiet:
        print(f"\nReport written to: {md_path}")
        if chart_paths:
            print(f"Charts saved: {', '.join(p.name for p in chart_paths)}")
        if not _HAS_MATPLOTLIB:
            print("\nNote: Install analytics extras for charts: uv sync --extra analytics")

    return {
        "metrics": metrics,
        "symbol_analytics": symbol_analytics,
        "strategy_analytics": strategy_analytics,
        "backtest_analytics": backtest_analytics,
        "suggestions": suggestions,
        "chart_paths": [str(p) for p in chart_paths],
        "report_path": str(md_path),
    }


# ---------------------------------------------------------------------------
# Terminal output
# ---------------------------------------------------------------------------


def _print_report(
    metrics: dict[str, Any],
    symbol_analytics: list[dict[str, Any]],
    strategy_analytics: list[dict[str, Any]],
    backtest_analytics: dict[str, Any],
    suggestions: list[str],
    days: int,
) -> None:
    """Print a structured terminal report."""
    total_trades = metrics.get("total_trades", 0)
    win_rate = metrics.get("win_rate", 0.0)
    total_pnl = metrics.get("total_pnl", 0.0)
    total_fees = metrics.get("total_fees", 0.0)
    sharpe = metrics.get("sharpe_ratio", 0.0)
    sortino = metrics.get("sortino_ratio", 0.0)
    max_dd = metrics.get("max_drawdown_pct", 0.0)
    profit_factor = metrics.get("profit_factor", 0.0)
    initial = metrics.get("initial_value", 0.0)
    final = metrics.get("final_value", 0.0)
    ret_pct = metrics.get("return_pct", 0.0)

    sep = "=" * 62

    print(f"\n{sep}")
    print(f"  Trading Analytics Report — Last {days} Days")
    print(sep)

    print("\n  Core Metrics")
    print("-" * 62)
    print(f"  {'Metric':<30} {'Value':>28}")
    print("-" * 62)
    rows = [
        ("Total Trades", str(total_trades)),
        ("Win Rate", f"{win_rate:.1f}%"),
        ("Total P&L", _fmt_eur(total_pnl)),
        ("Total Fees", f"€{total_fees:,.2f}"),
        ("Return", _fmt_pct(ret_pct) if ret_pct else "N/A"),
        ("Initial Portfolio Value", f"€{initial:,.2f}" if initial else "N/A"),
        ("Final Portfolio Value", f"€{final:,.2f}" if final else "N/A"),
        ("Max Drawdown", f"{max_dd:.2f}%"),
        ("Sharpe Ratio", f"{sharpe:.3f}" if sharpe else "N/A"),
        ("Sortino Ratio", f"{sortino:.3f}" if sortino else "N/A"),
        ("Profit Factor", f"{profit_factor:.2f}" if profit_factor else "N/A"),
    ]
    for label, value in rows:
        print(f"  {label:<30} {value:>28}")
    print("-" * 62)

    if symbol_analytics:
        print("\n  Per-Symbol Breakdown")
        print("-" * 62)
        print(f"  {'Symbol':<14} {'Trades':>6} {'Win%':>7} {'P&L':>14} {'Fees':>12}")
        print("-" * 62)
        for s in symbol_analytics:
            print(
                f"  {s['symbol']:<14} {s['total_trades']:>6} "
                f"{s['win_rate']:>6.1f}% {_fmt_eur(s['total_pnl']):>14} "
                f"€{s['total_fees']:>10.2f}"
            )
        print("-" * 62)

    if strategy_analytics:
        print("\n  Per-Strategy Breakdown (Live Trades)")
        print("-" * 62)
        print(f"  {'Strategy':<20} {'Trades':>6} {'Win%':>7} {'P&L':>14}")
        print("-" * 62)
        for s in strategy_analytics:
            print(
                f"  {s['strategy']:<20} {s['total_trades']:>6} "
                f"{s['win_rate']:>6.1f}% {_fmt_eur(s['total_pnl']):>14}"
            )
        print("-" * 62)

    if backtest_analytics and backtest_analytics.get("total_runs", 0) > 0:
        print("\n  Backtest Summary")
        print("-" * 62)
        print(f"  Total backtest runs:   {backtest_analytics['total_runs']}")
        print(
            f"  Profitable runs:       {backtest_analytics['profitable_runs']} "
            f"({backtest_analytics.get('success_rate', 0):.1f}%)"
        )
        print(f"  Avg return:            {backtest_analytics.get('avg_return_pct', 0):.2f}%")
        best = backtest_analytics.get("best_run")
        if best:
            print(
                f"  Best strategy:         {best['strategy']} "
                f"({best.get('return_pct', 0):.1f}% return)"
            )
        print("-" * 62)

    print("\n  Improvement Suggestions")
    print("-" * 62)
    for i, suggestion in enumerate(suggestions, 1):
        # Word-wrap at 58 chars
        words = suggestion.split()
        lines: list[str] = []
        line = f"  {i}. "
        indent = "     "
        for word in words:
            if len(line) + len(word) + 1 > 62:
                lines.append(line)
                line = indent + word
            else:
                line += (" " if line.strip() else "") + word
        lines.append(line)
        print("\n".join(lines))
        print()
    print(sep)


# ---------------------------------------------------------------------------
# Markdown report builder
# ---------------------------------------------------------------------------


def _build_markdown(
    metrics: dict[str, Any],
    symbol_analytics: list[dict[str, Any]],
    strategy_analytics: list[dict[str, Any]],
    backtest_analytics: dict[str, Any],
    suggestions: list[str],
    chart_paths: list[Path],
    days: int,
) -> str:
    """Build the full Markdown report string."""
    total_trades = metrics.get("total_trades", 0)
    win_rate = metrics.get("win_rate", 0.0)
    total_pnl = metrics.get("total_pnl", 0.0)
    total_fees = metrics.get("total_fees", 0.0)
    sharpe = metrics.get("sharpe_ratio", 0.0)
    sortino = metrics.get("sortino_ratio", 0.0)
    max_dd = metrics.get("max_drawdown_pct", 0.0)
    profit_factor = metrics.get("profit_factor", 0.0)
    ret_pct = metrics.get("return_pct", 0.0)
    initial = metrics.get("initial_value", 0.0)
    final = metrics.get("final_value", 0.0)

    lines: list[str] = [
        f"## Trading Analytics Report — Last {days} Days",
        "",
        "### Core Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Trades | {total_trades} |",
        f"| Win Rate | {win_rate:.1f}% |",
        f"| Total P&L | {_fmt_eur(total_pnl)} |",
        f"| Total Fees | €{total_fees:,.2f} |",
        f"| Return | {_fmt_pct(ret_pct) if ret_pct else 'N/A'} |",
        f"| Initial Portfolio Value | {f'€{initial:,.2f}' if initial else 'N/A'} |",
        f"| Final Portfolio Value | {f'€{final:,.2f}' if final else 'N/A'} |",
        f"| Max Drawdown | {max_dd:.2f}% |",
        f"| Sharpe Ratio | {sharpe:.3f if sharpe else 'N/A'} |",
        f"| Sortino Ratio | {sortino:.3f if sortino else 'N/A'} |",
        f"| Profit Factor | {profit_factor:.2f if profit_factor else 'N/A'} |",
        "",
    ]

    if symbol_analytics:
        lines += [
            "### Per-Symbol Breakdown",
            "",
            "| Symbol | Trades | Win Rate | Total P&L | Total Fees |",
            "|--------|--------|----------|-----------|------------|",
        ]
        for s in symbol_analytics:
            lines.append(
                f"| {s['symbol']} | {s['total_trades']} | {s['win_rate']:.1f}% | "
                f"{_fmt_eur(s['total_pnl'])} | €{s['total_fees']:.2f} |"
            )
        lines.append("")

    if strategy_analytics:
        lines += [
            "### Per-Strategy Breakdown (Live Trades)",
            "",
            "| Strategy | Trades | Win Rate | Total P&L |",
            "|----------|--------|----------|-----------|",
        ]
        for s in strategy_analytics:
            lines.append(
                f"| {s['strategy']} | {s['total_trades']} | {s['win_rate']:.1f}% | "
                f"{_fmt_eur(s['total_pnl'])} |"
            )
        lines.append("")

    if backtest_analytics and backtest_analytics.get("total_runs", 0) > 0:
        best = backtest_analytics.get("best_run", {})
        lines += [
            "### Backtest Summary",
            "",
            f"- **Total runs:** {backtest_analytics['total_runs']}",
            f"- **Profitable runs:** {backtest_analytics['profitable_runs']} "
            f"({backtest_analytics.get('success_rate', 0):.1f}%)",
            f"- **Avg return:** {backtest_analytics.get('avg_return_pct', 0):.2f}%",
        ]
        if best:
            lines.append(
                f"- **Best strategy:** {best['strategy']} "
                f"({best.get('return_pct', 0):.1f}% return, "
                f"{best.get('win_rate', 0):.1f}% win rate)"
            )
        lines.append("")

    lines += ["### Improvement Suggestions", ""]
    for suggestion in suggestions:
        lines.append(f"- {suggestion}")
    lines.append("")

    if chart_paths:
        lines += ["### Charts", ""]
        for p in chart_paths:
            lines.append(f"![{p.stem}]({p.name})")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point for the analytics report tool."""
    parser = argparse.ArgumentParser(
        description="Generate a comprehensive trading analytics report with charts."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Look-back window in calendar days for live-trading analytics (default: 30)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/reports"),
        help="Directory to write charts and report.md into (default: data/reports)",
    )
    args = parser.parse_args()

    try:
        generate_report(days=args.days, output_dir=args.output_dir)
    except Exception as e:
        logger.error(f"Analytics report failed: {e}", exc_info=True)
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
