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
    fpdf2~=2.8         — PDF generation for Telegram notifications
"""

from __future__ import annotations

import argparse
import asyncio
import math
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from loguru import logger

from src.config import settings
from src.utils.db_persistence import DatabasePersistence
from src.utils.telegram import TelegramNotifier

# ---------------------------------------------------------------------------
# Optional heavy deps — gracefully degrade without them
# ---------------------------------------------------------------------------

# Pre-declare so pyright sees these as always bound (chart functions are # pragma: no cover)
mdates: Any = None
plt: Any = None
mticker: Any = None

try:
    import matplotlib  # type: ignore[import-untyped]

    matplotlib.use("Agg")  # non-interactive backend for CI/headless environments
    import matplotlib.dates as mdates  # type: ignore[import-untyped]
    import matplotlib.pyplot as plt  # type: ignore[import-untyped]
    import matplotlib.ticker as mticker  # type: ignore[import-untyped]

    _HAS_MATPLOTLIB = True
except ImportError:  # pragma: no cover
    _HAS_MATPLOTLIB = False

try:
    import fpdf as _fpdf_module  # type: ignore[import-untyped]  # noqa: F401

    _HAS_FPDF2 = True
except ImportError:  # pragma: no cover
    _HAS_FPDF2 = False


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
    if std <= 0.0:
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
    if downside_std <= 0.0:
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
    if not gross_losses or not gross_wins:
        return 0.0
    return gross_wins / gross_losses


# ---------------------------------------------------------------------------
# Suggestions engine
# ---------------------------------------------------------------------------

_MIN_TRADES_FOR_SIGNAL = 10  # below this, avoid strong statistical claims
_HIGH_FEE_RATIO = 0.20  # fees > 20% of gross P&L → flag it


def _sharpe_suggestions(sharpe: float | None) -> list[str]:
    """Return suggestion strings for the Sharpe ratio value."""
    if sharpe is None:
        return []
    if sharpe < 0:
        return [
            f"Sharpe ratio is {sharpe:.2f} (negative). Returns do not compensate for "
            "volatility. Review stop-loss levels and strategy parameters."
        ]
    if sharpe < _WEAK_SHARPE:
        return [
            f"Sharpe ratio is {sharpe:.2f} (weak, target > 1.0). Risk-adjusted returns are "
            "below typical benchmarks. Run 'make backtest-compare' to explore alternatives."
        ]
    return []


def _profit_factor_suggestions(profit_factor: float | None) -> list[str]:
    """Return suggestion strings for the profit factor value."""
    if profit_factor is None:
        return []
    if profit_factor < 1.0:
        return [
            f"Profit factor is {profit_factor:.2f} (< 1.0 means total losses exceed total "
            "wins). Review stop-loss levels — losses may be cut too late or winners too early."
        ]
    if profit_factor < 1.3:
        return [
            f"Profit factor is {profit_factor:.2f} (marginal). Aim for > 1.5 for a robust strategy."
        ]
    return []


_HIGH_DRAWDOWN = 20.0  # max drawdown > 20% → flag it
_CAUTION_DRAWDOWN = 10.0
_LOW_WIN_RATE = 40.0
_WEAK_SHARPE = 0.5


def _check_no_trades(metrics: dict[str, Any]) -> list[str]:
    """Return a suggestion if no trades exist in the selected window."""
    if metrics.get("total_trades", 0) == 0:
        return [
            "No trading data found in the selected window. "
            "Run the bot or a backtest first to generate analytics."
        ]
    return []


def _check_win_rate(metrics: dict[str, Any]) -> list[str]:
    """Return a suggestion if win rate is below the low-win-rate threshold."""
    if (
        metrics.get("total_trades", 0) >= _MIN_TRADES_FOR_SIGNAL
        and metrics.get("win_rate", 0.0) < _LOW_WIN_RATE
    ):
        return [
            f"Win rate is {metrics['win_rate']:.1f}% (below {_LOW_WIN_RATE:.0f}%). "
            "Consider raising the minimum signal strength threshold "
            "(STRATEGY_MIN_SIGNAL_STRENGTH) to trade only on high-confidence signals."
        ]
    return []


def _check_fee_drag(metrics: dict[str, Any]) -> list[str]:
    """Return a suggestion if fees represent a large fraction of gross P&L."""
    total_fees = metrics.get("total_fees", 0.0)
    total_pnl = metrics.get("total_pnl", 0.0)
    if total_fees > 0 and total_pnl != 0:
        fee_ratio = total_fees / abs(total_pnl)
        if fee_ratio > _HIGH_FEE_RATIO:
            return [
                f"Fees represent {fee_ratio * 100:.0f}% of gross P&L (€{total_fees:.2f} fees vs "
                f"€{abs(total_pnl):.2f} P&L). Switch MARKET-order strategies to LIMIT orders "
                "(0% maker fee) where latency allows."
            ]
    return []


def _check_drawdown(metrics: dict[str, Any]) -> list[str]:
    """Return a suggestion if max drawdown exceeds warning thresholds."""
    max_dd = metrics.get("max_drawdown_pct", 0.0)
    if max_dd > _HIGH_DRAWDOWN:
        return [
            f"Max drawdown is {max_dd:.1f}% (above {_HIGH_DRAWDOWN:.0f}%). "
            "Consider switching to the 'conservative' risk level or reducing INITIAL_CAPITAL "
            "to limit per-trade position sizes."
        ]
    if max_dd > _CAUTION_DRAWDOWN:
        return [
            f"Max drawdown is {max_dd:.1f}%. Monitor closely — "
            "sustained trading at this drawdown level may approach uncomfortable territory."
        ]
    return []


def _check_symbol_losses(symbol_analytics: list[dict[str, Any]]) -> list[str]:
    """Return a suggestion for each symbol with negative P&L and sufficient trade history."""
    return [
        f"Symbol {sym['symbol']} has negative P&L "
        f"(€{sym['total_pnl']:.2f} over {sym['total_trades']} trades, "
        f"win rate {sym.get('win_rate', 0):.0f}%). "
        "Consider removing it from TRADING_PAIRS or adjusting its strategy."
        for sym in symbol_analytics
        if sym.get("total_trades", 0) >= 5 and sym.get("total_pnl", 0) < 0
    ]


def _check_best_backtest(backtest_analytics: dict[str, Any]) -> list[str]:
    """Return a suggestion highlighting the best-performing backtest strategy."""
    best = backtest_analytics.get("best_run")
    if best:
        return [
            f"Best backtest strategy: {best['strategy']} "
            f"(return {best.get('return_pct', 0):.1f}%, win rate {best.get('win_rate', 0):.1f}%). "
            "Use 'make backtest-compare' to explore all strategies."
        ]
    return []


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
    no_trades = _check_no_trades(metrics)
    if no_trades:
        return no_trades

    suggestions: list[str] = []
    suggestions.extend(_check_win_rate(metrics))
    suggestions.extend(_check_fee_drag(metrics))
    suggestions.extend(_check_drawdown(metrics))
    suggestions.extend(_sharpe_suggestions(metrics.get("sharpe_ratio")))
    suggestions.extend(_profit_factor_suggestions(metrics.get("profit_factor")))
    suggestions.extend(_check_symbol_losses(symbol_analytics))
    suggestions.extend(_check_best_backtest(backtest_analytics))
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
    values = [s["total_value"] for s in series]
    try:
        timestamps = [datetime.fromisoformat(str(s["timestamp"])) for s in series]
        use_dates = True
    except (ValueError, TypeError):
        timestamps = [s["timestamp"] for s in series]
        use_dates = False

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(timestamps, values, linewidth=1.5, color="#2196F3")
    ax.fill_between(timestamps, min(values), values, alpha=0.1, color="#2196F3")
    ax.set_title("Portfolio Equity Curve", fontsize=14, fontweight="bold")
    ax.set_xlabel("Time")
    ax.set_ylabel("Portfolio Value (EUR)")
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("€%.0f"))
    if use_dates:
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=8))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d %H:%M"))
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
    try:
        timestamps = [datetime.fromisoformat(str(s["timestamp"])) for s in series]
        use_dates = True
    except (ValueError, TypeError):
        timestamps = [s["timestamp"] for s in series]
        use_dates = False
    dd_series = _drawdown_series(values)

    fig, ax = plt.subplots(figsize=(12, 4))
    ax.fill_between(timestamps, dd_series, 0, alpha=0.6, color="#F44336")
    ax.plot(timestamps, dd_series, linewidth=1.0, color="#F44336")
    ax.set_title("Drawdown (%)", fontsize=14, fontweight="bold")
    ax.set_xlabel("Time")
    ax.set_ylabel("Drawdown (%)")
    ax.invert_yaxis()
    ax.grid(True, alpha=0.3)
    if use_dates:
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=8))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d %H:%M"))
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

    fig, ax = plt.subplots(figsize=(max(8, int(len(symbols) * 1.5)), 5))
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

    fig, ax = plt.subplots(figsize=(max(8, int(len(strategies) * 1.8)), 5))
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


def _fetch_report_data(
    db: DatabasePersistence, days: int
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """Fetch all data needed for the analytics report from the database."""
    analytics = db.get_analytics(days=days)
    symbol_analytics = db.get_symbol_analytics(days=days)
    strategy_analytics = db.get_strategy_live_analytics(days=days)
    portfolio_series = db.get_portfolio_value_series(days=days)
    backtest_analytics = db.get_backtest_analytics()
    backtest_runs = db.load_backtest_runs(limit=50)
    trade_history = db.load_trade_history(limit=10_000)
    return (
        analytics,
        symbol_analytics,
        strategy_analytics,
        portfolio_series,
        backtest_analytics,
        backtest_runs,
        trade_history,
    )


def _compute_report_metrics(
    analytics: dict[str, Any],
    portfolio_series: list[dict[str, Any]],
    trade_history: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute derived metrics (Sharpe, Sortino, drawdown, profit factor) from raw data."""
    values = [s["total_value"] for s in portfolio_series]
    daily_returns = compute_daily_returns(values)
    sharpe = compute_sharpe_ratio(daily_returns)
    sortino = compute_sortino_ratio(daily_returns)
    max_dd = compute_max_drawdown(values)
    pnl_values = [float(t["pnl"]) for t in trade_history if t.get("pnl") is not None]
    profit_factor = compute_profit_factor(pnl_values)
    return {
        **analytics,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "max_drawdown_pct": max_dd,
        "profit_factor": profit_factor,
    }


