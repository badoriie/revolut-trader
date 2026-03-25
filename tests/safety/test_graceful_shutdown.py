"""Graceful Shutdown Safety Tests - CRITICAL

These tests verify that:
1. All pending/open orders are cancelled on shutdown (they will be unmonitored)
2. Losing positions (unrealized_pnl < 0) are closed immediately via market orders
3. Profitable/breakeven positions are closed via trailing stop (or immediately if no config)
4. After shutdown completes, executor.positions is ALWAYS empty (zero open positions)
5. Shutdown is fault-tolerant — individual failures do not block other actions
6. All financial values in the summary use Decimal, never float

Critical because: The user's contract is EUR → trade → EUR.  Any open position
after shutdown means the user's capital is locked in crypto, not EUR.  Leaving
losing positions unmonitored would cause unbounded financial loss.
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

_DEFAULT_TICKER = {"last": Decimal("50000"), "bid": Decimal("49950"), "ask": Decimal("50050")}


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
    # get_ticker used by _wait_and_close_profitable — returns current price
    client.get_ticker = AsyncMock(return_value=_DEFAULT_TICKER)
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


# Convenience — avoids repeating trailing stop args in every test.
# max_wait_seconds=0 means the trailing-stop loop times out immediately (elapsed >= 0
# is always True), so tests that don't care about polling duration finish without any
# real wall-clock wait while still exercising the full shutdown code path.
_DEFAULT_SHUTDOWN_ARGS = {"trailing_stop_pct": Decimal("0.5"), "max_wait_seconds": 0}


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

        summary = await live_executor.graceful_shutdown(**_DEFAULT_SHUTDOWN_ARGS)

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

        summary = await paper_executor.graceful_shutdown(**_DEFAULT_SHUTDOWN_ARGS)

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

        summary = await live_executor.graceful_shutdown(**_DEFAULT_SHUTDOWN_ARGS)

        assert len(summary.errors) >= 1
        assert "Exchange unreachable" in summary.errors[0]
        # Position phase still ran
        assert summary.positions_evaluated == 1
        assert summary.positions_closed == 1

    @pytest.mark.asyncio
    async def test_no_orders_reports_zero_cancelled(self, paper_executor: OrderExecutor) -> None:
        """Shutdown with no open orders should report zero cancellations."""
        summary = await paper_executor.graceful_shutdown(**_DEFAULT_SHUTDOWN_ARGS)

        assert summary.orders_cancelled == 0

    @pytest.mark.asyncio
    async def test_paper_mode_does_not_call_api_cancel(
        self, paper_executor: OrderExecutor, mock_api_client: AsyncMock
    ) -> None:
        """Paper mode must NOT call the real cancel_all_orders API."""
        paper_executor.open_orders = {
            "paper-1": _make_open_order("paper-1", "BTC-EUR"),
        }

        await paper_executor.graceful_shutdown(**_DEFAULT_SHUTDOWN_ARGS)

        mock_api_client.cancel_all_orders.assert_not_awaited()


# ===========================================================================
# Position Evaluation — Close ALL Positions
# ===========================================================================


class TestGracefulShutdownPositionEvaluation:
    """Tests that ALL positions are closed on shutdown — no exceptions."""

    @pytest.mark.asyncio
    async def test_losing_position_is_closed_immediately(
        self, paper_executor: OrderExecutor
    ) -> None:
        """CRITICAL: Losing positions MUST be closed on shutdown.

        Context: Safety requirement SAF-12
        Critical because: Leaving a losing position unmonitored could cause
        unbounded loss.
        """
        # BUY at 50000, now at 49000 → unrealized_pnl = -1000
        paper_executor.positions["BTC-EUR"] = _make_position(
            "BTC-EUR", OrderSide.BUY, Decimal("50000"), Decimal("49000")
        )

        summary = await paper_executor.graceful_shutdown(**_DEFAULT_SHUTDOWN_ARGS)

        assert summary.positions_closed == 1
        assert summary.positions_trailing_stopped == 0
        assert summary.closed_positions_pnl == Decimal("-1000")
        # Position MUST be removed
        assert "BTC-EUR" not in paper_executor.positions

    @pytest.mark.asyncio
    async def test_profitable_position_is_closed(self, paper_executor: OrderExecutor) -> None:
        """CRITICAL: Profitable positions MUST also be closed on shutdown.

        The bot's contract: EUR → trade → EUR.
        Leaving any position open after shutdown violates this contract.
        """
        # BUY at 50000, now at 51000 → unrealized_pnl = +1000
        paper_executor.positions["BTC-EUR"] = _make_position(
            "BTC-EUR", OrderSide.BUY, Decimal("50000"), Decimal("51000")
        )

        summary = await paper_executor.graceful_shutdown(**_DEFAULT_SHUTDOWN_ARGS)

        assert summary.positions_closed == 1
        assert summary.positions_trailing_stopped == 1
        # trailing_stopped_pnl reflects PnL at actual close price (from position snapshot)
        assert summary.trailing_stopped_pnl >= Decimal("0")
        # Position MUST be removed
        assert "BTC-EUR" not in paper_executor.positions

    @pytest.mark.asyncio
    async def test_breakeven_position_is_closed(self, paper_executor: OrderExecutor) -> None:
        """CRITICAL: Breakeven positions must also be closed on shutdown."""
        paper_executor.positions["BTC-EUR"] = _make_position(
            "BTC-EUR", OrderSide.BUY, Decimal("50000"), Decimal("50000")
        )

        summary = await paper_executor.graceful_shutdown(**_DEFAULT_SHUTDOWN_ARGS)

        assert summary.positions_closed == 1
        assert "BTC-EUR" not in paper_executor.positions

    @pytest.mark.asyncio
    async def test_mixed_positions_all_closed(self, paper_executor: OrderExecutor) -> None:
        """CRITICAL: ALL positions must be closed — losers and winners alike.

        Scenario: BTC losing, ETH winning, SOL breakeven.
        Expected: All three are closed. executor.positions is empty.
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

        summary = await paper_executor.graceful_shutdown(**_DEFAULT_SHUTDOWN_ARGS)

        assert summary.positions_evaluated == 3
        assert summary.positions_closed == 3
        assert "BTC-EUR" not in paper_executor.positions
        assert "ETH-EUR" not in paper_executor.positions
        assert "SOL-EUR" not in paper_executor.positions

    @pytest.mark.asyncio
    async def test_executor_positions_empty_after_shutdown(
        self, paper_executor: OrderExecutor
    ) -> None:
        """CRITICAL: Hard guarantee — executor.positions is ALWAYS empty after shutdown."""
        paper_executor.positions["BTC-EUR"] = _make_position(
            "BTC-EUR", OrderSide.BUY, Decimal("50000"), Decimal("51000")
        )
        paper_executor.positions["ETH-EUR"] = _make_position(
            "ETH-EUR", OrderSide.BUY, Decimal("3000"), Decimal("2800")
        )

        await paper_executor.graceful_shutdown(**_DEFAULT_SHUTDOWN_ARGS)

        assert paper_executor.positions == {}

    @pytest.mark.asyncio
    async def test_short_losing_position_is_closed(self, paper_executor: OrderExecutor) -> None:
        """SELL (short) position that is losing MUST also be closed.

        Short losing = price went up (entry 50000, current 51000, pnl = -1000).
        Close order should be a BUY (opposite side).
        """
        paper_executor.positions["BTC-EUR"] = _make_position(
            "BTC-EUR", OrderSide.SELL, Decimal("50000"), Decimal("51000")
        )

        summary = await paper_executor.graceful_shutdown(**_DEFAULT_SHUTDOWN_ARGS)

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
            summary = await paper_executor.graceful_shutdown(**_DEFAULT_SHUTDOWN_ARGS)

        assert len(summary.errors) >= 1
        assert summary.positions_evaluated == 2
        # At least one position was attempted to be closed
        assert summary.positions_closed >= 1 or len(summary.errors) >= 1

    @pytest.mark.asyncio
    async def test_no_positions_reports_zero(self, paper_executor: OrderExecutor) -> None:
        """Shutdown with no positions should report zero evaluations."""
        summary = await paper_executor.graceful_shutdown(**_DEFAULT_SHUTDOWN_ARGS)

        assert summary.positions_evaluated == 0
        assert summary.positions_closed == 0
        assert summary.positions_trailing_stopped == 0


