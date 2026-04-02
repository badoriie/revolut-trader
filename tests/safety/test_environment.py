"""Environment Safety Tests - CRITICAL

These tests verify that:
1. ENVIRONMENT must be set before the bot starts
2. TRADING_MODE is configurable in 1Password and defaults to paper (safest)
3. Invalid environment values are rejected
4. INITIAL_CAPITAL is only required for paper mode, not live

Critical because: Running live trading requires explicit opt-in to prevent
accidental real money trading with downloaded binary.
"""

import os
from unittest.mock import patch

import pytest

from src.config import Environment, Settings, TradingMode

PATCH_TARGET = "src.utils.onepassword.get"
PATCH_TARGET_OPTIONAL = "src.utils.onepassword.get_optional"


def mock_get(config_dict):
    """Create a mock for op.get() that raises RuntimeError for missing keys."""

    def get_impl(key: str) -> str:
        if key not in config_dict:
            raise RuntimeError(
                f"{key} not found in 1Password vault 'revolut-trader'.\n"
                f"Run: make opconfig-set KEY={key} VALUE=<value>"
            )
        return config_dict[key]

    return get_impl


def mock_get_optional(config_dict):
    """Create a mock for op.get_optional() that returns None for missing keys."""

    def get_optional_impl(key: str) -> str | None:
        return config_dict.get(key)

    return get_optional_impl


# Valid config for paper mode — explicitly sets TRADING_MODE=paper.
VALID_PAPER_CONFIG = {
    "TRADING_MODE": "paper",
    "RISK_LEVEL": "conservative",
    "BASE_CURRENCY": "EUR",
    "TRADING_PAIRS": "BTC-EUR,ETH-EUR",
    "DEFAULT_STRATEGY": "market_making",
    "INITIAL_CAPITAL": "10000",
}

# Valid config without TRADING_MODE — should default to paper (safe default).
VALID_DEFAULT_CONFIG = {
    "RISK_LEVEL": "conservative",
    "BASE_CURRENCY": "EUR",
    "TRADING_PAIRS": "BTC-EUR,ETH-EUR",
    "DEFAULT_STRATEGY": "market_making",
    "INITIAL_CAPITAL": "10000",
}

# Valid config for live mode — explicit opt-in required.
VALID_LIVE_CONFIG = {
    "TRADING_MODE": "live",
    "RISK_LEVEL": "conservative",
    "BASE_CURRENCY": "EUR",
    "TRADING_PAIRS": "BTC-EUR,ETH-EUR",
    "DEFAULT_STRATEGY": "market_making",
}


class TestEnvironmentRequired:
    """Tests that ENVIRONMENT must be set and valid."""

    def test_missing_environment_raises_error(self):
        """CRITICAL: Bot MUST fail if ENVIRONMENT is not set.

        Context: Safety requirement ENV-01
        Critical because: Without a known environment, the bot cannot determine
        which 1Password items to use or which DB to write to.
        """
        env = os.environ.copy()
        env.pop("ENVIRONMENT", None)

        with patch.dict(os.environ, env, clear=True):
            with patch(PATCH_TARGET, side_effect=mock_get(VALID_PAPER_CONFIG)):
                with pytest.raises(RuntimeError, match="ENVIRONMENT"):
                    Settings()

    def test_invalid_environment_raises_error(self):
        """CRITICAL: Only dev, int, prod are valid environment values."""
        with patch.dict(os.environ, {"ENVIRONMENT": "staging"}):
            with patch(PATCH_TARGET, side_effect=mock_get(VALID_PAPER_CONFIG)):
                with pytest.raises(ValueError, match=r"(?i)invalid.*environment|staging"):
                    Settings()