def _generate_report_charts(
    output_dir: Path,
    portfolio_series: list[dict[str, Any]],
    trade_history: list[dict[str, Any]],
    symbol_analytics: list[dict[str, Any]],
    backtest_runs: list[dict[str, Any]],
) -> list[Path]:
    """Generate PNG charts and return their paths (no-op when matplotlib is absent)."""
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
    return chart_paths


async def _send_telegram_report(
    send_telegram: bool,
    days: int,
    metrics: dict[str, Any],
    md_path: Path,
    symbol_analytics: list[dict[str, Any]] | None = None,
    strategy_analytics: list[dict[str, Any]] | None = None,
    backtest_analytics: dict[str, Any] | None = None,
    suggestions: list[str] | None = None,
    chart_paths: list[Path] | None = None,
) -> None:
    """Send a Telegram notification summarising the analytics report if configured."""
    if not send_telegram:
        return
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.debug("Telegram not configured — skipping report notification")
        return
    try:
        notifier = TelegramNotifier(
            token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
        )
        # Try PDF first; any failure falls back to the text summary so the user
        # always receives *some* notification even when fpdf2 or chart loading fails.
        pdf_bytes: bytes | None = None
        try:
            pdf_bytes = _generate_pdf(
                md_path,
                metrics,
                days,
                symbol_analytics=symbol_analytics,
                strategy_analytics=strategy_analytics,
                backtest_analytics=backtest_analytics,
                suggestions=suggestions,
                chart_paths=chart_paths,
            )
        except Exception as pdf_err:
            logger.warning(f"PDF generation failed, falling back to text notification: {pdf_err!r}")

        if pdf_bytes is not None:
            total_pnl = metrics.get("total_pnl", 0.0)
            return_pct = metrics.get("return_pct", 0.0)
            win_rate = metrics.get("win_rate", 0.0)
            sharpe = metrics.get("sharpe_ratio", 0.0)
            max_dd = metrics.get("max_drawdown_pct", 0.0)
            total_trades = metrics.get("total_trades", 0)
            emoji = "📊" if total_pnl >= 0 else "📉"
            pnl_sign = "+" if total_pnl >= 0 else "-"
            ret_sign = "+" if return_pct >= 0 else ""
            sharpe_str = f"{sharpe:.3f}" if sharpe else "N/A"
            caption = (
                f"{emoji} <b>Analytics Report — {days} days</b>\n"
                f"Trades: {total_trades} | Win Rate: {win_rate:.1f}%\n"
                f"P&amp;L: {pnl_sign}€{abs(total_pnl):.2f} | Return: {ret_sign}{return_pct:.2f}%\n"
                f"Sharpe: {sharpe_str} | Max DD: {max_dd:.1f}%"
            )
            await notifier.send_document(pdf_bytes, "analytics_report.pdf", caption=caption)
        else:
            await notifier.notify_report_ready(
                days=days,
                total_trades=metrics.get("total_trades", 0),
                total_pnl=Decimal(str(metrics.get("total_pnl", 0.0))),
                return_pct=metrics.get("return_pct", 0.0),
                win_rate=metrics.get("win_rate", 0.0),
                sharpe_ratio=metrics.get("sharpe_ratio", 0.0),
                max_drawdown_pct=metrics.get("max_drawdown_pct", 0.0),
                report_path=str(md_path),
            )
    except Exception as e:
        logger.warning(f"Failed to send Telegram report notification: {e}")


