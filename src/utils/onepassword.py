"""1Password integration - the single source for all credentials and configuration.

All credentials and configuration are fetched exclusively from 1Password.
No defaults, no environment variable fallbacks, no alternative code paths.

Session token caching
---------------------
``_VaultCache`` calls ``op signin --raw`` once to obtain a 30-minute session
token and passes it via ``--session`` to every subsequent ``op`` command.
This means the biometric prompt (Touch ID / Face ID) appears **at most once
per 29-minute window** regardless of how many credentials are fetched.

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

# Session token is valid for 30 minutes in 1Password.
# We refresh at 29 minutes to avoid using an expired token.
_SESSION_TTL = 1740  # seconds (29 minutes)

# Vault cache TTL matches the session token lifetime so a single sign-in
# covers the entire cache window.
_CACHE_TTL = 1740  # seconds (29 minutes)


def _fetch_item_fields(item_name: str, session_token: str | None = None) -> dict[str, str]:
    """Fetch all fields from a 1Password item as a flat ``{label: value}`` dict.

    Args:
        item_name: Name of the item in the vault.
        session_token: Optional session token to avoid biometric re-prompt.

    Returns:
        Dict of field labels to values; empty dict on any failure.
    """
    output = _run_op(
        "item",
        "get",
        item_name,
        "--vault",
        VAULT,
        "--format",
        "json",
        session_token=session_token,
    )
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


def _run_op(*args: str, timeout: int = 10, session_token: str | None = None) -> str | None:
    """Execute an ``op`` CLI command.

    Passes ``--session <token>`` when a session token is available so that
    no additional biometric prompts are required.

    Args:
        *args: Arguments forwarded to the ``op`` CLI.
        timeout: Subprocess timeout in seconds.
        session_token: Optional 1Password session token from ``op signin --raw``.

    Returns:
        stdout on success, ``None`` on any failure.
    """
    cmd = ["op"]
    if session_token:
        cmd += ["--session", session_token]
    cmd += list(args)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL
        )
        return result.stdout if result.returncode == 0 else None
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
        logger.debug(f"op command failed: {e}")
        return None


class _VaultCache:
    """Single in-memory cache for all 1Password values (credentials + config).

    Sign-in strategy
    ~~~~~~~~~~~~~~~~
    On the first access (or after the session token expires), calls
    ``op signin --raw`` to obtain a fresh 30-minute session token.  All
    subsequent ``op item get / edit`` calls receive this token via
    ``--session``, so the biometric prompt is shown **at most once per
    29-minute window**.

    Vault data strategy
    ~~~~~~~~~~~~~~~~~~~
    Batch-fetches both items (credentials + config) in a single refresh cycle
    and merges them into one flat dict.  Cache TTL matches the session token
    lifetime (29 minutes).
    """

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}
        self._cache_time: float | None = None
        self._lock = Lock()
        self._signed_in: bool | None = None
        self._session_token: str | None = None
        self._session_time: float | None = None

    # ------------------------------------------------------------------
    # Session token management
    # ------------------------------------------------------------------

    def _session_is_fresh(self) -> bool:
        """Return True if the cached session token is still valid."""
        return (
            self._session_token is not None
            and self._session_time is not None
            and (time.time() - self._session_time) < _SESSION_TTL
        )

    def _ensure_session(self) -> str | None:
        """Return a valid session token, signing in if necessary.

        ``op signin --raw`` is called at most once per ``_SESSION_TTL`` window.
        With 1Password app CLI integration the biometric prompt appears in the
        app (Touch ID / Face ID) rather than blocking the terminal.

        Returns:
            Session token string, or ``None`` if sign-in is unavailable.
        """
        if self._session_is_fresh():
            return self._session_token

        token = _run_op("signin", "--raw", timeout=60)
        if token and token.strip():
            self._session_token = token.strip()
            self._session_time = time.time()
            logger.debug("1Password session token obtained (valid for 29 minutes)")
            return self._session_token

        return None

    # ------------------------------------------------------------------
    # Availability check
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Check if the 1Password CLI is installed and the user is signed in.

        Result is cached for the lifetime of the process — the CLI either
        exists or it doesn't.
        """
        if self._signed_in is None:
            if _run_op("--version", timeout=5) is None:
                self._signed_in = False
            else:
                # Use account list (no biometric required) to confirm sign-in
                self._signed_in = _run_op("account", "list", timeout=5) is not None
                if not self._signed_in:
                    logger.warning(
                        "1Password CLI installed but not signed in. Run: eval $(op signin)"
                    )
        return self._signed_in

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def _is_stale(self) -> bool:
        return (
            not self._cache
            or self._cache_time is None
            or (time.time() - self._cache_time) > _CACHE_TTL
        )

    def _refresh(self) -> None:
        """Sign in (if needed) then batch-fetch all fields from both items."""
        if not self.is_available():
            raise RuntimeError(
                "1Password is required but not available.\n"
                "1. Install: brew install --cask 1password-cli\n"
                "2. Sign in: eval $(op signin)\n"
                "3. Setup credentials: make ops"
            )

        token = self._ensure_session()

        credentials = _fetch_item_fields(CREDENTIALS_ITEM, token)
        config = _fetch_item_fields(CONFIG_ITEM, token)
        merged = {**credentials, **config}

        if not merged:
            raise RuntimeError(
                f"No fields found in 1Password vault '{VAULT}'.\n"
                "Run: make ops && make opconfig-init"
            )

        self._cache = merged
        self._cache_time = time.time()
        logger.info(f"1Password cache refreshed: {len(merged)} fields loaded")

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

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
        """Store a concealed value in a 1Password item using the cached session token."""
        token = self._ensure_session()
        result = _run_op(
            "item",
            "edit",
            item_name,
            "--vault",
            VAULT,
            f"{field_name}[concealed]={value}",
            session_token=token,
        )
        if result is not None:
            with self._lock:
                self._cache[field_name] = value  # Update cache in-place
                # No need to invalidate — we just wrote the value we know
            logger.info(f"Stored '{field_name}' in 1Password item '{item_name}'")
            return True
        logger.warning(f"Failed to store '{field_name}' in 1Password item '{item_name}'")
        return False

    def invalidate(self) -> None:
        """Force cache refresh on next access (does not invalidate session token)."""
        with self._lock:
            self._cache_time = None
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
    Use this for optional features (e.g., Telegram notifications).

    Args:
        key: Field name (e.g., ``"TELEGRAM_BOT_TOKEN"``).

    Returns:
        The field value, or ``None`` if not found.
    """
    return _vault.get_optional(key)


def is_available() -> bool:
    """Check if 1Password CLI is installed and the user is signed in."""
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
    """Force vault cache refresh on next access.

    Does not invalidate the session token — the biometric prompt will not
    reappear unless the token has also expired.
    """
    _vault.invalidate()
