"""Telegram notification service for trading events.

Sends notifications via the Telegram Bot API when key trading events occur:
- Bot started / stopped
- Order filled (buy or sell)
- Critical errors (authentication failure, daily loss limit)

Failures are always silent — Telegram errors are logged but never raised,
so a connectivity issue or misconfiguration can never disrupt live trading.

Configuration (optional — stored in 1Password):
    TELEGRAM_BOT_TOKEN  Bot API token from @BotFather
    TELEGRAM_CHAT_ID    Target chat or channel ID (use a negative ID for channels)
"""

import asyncio
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

import httpx
from loguru import logger

from src.models.domain import Order, OrderSide


class TelegramNotifier:
    """Sends trading event notifications via the Telegram Bot API.

    All public methods are fire-and-forget: any exception raised during the
    HTTP call is caught, logged at WARNING level, and swallowed.  This
    guarantees that Telegram outages or misconfiguration cannot affect the
    trading loop.

    Messages use Telegram's HTML parse mode so bold headings and special
    characters (``&``, ``<``, ``>``) are handled correctly.
    """

    _API_URL = "https://api.telegram.org/bot{token}/sendMessage"
    _DOC_URL = "https://api.telegram.org/bot{token}/sendDocument"
    _UPDATES_URL = "https://api.telegram.org/bot{token}/getUpdates"
    # Short timeout: a slow Telegram API must not stall the trading loop.
    _TIMEOUT = 30.0  # file uploads need a longer timeout than text messages

    def __init__(self, token: str, chat_id: str) -> None:
        """Initialise the notifier with bot credentials.

        Args:
            token:   Telegram Bot API token (obtain from @BotFather).
            chat_id: Target chat or channel ID.  Use a negative integer
                     string for channels (e.g. ``"-100123456789"``).
        """
        self._url = self._API_URL.format(token=token)
        self._doc_url = self._DOC_URL.format(token=token)
        self._updates_url = self._UPDATES_URL.format(token=token)
        self._chat_id = chat_id

    async def _send(self, text: str) -> None:
        """POST a message to the Telegram Bot API.

        Silently logs and discards all exceptions so callers are never
        disrupted by Telegram failures.

        Args:
            text: HTML-formatted message body.
        """
        try:
            async with httpx.AsyncClient(timeout=self._TIMEOUT) as client:
                response = await client.post(
                    self._url,
                    json={
                        "chat_id": self._chat_id,
                        "text": text,
                        "parse_mode": "HTML",
                    },
                )
                response.raise_for_status()
        except Exception as exc:
            logger.warning(f"Telegram notification failed: {exc}")

    async def notify_started(
        self,
        strategy: str,
        risk_level: str,
        pairs: list[str],
        mode: str,
    ) -> None:
        """Notify that the trading bot has started.

        Args:
            strategy:   Active strategy name (e.g. ``"momentum"``).
            risk_level: Active risk level (e.g. ``"moderate"``).
            pairs:      Trading pairs being monitored (e.g. ``["BTC-EUR"]``).
            mode:       Trading mode — ``"live"`` or ``"paper"``.
        """
        mode_label = "🔴 LIVE" if mode == "live" else "🟡 Paper"
        await self._send(
            f"🤖 <b>Trading Bot Started</b>\n"
            f"Strategy: {strategy}\n"
            f"Risk: {risk_level}\n"
            f"Pairs: {', '.join(pairs)}\n"
            f"Mode: {mode_label}"
        )

    async def notify_stopped(
        self,
        session_id: int | None,
        realized_pnl: Decimal,
        currency_symbol: str = "€",
    ) -> None:
        """Notify that the trading bot has stopped.

        Args:
            session_id:      Database session ID, or ``None`` if unavailable.
            realized_pnl:    Total realized P&L for the session.
            currency_symbol: Symbol for the base currency (e.g. ``"€"``).
        """
        sign = "+" if realized_pnl >= 0 else "-"
        session_label = f"#{session_id}" if session_id is not None else "—"
        await self._send(
            f"🛑 <b>Trading Bot Stopped</b>\n"
            f"Session: {session_label}\n"
            f"Realized P&amp;L: {sign}{currency_symbol}{abs(realized_pnl):,.2f}"
        )

    async def notify_trade(self, order: Order, currency_symbol: str = "€") -> None:
        """Notify that an order has been filled.

        No message is sent if the order has no execution price (which should
        not happen for a FILLED order, but is handled defensively).

        Args:
            order:           The filled order to report.
            currency_symbol: Symbol for the base currency (e.g. ``"€"``).
        """
        if order.price is None:
            return

        if order.side == OrderSide.BUY:
            emoji, action = "📈", "BUY"
        else:
            emoji, action = "📉", "SELL"

        lines = [
            f"{emoji} <b>{action} Executed</b>",
            f"Symbol: {order.symbol}",
            f"Qty: {order.filled_quantity}",
            f"Price: {currency_symbol}{order.price:,.2f}",
            f"Fee: {currency_symbol}{order.commission:,.4f}",
        ]

        if order.realized_pnl is not None:
            sign = "+" if order.realized_pnl >= 0 else "-"
            lines.append(f"P&amp;L: {sign}{currency_symbol}{abs(order.realized_pnl):,.2f}")

        await self._send("\n".join(lines))

    async def notify_error(self, message: str) -> None:
        """Notify a critical trading error.

        Args:
            message: Human-readable description of the error.
        """
        await self._send(f"🚨 <b>Critical Error</b>\n{message}")

    async def send_test(self) -> None:
        """Send a test notification to verify connectivity; raises on any failure.

        Unlike all other ``notify_*`` methods (which are fire-and-forget),
        this method lets exceptions propagate so the caller can report
        success or failure to the user.  Use only for manual connectivity
        checks — never call this from the trading loop.

        Raises:
            httpx.ConnectError: If the Telegram API is unreachable.
            httpx.HTTPStatusError: If the bot token or chat ID is invalid.
        """
        async with httpx.AsyncClient(timeout=self._TIMEOUT) as client:
            response = await client.post(
                self._url,
                json={
                    "chat_id": self._chat_id,
                    "text": "✅ <b>Revolut Trader</b> — Telegram notifications are working correctly.",
                    "parse_mode": "HTML",
                },
            )
            response.raise_for_status()

    async def notify_daily_loss_limit(
        self,
        daily_pnl: Decimal,
        currency_symbol: str = "€",
    ) -> None:
        """Notify that the daily loss limit has been hit and trading is suspended.

        Args:
            daily_pnl:       Current day's P&L (negative value).
            currency_symbol: Symbol for the base currency (e.g. ``"€"``).
        """
        await self._send(
            f"⛔ <b>Daily Loss Limit Hit</b>\n"
            f"P&amp;L: {currency_symbol}{daily_pnl:,.2f}\n"
            f"Trading suspended until reset."
        )

    async def send_document(
        self,
        document: bytes,
        filename: str,
        caption: str = "",
    ) -> None:
        """Send a document file to the Telegram chat.

        Uses Telegram's sendDocument endpoint with multipart form data.
        Silently logs and discards all exceptions — same contract as other
        ``notify_*`` methods.

        Args:
            document: Raw file bytes to send.
            filename: Filename to display in Telegram.
            caption:  Optional HTML-formatted caption (max 1024 chars).
        """
        try:
            async with httpx.AsyncClient(timeout=self._TIMEOUT) as client:
                response = await client.post(
                    self._doc_url,
                    data={"chat_id": self._chat_id, "parse_mode": "HTML", "caption": caption},
                    files={"document": (filename, document, "application/pdf")},
                )
                response.raise_for_status()
        except Exception as exc:
            logger.warning(f"Telegram document upload failed: {exc}")

    async def notify_report_ready(
        self,
        days: int,
        total_trades: int,
        total_pnl: Decimal,
        return_pct: float,
        win_rate: float,
        sharpe_ratio: float,
        max_drawdown_pct: float,
        report_path: str,
        currency_symbol: str = "€",
    ) -> None:
        """Notify that an analytics report has been generated.

        Args:
            days:             Look-back window in calendar days.
            total_trades:     Total number of trades in the period.
            total_pnl:        Net P&L after fees.
            return_pct:       Return as a percentage of initial capital.
            win_rate:         Percentage of winning trades.
            sharpe_ratio:     Annualised Sharpe ratio.
            max_drawdown_pct: Maximum drawdown as a percentage of peak equity.
            report_path:      File path to the generated report.
            currency_symbol:  Symbol for the base currency (e.g. ``"€"``).
        """
        pnl_sign = "+" if total_pnl >= 0 else "-"
        ret_sign = "+" if return_pct >= 0 else ""
        emoji = "📊" if total_pnl >= 0 else "📉"

        lines = [
            f"{emoji} <b>Analytics Report Ready</b>",
            f"Period: {days} days",
            f"Trades: {total_trades}",
            f"Net P&amp;L: {pnl_sign}{currency_symbol}{abs(total_pnl):,.2f}",
            f"Return: {ret_sign}{return_pct:.2f}%",
            f"Win Rate: {win_rate:.1f}%",
            f"Sharpe: {sharpe_ratio:.3f}" if sharpe_ratio else "Sharpe: N/A",
            f"Max DD: {max_drawdown_pct:.1f}%",
            f"Report: {report_path}",
        ]

        await self._send("\n".join(lines))

    async def reply(self, text: str) -> None:
        """Send a plain HTML text reply (e.g. in response to a bot command).

        Behaves identically to all other ``notify_*`` methods: fire-and-forget,
        silent on any error.

        Args:
            text: HTML-formatted message to send.
        """
        await self._send(text)

    async def get_updates(self, offset: int = 0, timeout: int = 30) -> list[dict[str, Any]]:
        """Fetch pending updates from Telegram via long polling (getUpdates).

        Returns an empty list on any error so the polling loop continues safely.

        Args:
            offset:  First update ID to return; pass previous ``update_id + 1``
                     to acknowledge processed updates.
            timeout: Long-poll timeout in seconds.

        Returns:
            List of raw update dicts, or ``[]`` on failure.
        """
        try:
            async with httpx.AsyncClient(timeout=float(timeout + 5)) as client:
                response = await client.get(
                    self._updates_url,
                    params={
                        "offset": offset,
                        "timeout": timeout,
                        "allowed_updates": ["message"],
                    },
                )
                response.raise_for_status()
                data = response.json()
                return data.get("result", []) if data.get("ok") else []
        except Exception as exc:
            logger.warning(f"Telegram getUpdates failed: {exc}")
            return []

    async def start_polling(
        self,
        command_handler: Callable[[str, list[str]], Awaitable[None]],
        stop_event: asyncio.Event,
    ) -> None:
        """Poll for incoming Telegram commands until *stop_event* is set.

        Long-polls ``getUpdates``, dispatches ``/command [args]`` messages from
        the configured chat, and advances the offset to acknowledge each update.
        Messages from other chats are silently ignored for security.

        Args:
            command_handler: Async callable invoked as
                             ``handler(command, args)`` for each ``/command``.
            stop_event:      Setting this exits the loop after the current
                             ``getUpdates`` call completes.
        """
        offset = 0
        while not stop_event.is_set():
            updates = await self.get_updates(offset=offset, timeout=25)
            for update in updates:
                offset = update["update_id"] + 1
                message = update.get("message", {})
                chat_id = str(message.get("chat", {}).get("id", ""))
                if chat_id != self._chat_id:
                    continue  # security: ignore messages from other chats
                text = message.get("text", "")
                if not text.startswith("/"):
                    continue
                parts = text.split()
                # Strip optional @BotName suffix (e.g. /status@MyBot → status)
                command = parts[0].lstrip("/").split("@")[0].lower()
                args = parts[1:]
                await command_handler(command, args)
