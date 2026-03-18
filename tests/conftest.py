"""Shared pytest fixtures and configuration for all tests."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from tests.mocks.mock_onepassword import create_mock_vault

_MOCK_VAULT = create_mock_vault()


# Mock get / get_optional BEFORE importing src.config to prevent Settings() init failure.
def _mock_get(key: str) -> str:
    """Simulate op.get() — raises RuntimeError if key not in mock vault."""
    if key not in _MOCK_VAULT:
        raise RuntimeError(f"'{key}' not found in mock 1Password vault")
    return _MOCK_VAULT[key]


def _mock_get_optional(key: str) -> str | None:
    """Simulate op.get_optional() — returns None if key not in mock vault."""
    return _MOCK_VAULT.get(key)


_patcher_get = patch("src.utils.onepassword.get", side_effect=_mock_get)
_patcher_get_optional = patch("src.utils.onepassword.get_optional", side_effect=_mock_get_optional)
_patcher_get.start()
_patcher_get_optional.start()

# Import AFTER patching to prevent Settings() init failure.
from src.config import RiskLevel  # noqa: E402
from src.data.models import MarketData, OrderSide, Position  # noqa: E402
from src.risk_management.risk_manager import RiskManager  # noqa: E402

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
