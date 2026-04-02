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
    revt update                Update revt (preserves data/ and config)
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
        "prod": "prod (real API · paper mode by default)",
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
# Update notification helpers
# ---------------------------------------------------------------------------


def _read_update_cache(cache_file: Path, cache_ttl: int) -> tuple[str, str] | None:
    """Read and validate update cache.

    Returns:
        Tuple of (current, latest) if cache is fresh and update available, else None.
    """
    import json
    import time

    if not cache_file.exists():
        return None

    try:
        with open(cache_file) as f:
            cache = json.load(f)
            if time.time() - cache.get("timestamp", 0) < cache_ttl:
                # Cache is fresh
                if cache.get("update_available"):
                    return (cache.get("current"), cache.get("latest"))
                return None
    except Exception as e:
        # Invalid cache, will re-check - silently continue
        import logging

        logging.debug(f"Failed to read update cache: {e}")
    return None


def _get_current_version_from_pyproject() -> str | None:
    """Get current version from pyproject.toml."""
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[import-not-found]  # fallback
        except ImportError:
            return None  # Can't check without tomllib

    pyproject_path = _ROOT / "pyproject.toml"
    if not pyproject_path.exists():
        return None

    try:
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
            return data.get("project", {}).get("version")
    except Exception:
        return None


def _get_latest_github_release() -> str | None:
    """Get latest release tag from GitHub API.

    Returns:
        Latest tag (without 'v' prefix) or None if unavailable.
    """
    import json
    import urllib.request

    try:
        url = "https://api.github.com/repos/badoriie/revolut-trader/releases/latest"
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/vnd.github.v3+json")
        # nosec B310: HTTPS URL from trusted GitHub API
        with urllib.request.urlopen(req, timeout=5) as response:  # nosec B310
            data = json.loads(response.read().decode())
            return data.get("tag_name", "").lstrip("v")
    except Exception:
        # Network error or rate limit - don't show notification
        return None


def _write_update_cache(
    cache_file: Path, current: str, latest: str, update_available: bool
) -> None:
    """Write update check results to cache file."""
    import json
    import time

    cache_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(cache_file, "w") as f:
            json.dump(
                {
                    "timestamp": time.time(),
                    "current": current,
                    "latest": latest,
                    "update_available": update_available,
                },
                f,
            )
    except Exception as e:
        # Cache write failure is non-critical - silently continue
        import logging

        logging.debug(f"Failed to write update cache: {e}")


def _check_for_updates() -> tuple[str, str] | None:
    """Check if a new version is available.

    Returns:
        Tuple of (current_version, latest_version) if update available, else None.

    Uses a cache file to avoid hitting GitHub API too frequently (once per day).
    """
    cache_file = _ROOT / "data" / ".update_check_cache"
    cache_ttl = 86400  # 24 hours in seconds

    # Check cache first
    cached_result = _read_update_cache(cache_file, cache_ttl)
    if cached_result is not None:
        return cached_result

    # Get current version
    current_version = _get_current_version_from_pyproject()
    if not current_version:
        return None

    # Get latest release from GitHub API
    latest_tag = _get_latest_github_release()
    if not latest_tag:
        return None

    # Compare versions
    current = current_version.lstrip("v")
    latest = latest_tag.lstrip("v")
    update_available = current != latest

    # Update cache
    _write_update_cache(cache_file, current, latest, update_available)

    if update_available:
        return (current, latest)
    return None


def _show_update_notification() -> None:
    """Show update notification if a new version is available."""
    result = _check_for_updates()
    if result:
        current, latest = result
        print()
        print("┌─────────────────────────────────────────────────────────────┐")
        print("│  📦  Update Available!                                      │")
        print("│                                                             │")
        print(f"│  Current: v{current:<48} │")
        print(f"│  Latest:  v{latest:<48} │")
        print("│                                                             │")
        print("│  Update now:  revt update                                  │")
        print("└─────────────────────────────────────────────────────────────┘")
        print()


# ---------------------------------------------------------------------------
# cmd: run
# ---------------------------------------------------------------------------


