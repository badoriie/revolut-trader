#!/usr/bin/env python3
"""Compare all trading strategies in a single backtest run.

Runs each strategy against the same historical data and prints a side-by-side
analytics table so you can quickly see which strategies perform best under the
given conditions.

Usage:
    make backtest-compare                         # defaults: 30d, 60min, BTC-EUR,ETH-EUR
    make backtest-compare DAYS=90 PAIRS=BTC-EUR   # custom parameters
    make backtest-compare RISK=aggressive          # single risk level
    make backtest-matrix                           # all strategies × all risk levels

Results are persisted to the encrypted database for each run.
Use ``make db-backtests`` to view stored results.
"""

import argparse
import asyncio
import sys
from decimal import Decimal
from typing import Any

from loguru import logger

from src.api import create_api_client
from src.backtest.engine import BacktestEngine, BacktestResults
from src.config import RiskLevel, StrategyType, settings
from src.utils.db_persistence import DatabasePersistence

ALL_STRATEGIES: list[str] = [s.value for s in StrategyType]

ALL_RISK_LEVELS: list[str] = [r.value for r in RiskLevel]


def setup_logging(log_level: str) -> None:
    """Configure console-only logging (no plaintext log files)."""
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level=log_level,
    )


def _persist_result(
    db: DatabasePersistence,
    strategy: str,
    risk_level: str,
    symbols: list[str],
    days: int,
    interval: int,
    initial_capital: Decimal,
    results: BacktestResults,
) -> int:
    """Save a single backtest run to the encrypted database.

    Args:
        db: Database persistence instance.
        strategy: Strategy name used for the run.
        risk_level: Risk level label.
        symbols: Traded symbol list.
        days: Historical look-back in days.
        interval: Candle width in minutes.
        initial_capital: Starting capital.
        results: Completed backtest results.

    Returns:
        Database primary key of the saved run.
    """
    results_dict: dict[str, Any] = {
        "final_capital": float(results.final_capital),
        "total_pnl": float(results.total_pnl),
        "total_fees": float(results.total_fees),
        "return_pct": results.return_pct,
        "total_trades": results.total_trades,
        "winning_trades": results.winning_trades,
        "losing_trades": results.losing_trades,
        "win_rate": results.win_rate,
        "profit_factor": results.profit_factor,
        "max_drawdown": float(results.max_drawdown),
        "sharpe_ratio": results.sharpe_ratio,
    }
    return db.save_backtest_run(
        strategy=strategy,
        risk_level=risk_level,
        symbols=symbols,
        days=days,
        interval=str(interval),
        initial_capital=initial_capital,
        results=results_dict,
    )


# ---------------------------------------------------------------------------
# Pretty-printing
# ---------------------------------------------------------------------------


def _print_comparison_table(
    rows: list[dict[str, Any]],
    currency_symbol: str = "€",
) -> None:
    """Print a side-by-side strategy comparison table to stdout.

    Args:
        rows: List of dicts, one per strategy run.
        currency_symbol: Display symbol for the base currency.
    """
    if not rows:
        print("No results to display.")
        return

    sym = currency_symbol

    # Sort by return_pct descending (best first)
    rows = sorted(rows, key=lambda r: r["return_pct"], reverse=True)

    # Header
    print("\n" + "=" * 130)
    print("STRATEGY COMPARISON")
    print("=" * 130)
    header = (
        f"{'#':<3} {'Strategy':<18} {'Risk':<14} {'Return %':>9} "
        f"{'Gross P&L':>12} {'Fees':>10} {'Net P&L':>12} "
        f"{'Trades':>7} {'Win%':>7} {'PF':>6} "
        f"{'MaxDD':>10} {'Sharpe':>7}"
    )
    print(header)
    print("-" * 130)

    for i, r in enumerate(rows, 1):
        return_pct = r["return_pct"]
        net_pnl = r["total_pnl"]
        fees = r["total_fees"]
        gross_pnl = net_pnl + fees
        pf = r["profit_factor"]
        pf_str = f"{pf:.2f}" if pf != float("inf") else "inf"

        ret_str = f"{return_pct:+.2f}%"
        gross_str = f"{'+' if gross_pnl >= 0 else '-'}{sym}{abs(gross_pnl):,.2f}"
        fees_str = f"-{sym}{fees:,.2f}"
        net_str = f"{'+' if net_pnl >= 0 else '-'}{sym}{abs(net_pnl):,.2f}"

        line = (
            f"{i:<3} {r['strategy']:<18} {r['risk_level']:<14} "
            f"{ret_str:>9} "
            f"{gross_str:>12} "
            f"{fees_str:>10} "
            f"{net_str:>12} "
            f"{r['total_trades']:>7} "
            f"{r['win_rate']:>6.1f}% "
            f"{pf_str:>6} "
            f"{sym}{r['max_drawdown']:>9,.2f} "
            f"{r['sharpe_ratio']:>7.2f}"
        )
        print(line)

    print("=" * 130)

    # Summary
    best = rows[0]
    worst = rows[-1]
    print(f"\nBest:  {best['strategy']} ({best['risk_level']}) → {best['return_pct']:+.2f}%")
    print(f"Worst: {worst['strategy']} ({worst['risk_level']}) → {worst['return_pct']:+.2f}%")

    # Averages
    avg_return = sum(r["return_pct"] for r in rows) / len(rows)
    avg_win_rate = sum(r["win_rate"] for r in rows) / len(rows)
    avg_sharpe = sum(r["sharpe_ratio"] for r in rows) / len(rows)
    print(
        f"Avg return: {avg_return:+.2f}%  |  Avg win rate: {avg_win_rate:.1f}%  |  Avg Sharpe: {avg_sharpe:.2f}"
    )
    print()


