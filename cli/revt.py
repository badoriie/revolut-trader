#!/usr/bin/env python3
"""revt — Revolut Trader CLI.

The polished, user-facing entry point replacing all non-development make targets.
Environment is strictly auto-detected from the git branch / tag / binary type.
No override is permitted.

Usage
-----
    revt run                   Start the trading bot
    revt backtest              Run backtests  (--compare · --matrix)
    revt ops init|--show       Manage API credentials in 1Password
    revt config                View / update trading configuration
    revt api test|ready        Check API connectivity and permissions
    revt db  <subcommand>      Database management and analytics
    revt update                Update revt (preserves revt-data/ and config)
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import errno
import getpass
import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_OP_VAULT = "revolut-trader"


def _get_data_dir() -> Path:
    """Return the data directory from REVT_DATA_DIR env var or ~/revt-data."""
    raw = os.environ.get("REVT_DATA_DIR", "").strip()
    return Path(raw) if raw else Path.home() / "revt-data"


_OP_CATEGORY = "Secure Note"
_CANCELLED = "\nCancelled."
_DAYS_HELP = "Look-back days (default: 30)"


# ---------------------------------------------------------------------------
# Environment helpers — detection delegated to cli.env_detect
# ---------------------------------------------------------------------------

from cli.utils.env_detect import set_env as _set_env  # noqa: E402


def _env_badge(env: str) -> str:
    """Return a human-readable label for the given environment."""
    labels = {
        "dev": "dev  (mock API · paper mode)",
        "int": "int  (real API · paper mode)",
        "prod": "prod (real API · paper mode unless TRADING_MODE=live in 1Password)",
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
    """Get current version, works for both frozen binaries and source installs.

    Tries importlib.metadata first (works in PyInstaller bundles), then falls
    back to reading pyproject.toml directly (works in source/dev mode).
    """
    # importlib.metadata works when the package is installed (including PyInstaller bundles)
    try:
        from importlib.metadata import version

        return version("revolut-trader")
    except Exception:
        pass  # nosec B110 — fallback to pyproject.toml below; exception is non-critical

    # Fallback: read pyproject.toml directly (dev/source mode)
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


def _get_latest_github_release(timeout: int = 5) -> str | None:
    """Get latest release tag from GitHub API.

    Args:
        timeout: Request timeout in seconds (default: 5).

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
        with urllib.request.urlopen(req, timeout=timeout) as response:  # nosec B310
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
    Can be disabled via REVT_SKIP_UPDATE_CHECK environment variable.
    """
    # Allow disabling update checks
    if os.environ.get("REVT_SKIP_UPDATE_CHECK"):
        return None

    cache_file = _get_data_dir() / ".update_check_cache"
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

    env = _set_env()
    mode_override = getattr(args, "mode", None)
    confirm_live = getattr(args, "confirm_live", False)

    # Validate trading pairs if provided
    if args.pairs:
        from cli.utils.validators import validate_trading_pairs

        is_valid, error = validate_trading_pairs(args.pairs)
        if not is_valid:
            print(f"❌  {error}")
            print("    Example: --pairs BTC-EUR,ETH-EUR")
            sys.exit(1)

    _print_run_config(args, env, mode_override)

    # Import config to check actual trading mode
    from src.config import TradingMode, settings

    # Apply mode override if provided
    if mode_override:
        settings.override_trading_mode(TradingMode(mode_override))

    _handle_live_mode_confirmation(confirm_live)
    _setup_logger(args.log_level)

    # Deferred import — ENVIRONMENT must be set before src.config is loaded.
    from cli.commands.run import run_bot

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
    """Run a backtest — single strategy, compare, or matrix.

    Sets ENVIRONMENT then delegates to the appropriate backtest CLI function.
    """
    # Check for updates (non-blocking, cached)
    _show_update_notification()

    _set_env()

    # --real-data: promote to int so settings loads int credentials from 1Password.
    # Must happen before any deferred import that triggers src.config loading.
    if getattr(args, "real_data", False):
        os.environ["ENVIRONMENT"] = "int"

    # Validate conflicting flags
    if args.matrix and (args.strategy or args.strategies):
        print("⚠️  Warning: --strategy and --strategies are ignored in --matrix mode")
        print("    Matrix mode tests all strategies × all risk levels")
        print()

    if args.compare and args.strategy:
        print("⚠️  Warning: --strategy is ignored in --compare mode")
        print("    Compare mode tests multiple strategies side-by-side")
        print()

    from loguru import logger

    logger.remove()
    logger.add(sys.stderr, level=args.log_level or "INFO")

    real_data = getattr(args, "real_data", False)

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
            real_data=real_data,
        )
    elif args.compare:
        _run_compare_cli(
            days=args.days,
            interval=args.interval,
            pairs=args.pairs,
            capital=args.capital,
            risk=args.risk,
            risk_levels=getattr(args, "risk_levels", None),
            strategies=getattr(args, "strategies", None),
            log_level=args.log_level,
            real_data=real_data,
        )
    else:
        _backtest_single(args)


def _backtest_single(
    args: argparse.Namespace,
    interval_override: int | None = None,
) -> None:
    """Run a single-strategy backtest by calling ``cli.backtest.run_backtest``."""
    from cli.commands.backtest import run_backtest

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
    real_data: bool = False,
) -> None:
    """Invoke backtest_compare.run_compare_cli() directly with parameters.

    No more sys.argv patching - calls the function directly.
    """
    from cli.commands.backtest_compare import run_compare_cli

    run_compare_cli(
        days=days,
        interval=interval,
        pairs=pairs,
        capital=capital,
        risk=risk,
        risk_levels=risk_levels,
        strategies=strategies,
        log_level=log_level,
        real_data=real_data,
    )


# ---------------------------------------------------------------------------
# cmd: ops
# ---------------------------------------------------------------------------


def cmd_ops(args: argparse.Namespace) -> None:
    """Manage Revolut X API credentials stored in 1Password."""
    env = _set_env()

    if getattr(args, "ops_cmd", None) == "init":
        _ops_init(env)
    elif args.status:
        _ops_status(env)
    elif args.show:
        _ops_show(env)
    else:
        _ops_set_creds(env)


def _ops_status(env: str) -> None:
    """Print 1Password CLI and vault/item status for the given environment."""
    from src.utils.onepassword import get_install_instructions

    print("=== 1Password Status ===\n")

    r = _op("--version")
    if r.returncode == 0:
        print(f"  CLI              {r.stdout.strip()}")
    else:
        install_cmd = get_install_instructions()
        print(
            f"  CLI              not installed\n\n  Install with:\n  {install_cmd.replace(chr(10), chr(10) + '  ')}"
        )
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


def _safe_mask(raw: str) -> str:
    """
    Apply secret masking and enforce that no more than a small suffix of the
    secret is ever exposed. This ensures nothing close to the full secret is
    printed, even if _mask_secret is relaxed in the future.
    """
    masked = _mask_secret(raw)
    # As an extra safety net, only allow at most the last 4 characters to be visible.
    # Everything else is replaced with '*' so the original secret cannot be reconstructed.
    # Note: _mask_secret always returns a string, so no None check needed
    if len(masked) <= 4:
        return "*" * len(masked)
    return "*" * (len(masked) - 4) + masked[-4:]


def _ops_show(env: str) -> None:
    """Print stored credentials and configuration (secrets masked)."""
    if not _check_op():
        sys.exit(1)

    # Safety: Ensure we're not redirecting to a file (prevents accidental secret leakage)
    if not sys.stdout.isatty():
        print("❌  This command displays sensitive data.")
        print("    It can only be run interactively (not piped or redirected to a file).")
        print("    Example of what NOT to do: revt ops --show > file.txt")
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
                print(f"  {field:<28}  {_safe_mask(r.stdout.strip())}")
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
        print(f"  {'TELEGRAM_BOT_TOKEN':<28}  <stored in 1Password (hidden)>")

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


def _ops_init(env: str) -> None:
    """Create credentials and config placeholders in 1Password.

    For int/prod environments an Ed25519 keypair is generated automatically.
    The public key is printed so the user can register it in Revolut X.
    The credentials item is created (or reset) with placeholders; the user
    only needs to fill in ``REVOLUT_API_KEY`` after registering the public key.

    For dev the keypair is skipped — the mock API needs no real credentials.
    """
    if not _check_op():
        sys.exit(1)

    print(f"\n  Initialising revolut-trader for env: {_env_badge(env)}\n")

    # ── Step 1: credentials item ─────────────────────────────────────────────
    creds_item = _op_creds_item(env)
    r = _op("item", "get", creds_item, "--vault", _OP_VAULT)
    if r.returncode == 0:
        print(f"  Credentials item already exists: {creds_item}")
        try:
            confirm = input("  Reset it? This will overwrite stored keys. (y/N): ").strip()
        except (KeyboardInterrupt, EOFError):
            confirm = ""
        if confirm.lower() == "y":
            _op("item", "delete", creds_item, "--vault", _OP_VAULT)
            _create_creds_item(env, creds_item)
        else:
            print("  Skipping credentials item.")
    else:
        _create_creds_item(env, creds_item)

    # ── Step 2: config item ──────────────────────────────────────────────────
    cfg_item = _op_config_item(env)
    r = _op("item", "get", cfg_item, "--vault", _OP_VAULT)
    if r.returncode == 0:
        print(f"\n  Config item already exists: {cfg_item}  (skipped)")
    else:
        _create_config_item_defaults(env, cfg_item)

    # ── Step 3: risk level items (shared, no env suffix) ─────────────────────
    print()
    _create_risk_items()

    # ── Step 4: strategy items (shared, no env suffix) ───────────────────────
    print()
    _create_strategy_items()

    # ── Step 5: next steps ───────────────────────────────────────────────────
    print("\n  ─────────────────────────────────────────────────")
    if env == "dev":
        print("  Dev is ready — no API credentials required.")
        print("  Run: revt run")
    else:
        print("  Next steps:")
        print("  1. Log in to Revolut X → Settings → API → Add new key")
        print("  2. Paste the PUBLIC KEY printed above")
        print("  3. Copy the API key ID shown by Revolut X")
        print(f"  4. Run: revt ops  (to store the API key ID for {env})")
        print("  5. Run: revt api ready  (to verify)")
        print()
        print("  Optional — Telegram notifications:")
        print("  6. Create a bot via @BotFather and get the token")
        print(f"  7. revt config set TELEGRAM_BOT_TOKEN <token>  (env: {env})")
        print(f"  8. revt config set TELEGRAM_CHAT_ID <chat_id>  (env: {env})")
    print()


_RISK_ITEMS: dict[str, list[str]] = {
    "conservative": [
        "MAX_POSITION_SIZE_PCT[text]=1.5",
        "MAX_DAILY_LOSS_PCT[text]=3.0",
        "STOP_LOSS_PCT[text]=1.5",
        "TAKE_PROFIT_PCT[text]=2.5",
        "MAX_OPEN_POSITIONS[text]=3",
    ],
    "moderate": [
        "MAX_POSITION_SIZE_PCT[text]=3.0",
        "MAX_DAILY_LOSS_PCT[text]=5.0",
        "STOP_LOSS_PCT[text]=2.5",
        "TAKE_PROFIT_PCT[text]=4.0",
        "MAX_OPEN_POSITIONS[text]=5",
    ],
    "aggressive": [
        "MAX_POSITION_SIZE_PCT[text]=5.0",
        "MAX_DAILY_LOSS_PCT[text]=10.0",
        "STOP_LOSS_PCT[text]=4.0",
        "TAKE_PROFIT_PCT[text]=7.0",
        "MAX_OPEN_POSITIONS[text]=8",
    ],
}

_ORDER_TYPE_LIMIT = "ORDER_TYPE[text]=limit"
_ORDER_TYPE_MARKET = "ORDER_TYPE[text]=market"

_STRATEGY_ITEMS: dict[str, list[str]] = {
    "market_making": [
        "INTERVAL[text]=5",
        "MIN_SIGNAL_STRENGTH[text]=0.3",
        _ORDER_TYPE_LIMIT,
        "STOP_LOSS_PCT[text]=0.5",
        "TAKE_PROFIT_PCT[text]=0.3",
        "SPREAD_THRESHOLD[text]=0.0005",
        "INVENTORY_TARGET[text]=0.5",
    ],
    "momentum": [
        "INTERVAL[text]=10",
        "MIN_SIGNAL_STRENGTH[text]=0.6",
        _ORDER_TYPE_MARKET,
        "STOP_LOSS_PCT[text]=2.5",
        "TAKE_PROFIT_PCT[text]=4.0",
        "RSI_PERIOD[text]=14",
        "RSI_OVERBOUGHT[text]=70.0",
        "RSI_OVERSOLD[text]=30.0",
        "FAST_PERIOD[text]=12",
        "SLOW_PERIOD[text]=26",
    ],
    "mean_reversion": [
        "INTERVAL[text]=15",
        "MIN_SIGNAL_STRENGTH[text]=0.5",
        _ORDER_TYPE_LIMIT,
        "STOP_LOSS_PCT[text]=1.0",
        "TAKE_PROFIT_PCT[text]=1.5",
        "LOOKBACK_PERIOD[text]=20",
        "NUM_STD_DEV[text]=2.0",
        "MIN_DEVIATION[text]=0.01",
    ],
    "breakout": [
        "INTERVAL[text]=5",
        "MIN_SIGNAL_STRENGTH[text]=0.7",
        _ORDER_TYPE_MARKET,
        "STOP_LOSS_PCT[text]=3.0",
        "TAKE_PROFIT_PCT[text]=5.0",
        "RSI_PERIOD[text]=14",
        "RSI_OVERBOUGHT[text]=70.0",
        "RSI_OVERSOLD[text]=30.0",
        "LOOKBACK_PERIOD[text]=20",
        "BREAKOUT_THRESHOLD[text]=0.002",
    ],
    "range_reversion": [
        "INTERVAL[text]=15",
        "MIN_SIGNAL_STRENGTH[text]=0.5",
        _ORDER_TYPE_LIMIT,
        "STOP_LOSS_PCT[text]=1.0",
        "TAKE_PROFIT_PCT[text]=1.5",
        "RSI_PERIOD[text]=7",
        "BUY_ZONE[text]=0.20",
        "SELL_ZONE[text]=0.80",
        "RSI_CONFIRMATION_OVERSOLD[text]=40.0",
        "RSI_CONFIRMATION_OVERBOUGHT[text]=60.0",
        "MIN_RANGE_PCT[text]=0.01",
    ],
    "multi_strategy": [
        "INTERVAL[text]=10",
        "MIN_SIGNAL_STRENGTH[text]=0.55",
        _ORDER_TYPE_LIMIT,
        "MIN_CONSENSUS[text]=0.6",
        "WEIGHT_MOMENTUM[text]=0.30",
        "WEIGHT_BREAKOUT[text]=0.25",
        "WEIGHT_MARKET_MAKING[text]=0.20",
        "WEIGHT_MEAN_REVERSION[text]=0.15",
        "WEIGHT_RANGE_REVERSION[text]=0.10",
    ],
}


def _create_risk_items() -> None:
    """Create the three risk-level items in 1Password (shared, no env suffix).

    Skips items that already exist.
    """
    for level, fields in _RISK_ITEMS.items():
        item_name = f"revolut-trader-risk-{level}"
        r = _op("item", "get", item_name, "--vault", _OP_VAULT)
        if r.returncode == 0:
            print(f"  Risk item already exists: {item_name}  (skipped)")
            continue
        r = subprocess.run(
            [
                "op",
                "item",
                "create",
                "--category",
                _OP_CATEGORY,
                "--vault",
                _OP_VAULT,
                "--title",
                item_name,
                *fields,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if r.returncode == 0:
            print(f"  ✓  Risk item created: {item_name}")
        else:
            print(f"  ✗  Failed to create {item_name}: {r.stderr.strip()}")
            sys.exit(1)


def _create_strategy_items() -> None:
    """Create the six strategy items in 1Password (shared, no env suffix).

    Skips items that already exist.
    """
    for strategy, fields in _STRATEGY_ITEMS.items():
        item_name = f"revolut-trader-strategy-{strategy}"
        r = _op("item", "get", item_name, "--vault", _OP_VAULT)
        if r.returncode == 0:
            print(f"  Strategy item already exists: {item_name}  (skipped)")
            continue
        r = subprocess.run(
            [
                "op",
                "item",
                "create",
                "--category",
                _OP_CATEGORY,
                "--vault",
                _OP_VAULT,
                "--title",
                item_name,
                *fields,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if r.returncode == 0:
            print(f"  ✓  Strategy item created: {item_name}")
        else:
            print(f"  ✗  Failed to create {item_name}: {r.stderr.strip()}")
            sys.exit(1)


def _create_creds_item(env: str, creds_item: str) -> None:
    """Create the credentials 1Password item, generating keypair for int/prod."""
    if env == "dev":
        # Dev uses mock API — create placeholder item with no real keys
        fields = [
            "REVOLUT_API_KEY[concealed]=placeholder",
            "TELEGRAM_BOT_TOKEN[concealed]=placeholder",
        ]
        r = subprocess.run(
            [
                "op",
                "item",
                "create",
                "--category",
                _OP_CATEGORY,
                "--vault",
                _OP_VAULT,
                "--title",
                creds_item,
                *fields,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if r.returncode == 0:
            print(f"  ✓  Credentials item created: {creds_item}")
            print("     (dev uses mock API — no real Revolut keys needed)")
        else:
            print(f"  ✗  Failed: {r.stderr.strip()}")
            sys.exit(1)
        return

    # int / prod — generate Ed25519 keypair
    print("  Generating Ed25519 keypair…")
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            NoEncryption,
            PrivateFormat,
            PublicFormat,
        )
    except ImportError:
        print("  ✗  Missing dependency: pip install cryptography")
        sys.exit(1)

    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption(),
    ).decode()
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=Encoding.PEM,
            format=PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )

    print("  ✓  Keypair generated\n")
    print("  ┌─ PUBLIC KEY — paste this into Revolut X ──────────────────────")
    for line in public_pem.strip().splitlines():
        print(f"  │  {line}")
    print("  └───────────────────────────────────────────────────────────────\n")

    fields = [
        "REVOLUT_API_KEY[concealed]=placeholder",
        f"REVOLUT_PRIVATE_KEY[concealed]={private_pem}",
        f"REVOLUT_PUBLIC_KEY[concealed]={public_pem}",
        "TELEGRAM_BOT_TOKEN[concealed]=placeholder",
    ]
    r = subprocess.run(
        [
            "op",
            "item",
            "create",
            "--category",
            _OP_CATEGORY,
            "--vault",
            _OP_VAULT,
            "--title",
            creds_item,
            *fields,
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if r.returncode == 0:
        print(f"  ✓  Credentials item created: {creds_item}")
        print("     Private key stored in 1Password — not written to disk.")
    else:
        print(f"  ✗  Failed: {r.stderr.strip()}")
        sys.exit(1)


def _create_config_item_defaults(env: str, cfg_item: str) -> None:
    """Create the config 1Password item with all fields from config.py.

    Required fields are pre-filled with safe defaults.
    Optional fields are set to their default values so users can see and
    adjust every knob without needing to know the field names.
    """
    fields = [
        # ── Required ──────────────────────────────────────────────────────────
        "RISK_LEVEL[text]=conservative",
        "BASE_CURRENCY[text]=EUR",
        "TRADING_PAIRS[text]=BTC-EUR,ETH-EUR",
        "DEFAULT_STRATEGY[text]=market_making",
        # ── Trading mode ──────────────────────────────────────────────────────
        # paper (safe default) or live (prod only, requires confirmation)
        "TRADING_MODE[text]=paper",
        # ── Capital limits ────────────────────────────────────────────────────
        # Maximum capital the bot may use across all positions (leave blank = no cap)
        "MAX_CAPITAL[text]=",
        # ── Shutdown behaviour ────────────────────────────────────────────────
        # Trailing stop % applied to profitable positions on graceful shutdown
        "SHUTDOWN_TRAILING_STOP_PCT[text]=",
        # Hard timeout (seconds) before force-closing trailing positions on shutdown
        "SHUTDOWN_MAX_WAIT_SECONDS[text]=120",
        # ── Backtest defaults ─────────────────────────────────────────────────
        "BACKTEST_DAYS[text]=30",
        # Candle width in minutes: 1 5 15 30 60 240 1440
        "BACKTEST_INTERVAL[text]=60",
        # ── Logging ───────────────────────────────────────────────────────────
        # DEBUG INFO WARNING ERROR
        "LOG_LEVEL[text]=INFO",
        # ── Trading loop interval override ────────────────────────────────────
        # Override strategy interval (seconds); leave blank = use strategy default
        "INTERVAL[text]=",
        # ── Fees ──────────────────────────────────────────────────────────────
        "MAKER_FEE_PCT[text]=0.0",
        "TAKER_FEE_PCT[text]=0.0009",
        # ── Order size limits ─────────────────────────────────────────────────
        "MAX_ORDER_VALUE[text]=10000",
        "MIN_ORDER_VALUE[text]=10",
        # ── Telegram ──────────────────────────────────────────────────────────
        "TELEGRAM_CHAT_ID[text]=",
        # ── Data directory ────────────────────────────────────────────────────
        # Absolute path for databases, exports, and reports (leave blank = ~/revt-data)
        "DATA_DIR[text]=",
    ]
    if env != "prod":
        fields.insert(4, "INITIAL_CAPITAL[text]=10000")

    r = subprocess.run(
        [
            "op",
            "item",
            "create",
            "--category",
            _OP_CATEGORY,
            "--vault",
            _OP_VAULT,
            "--title",
            cfg_item,
            *fields,
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if r.returncode == 0:
        print(f"\n  ✓  Config item created: {cfg_item}")
        if env == "prod":
            print("     Tip: set a capital cap — revt config set MAX_CAPITAL 5000")
    else:
        print(f"\n  ✗  Failed to create config: {r.stderr.strip()}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# cmd: config
# ---------------------------------------------------------------------------


def cmd_config(args: argparse.Namespace) -> None:
    """View and manage trading configuration stored in 1Password."""
    env = _set_env()
    sub = getattr(args, "config_cmd", None) or "show"

    if sub == "show":
        _config_show(env)
    elif sub == "set":
        _config_set(env, args.key, args.value)
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

    # Validate the value before setting
    from cli.utils.validators import validate_config_value

    is_valid, error = validate_config_value(key, value)
    if not is_valid:
        print(f"  ✗  Validation error: {error}")
        print("     Use 'revt config show' to see current values")
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
        print("     Run 'revt ops init' to create the config item first.")
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
def cmd_api(args: argparse.Namespace) -> None:
    """Check Revolut X API connectivity and permissions.

    Dev environment is blocked — it uses a local mock with no real endpoints.
    """
    env = _set_env()
    if env == "dev":
        print("⚠️   API commands require a real API environment.")
        print("    Dev uses a local mock — no network calls are made.")
        print("    Switch to the main branch (int) or a tagged commit (prod).")
        sys.exit(1)

    from cli.commands.api import run_api_command

    cmd_map = {"ready": "trade-ready", "test": "test"}
    run_api_command(cmd_map[args.api_cmd])


# ---------------------------------------------------------------------------
# cmd: telegram
# ---------------------------------------------------------------------------


def cmd_telegram(args: argparse.Namespace) -> None:
    """Telegram bot utilities and always-on control plane.

    Subcommands:
      test   — send a test message to verify Telegram is configured correctly
      start  — start the always-on Telegram Control Plane process
    """
    env = _set_env()
    sub_cmd = getattr(args, "telegram_cmd", None) or "test"

    if sub_cmd == "start":
        # Check for updates (non-blocking, cached)
        _show_update_notification()

        # Deferred import — ENVIRONMENT must be set before src.config is loaded.
        from cli.commands.telegram import run_control_plane

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
    # Resolve environment and set ENVIRONMENT variable for database selection
    _set_env()

    sub = getattr(args, "db_cmd", None) or "stats"

    if sub == "stats":
        from cli.commands.db import show_stats

        show_stats()

    elif sub == "analytics":
        from cli.commands.db import show_analytics

        show_analytics(days=getattr(args, "days", 30))

    elif sub == "backtests":
        from cli.commands.db import show_backtest_results

        show_backtest_results(limit=getattr(args, "limit", 10))

    elif sub == "export":
        from cli.commands.db import export_csv

        export_csv()

    elif sub == "report":
        from cli.utils.analytics_report import generate_report

        generate_report(
            days=getattr(args, "days", 30),
            output_dir=Path(getattr(args, "output_dir", None) or (_get_data_dir() / "reports")),
        )


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
        # Use a writable temp dir for backup instead of the (potentially root-owned) binary dir
        backup_path = Path(tempfile.gettempdir()) / f"revt.backup.{os.getpid()}"

        # Backup current binary
        try:
            if current_binary.exists():
                shutil.copy2(current_binary, backup_path)
                print(f"✓ Backed up current binary to: {backup_path}")
        except OSError as e:
            print(f"⚠️  Warning: Failed to backup current binary: {e}")
            print("   Continuing with update...")

        # Replace with new binary.
        # On Linux, shutil.move / os.replace raise ETXTBSY when the target is a running
        # executable.  The safe pattern is: unlink the old inode first (the running process
        # keeps its open file-descriptor), then copy the new binary into place.
        try:
            # Only suppress FileNotFoundError — PermissionError must propagate so we
            # can detect it and suggest `sudo` below.
            with contextlib.suppress(FileNotFoundError):
                current_binary.unlink()
            shutil.copy2(str(tmp_path), str(current_binary))
            current_binary.chmod(0o755)
            tmp_path.unlink(missing_ok=True)
        except OSError as e:
            # Try to restore backup if copy failed
            if backup_path.exists():
                try:
                    shutil.copy2(backup_path, current_binary)
                    current_binary.chmod(0o755)
                    print(f"⚠️  Update failed, restored backup: {e}")
                except Exception:
                    # Backup restore failed - not critical since we're raising the main error
                    pass  # nosec B110 — best-effort restore; original error raised below
            if e.errno in (errno.EPERM, errno.EACCES):
                raise RuntimeError(
                    f"Failed to replace binary: {e}\n"
                    f"   The binary at {current_binary} is owned by root.\n"
                    f"   Re-run with sudo:  sudo {current_binary} update"
                ) from e
            raise RuntimeError(f"Failed to replace binary: {e}") from e

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
        Tuple of (current_version, latest_version) or (None, None) if unavailable.
    """
    current_version = _get_current_version_from_pyproject()
    latest_tag = _get_latest_github_release(timeout=10)
    # Latest tag comes with 'v' prefix from some callers, strip it
    if latest_tag and latest_tag.startswith("v"):
        latest_tag = latest_tag.lstrip("v")
    return current_version, latest_tag


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


