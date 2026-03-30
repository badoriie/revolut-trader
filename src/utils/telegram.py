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

from decimal import Decimal

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
    # Short timeout: a slow Telegram API must not stall the trading loop.
    _TIMEOUT = 5.0

    def __init__(self, token: str, chat_id: str) -> None:
        """Initialise the notifier with bot credentials.

        Args:
            token:   Telegram Bot API token (obtain from @BotFather).
            chat_id: Target chat or channel ID.  Use a negative integer
                     string for channels (e.g. ``"-100123456789"``).
        """
        self._url = self._API_URL.format(token=token)
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

    async def notify_backtest_started(
        self,
        strategy: str,
        risk_level: str,
        pairs: list[str],
        days: int,
        interval: int,
        capital: Decimal,
        currency_symbol: str = "€",
    ) -> None:
        """Notify that a backtest has started.

        Args:
            strategy:        Strategy name (e.g. ``"momentum"``).
            risk_level:      Risk level (e.g. ``"moderate"``).
            pairs:           Trading pairs being tested.
            days:            Historical look-back in calendar days.
            interval:        Candle width in minutes.
            capital:         Initial capital.
            currency_symbol: Symbol for the base currency (e.g. ``"€"``).
        """
        await self._send(
            f"🔍 <b>Backtest Started</b>\n"
            f"Strategy: {strategy} / {risk_level}\n"
            f"Pairs: {', '.join(pairs)}\n"
            f"Period: {days}d × {interval}min candles\n"
            f"Capital: {currency_symbol}{capital:,.2f}"
        )

    async def notify_backtest_completed(
        self,
        strategy: str,
        risk_level: str,
        days: int,
        total_pnl: Decimal,
        return_pct: float,
        total_trades: int,
        win_rate: float,
        sharpe_ratio: float,
        max_drawdown_pct: float,
        currency_symbol: str = "€",
    ) -> None:
        """Notify that a backtest has completed with its key results.

        Args:
            strategy:         Strategy name.
            risk_level:       Risk level.
            days:             Historical look-back used.
            total_pnl:        Net P&L after fees.
            return_pct:       Return as a percentage of initial capital.
            total_trades:     Number of closed trades.
            win_rate:         Percentage of winning trades.
            sharpe_ratio:     Annualised Sharpe ratio.
            max_drawdown_pct: Maximum drawdown as a percentage of peak equity.
            currency_symbol:  Symbol for the base currency (e.g. ``"€"``).
        """
        pnl_sign = "+" if total_pnl >= 0 else "-"
        ret_sign = "+" if return_pct >= 0 else ""
        await self._send(
            f"{'✅' if total_pnl >= 0 else '❌'} <b>Backtest Completed</b>\n"
            f"Strategy: {strategy} / {risk_level}\n"
            f"Period: {days}d\n"
            f"Net P&amp;L: {pnl_sign}{currency_symbol}{abs(total_pnl):,.2f} "
            f"({ret_sign}{return_pct:.2f}%)\n"
            f"Trades: {total_trades}  Win rate: {win_rate:.1f}%\n"
            f"Sharpe: {sharpe_ratio:.3f}  Max DD: {max_drawdown_pct:.1f}%"
        )

    async def notify_backtest_compare_completed(
        self,
        total_runs: int,
        days: int,
        best_strategy: str,
        best_risk: str,
        best_return_pct: float,
        worst_strategy: str,
        worst_risk: str,
        worst_return_pct: float,
        avg_return_pct: float,
    ) -> None:
        """Notify that a compare or matrix backtest has finished with a summary.

        Sends one message covering all runs — avoids flooding the chat with
        per-run notifications when many strategies are tested at once.

        Args:
            total_runs:       Total number of strategy/risk combinations tested.
            days:             Historical look-back used across all runs.
            best_strategy:    Strategy name with the highest return.
            best_risk:        Risk level of the best run.
            best_return_pct:  Return percentage of the best run.
            worst_strategy:   Strategy name with the lowest return.
            worst_risk:       Risk level of the worst run.
            worst_return_pct: Return percentage of the worst run.
            avg_return_pct:   Average return across all runs.
        """
        avg_sign = "+" if avg_return_pct >= 0 else ""
        await self._send(
            f"📊 <b>Backtest Compare Completed</b>\n"
            f"Runs: {total_runs}  |  Period: {days}d\n"
            f"🏆 Best:  {best_strategy} / {best_risk} → {best_return_pct:+.2f}%\n"
            f"📉 Worst: {worst_strategy} / {worst_risk} → {worst_return_pct:+.2f}%\n"
            f"Avg return: {avg_sign}{avg_return_pct:.2f}%"
        )

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
