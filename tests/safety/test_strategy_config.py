"""Strategy Config Safety Tests

Verifies that per-strategy constants (interval, min signal strength,
order type, stop-loss %, take-profit %) are loaded from 1Password strategy
items and validated correctly.

Falls back to hardcoded defaults when a strategy item is absent so existing
installations are not broken before running `make setup`.
"""

from unittest.mock import patch

import pytest

from src.config import Settings, StrategyConfig

PATCH_OP_GET = "src.utils.onepassword.get"
PATCH_OP_GET_OPTIONAL = "src.utils.onepassword.get_optional"

_BASE_CONFIG = {
    "RISK_LEVEL": "conservative",
    "BASE_CURRENCY": "EUR",
    "TRADING_PAIRS": "BTC-EUR,ETH-EUR",
    "DEFAULT_STRATEGY": "market_making",
    "INITIAL_CAPITAL": "10000",
}

# Canonical defaults matching _STRATEGY_CONFIG_DEFAULTS in config.py
_STRATEGY_DEFAULTS = {
    "market_making": {
        "INTERVAL": "5",
        "MIN_SIGNAL_STRENGTH": "0.3",
        "ORDER_TYPE": "limit",
        "STOP_LOSS_PCT": "0.5",
        "TAKE_PROFIT_PCT": "0.3",
    },
    "momentum": {
        "INTERVAL": "10",
        "MIN_SIGNAL_STRENGTH": "0.6",
        "ORDER_TYPE": "market",
        "STOP_LOSS_PCT": "2.5",
        "TAKE_PROFIT_PCT": "4.0",
    },
    "breakout": {
        "INTERVAL": "5",
        "MIN_SIGNAL_STRENGTH": "0.7",
        "ORDER_TYPE": "market",
        "STOP_LOSS_PCT": "3.0",
        "TAKE_PROFIT_PCT": "5.0",
    },
    "mean_reversion": {
        "INTERVAL": "15",
        "MIN_SIGNAL_STRENGTH": "0.5",
        "ORDER_TYPE": "limit",
        "STOP_LOSS_PCT": "1.0",
        "TAKE_PROFIT_PCT": "1.5",
    },
    "range_reversion": {
        "INTERVAL": "15",
        "MIN_SIGNAL_STRENGTH": "0.5",
        "ORDER_TYPE": "limit",
        "STOP_LOSS_PCT": "1.0",
        "TAKE_PROFIT_PCT": "1.5",
    },
    "multi_strategy": {"INTERVAL": "10", "MIN_SIGNAL_STRENGTH": "0.55", "ORDER_TYPE": "limit"},
}


def _strategy_vault(overrides: dict | None = None) -> dict[str, str]:
    """Build a mock vault including all strategy config keys."""
    config = dict(_BASE_CONFIG)
    for name, fields in _STRATEGY_DEFAULTS.items():
        prefix = f"STRATEGY_{name.upper()}"
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


class TestStrategyConfigLoading:
    """Strategy configs are loaded from 1Password into settings.strategy_configs."""

    def test_all_strategies_present_in_configs(self) -> None:
        """All six strategies must appear in settings.strategy_configs."""
        config = _strategy_vault()
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        expected = {
            "market_making",
            "momentum",
            "breakout",
            "mean_reversion",
            "range_reversion",
            "multi_strategy",
        }
        assert set(s.strategy_configs.keys()) == expected

    def test_strategy_config_values_loaded_correctly(self) -> None:
        """Values from 1Password are stored in StrategyConfig fields."""
        config = _strategy_vault()
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        mm = s.strategy_configs["market_making"]
        assert mm.interval == 5
        assert mm.min_signal_strength == pytest.approx(0.3)
        assert mm.order_type == "limit"
        assert mm.stop_loss_pct == pytest.approx(0.5)
        assert mm.take_profit_pct == pytest.approx(0.3)

        mo = s.strategy_configs["momentum"]
        assert mo.interval == 10
        assert mo.min_signal_strength == pytest.approx(0.6)
        assert mo.order_type == "market"
        assert mo.stop_loss_pct == pytest.approx(2.5)
        assert mo.take_profit_pct == pytest.approx(4.0)

    def test_multi_strategy_has_no_risk_overrides(self) -> None:
        """multi_strategy intentionally omits stop_loss_pct and take_profit_pct."""
        config = _strategy_vault()
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        ms = s.strategy_configs["multi_strategy"]
        assert ms.stop_loss_pct is None
        assert ms.take_profit_pct is None

    def test_strategy_config_falls_back_to_defaults_when_absent(self) -> None:
        """When strategy items are not in 1Password, hardcoded defaults are used."""
        config = dict(_BASE_CONFIG)  # no strategy keys
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        assert s.strategy_configs["market_making"].interval == 5
        assert s.strategy_configs["breakout"].stop_loss_pct == pytest.approx(3.0)
        assert s.strategy_configs["multi_strategy"].stop_loss_pct is None

    def test_1password_values_override_defaults(self) -> None:
        """Values present in 1Password override the hardcoded defaults."""
        config = _strategy_vault({"STRATEGY_MOMENTUM_INTERVAL": "30"})
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        assert s.strategy_configs["momentum"].interval == 30

    def test_strategy_config_returns_strategyconfig_instances(self) -> None:
        """Every value in strategy_configs must be a StrategyConfig instance."""
        config = _strategy_vault()
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        for cfg in s.strategy_configs.values():
            assert isinstance(cfg, StrategyConfig)


