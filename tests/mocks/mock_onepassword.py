"""Mock 1Password client for testing without real vault.

This module provides mock implementations of the 1Password client
to enable testing without requiring actual 1Password CLI or vault access.
"""


class Mock1PasswordClient:
    """Mock 1Password client for testing."""

    def __init__(
        self,
        credentials: dict[str, str] | None = None,
        config: dict[str, str] | None = None,
        available: bool = True,
    ):
        """Initialize mock 1Password client.

        Args:
            credentials: Mock credential values (concealed fields)
            config: Mock configuration values (text fields)
            available: Whether 1Password CLI should appear available
        """
        self.credentials = credentials or {}
        self.config = config or {}
        self._available = available
        self.vault_name = "revolut-trader"
        self.item_name = "revolut-trader-credentials"

    def is_available(self) -> bool:
        """Check if mock 1Password is available."""
        return self._available

    def get_field(self, field_name: str) -> str | None:
        """Get a field value from mock storage.

        Args:
            field_name: The field to retrieve

        Returns:
            The field value or None if not found
        """
        # Check credentials first, then config
        if field_name in self.credentials:
            return self.credentials[field_name]
        if field_name in self.config:
            return self.config[field_name]
        return None

    def get_all_fields(self) -> dict[str, str]:
        """Get all fields from mock storage."""
        return {**self.credentials, **self.config}

    def set_field(self, field_name: str, value: str) -> bool:
        """Set a field value in mock storage."""
        if field_name.isupper():
            self.config[field_name] = value
        else:
            self.credentials[field_name] = value
        return True


class MockConfigClient:
    """Mock client specifically for config item (revolut-trader-config)."""

    def __init__(
        self,
        config: dict[str, str] | None = None,
        available: bool = True,
    ):
        """Initialize mock config client.

        Args:
            config: Mock configuration values
            available: Whether 1Password CLI should appear available
        """
        self.config = config or {}
        self._available = available
        self.vault_name = "revolut-trader"
        self.item_name = "revolut-trader-config"

    def is_available(self) -> bool:
        """Check if mock 1Password is available."""
        return self._available

    def get_field(self, field_name: str) -> str | None:
        """Get a config field value."""
        return self.config.get(field_name)


def create_valid_config() -> dict[str, str]:
    """Create a valid complete configuration.

    Returns:
        Dictionary with all required config fields set to valid values
    """
    return {
        "TRADING_MODE": "paper",
        "RISK_LEVEL": "conservative",
        "BASE_CURRENCY": "EUR",
        "TRADING_PAIRS": "BTC-EUR,ETH-EUR",
        "DEFAULT_STRATEGY": "market_making",
        "INITIAL_CAPITAL": "10000",
    }


def create_valid_credentials() -> dict[str, str]:
    """Create valid mock credentials.

    Returns:
        Dictionary with all required credentials
    """
    # Generate a mock Ed25519 private key in PEM format
    mock_private_key = """-----BEGIN PRIVATE KEY-----
MC4CAQAwBQYDK2VwBCIEIFakeKeyForTestingPurposesOnly123456789ABC
-----END PRIVATE KEY-----"""

    return {
        "REVOLUT_API_KEY": "test-api-key-64-characters-long-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "REVOLUT_PRIVATE_KEY": mock_private_key,
        "TELEGRAM_BOT_TOKEN": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        "TELEGRAM_CHAT_ID": "123456789",
    }