# Characters outside Helvetica's Latin-1 charset mapped to safe ASCII equivalents.
_PDF_CHAR_MAP = str.maketrans(
    {
        "\u20ac": "EUR",  # € euro sign
        "\u2014": "-",  # — em dash
        "\u2013": "-",  # – en dash
        "\u2018": "'",  # ' left single quote
        "\u2019": "'",  # ' right single quote
        "\u201c": '"',  # " left double quote
        "\u201d": '"',  # " right double quote
        "\u2026": "...",  # … ellipsis
        "\u00a0": " ",  # non-breaking space
    }
)


def _pdf_safe_text(text: str) -> str:  # pragma: no cover
    """Replace characters outside Helvetica's Latin-1 range with ASCII equivalents."""
    return text.translate(_PDF_CHAR_MAP)


def _pdf_section_header(pdf: Any, title: str) -> None:  # pragma: no cover
    """Print a bold section header line in the PDF."""
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, _pdf_safe_text(title), new_x="LMARGIN", new_y="NEXT")


def _pdf_two_col_table(pdf: Any, rows: list[tuple[str, str]]) -> None:  # pragma: no cover
    """Print a label/value two-column table in the PDF."""
    for label, value in rows:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(70, 6, _pdf_safe_text(label))
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, _pdf_safe_text(value), new_x="LMARGIN", new_y="NEXT")


