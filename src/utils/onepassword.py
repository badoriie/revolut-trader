"""1Password integration - the single source for all credentials and configuration.

All credentials and configuration are fetched exclusively from 1Password.
No defaults, no environment variable fallbacks, no alternative code paths.

Public API:
    get(key)          - required field; raises RuntimeError if missing
    get_optional(key) - optional field; returns None if missing
    is_available()    - True if 1Password CLI is installed and signed in
    set_credential(item, field, value) - store a value (used for setup only)
    invalidate_cache()  - force refresh on next access
"""

import json
import subprocess
import time
from threading import Lock

from loguru import logger

VAULT = "revolut-trader"
CREDENTIALS_ITEM = "revolut-trader-credentials"
CONFIG_ITEM = "revolut-trader-config"


def _run_op(*args: str, timeout: int = 10) -> str | None:
    """Execute op CLI command. Returns stdout on success, None on any failure."""
    try:
        result = subprocess.run(
            ["op", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout if result.returncode == 0 else None
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
        logger.debug(f"op command failed: {e}")
        return None


def _fetch_item_fields(item_name: str) -> dict[str, str]:
    """Fetch all fields from a 1Password item as a flat dict."""
    output = _run_op("item", "get", item_name, "--vault", VAULT, "--format", "json")
    if not output:
        logger.warning(f"1Password item '{item_name}' not found or empty")
        return {}
    try:
        item_data = json.loads(output)
        return {
            field["label"]: field["value"]
            for field in item_data.get("fields", [])
            if field.get("label") and field.get("value")
        }
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Failed to parse 1Password item '{item_name}': {e}")
        return {}


class _VaultCache:
    """Single in-memory cache for all 1Password values (credentials + config).

    Batch-fetches from both items on each refresh cycle and merges them.
    Thread-safe via Lock. Cache TTL: 5 minutes.
    """

    TTL = 300  # seconds

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}
        self._cache_time: float | None = None
        self._lock = Lock()
        self._signed_in: bool | None = None

    def is_available(self) -> bool:
        """Check if 1Password CLI is installed and the user is signed in."""
        if self._signed_in is None:
            if _run_op("--version", timeout=5) is None:
                self._signed_in = False
            else:
                self._signed_in = _run_op("account", "list", timeout=5) is not None
                if not self._signed_in:
                    logger.warning("1Password CLI installed but not signed in. Run: eval $(op signin)")
        return self._signed_in

    def _is_stale(self) -> bool:
        return (
            not self._cache
            or self._cache_time is None
            or (time.time() - self._cache_time) > self.TTL
        )

    def _refresh(self) -> None:
        """Batch-fetch all fields from both 1Password items and merge into cache."""
        if not self.is_available():
            raise RuntimeError(
                "1Password is required but not available.\n"
                "1. Install: brew install --cask 1password-cli\n"
                "2. Sign in: eval $(op signin)\n"
                "3. Setup credentials: make ops"
            )

        credentials = _fetch_item_fields(CREDENTIALS_ITEM)
        config = _fetch_item_fields(CONFIG_ITEM)
        merged = {**credentials, **config}

        if not merged:
            raise RuntimeError(
                f"No fields found in 1Password vault '{VAULT}'.\n"
                "Run: make ops && make opconfig-init"
            )

        self._cache = merged
        self._cache_time = time.time()
        logger.info(f"1Password cache refreshed: {len(merged)} fields loaded")

    def get(self, key: str) -> str:
        """Get a required value. Raises RuntimeError if 1Password unavailable or key missing."""
        with self._lock:
            if self._is_stale():
                self._refresh()
            value = self._cache.get(key)

        if not value:
            raise RuntimeError(
                f"{key} not found in 1Password vault '{VAULT}'.\n"
                f"Run: make opconfig-set KEY={key} VALUE=<value>"
            )
        return value

    def get_optional(self, key: str) -> str | None:
        """Get an optional value. Returns None if 1Password unavailable or key missing."""
        try:
            with self._lock:
                if self._is_stale():
                    self._refresh()
            return self._cache.get(key)
        except RuntimeError:
            return None

    def set_credential(self, item_name: str, field_name: str, value: str) -> bool:
        """Store a concealed value in a 1Password item. Invalidates cache on success."""
        result = _run_op(
            "item", "edit", item_name,
            "--vault", VAULT,
            f"{field_name}[concealed]={value}",
        )
        if result is not None:
            with self._lock:
                self._cache_time = None  # Invalidate so next read picks up the new value
            logger.info(f"Stored '{field_name}' in 1Password item '{item_name}'")
            return True
        logger.warning(f"Failed to store '{field_name}' in 1Password item '{item_name}'")
        return False

    def invalidate(self) -> None:
        """Force cache refresh on next access."""
        with self._lock:
            self._cache_time = None
        logger.debug("1Password cache invalidated")


# Module-level singleton — the ONLY place in the codebase that talks to 1Password.
_vault = _VaultCache()


def get(key: str) -> str:
    """Get any required credential or configuration value from 1Password.

    Args:
        key: Field name (e.g., "REVOLUT_API_KEY", "TRADING_MODE")

    Returns:
        The field value from 1Password

    Raises:
        RuntimeError: If 1Password is unavailable or the key is not found
    """
    return _vault.get(key)


def get_optional(key: str) -> str | None:
    """Get an optional credential or configuration value from 1Password.

    Returns None instead of raising if the key is not found.
    Use this for optional features (e.g., Telegram notifications).

    Args:
        key: Field name (e.g., "TELEGRAM_BOT_TOKEN")

    Returns:
        The field value or None if not found
    """
    return _vault.get_optional(key)


def is_available() -> bool:
    """Check if 1Password CLI is installed and the user is signed in."""
    return _vault.is_available()


def set_credential(item_name: str, field_name: str, value: str) -> bool:
    """Store a concealed value in 1Password. Used for initial setup only.

    Args:
        item_name: The 1Password item name (e.g., CREDENTIALS_ITEM or CONFIG_ITEM)
        field_name: The field label
        value: The value to store

    Returns:
        True if successful
    """
    return _vault.set_credential(item_name, field_name, value)


def invalidate_cache() -> None:
    """Force cache refresh on next access."""
    _vault.invalidate()