class TestStrategyConfigValidation:
    """Invalid strategy config values are rejected with actionable errors."""

    def test_invalid_interval_rejected(self) -> None:
        """Non-integer STRATEGY_*_INTERVAL MUST be rejected."""
        config = _strategy_vault({"STRATEGY_MOMENTUM_INTERVAL": "not_an_int"})
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)interval"):
                Settings()

    def test_zero_interval_rejected(self) -> None:
        """STRATEGY_*_INTERVAL=0 MUST be rejected."""
        config = _strategy_vault({"STRATEGY_BREAKOUT_INTERVAL": "0"})
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)interval"):
                Settings()

    def test_invalid_min_signal_strength_rejected(self) -> None:
        """Non-numeric MIN_SIGNAL_STRENGTH MUST be rejected."""
        config = _strategy_vault({"STRATEGY_MARKET_MAKING_MIN_SIGNAL_STRENGTH": "strong"})
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)min_signal_strength"):
                Settings()

    def test_min_signal_strength_above_one_rejected(self) -> None:
        """MIN_SIGNAL_STRENGTH > 1.0 MUST be rejected."""
        config = _strategy_vault({"STRATEGY_MOMENTUM_MIN_SIGNAL_STRENGTH": "1.5"})
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)min_signal_strength"):
                Settings()

    def test_invalid_order_type_rejected(self) -> None:
        """ORDER_TYPE values other than 'limit'/'market' MUST be rejected."""
        config = _strategy_vault({"STRATEGY_BREAKOUT_ORDER_TYPE": "instant"})
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)order_type"):
                Settings()

    def test_order_type_case_insensitive(self) -> None:
        """ORDER_TYPE is normalised to lowercase regardless of vault case."""
        config = _strategy_vault({"STRATEGY_MOMENTUM_ORDER_TYPE": "MARKET"})
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        assert s.strategy_configs["momentum"].order_type == "market"

    def test_negative_stop_loss_pct_rejected(self) -> None:
        """Negative STOP_LOSS_PCT MUST be rejected."""
        config = _strategy_vault({"STRATEGY_MARKET_MAKING_STOP_LOSS_PCT": "-1.0"})
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)stop_loss_pct"):
                Settings()

    def test_negative_take_profit_pct_rejected(self) -> None:
        """Negative TAKE_PROFIT_PCT MUST be rejected."""
        config = _strategy_vault({"STRATEGY_MOMENTUM_TAKE_PROFIT_PCT": "-2.0"})
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)take_profit_pct"):
                Settings()


