"""Mock 1Password vault for testing without real vault access.

Provides a flat dictionary of all test values (credentials + config merged)
matching the structure of the real _VaultCache singleton.  Supports
per-environment mock vaults (dev, int, prod).

TRADING_MODE is not stored in 1Password — it is derived from the environment
(dev/int → paper, prod → live).  INITIAL_CAPITAL is only needed for paper
mode environments (dev/int).  MAX_CAPITAL is optional for all environments —
when set, it caps the cash balance at startup.

Strategy configs are loaded from revolut-trader-strategy-{name} items and
stored with STRATEGY_{NAME_UPPER}_{FIELD} keys in the flat cache.
"""

_MOCK_PRIVATE_KEY = (
    "-----BEGIN PRIVATE KEY-----\n"
    "MC4CAQAwBQYDK2VwBCIEIFakeKeyForTestingPurposesOnly123456789ABC\n"
    "-----END PRIVATE KEY-----"
)


def create_mock_vault(environment: str = "dev", max_capital: str | None = None) -> dict[str, str]:
    """Return all test values as a single flat dict (mirrors the real vault cache).

    Args:
        environment: The environment to mock (dev, int, prod).
        max_capital: Optional MAX_CAPITAL value.  When set, caps the cash
            balance at startup so the bot never trades with more than this.

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

    # MAX_CAPITAL — optional for all environments.
    if max_capital is not None:
        base["MAX_CAPITAL"] = max_capital

    # Strategy configs — loaded from revolut-trader-strategy-{name} items.
    # Keys are namespaced: STRATEGY_{NAME_UPPER}_{FIELD}.
    for name, interval, min_signal, order_type, stop_loss, take_profit in [
        ("market_making", "5", "0.3", "limit", "0.5", "0.3"),
        ("momentum", "10", "0.6", "market", "2.5", "4.0"),
        ("breakout", "5", "0.7", "market", "3.0", "5.0"),
        ("mean_reversion", "15", "0.5", "limit", "1.0", "1.5"),
        ("range_reversion", "15", "0.5", "limit", "1.0", "1.5"),
        ("multi_strategy", "10", "0.55", "limit", None, None),
    ]:
        prefix = f"STRATEGY_{name.upper()}"
        base[f"{prefix}_INTERVAL"] = interval
        base[f"{prefix}_MIN_SIGNAL_STRENGTH"] = min_signal
        base[f"{prefix}_ORDER_TYPE"] = order_type
        if stop_loss is not None:
            base[f"{prefix}_STOP_LOSS_PCT"] = stop_loss
        if take_profit is not None:
            base[f"{prefix}_TAKE_PROFIT_PCT"] = take_profit
        # Internal calibration params are intentionally omitted here so they
        # default to None in StrategyConfig and each strategy uses its own defaults.
        # Override specific fields in tests that need non-default values.

    # Risk level configs — loaded from revolut-trader-risk-{level} items.
    # Keys are namespaced: RISK_{LEVEL_UPPER}_{FIELD}.
    for level, max_pos, max_loss, sl, tp, max_pos_count in [
        ("conservative", "1.5", "3.0", "1.5", "2.5", "3"),
        ("moderate", "3.0", "5.0", "2.5", "4.0", "5"),
        ("aggressive", "5.0", "10.0", "4.0", "7.0", "8"),
    ]:
        prefix = f"RISK_{level.upper()}"
        base[f"{prefix}_MAX_POSITION_SIZE_PCT"] = max_pos
        base[f"{prefix}_MAX_DAILY_LOSS_PCT"] = max_loss
        base[f"{prefix}_STOP_LOSS_PCT"] = sl
        base[f"{prefix}_TAKE_PROFIT_PCT"] = tp
        base[f"{prefix}_MAX_OPEN_POSITIONS"] = max_pos_count

    return base


def create_mock_vault_with_telegram(
    environment: str = "dev",
    bot_token: str = "123456:TEST_TOKEN",
    chat_id: str = "-100123456789",
) -> dict[str, str]:
    """Return a mock vault with Telegram notification fields set.

    Args:
        environment: The environment to mock (dev, int, prod).
        bot_token:   Telegram Bot API token.
        chat_id:     Target chat or channel ID.

    Returns:
        Dict with all required credentials, config, and Telegram fields.
    """
    vault = create_mock_vault(environment)
    vault["TELEGRAM_BOT_TOKEN"] = bot_token
    vault["TELEGRAM_CHAT_ID"] = chat_id
    return vault


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
