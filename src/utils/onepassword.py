"""1Password integration - the single source for all credentials and configuration.

All credentials and configuration are fetched exclusively from 1Password via a
service account (``OP_SERVICE_ACCOUNT_TOKEN`` environment variable).

Authentication
--------------
Set ``OP_SERVICE_ACCOUNT_TOKEN`` before running the bot or any CLI command::

    export OP_SERVICE_ACCOUNT_TOKEN=ops_xxxx...

The ``op`` CLI picks up the token automatically — no interactive sign-in,
no biometric prompts, no session expiry to manage.

Public API:
    get(key)          - required field; raises RuntimeError if missing
    get_optional(key) - optional field; returns None if missing
    is_available()    - True if 1Password CLI is installed and authenticated
    set_credential(item, field, value) - store a value (used for setup only)
    invalidate_cache()  - force refresh on next access
"""

import json
import os
import subprocess
from threading import Lock

from loguru import logger

VAULT = "revolut-trader"

# Legacy constants kept for backward-compatible imports (e.g. db_encryption.py).
# Prefer the functions get_credentials_item() / get_config_item() for new code.
CREDENTIALS_ITEM = "revolut-trader-credentials"
CONFIG_ITEM = "revolut-trader-config"


def get_credentials_item(env: str | None = None) -> str:
    """Return the environment-suffixed credentials item name.

    Args:
        env: Environment string (dev, int, prod).  Falls back to
             ``os.environ["ENVIRONMENT"]`` if not provided.

    Returns:
        1Password item name, e.g. ``"revolut-trader-credentials-dev"``.
    """
    if env is None:
        env = os.environ.get("ENVIRONMENT", "dev")
    return f"revolut-trader-credentials-{env}"


def get_config_item(env: str | None = None) -> str:
    """Return the environment-suffixed config item name.

    Args:
        env: Environment string (dev, int, prod).  Falls back to
             ``os.environ["ENVIRONMENT"]`` if not provided.

    Returns:
        1Password item name, e.g. ``"revolut-trader-config-dev"``.
    """
    if env is None:
        env = os.environ.get("ENVIRONMENT", "dev")
    return f"revolut-trader-config-{env}"


def _fetch_item_fields(item_name: str) -> dict[str, str]:
    """Fetch all fields from a 1Password item as a flat ``{label: value}`` dict.

    Args:
        item_name: Name of the item in the vault.

    Returns:
        Dict of field labels to values; empty dict on any failure.
    """
    output = _run_op("item", "get", item_name, "--vault", VAULT, "--format", "json")
    if not output:
        logger.warning(f"1Password item '{item_name}' not found or empty")
        return {}
    try:
        item_data = json.loads(output)
        return {
            field["label"]: field["value"]
            for field in item_data.get("fields", [])
            if field.get("label") and field.get("value") and not str(field["value"]).startswith("<")
        }
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Failed to parse 1Password item '{item_name}': {e}")
        return {}


def _run_op(*args: str, timeout: int = 10) -> str | None:
    """Execute an ``op`` CLI command.

    Authentication is handled automatically via the ``OP_SERVICE_ACCOUNT_TOKEN``
    environment variable — no ``--session`` flag is required.

    Args:
        *args: Arguments forwarded to the ``op`` CLI.
        timeout: Subprocess timeout in seconds.

    Returns:
        stdout on success, ``None`` on any failure.
    """
    cmd = ["op", *args]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL
        )
        return result.stdout if result.returncode == 0 else None
    except Exception as e:
        logger.debug(f"op command failed: {e}")
        return None


