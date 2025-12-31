"""1Password integration for secure credential management.

This module provides 1Password-only credential management.
No .env file fallback - 1Password is required for all credentials.
"""

import json
import subprocess
import time
from threading import Lock

from loguru import logger


class OnePasswordClient:
    """Client for interacting with 1Password CLI."""

    def __init__(
        self,
        vault_name: str = "revolut-trader",
        item_name: str = "revolut-trader-credentials",
    ):
        """Initialize 1Password client.

        Args:
            vault_name: Name of the 1Password vault
            item_name: Name of the item containing credentials
        """
        self.vault_name = vault_name
        self.item_name = item_name
        self._is_available: bool | None = None

    def is_available(self) -> bool:
        """Check if 1Password CLI is available and signed in.

        Returns:
            True if 1Password CLI is available and ready to use
        """
        if self._is_available is not None:
            return self._is_available

        try:
            # Check if op command exists
            result = subprocess.run(
                ["op", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                self._is_available = False
                return False

            # Check if signed in
            result = subprocess.run(
                ["op", "account", "list"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                logger.warning("1Password CLI installed but not signed in. Run: eval $(op signin)")
                self._is_available = False
                return False

            self._is_available = True
            logger.debug("1Password CLI is available and ready")
            return True

        except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
            logger.debug(f"1Password CLI not available: {e}")
            self._is_available = False
            return False

    def get_field(self, field_name: str) -> str | None:
        """Get a specific field value from 1Password.

        Args:
            field_name: The field label to retrieve

        Returns:
            The field value or None if not found
        """
        if not self.is_available():
            return None

        try:
            result = subprocess.run(
                [
                    "op",
                    "item",
                    "get",
                    self.item_name,
                    "--vault",
                    self.vault_name,
                    "--fields",
                    field_name,
                    "--reveal",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                value = result.stdout.strip()
                if value:
                    logger.debug(f"Retrieved {field_name} from 1Password")
                    return value

            logger.debug(f"Field {field_name} not found in 1Password")
            return None

        except (subprocess.TimeoutExpired, Exception) as e:
            logger.warning(f"Error retrieving {field_name} from 1Password: {e}")
            return None

    def get_all_fields(self) -> dict[str, str]:
        """Get all fields from 1Password item.

        Returns:
            Dictionary of field names and values
        """
        if not self.is_available():
            return {}

        try:
            # Get the item in JSON format
            result = subprocess.run(
                [
                    "op",
                    "item",
                    "get",
                    self.item_name,
                    "--vault",
                    self.vault_name,
                    "--format",
                    "json",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                logger.warning(f"Item {self.item_name} not found in 1Password")
                return {}

            item_data = json.loads(result.stdout)
            fields = {}

            # Extract fields
            for field in item_data.get("fields", []):
                label = field.get("label")
                value = field.get("value")
                if label and value:
                    fields[label] = value

            logger.info(f"Retrieved {len(fields)} fields from 1Password")
            return fields

        except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
            logger.warning(f"Error retrieving fields from 1Password: {e}")
            return {}

    def set_field(self, field_name: str, value: str) -> bool:
        """Set a field value in 1Password.

        Args:
            field_name: The field label to set
            value: The value to set

        Returns:
            True if successful, False otherwise
        """
        if not self.is_available():
            return False

        try:
            result = subprocess.run(
                [
                    "op",
                    "item",
                    "edit",
                    self.item_name,
                    "--vault",
                    self.vault_name,
                    f"{field_name}[concealed]={value}",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                logger.info(f"Updated {field_name} in 1Password")
                return True

            logger.warning(f"Failed to update {field_name} in 1Password")
            return False

        except (subprocess.TimeoutExpired, Exception) as e:
            logger.warning(f"Error setting {field_name} in 1Password: {e}")
            return False


class ConfigCache:
    """Fast config cache with batch fetching from 1Password.

    Fetches ALL config values in ONE 1Password call and caches them
    in memory with TTL. This is ~5-10x faster than individual calls.
    """

    def __init__(self, ttl_seconds: int = 300):
        """Initialize config cache.

        Args:
            ttl_seconds: Time-to-live for cache in seconds (default: 5 minutes)
        """
        self._cache: dict[str, str] = {}
        self._cache_time: float | None = None
        self._ttl = ttl_seconds
        self._lock = Lock()  # Thread-safe cache access
        self._client = OnePasswordClient(
            vault_name="revolut-trader",
            item_name="revolut-trader-config",
        )

    def get(self, key: str, default: str | None = None) -> str | None:
        """Get config value from cache (fetches from 1Password if stale).

        Args:
            key: Configuration key
            default: Default value if not found

        Returns:
            Configuration value or default
        """
        with self._lock:
            # Refresh cache if expired or empty
            if self._is_cache_stale():
                self._refresh_cache()

            # Return from cache or default
            return self._cache.get(key, default)

    def _is_cache_stale(self) -> bool:
        """Check if cache needs refresh."""
        if not self._cache or self._cache_time is None:
            return True
        return (time.time() - self._cache_time) > self._ttl

    def _refresh_cache(self) -> None:
        """Refresh cache by batch-fetching all config from 1Password."""
        if not self._client.is_available():
            logger.debug("1Password not available, cache not refreshed")
            return

        # Batch fetch ALL fields in ONE call
        start_time = time.time()
        all_fields = self._client.get_all_fields()

        if all_fields:
            self._cache = all_fields
            self._cache_time = time.time()
            elapsed = (time.time() - start_time) * 1000  # ms
            logger.info(
                f"✅ Config cache refreshed: {len(all_fields)} fields in {elapsed:.0f}ms "
                f"(cached for {self._ttl}s)"
            )
        else:
            logger.warning("Failed to refresh config cache from 1Password")

    def invalidate(self) -> None:
        """Force cache invalidation (next get() will refresh)."""
        with self._lock:
            self._cache_time = None
            logger.debug("Config cache invalidated")

    def get_cache_stats(self) -> dict:
        """Get cache statistics for debugging."""
        with self._lock:
            age = (time.time() - self._cache_time) if self._cache_time else None
            return {
                "cached_keys": len(self._cache),
                "cache_age_seconds": age,
                "ttl_seconds": self._ttl,
                "is_stale": self._is_cache_stale(),
            }


# Global config cache instance (singleton)
_config_cache = ConfigCache(ttl_seconds=300)  # 5 minute TTL


def get_config(
    key: str,
    default: str | None = None,
) -> str | None:
    """Get a configuration value from 1Password with intelligent caching.

    Uses a fast in-memory cache that batch-fetches ALL config in ONE 1Password call.
    Much faster than individual calls (~5-10x speedup).

    Cache TTL: 5 minutes (configurable in ConfigCache)

    Args:
        key: The configuration key (e.g., "TRADING_MODE", "BASE_CURRENCY")
        default: Default value if not found in 1Password

    Returns:
        The configuration value from 1Password cache, or default if not found

    Examples:
        >>> get_config("TRADING_MODE", "paper")
        "live"  # If set in 1Password
        >>> get_config("BASE_CURRENCY", "EUR")
        "EUR"  # Falls back to default if not in 1Password
    """
    # Use global cache - batch fetches all config in one call
    return _config_cache.get(key, default)


def invalidate_config_cache() -> None:
    """Invalidate the config cache (force refresh on next access).

    Useful for testing or when you know config has changed in 1Password.
    """
    _config_cache.invalidate()
    logger.info("Config cache invalidated - will refresh on next access")


def get_config_cache_stats() -> dict:
    """Get config cache statistics for debugging.

    Returns:
        Dictionary with cache stats (keys, age, TTL, staleness)
    """
    return _config_cache.get_cache_stats()


def get_credential(
    key: str,
    default: str | None = None,
) -> str | None:
    """Get a credential from 1Password only (no .env fallback).

    Args:
        key: The credential key
        default: Default value if not found

    Returns:
        The credential value or default

    Raises:
        RuntimeError: If 1Password is not available (when no default provided)
    """
    client = OnePasswordClient()

    if not client.is_available():
        if default is not None:
            logger.warning(f"1Password not available, using default for {key}")
            return default
        raise RuntimeError(
            "1Password is required but not available. Please:\n"
            "1. Install 1Password CLI: brew install --cask 1password-cli\n"
            "2. Sign in: eval $(op signin)\n"
            "3. Setup credentials: make ops"
        )

    value = client.get_field(key)
    if value:
        return value

    if default is not None:
        return default

    raise RuntimeError(
        f"Credential '{key}' not found in 1Password and no default provided. "
        f"Please store it: op item edit revolut-trader-credentials --vault revolut-trader {key}[concealed]=YOUR_VALUE"
    )
