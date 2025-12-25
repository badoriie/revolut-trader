from typing import Optional

from loguru import logger
from telegram import Bot
from telegram.error import TelegramError

from src.config import settings
from src.data.models import Order, Position, Signal


class TelegramNotifier:
    """Send trading notifications via Telegram."""

    def __init__(
        self, bot_token: Optional[str] = None, chat_id: Optional[str] = None
    ):
        self.enabled = settings.enable_telegram
        self.bot_token = bot_token or settings.telegram_bot_token
        self.chat_id = chat_id or settings.telegram_chat_id
        self.bot: Optional[Bot] = None

        if self.enabled:
            if not self.bot_token or not self.chat_id:
                logger.warning(
                    "Telegram notifications enabled but credentials not provided. Disabling."
                )
                self.enabled = False
            else:
                self.bot = Bot(token=self.bot_token)
                logger.info("Telegram notifier initialized")

    async def send_message(self, message: str, parse_mode: str = "Markdown"):
        """Send a message to Telegram."""
        if not self.enabled:
            return

        try:
            await self.bot.send_message(
                chat_id=self.chat_id, text=message, parse_mode=parse_mode
            )
        except TelegramError as e:
            logger.error(f"Failed to send Telegram message: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error sending Telegram message: {str(e)}")

    async def notify_signal(self, signal: Signal):
        """Notify about a trading signal."""
        message = f"""
🔔 *Trading Signal*

Symbol: `{signal.symbol}`
Strategy: `{signal.strategy}`
Action: *{signal.signal_type}*
Strength: {signal.strength:.1%}
Price: ${signal.price}

Reason: {signal.reason}
"""
        await self.send_message(message)

    async def notify_order(self, order: Order):
        """Notify about order execution."""
        emoji = "✅" if order.status.value == "FILLED" else "⏳"
        message = f"""
{emoji} *Order {order.status.value}*

ID: `{order.order_id}`
Symbol: `{order.symbol}`
Side: *{order.side.value}*
Quantity: {order.quantity}
Price: ${order.price}
Strategy: {order.strategy}
"""
        await self.send_message(message)

    async def notify_position_update(self, position: Position, action: str):
        """Notify about position updates."""
        emoji = "📈" if position.side.value == "BUY" else "📉"
        message = f"""
{emoji} *Position {action}*

Symbol: `{position.symbol}`
Side: {position.side.value}
Quantity: {position.quantity}
Entry Price: ${position.entry_price}
Current Price: ${position.current_price}
Unrealized P&L: ${position.unrealized_pnl} ({(position.unrealized_pnl / (position.entry_price * position.quantity) * 100):.2f}%)

Stop Loss: ${position.stop_loss}
Take Profit: ${position.take_profit}
"""
        await self.send_message(message)

    async def notify_error(self, error_msg: str):
        """Notify about errors."""
        message = f"""
⚠️ *Error Alert*

{error_msg}
"""
        await self.send_message(message)

    async def notify_daily_summary(
        self, total_pnl: float, win_rate: float, num_trades: int
    ):
        """Send daily trading summary."""
        pnl_emoji = "💰" if total_pnl >= 0 else "📉"
        message = f"""
{pnl_emoji} *Daily Trading Summary*

Total P&L: ${total_pnl:.2f}
Win Rate: {win_rate:.1%}
Number of Trades: {num_trades}

Keep up the good work! 🚀
"""
        await self.send_message(message)

    async def notify_risk_alert(self, alert_msg: str):
        """Send risk management alerts."""
        message = f"""
🚨 *RISK ALERT*

{alert_msg}

Action may be required!
"""
        await self.send_message(message)