# ---------------------------------------------------------------------------
# Runners
# ---------------------------------------------------------------------------


async def run_compare(args) -> None:
    """Run all selected strategies against the same data and compare results.

    Args:
        args: Parsed CLI arguments.
    """
    strategies = args.strategies.split(",") if args.strategies else ALL_STRATEGIES
    risk_levels = args.risk_levels.split(",") if args.risk_levels else [args.risk]
    symbols = args.pairs.split(",") if args.pairs else ["BTC-EUR", "ETH-EUR"]
    initial_capital = Decimal(str(args.capital))

    api_client = create_api_client(settings.environment)
    await api_client.initialize()
    db = DatabasePersistence()

    comparison_rows: list[dict[str, Any]] = []

    try:
        total_runs = len(strategies) * len(risk_levels)
        current_run = 0

        for risk_level_str in risk_levels:
            risk_level = RiskLevel(risk_level_str)

            for strategy_str in strategies:
                current_run += 1
                strategy_type = StrategyType(strategy_str)

                print(f"\n{'─' * 60}")
                print(f"[{current_run}/{total_runs}] {strategy_str} @ {risk_level_str}")
                print(f"{'─' * 60}")

                engine = BacktestEngine(
                    api_client=api_client,
                    strategy_type=strategy_type,
                    risk_level=risk_level,
                    initial_capital=initial_capital,
                )

                results = await engine.run(
                    symbols=symbols,
                    days=args.days,
                    interval=args.interval,
                )

                # Persist to DB
                run_id = _persist_result(
                    db=db,
                    strategy=strategy_str,
                    risk_level=risk_level_str,
                    symbols=symbols,
                    days=args.days,
                    interval=args.interval,
                    initial_capital=initial_capital,
                    results=results,
                )

                comparison_rows.append(
                    {
                        "strategy": strategy_str,
                        "risk_level": risk_level_str,
                        "return_pct": results.return_pct,
                        "total_pnl": float(results.total_pnl),
                        "total_fees": float(results.total_fees),
                        "total_trades": results.total_trades,
                        "winning_trades": results.winning_trades,
                        "losing_trades": results.losing_trades,
                        "win_rate": results.win_rate,
                        "profit_factor": results.profit_factor,
                        "max_drawdown": float(results.max_drawdown),
                        "sharpe_ratio": results.sharpe_ratio,
                        "db_id": run_id,
                    }
                )

        _print_comparison_table(comparison_rows)

        logger.info(
            f"All {total_runs} backtest runs saved to database. View with: make db-backtests"
        )

    finally:
        await api_client.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """Main CLI entry point for strategy comparison backtests."""
    parser = argparse.ArgumentParser(
        description="Compare trading strategies via backtest",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  make backtest-compare                              # all strategies, conservative risk
  make backtest-compare DAYS=90 PAIRS=BTC-EUR        # custom parameters
  make backtest-compare RISK=aggressive              # single risk level
  make backtest-matrix                               # all strategies × all risk levels
        """,
    )

    parser.add_argument(
        "--strategies",
        type=str,
        default=None,
        help=(f"Comma-separated strategies to compare (default: all — {','.join(ALL_STRATEGIES)})"),
    )
    parser.add_argument(
        "--risk",
        "-r",
        type=str,
        choices=ALL_RISK_LEVELS,
        default="conservative",
        help="Risk level for all runs (default: conservative). Use --risk-levels to test multiple.",
    )
    parser.add_argument(
        "--risk-levels",
        type=str,
        default=None,
        help=(
            "Comma-separated risk levels to compare "
            f"(e.g. '{','.join(ALL_RISK_LEVELS)}'). "
            "Overrides --risk."
        ),
    )
    parser.add_argument(
        "--pairs",
        "-p",
        type=str,
        default="BTC-EUR,ETH-EUR",
        help="Comma-separated trading pairs (default: BTC-EUR,ETH-EUR)",
    )
    parser.add_argument(
        "--days",
        "-d",
        type=int,
        default=30,
        help="Days of historical data (default: 30)",
    )
    parser.add_argument(
        "--interval",
        "-i",
        type=int,
        default=60,
        choices=[5, 15, 30, 60, 240, 1440],
        help="Candle interval in minutes (default: 60)",
    )
    parser.add_argument(
        "--capital",
        "-c",
        type=float,
        default=10000.0,
        help="Initial capital in EUR (default: 10000)",
    )
    parser.add_argument(
        "--log-level",
        "-l",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="WARNING",
        help="Logging level (default: WARNING to keep output clean)",
    )

    args = parser.parse_args()
    setup_logging(args.log_level)

    try:
        asyncio.run(run_compare(args))
    except KeyboardInterrupt:
        logger.info("Comparison interrupted by user")
    except Exception as e:
        logger.error(f"Comparison failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
