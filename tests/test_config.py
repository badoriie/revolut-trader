"""Basic configuration tests."""

from unittest.mock import MagicMock

import pytest

from src.config import RiskLevel, Settings, StrategyType, TradingMode
from src.risk_management.risk_manager import RiskManager


def test_risk_levels():
    """Test risk level enumeration."""
    assert RiskLevel.CONSERVATIVE.value == "conservative"
    assert RiskLevel.MODERATE.value == "moderate"
    assert RiskLevel.AGGRESSIVE.value == "aggressive"


def test_strategy_types():
    """Test strategy type enumeration."""
    assert StrategyType.MARKET_MAKING.value == "market_making"
    assert StrategyType.MOMENTUM.value == "momentum"
    assert StrategyType.MEAN_REVERSION.value == "mean_reversion"
    assert StrategyType.MULTI_STRATEGY.value == "multi_strategy"


def test_trading_modes():
    """Test trading mode enumeration."""
    assert TradingMode.PAPER.value == "paper"
    assert TradingMode.LIVE.value == "live"


def test_risk_parameters():
    """Risk parameters are owned by RiskManager, not Settings."""
    risk_params = RiskManager(RiskLevel.CONSERVATIVE).get_risk_parameters()
    assert "max_position_size_pct" in risk_params
    assert "max_daily_loss_pct" in risk_params
    assert "stop_loss_pct" in risk_params
    assert "take_profit_pct" in risk_params
    assert "max_open_positions" in risk_params


# ── Settings._load_strategy_bool ──────────────────────────────────────────────


def test_load_strategy_bool_returns_none_when_absent():
    """`_load_strategy_bool` returns None when the key is not in 1Password."""
    mock_op = MagicMock()
    mock_op.get_optional.return_value = None
    assert Settings._load_strategy_bool(mock_op, "KEY", "strat", "FIELD") is None


def test_load_strategy_bool_returns_true_case_insensitive():
    """`_load_strategy_bool` accepts 'True' / 'TRUE' / 'true' as True."""
    mock_op = MagicMock()
    for value in ("true", "True", "TRUE"):
        mock_op.get_optional.return_value = value
        assert Settings._load_strategy_bool(mock_op, "KEY", "strat", "FIELD") is True


def test_load_strategy_bool_returns_false_case_insensitive():
    """`_load_strategy_bool` accepts 'False' / 'FALSE' / 'false' as False."""
    mock_op = MagicMock()
    for value in ("false", "False", "FALSE"):
        mock_op.get_optional.return_value = value
        assert Settings._load_strategy_bool(mock_op, "KEY", "strat", "FIELD") is False


def test_load_strategy_bool_raises_for_invalid_value():
    """`_load_strategy_bool` raises ValueError for unexpected strings like 'yes'."""
    mock_op = MagicMock()
    mock_op.get_optional.return_value = "yes"
    with pytest.raises(ValueError, match="expected 'true' or 'false'"):
        Settings._load_strategy_bool(mock_op, "KEY", "strat", "FIELD")