def _print_run_config(args: argparse.Namespace, env: str, mode_override: str | None) -> None:
    """Print the run configuration banner."""
    print(f"\n  Environment : {_env_badge(env)}")
    print(f"  Strategy    : {args.strategy or '(from 1Password)'}")
    print(f"  Risk level  : {args.risk or '(from 1Password)'}")
    if mode_override:
        print(f"  Trading mode: {mode_override} (override)")
    else:
        print("  Trading mode: (from 1Password config, defaults to paper)")
    print()


def _handle_live_mode_confirmation(confirm_live: bool) -> None:
    """Handle live mode confirmation prompt.

    Args:
        confirm_live: If True, skip confirmation prompt.

    Raises:
        SystemExit: If user cancels or doesn't confirm.
    """
    from src.config import settings

    warning = settings.get_mode_warning()
    if not warning:
        return

    print(warning)
    print()
    if not confirm_live:
        try:
            confirm = input("Type 'I UNDERSTAND' to continue: ").strip()
        except (KeyboardInterrupt, EOFError):
            print(_CANCELLED)
            sys.exit(0)
        if confirm != "I UNDERSTAND":
            print("Cancelled.")
            sys.exit(0)
        print()


def _setup_logger(log_level: str | None) -> None:
    """Configure loguru logger for the bot."""
    from loguru import logger

    logger.remove()
    logger.add(
        sys.stderr,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<level>{message}</level>"
        ),
        level=log_level or "INFO",
    )


def cmd_run(args: argparse.Namespace) -> None:
    """Start the trading bot.

    Sets ENVIRONMENT early (before any ``src.config`` import) then delegates to
    ``cli.run.run_bot`` via a compatible argument namespace.
    """
    # Check for updates (non-blocking, cached)
    _show_update_notification()

    env = _resolve_env(args)
    mode_override = getattr(args, "mode", None)
    confirm_live = getattr(args, "confirm_live", False)

    _print_run_config(args, env, mode_override)

    # Import config to check actual trading mode
    from src.config import TradingMode, settings

    # Apply mode override if provided
    if mode_override:
        settings.override_trading_mode(TradingMode(mode_override))

    _handle_live_mode_confirmation(confirm_live)
    _setup_logger(args.log_level)

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
    # Check for updates (non-blocking, cached)
    _show_update_notification()

    _resolve_env(args)

    from loguru import logger

    logger.remove()
    logger.add(sys.stderr, level=args.log_level or "INFO")

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
    days: int | None,
    interval: int | None,
    pairs: str | None,
    capital: float | None,
    risk: str | None,
    risk_levels: str | None,
    strategies: str | None,
    log_level: str | None,
) -> None:
    """Invoke ``backtest_compare.main()`` by patching sys.argv.

    Any None argument is omitted from argv so backtest_compare falls back to its
    1Password-sourced defaults.
    """
    from cli.backtest_compare import main as _compare_main

    argv = ["backtest_compare"]
    if days is not None:
        argv += ["--days", str(days)]
    if interval is not None:
        argv += ["--interval", str(interval)]
    if pairs is not None:
        argv += ["--pairs", pairs]
    if capital is not None:
        argv += ["--capital", str(capital)]
    if log_level is not None:
        argv += ["--log-level", log_level]
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
    """Telegram bot utilities and always-on control plane.

    Subcommands:
      test   — send a test message to verify Telegram is configured correctly
      start  — start the always-on Telegram Control Plane process
    """
    env = _resolve_env(args)
    sub_cmd = getattr(args, "telegram_cmd", None) or "test"

    if sub_cmd == "start":
        # Check for updates (non-blocking, cached)
        _show_update_notification()

        # Deferred import — ENVIRONMENT must be set before src.config is loaded.
        from cli.telegram_control import run_control_plane

        print(f"\n  Environment : {_env_badge(env)}")
        print("  Starting Telegram Control Plane…")
        print("  Control the bot via Telegram: /run /stop /status /balance /report /help")
        print()
        run_control_plane()
        return

    # Default: test
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


