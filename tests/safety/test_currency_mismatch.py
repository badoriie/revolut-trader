"""Currency Mismatch Safety Tests - CRITICAL

These tests verify that the bot refuses to start when trading pairs do not
match the configured BASE_CURRENCY.

Critical because: A mismatch causes the bot to size positions using the wrong
currency (e.g., USD portfolio value vs EUR-denominated prices), and all orders
get rejected by the API because the account does not hold the pair's quote
currency.  This is a silent financial risk — the bot would happily calculate
positions and attempt trades, but with completely wrong sizing and failing orders.
"""

import os
from unittest.mock import patch

import pytest

from src.config import Settings

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


def mock_get_optional(config_dict):
    """Create a mock for op.get_optional() that returns None for missing keys."""

    def get_optional_impl(key: str):
        return config_dict.get(key)

    return get_optional_impl


BASE_CONFIG = {
    "RISK_LEVEL": "conservative",
    "DEFAULT_STRATEGY": "market_making",
    "INITIAL_CAPITAL": "10000",
}


class TestCurrencyMismatchValidation:
    """Tests that trading pairs must match BASE_CURRENCY."""

    def test_matching_pairs_accepted(self):
        """EUR base currency with EUR pairs should pass validation."""
        config = {
            **BASE_CONFIG,
            "BASE_CURRENCY": "EUR",
            "TRADING_PAIRS": "BTC-EUR,ETH-EUR",
        }
        with patch.dict(os.environ, {"ENVIRONMENT": "dev"}):
            with patch(PATCH_TARGET, side_effect=mock_get(config)):
                with patch(
                    "src.utils.onepassword.get_optional", side_effect=mock_get_optional(config)
                ):
                    settings = Settings()
                    assert settings.base_currency == "EUR"
                    assert settings.trading_pairs == ["BTC-EUR", "ETH-EUR"]

    def test_mismatched_pair_raises_error(self):
        """CRITICAL: BTC-EUR pair with USD base currency must be rejected.

        Context: Safety requirement CURR-01
        Critical because: Bot would size positions using USD balance against
        EUR prices — completely wrong math and API-rejected orders.
        """
        config = {
            **BASE_CONFIG,
            "BASE_CURRENCY": "USD",
            "TRADING_PAIRS": "BTC-EUR,ETH-USD",
        }
        with patch.dict(os.environ, {"ENVIRONMENT": "dev"}):
            with patch(PATCH_TARGET, side_effect=mock_get(config)):
                with patch(
                    "src.utils.onepassword.get_optional", side_effect=mock_get_optional(config)
                ):
                    with pytest.raises(ValueError, match="BTC-EUR"):
                        Settings()

    def test_all_pairs_mismatched_raises_error(self):
        """All pairs mismatched — error must name at least one offending pair."""
        config = {
            **BASE_CONFIG,
            "BASE_CURRENCY": "GBP",
            "TRADING_PAIRS": "BTC-EUR,ETH-USD,SOL-EUR",
        }
        with patch.dict(os.environ, {"ENVIRONMENT": "dev"}):
            with patch(PATCH_TARGET, side_effect=mock_get(config)):
                with patch(
                    "src.utils.onepassword.get_optional", side_effect=mock_get_optional(config)
                ):
                    with pytest.raises(ValueError, match=r"BTC-EUR|ETH-USD|SOL-EUR"):
                        Settings()

    def test_error_mentions_base_currency(self):
        """Error message must tell the user what BASE_CURRENCY is set to."""
        config = {
            **BASE_CONFIG,
            "BASE_CURRENCY": "USD",
            "TRADING_PAIRS": "BTC-EUR",
        }
        with patch.dict(os.environ, {"ENVIRONMENT": "dev"}):
            with patch(PATCH_TARGET, side_effect=mock_get(config)):
                with patch(
                    "src.utils.onepassword.get_optional", side_effect=mock_get_optional(config)
                ):
                    with pytest.raises(ValueError, match="USD"):
                        Settings()

    def test_single_mismatched_pair_raises_error(self):
        """CRITICAL: Even one mismatched pair in a list must be rejected."""
        config = {
            **BASE_CONFIG,
            "BASE_CURRENCY": "EUR",
            "TRADING_PAIRS": "BTC-EUR,ETH-USD",  # ETH-USD doesn't match EUR
        }
        with patch.dict(os.environ, {"ENVIRONMENT": "dev"}):
            with patch(PATCH_TARGET, side_effect=mock_get(config)):
                with patch(
                    "src.utils.onepassword.get_optional", side_effect=mock_get_optional(config)
                ):
                    with pytest.raises(ValueError, match="ETH-USD"):
                        Settings()

    def test_usd_base_with_usd_pairs_accepted(self):
        """USD base currency with USD pairs should pass validation."""
        config = {
            **BASE_CONFIG,
            "BASE_CURRENCY": "USD",
            "TRADING_PAIRS": "BTC-USD,ETH-USD",
        }
        with patch.dict(os.environ, {"ENVIRONMENT": "dev"}):
            with patch(PATCH_TARGET, side_effect=mock_get(config)):
                with patch(
                    "src.utils.onepassword.get_optional", side_effect=mock_get_optional(config)
                ):
                    settings = Settings()
                    assert settings.base_currency == "USD"
                    assert settings.trading_pairs == ["BTC-USD", "ETH-USD"]

    def test_case_insensitive_base_currency_matching(self):
        """BASE_CURRENCY stored as 'eur' in 1Password should still match 'BTC-EUR'."""
        config = {
            **BASE_CONFIG,
            "BASE_CURRENCY": "eur",  # lowercase in vault
            "TRADING_PAIRS": "BTC-EUR,ETH-EUR",
        }
        with patch.dict(os.environ, {"ENVIRONMENT": "dev"}):
            with patch(PATCH_TARGET, side_effect=mock_get(config)):
                with patch(
                    "src.utils.onepassword.get_optional", side_effect=mock_get_optional(config)
                ):
                    settings = Settings()
                    assert settings.base_currency == "EUR"
