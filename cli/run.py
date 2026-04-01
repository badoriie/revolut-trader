#!/usr/bin/env python3
"""
Revolut Trader: Professional Algorithmic Trading Bot for Revolut Crypto
"""

import argparse
import asyncio
import os
import sys

from loguru import logger


def setup_logging(log_level: str) -> None:
    """Configure console-only logging (no plaintext log files)."""
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level=log_level,
    )


async def run_bot(args):
    """Run the trading bot with specified configuration."""
    # Deferred imports so ENVIRONMENT is set before Settings() singleton runs.
    from src.bot import TradingBot
    from src.config import RiskLevel, StrategyType, settings

    # CLI flags override 1Password settings; fall back to 1Password values when not given.
    effective_log_level = args.log_level or settings.log_level
    setup_logging(effective_log_level)

    strategy_type = StrategyType(args.strategy or settings.default_strategy.value)
    risk_level = RiskLevel(args.risk or settings.risk_level.value)
    trading_pairs = args.pairs.split(",") if args.pairs else None
    effective_interval = args.interval if args.interval is not None else settings.interval

    env = os.environ.get("ENVIRONMENT", "?")
    logger.info("=" * 60)
    logger.info("REVOLUT TRADER - Algorithmic Trading Bot")
    logger.info("=" * 60)
    logger.info(f"Environment: {env}")
    logger.info(f"Strategy: {strategy_type.value}")
    logger.info(f"Risk Level: {risk_level.value}")
    logger.info(f"Trading Mode: {settings.trading_mode.value} (derived from environment)")
    interval_label = (
        f"{effective_interval}s" if effective_interval is not None else "strategy-dependent"
    )
    logger.info(f"Interval: {interval_label}")
    logger.info("=" * 60)

    # Initialize bot
    bot = TradingBot(
        strategy_type=strategy_type,
        risk_level=risk_level,
        trading_pairs=trading_pairs,
    )

    try:
        await bot.start()
        await bot.run_trading_loop(interval=effective_interval)
    except KeyboardInterrupt:
        logger.info("\n👋 Shutting down gracefully...")
    except Exception as e:
        logger.error(f"Fatal error: {e!s}", exc_info=True)
    finally:
        await bot.stop()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Professional Algorithmic Trading Bot for Revolut Crypto",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run in dev environment (mock API, paper mode)
  python run.py --env dev --strategy market_making

  # Run in int environment (real API, paper mode — staging ground)
  python run.py --env int --strategy momentum

  # Run in prod environment (live trading — real money)
  python run.py --env prod --strategy momentum --risk moderate

  # Run multi-strategy with custom pairs
  python run.py --env dev --strategy multi_strategy --pairs BTC-EUR,ETH-EUR,SOL-EUR

  # Override interval (strategy-dependent by default; market_making=5s, momentum=10s, mean_reversion=15s)
  python run.py --env dev --strategy momentum --interval 30

Trading mode is derived from environment:
  dev/int → paper (simulated)
  prod    → live  (real money)
        """,
    )

    parser.add_argument(
        "--env",
        "-e",
        type=str,
        choices=["dev", "int", "prod"],
        default=None,
        help="Environment (dev, int, prod). Overrides ENVIRONMENT env var.",
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
        help="Trading strategy to use (default: DEFAULT_STRATEGY from 1Password config)",
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
        help="Comma-separated trading pairs (default: BTC-USD,ETH-USD)",
    )

    parser.add_argument(
        "--interval",
        "-i",
        type=int,
        default=None,
        help=(
            "Trading loop interval in seconds. "
            "Omit to use the strategy-dependent default "
            "(market_making/breakout=5s, momentum/multi_strategy=10s, "
            "mean_reversion/range_reversion=15s)."
        ),
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

    # Set ENVIRONMENT early — before any import of src.config (which creates
    # the Settings singleton).  CLI --env takes priority over the env var.
    if args.env:
        os.environ["ENVIRONMENT"] = args.env
    elif "ENVIRONMENT" not in os.environ:
        logger.error("ENVIRONMENT not set. Use --env or export ENVIRONMENT=dev|int|prod")
        sys.exit(1)

    # Bootstrap logging at INFO; run_bot reconfigures once settings are loaded.
    setup_logging(args.log_level or "INFO")

    env = os.environ["ENVIRONMENT"]
    logger.info(f"Environment: {env}")

    # Safety confirmation for prod (live trading)
    if env == "prod":
        logger.warning("⚠️  LIVE TRADING MODE - PRODUCTION - REAL MONEY AT RISK ⚠️")
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
        logger.error(f"Failed to start bot: {e!s}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