def _verify_git_repository() -> None:
    """Verify we're in a git repository, exit if not."""
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


def _get_git_commits(local_ref: str, remote_ref: str) -> tuple[str, str]:
    """Get local and remote commit SHAs."""
    local_commit = subprocess.run(
        ["git", "rev-parse", local_ref],
        capture_output=True,
        text=True,
        check=True,
        cwd=_ROOT,
    ).stdout.strip()

    remote_commit = subprocess.run(
        ["git", "rev-parse", remote_ref],
        capture_output=True,
        text=True,
        check=True,
        cwd=_ROOT,
    ).stdout.strip()

    return local_commit, remote_commit


def _stash_local_changes() -> bool:
    """Stash local changes if any exist.

    Returns:
        True if changes were stashed, False otherwise.
    """
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        cwd=_ROOT,
    )

    if status.stdout.strip():
        print("📦 Stashing local changes...")
        stash_result = subprocess.run(
            ["git", "stash", "push", "-m", "revt update"],
            capture_output=True,
            text=True,
            cwd=_ROOT,
        )
        if stash_result.returncode != 0:
            print(f"❌ Failed to stash changes:\n{stash_result.stderr.strip()}")
            print("\n💡 Suggestions:")
            print("   - Commit your changes: git commit -am 'WIP'")
            print("   - Discard changes: git reset --hard")
            print("   - Resolve conflicts and try again")
            sys.exit(1)
        print("✓ Changes stashed")
        print()
        return True

    return False


