"""Shared pytest fixtures and configuration for all tests."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest


# Mock get_config BEFORE importing src.config to prevent global settings init failure
def _mock_get_config(key, default=None):
    """Default mock for get_config during test imports."""
    config = {
        "TRADING_MODE": "paper",
        "RISK_LEVEL": "conservative",
        "BASE_CURRENCY": "EUR",
        "TRADING_PAIRS": "BTC-EUR,ETH-EUR",
        "DEFAULT_STRATEGY": "market_making",
        "INITIAL_CAPITAL": "10000",
    }
    return config.get(key, default)


# Patch get_config globally for all tests
_patcher = patch("src.utils.onepassword.get_config", side_effect=_mock_get_config)
_patcher.start()

# Import AFTER patching to prevent Settings() init failure
from src.config import RiskLevel  # noqa: E402
from src.data.models import MarketData, OrderSide, Position  # noqa: E402
from src.risk_management.risk_manager import RiskManager  # noqa: E402
from tests.mocks.mock_onepassword import (  # noqa: E402
    Mock1PasswordClient,
    MockConfigClient,
    create_valid_config,
    create_valid_credentials,
)

# ============================================================================
# 1Password Mocks
# ============================================================================


@pytest.fixture
def valid_1password_config():
    """1Password with complete valid configuration."""
    return MockConfigClient(config=create_valid_config(), available=True)


@pytest.fixture
def valid_1password_credentials():
    """1Password with valid credentials."""
    return Mock1PasswordClient(credentials=create_valid_credentials(), available=True)


@pytest.fixture
def missing_trading_mode_config():
    """1Password config missing TRADING_MODE - should cause failure."""
    config = create_valid_config()
    del config["TRADING_MODE"]
    return MockConfigClient(config=config, available=True)


@pytest.fixture
def missing_risk_level_config():
    """1Password config missing RISK_LEVEL - should cause failure."""
    config = create_valid_config()
    del config["RISK_LEVEL"]
    return MockConfigClient(config=config, available=True)


@pytest.fixture
def invalid_trading_mode_config():
    """1Password config with invalid TRADING_MODE value."""
    config = create_valid_config()
    config["TRADING_MODE"] = "invalid_mode"
    return MockConfigClient(config=config, available=True)


@pytest.fixture
def unavailable_1password():
    """1Password CLI not available (not installed or not signed in)."""
    return MockConfigClient(config={}, available=False)


# ============================================================================
# Market Data
# ============================================================================


@pytest.fixture
def btc_market_data():
    """Sample BTC-EUR market data."""
    return MarketData(
        symbol="BTC-EUR",
        timestamp=datetime.now(UTC),
        bid=Decimal("49950"),
        ask=Decimal("50050"),
        last=Decimal("50000"),
        volume_24h=Decimal("1000"),
        high_24h=Decimal("51000"),
        low_24h=Decimal("49000"),
    )


@pytest.fixture
def eth_market_data():
    """Sample ETH-EUR market data."""
    return MarketData(
        symbol="ETH-EUR",
        timestamp=datetime.now(UTC),
        bid=Decimal("2995"),
        ask=Decimal("3005"),
        last=Decimal("3000"),
        volume_24h=Decimal("5000"),
        high_24h=Decimal("3100"),
        low_24h=Decimal("2900"),
    )


# ============================================================================
# Positions
# ============================================================================


@pytest.fixture
def btc_long_position():
    """Sample BTC long position (bought at 50000 EUR)."""
    return Position(
        symbol="BTC-EUR",
        side=OrderSide.BUY,
        entry_price=Decimal("50000"),
        current_price=Decimal("50000"),
        quantity=Decimal("0.1"),
        stop_loss=Decimal("49000"),
        take_profit=Decimal("51500"),
    )


@pytest.fixture
def eth_long_position():
    """Sample ETH long position (bought at 3000 EUR)."""
    return Position(
        symbol="ETH-EUR",
        side=OrderSide.BUY,
        entry_price=Decimal("3000"),
        current_price=Decimal("3000"),
        quantity=Decimal("1.0"),
        stop_loss=Decimal("2940"),
        take_profit=Decimal("3090"),
    )


# ============================================================================
# Risk Management
# ============================================================================


@pytest.fixture
def conservative_risk_manager():
    """Risk manager with conservative settings.

    - Max position size: 1.5%
    - Max daily loss: 3%
    - Stop loss: 1.5%
    - Take profit: 2.5%
    - Max open positions: 3
    """
    return RiskManager(risk_level=RiskLevel.CONSERVATIVE, max_order_value_usd=10000)


@pytest.fixture
def moderate_risk_manager():
    """Risk manager with moderate settings.

    - Max position size: 3%
    - Max daily loss: 5%
    - Stop loss: 2.5%
    - Take profit: 4%
    - Max open positions: 5
    """
    return RiskManager(risk_level=RiskLevel.MODERATE, max_order_value_usd=10000)


@pytest.fixture
def aggressive_risk_manager():
    """Risk manager with aggressive settings.

    - Max position size: 5%
    - Max daily loss: 10%
    - Stop loss: 4%
    - Take profit: 7%
    - Max open positions: 8
    """
    return RiskManager(risk_level=RiskLevel.AGGRESSIVE, max_order_value_usd=10000)


# ============================================================================
# Portfolio Values
# ============================================================================


@pytest.fixture
def small_portfolio_value():
    """Small portfolio: 1,000 EUR."""
    return Decimal("1000")


@pytest.fixture
def medium_portfolio_value():
    """Medium portfolio: 10,000 EUR."""
    return Decimal("10000")


@pytest.fixture
def large_portfolio_value():
    """Large portfolio: 100,000 EUR."""
    return Decimal("100000")