class TestTradingModeConfiguration:
    """Tests that TRADING_MODE is configurable and defaults to paper (safest).

    TRADING_MODE is stored in 1Password and defaults to 'paper' if not set.
    Users must explicitly set it to 'live' to trade with real money.
    """

    def test_trading_mode_defaults_to_paper_when_not_set(self):
        """CRITICAL: When TRADING_MODE is not in 1Password, it MUST default to paper."""
        with patch.dict(os.environ, {"ENVIRONMENT": "prod"}):
            with patch(PATCH_TARGET, side_effect=mock_get(VALID_DEFAULT_CONFIG)):
                settings = Settings()
                assert settings.trading_mode == TradingMode.PAPER

    def test_explicit_paper_mode_is_respected(self):
        """Explicit TRADING_MODE=paper in 1Password should be used."""
        with patch.dict(os.environ, {"ENVIRONMENT": "int"}):
            with patch(PATCH_TARGET, side_effect=mock_get(VALID_PAPER_CONFIG)):
                with patch(
                    PATCH_TARGET_OPTIONAL, side_effect=mock_get_optional(VALID_PAPER_CONFIG)
                ):
                    settings = Settings()
                    assert settings.trading_mode == TradingMode.PAPER
                    assert settings.environment == Environment.INT

    def test_explicit_live_mode_is_respected(self):
        """CRITICAL: Explicit TRADING_MODE=live in 1Password enables real trading.

        Context: Safety requirement ENV-02
        Critical because: Live mode uses real money. Requires explicit opt-in.
        """
        with patch.dict(os.environ, {"ENVIRONMENT": "prod"}):
            with patch(PATCH_TARGET, side_effect=mock_get(VALID_LIVE_CONFIG)):
                with patch(PATCH_TARGET_OPTIONAL, side_effect=mock_get_optional(VALID_LIVE_CONFIG)):
                    settings = Settings()
                    assert settings.trading_mode == TradingMode.LIVE
                    assert settings.environment == Environment.PROD

    def test_invalid_trading_mode_raises_error(self):
        """Invalid TRADING_MODE values should be rejected."""
        invalid_config = {**VALID_PAPER_CONFIG, "TRADING_MODE": "invalid"}

        with patch.dict(os.environ, {"ENVIRONMENT": "dev"}):
            with patch(PATCH_TARGET, side_effect=mock_get(invalid_config)):
                with patch(PATCH_TARGET_OPTIONAL, side_effect=mock_get_optional(invalid_config)):
                    with pytest.raises(ValueError, match=r"(?i)invalid.*trading.*mode"):
                        Settings()

    def test_trading_mode_is_case_insensitive(self):
        """TRADING_MODE should accept various cases."""
        for mode_str in ["paper", "PAPER", "Paper"]:
            config = {**VALID_PAPER_CONFIG, "TRADING_MODE": mode_str}
            with patch.dict(os.environ, {"ENVIRONMENT": "dev"}):
                with patch(PATCH_TARGET, side_effect=mock_get(config)):
                    settings = Settings()
                    assert settings.trading_mode == TradingMode.PAPER


class TestInitialCapitalByTradingMode:
    """Tests that INITIAL_CAPITAL is only required for paper mode, not live."""

    def test_initial_capital_required_for_paper_mode(self):
        """CRITICAL: Paper mode requires INITIAL_CAPITAL."""
        config_without_capital = {
            k: v for k, v in VALID_PAPER_CONFIG.items() if k != "INITIAL_CAPITAL"
        }

        with patch.dict(os.environ, {"ENVIRONMENT": "dev"}):
            with patch(PATCH_TARGET, side_effect=mock_get(config_without_capital)):
                with pytest.raises(RuntimeError, match="INITIAL_CAPITAL"):
                    Settings()

    def test_initial_capital_not_required_for_live_mode(self):
        """Live mode does NOT need INITIAL_CAPITAL — real balance from API."""
        with patch.dict(os.environ, {"ENVIRONMENT": "prod"}):
            with patch(PATCH_TARGET, side_effect=mock_get(VALID_LIVE_CONFIG)):
                with patch(PATCH_TARGET_OPTIONAL, side_effect=mock_get_optional(VALID_LIVE_CONFIG)):
                    settings = Settings()
                    assert settings.trading_mode == TradingMode.LIVE
                    # paper_initial_capital stays at pydantic default (unused in live)
                    assert settings.paper_initial_capital == 10000.0

    def test_default_paper_mode_requires_initial_capital(self):
        """When TRADING_MODE defaults to paper, INITIAL_CAPITAL is required."""
        config_without_capital = {
            k: v for k, v in VALID_DEFAULT_CONFIG.items() if k != "INITIAL_CAPITAL"
        }

        with patch.dict(os.environ, {"ENVIRONMENT": "int"}):
            with patch(PATCH_TARGET, side_effect=mock_get(config_without_capital)):
                with patch(
                    PATCH_TARGET_OPTIONAL, side_effect=mock_get_optional(config_without_capital)
                ):
                    with pytest.raises(RuntimeError, match="INITIAL_CAPITAL"):
                        Settings()


