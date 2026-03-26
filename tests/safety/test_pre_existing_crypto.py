"""Pre-existing Crypto Protection Tests - CRITICAL

These tests verify that the bot never sells crypto it did not open a position
in. This protects pre-existing holdings (e.g., BTC you hold as a long-term
investment) from being accidentally liquidated by the bot's strategy signals.

Critical because: The Revolut X API fills sell orders from your total account
holdings — it does not distinguish "bot-bought BTC" from "personally held BTC".
If the bot places a sell order for a symbol it never bought, it would consume
the user's pre-existing crypto.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.config import RiskLevel, TradingMode
from src.execution.executor import OrderExecutor
from src.models.domain import OrderSide, OrderStatus, Position, Signal
from src.risk_management.risk_manager import RiskManager


def make_signal(
    symbol: str = "BTC-EUR",
    signal_type: str = "SELL",
    price: Decimal = Decimal("50000"),
    strength: float = 0.5,
) -> Signal:
    from datetime import UTC, datetime

    return Signal(
        symbol=symbol,
        strategy="market_making",
        signal_type=signal_type,
        strength=strength,
        price=price,
        reason="test signal",
        timestamp=datetime.now(UTC),
    )


def make_position(
    symbol: str = "BTC-EUR",
    quantity: Decimal = Decimal("0.1"),
    entry_price: Decimal = Decimal("48000"),
) -> Position:
    return Position(
        symbol=symbol,
        side=OrderSide.BUY,
        quantity=quantity,
        entry_price=entry_price,
        current_price=entry_price,
        unrealized_pnl=Decimal("0"),
    )


@pytest.fixture
def mock_api():
    api = MagicMock()
    api.create_order = AsyncMock(
        return_value={"venue_order_id": "live-123", "client_order_id": "c-123", "state": "new"}
    )
    return api


@pytest.fixture
def executor(mock_api):
    rm = RiskManager(RiskLevel.MODERATE, max_order_value=100_000)
    return OrderExecutor(mock_api, rm, TradingMode.LIVE)


class TestPreExistingCryptoProtection:
    """Bot must never sell crypto it did not open a position in."""

    @pytest.mark.asyncio
    async def test_sell_signal_blocked_when_no_position(self, executor, mock_api):
        """CRITICAL: SELL signal for a symbol with no tracked position must be rejected.

        Context: Safety requirement CRYPTO-01
        Critical because: the Revolut API fills sells from total account holdings.
        A stray SELL signal would liquidate the user's pre-existing crypto.
        """
        signal = make_signal(symbol="BTC-EUR", signal_type="SELL")
        assert "BTC-EUR" not in executor.positions  # no position opened by bot

        order = await executor.execute_signal(signal, portfolio_value=Decimal("10000"))

        assert order is not None
        assert order.status == OrderStatus.REJECTED
        mock_api.create_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_sell_signal_allowed_when_position_exists(self, executor, mock_api):
        """SELL signal is allowed only when the bot has an open position for that symbol."""
        # Portfolio large enough so risk checks pass: 0.1 BTC @ 50000 = 5000 EUR = 1% of 500k
        executor.positions["BTC-EUR"] = make_position("BTC-EUR")

        signal = make_signal(symbol="BTC-EUR", signal_type="SELL")

        order = await executor.execute_signal(signal, portfolio_value=Decimal("500000"))

        # Key assertion: the no-position guard did NOT reject this order
        assert order is not None
        assert order.status != OrderStatus.REJECTED
        mock_api.create_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_buy_signal_always_allowed(self, executor, mock_api):
        """BUY signals should never be blocked by the no-position guard."""
        assert "BTC-EUR" not in executor.positions

        signal = make_signal(symbol="BTC-EUR", signal_type="BUY")
        # Portfolio large enough so risk checks pass: 3% of 500k = 15000 EUR; order = 0.3 BTC
        await executor.execute_signal(signal, portfolio_value=Decimal("500000"))

        # BUY should reach the API regardless of whether a position exists
        mock_api.create_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_sell_blocked_for_correct_symbol_only(self, executor, mock_api):
        """SELL blocked only for the symbol with no position; other symbols are unaffected."""
        # Bot has an ETH position but NOT a BTC position
        executor.positions["ETH-EUR"] = make_position("ETH-EUR")

        btc_sell = make_signal(symbol="BTC-EUR", signal_type="SELL")
        order = await executor.execute_signal(btc_sell, portfolio_value=Decimal("10000"))

        assert order.status == OrderStatus.REJECTED
        mock_api.create_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_shutdown_does_not_touch_symbols_outside_positions(self, executor, mock_api):
        """Graceful shutdown only closes positions the bot opened — never pre-existing crypto."""
        mock_api.cancel_all_orders = AsyncMock()

        # Bot has no positions — simulates a user who holds BTC externally
        assert executor.positions == {}

        summary = await executor.graceful_shutdown()

        assert summary.positions_closed == 0
        assert summary.positions_trailing_stopped == 0
        mock_api.cancel_all_orders.assert_not_called()  # no orders to cancel either
