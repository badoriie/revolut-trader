#!/usr/bin/env python3
"""Backtesting CLI for Revolut Trader.

Results are persisted exclusively to the encrypted SQLite database.
Use ``make db-backtests`` to view results and ``make db-export-csv`` to export.
"""

import argparse
import asyncio
import sys
from decimal import Decimal

from loguru import logger

from cli.env_detect import set_env as _set_env

_set_env()

from src.api import create_api_client
from src.backtest.engine import BacktestEngine
from src.config import RiskLevel, StrategyType, settings
from src.utils.db_persistence import DatabasePersistence


def setup_logging(log_level: str) -> None:
    """Configure console-only logging (no plaintext log files)."""
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level=log_level,
    )


async def run_backtest(args) -> None:
    """Run backtest with specified configuration."""
    # CLI flags override 1Password settings; fall back to 1Password values when not given.
    strategy_type = StrategyType(args.strategy or settings.default_strategy.value)
    risk_level = RiskLevel(args.risk or settings.risk_level.value)
    raw_pairs = args.pairs if args.pairs else ",".join(settings.trading_pairs)
    symbols = raw_pairs.split(",")
    initial_capital = Decimal(
        str(args.capital if args.capital is not None else settings.paper_initial_capital)
    )
    effective_days = args.days if args.days is not None else settings.backtest_days
    effective_interval = args.interval if args.interval is not None else settings.backtest_interval

    api_client = create_api_client(settings.environment)
    await api_client.initialize()

    engine = BacktestEngine(
        api_client=api_client,
        strategy_type=strategy_type,
        risk_level=risk_level,
        initial_capital=initial_capital,
    )

    try:
        results = await engine.run(
            symbols=symbols,
            days=effective_days,
            interval=effective_interval,
        )

        results.print_summary()

        # Persist to encrypted database
        results_dict = {
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

        db = DatabasePersistence()
        run_id = db.save_backtest_run(
            strategy=strategy_type.value,
            risk_level=risk_level.value,
            symbols=symbols,
            days=effective_days,
            interval=str(effective_interval),
            initial_capital=initial_capital,
            results=results_dict,
        )
        logger.info(f"Backtest saved to database (ID={run_id}). View with: make db-backtests")

    finally:
        await api_client.close()


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Backtest trading strategies on historical data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  make backtest STRATEGY=momentum DAYS=30
  make backtest STRATEGY=mean_reversion PAIRS=BTC-EUR,ETH-EUR DAYS=60
  make db-backtests          # view stored results
  make db-export-csv         # export to CSV
        """,
    )

    parser.add_argument(
        "--strategy",
        "-s",
        type=str,
        choices=[
            "market_making",
            "momentum",
            "mean_reversion",
            "multi_strategy",
            "breakout",
            "range_reversion",
        ],
        default=None,
        help="Trading strategy to backtest (default: DEFAULT_STRATEGY from 1Password config)",
    )
    parser.add_argument(
        "--risk",
        "-r",
        type=str,
        choices=["conservative", "moderate", "aggressive"],
        default=None,
        help="Risk management level (default: RISK_LEVEL from 1Password config)",
    )
    parser.add_argument(
        "--pairs",
        "-p",
        type=str,
        default=None,
        help="Comma-separated trading pairs (default: TRADING_PAIRS from 1Password config)",
    )
    parser.add_argument(
        "--days",
        "-d",
        type=int,
        default=None,
        help="Number of days of historical data (default: BACKTEST_DAYS from 1Password config, or 30)",
    )
    parser.add_argument(
        "--interval",
        "-i",
        type=int,
        default=None,
        choices=[1, 5, 15, 30, 60, 240, 1440, 2880, 5760, 10080, 20160, 40320],
        help="Candle interval in minutes (default: BACKTEST_INTERVAL from 1Password config, or 60)",
    )
    parser.add_argument(
        "--capital",
        "-c",
        type=float,
        default=None,
        help="Initial capital in EUR (default: INITIAL_CAPITAL from 1Password config)",
    )
    parser.add_argument(
        "--log-level",
        "-l",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="Logging level (default: LOG_LEVEL from 1Password config, or INFO)",
    )

    args = parser.parse_args()
    setup_logging(args.log_level or settings.log_level)

    try:
        asyncio.run(run_backtest(args))
    except KeyboardInterrupt:
        logger.info("Backtest interrupted by user")
    except Exception as e:
        logger.error(f"Backtest failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
