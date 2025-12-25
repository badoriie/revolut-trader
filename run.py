#!/usr/bin/env python3
"""
Revolut Trader: Professional Algorithmic Trading Bot for Revolut Crypto
"""
import argparse
import asyncio
import sys
from pathlib import Path

from loguru import logger

from src.bot import TradingBot
from src.config import RiskLevel, StrategyType, TradingMode


def setup_logging(log_level: str, log_file: Path):
    """Configure logging."""
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level=log_level,
    )

    # File logging
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_file,
        rotation="500 MB",
        retention="10 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        level=log_level,
    )


async def run_bot(args):
    """Run the trading bot with specified configuration."""

    # Parse arguments
    strategy_type = StrategyType(args.strategy)
    risk_level = RiskLevel(args.risk)
    trading_mode = TradingMode(args.mode)
    trading_pairs = args.pairs.split(",") if args.pairs else None

    logger.info("=" * 60)
    logger.info("REVOLUT TRADER - Algorithmic Trading Bot")
    logger.info("=" * 60)
    logger.info(f"Strategy: {strategy_type.value}")
    logger.info(f"Risk Level: {risk_level.value}")
    logger.info(f"Trading Mode: {trading_mode.value}")
    logger.info(f"Interval: {args.interval}s")
    logger.info("=" * 60)

    # Initialize bot
    bot = TradingBot(
        strategy_type=strategy_type,
        risk_level=risk_level,
        trading_mode=trading_mode,
        trading_pairs=trading_pairs,
    )

    try:
        await bot.start()
        await bot.run_trading_loop(interval=args.interval)
    except KeyboardInterrupt:
        logger.info("\n👋 Shutting down gracefully...")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
    finally:
        await bot.stop()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Professional Algorithmic Trading Bot for Revolut Crypto",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with market making strategy in paper mode (safe for testing)
  python run.py --strategy market_making --mode paper

  # Run with momentum strategy, moderate risk, live trading
  python run.py --strategy momentum --risk moderate --mode live

  # Run multi-strategy with custom pairs
  python run.py --strategy multi_strategy --pairs BTC-USD,ETH-USD,SOL-USD

  # Run with faster update interval (30 seconds)
  python run.py --strategy momentum --interval 30
        """,
    )

    parser.add_argument(
        "--strategy",
        "-s",
        type=str,
        choices=["market_making", "momentum", "mean_reversion", "multi_strategy"],
        default="market_making",
        help="Trading strategy to use (default: market_making)",
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
        "--mode",
        "-m",
        type=str,
        choices=["paper", "live"],
        default="paper",
        help="Trading mode: paper (simulated) or live (real money) (default: paper)",
    )

    parser.add_argument(
        "--pairs",
        "-p",
        type=str,
        help="Comma-separated trading pairs (default: from .env)",
    )

    parser.add_argument(
        "--interval",
        "-i",
        type=int,
        default=60,
        help="Trading loop interval in seconds (default: 60)",
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
    setup_logging(args.log_level, Path("./logs/trading.log"))

    # Warn if using live mode
    if args.mode == "live":
        logger.warning("⚠️  LIVE TRADING MODE - REAL MONEY AT RISK ⚠️")
        response = input("Are you sure you want to trade with real money? (yes/no): ")
        if response.lower() != "yes":
            logger.info("Aborting live trading")
            sys.exit(0)

    # Run the bot
    try:
        asyncio.run(run_bot(args))
    except KeyboardInterrupt:
        logger.info("Goodbye! 👋")
    except Exception as e:
        logger.error(f"Failed to start bot: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
