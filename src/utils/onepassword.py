"""1Password integration for secure credential management.

This module provides 1Password-only credential management.
No .env file fallback - 1Password is required for all credentials.
"""

import json
import subprocess

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


def get_config(
    key: str,
    default: str | None = None,
) -> str | None:
    """Get a configuration value from 1Password with fallback to default.

    Unlike credentials, config values are optional - if not found in 1Password,
    the default is used without raising errors.

    Looks for config in a separate item: "revolut-trader-config"

    Args:
        key: The configuration key (e.g., "TRADING_MODE", "BASE_CURRENCY")
        default: Default value if not found in 1Password

    Returns:
        The configuration value from 1Password, or default if not found

    Examples:
        >>> get_config("TRADING_MODE", "paper")
        "live"  # If set in 1Password
        >>> get_config("BASE_CURRENCY", "EUR")
        "EUR"  # Falls back to default if not in 1Password
    """
    # Use separate config item, not credentials item
    config_client = OnePasswordClient(
        vault_name="revolut-trader",
        item_name="revolut-trader-config",
    )

    if not config_client.is_available():
        logger.debug(f"1Password not available, using default for config {key}")
        return default

    value = config_client.get_field(key)
    if value:
        logger.debug(f"Loaded config {key} from 1Password (revolut-trader-config item)")
        return value

    logger.debug(f"Config {key} not in 1Password config item, using default: {default}")
    return default


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