class _VaultCache:
    """Single in-memory cache for all 1Password values (credentials + config).

    Batch-fetches both vault items (credentials + config) on first access and
    merges them into one flat dict.  Cache is held for the lifetime of the
    process — call ``invalidate()`` to force a refresh.

    Authentication is handled entirely by the ``OP_SERVICE_ACCOUNT_TOKEN``
    environment variable — no session token management is needed.
    """

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}
        self._lock = Lock()
        self._signed_in: bool | None = None

    def is_available(self) -> bool:
        """Check if the 1Password CLI is installed and authenticated.

        Uses ``op whoami`` which validates the service account token.
        Result is cached for the lifetime of the process.
        """
        if self._signed_in is None:
            if _run_op("--version", timeout=5) is None:
                self._signed_in = False
            else:
                self._signed_in = _run_op("whoami", timeout=5) is not None
                if not self._signed_in:
                    logger.warning(
                        "1Password CLI installed but not authenticated. "
                        "Set OP_SERVICE_ACCOUNT_TOKEN and try again."
                    )
        return self._signed_in

    def _is_stale(self) -> bool:
        return not self._cache

    def _refresh(self) -> None:
        """Batch-fetch all fields from both vault items (environment-aware)."""
        if not self.is_available():
            raise RuntimeError(
                "1Password is required but not available.\n"
                "1. Install: brew install --cask 1password-cli\n"
                "2. Set:     export OP_SERVICE_ACCOUNT_TOKEN=ops_xxxx...\n"
                "3. Setup:   make ops"
            )

        creds_item = get_credentials_item()
        conf_item = get_config_item()

        credentials = _fetch_item_fields(creds_item)
        config = _fetch_item_fields(conf_item)
        merged = {**credentials, **config}

        if not merged:
            env = os.environ.get("ENVIRONMENT", "dev")
            raise RuntimeError(
                f"No fields found in 1Password vault '{VAULT}' "
                f"for environment '{env}'.\n"
                f"Run: make ops ENV={env} && make opconfig-init ENV={env}"
            )

        self._cache = merged
        env = os.environ.get("ENVIRONMENT", "dev")
        logger.info(f"1Password cache loaded ({env}): {len(merged)} fields")

    def get(self, key: str) -> str:
        """Get a required value; raises ``RuntimeError`` if missing."""
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
        """Get an optional value; returns ``None`` if missing."""
        try:
            with self._lock:
                if self._is_stale():
                    self._refresh()
            return self._cache.get(key)
        except RuntimeError:
            return None

    def set_credential(self, item_name: str, field_name: str, value: str) -> bool:
        """Store a concealed value in a 1Password item."""
        result = _run_op(
            "item", "edit", item_name, "--vault", VAULT, f"{field_name}[concealed]={value}"
        )
        if result is not None:
            with self._lock:
                self._cache[field_name] = value
            logger.info(f"Stored '{field_name}' in 1Password item '{item_name}'")
            return True
        logger.warning(f"Failed to store '{field_name}' in 1Password item '{item_name}'")
        return False

    def invalidate(self) -> None:
        """Force cache refresh on next access."""
        with self._lock:
            self._cache.clear()
        logger.debug("1Password cache invalidated")


# Module-level singleton — the ONLY place in the codebase that talks to 1Password.
_vault = _VaultCache()


def get(key: str) -> str:
    """Get any required credential or configuration value from 1Password.

    Args:
        key: Field name (e.g., ``"REVOLUT_API_KEY"``, ``"TRADING_MODE"``).

    Returns:
        The field value from 1Password.

    Raises:
        RuntimeError: If 1Password is unavailable or the key is not found.
    """
    return _vault.get(key)


def get_optional(key: str) -> str | None:
    """Get an optional credential or configuration value from 1Password.

    Returns ``None`` instead of raising if the key is not found.
    Use this for optional features.

    Args:
        key: Field name.

    Returns:
        The field value, or ``None`` if not found.
    """
    return _vault.get_optional(key)


def is_available() -> bool:
    """Check if 1Password CLI is installed and authenticated via service account."""
    return _vault.is_available()


def set_credential(item_name: str, field_name: str, value: str) -> bool:
    """Store a concealed value in 1Password. Used for initial setup only.

    Args:
        item_name: The 1Password item name (e.g., ``CREDENTIALS_ITEM``).
        field_name: The field label.
        value: The value to store.

    Returns:
        ``True`` if successful.
    """
    return _vault.set_credential(item_name, field_name, value)


def invalidate_cache() -> None:
    """Force vault cache refresh on next access."""
    _vault.invalidate()
