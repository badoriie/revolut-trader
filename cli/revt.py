#!/usr/bin/env python3
"""revt — Revolut Trader CLI.

The polished, user-facing entry point replacing all non-development make targets.
Environment is auto-detected from the git branch (mirrors Makefile logic) and can
always be overridden with ``--env``.

Usage
-----
    revt run                   Start the trading bot
    revt backtest              Run backtests  (--hf · --compare · --matrix)
    revt ops                   Manage API credentials in 1Password
    revt config                View / update trading configuration
    revt api <endpoint>        Call Revolut X API endpoints
    revt db  <subcommand>      Database management and analytics
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_OP_VAULT = "revolut-trader"
_CANCELLED = "\nCancelled."
_DAYS_HELP = "Look-back days (default: 30)"


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------


def _detect_env() -> str:
    """Determine the default environment.

    * Frozen binary (release build via PyInstaller) → always ``prod``.
      End users download the binary to trade with real money; ``prod`` is the
      only meaningful default.
    * Running from source → mirror Makefile logic: tagged commit → ``prod``,
      ``main`` branch → ``int``, any other branch → ``dev``.
    """
    # PyInstaller sets sys.frozen when running as a packaged binary
    if getattr(sys, "frozen", False):
        return "prod"

    try:
        tag = subprocess.run(
            ["git", "describe", "--exact-match", "HEAD"],
            capture_output=True,
            text=True,
            cwd=_ROOT,
            timeout=5,
        )
        if tag.returncode == 0:
            return "prod"
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=_ROOT,
            timeout=5,
        )
        return "int" if branch.stdout.strip() == "main" else "dev"
    except Exception:
        return "prod"  # safe fallback outside a git repo


def _resolve_env(args: argparse.Namespace) -> str:
    """Pick environment from ``--env`` flag or auto-detect, then export it.

    ENVIRONMENT must be set before any ``src.config`` import because the
    Settings singleton is created at import time.
    """
    env = getattr(args, "env", None) or _detect_env()
    os.environ["ENVIRONMENT"] = env
    return env


def _env_badge(env: str) -> str:
    """Return a human-readable label for the given environment."""
    labels = {
        "dev": "dev  (mock API · paper mode)",
        "int": "int  (real API · paper mode)",
        "prod": "prod (real API · LIVE mode — REAL MONEY)",
    }
    return labels.get(env, env)


# ---------------------------------------------------------------------------
# 1Password helpers
# ---------------------------------------------------------------------------


def _op_creds_item(env: str) -> str:
    """Return the 1Password credentials item name for the given environment."""
    return f"revolut-trader-credentials-{env}"


def _op_config_item(env: str) -> str:
    """Return the 1Password config item name for the given environment."""
    return f"revolut-trader-config-{env}"


def _check_op() -> bool:
    """Return True if the 1Password CLI is installed and authenticated."""
    r = subprocess.run(["op", "whoami"], capture_output=True, timeout=10)
    if r.returncode != 0:
        print("❌  1Password not authenticated.")
        print("    Set OP_SERVICE_ACCOUNT_TOKEN, or run: op signin")
        return False
    return True


def _op(*args: str) -> subprocess.CompletedProcess[str]:
    """Run an ``op`` CLI command and return the completed process."""
    return subprocess.run(["op", *args], capture_output=True, text=True, timeout=15)


# ---------------------------------------------------------------------------
# cmd: run
# ---------------------------------------------------------------------------


def cmd_run(args: argparse.Namespace) -> None:
    """Start the trading bot.

    Sets ENVIRONMENT early (before any ``src.config`` import) then delegates to
    ``cli.run.run_bot`` via a compatible argument namespace.
    """
    env = _resolve_env(args)

    print(f"\n  Environment : {_env_badge(env)}")
    print(f"  Strategy    : {args.strategy}")
    print(f"  Risk level  : {args.risk}")
    print()

    if env == "prod":
        print("⚠️   LIVE TRADING — REAL MONEY AT RISK  ⚠️")
        print()
        try:
            confirm = input("Type 'I UNDERSTAND' to continue: ").strip()
        except (KeyboardInterrupt, EOFError):
            print(_CANCELLED)
            sys.exit(0)
        if confirm != "I UNDERSTAND":
            print("Cancelled.")
            sys.exit(0)
        print()

    from loguru import logger

    logger.remove()
    logger.add(
        sys.stderr,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<level>{message}</level>"
        ),
        level=args.log_level,
    )

    # Deferred import — ENVIRONMENT must be set before src.config is loaded.
    from cli.run import run_bot

    class _RunArgs:
        strategy = args.strategy
        risk = args.risk
        pairs = args.pairs
        interval = args.interval
        log_level = args.log_level

    try:
        asyncio.run(run_bot(_RunArgs()))
    except KeyboardInterrupt:
        print("\n👋  Shutdown complete.")


# ---------------------------------------------------------------------------
# cmd: backtest
# ---------------------------------------------------------------------------


def cmd_backtest(args: argparse.Namespace) -> None:
    """Run a backtest — single strategy, high-frequency, compare, or matrix.

    Sets ENVIRONMENT then delegates to the appropriate backtest CLI function.
    """
    _resolve_env(args)

    from loguru import logger

    logger.remove()
    logger.add(sys.stderr, level=args.log_level)

    if args.matrix:
        print("\n  STRATEGY × RISK LEVEL MATRIX BACKTEST\n")
        _run_compare_cli(
            days=args.days,
            interval=args.interval,
            pairs=args.pairs,
            capital=args.capital,
            risk=None,
            risk_levels="conservative,moderate,aggressive",
            strategies=None,
            log_level=args.log_level,
        )
    elif args.compare:
        _run_compare_cli(
            days=args.days,
            interval=args.interval,
            pairs=args.pairs,
            capital=args.capital,
            risk=args.risk,
            risk_levels=None,
            strategies=getattr(args, "strategies", None),
            log_level=args.log_level,
        )
    elif args.hf:
        print("\n  HIGH-FREQUENCY BACKTEST (1-minute candles)")
        print("  Note: live bot polls every 5s; 1-min is the highest API granularity.\n")
        _backtest_single(args, interval_override=1)
    else:
        _backtest_single(args)


def _backtest_single(
    args: argparse.Namespace,
    interval_override: int | None = None,
) -> None:
    """Run a single-strategy backtest by calling ``cli.backtest.run_backtest``."""
    from cli.backtest import run_backtest

    class _BArgs:
        strategy = args.strategy
        risk = args.risk
        pairs = args.pairs
        days = args.days
        interval = interval_override if interval_override is not None else args.interval
        capital = args.capital
        log_level = args.log_level

    try:
        asyncio.run(run_backtest(_BArgs()))
    except KeyboardInterrupt:
        print("\nBacktest interrupted.")


def _run_compare_cli(
    *,
    days: int,
    interval: int,
    pairs: str,
    capital: float,
    risk: str | None,
    risk_levels: str | None,
    strategies: str | None,
    log_level: str,
) -> None:
    """Invoke ``backtest_compare.main()`` by patching sys.argv."""
    from cli.backtest_compare import main as _compare_main

    argv = [
        "backtest_compare",
        "--days",
        str(days),
        "--interval",
        str(interval),
        "--pairs",
        pairs,
        "--capital",
        str(capital),
        "--log-level",
        log_level,
    ]
    if risk_levels:
        argv += ["--risk-levels", risk_levels]
    elif risk:
        argv += ["--risk", risk]
    if strategies:
        argv += ["--strategies", strategies]

    old_argv, sys.argv = sys.argv, argv
    try:
        _compare_main()
    finally:
        sys.argv = old_argv


# ---------------------------------------------------------------------------
# cmd: ops
# ---------------------------------------------------------------------------


def cmd_ops(args: argparse.Namespace) -> None:
    """Manage Revolut X API credentials stored in 1Password."""
    env = getattr(args, "env", None) or _detect_env()

    if args.status:
        _ops_status(env)
    elif args.show:
        _ops_show(env)
    else:
        _ops_set_creds(env)


def _ops_status(env: str) -> None:
    """Print 1Password CLI and vault/item status for the given environment."""
    print("=== 1Password Status ===\n")

    r = _op("--version")
    if r.returncode == 0:
        print(f"  CLI              {r.stdout.strip()}")
    else:
        print("  CLI              not installed  (brew install --cask 1password-cli)")
        return

    r = _op("whoami")
    if r.returncode != 0:
        print("  Authenticated    no  (set OP_SERVICE_ACCOUNT_TOKEN)")
        return
    print("  Authenticated    yes")

    r = _op("vault", "get", _OP_VAULT)
    print(
        f"  Vault            {_OP_VAULT} ({'✓' if r.returncode == 0 else '✗  missing — run: make setup'})"
    )

    for item in (_op_creds_item(env), _op_config_item(env)):
        r = _op("item", "get", item, "--vault", _OP_VAULT)
        print(f"  {item:<42} {'✓' if r.returncode == 0 else '✗  missing'}")


def _mask_secret(val: str) -> str:
    """Return a display-safe masked representation of a secret field value."""
    if len(val) > 100:
        return f"<set, {len(val)} chars>"
    if len(val) > 8:
        return val[:8] + "..."
    if val:
        return val[:4] + "..."
    return "(empty)"


def _ops_show(env: str) -> None:
    """Print stored credentials and configuration (secrets masked)."""
    if not _check_op():
        sys.exit(1)

    print(f"\n=== Credentials  ({_op_creds_item(env)}) ===\n")
    if env == "dev":
        print("  (dev uses mock API — no Revolut API key needed)")
    else:
        for field in ("REVOLUT_API_KEY", "REVOLUT_PRIVATE_KEY", "REVOLUT_PUBLIC_KEY"):
            r = _op(
                "item",
                "get",
                _op_creds_item(env),
                "--vault",
                _OP_VAULT,
                "--fields",
                field,
                "--reveal",
            )
            if r.returncode == 0:
                print(f"  {field:<28}  {_mask_secret(r.stdout.strip())}")
    r = _op(
        "item",
        "get",
        _op_creds_item(env),
        "--vault",
        _OP_VAULT,
        "--fields",
        "TELEGRAM_BOT_TOKEN",
        "--reveal",
    )
    if r.returncode == 0:
        print(f"  {'TELEGRAM_BOT_TOKEN':<28}  {_mask_secret(r.stdout.strip())}")

    print(f"\n=== Configuration  ({_op_config_item(env)}) ===\n")
    print(f"  {'TRADING_MODE':<28}  (derived: dev/int → paper, prod → live)")
    for field in (
        "RISK_LEVEL",
        "BASE_CURRENCY",
        "TRADING_PAIRS",
        "DEFAULT_STRATEGY",
        "INITIAL_CAPITAL",
        "MAX_CAPITAL",
        "SHUTDOWN_TRAILING_STOP_PCT",
        "SHUTDOWN_MAX_WAIT_SECONDS",
        "TELEGRAM_CHAT_ID",
    ):
        r = _op("item", "get", _op_config_item(env), "--vault", _OP_VAULT, "--fields", field)
        if r.returncode == 0:
            print(f"  {field:<28}  {r.stdout.strip()}")


def _ops_set_creds(env: str) -> None:
    """Interactively prompt for and store the Revolut API key in 1Password."""
    if not _check_op():
        sys.exit(1)

    if env == "dev":
        print("Dev environment uses mock API — no API credentials needed.")
        print("Run 'revt run' to start with the mock API.")
        return

    print(f"Updating credentials in 1Password  ({_OP_VAULT}/{_op_creds_item(env)})\n")

    try:
        api_key = getpass.getpass("Revolut API Key: ").strip()
    except (KeyboardInterrupt, EOFError):
        print(_CANCELLED)
        return

    if api_key:
        r = _op(
            "item",
            "edit",
            _op_creds_item(env),
            "--vault",
            _OP_VAULT,
            f"REVOLUT_API_KEY[concealed]={api_key}",
        )
        if r.returncode == 0:
            print("  ✓  REVOLUT_API_KEY stored")
        else:
            print(f"  ✗  Failed: {r.stderr.strip()}")
            sys.exit(1)

    print("\nDone. Run 'revt ops --show' to verify.")


# ---------------------------------------------------------------------------
# cmd: config
# ---------------------------------------------------------------------------


def cmd_config(args: argparse.Namespace) -> None:
    """View and manage trading configuration stored in 1Password."""
    env = getattr(args, "env", None) or _detect_env()
    sub = getattr(args, "config_cmd", None) or "show"

    if sub == "show":
        _config_show(env)
    elif sub == "set":
        _config_set(env, args.key, args.value)
    elif sub == "init":
        _config_init(env)
    elif sub == "delete":
        _config_delete(env, args.key)


def _config_show(env: str) -> None:
    """Display all trading configuration values for the environment."""
    if not _check_op():
        sys.exit(1)

    print(f"\nConfiguration  ({_OP_VAULT} / {_op_config_item(env)})\n")
    print("─" * 55)
    print(f"  {'TRADING_MODE':<30} (derived: dev/int → paper, prod → live)")
    for key in (
        "RISK_LEVEL",
        "BASE_CURRENCY",
        "TRADING_PAIRS",
        "DEFAULT_STRATEGY",
        "INITIAL_CAPITAL",
        "MAX_CAPITAL",
        "SHUTDOWN_TRAILING_STOP_PCT",
        "SHUTDOWN_MAX_WAIT_SECONDS",
        "TELEGRAM_CHAT_ID",
    ):
        r = _op("item", "get", _op_config_item(env), "--vault", _OP_VAULT, "--fields", key)
        value = r.stdout.strip() if r.returncode == 0 else "(not set)"
        print(f"  {key:<30} {value}")


def _config_set(env: str, key: str, value: str) -> None:
    """Write a single configuration key to 1Password."""
    if not _check_op():
        sys.exit(1)

    r = _op(
        "item",
        "edit",
        _op_config_item(env),
        "--vault",
        _OP_VAULT,
        f"{key}[text]={value}",
    )
    if r.returncode == 0:
        print(f"  ✓  {key} = {value}")
    else:
        print(f"  ✗  Failed: {r.stderr.strip()}")
        print(f"     Run 'revt config init --env {env}' to create the config item first.")
        sys.exit(1)


def _config_init(env: str) -> None:
    """Create a config item in 1Password with safe defaults."""
    if not _check_op():
        sys.exit(1)

    r = _op("item", "get", _op_config_item(env), "--vault", _OP_VAULT)
    if r.returncode == 0:
        print(f"Config item already exists: {_op_config_item(env)}")
        try:
            confirm = input("Reset to defaults? (y/N): ").strip()
        except (KeyboardInterrupt, EOFError):
            print(_CANCELLED)
            return
        if confirm.lower() != "y":
            print("Cancelled.")
            return
        _op("item", "delete", _op_config_item(env), "--vault", _OP_VAULT)

    fields = [
        "RISK_LEVEL[text]=conservative",
        "BASE_CURRENCY[text]=EUR",
        "TRADING_PAIRS[text]=BTC-EUR,ETH-EUR",
        "DEFAULT_STRATEGY[text]=market_making",
    ]
    if env != "prod":
        fields.append("INITIAL_CAPITAL[text]=10000")

    r = subprocess.run(
        [
            "op",
            "item",
            "create",
            "--category",
            "Secure Note",
            "--vault",
            _OP_VAULT,
            "--title",
            _op_config_item(env),
            *fields,
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if r.returncode == 0:
        print(f"  ✓  Config item created: {_op_config_item(env)}")
        if env == "prod":
            print("  Tip: cap trading capital: revt config set MAX_CAPITAL 5000 --env prod")
    else:
        print(f"  ✗  Failed: {r.stderr.strip()}")
        sys.exit(1)


def _config_delete(env: str, key: str) -> None:
    """Remove a configuration key from 1Password."""
    if not _check_op():
        sys.exit(1)

    r = _op("item", "edit", _op_config_item(env), "--vault", _OP_VAULT, f"{key}[delete]")
    if r.returncode == 0:
        print(f"  ✓  {key} removed")
    else:
        print(f"  ✗  Failed: {r.stderr.strip()}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# cmd: api
# ---------------------------------------------------------------------------

# Friendly revt names → api_test.py command strings
_API_CMD_MAP: dict[str, str] = {
    "ready": "trade-ready",
    "pairs": "currency-pairs",
    "orders": "historical-orders",
    "last-trades": "last-public-trades",
}


def cmd_api(args: argparse.Namespace) -> None:
    """Call a Revolut X API endpoint and display the result.

    Translates user-friendly ``revt api`` command names to the underlying
    ``cli.api_test`` command names, then delegates to that module's ``main()``.
    Dev environment is blocked — it uses a local mock with no real endpoints.
    """
    env = getattr(args, "env", None) or _detect_env()
    if env == "dev":
        print("⚠️   API commands require a real API environment.")
        print("    Dev uses a local mock — no network calls are made.")
        print("    Use --env int or --env prod.")
        sys.exit(1)

    os.environ["ENVIRONMENT"] = env

    from loguru import logger

    logger.remove()
    logger.add(sys.stderr, level="WARNING")

    raw_cmd: str = args.api_cmd
    api_cmd: str = _API_CMD_MAP.get(raw_cmd, raw_cmd)

    from cli.api_test import main as _api_main

    argv: list[str] = ["api", api_cmd]
    if getattr(args, "symbol", None):
        argv += ["--symbol", args.symbol]
    if getattr(args, "symbols", None):
        argv += ["--symbols", args.symbols]
    if getattr(args, "order_id", None):
        argv += ["--order-id", args.order_id]
    if getattr(args, "interval", None) is not None:
        argv += ["--interval", str(args.interval)]
    if getattr(args, "limit", None) is not None:
        argv += ["--limit", str(args.limit)]
    if getattr(args, "depth", None) is not None:
        argv += ["--depth", str(args.depth)]

    old_argv, sys.argv = sys.argv, argv
    try:
        _api_main()
    finally:
        sys.argv = old_argv


# ---------------------------------------------------------------------------
# cmd: telegram
# ---------------------------------------------------------------------------


def cmd_telegram(args: argparse.Namespace) -> None:
    """Test Telegram notification connectivity.

    Loads credentials from 1Password, sends a test message to the configured
    chat/channel, and reports whether it was delivered.
    """
    env = _resolve_env(args)

    # Deferred import — ENVIRONMENT must be set before src.config is loaded.
    from src.config import settings
    from src.utils.telegram import TelegramNotifier

    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id

    if not token or not chat_id:
        missing = []
        if not token:
            missing.append(f"TELEGRAM_BOT_TOKEN  →  make ops ENV={env}")
        if not chat_id:
            missing.append(
                f"TELEGRAM_CHAT_ID    →  make opconfig-set KEY=TELEGRAM_CHAT_ID VALUE=<id> ENV={env}"
            )
        print("❌  Telegram is not configured. Set the missing fields:")
        for m in missing:
            print(f"     {m}")
        sys.exit(1)

    notifier = TelegramNotifier(token=token, chat_id=chat_id)
    print(f"Sending test notification (chat {chat_id})…")
    try:
        asyncio.run(notifier.send_test())
        print("✓  Test message delivered — check your Telegram chat.")
    except Exception as e:
        print(f"❌  Failed: {e}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# cmd: db
# ---------------------------------------------------------------------------


def cmd_db(args: argparse.Namespace) -> None:
    """Database management and analytics.

    Delegates to the appropriate ``cli.db_manage`` or ``cli.analytics_report``
    function based on the subcommand.
    """
    env = getattr(args, "env", None) or _detect_env()
    os.environ["ENVIRONMENT"] = env

    sub = getattr(args, "db_cmd", None) or "stats"

    if sub == "stats":
        from cli.db_manage import show_stats

        show_stats()

    elif sub == "analytics":
        from cli.db_manage import show_analytics

        show_analytics(days=getattr(args, "days", 30))

    elif sub == "backtests":
        from cli.db_manage import show_backtest_results

        show_backtest_results(limit=getattr(args, "limit", 10))

    elif sub == "export":
        from cli.db_manage import export_csv

        export_csv()

    elif sub == "report":
        from cli.analytics_report import generate_report

        generate_report(
            days=getattr(args, "days", 30),
            output_dir=Path(getattr(args, "output_dir", "data/reports")),
        )

    elif sub == "encrypt-setup":
        from src.utils.db_encryption import setup_database_encryption

        setup_database_encryption()

    elif sub == "encrypt-status":
        from src.utils.db_encryption import DatabaseEncryption

        enc = DatabaseEncryption()
        status = "enabled ✓" if enc.is_enabled else "DISABLED ✗"
        print(f"Database encryption: {status}")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _add_env_arg(p: argparse.ArgumentParser) -> None:
    """Add the standard --env argument to a subparser."""
    p.add_argument(
        "--env",
        "-e",
        choices=["dev", "int", "prod"],
        help=(
            "Environment (default: prod). Use --env int for paper trading with real market data."
        ),
    )


def _build_parser() -> argparse.ArgumentParser:
    """Build and return the full ``revt`` argument parser."""
    parser = argparse.ArgumentParser(
        prog="revt",
        description="Revolut Trader — user-facing CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  revt ops                                    store your Revolut API key
  revt ops --show                             show credentials + config
  revt ops --status                           check 1Password connection

  revt config show                            view trading configuration
  revt config set RISK_LEVEL aggressive
  revt config set MAX_CAPITAL 5000            cap how much the bot can trade

  revt run                                    start live trading
  revt run --strategy momentum --risk moderate
  revt run --env int                          paper trading (real data, no real trades)

  revt backtest                               30-day backtest
  revt backtest --hf                          high-frequency (1-min candles)
  revt backtest --compare                     compare all strategies
  revt backtest --matrix                      all strategies × all risk levels

  revt api balance                            account balances
  revt api ready                              check API permissions
  revt api ticker --symbol BTC-EUR

  revt db stats                               database overview
  revt db analytics --days 60
  revt db backtests
  revt db export
  revt db report                              full analytics report + charts

  revt telegram test                          verify Telegram notifications are working
""",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # ── run ──────────────────────────────────────────────────────────────────
    p_run = sub.add_parser("run", help="Start the trading bot")
    _add_env_arg(p_run)
    p_run.add_argument(
        "--strategy",
        "-s",
        choices=[
            "market_making",
            "momentum",
            "mean_reversion",
            "multi_strategy",
            "breakout",
            "range_reversion",
        ],
        default="market_making",
        help="Trading strategy (default: market_making)",
    )
    p_run.add_argument(
        "--risk",
        "-r",
        choices=["conservative", "moderate", "aggressive"],
        default="conservative",
        help="Risk level (default: conservative)",
    )
    p_run.add_argument(
        "--pairs",
        "-p",
        help="Comma-separated pairs, e.g. BTC-EUR,ETH-EUR (default: from 1Password config)",
    )
    p_run.add_argument(
        "--interval",
        "-i",
        type=int,
        help="Polling interval in seconds (default: strategy-dependent)",
    )
    p_run.add_argument(
        "--log-level",
        "-l",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
    )
    p_run.set_defaults(func=cmd_run)

    # ── backtest ──────────────────────────────────────────────────────────────
    p_bt = sub.add_parser("backtest", help="Backtest strategies on historical data")
    _add_env_arg(p_bt)
    p_bt.add_argument(
        "--hf",
        action="store_true",
        help="High-frequency mode (1-min candles, closest to live 5s polling)",
    )
    p_bt.add_argument("--compare", action="store_true", help="Compare all strategies side-by-side")
    p_bt.add_argument(
        "--matrix", action="store_true", help="All strategies × all risk levels matrix"
    )
    p_bt.add_argument(
        "--strategy",
        "-s",
        choices=[
            "market_making",
            "momentum",
            "mean_reversion",
            "multi_strategy",
            "breakout",
            "range_reversion",
        ],
        default="market_making",
        help="Strategy for single run (ignored with --compare / --matrix)",
    )
    p_bt.add_argument(
        "--strategies",
        help="Comma-separated strategies for --compare (default: all)",
    )
    p_bt.add_argument("--days", "-d", type=int, default=30, help=_DAYS_HELP)
    p_bt.add_argument(
        "--interval",
        "-i",
        type=int,
        default=60,
        choices=[1, 5, 15, 30, 60, 240, 1440],
        help="Candle interval in minutes (default: 60)",
    )
    p_bt.add_argument(
        "--risk",
        "-r",
        choices=["conservative", "moderate", "aggressive"],
        default="conservative",
        help="Risk level (default: conservative)",
    )
    p_bt.add_argument(
        "--pairs",
        "-p",
        default="BTC-EUR,ETH-EUR",
        help="Comma-separated pairs (default: BTC-EUR,ETH-EUR)",
    )
    p_bt.add_argument(
        "--capital",
        "-c",
        type=float,
        default=10000.0,
        help="Initial capital in EUR (default: 10000)",
    )
    p_bt.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
    )
    p_bt.set_defaults(func=cmd_backtest)

    # ── ops ───────────────────────────────────────────────────────────────────
    p_ops = sub.add_parser("ops", help="Manage API credentials in 1Password")
    _add_env_arg(p_ops)
    ops_grp = p_ops.add_mutually_exclusive_group()
    ops_grp.add_argument(
        "--show", action="store_true", help="Show stored credentials + config (secrets masked)"
    )
    ops_grp.add_argument(
        "--status", action="store_true", help="Check 1Password CLI status and item availability"
    )
    p_ops.set_defaults(func=cmd_ops)

    # ── config ────────────────────────────────────────────────────────────────
    p_cfg = sub.add_parser("config", help="View / update trading configuration in 1Password")
    _add_env_arg(p_cfg)
    cfg_sub = p_cfg.add_subparsers(dest="config_cmd", metavar="<subcommand>")

    cfg_sub.add_parser("show", help="Show current configuration")

    p_cfg_set = cfg_sub.add_parser("set", help="Set a configuration value")
    p_cfg_set.add_argument("key", help="Config key, e.g. RISK_LEVEL")
    p_cfg_set.add_argument("value", help="New value")

    cfg_sub.add_parser("init", help="Create config item with safe defaults")

    p_cfg_del = cfg_sub.add_parser("delete", help="Remove a configuration key")
    p_cfg_del.add_argument("key", help="Config key to remove")

    p_cfg.set_defaults(func=cmd_config)

    # ── api ───────────────────────────────────────────────────────────────────
    p_api = sub.add_parser(
        "api",
        help="Call Revolut X API endpoints (requires --env int or prod)",
    )
    _add_env_arg(p_api)
    p_api.add_argument(
        "api_cmd",
        metavar="<endpoint>",
        choices=[
            "test",
            "ready",
            "balance",
            "ticker",
            "tickers",
            "all-tickers",
            "currencies",
            "pairs",
            "last-trades",
            "order-book",
            "candles",
            "open-orders",
            "orders",
            "trades",
            "public-trades",
            "order",
        ],
        help=(
            "test · ready · balance · ticker · tickers · all-tickers · "
            "currencies · pairs · last-trades · order-book · candles · "
            "open-orders · orders · trades · public-trades · order"
        ),
    )
    p_api.add_argument("--symbol", "-s", help="Trading pair, e.g. BTC-EUR")
    p_api.add_argument("--symbols", help="Comma-separated pairs, e.g. BTC-EUR,ETH-EUR")
    p_api.add_argument("--order-id", dest="order_id", help="Order UUID")
    p_api.add_argument(
        "--interval",
        "-i",
        type=int,
        default=60,
        choices=[1, 5, 15, 30, 60, 240, 1440],
        help="Candle interval in minutes (default: 60)",
    )
    p_api.add_argument("--limit", "-l", type=int, default=20, help="Result limit (default: 20)")
    p_api.add_argument("--depth", type=int, default=20, help="Order book depth (default: 20)")
    p_api.set_defaults(func=cmd_api)

    # ── db ────────────────────────────────────────────────────────────────────
    p_db = sub.add_parser("db", help="Database management and analytics")
    _add_env_arg(p_db)
    db_sub = p_db.add_subparsers(dest="db_cmd", metavar="<subcommand>")

    db_sub.add_parser("stats", help="Database statistics overview")

    p_db_an = db_sub.add_parser("analytics", help="Trading analytics")
    p_db_an.add_argument("--days", type=int, default=30, help=_DAYS_HELP)

    p_db_bt = db_sub.add_parser("backtests", help="Recent backtest results")
    p_db_bt.add_argument(
        "--limit", type=int, default=10, help="Number of results to show (default: 10)"
    )

    db_sub.add_parser("export", help="Export all data to CSV")

    p_db_rep = db_sub.add_parser("report", help="Full analytics report with charts")
    p_db_rep.add_argument("--days", type=int, default=30, help=_DAYS_HELP)
    p_db_rep.add_argument(
        "--output-dir",
        dest="output_dir",
        default="data/reports",
        help="Output directory (default: data/reports)",
    )

    db_sub.add_parser("encrypt-setup", help="Generate and store the DB encryption key in 1Password")
    db_sub.add_parser("encrypt-status", help="Check whether DB encryption is active")

    p_db.set_defaults(func=cmd_db)

    # ── telegram ──────────────────────────────────────────────────────────────
    p_tg = sub.add_parser("telegram", help="Telegram notification utilities")
    _add_env_arg(p_tg)
    tg_sub = p_tg.add_subparsers(dest="telegram_cmd", metavar="<subcommand>")
    tg_sub.add_parser("test", help="Send a test message to verify Telegram is configured correctly")
    p_tg.set_defaults(func=cmd_telegram)

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Revolut Trader CLI entry point (the ``revt`` command).

    Parses arguments, dispatches to the appropriate command handler, and
    handles top-level errors gracefully.
    """
    parser = _build_parser()
    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(0)

    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as e:
        print(f"\n❌  {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
