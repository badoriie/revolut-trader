"""Unit tests for OrderExecutor."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

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
        strategy="market_making",
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
        return_value={"venue_order_id": "live-123", "client_order_id": "c-123", "state": "new"}
    )
    return api


@pytest.fixture
def moderate_rm():
    return RiskManager(RiskLevel.MODERATE, max_order_value=100000)


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
        tiny_rm = RiskManager(RiskLevel.MODERATE, max_order_value=1)
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
        # API "new" state (working order) must map to OrderStatus.OPEN
        assert order.status == OrderStatus.OPEN

    @pytest.mark.asyncio
    async def test_live_order_api_failure_rejects_order(self, live_executor, mock_api):
        mock_api.create_order = AsyncMock(side_effect=Exception("API down"))
        signal = make_signal(strength=0.5)
        order = await live_executor.execute_signal(signal, Decimal("10000"))
        assert order.status == OrderStatus.REJECTED

    @pytest.mark.asyncio
    async def test_live_filled_order_updates_open_orders(self, live_executor, mock_api):
        mock_api.create_order = AsyncMock(
            return_value={"venue_order_id": "live-456", "client_order_id": "c-456", "state": "new"}
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


class TestSignalValidation:
    @pytest.mark.asyncio
    async def test_hold_signal_returns_none(self, paper_executor):
        """HOLD signals must not produce any order."""
        signal = make_signal(signal_type="HOLD")
        result = await paper_executor.execute_signal(signal, Decimal("10000"))
        assert result is None

    @pytest.mark.asyncio
    async def test_hold_signal_creates_no_position(self, paper_executor):
        signal = make_signal(signal_type="HOLD")
        await paper_executor.execute_signal(signal, Decimal("10000"))
        assert paper_executor.positions == {}


class TestCloseOrderOnStopTakeProfit:
    @pytest.mark.asyncio
    async def test_stop_loss_executes_close_order_not_just_deletes(self, paper_executor):
        """When stop loss triggers, a real closing order must be placed, not just
        the position deleted from the dict."""
        pos = make_position(quantity=Decimal("0.1"), entry_price=Decimal("50000"))
        pos.stop_loss = Decimal("49000")
        paper_executor.positions["BTC-EUR"] = pos

        with patch.object(
            paper_executor, "_execute_paper_order", wraps=paper_executor._execute_paper_order
        ) as mock_execute:
            await paper_executor.update_market_prices("BTC-EUR", Decimal("48000"))
            mock_execute.assert_called_once()
            close_order = mock_execute.call_args[0][0]
            assert close_order.side == OrderSide.SELL
            assert close_order.symbol == "BTC-EUR"

    @pytest.mark.asyncio
    async def test_take_profit_executes_close_order(self, paper_executor):
        pos = make_position(quantity=Decimal("0.1"), entry_price=Decimal("50000"))
        pos.take_profit = Decimal("52000")
        paper_executor.positions["BTC-EUR"] = pos

        with patch.object(
            paper_executor, "_execute_paper_order", wraps=paper_executor._execute_paper_order
        ) as mock_execute:
            await paper_executor.update_market_prices("BTC-EUR", Decimal("53000"))
            mock_execute.assert_called_once()
            close_order = mock_execute.call_args[0][0]
            assert close_order.side == OrderSide.SELL

    @pytest.mark.asyncio
    async def test_stop_loss_close_order_uses_market_type(self, paper_executor):
        """Close orders triggered by SL/TP must be market orders for immediate fill."""
        pos = make_position(quantity=Decimal("0.1"), entry_price=Decimal("50000"))
        pos.stop_loss = Decimal("49000")
        paper_executor.positions["BTC-EUR"] = pos

        with patch.object(
            paper_executor, "_execute_paper_order", wraps=paper_executor._execute_paper_order
        ) as mock_execute:
            await paper_executor.update_market_prices("BTC-EUR", Decimal("48000"))
            close_order = mock_execute.call_args[0][0]
            assert close_order.order_type == OrderType.MARKET

    @pytest.mark.asyncio
    async def test_update_market_prices_returns_close_order_on_sl(self, paper_executor):
        """update_market_prices must return the filled close Order when SL fires
        so the caller (bot._process_symbol) can update cash balance and persist the trade."""
        pos = make_position(quantity=Decimal("0.1"), entry_price=Decimal("50000"))
        pos.stop_loss = Decimal("49000")
        paper_executor.positions["BTC-EUR"] = pos

        close_order = await paper_executor.update_market_prices("BTC-EUR", Decimal("48000"))

        assert close_order is not None
        assert close_order.status == OrderStatus.FILLED
        assert close_order.side == OrderSide.SELL
        assert close_order.symbol == "BTC-EUR"

    @pytest.mark.asyncio
    async def test_update_market_prices_returns_close_order_on_tp(self, paper_executor):
        """update_market_prices must return the filled close Order when TP fires."""
        pos = make_position(quantity=Decimal("0.1"), entry_price=Decimal("50000"))
        pos.take_profit = Decimal("52000")
        paper_executor.positions["BTC-EUR"] = pos

        close_order = await paper_executor.update_market_prices("BTC-EUR", Decimal("53000"))

        assert close_order is not None
        assert close_order.status == OrderStatus.FILLED
        assert close_order.side == OrderSide.SELL

    @pytest.mark.asyncio
    async def test_update_market_prices_returns_none_when_no_sl_tp_hit(self, paper_executor):
        """update_market_prices returns None when price does not hit SL or TP."""
        pos = make_position(quantity=Decimal("0.1"), entry_price=Decimal("50000"))
        pos.stop_loss = Decimal("49000")
        pos.take_profit = Decimal("52000")
        paper_executor.positions["BTC-EUR"] = pos

        # Price is between SL and TP
        result = await paper_executor.update_market_prices("BTC-EUR", Decimal("50500"))
        assert result is None
        assert "BTC-EUR" in paper_executor.positions  # Position still open

    @pytest.mark.asyncio
    async def test_update_market_prices_returns_none_when_no_position(self, paper_executor):
        """update_market_prices returns None when there is no position to check."""
        result = await paper_executor.update_market_prices("BTC-EUR", Decimal("50000"))
        assert result is None

    @pytest.mark.asyncio
    async def test_reduce_buy_position_positive_pnl(self, paper_executor):
        """Selling part of a BUY position above entry price yields positive PnL."""
        paper_executor.positions["BTC-EUR"] = make_position(
            quantity=Decimal("1.0"), entry_price=Decimal("50000")
        )
        partial_sell = Order(
            symbol="BTC-EUR",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.5"),
            price=Decimal("52000"),
            filled_quantity=Decimal("0.5"),
            status=OrderStatus.FILLED,
        )
        await paper_executor._update_positions(partial_sell)
        assert paper_executor.positions["BTC-EUR"].realized_pnl == Decimal("1000")

    @pytest.mark.asyncio
    async def test_reduce_sell_position_positive_pnl(self, paper_executor):
        """Buying back part of a SELL (short) position below entry price yields positive PnL."""
        paper_executor.positions["BTC-EUR"] = make_position(
            side=OrderSide.SELL,
            quantity=Decimal("1.0"),
            entry_price=Decimal("50000"),
        )
        partial_buy = Order(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.5"),
            price=Decimal("48000"),  # bought back cheaper → profit for short
            filled_quantity=Decimal("0.5"),
            status=OrderStatus.FILLED,
        )
        await paper_executor._update_positions(partial_buy)
        assert paper_executor.positions["BTC-EUR"].realized_pnl == Decimal("1000")

    @pytest.mark.asyncio
    async def test_reduce_sell_position_negative_pnl_on_loss(self, paper_executor):
        """Buying back a short above entry price yields negative PnL."""
        paper_executor.positions["BTC-EUR"] = make_position(
            side=OrderSide.SELL,
            quantity=Decimal("1.0"),
            entry_price=Decimal("50000"),
        )
        partial_buy = Order(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.5"),
            price=Decimal("52000"),  # bought back more expensive → loss for short
            filled_quantity=Decimal("0.5"),
            status=OrderStatus.FILLED,
        )
        await paper_executor._update_positions(partial_buy)
        assert paper_executor.positions["BTC-EUR"].realized_pnl == Decimal("-1000")


class TestLiveOrderResponseMapping:
    @pytest.mark.asyncio
    async def test_live_order_reads_venue_order_id(self, live_executor, mock_api):
        """Executor must read venue_order_id from API response, not orderId."""
        mock_api.create_order = AsyncMock(
            return_value={
                "venue_order_id": "venue-789",
                "client_order_id": "c-789",
                "state": "new",
            }
        )
        signal = make_signal(strength=0.5)
        order = await live_executor.execute_signal(signal, Decimal("10000"))
        assert order.order_id == "venue-789"

    @pytest.mark.asyncio
    async def test_live_order_maps_new_state(self, live_executor, mock_api):
        """API 'new' state (working order) maps to OrderStatus.OPEN."""
        mock_api.create_order = AsyncMock(
            return_value={"venue_order_id": "v1", "client_order_id": "c1", "state": "new"}
        )
        order = await live_executor.execute_signal(make_signal(strength=0.5), Decimal("10000"))
        assert order.status == OrderStatus.OPEN

    @pytest.mark.asyncio
    async def test_live_order_maps_pending_new_state(self, live_executor, mock_api):
        """API 'pending_new' state maps to OrderStatus.PENDING."""
        mock_api.create_order = AsyncMock(
            return_value={"venue_order_id": "v1", "client_order_id": "c1", "state": "pending_new"}
        )
        order = await live_executor.execute_signal(make_signal(strength=0.5), Decimal("10000"))
        assert order.status == OrderStatus.PENDING

    @pytest.mark.asyncio
    async def test_live_order_maps_filled_state(self, live_executor, mock_api):
        """API 'filled' state maps to OrderStatus.FILLED."""
        mock_api.create_order = AsyncMock(
            return_value={"venue_order_id": "v2", "client_order_id": "c2", "state": "filled"}
        )
        order = await live_executor.execute_signal(make_signal(strength=0.5), Decimal("10000"))
        assert order.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_live_order_maps_replaced_state(self, live_executor, mock_api):
        """API 'replaced' state maps to OrderStatus.REPLACED."""
        mock_api.create_order = AsyncMock(
            return_value={"venue_order_id": "v2", "client_order_id": "c2", "state": "replaced"}
        )
        order = await live_executor.execute_signal(make_signal(strength=0.5), Decimal("10000"))
        assert order.status == OrderStatus.REPLACED

    @pytest.mark.asyncio
    async def test_live_order_unknown_state_defaults_to_pending(self, live_executor, mock_api):
        """Unknown API state defaults to PENDING rather than crashing."""
        mock_api.create_order = AsyncMock(
            return_value={
                "venue_order_id": "v3",
                "client_order_id": "c3",
                "state": "unknown_future_state",
            }
        )
        order = await live_executor.execute_signal(make_signal(strength=0.5), Decimal("10000"))
        assert order.status == OrderStatus.PENDING


def _make_signal_for_strategy(
    strategy: str,
    signal_type: str = "BUY",
    strength: float = 0.8,
    price: Decimal = Decimal("50000"),
) -> Signal:
    """Create a Signal with an explicit lowercase strategy name for threshold/order-type tests."""
    from datetime import UTC, datetime

    return Signal(
        symbol="BTC-EUR",
        strategy=strategy,
        signal_type=signal_type,
        strength=strength,
        price=price,
        reason="test signal",
        timestamp=datetime.now(UTC),
    )


class TestSignalStrengthFilter:
    """Signal strength filtering prevents weak signals from reaching the exchange."""

    @pytest.mark.asyncio
    async def test_breakout_below_threshold_returns_none(self, paper_executor):
        signal = _make_signal_for_strategy("breakout", strength=0.5)
        assert await paper_executor.execute_signal(signal, Decimal("10000")) is None

    @pytest.mark.asyncio
    async def test_breakout_at_threshold_executes(self, paper_executor):
        signal = _make_signal_for_strategy("breakout", strength=0.7)
        result = await paper_executor.execute_signal(signal, Decimal("10000"))
        assert result is not None
        assert result.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_momentum_below_threshold_returns_none(self, paper_executor):
        signal = _make_signal_for_strategy("momentum", strength=0.5)
        assert await paper_executor.execute_signal(signal, Decimal("10000")) is None

    @pytest.mark.asyncio
    async def test_momentum_above_threshold_executes(self, paper_executor):
        signal = _make_signal_for_strategy("momentum", strength=0.7)
        result = await paper_executor.execute_signal(signal, Decimal("10000"))
        assert result is not None
        assert result.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_market_making_accepts_low_strength(self, paper_executor):
        # market_making threshold is 0.3 — deliberately the lowest
        signal = _make_signal_for_strategy("market_making", strength=0.35)
        result = await paper_executor.execute_signal(signal, Decimal("10000"))
        assert result is not None
        assert result.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_market_making_below_threshold_filtered(self, paper_executor):
        signal = _make_signal_for_strategy("market_making", strength=0.25)
        assert await paper_executor.execute_signal(signal, Decimal("10000")) is None

    @pytest.mark.asyncio
    async def test_unknown_strategy_uses_default_threshold_filters(self, paper_executor):
        # default = 0.5; strength 0.4 should be filtered
        signal = _make_signal_for_strategy("unknown_strategy", strength=0.4)
        assert await paper_executor.execute_signal(signal, Decimal("10000")) is None

    @pytest.mark.asyncio
    async def test_unknown_strategy_at_default_threshold_executes(self, paper_executor):
        # default = 0.5; strength 0.5 is not strictly less than threshold → executes
        signal = _make_signal_for_strategy("unknown_strategy", strength=0.5)
        result = await paper_executor.execute_signal(signal, Decimal("10000"))
        assert result is not None
        assert result.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_display_name_market_making_executes_above_its_threshold(self, paper_executor):
        """'Market Making' (display name) normalises to 'market_making' with threshold 0.3."""
        signal = _make_signal_for_strategy("Market Making", strength=0.35)
        result = await paper_executor.execute_signal(signal, Decimal("10000"))
        assert result is not None
        assert result.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_display_name_momentum_filtered_below_its_threshold(self, paper_executor):
        """'Momentum' normalises to 'momentum' with threshold 0.6; strength 0.5 must be filtered."""
        signal = _make_signal_for_strategy("Momentum", strength=0.5)
        assert await paper_executor.execute_signal(signal, Decimal("10000")) is None

    @pytest.mark.asyncio
    async def test_display_name_multi_strategy_normalises_hyphen(self, paper_executor):
        """'Multi-Strategy' normalises to 'multi_strategy' (hyphen → underscore)."""
        # multi_strategy threshold is 0.55; 0.5 < 0.55 → filtered
        signal = _make_signal_for_strategy("Multi-Strategy", strength=0.5)
        assert await paper_executor.execute_signal(signal, Decimal("10000")) is None


class TestStrategyOrderType:
    """Each strategy maps to the order type that best matches its execution needs."""

    @pytest.mark.asyncio
    async def test_momentum_uses_market_order(self, paper_executor):
        signal = _make_signal_for_strategy("momentum", strength=0.8)
        result = await paper_executor.execute_signal(signal, Decimal("10000"))
        assert result is not None
        assert result.order_type == OrderType.MARKET

    @pytest.mark.asyncio
    async def test_breakout_uses_market_order(self, paper_executor):
        signal = _make_signal_for_strategy("breakout", strength=0.8)
        result = await paper_executor.execute_signal(signal, Decimal("10000"))
        assert result is not None
        assert result.order_type == OrderType.MARKET

    @pytest.mark.asyncio
    async def test_market_making_uses_limit_order(self, paper_executor):
        signal = _make_signal_for_strategy("market_making", strength=0.8)
        result = await paper_executor.execute_signal(signal, Decimal("10000"))
        assert result is not None
        assert result.order_type == OrderType.LIMIT

    @pytest.mark.asyncio
    async def test_mean_reversion_uses_limit_order(self, paper_executor):
        signal = _make_signal_for_strategy("mean_reversion", strength=0.8)
        result = await paper_executor.execute_signal(signal, Decimal("10000"))
        assert result is not None
        assert result.order_type == OrderType.LIMIT

    @pytest.mark.asyncio
    async def test_range_reversion_uses_limit_order(self, paper_executor):
        signal = _make_signal_for_strategy("range_reversion", strength=0.8)
        result = await paper_executor.execute_signal(signal, Decimal("10000"))
        assert result is not None
        assert result.order_type == OrderType.LIMIT

    @pytest.mark.asyncio
    async def test_unknown_strategy_defaults_to_limit_order(self, paper_executor):
        signal = _make_signal_for_strategy("unknown_strategy", strength=0.8)
        result = await paper_executor.execute_signal(signal, Decimal("10000"))
        assert result is not None
        assert result.order_type == OrderType.LIMIT

    @pytest.mark.asyncio
    async def test_display_name_momentum_uses_market_order(self, paper_executor):
        """'Momentum' display name must normalise to 'momentum' and select MARKET order."""
        signal = _make_signal_for_strategy("Momentum", strength=0.8)
        result = await paper_executor.execute_signal(signal, Decimal("10000"))
        assert result is not None
        assert result.order_type == OrderType.MARKET

    @pytest.mark.asyncio
    async def test_display_name_breakout_uses_market_order(self, paper_executor):
        """'Breakout' display name must normalise to 'breakout' and select MARKET order."""
        signal = _make_signal_for_strategy("Breakout", strength=0.8)
        result = await paper_executor.execute_signal(signal, Decimal("10000"))
        assert result is not None
        assert result.order_type == OrderType.MARKET

    @pytest.mark.asyncio
    async def test_display_name_mean_reversion_uses_limit_order(self, paper_executor):
        """'Mean Reversion' display name must normalise and select LIMIT order."""
        signal = _make_signal_for_strategy("Mean Reversion", strength=0.8)
        result = await paper_executor.execute_signal(signal, Decimal("10000"))
        assert result is not None
        assert result.order_type == OrderType.LIMIT
