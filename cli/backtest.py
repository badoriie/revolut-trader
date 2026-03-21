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

from src.api.client import RevolutAPIClient
from src.backtest.engine import BacktestEngine
from src.config import RiskLevel, StrategyType
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
    strategy_type = StrategyType(args.strategy)
    risk_level = RiskLevel(args.risk)
    symbols = args.pairs.split(",") if args.pairs else ["BTC-EUR", "ETH-EUR"]
    initial_capital = Decimal(str(args.capital))

    api_client = RevolutAPIClient()
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
            days=args.days,
            interval=args.interval,
        )

        results.print_summary()

        # Persist to encrypted database
        results_dict = {
            "final_capital": float(results.final_capital),
            "total_pnl": float(results.total_pnl),
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
            days=args.days,
            interval=args.interval,
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
        default="market_making",
        help="Trading strategy to backtest (default: market_making)",
    )
    parser.add_argument(
        "--risk",
        "-r",
        type=str,
        choices=["conservative", "moderate", "aggressive"],
        default="conservative",
        help="Risk management level (default: conservative)",
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
        help="Number of days of historical data (default: 30)",
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
        default="INFO",
        help="Logging level (default: INFO)",
    )

    args = parser.parse_args()
    setup_logging(args.log_level)

    try:
        asyncio.run(run_backtest(args))
    except KeyboardInterrupt:
        logger.info("Backtest interrupted by user")
    except Exception as e:
        logger.error(f"Backtest failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
