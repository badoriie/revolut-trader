"""Environment Safety Tests - CRITICAL

These tests verify that:
1. ENVIRONMENT must be set before the bot starts
2. TRADING_MODE=live is ONLY allowed when ENVIRONMENT=prod
3. Paper mode is allowed in all environments
4. Invalid environment values are rejected

Critical because: Running live trading outside production could use wrong
API keys, wrong database, and bypass safety controls.
"""

import os
from unittest.mock import patch

import pytest

from src.config import Environment, Settings, TradingMode

PATCH_TARGET = "src.utils.onepassword.get"


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


VALID_CONFIG = {
    "TRADING_MODE": "paper",
    "RISK_LEVEL": "conservative",
    "BASE_CURRENCY": "EUR",
    "TRADING_PAIRS": "BTC-EUR,ETH-EUR",
    "DEFAULT_STRATEGY": "market_making",
    "INITIAL_CAPITAL": "10000",
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
            with patch(PATCH_TARGET, side_effect=mock_get(VALID_CONFIG)):
                with pytest.raises(RuntimeError, match="ENVIRONMENT"):
                    Settings()

    def test_invalid_environment_raises_error(self):
        """CRITICAL: Only dev, int, prod are valid environment values."""
        with patch.dict(os.environ, {"ENVIRONMENT": "staging"}):
            with patch(PATCH_TARGET, side_effect=mock_get(VALID_CONFIG)):
                with pytest.raises(ValueError, match="(?i)invalid.*environment|staging"):
                    Settings()


class TestLiveModeEnvironmentRestriction:
    """Tests that TRADING_MODE=live is only allowed in ENVIRONMENT=prod."""

    def test_live_mode_rejected_in_dev(self):
        """CRITICAL: TRADING_MODE=live MUST be rejected in dev environment.

        Context: Safety requirement ENV-02
        Critical because: Dev uses mock/test API keys — live trading would fail
        or use wrong credentials.
        """
        live_config = {**VALID_CONFIG, "TRADING_MODE": "live"}

        with patch.dict(os.environ, {"ENVIRONMENT": "dev"}):
            with patch(PATCH_TARGET, side_effect=mock_get(live_config)):
                with pytest.raises(ValueError, match="(?i)live.*only.*prod"):
                    Settings()

    def test_live_mode_rejected_in_int(self):
        """CRITICAL: TRADING_MODE=live MUST be rejected in int environment.

        Context: Safety requirement ENV-03
        Critical because: Int uses integration API keys — not for real money.
        """
        live_config = {**VALID_CONFIG, "TRADING_MODE": "live"}

        with patch.dict(os.environ, {"ENVIRONMENT": "int"}):
            with patch(PATCH_TARGET, side_effect=mock_get(live_config)):
                with pytest.raises(ValueError, match="(?i)live.*only.*prod"):
                    Settings()

    def test_live_mode_accepted_in_prod(self):
        """TRADING_MODE=live MUST be accepted in prod environment."""
        live_config = {**VALID_CONFIG, "TRADING_MODE": "live"}

        with patch.dict(os.environ, {"ENVIRONMENT": "prod"}):
            with patch(PATCH_TARGET, side_effect=mock_get(live_config)):
                settings = Settings()
                assert settings.trading_mode == TradingMode.LIVE
                assert settings.environment == Environment.PROD

    def test_paper_mode_accepted_in_all_environments(self):
        """TRADING_MODE=paper MUST be accepted in all environments."""
        for env in ["dev", "int", "prod"]:
            with patch.dict(os.environ, {"ENVIRONMENT": env}):
                with patch(PATCH_TARGET, side_effect=mock_get(VALID_CONFIG)):
                    settings = Settings()
                    assert settings.trading_mode == TradingMode.PAPER
                    assert settings.environment == Environment(env)


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
                with patch(PATCH_TARGET, side_effect=mock_get(VALID_CONFIG)):
                    settings = Settings()
                    assert settings.environment == Environment.DEV