def _get_binary_name_for_platform() -> str:
    """Determine the binary name for the current platform.

    Returns:
        Binary name string (e.g., "revt-linux-arm64").

    Raises:
        SystemExit: If platform is not supported.
    """
    import platform

    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "linux":
        if "arm" in machine or "aarch64" in machine:
            return "revt-linux-arm64"
        if "x86_64" in machine or "amd64" in machine:
            return "revt-linux-x86_64"

        print(f"❌ Unsupported Linux architecture: {machine}")
        print("   Supported: ARM64, x86_64")
        sys.exit(1)
    else:
        print(f"❌ Unsupported platform: {system}")
        print("   Supported platforms: Linux (ARM64, x86_64)")
        sys.exit(1)


def _download_and_install_binary(url: str, latest_tag: str | None) -> None:
    """Download binary from URL and replace current executable.

    Args:
        url: Download URL for the binary.
        latest_tag: Latest version tag for display (e.g., "v0.3.0").

    Raises:
        SystemExit: If download or installation fails.
    """
    import shutil
    import tempfile
    import urllib.error
    import urllib.request

    try:
        # Download to temp file
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            # nosec B310: HTTPS URL from trusted GitHub releases
            urllib.request.urlretrieve(url, tmp.name)  # nosec B310
            tmp_path = Path(tmp.name)

        # Make executable
        tmp_path.chmod(0o755)

        # Get current binary path
        current_binary = Path(sys.executable)
        backup_path = current_binary.with_suffix(".backup")

        # Backup current binary
        if current_binary.exists():
            shutil.copy2(current_binary, backup_path)
            print(f"✓ Backed up current binary to: {backup_path}")

        # Replace with new binary
        shutil.move(str(tmp_path), str(current_binary))
        print(f"✓ Updated: {current_binary}")
        print()
        print("✅ Update complete!")
        print()
        if latest_tag:
            print(f"Now running: {latest_tag}")
            print()
        print("Verify:")
        print(f"  {current_binary} --version")
        print()
        print("Rollback (if needed):")
        print(f"  mv {backup_path} {current_binary}")

    except urllib.error.HTTPError as e:
        print(f"\n❌ Download failed: {e}")
        print(f"   URL: {url}")
        print("\n   This might mean:")
        print("   - No release exists for your platform")
        print("   - Network connectivity issue")
        print("   - GitHub release not yet published")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Update failed: {e}")
        sys.exit(1)


def _check_binary_version() -> tuple[str | None, str | None]:
    """Check current and latest binary versions.

    Returns:
        Tuple of (current_version, latest_tag) or (None, None) if unavailable.
    """
    import json
    import urllib.request

    def get_current_version() -> str | None:
        """Get current version from pyproject.toml."""
        try:
            import tomllib  # Python 3.11+
        except ImportError:
            import tomli as tomllib  # type: ignore[import-not-found]  # fallback for older Python

        pyproject_path = _ROOT / "pyproject.toml"
        if pyproject_path.exists():
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
                return data.get("project", {}).get("version")
        return None

    def get_latest_release_tag() -> str | None:
        """Get latest release tag from GitHub API."""
        try:
            url = "https://api.github.com/repos/badoriie/revolut-trader/releases/latest"
            req = urllib.request.Request(url)
            req.add_header("Accept", "application/vnd.github.v3+json")
            # nosec B310: HTTPS URL from trusted GitHub API
            with urllib.request.urlopen(req, timeout=10) as response:  # nosec B310
                data = json.loads(response.read().decode())
                return data.get("tag_name")  # e.g., "v0.3.0"
        except Exception:
            return None

    return get_current_version(), get_latest_release_tag()


def _update_from_binary() -> None:
    """Update when running as a frozen PyInstaller binary."""
    print("🔄 Checking for updates...")
    print()

    # Get current and latest versions
    current_version, latest_tag = _check_binary_version()

    if current_version and latest_tag:
        # Normalize versions for comparison (remove 'v' prefix if present)
        current = current_version.lstrip("v")
        latest = latest_tag.lstrip("v")

        print(f"Current version: v{current}")
        print(f"Latest release:  {latest_tag}")
        print()

        if current == latest:
            print("✅ Already up to date!")
            print()
            print("You're running the latest version.")
            return

        print("📥 New version available!")
        print()

    # Determine platform and binary name
    binary_name = _get_binary_name_for_platform()

    # Download URL
    url = f"https://github.com/badoriie/revolut-trader/releases/latest/download/{binary_name}"
    print(f"Downloading: {url}")

    # Download and install
    _download_and_install_binary(url, latest_tag)


