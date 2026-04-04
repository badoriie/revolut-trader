# Telegram Bot Commands Setup

This file contains the exact command list to paste into @BotFather when setting up your Revolut Trader Telegram bot.

## Quick Setup

1. Open Telegram and go to [@BotFather](https://t.me/BotFather)
1. Select your bot (or create a new one with `/newbot`)
1. Send `/setcommands` to BotFather
1. Select your bot from the list
1. Copy and paste the command list below:

## Command List

```
run - Start the trading bot (optional: strategy, risk, pairs)
stop - Stop the trading bot gracefully
status - Show bot status and session P&L
balance - Show cash balance and open positions
report - Generate analytics report (optional: days, default 30)
help - Show list of available commands
```

## What This Does

Setting up these commands enables:

- **Command autocomplete** — when users type `/` in the chat, they see all available commands
- **Command descriptions** — each command shows a helpful description
- **Better UX** — no need to remember or look up command syntax

## Available Commands (Details)

| Command          | Description                                                           | Usage                      |
| ---------------- | --------------------------------------------------------------------- | -------------------------- |
| `/run`           | Start the trading bot with optional parameters                        | `/run momentum aggressive` |
| `/stop`          | Stop the trading bot gracefully (closes positions, saves state)       | `/stop`                    |
| `/status`        | Show bot status, uptime, open positions, and session P&L              | `/status`                  |
| `/balance`       | Show cash balance, open positions with entry price and unrealized P&L | `/balance`                 |
| `/report [days]` | Generate analytics report (PDF or text) for the last N days           | `/report 30`               |
| `/help`          | Show list of available commands                                       | `/help`                    |

## Notes

- These commands work with both the standalone bot (`revt run`) and the Telegram Control Plane (`revt telegram start`)
- The Control Plane owns the polling loop and allows you to `/run` and `/stop` the trading bot remotely
- When running the bot directly (`revt run`), only status/balance/report commands are available
- All commands are secured to the configured `TELEGRAM_CHAT_ID` — other users cannot control your bot

## Full Setup Guide

See the complete setup instructions in:

- [1PASSWORD.md](1PASSWORD.md#telegram-integration) — Credential storage
- [END_USER_GUIDE.md](END_USER_GUIDE.md#4-set-up-telegram-optional-but-recommended) — Quick start
- [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md#11-telegram-notifications-optional) — Advanced usage
