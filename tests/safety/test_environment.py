"""Environment Safety Tests - CRITICAL

These tests verify that:
1. ENVIRONMENT must be set before the bot starts
2. TRADING_MODE is derived from environment (dev/int → paper, prod → live)
3. Invalid environment values are rejected
4. INITIAL_CAPITAL is only required for paper mode (dev/int), not prod

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


# Valid config for paper mode environments (dev/int) — no TRADING_MODE field.
VALID_PAPER_CONFIG = {
    "RISK_LEVEL": "conservative",
    "BASE_CURRENCY": "EUR",
    "TRADING_PAIRS": "BTC-EUR,ETH-EUR",
    "DEFAULT_STRATEGY": "market_making",
    "INITIAL_CAPITAL": "10000",
}

# Valid config for prod — no TRADING_MODE, no INITIAL_CAPITAL.
VALID_PROD_CONFIG = {
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
                with pytest.raises(ValueError, match="(?i)invalid.*environment|staging"):
                    Settings()


class TestTradingModeDerivedFromEnvironment:
    """Tests that TRADING_MODE is automatically derived from environment.

    TRADING_MODE is not stored in 1Password.  It is determined by the
    environment: dev/int → paper, prod → live.
    """

    def test_dev_environment_is_paper_mode(self):
        """CRITICAL: Dev environment MUST use paper mode."""
        with patch.dict(os.environ, {"ENVIRONMENT": "dev"}):
            with patch(PATCH_TARGET, side_effect=mock_get(VALID_PAPER_CONFIG)):
                settings = Settings()
                assert settings.trading_mode == TradingMode.PAPER
                assert settings.environment == Environment.DEV

    def test_int_environment_is_paper_mode(self):
        """CRITICAL: Int environment MUST use paper mode."""
        with patch.dict(os.environ, {"ENVIRONMENT": "int"}):
            with patch(PATCH_TARGET, side_effect=mock_get(VALID_PAPER_CONFIG)):
                settings = Settings()
                assert settings.trading_mode == TradingMode.PAPER
                assert settings.environment == Environment.INT

    def test_prod_environment_is_live_mode(self):
        """CRITICAL: Prod environment MUST use live mode.

        Context: Safety requirement ENV-02
        Critical because: Prod is for real money only. Use int for paper
        trading with the real API.
        """
        with patch.dict(os.environ, {"ENVIRONMENT": "prod"}):
            with patch(PATCH_TARGET, side_effect=mock_get(VALID_PROD_CONFIG)):
                settings = Settings()
                assert settings.trading_mode == TradingMode.LIVE
                assert settings.environment == Environment.PROD

    def test_trading_mode_not_read_from_1password(self):
        """Trading mode should NOT be read from 1Password, even if present."""
        config_with_trading_mode = {**VALID_PAPER_CONFIG, "TRADING_MODE": "live"}

        with patch.dict(os.environ, {"ENVIRONMENT": "dev"}):
            with patch(PATCH_TARGET, side_effect=mock_get(config_with_trading_mode)):
                settings = Settings()
                # Should still be paper because dev → paper, regardless of 1Password
                assert settings.trading_mode == TradingMode.PAPER


class TestInitialCapitalByEnvironment:
    """Tests that INITIAL_CAPITAL is only required for paper mode (dev/int)."""

    def test_initial_capital_required_for_dev(self):
        """CRITICAL: Dev environment requires INITIAL_CAPITAL for paper trading."""
        config_without_capital = {
            k: v for k, v in VALID_PAPER_CONFIG.items() if k != "INITIAL_CAPITAL"
        }

        with patch.dict(os.environ, {"ENVIRONMENT": "dev"}):
            with patch(PATCH_TARGET, side_effect=mock_get(config_without_capital)):
                with pytest.raises(RuntimeError, match="INITIAL_CAPITAL"):
                    Settings()

    def test_initial_capital_required_for_int(self):
        """CRITICAL: Int environment requires INITIAL_CAPITAL for paper trading."""
        config_without_capital = {
            k: v for k, v in VALID_PAPER_CONFIG.items() if k != "INITIAL_CAPITAL"
        }

        with patch.dict(os.environ, {"ENVIRONMENT": "int"}):
            with patch(PATCH_TARGET, side_effect=mock_get(config_without_capital)):
                with pytest.raises(RuntimeError, match="INITIAL_CAPITAL"):
                    Settings()

    def test_initial_capital_not_required_for_prod(self):
        """Prod does NOT need INITIAL_CAPITAL — real balance from API."""
        with patch.dict(os.environ, {"ENVIRONMENT": "prod"}):
            with patch(PATCH_TARGET, side_effect=mock_get(VALID_PROD_CONFIG)):
                settings = Settings()
                assert settings.trading_mode == TradingMode.LIVE
                # paper_initial_capital stays at pydantic default (unused in live)
                assert settings.paper_initial_capital == 10000.0


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
                    settings = Settings()
                    assert settings.environment == Environment.DEV
