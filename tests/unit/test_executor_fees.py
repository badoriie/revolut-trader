"""Unit tests for fee tracking in OrderExecutor.

Verifies that:
- Paper fills populate order.commission correctly (MARKET vs LIMIT rate)
- Closing orders deduct the fee from realized_pnl
- Opening orders leave realized_pnl as None
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.config import RiskLevel, TradingMode
from src.execution.executor import OrderExecutor
from src.models.domain import Order, OrderSide, OrderStatus, OrderType, Position, Signal
from src.risk_management.risk_manager import RiskManager


def make_signal(
    symbol: str = "BTC-EUR",
    signal_type: str = "BUY",
    price: Decimal = Decimal("50000"),
    strength: float = 0.5,
    strategy: str = "market_making",
) -> Signal:
    from datetime import UTC, datetime

    return Signal(
        symbol=symbol,
        strategy=strategy,
        signal_type=signal_type,
        strength=strength,
        price=price,
        reason="test signal",
        timestamp=datetime.now(UTC),
    )


def make_executor(order_type_strategy: str = "market_making") -> OrderExecutor:
    """Create a paper executor with a moderate risk manager."""
    mock_api = MagicMock()
    rm = RiskManager(RiskLevel.MODERATE, max_order_value=100_000)
    return OrderExecutor(mock_api, rm, TradingMode.PAPER)


@pytest.mark.asyncio
async def test_paper_fill_market_order_populates_commission():
    """MARKET orders in paper mode must have commission = price * qty * 0.0009."""
    executor = make_executor()
    # momentum strategy maps to MARKET order type
    signal = make_signal(
        signal_type="BUY", price=Decimal("50000"), strength=0.7, strategy="momentum"
    )
    order = await executor.execute_signal(signal, Decimal("10000"))
    assert order is not None
    assert order.status == OrderStatus.FILLED
    assert order.order_type == OrderType.MARKET
    expected_fee = order.price * order.filled_quantity * Decimal("0.0009")
    assert order.commission == expected_fee
    assert order.commission > Decimal("0")


@pytest.mark.asyncio
async def test_paper_fill_limit_order_commission_is_zero():
    """LIMIT orders in paper mode must have commission = 0."""
    executor = make_executor()
    # market_making strategy maps to LIMIT order type
    signal = make_signal(
        signal_type="BUY", price=Decimal("50000"), strength=0.5, strategy="market_making"
    )
    order = await executor.execute_signal(signal, Decimal("10000"))
    assert order is not None
    assert order.status == OrderStatus.FILLED
    assert order.order_type == OrderType.LIMIT
    assert order.commission == Decimal("0")


@pytest.mark.asyncio
async def test_opening_order_realized_pnl_is_none():
    """Opening a new position must leave realized_pnl as None on the order."""
    executor = make_executor()
    signal = make_signal(signal_type="BUY", price=Decimal("50000"), strength=0.5)
    order = await executor.execute_signal(signal, Decimal("10000"))
    assert order is not None
    assert order.status == OrderStatus.FILLED
    assert order.realized_pnl is None


@pytest.mark.asyncio
async def test_close_buy_position_deducts_fee_from_realized_pnl():
    """Closing a BUY position must deduct the commission from realized_pnl.

    Uses _execute_paper_order + _update_positions directly to bypass risk
    manager concentration checks (which would reject the close on a small
    portfolio value).
    """
    executor = make_executor()
    entry_price = Decimal("50000")
    close_price = Decimal("51000")
    qty = Decimal("0.1")

    # Inject open position
    executor.positions["BTC-EUR"] = Position(
        symbol="BTC-EUR",
        side=OrderSide.BUY,
        quantity=qty,
        entry_price=entry_price,
        current_price=close_price,
        unrealized_pnl=(close_price - entry_price) * qty,
    )

    # Build and fill a MARKET close order directly (bypasses risk manager)
    close_order = Order(
        symbol="BTC-EUR",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=qty,
        price=close_price,
    )
    await executor._execute_paper_order(close_order)
    await executor._update_positions(close_order)

    # Gross PnL = (51000 - 50000) * 0.1 = 100 EUR
    # Fee = 51000 * 0.1 * 0.0009
    expected_gross = Decimal("100")
    expected_fee = close_price * qty * Decimal("0.0009")
    expected_net = expected_gross - expected_fee

    assert close_order.realized_pnl is not None
    assert close_order.realized_pnl == pytest.approx(expected_net, rel=Decimal("0.001"))


@pytest.mark.asyncio
async def test_close_limit_order_no_fee():
    """Closing a BUY position with a LIMIT order must not deduct any fee."""
    executor = make_executor()
    entry_price = Decimal("50000")
    close_price = Decimal("51000")
    qty = Decimal("0.1")

    executor.positions["BTC-EUR"] = Position(
        symbol="BTC-EUR",
        side=OrderSide.BUY,
        quantity=qty,
        entry_price=entry_price,
        current_price=close_price,
        unrealized_pnl=(close_price - entry_price) * qty,
    )

    close_order = Order(
        symbol="BTC-EUR",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        quantity=qty,
        price=close_price,
    )
    await executor._execute_paper_order(close_order)
    await executor._update_positions(close_order)

    assert close_order.commission == Decimal("0")
    # Gross PnL = 100 EUR, fee = 0 EUR
    assert close_order.realized_pnl == Decimal("100")


@pytest.mark.asyncio
async def test_partial_close_buy_position_deducts_fee_from_realized_pnl():
    """Partially closing a BUY position must deduct the commission from realized_pnl."""
    executor = make_executor()
    entry_price = Decimal("50000")
    close_price = Decimal("51000")
    full_qty = Decimal("0.2")
    close_qty = Decimal("0.1")  # partial close

    executor.positions["BTC-EUR"] = Position(
        symbol="BTC-EUR",
        side=OrderSide.BUY,
        quantity=full_qty,
        entry_price=entry_price,
        current_price=close_price,
        unrealized_pnl=(close_price - entry_price) * full_qty,
    )

    close_order = Order(
        symbol="BTC-EUR",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=close_qty,
        price=close_price,
    )
    await executor._execute_paper_order(close_order)
    await executor._update_positions(close_order)

    # Gross PnL = (51000 - 50000) * 0.1 = 100 EUR
    # Fee = 51000 * 0.1 * 0.0009
    expected_fee = close_price * close_qty * Decimal("0.0009")
    expected_net = (close_price - entry_price) * close_qty - expected_fee

    assert close_order.realized_pnl is not None
    assert close_order.realized_pnl == pytest.approx(expected_net, rel=Decimal("0.001"))
    # Position should still be open with remaining quantity
    assert "BTC-EUR" in executor.positions
    assert executor.positions["BTC-EUR"].quantity == full_qty - close_qty


@pytest.mark.asyncio
async def test_partial_close_short_position_deducts_fee_from_realized_pnl():
    """Partially closing a SELL (short) position must deduct the commission from realized_pnl."""
    executor = make_executor()
    entry_price = Decimal("50000")
    close_price = Decimal("49000")  # price fell — short is profitable
    full_qty = Decimal("0.2")
    close_qty = Decimal("0.1")  # partial close

    executor.positions["BTC-EUR"] = Position(
        symbol="BTC-EUR",
        side=OrderSide.SELL,
        quantity=full_qty,
        entry_price=entry_price,
        current_price=close_price,
        unrealized_pnl=(entry_price - close_price) * full_qty,
    )

    # Closing a short means buying back
    close_order = Order(
        symbol="BTC-EUR",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=close_qty,
        price=close_price,
    )
    await executor._execute_paper_order(close_order)
    await executor._update_positions(close_order)

    # Gross PnL = (50000 - 49000) * 0.1 = 100 EUR
    # Fee = 49000 * 0.1 * 0.0009
    expected_fee = close_price * close_qty * Decimal("0.0009")
    expected_net = (entry_price - close_price) * close_qty - expected_fee

    assert close_order.realized_pnl is not None
    assert close_order.realized_pnl == pytest.approx(expected_net, rel=Decimal("0.001"))
    # Position should still be open with remaining quantity
    assert "BTC-EUR" in executor.positions
    assert executor.positions["BTC-EUR"].quantity == full_qty - close_qty


@pytest.mark.asyncio
async def test_closing_order_has_realized_pnl_set():
    """Any order that closes a position must have realized_pnl set (not None)."""
    executor = make_executor()
    entry_price = Decimal("50000")
    close_price = Decimal("49000")  # closing at a loss
    qty = Decimal("0.1")

    executor.positions["BTC-EUR"] = Position(
        symbol="BTC-EUR",
        side=OrderSide.BUY,
        quantity=qty,
        entry_price=entry_price,
        current_price=close_price,
        unrealized_pnl=(close_price - entry_price) * qty,
    )

    close_order = Order(
        symbol="BTC-EUR",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=qty,
        price=close_price,
    )
    await executor._execute_paper_order(close_order)
    await executor._update_positions(close_order)

    assert close_order.status == OrderStatus.FILLED
    assert close_order.realized_pnl is not None
