"""Fee Config Safety Tests

Verifies that trading fee rates (maker/taker) are loaded from 1Password config
and validated correctly.

Falls back to the published Revolut X fee schedule when absent: 0% maker (LIMIT),
0.09% taker (MARKET).  These values can change if Revolut updates its fee schedule
— having them in 1Password means users can update without a code change.
"""

from unittest.mock import patch

import pytest

from src.config import Settings

PATCH_OP_GET = "src.utils.onepassword.get"
PATCH_OP_GET_OPTIONAL = "src.utils.onepassword.get_optional"

_BASE_CONFIG = {
    "RISK_LEVEL": "conservative",
    "BASE_CURRENCY": "EUR",
    "TRADING_PAIRS": "BTC-EUR,ETH-EUR",
    "DEFAULT_STRATEGY": "market_making",
    "INITIAL_CAPITAL": "10000",
}


def _mock_get(config_dict):
    def get_impl(key):
        if key not in config_dict:
            raise RuntimeError(f"{key} not found")
        return config_dict[key]

    return get_impl


def _mock_get_optional(config_dict):
    return lambda key: config_dict.get(key)


class TestFeeConfigLoading:
    """Fee constants are loaded from 1Password with correct defaults."""

    def test_defaults_used_when_fee_keys_absent(self) -> None:
        """When MAKER_FEE_PCT and TAKER_FEE_PCT are absent, defaults are used."""
        config = dict(_BASE_CONFIG)
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        assert s.maker_fee_pct == pytest.approx(0.0)
        assert s.taker_fee_pct == pytest.approx(0.0009)

    def test_maker_fee_override_from_1password(self) -> None:
        """MAKER_FEE_PCT from 1Password overrides the default of 0."""
        config = {**_BASE_CONFIG, "MAKER_FEE_PCT": "0.0001"}
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        assert s.maker_fee_pct == pytest.approx(0.0001)

    def test_taker_fee_override_from_1password(self) -> None:
        """TAKER_FEE_PCT from 1Password overrides the default."""
        config = {**_BASE_CONFIG, "TAKER_FEE_PCT": "0.001"}
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        assert s.taker_fee_pct == pytest.approx(0.001)

    def test_both_fees_can_be_set(self) -> None:
        """Both maker and taker fees can be set independently."""
        config = {**_BASE_CONFIG, "MAKER_FEE_PCT": "0.0002", "TAKER_FEE_PCT": "0.0015"}
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        assert s.maker_fee_pct == pytest.approx(0.0002)
        assert s.taker_fee_pct == pytest.approx(0.0015)


class TestFeeConfigValidation:
    """Invalid fee values are rejected with actionable errors."""

    def test_non_numeric_maker_fee_rejected(self) -> None:
        """Non-numeric MAKER_FEE_PCT MUST be rejected."""
        config = {**_BASE_CONFIG, "MAKER_FEE_PCT": "free"}
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)maker_fee_pct"):
                Settings()

    def test_non_numeric_taker_fee_rejected(self) -> None:
        """Non-numeric TAKER_FEE_PCT MUST be rejected."""
        config = {**_BASE_CONFIG, "TAKER_FEE_PCT": "cheap"}
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)taker_fee_pct"):
                Settings()

    def test_negative_maker_fee_rejected(self) -> None:
        """Negative MAKER_FEE_PCT MUST be rejected."""
        config = {**_BASE_CONFIG, "MAKER_FEE_PCT": "-0.001"}
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)maker_fee_pct"):
                Settings()

    def test_negative_taker_fee_rejected(self) -> None:
        """Negative TAKER_FEE_PCT MUST be rejected."""
        config = {**_BASE_CONFIG, "TAKER_FEE_PCT": "-0.001"}
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)taker_fee_pct"):
                Settings()


class TestSafetyLimitsConfigLoading:
    """Safety limit constants (max/min order value) are loaded from 1Password."""

    def test_defaults_used_when_absent(self) -> None:
        """When MAX_ORDER_VALUE and MIN_ORDER_VALUE are absent, defaults apply."""
        config = dict(_BASE_CONFIG)
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        assert s.max_order_value == pytest.approx(10000.0)
        assert s.min_order_value == pytest.approx(10.0)

    def test_max_order_value_override_from_1password(self) -> None:
        """MAX_ORDER_VALUE from 1Password overrides the default."""
        config = {**_BASE_CONFIG, "MAX_ORDER_VALUE": "5000"}
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        assert s.max_order_value == pytest.approx(5000.0)

    def test_min_order_value_override_from_1password(self) -> None:
        """MIN_ORDER_VALUE from 1Password overrides the default."""
        config = {**_BASE_CONFIG, "MIN_ORDER_VALUE": "25"}
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        assert s.min_order_value == pytest.approx(25.0)

    def test_zero_max_order_value_rejected(self) -> None:
        """MAX_ORDER_VALUE=0 MUST be rejected."""
        config = {**_BASE_CONFIG, "MAX_ORDER_VALUE": "0"}
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)max_order_value"):
                Settings()

    def test_zero_min_order_value_rejected(self) -> None:
        """MIN_ORDER_VALUE=0 MUST be rejected."""
        config = {**_BASE_CONFIG, "MIN_ORDER_VALUE": "0"}
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)min_order_value"):
                Settings()

    def test_non_numeric_max_order_value_rejected(self) -> None:
        """Non-numeric MAX_ORDER_VALUE MUST be rejected."""
        config = {**_BASE_CONFIG, "MAX_ORDER_VALUE": "alot"}
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)max_order_value"):
                Settings()
