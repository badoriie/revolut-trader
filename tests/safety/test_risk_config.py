"""Risk Level Config Safety Tests

Verifies that per-risk-level parameters (max position size, daily loss limit,
stop-loss %, take-profit %, max open positions) are loaded from 1Password risk
items and validated correctly.

Falls back to hardcoded defaults when a risk item is absent so existing
installations are not broken before running `make setup`.
"""

from unittest.mock import patch

import pytest

from src.config import RiskLevelConfig, Settings

PATCH_OP_GET = "src.utils.onepassword.get"
PATCH_OP_GET_OPTIONAL = "src.utils.onepassword.get_optional"

_BASE_CONFIG = {
    "RISK_LEVEL": "conservative",
    "BASE_CURRENCY": "EUR",
    "TRADING_PAIRS": "BTC-EUR,ETH-EUR",
    "DEFAULT_STRATEGY": "market_making",
    "INITIAL_CAPITAL": "10000",
}

# Canonical defaults matching _RISK_LEVEL_CONFIG_DEFAULTS in config.py
_RISK_DEFAULTS = {
    "conservative": {
        "MAX_POSITION_SIZE_PCT": "1.5",
        "MAX_DAILY_LOSS_PCT": "3.0",
        "STOP_LOSS_PCT": "1.5",
        "TAKE_PROFIT_PCT": "2.5",
        "MAX_OPEN_POSITIONS": "3",
    },
    "moderate": {
        "MAX_POSITION_SIZE_PCT": "3.0",
        "MAX_DAILY_LOSS_PCT": "5.0",
        "STOP_LOSS_PCT": "2.5",
        "TAKE_PROFIT_PCT": "4.0",
        "MAX_OPEN_POSITIONS": "5",
    },
    "aggressive": {
        "MAX_POSITION_SIZE_PCT": "5.0",
        "MAX_DAILY_LOSS_PCT": "10.0",
        "STOP_LOSS_PCT": "4.0",
        "TAKE_PROFIT_PCT": "7.0",
        "MAX_OPEN_POSITIONS": "8",
    },
}


def _risk_vault(overrides: dict | None = None) -> dict[str, str]:
    """Build a mock vault including all risk config keys."""
    config = dict(_BASE_CONFIG)
    for level, fields in _RISK_DEFAULTS.items():
        prefix = f"RISK_{level.upper()}"
        for field, value in fields.items():
            config[f"{prefix}_{field}"] = value
    if overrides:
        config.update(overrides)
    return config


def _mock_get(config_dict):
    def get_impl(key):
        if key not in config_dict:
            raise RuntimeError(f"{key} not found")
        return config_dict[key]

    return get_impl


def _mock_get_optional(config_dict):
    return lambda key: config_dict.get(key)


