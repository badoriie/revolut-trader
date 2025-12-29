#!/usr/bin/env python3
"""
Backtesting CLI for Revolut Trader
Run strategies on historical data to validate performance
"""

import argparse
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

from loguru import logger

from src.api.client import RevolutAPIClient
from src.backtest.engine import BacktestEngine
from src.config import RiskLevel, StrategyType
from src.utils.db_persistence import DatabasePersistence


def setup_logging(log_level: str):
    """Configure logging for backtest."""
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level=log_level,
    )

    # File logging
    log_file = Path("./logs/backtest.log")
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_file,
        rotation="100 MB",
        retention="30 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        level=log_level,
    )


async def run_backtest(args):
    """Run backtest with specified configuration."""

    # Parse arguments
    strategy_type = StrategyType(args.strategy)
    risk_level = RiskLevel(args.risk)
    symbols = args.pairs.split(",") if args.pairs else ["BTC-USD", "ETH-USD"]
    initial_capital = Decimal(str(args.capital))

    # Initialize API client
    api_client = RevolutAPIClient()
    await api_client.initialize()

    # Create backtest engine
    engine = BacktestEngine(
        api_client=api_client,
        strategy_type=strategy_type,
        risk_level=risk_level,
        initial_capital=initial_capital,
    )

    try:
        # Run backtest
        results = await engine.run(
            symbols=symbols,
            days=args.days,
            interval=args.interval,
        )

        # Optionally save results
        if args.output:
            import json
            from datetime import UTC, datetime

            output_file = Path(args.output)

            # Convert trades with datetime objects to serializable format
            serializable_trades = []
            for trade in results.trades:
                trade_copy = trade.copy()
                if "timestamp" in trade_copy and isinstance(trade_copy["timestamp"], datetime):
                    trade_copy["timestamp"] = trade_copy["timestamp"].isoformat()
                serializable_trades.append(trade_copy)

            # Convert equity curve to serializable format
            equity_curve = [
                {"timestamp": ts.isoformat(), "equity": float(equity)}
                for ts, equity in results.equity_curve
            ]

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
            }

            output_data = {
                "timestamp": datetime.now(UTC).isoformat(),
                "config": {
                    "strategy": strategy_type.value,
                    "risk_level": risk_level.value,
                    "symbols": symbols,
                    "days": args.days,
                    "interval": args.interval,
                    "initial_capital": float(initial_capital),
                },
                "results": results_dict,
                "trades": serializable_trades,
                "equity_curve": equity_curve,
            }

            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, "w") as f:
                json.dump(output_data, f, indent=2)

            logger.info(f"Results saved to {output_file}")

            # Also save to database for analytics
            db = DatabasePersistence()
            run_id = db.save_backtest_run(
                strategy=strategy_type.value,
                risk_level=risk_level.value,
                symbols=symbols,
                days=args.days,
                interval=args.interval,
                initial_capital=float(initial_capital),
                results=results_dict,
                equity_curve_file=str(output_file),
                trades_file=str(output_file),
            )
            logger.info(f"Backtest run saved to database: ID={run_id}")

    finally:
        await api_client.close()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Backtest trading strategies on historical data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Backtest market making strategy on BTC-USD for 30 days
  python backtest.py --strategy market_making --pairs BTC-USD --days 30

  # Test momentum strategy with moderate risk on multiple pairs
  python backtest.py --strategy momentum --risk moderate --pairs BTC-USD,ETH-USD,SOL-USD --days 60

  # Run with 1-hour candles and save results
  python backtest.py --strategy mean_reversion --interval 60 --days 90 --output ./results/backtest.json

  # Test with custom initial capital
  python backtest.py --strategy multi_strategy --capital 50000 --days 180
        """,
    )

    parser.add_argument(
        "--strategy",
        "-s",
        type=str,
        choices=["market_making", "momentum", "mean_reversion", "multi_strategy"],
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
        default="BTC-USD,ETH-USD",
        help="Comma-separated trading pairs (default: BTC-USD,ETH-USD)",
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
        help="Candle interval in minutes (default: 60). Options: 5, 15, 30, 60, 240, 1440",
    )

    parser.add_argument(
        "--capital",
        "-c",
        type=float,
        default=10000.0,
        help="Initial capital in USD (default: 10000)",
    )

    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="Save results to JSON file (optional)",
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

    # Setup logging
    setup_logging(args.log_level)

    # Run backtest
    try:
        asyncio.run(run_backtest(args))
    except KeyboardInterrupt:
        logger.info("Backtest interrupted by user")
    except Exception as e:
        logger.error(f"Backtest failed: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
