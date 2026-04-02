"""Configuration Safety Tests - CRITICAL

These tests verify that:
1. ALL trading configuration MUST come from 1Password (except TRADING_MODE
   which is derived from the environment)
2. Bot MUST fail immediately if config is missing
3. Bot MUST fail immediately if config is invalid
4. No accidental trading with hardcoded defaults

Critical because: Missing/wrong config could cause wrong risk levels,
or trading with unintended settings.

Test strategy: Mock op.get() to simulate 1Password behavior with missing/invalid
values and verify RuntimeError or ValueError is raised.
"""

import os
from unittest.mock import patch

import pytest

from src.config import RiskLevel, Settings, StrategyType, TradingMode

# Patch target — op.get is called inside model_post_init via `import src.utils.onepassword as op`
PATCH_TARGET = "src.utils.onepassword.get"
PATCH_TARGET_OPTIONAL = "src.utils.onepassword.get_optional"


def mock_get(config_dict):
    """Create a mock for op.get() that raises RuntimeError for missing keys.

    Args:
        config_dict: Dictionary of config key->value mappings

    Returns:
        Mock function that behaves like op.get()
    """

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


class TestConfigurationRequired:
    """Tests that verify configuration MUST be in 1Password.

    TRADING_MODE is optional in 1Password and defaults to 'paper' (safest default).
    INITIAL_CAPITAL is only required for paper mode.
    """

    def test_risk_level_required_from_1password(self):
        """CRITICAL: Bot MUST fail if RISK_LEVEL not in 1Password.

        Context: Safety requirement SAF-02
        Critical because: Wrong risk level = wrong position sizing
        """
        config = {
            "BASE_CURRENCY": "EUR",
            "TRADING_PAIRS": "BTC-EUR,ETH-EUR",
            "DEFAULT_STRATEGY": "market_making",
            "INITIAL_CAPITAL": "10000",
        }

        with patch(PATCH_TARGET, side_effect=mock_get(config)):
            with pytest.raises(RuntimeError) as exc_info:
                Settings()

            error_msg = str(exc_info.value)
            assert "RISK_LEVEL" in error_msg
            assert "not found" in error_msg

    def test_base_currency_required_from_1password(self):
        """CRITICAL: Bot MUST fail if BASE_CURRENCY not in 1Password."""
        config = {
            "RISK_LEVEL": "conservative",
            "TRADING_PAIRS": "BTC-EUR,ETH-EUR",
            "DEFAULT_STRATEGY": "market_making",
            "INITIAL_CAPITAL": "10000",
        }

        with patch(PATCH_TARGET, side_effect=mock_get(config)):
            with pytest.raises(RuntimeError) as exc_info:
                Settings()

            assert "BASE_CURRENCY" in str(exc_info.value)

    def test_trading_pairs_required_from_1password(self):
        """CRITICAL: Bot MUST fail if TRADING_PAIRS not in 1Password."""
        config = {
            "RISK_LEVEL": "conservative",
            "BASE_CURRENCY": "EUR",
            "DEFAULT_STRATEGY": "market_making",
            "INITIAL_CAPITAL": "10000",
        }

        with patch(PATCH_TARGET, side_effect=mock_get(config)):
            with pytest.raises(RuntimeError) as exc_info:
                Settings()

            assert "TRADING_PAIRS" in str(exc_info.value)

    def test_default_strategy_required_from_1password(self):
        """CRITICAL: Bot MUST fail if DEFAULT_STRATEGY not in 1Password."""
        config = {
            "RISK_LEVEL": "conservative",
            "BASE_CURRENCY": "EUR",
            "TRADING_PAIRS": "BTC-EUR,ETH-EUR",
            "INITIAL_CAPITAL": "10000",
        }

        with patch(PATCH_TARGET, side_effect=mock_get(config)):
            with pytest.raises(RuntimeError) as exc_info:
                Settings()

            assert "DEFAULT_STRATEGY" in str(exc_info.value)

    def test_initial_capital_required_for_paper_mode(self):
        """CRITICAL: Bot MUST fail if INITIAL_CAPITAL not in 1Password (dev/int)."""
        config = {
            "RISK_LEVEL": "conservative",
            "BASE_CURRENCY": "EUR",
            "TRADING_PAIRS": "BTC-EUR,ETH-EUR",
            "DEFAULT_STRATEGY": "market_making",
        }

        with patch(PATCH_TARGET, side_effect=mock_get(config)):
            with pytest.raises(RuntimeError) as exc_info:
                Settings()

            assert "INITIAL_CAPITAL" in str(exc_info.value)

    def test_initial_capital_not_required_for_prod(self):
        """Live mode does NOT require INITIAL_CAPITAL — balance fetched from API."""
        config = {
            "TRADING_MODE": "live",
            "RISK_LEVEL": "conservative",
            "BASE_CURRENCY": "EUR",
            "TRADING_PAIRS": "BTC-EUR,ETH-EUR",
            "DEFAULT_STRATEGY": "market_making",
        }

        with patch.dict(os.environ, {"ENVIRONMENT": "prod"}):
            with patch(PATCH_TARGET, side_effect=mock_get(config)):
                with patch(PATCH_TARGET_OPTIONAL, side_effect=mock_get_optional(config)):
                    settings = Settings()
                    assert settings.trading_mode == TradingMode.LIVE


