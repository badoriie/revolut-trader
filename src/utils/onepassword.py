"""1Password integration for secure credential management."""

import json
import os
import subprocess
from pathlib import Path

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
                logger.warning(
                    "1Password CLI installed but not signed in. Run: eval $(op signin)"
                )
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

    def create_env_file(self, env_path: Path = Path(".env")) -> bool:
        """Create .env file from 1Password credentials.

        Args:
            env_path: Path to the .env file

        Returns:
            True if successful, False otherwise
        """
        if not self.is_available():
            logger.warning("1Password not available, cannot create .env file")
            return False

        fields = self.get_all_fields()
        if not fields:
            logger.warning("No fields found in 1Password")
            return False

        try:
            with open(env_path, "w") as f:
                f.write(f"# Generated from 1Password\n")
                f.write(f"# Vault: {self.vault_name}\n")
                f.write(f"# Item: {self.item_name}\n")
                f.write(f"#\n")
                f.write(f"# DO NOT COMMIT THIS FILE\n")
                f.write(f"\n")

                for key, value in fields.items():
                    f.write(f"{key}={value}\n")

            logger.success(f"Created {env_path} from 1Password")
            return True

        except Exception as e:
            logger.error(f"Error creating .env file: {e}")
            return False


def get_credential(
    key: str,
    default: str | None = None,
    use_1password: bool = True,
) -> str | None:
    """Get a credential from 1Password or environment variable.

    Args:
        key: The credential key
        default: Default value if not found
        use_1password: Whether to try 1Password first

    Returns:
        The credential value or default
    """
    # Try 1Password first if enabled
    if use_1password:
        client = OnePasswordClient()
        value = client.get_field(key)
        if value:
            return value

    # Fall back to environment variable
    value = os.getenv(key)
    if value:
        return value

    # Return default
    return default


def ensure_env_file(force_1password: bool = False) -> bool:
    """Ensure .env file exists, creating from 1Password if available.

    Args:
        force_1password: Force creation from 1Password even if .env exists

    Returns:
        True if .env file exists or was created
    """
    env_path = Path(".env")

    # If .env exists and we're not forcing, we're done
    if env_path.exists() and not force_1password:
        return True

    # Try to create from 1Password
    client = OnePasswordClient()
    if client.is_available():
        logger.info("Creating .env from 1Password...")
        return client.create_env_file(env_path)

    # 1Password not available
    if not env_path.exists():
        logger.warning(
            ".env file not found and 1Password not available. "
            "Please create .env file manually."
        )
        return False

    return True