def _update_from_source() -> None:
    """Update when running from source (git repository)."""
    print("🔄 Checking for updates...")
    print()

    # Check if in git repository
    try:
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            check=True,
            cwd=_ROOT,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Not in a git repository")
        print("   Clone from: https://github.com/badoriie/revolut-trader")
        sys.exit(1)

    # Get current branch
    current_branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        cwd=_ROOT,
    ).stdout.strip()

    # Fetch to check for updates
    print("⬇️  Fetching latest changes...")
    subprocess.run(["git", "fetch", "origin"], check=True, cwd=_ROOT)

    # Check if behind
    local_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        cwd=_ROOT,
    ).stdout.strip()

    remote_commit = subprocess.run(
        ["git", "rev-parse", f"origin/{current_branch}"],
        capture_output=True,
        text=True,
        check=True,
        cwd=_ROOT,
    ).stdout.strip()

    print(f"Current branch: {current_branch}")
    print()

    if local_commit == remote_commit:
        print("✅ Already up to date!")
        print()
        print("Your local branch matches origin.")
        return

    # Show what's new
    commits_behind = subprocess.run(
        ["git", "rev-list", "--count", f"HEAD..origin/{current_branch}"],
        capture_output=True,
        text=True,
        cwd=_ROOT,
    ).stdout.strip()

    print(f"📥 {commits_behind} new commit(s) available")
    print()

    # Check for uncommitted changes
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        cwd=_ROOT,
    )

    has_changes = bool(status.stdout.strip())

    if has_changes:
        print("📦 Stashing local changes...")
        subprocess.run(["git", "stash", "push", "-m", "revt update"], check=True, cwd=_ROOT)
        print("✓ Changes stashed")
        print()

    # Pull latest changes
    print(f"📥 Pulling origin/{current_branch}...")
    result = subprocess.run(
        ["git", "pull", "origin", current_branch],
        capture_output=True,
        text=True,
        cwd=_ROOT,
    )

    if result.returncode != 0:
        print(f"❌ Pull failed:\n{result.stderr}")
        if has_changes:
            print("\n🔄 Re-applying stashed changes...")
            subprocess.run(["git", "stash", "pop"], cwd=_ROOT)
        sys.exit(1)

    print("✓ Pulled latest changes")
    if result.stdout.strip():
        print(result.stdout)

    # Re-apply stashed changes if any
    if has_changes:
        print("🔄 Re-applying local changes...")
        pop_result = subprocess.run(
            ["git", "stash", "pop"],
            capture_output=True,
            text=True,
            cwd=_ROOT,
        )
        if pop_result.returncode == 0:
            print("✓ Changes re-applied")
        else:
            print("⚠️  Conflicts detected — resolve manually")
            print(pop_result.stdout)

    # Update dependencies
    print()
    print("📦 Updating dependencies...")
    subprocess.run(["uv", "sync", "--extra", "dev"], check=True, cwd=_ROOT)
    print("✓ Dependencies updated")

    print()
    print("✅ Update complete!")
    print()
    print("ℹ️  Your data/ folder and 1Password config are untouched.")


def cmd_update(args: argparse.Namespace) -> None:
    """Update the codebase while preserving data and configuration.

    Running from source:
        - Checks if already up to date
        - Stashes local changes (if any)
        - Pulls latest from origin/main
        - Re-applies stashed changes
        - Reinstalls dependencies (uv sync)

    Running as frozen binary:
        - Checks current version vs latest release
        - Downloads the latest release binary for current platform (if newer)
        - Replaces the current binary
        - Preserves all data, config, and 1Password credentials

    The data/ folder and all 1Password configuration remain untouched.
    """
    # Check if running as frozen binary
    if getattr(sys, "frozen", False):
        _update_from_binary()
    else:
        _update_from_source()


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