class TestConfigurationValidation:
    """Tests that verify invalid configuration values are rejected."""

    def test_invalid_risk_level_raises_error(self):
        """CRITICAL: Invalid RISK_LEVEL values MUST be rejected.

        Only "conservative", "moderate", "aggressive" are valid (case-insensitive).
        """
        config = {
            "RISK_LEVEL": "extreme",  # Invalid value
            "BASE_CURRENCY": "EUR",
            "TRADING_PAIRS": "BTC-EUR,ETH-EUR",
            "DEFAULT_STRATEGY": "market_making",
            "INITIAL_CAPITAL": "10000",
        }

        with patch(PATCH_TARGET, side_effect=mock_get(config)):
            with pytest.raises(ValueError, match=r"(?i)invalid.*risk_level|extreme"):
                Settings()

    def test_invalid_default_strategy_raises_error(self):
        """CRITICAL: Invalid DEFAULT_STRATEGY values MUST be rejected."""
        config = {
            "RISK_LEVEL": "conservative",
            "BASE_CURRENCY": "EUR",
            "TRADING_PAIRS": "BTC-EUR,ETH-EUR",
            "DEFAULT_STRATEGY": "invalid_strategy",  # Invalid value
            "INITIAL_CAPITAL": "10000",
        }

        with patch(PATCH_TARGET, side_effect=mock_get(config)):
            with pytest.raises(ValueError, match=r"(?i)invalid.*default_strategy|invalid_strategy"):
                Settings()

    def test_invalid_initial_capital_raises_error(self):
        """CRITICAL: Non-numeric INITIAL_CAPITAL MUST be rejected."""
        config = {
            "RISK_LEVEL": "conservative",
            "BASE_CURRENCY": "EUR",
            "TRADING_PAIRS": "BTC-EUR,ETH-EUR",
            "DEFAULT_STRATEGY": "market_making",
            "INITIAL_CAPITAL": "not_a_number",  # Invalid value
        }

        with patch(PATCH_TARGET, side_effect=mock_get(config)):
            with pytest.raises(ValueError, match=r"(?i)invalid.*initial_capital|not_a_number"):
                Settings()