def _update_from_source() -> None:
    """Update when running from source (git repository)."""
    print("🔄 Checking for updates...")
    print()

    _verify_git_repository()

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
    local_commit, remote_commit = _get_git_commits("HEAD", f"origin/{current_branch}")

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

    had_stashed_changes = _stash_local_changes()

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
        if had_stashed_changes:
            print("\n🔄 Re-applying stashed changes...")
            pop_result = subprocess.run(
                ["git", "stash", "pop"],
                capture_output=True,
                text=True,
                cwd=_ROOT,
            )
            if pop_result.returncode != 0:
                print(f"⚠️  Failed to re-apply stash:\n{pop_result.stderr}")
                print("💡 Your changes are still in the stash. Use: git stash pop")
        sys.exit(1)

    print("✓ Pulled latest changes")
    if result.stdout.strip():
        print(result.stdout)

    # Re-apply stashed changes if any
    if had_stashed_changes:
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
            print("⚠️  Conflicts detected while re-applying changes")
            print(pop_result.stdout)
            print("\n💡 Resolve conflicts manually:")
            print("   1. git status  (view conflicts)")
            print("   2. Edit conflicting files")
            print("   3. git add <files>")
            print("   4. git stash drop  (once resolved)")

    # Update dependencies
    print()
    print("📦 Updating dependencies...")
    subprocess.run(["uv", "sync", "--extra", "dev"], check=True, cwd=_ROOT)
    print("✓ Dependencies updated")

    print()
    print("✅ Update complete!")
    print()
    print("ℹ️  Your revt-data/ folder and 1Password config are untouched.")


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

    The revt-data/ folder and all 1Password configuration remain untouched.
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


