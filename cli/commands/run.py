#!/usr/bin/env python3
"""
Revolut Trader: Professional Algorithmic Trading Bot for Revolut Crypto
"""

import argparse
import asyncio
import os
import sys

from loguru import logger

from cli.utils.env_detect import detect_env as _detect_env


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
    logger.info(f"Trading Mode: {settings.trading_mode.value}")
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
Environment is auto-detected from git branch (no override):
  feature branch → dev  (mock API, paper mode)
  main branch    → int  (real API, paper mode)
  tagged commit  → prod (real API, paper by default)
  frozen binary  → prod

Examples:
  # On a feature branch (auto: dev, mock API, paper mode)
  python run.py --strategy market_making

  # On main branch (auto: int, real API, paper mode)
  python run.py --strategy momentum

  # On a tagged commit (auto: prod, paper by default)
  python run.py --strategy momentum --risk moderate

  # Override interval (strategy-dependent by default)
  python run.py --strategy momentum --interval 30

Trading mode: paper by default in all environments.
  Live trading requires TRADING_MODE=live in 1Password and is only
  permitted in prod (tagged commit or frozen binary).
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

    # Detect environment from git branch/tag or frozen binary.
    # ENVIRONMENT must be set before src.config is imported (Settings singleton).
    if "ENVIRONMENT" not in os.environ:
        os.environ["ENVIRONMENT"] = _detect_env()

    # Bootstrap logging at INFO; run_bot reconfigures once settings are loaded.
    setup_logging(args.log_level or "INFO")

    env = os.environ["ENVIRONMENT"]
    logger.info(f"Environment: {env}")

    # Import settings now that ENVIRONMENT is set.
    # Check actual trading mode — paper is the default everywhere; live is prod-only.
    from src.config import TradingMode, settings

    if settings.trading_mode == TradingMode.LIVE:
        warning = settings.get_mode_warning()
        if warning:
            logger.warning(warning)
        try:
            response = input("Type 'I UNDERSTAND' to continue with live trading: ").strip()
        except (KeyboardInterrupt, EOFError):
            logger.info("Aborting.")
            sys.exit(0)
        if response != "I UNDERSTAND":
            logger.info("Aborting.")
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
