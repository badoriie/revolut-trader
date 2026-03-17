"""Mock 1Password vault for testing without real vault access.

Provides a flat dictionary of all test values (credentials + config merged)
matching the structure of the real _VaultCache singleton.
"""


def create_mock_vault() -> dict[str, str]:
    """Return all test values as a single flat dict (mirrors the real vault cache).

    Returns:
        Dict with all required credentials and configuration for tests
    """
    mock_private_key = (
        "-----BEGIN PRIVATE KEY-----\n"
        "MC4CAQAwBQYDK2VwBCIEIFakeKeyForTestingPurposesOnly123456789ABC\n"
        "-----END PRIVATE KEY-----"
    )
    return {
        # Credentials (revolut-trader-credentials item)
        "REVOLUT_API_KEY": "test-api-key-64-characters-long-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "REVOLUT_PRIVATE_KEY": mock_private_key,
        # Config (revolut-trader-config item)
        "TRADING_MODE": "paper",
        "RISK_LEVEL": "conservative",
        "BASE_CURRENCY": "EUR",
        "TRADING_PAIRS": "BTC-EUR,ETH-EUR",
        "DEFAULT_STRATEGY": "market_making",
        "INITIAL_CAPITAL": "10000",
    }


def create_valid_config() -> dict[str, str]:
    """Return the configuration subset of the mock vault (for backwards compatibility)."""
    return {
        "TRADING_MODE": "paper",
        "RISK_LEVEL": "conservative",
        "BASE_CURRENCY": "EUR",
        "TRADING_PAIRS": "BTC-EUR,ETH-EUR",
        "DEFAULT_STRATEGY": "market_making",
        "INITIAL_CAPITAL": "10000",
    }


def create_valid_credentials() -> dict[str, str]:
    """Return the credentials subset of the mock vault (for backwards compatibility)."""
    mock_private_key = (
        "-----BEGIN PRIVATE KEY-----\n"
        "MC4CAQAwBQYDK2VwBCIEIFakeKeyForTestingPurposesOnly123456789ABC\n"
        "-----END PRIVATE KEY-----"
    )
    return {
        "REVOLUT_API_KEY": "test-api-key-64-characters-long-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "REVOLUT_PRIVATE_KEY": mock_private_key,
    }