class TestLiveTradingRestrictions:
    """Tests that LIVE trading is only allowed in prod environment.

    CRITICAL: This prevents accidental real money trading in dev/int environments.
    """

    def test_live_mode_blocked_in_dev_from_1password(self):
        """CRITICAL: LIVE mode in 1Password must be blocked in dev environment."""
        config_with_live = {**VALID_LIVE_CONFIG}

        with patch.dict(os.environ, {"ENVIRONMENT": "dev"}):
            with patch(PATCH_TARGET, side_effect=mock_get(config_with_live)):
                with patch(PATCH_TARGET_OPTIONAL, side_effect=mock_get_optional(config_with_live)):
                    with pytest.raises(
                        RuntimeError, match=r"LIVE trading is only allowed in 'prod'"
                    ):
                        Settings()

    def test_live_mode_blocked_in_int_from_1password(self):
        """CRITICAL: LIVE mode in 1Password must be blocked in int environment."""
        config_with_live = {**VALID_LIVE_CONFIG}

        with patch.dict(os.environ, {"ENVIRONMENT": "int"}):
            with patch(PATCH_TARGET, side_effect=mock_get(config_with_live)):
                with patch(PATCH_TARGET_OPTIONAL, side_effect=mock_get_optional(config_with_live)):
                    with pytest.raises(
                        RuntimeError, match=r"LIVE trading is only allowed in 'prod'"
                    ):
                        Settings()

    def test_live_mode_allowed_in_prod(self):
        """LIVE mode in 1Password is allowed in prod environment."""
        config_with_live = {**VALID_LIVE_CONFIG}

        with patch.dict(os.environ, {"ENVIRONMENT": "prod"}):
            with patch(PATCH_TARGET, side_effect=mock_get(config_with_live)):
                with patch(PATCH_TARGET_OPTIONAL, side_effect=mock_get_optional(config_with_live)):
                    settings = Settings()
                    assert settings.trading_mode == TradingMode.LIVE
                    assert settings.environment == Environment.PROD

    def test_override_to_live_blocked_in_dev(self):
        """CRITICAL: CLI override to LIVE mode must be blocked in dev."""
        with patch.dict(os.environ, {"ENVIRONMENT": "dev"}):
            with patch(PATCH_TARGET, side_effect=mock_get(VALID_PAPER_CONFIG)):
                with patch(
                    PATCH_TARGET_OPTIONAL, side_effect=mock_get_optional(VALID_PAPER_CONFIG)
                ):
                    settings = Settings()
                    assert settings.trading_mode == TradingMode.PAPER

                    with pytest.raises(
                        RuntimeError, match=r"LIVE trading is only allowed in 'prod'"
                    ):
                        settings.override_trading_mode(TradingMode.LIVE)

    def test_override_to_live_blocked_in_int(self):
        """CRITICAL: CLI override to LIVE mode must be blocked in int."""
        with patch.dict(os.environ, {"ENVIRONMENT": "int"}):
            with patch(PATCH_TARGET, side_effect=mock_get(VALID_PAPER_CONFIG)):
                with patch(
                    PATCH_TARGET_OPTIONAL, side_effect=mock_get_optional(VALID_PAPER_CONFIG)
                ):
                    settings = Settings()
                    assert settings.trading_mode == TradingMode.PAPER

                    with pytest.raises(
                        RuntimeError, match=r"LIVE trading is only allowed in 'prod'"
                    ):
                        settings.override_trading_mode(TradingMode.LIVE)

    def test_override_to_live_allowed_in_prod(self):
        """CLI override to LIVE mode is allowed in prod."""
        with patch.dict(os.environ, {"ENVIRONMENT": "prod"}):
            with patch(PATCH_TARGET, side_effect=mock_get(VALID_PAPER_CONFIG)):
                with patch(
                    PATCH_TARGET_OPTIONAL, side_effect=mock_get_optional(VALID_PAPER_CONFIG)
                ):
                    settings = Settings()
                    assert settings.trading_mode == TradingMode.PAPER

                    settings.override_trading_mode(TradingMode.LIVE)
                    assert settings.trading_mode == TradingMode.LIVE

    def test_override_to_paper_allowed_in_all_environments(self):
        """Overriding to PAPER mode should be allowed in all environments."""
        for env in ["dev", "int", "prod"]:
            with patch.dict(os.environ, {"ENVIRONMENT": env}):
                with patch(
                    PATCH_TARGET,
                    side_effect=mock_get(
                        VALID_LIVE_CONFIG if env == "prod" else VALID_PAPER_CONFIG
                    ),
                ):
                    with patch(
                        PATCH_TARGET_OPTIONAL,
                        side_effect=mock_get_optional(
                            VALID_LIVE_CONFIG if env == "prod" else VALID_PAPER_CONFIG
                        ),
                    ):
                        settings = Settings()
                        settings.override_trading_mode(TradingMode.PAPER)
                        assert settings.trading_mode == TradingMode.PAPER


class TestEnvironmentEnum:
    """Tests for the Environment enum values."""

    def test_environment_values(self):
        """Environment enum must have exactly dev, int, prod."""
        assert Environment.DEV.value == "dev"
        assert Environment.INT.value == "int"
        assert Environment.PROD.value == "prod"
        assert len(Environment) == 3

    def test_environment_case_insensitive(self):
        """ENVIRONMENT should accept various cases."""
        for env_str in ["dev", "DEV", "Dev"]:
            with patch.dict(os.environ, {"ENVIRONMENT": env_str}):
                with patch(PATCH_TARGET, side_effect=mock_get(VALID_PAPER_CONFIG)):
                    with patch(
                        PATCH_TARGET_OPTIONAL, side_effect=mock_get_optional(VALID_PAPER_CONFIG)
                    ):
                        settings = Settings()
                        assert settings.environment == Environment.DEV