_SUBCOMMAND_METAVAR = "<subcommand>"


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
  revt telegram start                         start always-on Telegram Control Plane

  revt update                                 update revt (preserves data/ and config)
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
        default=None,
        help="Trading strategy (default: DEFAULT_STRATEGY from 1Password config)",
    )
    p_run.add_argument(
        "--risk",
        "-r",
        choices=["conservative", "moderate", "aggressive"],
        default=None,
        help="Risk level (default: RISK_LEVEL from 1Password config)",
    )
    p_run.add_argument(
        "--pairs",
        "-p",
        help="Comma-separated pairs, e.g. BTC-EUR,ETH-EUR (default: TRADING_PAIRS from 1Password config)",
    )
    p_run.add_argument(
        "--interval",
        "-i",
        type=int,
        help="Polling interval in seconds (default: INTERVAL from 1Password config, or strategy-dependent)",
    )
    p_run.add_argument(
        "--log-level",
        "-l",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="Logging level (default: LOG_LEVEL from 1Password config, or INFO)",
    )
    p_run.add_argument(
        "--mode",
        "-m",
        choices=["paper", "live"],
        default=None,
        help="Trading mode (default: TRADING_MODE from 1Password config, or paper if not set)",
    )
    p_run.add_argument(
        "--confirm-live",
        action="store_true",
        help="Skip confirmation prompt for live mode (use with --mode live in scripts)",
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
        default=None,
        help="Strategy for single run (default: DEFAULT_STRATEGY from 1Password config)",
    )
    p_bt.add_argument(
        "--strategies",
        help="Comma-separated strategies for --compare (default: all)",
    )
    p_bt.add_argument(
        "--days",
        "-d",
        type=int,
        default=None,
        help="Days of historical data (default: BACKTEST_DAYS from 1Password config, or 30)",
    )
    p_bt.add_argument(
        "--interval",
        "-i",
        type=int,
        default=None,
        choices=[1, 5, 15, 30, 60, 240, 1440, 2880, 5760, 10080, 20160, 40320],
        help="Candle interval in minutes (default: BACKTEST_INTERVAL from 1Password config, or 60)",
    )
    p_bt.add_argument(
        "--risk",
        "-r",
        choices=["conservative", "moderate", "aggressive"],
        default=None,
        help="Risk level (default: RISK_LEVEL from 1Password config)",
    )
    p_bt.add_argument(
        "--pairs",
        "-p",
        default=None,
        help="Comma-separated pairs (default: TRADING_PAIRS from 1Password config)",
    )
    p_bt.add_argument(
        "--capital",
        "-c",
        type=float,
        default=None,
        help="Initial capital in EUR (default: INITIAL_CAPITAL from 1Password config)",
    )
    p_bt.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="Logging level (default: LOG_LEVEL from 1Password config, or INFO)",
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
    cfg_sub = p_cfg.add_subparsers(dest="config_cmd", metavar=_SUBCOMMAND_METAVAR)

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
    db_sub = p_db.add_subparsers(dest="db_cmd", metavar=_SUBCOMMAND_METAVAR)

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
    p_tg = sub.add_parser("telegram", help="Telegram bot utilities and always-on control plane")
    _add_env_arg(p_tg)
    tg_sub = p_tg.add_subparsers(dest="telegram_cmd", metavar=_SUBCOMMAND_METAVAR)
    tg_sub.add_parser("test", help="Send a test message to verify Telegram is configured correctly")
    tg_sub.add_parser(
        "start",
        help=(
            "Start the always-on Telegram Control Plane — "
            "control the bot via /run, /stop, /status, /balance, /report"
        ),
    )
    p_tg.set_defaults(func=cmd_telegram)

    # ── update ────────────────────────────────────────────────────────────────
    p_update = sub.add_parser(
        "update",
        help="Update revt to the latest version (preserves data/ folder and 1Password config)",
    )
    p_update.set_defaults(func=cmd_update)

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
