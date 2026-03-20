"""Basic configuration tests."""

from src.config import RiskLevel, StrategyType, TradingMode
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