def _pdf_table(
    pdf: Any,
    headers: list[str],
    rows: list[list[str]],
    col_widths: list[int],
) -> None:  # pragma: no cover
    """Print a bordered multi-column table with a header row in the PDF."""
    pdf.set_font("Helvetica", "B", 9)
    for header, w in zip(headers, col_widths, strict=False):
        pdf.cell(w, 6, _pdf_safe_text(header), border=1)
    pdf.ln()
    pdf.set_font("Helvetica", "", 9)
    for row in rows:
        for value, w in zip(row, col_widths, strict=False):
            pdf.cell(w, 6, _pdf_safe_text(value), border=1)
        pdf.ln()


def _generate_pdf(
    md_path: Path,
    metrics: dict[str, Any],
    days: int,
    symbol_analytics: list[dict[str, Any]] | None = None,
    strategy_analytics: list[dict[str, Any]] | None = None,
    backtest_analytics: dict[str, Any] | None = None,
    suggestions: list[str] | None = None,
    chart_paths: list[Path] | None = None,
) -> bytes | None:  # pragma: no cover
    """Generate a comprehensive PDF analytics report using fpdf2.

    Mirrors the full content of ``report.md``: core metrics, per-symbol and
    per-strategy breakdowns, backtest summary, improvement suggestions, and
    all PNG charts embedded as images.  Uses the built-in Helvetica font
    (Latin-1 only) so no external font files are required.

    Returns the raw PDF bytes, or ``None`` when fpdf2 is not installed.

    Args:
        md_path:            Path to the generated ``report.md`` file (footer).
        metrics:            Computed metrics from :func:`_compute_report_metrics`.
        days:               Look-back window in calendar days.
        symbol_analytics:   Per-symbol rows from the database.
        strategy_analytics: Per-strategy rows from the database.
        backtest_analytics: Aggregate backtest dict from the database.
        suggestions:        Rule-based improvement suggestion strings.
        chart_paths:        Paths to PNG chart files to embed.

    Returns:
        Raw PDF bytes, or ``None`` when fpdf2 is unavailable.
    """
    if not _HAS_FPDF2:
        return None

    from fpdf import FPDF  # type: ignore[import-untyped]

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # ── Title ─────────────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(
        0,
        10,
        _pdf_safe_text(f"Trading Analytics Report - Last {days} Days"),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(3)

    # ── Core Metrics ──────────────────────────────────────────────────────────
    _pdf_section_header(pdf, "Core Metrics")
    total_trades = metrics.get("total_trades", 0)
    win_rate = metrics.get("win_rate", 0.0)
    total_pnl = metrics.get("total_pnl", 0.0)
    total_fees = metrics.get("total_fees", 0.0)
    ret_pct = metrics.get("return_pct", 0.0)
    max_dd = metrics.get("max_drawdown_pct", 0.0)
    sharpe = metrics.get("sharpe_ratio", 0.0)
    sortino = metrics.get("sortino_ratio", 0.0)
    profit_factor = metrics.get("profit_factor", 0.0)
    initial = metrics.get("initial_value", 0.0)
    final = metrics.get("final_value", 0.0)
    pnl_pfx = "+" if total_pnl >= 0 else "-"
    ret_pfx = "+" if ret_pct >= 0 else ""
    _pdf_two_col_table(
        pdf,
        [
            ("Total Trades", str(total_trades)),
            ("Win Rate", f"{win_rate:.1f}%"),
            ("Total P&L", f"{pnl_pfx}EUR{abs(total_pnl):,.2f}"),
            ("Total Fees", f"EUR{total_fees:,.2f}"),
            ("Return", f"{ret_pfx}{ret_pct:.2f}%"),
            ("Initial Portfolio Value", f"EUR{initial:,.2f}" if initial else "N/A"),
            ("Final Portfolio Value", f"EUR{final:,.2f}" if final else "N/A"),
            ("Max Drawdown", f"{max_dd:.2f}%"),
            ("Sharpe Ratio", f"{sharpe:.3f}" if sharpe else "N/A"),
            ("Sortino Ratio", f"{sortino:.3f}" if sortino else "N/A"),
            ("Profit Factor", f"{profit_factor:.2f}" if profit_factor else "N/A"),
        ],
    )

    # ── Per-Symbol Breakdown ──────────────────────────────────────────────────
    if symbol_analytics:
        pdf.ln(4)
        _pdf_section_header(pdf, "Per-Symbol Breakdown")
        _pdf_table(
            pdf,
            headers=["Symbol", "Trades", "Win%", "P&L (EUR)", "Fees (EUR)"],
            rows=[
                [
                    s["symbol"],
                    str(s["total_trades"]),
                    f"{s['win_rate']:.1f}%",
                    f"{'+' if s['total_pnl'] >= 0 else ''}{s['total_pnl']:,.2f}",
                    f"{s['total_fees']:,.2f}",
                ]
                for s in symbol_analytics
            ],
            col_widths=[40, 22, 22, 52, 44],
        )

    # ── Per-Strategy Breakdown ────────────────────────────────────────────────
    if strategy_analytics:
        pdf.ln(4)
        _pdf_section_header(pdf, "Per-Strategy Breakdown (Live Trades)")
        _pdf_table(
            pdf,
            headers=["Strategy", "Trades", "Win%", "P&L (EUR)"],
            rows=[
                [
                    s["strategy"],
                    str(s["total_trades"]),
                    f"{s['win_rate']:.1f}%",
                    f"{'+' if s['total_pnl'] >= 0 else ''}{s['total_pnl']:,.2f}",
                ]
                for s in strategy_analytics
            ],
            col_widths=[65, 25, 25, 65],
        )

    # ── Backtest Summary ──────────────────────────────────────────────────────
    if backtest_analytics and backtest_analytics.get("total_runs", 0) > 0:
        pdf.ln(4)
        _pdf_section_header(pdf, "Backtest Summary")
        best = backtest_analytics.get("best_run", {})
        bt_rows: list[tuple[str, str]] = [
            ("Total runs", str(backtest_analytics["total_runs"])),
            (
                "Profitable runs",
                f"{backtest_analytics['profitable_runs']} "
                f"({backtest_analytics.get('success_rate', 0):.1f}%)",
            ),
            ("Avg return", f"{backtest_analytics.get('avg_return_pct', 0):.2f}%"),
        ]
        if best:
            bt_rows.append(
                ("Best strategy", f"{best['strategy']} ({best.get('return_pct', 0):.1f}% return)")
            )
        _pdf_two_col_table(pdf, bt_rows)

    # ── Improvement Suggestions ───────────────────────────────────────────────
    if suggestions:
        pdf.ln(4)
        _pdf_section_header(pdf, "Improvement Suggestions")
        for i, suggestion in enumerate(suggestions, 1):
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(8, 5, f"{i}.")
            pdf.set_font("Helvetica", "", 9)
            pdf.multi_cell(0, 5, _pdf_safe_text(suggestion))
            pdf.ln(1)

    # ── Charts ────────────────────────────────────────────────────────────────
    if chart_paths:
        pdf.add_page()
        _pdf_section_header(pdf, "Charts")
        for chart_path in chart_paths:
            if not chart_path.exists():
                continue
            try:
                pdf.ln(2)
                pdf.set_font("Helvetica", "I", 9)
                chart_caption = _pdf_safe_text(chart_path.stem.replace("_", " ").title())
                pdf.cell(0, 5, chart_caption, new_x="LMARGIN", new_y="NEXT")
                pdf.image(str(chart_path), w=180)
                pdf.ln(4)
            except Exception:
                logger.debug(f"Could not embed chart {chart_path.name} in PDF — skipping")

    # ── Footer ────────────────────────────────────────────────────────────────
    pdf.ln(2)
    pdf.set_font("Helvetica", "I", 8)
    pdf.cell(0, 5, _pdf_safe_text(f"Full report: {md_path}"), new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())