class TestRiskLevelConfigLoading:
    """Risk configs are loaded from 1Password into settings.risk_configs."""

    def test_all_risk_levels_present_in_configs(self) -> None:
        """All three risk levels must appear in settings.risk_configs."""
        config = _risk_vault()
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        expected = {"conservative", "moderate", "aggressive"}
        assert set(s.risk_configs.keys()) == expected

    def test_conservative_risk_config_values_loaded_correctly(self) -> None:
        """Conservative risk level values from 1Password are correct."""
        config = _risk_vault()
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        c = s.risk_configs["conservative"]
        assert c.max_position_size_pct == pytest.approx(1.5)
        assert c.max_daily_loss_pct == pytest.approx(3.0)
        assert c.stop_loss_pct == pytest.approx(1.5)
        assert c.take_profit_pct == pytest.approx(2.5)
        assert c.max_open_positions == 3

    def test_moderate_risk_config_values_loaded_correctly(self) -> None:
        """Moderate risk level values from 1Password are correct."""
        config = _risk_vault()
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        m = s.risk_configs["moderate"]
        assert m.max_position_size_pct == pytest.approx(3.0)
        assert m.max_open_positions == 5

    def test_aggressive_risk_config_values_loaded_correctly(self) -> None:
        """Aggressive risk level values from 1Password are correct."""
        config = _risk_vault()
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        a = s.risk_configs["aggressive"]
        assert a.max_position_size_pct == pytest.approx(5.0)
        assert a.max_open_positions == 8

    def test_risk_config_falls_back_to_defaults_when_absent(self) -> None:
        """When risk items are not in 1Password, hardcoded defaults are used."""
        config = dict(_BASE_CONFIG)  # no risk keys
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        assert s.risk_configs["conservative"].max_position_size_pct == pytest.approx(1.5)
        assert s.risk_configs["moderate"].max_open_positions == 5
        assert s.risk_configs["aggressive"].stop_loss_pct == pytest.approx(4.0)

    def test_1password_values_override_defaults(self) -> None:
        """Values present in 1Password override the hardcoded defaults."""
        config = _risk_vault({"RISK_CONSERVATIVE_MAX_POSITION_SIZE_PCT": "2.0"})
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        assert s.risk_configs["conservative"].max_position_size_pct == pytest.approx(2.0)

    def test_risk_config_returns_risklevelconfig_instances(self) -> None:
        """Every value in risk_configs must be a RiskLevelConfig instance."""
        config = _risk_vault()
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        for cfg in s.risk_configs.values():
            assert isinstance(cfg, RiskLevelConfig)


class TestRiskLevelConfigValidation:
    """Invalid risk config values are rejected with actionable errors."""

    def test_invalid_max_position_size_pct_rejected(self) -> None:
        """Non-numeric MAX_POSITION_SIZE_PCT MUST be rejected."""
        config = _risk_vault({"RISK_CONSERVATIVE_MAX_POSITION_SIZE_PCT": "huge"})
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)max_position_size_pct"):
                Settings()

    def test_zero_max_position_size_pct_rejected(self) -> None:
        """MAX_POSITION_SIZE_PCT=0 MUST be rejected."""
        config = _risk_vault({"RISK_MODERATE_MAX_POSITION_SIZE_PCT": "0"})
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)max_position_size_pct"):
                Settings()

    def test_zero_max_open_positions_rejected(self) -> None:
        """MAX_OPEN_POSITIONS=0 MUST be rejected."""
        config = _risk_vault({"RISK_AGGRESSIVE_MAX_OPEN_POSITIONS": "0"})
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)max_open_positions"):
                Settings()

    def test_invalid_max_open_positions_rejected(self) -> None:
        """Non-integer MAX_OPEN_POSITIONS MUST be rejected."""
        config = _risk_vault({"RISK_CONSERVATIVE_MAX_OPEN_POSITIONS": "many"})
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)max_open_positions"):
                Settings()

    def test_negative_stop_loss_pct_rejected(self) -> None:
        """Negative STOP_LOSS_PCT MUST be rejected."""
        config = _risk_vault({"RISK_MODERATE_STOP_LOSS_PCT": "-2.0"})
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)stop_loss_pct"):
                Settings()

    def test_invalid_max_daily_loss_pct_rejected(self) -> None:
        """Non-numeric MAX_DAILY_LOSS_PCT MUST be rejected."""
        config = _risk_vault({"RISK_AGGRESSIVE_MAX_DAILY_LOSS_PCT": "alot"})
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)max_daily_loss_pct"):
                Settings()

    def test_zero_max_daily_loss_pct_rejected(self) -> None:
        """MAX_DAILY_LOSS_PCT=0 MUST be rejected (must be strictly positive)."""
        config = _risk_vault({"RISK_MODERATE_MAX_DAILY_LOSS_PCT": "0"})
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)max_daily_loss_pct"):
                Settings()

    def test_negative_take_profit_pct_rejected(self) -> None:
        """Negative TAKE_PROFIT_PCT MUST be rejected."""
        config = _risk_vault({"RISK_CONSERVATIVE_TAKE_PROFIT_PCT": "-1.0"})
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)take_profit_pct"):
                Settings()
