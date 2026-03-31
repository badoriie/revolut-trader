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


# ── send_test ─────────────────────────────────────────────────────────────────


async def test_send_test_posts_to_api(notifier, mock_http):
    """send_test must POST a message to the Telegram Bot API."""
    await notifier.send_test()
    mock_http.post.assert_awaited_once()
    url = mock_http.post.call_args.args[0]
    assert TOKEN in url


async def test_send_test_message_indicates_working(notifier, mock_http):
    """Test message must communicate that notifications are working."""
    await notifier.send_test()
    text = mock_http.post.call_args.kwargs["json"]["text"]
    assert "working" in text.lower() or "✅" in text


async def test_send_test_raises_on_connection_error(notifier, failing_http):
    """send_test must propagate errors — unlike the silent production methods."""
    with pytest.raises(httpx.ConnectError):
        await notifier.send_test()


async def test_send_test_raises_on_http_error(notifier, http_error):
    """send_test must propagate HTTP errors — unlike the silent production methods."""
    with pytest.raises(httpx.HTTPStatusError):
        await notifier.send_test()


# ── send_document ─────────────────────────────────────────────────────────────


async def test_send_document_posts_to_send_document_url(notifier, mock_http):
    """send_document must call the sendDocument endpoint, not sendMessage."""
    await notifier.send_document(b"%PDF-dummy", "report.pdf")
    url = mock_http.post.call_args.args[0]
    assert "sendDocument" in url
    assert "sendMessage" not in url


async def test_send_document_sends_file_bytes(notifier, mock_http):
    """The PDF bytes must be included in the multipart files payload."""
    pdf_bytes = b"%PDF-1.4 test content"
    await notifier.send_document(pdf_bytes, "report.pdf")
    files = mock_http.post.call_args.kwargs["files"]
    # files["document"] is a tuple (filename, bytes, content_type)
    assert files["document"][1] == pdf_bytes


async def test_send_document_uses_pdf_filename(notifier, mock_http):
    """The filename in the multipart payload must match what was passed."""
    await notifier.send_document(b"%PDF", "analytics_report.pdf")
    files = mock_http.post.call_args.kwargs["files"]
    assert files["document"][0] == "analytics_report.pdf"


async def test_send_document_includes_caption(notifier, mock_http):
    """A non-empty caption must appear in the form data payload."""
    await notifier.send_document(b"%PDF", "report.pdf", caption="<b>Summary</b>")
    data = mock_http.post.call_args.kwargs["data"]
    assert data["caption"] == "<b>Summary</b>"


async def test_send_document_is_silent_on_error(notifier, failing_http):
    """send_document must not raise on network failure — same contract as other notify_* methods."""
    await notifier.send_document(b"%PDF", "report.pdf")  # must not raise


# ── notify_report_ready ───────────────────────────────────────────────────────


async def test_notify_report_ready_contains_days(notifier, mock_http):
    await notifier.notify_report_ready(
        days=30,
        total_trades=100,
        total_pnl=Decimal("500.00"),
        return_pct=5.0,
        win_rate=60.0,
        sharpe_ratio=1.5,
        max_drawdown_pct=3.2,
        report_path="data/reports/report.md",
    )
    text = mock_http.post.call_args.kwargs["json"]["text"]
    assert "30 days" in text


async def test_notify_report_ready_contains_total_trades(notifier, mock_http):
    await notifier.notify_report_ready(
        days=30,
        total_trades=100,
        total_pnl=Decimal("500.00"),
        return_pct=5.0,
        win_rate=60.0,
        sharpe_ratio=1.5,
        max_drawdown_pct=3.2,
        report_path="data/reports/report.md",
    )
    text = mock_http.post.call_args.kwargs["json"]["text"]
    assert "100" in text


async def test_notify_report_ready_positive_pnl(notifier, mock_http):
    await notifier.notify_report_ready(
        days=30,
        total_trades=100,
        total_pnl=Decimal("500.00"),
        return_pct=5.0,
        win_rate=60.0,
        sharpe_ratio=1.5,
        max_drawdown_pct=3.2,
        report_path="data/reports/report.md",
    )
    text = mock_http.post.call_args.kwargs["json"]["text"]
    assert "+€500.00" in text
    assert "+5.00%" in text


async def test_notify_report_ready_negative_pnl(notifier, mock_http):
    await notifier.notify_report_ready(
        days=30,
        total_trades=50,
        total_pnl=Decimal("-200.00"),
        return_pct=-2.0,
        win_rate=40.0,
        sharpe_ratio=-0.3,
        max_drawdown_pct=5.1,
        report_path="data/reports/report.md",
    )
    text = mock_http.post.call_args.kwargs["json"]["text"]
    assert "-€200.00" in text
    assert "-2.00%" in text


async def test_notify_report_ready_contains_sharpe(notifier, mock_http):
    await notifier.notify_report_ready(
        days=30,
        total_trades=100,
        total_pnl=Decimal("500.00"),
        return_pct=5.0,
        win_rate=60.0,
        sharpe_ratio=1.523,
        max_drawdown_pct=3.2,
        report_path="data/reports/report.md",
    )
    text = mock_http.post.call_args.kwargs["json"]["text"]
    assert "1.523" in text


async def test_notify_report_ready_contains_win_rate(notifier, mock_http):
    await notifier.notify_report_ready(
        days=30,
        total_trades=100,
        total_pnl=Decimal("500.00"),
        return_pct=5.0,
        win_rate=62.5,
        sharpe_ratio=1.5,
        max_drawdown_pct=3.2,
        report_path="data/reports/report.md",
    )
    text = mock_http.post.call_args.kwargs["json"]["text"]
    assert "62.5%" in text


async def test_notify_report_ready_contains_max_drawdown(notifier, mock_http):
    await notifier.notify_report_ready(
        days=30,
        total_trades=100,
        total_pnl=Decimal("500.00"),
        return_pct=5.0,
        win_rate=60.0,
        sharpe_ratio=1.5,
        max_drawdown_pct=3.27,
        report_path="data/reports/report.md",
    )
    text = mock_http.post.call_args.kwargs["json"]["text"]
    assert "3.3%" in text


async def test_notify_report_ready_contains_report_path(notifier, mock_http):
    await notifier.notify_report_ready(
        days=30,
        total_trades=100,
        total_pnl=Decimal("500.00"),
        return_pct=5.0,
        win_rate=60.0,
        sharpe_ratio=1.5,
        max_drawdown_pct=3.2,
        report_path="data/reports/report.md",
    )
    text = mock_http.post.call_args.kwargs["json"]["text"]
    assert "data/reports/report.md" in text


async def test_notify_report_ready_zero_sharpe_shows_na(notifier, mock_http):
    await notifier.notify_report_ready(
        days=30,
        total_trades=100,
        total_pnl=Decimal("500.00"),
        return_pct=5.0,
        win_rate=60.0,
        sharpe_ratio=0.0,
        max_drawdown_pct=3.2,
        report_path="data/reports/report.md",
    )
    text = mock_http.post.call_args.kwargs["json"]["text"]
    assert "N/A" in text


async def test_notify_report_ready_is_silent_on_error(notifier, failing_http):
    """Report notification must not raise on network failure."""
    await notifier.notify_report_ready(
        days=30,
        total_trades=100,
        total_pnl=Decimal("500.00"),
        return_pct=5.0,
        win_rate=60.0,
        sharpe_ratio=1.5,
        max_drawdown_pct=3.2,
        report_path="data/reports/report.md",
    )  # must not raise
