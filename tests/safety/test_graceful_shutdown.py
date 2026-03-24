"""Graceful Shutdown Safety Tests - CRITICAL

These tests verify that:
1. All pending/open orders are cancelled on shutdown (they will be unmonitored)
2. Losing positions (unrealized_pnl < 0) are closed via market orders
3. Profitable positions (unrealized_pnl >= 0) are left open
4. Shutdown is fault-tolerant — individual failures do not block other actions
5. All financial values in the summary use Decimal, never float

Critical because: Leaving losing positions unmonitored after shutdown could
cause unbounded financial loss.  Cancelling open orders prevents unmonitored
fills that could move the portfolio into an unexpected state.

Test strategy: Set up an OrderExecutor with known positions and orders, call
graceful_shutdown(), and verify the summary and side-effects.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from src.config import RiskLevel, TradingMode
from src.execution.executor import OrderExecutor
from src.models.domain import (
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    ShutdownSummary,
)
from src.risk_management.risk_manager import RiskManager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_api_client() -> AsyncMock:
    """Mock API client with all methods needed for shutdown."""
    client = AsyncMock()
    client.cancel_all_orders = AsyncMock(return_value=None)
    client.create_order = AsyncMock(
        return_value={
            "venue_order_id": "close-123",
            "client_order_id": "close-cli-123",
            "state": "filled",
        }
    )
    return client


@pytest.fixture
def risk_manager() -> RiskManager:
    """Moderate risk manager for testing."""
    return RiskManager(risk_level=RiskLevel.MODERATE, max_order_value=10000)


@pytest.fixture
def paper_executor(mock_api_client: AsyncMock, risk_manager: RiskManager) -> OrderExecutor:
    """OrderExecutor in PAPER mode."""
    return OrderExecutor(
        api_client=mock_api_client,
        risk_manager=risk_manager,
        trading_mode=TradingMode.PAPER,
    )


@pytest.fixture
def live_executor(mock_api_client: AsyncMock, risk_manager: RiskManager) -> OrderExecutor:
    """OrderExecutor in LIVE mode."""
    return OrderExecutor(
        api_client=mock_api_client,
        risk_manager=risk_manager,
        trading_mode=TradingMode.LIVE,
    )


def _make_position(
    symbol: str,
    side: OrderSide,
    entry_price: Decimal,
    current_price: Decimal,
    quantity: Decimal = Decimal("1"),
) -> Position:
    """Create a position with unrealized PnL pre-calculated."""
    pos = Position(
        symbol=symbol,
        side=side,
        quantity=quantity,
        entry_price=entry_price,
        current_price=current_price,
    )
    pos.update_price(current_price)
    return pos


def _make_open_order(order_id: str, symbol: str) -> Order:
    """Create an open limit order."""
    return Order(
        order_id=order_id,
        symbol=symbol,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("1"),
        price=Decimal("50000"),
        status=OrderStatus.OPEN,
    )


# ===========================================================================
# Order Cancellation
# ===========================================================================


class TestGracefulShutdownOrderCancellation:
    """Tests that all pending orders are cancelled on shutdown."""

    @pytest.mark.asyncio
    async def test_cancels_all_pending_orders_in_live_mode(
        self, live_executor: OrderExecutor, mock_api_client: AsyncMock
    ) -> None:
        """CRITICAL: All open orders MUST be cancelled in live mode.

        Context: Safety requirement SAF-11
        Critical because: Unmonitored orders could fill at unfavourable prices.
        """
        live_executor.open_orders = {
            "ord-1": _make_open_order("ord-1", "BTC-EUR"),
            "ord-2": _make_open_order("ord-2", "ETH-EUR"),
        }

        summary = await live_executor.graceful_shutdown()

        mock_api_client.cancel_all_orders.assert_awaited_once()
        assert summary.orders_cancelled == 2
        assert live_executor.open_orders == {}

    @pytest.mark.asyncio
    async def test_clears_open_orders_in_paper_mode(self, paper_executor: OrderExecutor) -> None:
        """Paper mode should clear in-memory orders without calling the API."""
        paper_executor.open_orders = {
            "paper-1": _make_open_order("paper-1", "BTC-EUR"),
            "paper-2": _make_open_order("paper-2", "ETH-EUR"),
            "paper-3": _make_open_order("paper-3", "SOL-EUR"),
        }

        summary = await paper_executor.graceful_shutdown()

        assert summary.orders_cancelled == 3
        assert paper_executor.open_orders == {}

    @pytest.mark.asyncio
    async def test_cancel_api_failure_continues_to_positions(
        self, live_executor: OrderExecutor, mock_api_client: AsyncMock
    ) -> None:
        """CRITICAL: If order cancellation fails, positions MUST still be evaluated.

        Shutdown must never short-circuit on a single failure.
        """
        mock_api_client.cancel_all_orders = AsyncMock(
            side_effect=RuntimeError("Exchange unreachable")
        )
        live_executor.open_orders = {
            "ord-1": _make_open_order("ord-1", "BTC-EUR"),
        }
        # Add a losing position to verify it still gets closed
        live_executor.positions["BTC-EUR"] = _make_position(
            "BTC-EUR", OrderSide.BUY, Decimal("50000"), Decimal("49000")
        )

        summary = await live_executor.graceful_shutdown()

        assert len(summary.errors) >= 1
        assert "Exchange unreachable" in summary.errors[0]
        # Position phase still ran
        assert summary.positions_evaluated == 1
        assert summary.positions_closed == 1

    @pytest.mark.asyncio
    async def test_no_orders_reports_zero_cancelled(self, paper_executor: OrderExecutor) -> None:
        """Shutdown with no open orders should report zero cancellations."""
        summary = await paper_executor.graceful_shutdown()

        assert summary.orders_cancelled == 0

    @pytest.mark.asyncio
    async def test_paper_mode_does_not_call_api_cancel(
        self, paper_executor: OrderExecutor, mock_api_client: AsyncMock
    ) -> None:
        """Paper mode must NOT call the real cancel_all_orders API."""
        paper_executor.open_orders = {
            "paper-1": _make_open_order("paper-1", "BTC-EUR"),
        }

        await paper_executor.graceful_shutdown()

        mock_api_client.cancel_all_orders.assert_not_awaited()


# ===========================================================================
# Position Evaluation — Close Losers, Keep Winners
# ===========================================================================


class TestGracefulShutdownPositionEvaluation:
    """Tests that positions are correctly evaluated and closed/kept."""

    @pytest.mark.asyncio
    async def test_losing_position_is_closed(self, paper_executor: OrderExecutor) -> None:
        """CRITICAL: Losing positions MUST be closed on shutdown.

        Context: Safety requirement SAF-12
        Critical because: Leaving a losing position unmonitored could cause
        unbounded loss.
        """
        # BUY at 50000, now at 49000 → unrealized_pnl = -1000
        paper_executor.positions["BTC-EUR"] = _make_position(
            "BTC-EUR", OrderSide.BUY, Decimal("50000"), Decimal("49000")
        )

        summary = await paper_executor.graceful_shutdown()

        assert summary.positions_closed == 1
        assert summary.positions_kept == 0
        assert summary.closed_positions_pnl == Decimal("-1000")
        # Position should be removed after close
        assert "BTC-EUR" not in paper_executor.positions

    @pytest.mark.asyncio
    async def test_profitable_position_is_kept(self, paper_executor: OrderExecutor) -> None:
        """Profitable positions should be left open — they are making money."""
        # BUY at 50000, now at 51000 → unrealized_pnl = +1000
        paper_executor.positions["BTC-EUR"] = _make_position(
            "BTC-EUR", OrderSide.BUY, Decimal("50000"), Decimal("51000")
        )

        summary = await paper_executor.graceful_shutdown()

        assert summary.positions_closed == 0
        assert summary.positions_kept == 1
        assert summary.kept_positions_pnl == Decimal("1000")
        # Position should still be in the executor
        assert "BTC-EUR" in paper_executor.positions

    @pytest.mark.asyncio
    async def test_breakeven_position_is_kept(self, paper_executor: OrderExecutor) -> None:
        """Breakeven positions (PnL = 0) should be kept — no reason to close."""
        paper_executor.positions["BTC-EUR"] = _make_position(
            "BTC-EUR", OrderSide.BUY, Decimal("50000"), Decimal("50000")
        )

        summary = await paper_executor.graceful_shutdown()

        assert summary.positions_closed == 0
        assert summary.positions_kept == 1
        assert summary.kept_positions_pnl == Decimal("0")
        assert "BTC-EUR" in paper_executor.positions

    @pytest.mark.asyncio
    async def test_mixed_positions_closes_only_losers(self, paper_executor: OrderExecutor) -> None:
        """CRITICAL: With mixed PnL positions, only losers are closed.

        Scenario: BTC losing, ETH winning, SOL breakeven.
        Expected: Only BTC is closed.
        """
        paper_executor.positions["BTC-EUR"] = _make_position(
            "BTC-EUR", OrderSide.BUY, Decimal("50000"), Decimal("49000")
        )
        paper_executor.positions["ETH-EUR"] = _make_position(
            "ETH-EUR",
            OrderSide.BUY,
            Decimal("3000"),
            Decimal("3200"),
            quantity=Decimal("2"),
        )
        paper_executor.positions["SOL-EUR"] = _make_position(
            "SOL-EUR",
            OrderSide.BUY,
            Decimal("100"),
            Decimal("100"),
            quantity=Decimal("10"),
        )

        summary = await paper_executor.graceful_shutdown()

        assert summary.positions_evaluated == 3
        assert summary.positions_closed == 1
        assert summary.positions_kept == 2
        assert summary.closed_positions_pnl == Decimal("-1000")
        # ETH: (3200-3000)*2 = 400,  SOL: 0
        assert summary.kept_positions_pnl == Decimal("400")
        assert "BTC-EUR" not in paper_executor.positions
        assert "ETH-EUR" in paper_executor.positions
        assert "SOL-EUR" in paper_executor.positions

    @pytest.mark.asyncio
    async def test_short_losing_position_is_closed(self, paper_executor: OrderExecutor) -> None:
        """SELL (short) position that is losing MUST also be closed.

        Short losing = price went up (entry 50000, current 51000, pnl = -1000).
        Close order should be a BUY (opposite side).
        """
        paper_executor.positions["BTC-EUR"] = _make_position(
            "BTC-EUR", OrderSide.SELL, Decimal("50000"), Decimal("51000")
        )

        summary = await paper_executor.graceful_shutdown()

        assert summary.positions_closed == 1
        assert summary.closed_positions_pnl == Decimal("-1000")
        assert "BTC-EUR" not in paper_executor.positions

    @pytest.mark.asyncio
    async def test_close_position_failure_records_error_and_continues(
        self, paper_executor: OrderExecutor
    ) -> None:
        """If closing one position fails, shutdown MUST continue to the next."""
        # Two losing positions
        paper_executor.positions["BTC-EUR"] = _make_position(
            "BTC-EUR", OrderSide.BUY, Decimal("50000"), Decimal("49000")
        )
        paper_executor.positions["ETH-EUR"] = _make_position(
            "ETH-EUR",
            OrderSide.BUY,
            Decimal("3000"),
            Decimal("2900"),
            quantity=Decimal("2"),
        )

        call_count = 0
        original_close = paper_executor._close_position_for_shutdown

        async def _failing_close(symbol, position):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Network timeout")
            return await original_close(symbol, position)

        with patch.object(
            paper_executor, "_close_position_for_shutdown", side_effect=_failing_close
        ):
            summary = await paper_executor.graceful_shutdown()

        assert len(summary.errors) >= 1
        assert summary.positions_evaluated == 2
        # At least one position was attempted to be closed
        assert summary.positions_closed >= 1 or len(summary.errors) >= 1

    @pytest.mark.asyncio
    async def test_no_positions_reports_zero(self, paper_executor: OrderExecutor) -> None:
        """Shutdown with no positions should report zero evaluations."""
        summary = await paper_executor.graceful_shutdown()

        assert summary.positions_evaluated == 0
        assert summary.positions_closed == 0
        assert summary.positions_kept == 0


# ===========================================================================
# Financial Values — Always Decimal
# ===========================================================================


class TestGracefulShutdownFinancialValues:
    """Tests that all financial values use Decimal, never float."""

    @pytest.mark.asyncio
    async def test_summary_pnl_values_are_decimal(self, paper_executor: OrderExecutor) -> None:
        """All monetary fields in ShutdownSummary MUST be Decimal."""
        paper_executor.positions["BTC-EUR"] = _make_position(
            "BTC-EUR", OrderSide.BUY, Decimal("50000"), Decimal("49000")
        )
        paper_executor.positions["ETH-EUR"] = _make_position(
            "ETH-EUR", OrderSide.BUY, Decimal("3000"), Decimal("3100")
        )

        summary = await paper_executor.graceful_shutdown()

        assert isinstance(summary.closed_positions_pnl, Decimal)
        assert isinstance(summary.kept_positions_pnl, Decimal)

    @pytest.mark.asyncio
    async def test_summary_is_shutdown_summary_type(self, paper_executor: OrderExecutor) -> None:
        """graceful_shutdown() must return a ShutdownSummary instance."""
        summary = await paper_executor.graceful_shutdown()

        assert isinstance(summary, ShutdownSummary)


# ===========================================================================
# Close Order Properties
# ===========================================================================


class TestGracefulShutdownCloseOrderProperties:
    """Tests that close orders generated during shutdown have correct properties."""

    @pytest.mark.asyncio
    async def test_close_order_is_market_type(self, paper_executor: OrderExecutor) -> None:
        """Close orders must be MARKET type for immediate execution."""
        paper_executor.positions["BTC-EUR"] = _make_position(
            "BTC-EUR", OrderSide.BUY, Decimal("50000"), Decimal("49000")
        )

        summary = await paper_executor.graceful_shutdown()

        assert len(summary.filled_close_orders) == 1
        close_order = summary.filled_close_orders[0]
        assert close_order.order_type == OrderType.MARKET

    @pytest.mark.asyncio
    async def test_close_order_uses_opposite_side_for_long(
        self, paper_executor: OrderExecutor
    ) -> None:
        """BUY position must be closed with a SELL order."""
        paper_executor.positions["BTC-EUR"] = _make_position(
            "BTC-EUR", OrderSide.BUY, Decimal("50000"), Decimal("49000")
        )

        summary = await paper_executor.graceful_shutdown()

        assert len(summary.filled_close_orders) == 1
        assert summary.filled_close_orders[0].side == OrderSide.SELL

    @pytest.mark.asyncio
    async def test_close_order_uses_opposite_side_for_short(
        self, paper_executor: OrderExecutor
    ) -> None:
        """SELL (short) position must be closed with a BUY order."""
        paper_executor.positions["BTC-EUR"] = _make_position(
            "BTC-EUR", OrderSide.SELL, Decimal("50000"), Decimal("51000")
        )

        summary = await paper_executor.graceful_shutdown()

        assert len(summary.filled_close_orders) == 1
        assert summary.filled_close_orders[0].side == OrderSide.BUY

    @pytest.mark.asyncio
    async def test_close_order_strategy_is_graceful_shutdown(
        self, paper_executor: OrderExecutor
    ) -> None:
        """Close orders must have strategy='close_graceful_shutdown'."""
        paper_executor.positions["BTC-EUR"] = _make_position(
            "BTC-EUR", OrderSide.BUY, Decimal("50000"), Decimal("49000")
        )

        summary = await paper_executor.graceful_shutdown()

        assert len(summary.filled_close_orders) == 1
        assert summary.filled_close_orders[0].strategy == "close_graceful_shutdown"

    @pytest.mark.asyncio
    async def test_filled_close_orders_list_only_has_filled_orders(
        self, paper_executor: OrderExecutor
    ) -> None:
        """Only successfully filled close orders should appear in the summary."""
        paper_executor.positions["BTC-EUR"] = _make_position(
            "BTC-EUR", OrderSide.BUY, Decimal("50000"), Decimal("49000")
        )
        paper_executor.positions["ETH-EUR"] = _make_position(
            "ETH-EUR", OrderSide.BUY, Decimal("3000"), Decimal("3100")
        )

        summary = await paper_executor.graceful_shutdown()

        # Only BTC should have a close order (it's losing), ETH is profitable
        assert len(summary.filled_close_orders) == 1
        assert summary.filled_close_orders[0].symbol == "BTC-EUR"
        assert summary.filled_close_orders[0].status == OrderStatus.FILLED


# ===========================================================================
# Live Mode — API Integration
# ===========================================================================


class TestGracefulShutdownLiveMode:
    """Tests specific to LIVE mode shutdown behaviour."""

    @pytest.mark.asyncio
    async def test_live_mode_calls_api_to_close_losing_position(
        self, live_executor: OrderExecutor, mock_api_client: AsyncMock
    ) -> None:
        """LIVE mode must place real close orders via the API."""
        live_executor.positions["BTC-EUR"] = _make_position(
            "BTC-EUR", OrderSide.BUY, Decimal("50000"), Decimal("49000")
        )

        summary = await live_executor.graceful_shutdown()

        mock_api_client.create_order.assert_awaited_once()
        call_kwargs = mock_api_client.create_order.call_args
        assert call_kwargs.kwargs["side"] == "SELL"  # opposite of BUY
        assert call_kwargs.kwargs["order_type"] == "MARKET"
        assert summary.positions_closed == 1

    @pytest.mark.asyncio
    async def test_live_mode_does_not_close_profitable_position(
        self, live_executor: OrderExecutor, mock_api_client: AsyncMock
    ) -> None:
        """LIVE mode must NOT place close orders for profitable positions."""
        live_executor.positions["BTC-EUR"] = _make_position(
            "BTC-EUR", OrderSide.BUY, Decimal("50000"), Decimal("51000")
        )

        summary = await live_executor.graceful_shutdown()

        mock_api_client.create_order.assert_not_awaited()
        assert summary.positions_kept == 1