# ===========================================================================
# Trailing Stop Behaviour
# ===========================================================================


class TestTrailingStopBehavior:
    """Tests for the smart trailing-stop close on profitable positions."""

    @pytest.mark.asyncio
    async def test_trailing_stop_triggers_when_price_drops(
        self, paper_executor: OrderExecutor, mock_api_client: AsyncMock
    ) -> None:
        """Trailing stop closes position when price falls below watermark - stop%.

        Position: BUY @ 50000, current 51000.
        Trailing stop at 0.5% = 51000 * 0.995 = 50745.
        Ticker returns 50700 (below stop) → close immediately.
        """
        paper_executor.positions["BTC-EUR"] = _make_position(
            "BTC-EUR", OrderSide.BUY, Decimal("50000"), Decimal("51000")
        )
        # Return price below trailing stop on first poll
        mock_api_client.get_ticker = AsyncMock(
            return_value={
                "last": Decimal("50700"),
                "bid": Decimal("50650"),
                "ask": Decimal("50750"),
            }
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            summary = await paper_executor.graceful_shutdown(
                trailing_stop_pct=Decimal("0.5"), max_wait_seconds=30
            )

        assert summary.positions_closed == 1
        assert summary.positions_trailing_stopped == 1
        assert "BTC-EUR" not in paper_executor.positions

    @pytest.mark.asyncio
    async def test_trailing_stop_force_closes_on_timeout(
        self, paper_executor: OrderExecutor, mock_api_client: AsyncMock
    ) -> None:
        """CRITICAL: Position MUST be force-closed when max_wait_seconds expires.

        Even if the trailing stop never triggers, the bot must exit all positions.
        """
        paper_executor.positions["BTC-EUR"] = _make_position(
            "BTC-EUR", OrderSide.BUY, Decimal("50000"), Decimal("51000")
        )
        # Price stays well above stop — trailing stop never triggers
        mock_api_client.get_ticker = AsyncMock(
            return_value={
                "last": Decimal("55000"),
                "bid": Decimal("54950"),
                "ask": Decimal("55050"),
            }
        )

        summary = await paper_executor.graceful_shutdown(
            trailing_stop_pct=Decimal("0.5"), max_wait_seconds=0
        )

        # Force closed on timeout
        assert summary.positions_closed == 1
        assert "BTC-EUR" not in paper_executor.positions

    @pytest.mark.asyncio
    async def test_no_trailing_stop_config_closes_immediately(
        self, paper_executor: OrderExecutor, mock_api_client: AsyncMock
    ) -> None:
        """When trailing_stop_pct is None, profitable positions close immediately.

        No get_ticker calls should be made — no polling needed.
        """
        paper_executor.positions["BTC-EUR"] = _make_position(
            "BTC-EUR", OrderSide.BUY, Decimal("50000"), Decimal("51000")
        )

        summary = await paper_executor.graceful_shutdown(
            trailing_stop_pct=None, max_wait_seconds=None
        )

        assert summary.positions_closed == 1
        assert "BTC-EUR" not in paper_executor.positions
        mock_api_client.get_ticker.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_trailing_stop_close_order_strategy_label(
        self, paper_executor: OrderExecutor, mock_api_client: AsyncMock
    ) -> None:
        """Close orders from trailing stop must be labelled 'close_trailing_stop_shutdown'."""
        paper_executor.positions["BTC-EUR"] = _make_position(
            "BTC-EUR", OrderSide.BUY, Decimal("50000"), Decimal("51000")
        )
        mock_api_client.get_ticker = AsyncMock(
            return_value={
                "last": Decimal("50700"),
                "bid": Decimal("50650"),
                "ask": Decimal("50750"),
            }
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            summary = await paper_executor.graceful_shutdown(
                trailing_stop_pct=Decimal("0.5"), max_wait_seconds=30
            )

        trailing_orders = [o for o in summary.filled_close_orders if "trailing" in o.strategy]
        assert len(trailing_orders) == 1
        assert trailing_orders[0].strategy == "close_trailing_stop_shutdown"

    # ===========================================================================
    # Financial Values — Always Decimal
    # ===========================================================================

    @pytest.mark.asyncio
    async def test_profitable_short_position_closed_via_trailing_stop(
        self, paper_executor: OrderExecutor, mock_api_client: AsyncMock
    ) -> None:
        """Profitable SHORT position must also be closed via trailing stop.

        Short profitable = price fell below entry.
        Trailing stop for short: triggers when price rises back above low_watermark + stop%.
        """
        # SELL at 50000, now at 49000 → unrealized_pnl = +1000
        paper_executor.positions["BTC-EUR"] = _make_position(
            "BTC-EUR", OrderSide.SELL, Decimal("50000"), Decimal("49000")
        )
        # Return price above trailing stop for short: 49000 * (2 - 0.995) = 49000 * 1.005 = 49245
        # Return 49500 which is above 49245 → stop triggers
        mock_api_client.get_ticker = AsyncMock(
            return_value={
                "last": Decimal("49500"),
                "bid": Decimal("49450"),
                "ask": Decimal("49550"),
            }
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            summary = await paper_executor.graceful_shutdown(
                trailing_stop_pct=Decimal("0.5"), max_wait_seconds=30
            )

        assert summary.positions_closed == 1
        assert "BTC-EUR" not in paper_executor.positions
        close_orders = [o for o in summary.filled_close_orders if o.symbol == "BTC-EUR"]
        assert len(close_orders) == 1
        assert close_orders[0].side == OrderSide.BUY  # close a SELL with BUY

    @pytest.mark.asyncio
    async def test_ticker_api_failure_force_closes_position(
        self, paper_executor: OrderExecutor, mock_api_client: AsyncMock
    ) -> None:
        """If get_ticker fails during trailing stop wait, position is force-closed immediately."""
        paper_executor.positions["BTC-EUR"] = _make_position(
            "BTC-EUR", OrderSide.BUY, Decimal("50000"), Decimal("51000")
        )
        mock_api_client.get_ticker = AsyncMock(side_effect=RuntimeError("API timeout"))

        summary = await paper_executor.graceful_shutdown(
            trailing_stop_pct=Decimal("0.5"), max_wait_seconds=30
        )

        # Position must still be closed (force-closed on error)
        assert summary.positions_closed == 1
        assert "BTC-EUR" not in paper_executor.positions


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

        summary = await paper_executor.graceful_shutdown(**_DEFAULT_SHUTDOWN_ARGS)

        assert isinstance(summary.closed_positions_pnl, Decimal)
        assert isinstance(summary.trailing_stopped_pnl, Decimal)

    @pytest.mark.asyncio
    async def test_summary_is_shutdown_summary_type(self, paper_executor: OrderExecutor) -> None:
        """graceful_shutdown() must return a ShutdownSummary instance."""
        summary = await paper_executor.graceful_shutdown(**_DEFAULT_SHUTDOWN_ARGS)

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

        summary = await paper_executor.graceful_shutdown(**_DEFAULT_SHUTDOWN_ARGS)

        assert len(summary.filled_close_orders) >= 1
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

        summary = await paper_executor.graceful_shutdown(**_DEFAULT_SHUTDOWN_ARGS)

        assert len(summary.filled_close_orders) >= 1
        assert summary.filled_close_orders[0].side == OrderSide.SELL

    @pytest.mark.asyncio
    async def test_close_order_uses_opposite_side_for_short(
        self, paper_executor: OrderExecutor
    ) -> None:
        """SELL (short) position must be closed with a BUY order."""
        paper_executor.positions["BTC-EUR"] = _make_position(
            "BTC-EUR", OrderSide.SELL, Decimal("50000"), Decimal("51000")
        )

        summary = await paper_executor.graceful_shutdown(**_DEFAULT_SHUTDOWN_ARGS)

        assert len(summary.filled_close_orders) >= 1
        assert summary.filled_close_orders[0].side == OrderSide.BUY

    @pytest.mark.asyncio
    async def test_close_order_strategy_is_graceful_shutdown(
        self, paper_executor: OrderExecutor
    ) -> None:
        """Immediate close orders (losers) must have strategy='close_graceful_shutdown'."""
        paper_executor.positions["BTC-EUR"] = _make_position(
            "BTC-EUR", OrderSide.BUY, Decimal("50000"), Decimal("49000")
        )

        summary = await paper_executor.graceful_shutdown(**_DEFAULT_SHUTDOWN_ARGS)

        assert len(summary.filled_close_orders) >= 1
        assert summary.filled_close_orders[0].strategy == "close_graceful_shutdown"

    @pytest.mark.asyncio
    async def test_filled_close_orders_contains_all_positions(
        self, paper_executor: OrderExecutor
    ) -> None:
        """All closed positions must appear in filled_close_orders."""
        paper_executor.positions["BTC-EUR"] = _make_position(
            "BTC-EUR",
            OrderSide.BUY,
            Decimal("50000"),
            Decimal("49000"),  # loser
        )
        paper_executor.positions["ETH-EUR"] = _make_position(
            "ETH-EUR",
            OrderSide.BUY,
            Decimal("3000"),
            Decimal("3100"),  # winner
        )

        summary = await paper_executor.graceful_shutdown(**_DEFAULT_SHUTDOWN_ARGS)

        # Both BTC (immediate) and ETH (trailing) should have close orders
        assert len(summary.filled_close_orders) == 2
        symbols = {o.symbol for o in summary.filled_close_orders}
        assert "BTC-EUR" in symbols
        assert "ETH-EUR" in symbols
        assert all(o.status == OrderStatus.FILLED for o in summary.filled_close_orders)


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

        summary = await live_executor.graceful_shutdown(**_DEFAULT_SHUTDOWN_ARGS)

        mock_api_client.create_order.assert_awaited_once()
        call_kwargs = mock_api_client.create_order.call_args
        assert call_kwargs.kwargs["side"] == "SELL"  # opposite of BUY
        assert call_kwargs.kwargs["order_type"] == "MARKET"
        assert summary.positions_closed == 1

    @pytest.mark.asyncio
    async def test_live_mode_closes_profitable_position(
        self, live_executor: OrderExecutor, mock_api_client: AsyncMock
    ) -> None:
        """CRITICAL: LIVE mode must ALSO close profitable positions on shutdown.

        The bot's EUR → trade → EUR contract requires ALL positions be closed.
        """
        # Ticker price below trailing stop → close immediately
        mock_api_client.get_ticker = AsyncMock(
            return_value={
                "last": Decimal("50700"),
                "bid": Decimal("50650"),
                "ask": Decimal("50750"),
            }
        )
        live_executor.positions["BTC-EUR"] = _make_position(
            "BTC-EUR", OrderSide.BUY, Decimal("50000"), Decimal("51000")
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            summary = await live_executor.graceful_shutdown(
                trailing_stop_pct=Decimal("0.5"), max_wait_seconds=30
            )

        mock_api_client.create_order.assert_awaited_once()
        assert summary.positions_closed == 1
        assert "BTC-EUR" not in live_executor.positions
