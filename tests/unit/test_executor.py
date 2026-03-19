"""Unit tests for OrderExecutor."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

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
) -> Signal:
    from datetime import UTC, datetime

    return Signal(
        symbol=symbol,
        strategy="Momentum",
        signal_type=signal_type,
        strength=strength,
        price=price,
        reason="test signal",
        timestamp=datetime.now(UTC),
    )


def make_position(
    symbol: str = "BTC-EUR",
    side: OrderSide = OrderSide.BUY,
    quantity: Decimal = Decimal("0.1"),
    entry_price: Decimal = Decimal("50000"),
) -> Position:
    return Position(
        symbol=symbol,
        side=side,
        quantity=quantity,
        entry_price=entry_price,
        current_price=entry_price,
        unrealized_pnl=Decimal("0"),
    )


@pytest.fixture
def mock_api():
    api = MagicMock()
    api.create_order = AsyncMock(
        return_value={"orderId": "live-123", "status": "OPEN", "filledQty": 0}
    )
    return api


@pytest.fixture
def moderate_rm():
    return RiskManager(RiskLevel.MODERATE, max_order_value_usd=Decimal("100000"))


@pytest.fixture
def paper_executor(mock_api, moderate_rm):
    return OrderExecutor(mock_api, moderate_rm, TradingMode.PAPER)


@pytest.fixture
def live_executor(mock_api, moderate_rm):
    return OrderExecutor(mock_api, moderate_rm, TradingMode.LIVE)


class TestOrderExecutorInit:
    def test_initial_positions_empty(self, paper_executor):
        assert paper_executor.positions == {}

    def test_initial_open_orders_empty(self, paper_executor):
        assert paper_executor.open_orders == {}

    def test_trading_mode_set(self, paper_executor):
        assert paper_executor.trading_mode == TradingMode.PAPER


class TestPaperOrderExecution:
    @pytest.mark.asyncio
    async def test_buy_signal_fills_paper_order(self, paper_executor):
        signal = make_signal(signal_type="BUY", strength=0.5)
        order = await paper_executor.execute_signal(signal, Decimal("10000"))
        assert order is not None
        assert order.status == OrderStatus.FILLED
        assert order.order_id.startswith("paper_")

    @pytest.mark.asyncio
    async def test_buy_creates_new_position(self, paper_executor):
        signal = make_signal(signal_type="BUY", strength=0.5)
        await paper_executor.execute_signal(signal, Decimal("10000"))
        assert "BTC-EUR" in paper_executor.positions
        pos = paper_executor.positions["BTC-EUR"]
        assert pos.side == OrderSide.BUY

    @pytest.mark.asyncio
    async def test_buy_position_has_stop_and_take_profit(self, paper_executor):
        await paper_executor.execute_signal(make_signal("BTC-EUR", "BUY"), Decimal("10000"))
        pos = paper_executor.positions["BTC-EUR"]
        assert pos.stop_loss is not None
        assert pos.take_profit is not None

    @pytest.mark.asyncio
    async def test_sell_signal_paper_sets_sell_side(self, paper_executor):
        signal = make_signal(signal_type="SELL", strength=0.5)
        order = await paper_executor.execute_signal(signal, Decimal("10000"))
        assert order.side == OrderSide.SELL

    @pytest.mark.asyncio
    async def test_sanity_check_rejects_order_exceeding_limit(self, mock_api):
        tiny_rm = RiskManager(RiskLevel.MODERATE, max_order_value_usd=Decimal("1"))
        executor = OrderExecutor(mock_api, tiny_rm, TradingMode.PAPER)
        signal = make_signal(strength=1.0)
        order = await executor.execute_signal(signal, Decimal("1000000"))
        assert order.status == OrderStatus.REJECTED

    @pytest.mark.asyncio
    async def test_risk_manager_rejects_too_many_positions(self, mock_api, moderate_rm):
        executor = OrderExecutor(mock_api, moderate_rm, TradingMode.PAPER)
        for _i, sym in enumerate(["A-EUR", "B-EUR", "C-EUR", "D-EUR", "E-EUR"]):
            executor.positions[sym] = make_position(symbol=sym)
        signal = make_signal(symbol="NEW-EUR")
        order = await executor.execute_signal(signal, Decimal("10000"))
        assert order.status == OrderStatus.REJECTED


class TestLiveOrderExecution:
    @pytest.mark.asyncio
    async def test_live_order_calls_api(self, live_executor, mock_api):
        signal = make_signal(strength=0.5)
        order = await live_executor.execute_signal(signal, Decimal("10000"))
        assert mock_api.create_order.called
        assert order.order_id == "live-123"

    @pytest.mark.asyncio
    async def test_live_order_api_failure_rejects_order(self, live_executor, mock_api):
        mock_api.create_order = AsyncMock(side_effect=Exception("API down"))
        signal = make_signal(strength=0.5)
        order = await live_executor.execute_signal(signal, Decimal("10000"))
        assert order.status == OrderStatus.REJECTED

    @pytest.mark.asyncio
    async def test_live_filled_order_updates_open_orders(self, live_executor, mock_api):
        mock_api.create_order = AsyncMock(
            return_value={"orderId": "live-456", "status": "OPEN", "filledQty": 0}
        )
        await live_executor.execute_signal(make_signal(strength=0.5), Decimal("10000"))
        assert "live-456" in live_executor.open_orders


class TestPositionUpdate:
    @pytest.mark.asyncio
    async def test_add_to_existing_same_side_position(self, paper_executor):
        # Create position via trade
        signal = make_signal(signal_type="BUY", strength=0.5)
        await paper_executor.execute_signal(signal, Decimal("10000"))
        initial_qty = paper_executor.positions["BTC-EUR"].quantity

        # Add more
        await paper_executor.execute_signal(signal, Decimal("10000"))
        assert paper_executor.positions["BTC-EUR"].quantity > initial_qty

    @pytest.mark.asyncio
    async def test_close_position_on_full_sell(self, paper_executor):
        # Manually inject position and close it with a fill order
        paper_executor.positions["BTC-EUR"] = make_position(
            quantity=Decimal("0.1"), entry_price=Decimal("50000")
        )
        paper_executor.positions["BTC-EUR"].unrealized_pnl = Decimal("500")

        close_order = Order(
            symbol="BTC-EUR",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.1"),
            price=Decimal("55000"),
            filled_quantity=Decimal("0.1"),
            status=OrderStatus.FILLED,
        )
        await paper_executor._update_positions(close_order)
        assert "BTC-EUR" not in paper_executor.positions

    @pytest.mark.asyncio
    async def test_reduce_position_on_partial_sell(self, paper_executor):
        paper_executor.positions["BTC-EUR"] = make_position(quantity=Decimal("1.0"))

        partial_sell = Order(
            symbol="BTC-EUR",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.3"),
            price=Decimal("50000"),
            filled_quantity=Decimal("0.3"),
            status=OrderStatus.FILLED,
        )
        await paper_executor._update_positions(partial_sell)
        assert "BTC-EUR" in paper_executor.positions
        assert paper_executor.positions["BTC-EUR"].quantity == Decimal("0.7")

    @pytest.mark.asyncio
    async def test_update_market_prices_no_position_is_noop(self, paper_executor):
        # Should not raise
        await paper_executor.update_market_prices("BTC-EUR", Decimal("50000"))

    @pytest.mark.asyncio
    async def test_update_market_prices_updates_unrealized_pnl(self, paper_executor):
        paper_executor.positions["BTC-EUR"] = make_position(
            quantity=Decimal("1"), entry_price=Decimal("50000")
        )
        await paper_executor.update_market_prices("BTC-EUR", Decimal("52000"))
        assert paper_executor.positions["BTC-EUR"].unrealized_pnl == Decimal("2000")

    @pytest.mark.asyncio
    async def test_stop_loss_closes_position(self, paper_executor):
        pos = make_position(quantity=Decimal("0.1"), entry_price=Decimal("50000"))
        pos.stop_loss = Decimal("49000")
        paper_executor.positions["BTC-EUR"] = pos

        # Price drops below stop loss
        await paper_executor.update_market_prices("BTC-EUR", Decimal("48000"))
        assert "BTC-EUR" not in paper_executor.positions

    @pytest.mark.asyncio
    async def test_take_profit_closes_position(self, paper_executor):
        pos = make_position(quantity=Decimal("0.1"), entry_price=Decimal("50000"))
        pos.take_profit = Decimal("52000")
        paper_executor.positions["BTC-EUR"] = pos

        await paper_executor.update_market_prices("BTC-EUR", Decimal("53000"))
        assert "BTC-EUR" not in paper_executor.positions


class TestPortfolioHelpers:
    @pytest.mark.asyncio
    async def test_get_portfolio_value_no_positions(self, paper_executor):
        cash = Decimal("10000")
        value = await paper_executor.get_portfolio_value(cash)
        assert value == cash

    @pytest.mark.asyncio
    async def test_get_portfolio_value_with_position(self, paper_executor):
        paper_executor.positions["BTC-EUR"] = make_position(
            quantity=Decimal("1"), entry_price=Decimal("50000")
        )
        paper_executor.positions["BTC-EUR"].current_price = Decimal("52000")
        value = await paper_executor.get_portfolio_value(Decimal("10000"))
        assert value == Decimal("62000")

    def test_get_positions_returns_list(self, paper_executor):
        paper_executor.positions["BTC-EUR"] = make_position()
        positions = paper_executor.get_positions()
        assert len(positions) == 1

    def test_get_positions_empty(self, paper_executor):
        assert paper_executor.get_positions() == []

    def test_get_position_existing(self, paper_executor):
        pos = make_position()
        paper_executor.positions["BTC-EUR"] = pos
        assert paper_executor.get_position("BTC-EUR") is pos

    def test_get_position_nonexistent(self, paper_executor):
        assert paper_executor.get_position("UNKNOWN") is None