def _build_parser() -> argparse.ArgumentParser:
    """Build and return the full ``revt`` argument parser."""
    parser = argparse.ArgumentParser(
        prog="revt",
        description="Revolut Trader — user-facing CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  # Credentials & Configuration
  revt ops init                               create credentials + config; generate keypair
  revt ops                                    store your Revolut API key
  revt ops --show                             show credentials + config (masked)
  revt ops --status                           check 1Password connection
  revt config show                            view trading configuration
  revt config set RISK_LEVEL aggressive       change risk level
  revt config set MAX_CAPITAL 5000            cap how much the bot can trade
  revt config delete MAX_CAPITAL              remove capital cap

  # Trading & Backtesting (env auto-detected from git branch)
  revt run                                    start trading (paper mode by default)
  revt run --strategy momentum --risk moderate
  revt run --mode live --confirm-live         LIVE TRADING — only on tagged/prod commit
  revt backtest                               30-day backtest
  revt backtest --compare                     compare all strategies side-by-side
  revt backtest --matrix                      all strategies × all risk levels
  revt backtest --matrix --real-data          matrix with real API data (any branch)

  # API Commands (requires int or prod env — switch to main or tagged commit)
  revt api test                               verify API connection is working
  revt api ready                              check API permissions (view + trade)

  # Database & Analytics
  revt db stats                               database overview
  revt db analytics --days 60                 trading analytics
  revt db backtests                           view backtest results
  revt db export                              export all data to CSV
  revt db report                              full analytics report + charts

  # Telegram Control Plane
  revt telegram test                          verify Telegram is configured
  revt telegram start                         start always-on control plane

  # Updates
  revt update                                 update revt (preserves revt-data/ and config)

environment variables:
  REVT_SKIP_UPDATE_CHECK=1                    disable update notifications

environment detection (run / telegram — not overridable):
  tagged commit on main → prod  (real API, paper by default)
  main branch           → int   (real API, paper mode)
  feature branch        → dev   (mock API, paper mode)
  frozen binary         → prod
""",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # ── run ──────────────────────────────────────────────────────────────────
    p_run = sub.add_parser("run", help="Start the trading bot")
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
        help="⚠️  DANGEROUS: Skip confirmation for live mode (only use in trusted automation scripts)",
    )
    p_run.set_defaults(func=cmd_run)

    # ── backtest ──────────────────────────────────────────────────────────────
    p_bt = sub.add_parser("backtest", help="Backtest strategies on historical data")
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
        "--risk-levels",
        dest="risk_levels",
        default=None,
        help="Comma-separated risk levels for --compare (e.g. conservative,moderate,aggressive)",
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
    p_bt.add_argument(
        "--real-data",
        dest="real_data",
        action="store_true",
        default=False,
        help="Use real API data even on a dev branch (feature branch development)",
    )
    p_bt.set_defaults(func=cmd_backtest)

    # ── ops ───────────────────────────────────────────────────────────────────
    p_ops = sub.add_parser("ops", help="Manage API credentials in 1Password")
    ops_sub = p_ops.add_subparsers(dest="ops_cmd", metavar=_SUBCOMMAND_METAVAR)
    ops_sub.add_parser(
        "init",
        help="Create credentials + config placeholders; auto-generate Ed25519 keypair",
    )
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
    cfg_sub = p_cfg.add_subparsers(dest="config_cmd", metavar=_SUBCOMMAND_METAVAR)

    cfg_sub.add_parser("show", help="Show current configuration")

    p_cfg_set = cfg_sub.add_parser("set", help="Set a configuration value")
    p_cfg_set.add_argument("key", help="Config key, e.g. RISK_LEVEL")
    p_cfg_set.add_argument("value", help="New value")

    p_cfg_del = cfg_sub.add_parser("delete", help="Remove a configuration key")
    p_cfg_del.add_argument("key", help="Config key to remove")

    p_cfg.set_defaults(func=cmd_config)

    # ── api ───────────────────────────────────────────────────────────────────
    p_api = sub.add_parser(
        "api",
        help="Check API connectivity and permissions (requires int or prod env)",
    )
    p_api.add_argument(
        "api_cmd",
        metavar="<command>",
        choices=["test", "ready"],
        help="test — verify connection · ready — check view + trade permissions",
    )
    p_api.set_defaults(func=cmd_api)

    # ── db ────────────────────────────────────────────────────────────────────
    p_db = sub.add_parser("db", help="Database management and analytics")
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
        default=None,
        help="Output directory (default: ~/revt-data/reports or DATA_DIR/reports from 1Password)",
    )

    p_db.set_defaults(func=cmd_db)

    # ── telegram ──────────────────────────────────────────────────────────────
    p_tg = sub.add_parser("telegram", help="Telegram bot utilities and always-on control plane")
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
        help="Update revt to the latest version (preserves revt-data/ folder and 1Password config)",
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