class TestValidConfiguration:
    """Tests that verify valid configuration is accepted."""

    def test_valid_paper_mode_config_accepted(self):
        """Valid paper mode configuration should be accepted."""
        config = {
            "TRADING_MODE": "paper",
            "RISK_LEVEL": "conservative",
            "BASE_CURRENCY": "EUR",
            "TRADING_PAIRS": "BTC-EUR,ETH-EUR",
            "DEFAULT_STRATEGY": "market_making",
            "INITIAL_CAPITAL": "10000",
        }

        with patch(PATCH_TARGET, side_effect=mock_get(config)):
            settings = Settings()

            assert settings.trading_mode == TradingMode.PAPER
            assert settings.risk_level == RiskLevel.CONSERVATIVE
            assert settings.base_currency == "EUR"
            assert settings.trading_pairs == ["BTC-EUR", "ETH-EUR"]
            assert settings.default_strategy == StrategyType.MARKET_MAKING
            assert settings.paper_initial_capital == 10000.0

    def test_valid_live_mode_config_accepted(self):
        """Valid live mode configuration should be accepted (no INITIAL_CAPITAL needed)."""
        config = {
            "TRADING_MODE": "live",
            "RISK_LEVEL": "conservative",
            "BASE_CURRENCY": "EUR",
            "TRADING_PAIRS": "BTC-EUR,ETH-EUR",
            "DEFAULT_STRATEGY": "market_making",
        }

        with patch.dict(os.environ, {"ENVIRONMENT": "prod"}):
            with patch(PATCH_TARGET, side_effect=mock_get(config)):
                with patch(PATCH_TARGET_OPTIONAL, side_effect=mock_get_optional(config)):
                    settings = Settings()

                    assert settings.trading_mode == TradingMode.LIVE
                    assert settings.risk_level == RiskLevel.CONSERVATIVE

    def test_valid_moderate_risk_config_accepted(self):
        """Valid moderate risk configuration should be accepted."""
        config = {
            "RISK_LEVEL": "moderate",
            "BASE_CURRENCY": "EUR",
            "TRADING_PAIRS": "BTC-EUR,ETH-EUR",
            "DEFAULT_STRATEGY": "market_making",
            "INITIAL_CAPITAL": "10000",
        }

        with patch(PATCH_TARGET, side_effect=mock_get(config)):
            settings = Settings()

            assert settings.risk_level == RiskLevel.MODERATE

    def test_valid_aggressive_risk_config_accepted(self):
        """Valid aggressive risk configuration should be accepted."""
        config = {
            "RISK_LEVEL": "aggressive",
            "BASE_CURRENCY": "EUR",
            "TRADING_PAIRS": "BTC-EUR,ETH-EUR",
            "DEFAULT_STRATEGY": "market_making",
            "INITIAL_CAPITAL": "10000",
        }

        with patch(PATCH_TARGET, side_effect=mock_get(config)):
            settings = Settings()

            assert settings.risk_level == RiskLevel.AGGRESSIVE

    def test_trading_pairs_parsed_correctly(self):
        """Trading pairs should be parsed from comma-separated string."""
        config = {
            "RISK_LEVEL": "conservative",
            "BASE_CURRENCY": "EUR",
            "TRADING_PAIRS": "BTC-EUR,ETH-EUR,SOL-EUR,MATIC-EUR",
            "DEFAULT_STRATEGY": "market_making",
            "INITIAL_CAPITAL": "10000",
        }

        with patch(PATCH_TARGET, side_effect=mock_get(config)):
            settings = Settings()

            assert settings.trading_pairs == [
                "BTC-EUR",
                "ETH-EUR",
                "SOL-EUR",
                "MATIC-EUR",
            ]

    def test_base_currency_uppercased(self):
        """Base currency should be converted to uppercase."""
        config = {
            "RISK_LEVEL": "conservative",
            "BASE_CURRENCY": "usd",  # lowercase — pairs must use USD to avoid mismatch
            "TRADING_PAIRS": "BTC-USD,ETH-USD",
            "DEFAULT_STRATEGY": "market_making",
            "INITIAL_CAPITAL": "10000",
        }

        with patch(PATCH_TARGET, side_effect=mock_get(config)):
            settings = Settings()

            assert settings.base_currency == "USD"


class TestCaseSensitivity:
    """Tests that verify case handling is correct."""

    def test_risk_level_case_insensitive(self):
        """RISK_LEVEL should accept various cases."""
        for level in ["conservative", "CONSERVATIVE", "Conservative"]:
            config = {
                "RISK_LEVEL": level,
                "BASE_CURRENCY": "EUR",
                "TRADING_PAIRS": "BTC-EUR,ETH-EUR",
                "DEFAULT_STRATEGY": "market_making",
                "INITIAL_CAPITAL": "10000",
            }

            with patch(PATCH_TARGET, side_effect=mock_get(config)):
                settings = Settings()
                assert settings.risk_level == RiskLevel.CONSERVATIVE
