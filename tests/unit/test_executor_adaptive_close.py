"""Tests for adaptive close — LIMIT-with-fallback on take-profit exits.

Verifies:
- stop_loss always uses MARKET regardless of use_limit_close setting
- take_profit uses LIMIT when use_limit_close=True (paper: fills immediately, 0% fee)
- take_profit uses MARKET when use_limit_close=False (default)
- live mode: LIMIT times out → cancelled → MARKET fallback
- Position.strategy is propagated from the opening order
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import RiskLevel, TradingMode
from src.execution.executor import OrderExecutor
from src.models.domain import OrderSide, OrderStatus, OrderType, Position
from src.risk_management.risk_manager import RiskManager


def make_executor(mode: TradingMode = TradingMode.PAPER) -> OrderExecutor:
    """Create an executor with a mock API client."""
    mock_api = MagicMock()
    mock_api.get_order = AsyncMock()
    mock_api.cancel_order = AsyncMock()
    rm = RiskManager(RiskLevel.MODERATE, max_order_value=100_000)
    return OrderExecutor(mock_api, rm, mode)


def inject_position(
    executor: OrderExecutor,
    symbol: str = "BTC-EUR",
    strategy: str = "mean_reversion",
    entry: Decimal = Decimal("50000"),
    current: Decimal = Decimal("52000"),
    qty: Decimal = Decimal("0.1"),
) -> Position:
    """Inject an open BUY position into the executor."""
    pos = Position(
        symbol=symbol,
        side=OrderSide.BUY,
        quantity=qty,
        entry_price=entry,
        current_price=current,
        stop_loss=Decimal("48000"),
        take_profit=Decimal("52000"),
        strategy=strategy,
    )
    executor.positions[symbol] = pos
    return pos


# ── Position.strategy propagation ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_position_receives_strategy_from_opening_order():
    """strategy from opening signal must be stored on the Position."""
    from datetime import UTC, datetime

    from src.models.domain import Signal

    executor = make_executor()
    signal = Signal(
        symbol="BTC-EUR",
        strategy="mean_reversion",
        signal_type="BUY",
        strength=0.6,
        price=Decimal("50000"),
        reason="test",
        timestamp=datetime.now(UTC),
    )
    order = await executor.execute_signal(signal, Decimal("20000"))
    assert order is not None
    assert order.status == OrderStatus.FILLED
    assert "BTC-EUR" in executor.positions
    assert executor.positions["BTC-EUR"].strategy == "mean_reversion"


# ── stop_loss always MARKET ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stop_loss_always_uses_market_even_when_limit_close_enabled():
    """Stop-loss must always place a MARKET order regardless of use_limit_close."""
    executor = make_executor()
    inject_position(executor, strategy="mean_reversion")

    with patch("src.execution.executor.settings") as mock_settings:
        mock_cfg = MagicMock()
        mock_cfg.use_limit_close = True
        mock_cfg.close_limit_timeout_secs = 30
        mock_settings.strategy_configs = {"mean_reversion": mock_cfg}

        order = await executor._close_position("BTC-EUR", Decimal("48000"), "stop_loss")

    assert order is not None
    assert order.order_type == OrderType.MARKET


# ── take_profit with use_limit_close=False (default) ──────────────────────────


@pytest.mark.asyncio
async def test_take_profit_uses_market_by_default():
    """take_profit must use MARKET when use_limit_close=False."""
    executor = make_executor()
    inject_position(executor, strategy="mean_reversion")

    with patch("src.execution.executor.settings") as mock_settings:
        mock_cfg = MagicMock()
        mock_cfg.use_limit_close = False
        mock_settings.strategy_configs = {"mean_reversion": mock_cfg}

        order = await executor._close_position("BTC-EUR", Decimal("52000"), "take_profit")

    assert order is not None
    assert order.order_type == OrderType.MARKET


# ── take_profit with use_limit_close=True (paper) ─────────────────────────────


@pytest.mark.asyncio
async def test_take_profit_uses_limit_in_paper_when_enabled():
    """take_profit with use_limit_close=True must place a LIMIT order in paper mode."""
    executor = make_executor(TradingMode.PAPER)
    inject_position(executor, strategy="mean_reversion")

    with patch("src.execution.executor.settings") as mock_settings:
        mock_cfg = MagicMock()
        mock_cfg.use_limit_close = True
        mock_cfg.close_limit_timeout_secs = 30
        mock_settings.strategy_configs = {"mean_reversion": mock_cfg}

        order = await executor._close_position("BTC-EUR", Decimal("52000"), "take_profit")

    assert order is not None
    assert order.order_type == OrderType.LIMIT
    assert order.status == OrderStatus.FILLED


@pytest.mark.asyncio
async def test_limit_close_paper_charges_zero_fee():
    """LIMIT close in paper mode must apply 0% maker fee."""
    executor = make_executor(TradingMode.PAPER)
    qty = Decimal("0.1")
    inject_position(executor, strategy="mean_reversion", qty=qty)

    with patch("src.execution.executor.settings") as mock_settings:
        mock_cfg = MagicMock()
        mock_cfg.use_limit_close = True
        mock_cfg.close_limit_timeout_secs = 30
        mock_settings.strategy_configs = {"mean_reversion": mock_cfg}

        order = await executor._close_position("BTC-EUR", Decimal("52000"), "take_profit")

    assert order is not None
    assert order.commission == Decimal("0")


# ── live mode: fill immediately ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_limit_close_live_fills_immediately():
    """LIMIT close in live mode: if exchange fills on first placement, no polling needed."""
    executor = make_executor(TradingMode.LIVE)
    inject_position(executor, strategy="mean_reversion")

    executor.api_client.create_order = AsyncMock(
        return_value={"venue_order_id": "ord-1", "client_order_id": "c-1", "state": "filled"}
    )

    with patch("src.execution.executor.settings") as mock_settings:
        mock_cfg = MagicMock()
        mock_cfg.use_limit_close = True
        mock_cfg.close_limit_timeout_secs = 30
        mock_settings.strategy_configs = {"mean_reversion": mock_cfg}

        order = await executor._close_position("BTC-EUR", Decimal("52000"), "take_profit")

    assert order is not None
    assert order.order_type == OrderType.LIMIT
    assert order.status == OrderStatus.FILLED
    executor.api_client.get_order.assert_not_called()


# ── live mode: timeout → MARKET fallback ──────────────────────────────────────


@pytest.mark.asyncio
async def test_limit_close_live_falls_back_to_market_on_timeout():
    """LIMIT close in live mode must cancel and fall back to MARKET after timeout."""
    executor = make_executor(TradingMode.LIVE)
    inject_position(executor, strategy="mean_reversion")

    executor.api_client.create_order = AsyncMock(
        side_effect=[
            # First call: LIMIT order placed, stays pending
            {"venue_order_id": "ord-limit", "client_order_id": "c-1", "state": "new"},
            # Second call: MARKET fallback fills
            {"venue_order_id": "ord-market", "client_order_id": "c-2", "state": "filled"},
        ]
    )
    executor.api_client.get_order = AsyncMock(
        return_value={"state": "new"}  # always pending
    )
    executor.api_client.cancel_order = AsyncMock()

    with patch("src.execution.executor.settings") as mock_settings:
        mock_cfg = MagicMock()
        mock_cfg.use_limit_close = True
        mock_cfg.close_limit_timeout_secs = 1  # short timeout for test
        mock_settings.strategy_configs = {"mean_reversion": mock_cfg}

        with patch("asyncio.sleep", new_callable=AsyncMock):
            order = await executor._close_position("BTC-EUR", Decimal("52000"), "take_profit")

    assert order is not None
    assert order.order_type == OrderType.MARKET
    assert order.status == OrderStatus.FILLED
    executor.api_client.cancel_order.assert_called_once_with("ord-limit")


# ── live mode: fill during polling ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_limit_close_live_fills_during_polling():
    """LIMIT close in live mode: fills on a subsequent poll rather than immediately."""
    executor = make_executor(TradingMode.LIVE)
    inject_position(executor, strategy="mean_reversion")

    executor.api_client.create_order = AsyncMock(
        return_value={"venue_order_id": "ord-1", "client_order_id": "c-1", "state": "new"}
    )
    executor.api_client.get_order = AsyncMock(return_value={"state": "filled"})

    with patch("src.execution.executor.settings") as mock_settings:
        mock_cfg = MagicMock()
        mock_cfg.use_limit_close = True
        mock_cfg.close_limit_timeout_secs = 10
        mock_settings.strategy_configs = {"mean_reversion": mock_cfg}

        with patch("asyncio.sleep", new_callable=AsyncMock):
            order = await executor._close_position("BTC-EUR", Decimal("52000"), "take_profit")

    assert order is not None
    assert order.order_type == OrderType.LIMIT
    assert order.status == OrderStatus.FILLED
    executor.api_client.cancel_order.assert_not_called()


@pytest.mark.asyncio
async def test_limit_close_live_fills_during_polling_sets_commission():
    """Commission must be calculated when a LIMIT close fills during polling."""
    executor = make_executor(TradingMode.LIVE)
    inject_position(executor, strategy="mean_reversion", qty=Decimal("0.1"))

    executor.api_client.create_order = AsyncMock(
        return_value={"venue_order_id": "ord-1", "client_order_id": "c-1", "state": "new"}
    )
    executor.api_client.get_order = AsyncMock(return_value={"state": "filled"})

    with patch("src.execution.executor.settings") as mock_settings:
        mock_cfg = MagicMock()
        mock_cfg.use_limit_close = True
        mock_cfg.close_limit_timeout_secs = 10
        mock_settings.strategy_configs = {"mean_reversion": mock_cfg}

        with patch("asyncio.sleep", new_callable=AsyncMock):
            order = await executor._close_position("BTC-EUR", Decimal("52000"), "take_profit")

    assert order is not None
    assert order.commission == Decimal("0")  # LIMIT order → 0% maker fee


# ── live mode: cancelled/rejected during polling ───────────────────────────────


@pytest.mark.asyncio
async def test_limit_close_live_cancelled_during_polling_falls_back_to_market():
    """If exchange cancels the LIMIT before it fills, executor falls back to MARKET."""
    executor = make_executor(TradingMode.LIVE)
    inject_position(executor, strategy="mean_reversion")

    executor.api_client.create_order = AsyncMock(
        side_effect=[
            {"venue_order_id": "ord-limit", "client_order_id": "c-1", "state": "new"},
            {"venue_order_id": "ord-market", "client_order_id": "c-2", "state": "filled"},
        ]
    )
    executor.api_client.get_order = AsyncMock(return_value={"state": "cancelled"})
    executor.api_client.cancel_order = AsyncMock()

    with patch("src.execution.executor.settings") as mock_settings:
        mock_cfg = MagicMock()
        mock_cfg.use_limit_close = True
        mock_cfg.close_limit_timeout_secs = 10
        mock_settings.strategy_configs = {"mean_reversion": mock_cfg}

        with patch("asyncio.sleep", new_callable=AsyncMock):
            order = await executor._close_position("BTC-EUR", Decimal("52000"), "take_profit")

    assert order is not None
    assert order.order_type == OrderType.MARKET
    assert order.status == OrderStatus.FILLED


@pytest.mark.asyncio
async def test_limit_close_live_polling_exception_then_timeout_fallback():
    """If polling raises an exception on every attempt, executor times out and falls back."""
    executor = make_executor(TradingMode.LIVE)
    inject_position(executor, strategy="mean_reversion")

    executor.api_client.create_order = AsyncMock(
        side_effect=[
            {"venue_order_id": "ord-limit", "client_order_id": "c-1", "state": "new"},
            {"venue_order_id": "ord-market", "client_order_id": "c-2", "state": "filled"},
        ]
    )
    executor.api_client.get_order = AsyncMock(side_effect=Exception("network error"))
    executor.api_client.cancel_order = AsyncMock()

    with patch("src.execution.executor.settings") as mock_settings:
        mock_cfg = MagicMock()
        mock_cfg.use_limit_close = True
        mock_cfg.close_limit_timeout_secs = 1
        mock_settings.strategy_configs = {"mean_reversion": mock_cfg}

        with patch("asyncio.sleep", new_callable=AsyncMock):
            order = await executor._close_position("BTC-EUR", Decimal("52000"), "take_profit")

    assert order is not None
    assert order.order_type == OrderType.MARKET
    assert order.status == OrderStatus.FILLED


# ── live mode: cancel raises during fallback ───────────────────────────────────


@pytest.mark.asyncio
async def test_limit_close_live_cancel_raises_still_falls_back_to_market():
    """Even if cancel_order raises, the executor continues to place a MARKET fallback."""
    executor = make_executor(TradingMode.LIVE)
    inject_position(executor, strategy="mean_reversion")

    executor.api_client.create_order = AsyncMock(
        side_effect=[
            {"venue_order_id": "ord-limit", "client_order_id": "c-1", "state": "new"},
            {"venue_order_id": "ord-market", "client_order_id": "c-2", "state": "filled"},
        ]
    )
    executor.api_client.get_order = AsyncMock(return_value={"state": "new"})
    executor.api_client.cancel_order = AsyncMock(side_effect=Exception("cancel failed"))

    with patch("src.execution.executor.settings") as mock_settings:
        mock_cfg = MagicMock()
        mock_cfg.use_limit_close = True
        mock_cfg.close_limit_timeout_secs = 1
        mock_settings.strategy_configs = {"mean_reversion": mock_cfg}

        with patch("asyncio.sleep", new_callable=AsyncMock):
            order = await executor._close_position("BTC-EUR", Decimal("52000"), "take_profit")

    assert order is not None
    assert order.order_type == OrderType.MARKET
    assert order.status == OrderStatus.FILLED


# ── strategy key normalisation ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_limit_close_normalises_strategy_key_with_spaces():
    """Strategy names with spaces/hyphens must be normalised to snake_case for config lookup."""
    executor = make_executor(TradingMode.PAPER)
    inject_position(executor, strategy="Market Making")

    with patch("src.execution.executor.settings") as mock_settings:
        mock_cfg = MagicMock()
        mock_cfg.use_limit_close = True
        mock_cfg.close_limit_timeout_secs = 30
        mock_settings.strategy_configs = {"market_making": mock_cfg}

        order = await executor._close_position("BTC-EUR", Decimal("52000"), "take_profit")

    assert order is not None
    assert order.order_type == OrderType.LIMIT