class TestStrategyInternalParams:
    """Strategy internal calibration parameters are loaded from 1Password strategy items."""

    def test_momentum_internal_params_loaded_from_vault(self) -> None:
        """Momentum fast/slow/rsi period overrides are loaded correctly."""
        config = _strategy_vault(
            {
                "STRATEGY_MOMENTUM_FAST_PERIOD": "8",
                "STRATEGY_MOMENTUM_SLOW_PERIOD": "21",
                "STRATEGY_MOMENTUM_RSI_PERIOD": "10",
                "STRATEGY_MOMENTUM_RSI_OVERBOUGHT": "75.0",
                "STRATEGY_MOMENTUM_RSI_OVERSOLD": "25.0",
            }
        )
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        mo = s.strategy_configs["momentum"]
        assert mo.fast_period == 8
        assert mo.slow_period == 21
        assert mo.rsi_period == 10
        assert mo.rsi_overbought == pytest.approx(75.0)
        assert mo.rsi_oversold == pytest.approx(25.0)

    def test_market_making_spread_and_inventory_loaded(self) -> None:
        """Market-making spread_threshold and inventory_target are loaded."""
        config = _strategy_vault(
            {
                "STRATEGY_MARKET_MAKING_SPREAD_THRESHOLD": "0.001",
                "STRATEGY_MARKET_MAKING_INVENTORY_TARGET": "0.4",
            }
        )
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        mm = s.strategy_configs["market_making"]
        assert mm.spread_threshold == pytest.approx(0.001)
        assert mm.inventory_target == pytest.approx(0.4)

    def test_mean_reversion_internal_params_loaded(self) -> None:
        """Mean reversion lookback, std_dev, and min_deviation are loaded."""
        config = _strategy_vault(
            {
                "STRATEGY_MEAN_REVERSION_LOOKBACK_PERIOD": "30",
                "STRATEGY_MEAN_REVERSION_NUM_STD_DEV": "2.5",
                "STRATEGY_MEAN_REVERSION_MIN_DEVIATION": "0.02",
            }
        )
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        mr = s.strategy_configs["mean_reversion"]
        assert mr.lookback_period == 30
        assert mr.num_std_dev == pytest.approx(2.5)
        assert mr.min_deviation == pytest.approx(0.02)

    def test_breakout_internal_params_loaded(self) -> None:
        """Breakout lookback, threshold, and RSI params are loaded."""
        config = _strategy_vault(
            {
                "STRATEGY_BREAKOUT_LOOKBACK_PERIOD": "25",
                "STRATEGY_BREAKOUT_BREAKOUT_THRESHOLD": "0.003",
                "STRATEGY_BREAKOUT_RSI_PERIOD": "10",
                "STRATEGY_BREAKOUT_RSI_OVERBOUGHT": "80.0",
                "STRATEGY_BREAKOUT_RSI_OVERSOLD": "20.0",
            }
        )
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        bo = s.strategy_configs["breakout"]
        assert bo.lookback_period == 25
        assert bo.breakout_threshold == pytest.approx(0.003)
        assert bo.rsi_period == 10
        assert bo.rsi_overbought == pytest.approx(80.0)
        assert bo.rsi_oversold == pytest.approx(20.0)

    def test_range_reversion_internal_params_loaded(self) -> None:
        """Range reversion buy/sell zones and RSI confirmation levels are loaded."""
        config = _strategy_vault(
            {
                "STRATEGY_RANGE_REVERSION_BUY_ZONE": "0.15",
                "STRATEGY_RANGE_REVERSION_SELL_ZONE": "0.85",
                "STRATEGY_RANGE_REVERSION_RSI_PERIOD": "9",
                "STRATEGY_RANGE_REVERSION_RSI_CONFIRMATION_OVERSOLD": "35.0",
                "STRATEGY_RANGE_REVERSION_RSI_CONFIRMATION_OVERBOUGHT": "65.0",
                "STRATEGY_RANGE_REVERSION_MIN_RANGE_PCT": "0.02",
            }
        )
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        rr = s.strategy_configs["range_reversion"]
        assert rr.buy_zone == pytest.approx(0.15)
        assert rr.sell_zone == pytest.approx(0.85)
        assert rr.rsi_period == 9
        assert rr.rsi_confirmation_oversold == pytest.approx(35.0)
        assert rr.rsi_confirmation_overbought == pytest.approx(65.0)
        assert rr.min_range_pct == pytest.approx(0.02)

    def test_multi_strategy_weights_and_consensus_loaded(self) -> None:
        """Multi-strategy weights and min_consensus are loaded."""
        config = _strategy_vault(
            {
                "STRATEGY_MULTI_STRATEGY_MIN_CONSENSUS": "0.7",
                "STRATEGY_MULTI_STRATEGY_WEIGHT_MOMENTUM": "0.35",
                "STRATEGY_MULTI_STRATEGY_WEIGHT_BREAKOUT": "0.25",
                "STRATEGY_MULTI_STRATEGY_WEIGHT_MARKET_MAKING": "0.15",
                "STRATEGY_MULTI_STRATEGY_WEIGHT_MEAN_REVERSION": "0.15",
                "STRATEGY_MULTI_STRATEGY_WEIGHT_RANGE_REVERSION": "0.10",
            }
        )
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        ms = s.strategy_configs["multi_strategy"]
        assert ms.min_consensus == pytest.approx(0.7)
        assert ms.weight_momentum == pytest.approx(0.35)
        assert ms.weight_breakout == pytest.approx(0.25)
        assert ms.weight_market_making == pytest.approx(0.15)
        assert ms.weight_mean_reversion == pytest.approx(0.15)
        assert ms.weight_range_reversion == pytest.approx(0.10)

    def test_internal_params_none_when_absent(self) -> None:
        """Internal params absent from vault are stored as None (strategy uses its own defaults)."""
        config = _strategy_vault()  # no internal params beyond core fields
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            s = Settings()

        mo = s.strategy_configs["momentum"]
        assert mo.fast_period is None
        assert mo.slow_period is None
        assert mo.rsi_period is None

    def test_negative_rsi_period_rejected(self) -> None:
        """Negative RSI_PERIOD MUST be rejected."""
        config = _strategy_vault({"STRATEGY_MOMENTUM_RSI_PERIOD": "-5"})
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)rsi_period"):
                Settings()

    def test_invalid_buy_zone_above_one_rejected(self) -> None:
        """BUY_ZONE > 1.0 MUST be rejected."""
        config = _strategy_vault({"STRATEGY_RANGE_REVERSION_BUY_ZONE": "1.5"})
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)buy_zone"):
                Settings()

    def test_invalid_sell_zone_below_zero_rejected(self) -> None:
        """SELL_ZONE < 0 MUST be rejected."""
        config = _strategy_vault({"STRATEGY_RANGE_REVERSION_SELL_ZONE": "-0.1"})
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)sell_zone"):
                Settings()

    def test_invalid_min_consensus_above_one_rejected(self) -> None:
        """MIN_CONSENSUS > 1.0 MUST be rejected."""
        config = _strategy_vault({"STRATEGY_MULTI_STRATEGY_MIN_CONSENSUS": "1.5"})
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)min_consensus"):
                Settings()

    def test_negative_breakout_threshold_rejected(self) -> None:
        """Negative BREAKOUT_THRESHOLD MUST be rejected."""
        config = _strategy_vault({"STRATEGY_BREAKOUT_BREAKOUT_THRESHOLD": "-0.001"})
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)breakout_threshold"):
                Settings()

    def test_negative_min_range_pct_rejected(self) -> None:
        """Negative MIN_RANGE_PCT MUST be rejected (0.0 is allowed — disables the filter)."""
        config = _strategy_vault({"STRATEGY_RANGE_REVERSION_MIN_RANGE_PCT": "-0.01"})
        with (
            patch(PATCH_OP_GET, side_effect=_mock_get(config)),
            patch(PATCH_OP_GET_OPTIONAL, side_effect=_mock_get_optional(config)),
        ):
            with pytest.raises(ValueError, match=r"(?i)min_range_pct"):
                Settings()

    def test_multi_strategy_weight_overrides_applied_on_instantiation(self) -> None:
        """MultiStrategy.__init__ applies weight overrides from Settings when non-None."""
        from src.config import StrategyConfig
        from src.strategies.multi_strategy import MultiStrategy

        # Build a StrategyConfig with all weight overrides set (non-None).
        cfg_with_weights = StrategyConfig(
            interval=10,
            min_signal_strength=0.55,
            order_type="limit",
            weight_momentum=0.40,
            weight_breakout=0.20,
            weight_market_making=0.15,
            weight_mean_reversion=0.15,
            weight_range_reversion=0.10,
        )

        # Patch the module-level settings singleton so MultiStrategy sees the overrides.
        with patch("src.config.settings") as mock_settings:
            mock_settings.strategy_configs = {"multi_strategy": cfg_with_weights}
            strategy = MultiStrategy()

        # After normalisation the ratios should be preserved
        total = sum(strategy.weights.values())
        assert abs(total - 1.0) < 0.01
        # momentum has highest weight (0.40 vs others)
        assert strategy.weights["momentum"] > strategy.weights["breakout"]
