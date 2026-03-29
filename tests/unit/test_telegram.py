"""Tests for TelegramNotifier.

Covers: message formatting, HTTP payload, silent failure on network/HTTP errors.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.models.domain import Order, OrderSide, OrderStatus, OrderType
from src.utils.telegram import TelegramNotifier

TOKEN = "123456:ABCDEF_test_token"
CHAT_ID = "-100123456789"


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def notifier() -> TelegramNotifier:
    return TelegramNotifier(token=TOKEN, chat_id=CHAT_ID)


@pytest.fixture
def mock_http():
    """Mock httpx.AsyncClient — captures POST calls and returns 200."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    with patch("src.utils.telegram.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        yield mock_client


@pytest.fixture
def failing_http():
    """Mock httpx.AsyncClient — raises ConnectError on POST."""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("unreachable"))
    with patch("src.utils.telegram.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        yield mock_client


@pytest.fixture
def http_error():
    """Mock httpx.AsyncClient — raise_for_status raises HTTPStatusError."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError("429", request=MagicMock(), response=MagicMock())
    )
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    with patch("src.utils.telegram.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        yield mock_client


def _make_order(
    side: OrderSide = OrderSide.BUY,
    symbol: str = "BTC-EUR",
    price: str = "50000.00",
    filled_quantity: str = "0.001",
    commission: str = "0.045",
    realized_pnl: str | None = None,
) -> Order:
    return Order(
        symbol=symbol,
        side=side,
        order_type=OrderType.MARKET,
        quantity=Decimal(filled_quantity),
        price=Decimal(price),
        filled_quantity=Decimal(filled_quantity),
        status=OrderStatus.FILLED,
        commission=Decimal(commission),
        realized_pnl=Decimal(realized_pnl) if realized_pnl is not None else None,
    )


# ── URL construction ──────────────────────────────────────────────────────────


def test_url_contains_token():
    n = TelegramNotifier(token="abc:XYZ", chat_id="42")
    assert "abc:XYZ" in n._url


# ── Silent failure ────────────────────────────────────────────────────────────


async def test_connection_error_is_silent(notifier, failing_http):
    """A network error must not propagate — trading loop must stay alive."""
    await notifier.notify_error("boom")  # must not raise


async def test_http_status_error_is_silent(notifier, http_error):
    """A non-2xx response must not propagate."""
    await notifier.notify_error("boom")  # must not raise


# ── _send payload ─────────────────────────────────────────────────────────────


async def test_send_posts_to_correct_url(notifier, mock_http):
    await notifier._send("hello")
    mock_http.post.assert_awaited_once()
    url = mock_http.post.call_args.args[0]
    assert TOKEN in url


async def test_send_includes_chat_id(notifier, mock_http):
    await notifier._send("hello")
    payload = mock_http.post.call_args.kwargs["json"]
    assert payload["chat_id"] == CHAT_ID


async def test_send_uses_html_parse_mode(notifier, mock_http):
    await notifier._send("hello")
    payload = mock_http.post.call_args.kwargs["json"]
    assert payload["parse_mode"] == "HTML"


# ── notify_started ────────────────────────────────────────────────────────────


async def test_notify_started_contains_strategy(notifier, mock_http):
    await notifier.notify_started("momentum", "moderate", ["BTC-EUR"], "paper")
    text = mock_http.post.call_args.kwargs["json"]["text"]
    assert "momentum" in text


async def test_notify_started_contains_pairs(notifier, mock_http):
    await notifier.notify_started("momentum", "moderate", ["BTC-EUR", "ETH-EUR"], "paper")
    text = mock_http.post.call_args.kwargs["json"]["text"]
    assert "BTC-EUR" in text
    assert "ETH-EUR" in text


async def test_notify_started_live_mode_label(notifier, mock_http):
    await notifier.notify_started("momentum", "moderate", ["BTC-EUR"], "live")
    text = mock_http.post.call_args.kwargs["json"]["text"]
    assert "LIVE" in text


async def test_notify_started_paper_mode_label(notifier, mock_http):
    await notifier.notify_started("momentum", "moderate", ["BTC-EUR"], "paper")
    text = mock_http.post.call_args.kwargs["json"]["text"]
    assert "Paper" in text


# ── notify_stopped ────────────────────────────────────────────────────────────


async def test_notify_stopped_contains_session_id(notifier, mock_http):
    await notifier.notify_stopped(session_id=42, realized_pnl=Decimal("125.50"))
    text = mock_http.post.call_args.kwargs["json"]["text"]
    assert "42" in text


async def test_notify_stopped_positive_pnl_has_plus_sign(notifier, mock_http):
    await notifier.notify_stopped(session_id=1, realized_pnl=Decimal("50.00"))
    text = mock_http.post.call_args.kwargs["json"]["text"]
    assert "+€50.00" in text


async def test_notify_stopped_negative_pnl_no_plus_sign(notifier, mock_http):
    await notifier.notify_stopped(session_id=1, realized_pnl=Decimal("-30.00"))
    text = mock_http.post.call_args.kwargs["json"]["text"]
    assert "-€30.00" in text
    assert "+-€30.00" not in text


async def test_notify_stopped_none_session_id(notifier, mock_http):
    """None session_id must not crash."""
    await notifier.notify_stopped(session_id=None, realized_pnl=Decimal("0"))


# ── notify_trade — BUY ────────────────────────────────────────────────────────


async def test_notify_trade_buy_contains_symbol(notifier, mock_http):
    await notifier.notify_trade(_make_order(OrderSide.BUY))
    text = mock_http.post.call_args.kwargs["json"]["text"]
    assert "BTC-EUR" in text


async def test_notify_trade_buy_contains_price(notifier, mock_http):
    await notifier.notify_trade(_make_order(OrderSide.BUY, price="50000.00"))
    text = mock_http.post.call_args.kwargs["json"]["text"]
    assert "50,000.00" in text


async def test_notify_trade_buy_shows_buy_label(notifier, mock_http):
    await notifier.notify_trade(_make_order(OrderSide.BUY))
    text = mock_http.post.call_args.kwargs["json"]["text"]
    assert "BUY" in text


async def test_notify_trade_buy_no_pnl_line(notifier, mock_http):
    """BUY orders have no realized P&L — the P&L line must be absent."""
    await notifier.notify_trade(_make_order(OrderSide.BUY, realized_pnl=None))
    text = mock_http.post.call_args.kwargs["json"]["text"]
    assert "P&" not in text


# ── notify_trade — SELL ───────────────────────────────────────────────────────


async def test_notify_trade_sell_shows_sell_label(notifier, mock_http):
    await notifier.notify_trade(_make_order(OrderSide.SELL, realized_pnl="10.52"))
    text = mock_http.post.call_args.kwargs["json"]["text"]
    assert "SELL" in text


async def test_notify_trade_sell_with_positive_pnl(notifier, mock_http):
    await notifier.notify_trade(_make_order(OrderSide.SELL, realized_pnl="10.52"))
    text = mock_http.post.call_args.kwargs["json"]["text"]
    assert "+€10.52" in text


async def test_notify_trade_sell_with_negative_pnl(notifier, mock_http):
    await notifier.notify_trade(_make_order(OrderSide.SELL, realized_pnl="-5.00"))
    text = mock_http.post.call_args.kwargs["json"]["text"]
    assert "-€5.00" in text


async def test_notify_trade_no_price_skips_send(notifier, mock_http):
    """Order with no price should not send any message."""
    order = Order(
        symbol="BTC-EUR",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.001"),
        status=OrderStatus.FILLED,
    )
    await notifier.notify_trade(order)
    mock_http.post.assert_not_awaited()


# ── notify_error ──────────────────────────────────────────────────────────────


async def test_notify_error_contains_message(notifier, mock_http):
    await notifier.notify_error("Authentication failed!")
    text = mock_http.post.call_args.kwargs["json"]["text"]
    assert "Authentication failed!" in text


# ── notify_daily_loss_limit ───────────────────────────────────────────────────


async def test_notify_daily_loss_limit_contains_pnl(notifier, mock_http):
    await notifier.notify_daily_loss_limit(Decimal("-250.00"))
    text = mock_http.post.call_args.kwargs["json"]["text"]
    assert "-250.00" in text


async def test_notify_daily_loss_limit_mentions_suspended(notifier, mock_http):
    await notifier.notify_daily_loss_limit(Decimal("-100.00"))
    text = mock_http.post.call_args.kwargs["json"]["text"]
    assert "suspended" in text.lower()