def generate_report(
    days: int = 30,
    output_dir: Path = Path("data/reports"),
    quiet: bool = False,
    send_telegram: bool = True,
) -> dict[str, Any]:
    """Run the full analytics pipeline and write output files.

    Fetches data from the encrypted database, computes metrics, generates
    charts (if matplotlib is available), prints a terminal report, and
    writes a ``report.md`` to *output_dir*.

    Args:
        days: Look-back window in calendar days for live-trading metrics.
        output_dir: Directory to write charts and the markdown report into.
        quiet: Suppress terminal output (useful in tests).
        send_telegram: Send notification via Telegram if configured (default: True).

    Returns:
        Dict containing all computed metrics, suggestions, and file paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    db = DatabasePersistence()
    (
        analytics,
        symbol_analytics,
        strategy_analytics,
        portfolio_series,
        backtest_analytics,
        backtest_runs,
        trade_history,
    ) = _fetch_report_data(db, days)
    metrics = _compute_report_metrics(analytics, portfolio_series, trade_history)
    suggestions = generate_suggestions(metrics, symbol_analytics, backtest_analytics)
    chart_paths = _generate_report_charts(
        output_dir, portfolio_series, trade_history, symbol_analytics, backtest_runs
    )
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
    asyncio.run(
        _send_telegram_report(
            send_telegram,
            days,
            metrics,
            md_path,
            symbol_analytics=symbol_analytics,
            strategy_analytics=strategy_analytics,
            backtest_analytics=backtest_analytics,
            suggestions=suggestions,
            chart_paths=chart_paths,
        )
    )
    if not quiet:
        _print_report(
            metrics, symbol_analytics, strategy_analytics, backtest_analytics, suggestions, days
        )
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


def _print_symbol_table(symbol_analytics: list[dict[str, Any]]) -> None:
    """Print per-symbol breakdown table."""
    if not symbol_analytics:
        return
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


def _print_strategy_table(strategy_analytics: list[dict[str, Any]]) -> None:
    """Print per-strategy breakdown table."""
    if not strategy_analytics:
        return
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


def _print_backtest_section(backtest_analytics: dict[str, Any]) -> None:
    """Print backtest summary block."""
    if not backtest_analytics or backtest_analytics.get("total_runs", 0) <= 0:
        return
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
            f"  Best strategy:         {best['strategy']} ({best.get('return_pct', 0):.1f}% return)"
        )
    print("-" * 62)


def _print_suggestions(suggestions: list[str], sep: str) -> None:
    """Print word-wrapped improvement suggestions."""
    print("\n  Improvement Suggestions")
    print("-" * 62)
    for i, suggestion in enumerate(suggestions, 1):
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


def _print_report(
    metrics: dict[str, Any],
    symbol_analytics: list[dict[str, Any]],
    strategy_analytics: list[dict[str, Any]],
    backtest_analytics: dict[str, Any],
    suggestions: list[str],
    days: int,
) -> None:
    """Print a structured terminal report."""

    def print_core_metrics(metrics, days):
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

    print_core_metrics(metrics, days)
    _print_symbol_table(symbol_analytics)
    _print_strategy_table(strategy_analytics)
    _print_backtest_section(backtest_analytics)
    sep = "=" * 62
    _print_suggestions(suggestions, sep)


# ---------------------------------------------------------------------------
# Markdown report builder
# ---------------------------------------------------------------------------


def _md_symbol_section(symbol_analytics: list[dict[str, Any]]) -> list[str]:
    """Return Markdown lines for the per-symbol breakdown section."""
    if not symbol_analytics:
        return []
    lines: list[str] = [
        "### Per-Symbol Breakdown",
        "",
        "| Symbol | Trades | Win Rate | Total P&L | Total Fees |",
        "|--------|--------|----------|-----------|------------|",
    ]
    lines.extend(
        [
            f"| {s['symbol']} | {s['total_trades']} | {s['win_rate']:.1f}% | "
            f"{_fmt_eur(s['total_pnl'])} | €{s['total_fees']:.2f} |"
            for s in symbol_analytics
        ]
    )
    lines.append("")
    return lines


def _md_strategy_section(strategy_analytics: list[dict[str, Any]]) -> list[str]:
    """Return Markdown lines for the per-strategy breakdown section."""
    if not strategy_analytics:
        return []
    lines: list[str] = [
        "### Per-Strategy Breakdown (Live Trades)",
        "",
        "| Strategy | Trades | Win Rate | Total P&L |",
        "|----------|--------|----------|-----------|",
    ]
    lines.extend(
        [
            f"| {s['strategy']} | {s['total_trades']} | {s['win_rate']:.1f}% | "
            f"{_fmt_eur(s['total_pnl'])} |"
            for s in strategy_analytics
        ]
    )
    lines.append("")
    return lines


def _md_backtest_section(backtest_analytics: dict[str, Any]) -> list[str]:
    """Return Markdown lines for the backtest summary section."""
    if not backtest_analytics or backtest_analytics.get("total_runs", 0) <= 0:
        return []
    best = backtest_analytics.get("best_run", {})
    lines: list[str] = [
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
    return lines


def _md_charts_section(chart_paths: list[Path]) -> list[str]:
    """Return Markdown lines for the charts section."""
    if not chart_paths:
        return []
    lines: list[str] = ["### Charts", ""]
    lines.extend([f"![{p.stem}]({p.name})" for p in chart_paths])
    lines.append("")
    return lines


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
        f"| Sharpe Ratio | {f'{sharpe:.3f}' if sharpe else 'N/A'} |",
        f"| Sortino Ratio | {f'{sortino:.3f}' if sortino else 'N/A'} |",
        f"| Profit Factor | {f'{profit_factor:.2f}' if profit_factor else 'N/A'} |",
        "",
    ]

    lines += _md_symbol_section(symbol_analytics)
    lines += _md_strategy_section(strategy_analytics)
    lines += _md_backtest_section(backtest_analytics)
    lines += ["### Improvement Suggestions", ""]
    for suggestion in suggestions:
        lines.append(f"- {suggestion}")
    lines.append("")
    lines += _md_charts_section(chart_paths)

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
