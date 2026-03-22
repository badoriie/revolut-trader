"""Mock 1Password vault for testing without real vault access.

Provides a flat dictionary of all test values (credentials + config merged)
matching the structure of the real _VaultCache singleton.  Supports
per-environment mock vaults (dev, int, prod).

TRADING_MODE is not stored in 1Password — it is derived from the environment
(dev/int → paper, prod → live).  INITIAL_CAPITAL is only needed for paper
mode environments (dev/int).
"""

_MOCK_PRIVATE_KEY = (
    "-----BEGIN PRIVATE KEY-----\n"
    "MC4CAQAwBQYDK2VwBCIEIFakeKeyForTestingPurposesOnly123456789ABC\n"
    "-----END PRIVATE KEY-----"
)


def create_mock_vault(environment: str = "dev") -> dict[str, str]:
    """Return all test values as a single flat dict (mirrors the real vault cache).

    Args:
        environment: The environment to mock (dev, int, prod).

    Returns:
        Dict with all required credentials and configuration for tests
    """
    base = {
        # Credentials (revolut-trader-credentials-{env} item)
        "REVOLUT_API_KEY": f"test-api-key-{environment}-64chars-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "REVOLUT_PRIVATE_KEY": _MOCK_PRIVATE_KEY,
        # Config (revolut-trader-config-{env} item)
        "RISK_LEVEL": "conservative",
        "BASE_CURRENCY": "EUR",
        "TRADING_PAIRS": "BTC-EUR,ETH-EUR",
        "DEFAULT_STRATEGY": "market_making",
    }

    # INITIAL_CAPITAL — only for paper mode environments (dev/int).
    # Prod (live mode) fetches real balance from the Revolut API.
    if environment != "prod":
        base["INITIAL_CAPITAL"] = "10000"

    return base


def create_mock_vault_dev() -> dict[str, str]:
    """Return a mock vault for the dev environment."""
    return create_mock_vault("dev")


def create_mock_vault_int() -> dict[str, str]:
    """Return a mock vault for the int environment."""
    return create_mock_vault("int")


def create_mock_vault_prod() -> dict[str, str]:
    """Return a mock vault for the prod environment.

    Prod is the only environment where TRADING_MODE=live is used.
    INITIAL_CAPITAL is not needed (real balance from API).
    """
    return create_mock_vault("prod")


def create_valid_config() -> dict[str, str]:
    """Return the configuration subset of the mock vault (for backwards compatibility).

    Returns paper-mode config (dev/int).
    """
    return {
        "RISK_LEVEL": "conservative",
        "BASE_CURRENCY": "EUR",
        "TRADING_PAIRS": "BTC-EUR,ETH-EUR",
        "DEFAULT_STRATEGY": "market_making",
        "INITIAL_CAPITAL": "10000",
    }


def create_valid_credentials() -> dict[str, str]:
    """Return the credentials subset of the mock vault (for backwards compatibility)."""
    return {
        "REVOLUT_API_KEY": "test-api-key-64-characters-long-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "REVOLUT_PRIVATE_KEY": _MOCK_PRIVATE_KEY,
    }
