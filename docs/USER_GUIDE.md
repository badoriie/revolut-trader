# User Guide

This guide explains how to install, configure, and run the Revolut Trader bot — from a first-time setup through live trading and ongoing monitoring.

> **Risk disclaimer:** Cryptocurrency trading carries significant financial risk. You can lose your entire investment. Always paper-trade first, test on small amounts, and never invest money you cannot afford to lose.

______________________________________________________________________

## Table of Contents

1. [Prerequisites](#1-prerequisites)
1. [Installation](#2-installation)
1. [First-Time Setup](#3-first-time-setup)
1. [Configuring Your Trading Parameters](#4-configuring-your-trading-parameters)
1. [Choosing a Strategy](#5-choosing-a-strategy)
1. [Choosing a Risk Level](#6-choosing-a-risk-level)
1. [Running the Bot](#7-running-the-bot)
1. [Backtesting](#8-backtesting)
1. [Monitoring Performance](#9-monitoring-performance)
1. [Graceful Shutdown](#10-graceful-shutdown)
1. [Telegram Notifications (Optional)](#11-telegram-notifications-optional)
1. [Deploying Unattended (Raspberry Pi / Server)](#12-deploying-unattended-raspberry-pi--server)
1. [Troubleshooting](#13-troubleshooting)
1. [FAQ](#14-faq)
1. [Trading Terminology](#15-trading-terminology)

______________________________________________________________________

## 1. Prerequisites

Before you start, make sure the following are in place.

### Required accounts

| Requirement           | Notes                                                                      |
| --------------------- | -------------------------------------------------------------------------- |
| **Revolut X account** | With API keys generated (sandbox for testing, production for real trading) |
| **1Password account** | Used to store all credentials and configuration securely                   |

### Required software

| Tool                     | Purpose           | Install                                                                     |
| ------------------------ | ----------------- | --------------------------------------------------------------------------- |
| **Python 3.11+**         | Runtime           | [python.org](https://www.python.org/downloads/)                             |
| **uv**                   | Package manager   | `curl -LsSf https://astral.sh/uv/install.sh \| sh`                          |
| **1Password CLI (`op`)** | Credential access | [1Password CLI docs](https://developer.1password.com/docs/cli/get-started/) |
| **Git**                  | Clone the repo    | [git-scm.com](https://git-scm.com/)                                         |

### Verify everything is installed

```bash
python3 --version     # Python 3.11.x or higher
uv --version          # any version
op --version          # any version
git --version         # any version
```

### Revolut X API keys

1. Log in to your Revolut X account
1. Generate an **Ed25519 key pair** (Revolut requires Ed25519 — not RSA):
   ```bash
   openssl genpkey -algorithm Ed25519 -out private_key.pem
   openssl pkey -pubout -in private_key.pem -out public_key.pem
   ```
1. Upload `public_key.pem` to Revolut X (API section of your account settings)
1. Keep `private_key.pem` safe — it goes into 1Password during setup, then can be deleted

______________________________________________________________________

## 2. Installation

```bash
# Clone the repository
git clone https://github.com/badoriie/revolut-trader.git
cd revolut-trader

# Install dependencies
uv sync --extra dev
```

______________________________________________________________________

## 3. First-Time Setup

The setup wizard creates all required 1Password vault items for the three environments (`dev`, `int`, `prod`) and installs Git hooks:

```bash
make setup
```

This single command:

- Creates `revolut-trader-credentials-{dev,int,prod}` items in 1Password
- Creates `revolut-trader-config-{dev,int,prod}` items in 1Password
- Generates and stores Ed25519 keys for `int` and `prod`
- Installs pre-commit hooks
- Runs `uv sync`

> If `make setup` fails, check that `op` is authenticated: run `op whoami` and sign in if prompted.

### Store your API key

After `make setup`, store the Revolut X API credentials for each environment you intend to use:

```bash
# Store credentials for the int (paper trading) environment
make ops ENV=int

# Store credentials for prod (live trading)
make ops ENV=prod
```

You will be prompted for:

- **API Key** — the key ID from Revolut X
- **Private Key** — contents of your `private_key.pem` file

Verify the values were stored correctly:

```bash
make opshow ENV=int
```

______________________________________________________________________

## 4. Configuring Your Trading Parameters

All trading configuration is stored in 1Password under `revolut-trader-config-{env}`. Set each value with:

```bash
make opconfig-set KEY=<key> VALUE=<value> ENV=<env>
```

### Required parameters

| Key                | Valid values                           | Example           | Notes                                                        |
| ------------------ | -------------------------------------- | ----------------- | ------------------------------------------------------------ |
| `RISK_LEVEL`       | `conservative` `moderate` `aggressive` | `conservative`    | See [Choosing a Risk Level](#6-choosing-a-risk-level)        |
| `BASE_CURRENCY`    | `EUR` (and other supported currencies) | `EUR`             | All trading pairs must end with this currency                |
| `TRADING_PAIRS`    | Comma-separated pairs                  | `BTC-EUR,ETH-EUR` | Must match your `BASE_CURRENCY`                              |
| `DEFAULT_STRATEGY` | See strategy names below               | `momentum`        | See [Choosing a Strategy](#5-choosing-a-strategy)            |
| `INITIAL_CAPITAL`  | Positive number                        | `10000`           | Required for `dev` and `int` only; `prod` reads live balance |

### Optional parameters

| Key                          | Default                      | Example         | Notes                                                                                                   |
| ---------------------------- | ---------------------------- | --------------- | ------------------------------------------------------------------------------------------------------- |
| `MAX_CAPITAL`                | *(none — uses full balance)* | `5000`          | Caps the amount used for trading. Useful if your account holds more than you want the bot to trade with |
| `SHUTDOWN_TRAILING_STOP_PCT` | *(none — close immediately)* | `0.5`           | On shutdown, profitable positions wait for a trailing stop of this % before closing                     |
| `SHUTDOWN_MAX_WAIT_SECONDS`  | `120`                        | `180`           | Hard timeout; if the trailing stop has not triggered after this many seconds, force-close the position  |
| `TELEGRAM_BOT_TOKEN`         | *(none — notifications off)* | `123:ABCdef...` | Telegram Bot API token from @BotFather — enables trade and status notifications                         |
| `TELEGRAM_CHAT_ID`           | *(none — notifications off)* | `-100123456789` | Telegram chat or channel ID to send notifications to (both token and ID must be set)                    |

### Example: full configuration for paper trading

```bash
make opconfig-set KEY=RISK_LEVEL            VALUE=conservative     ENV=int
make opconfig-set KEY=BASE_CURRENCY         VALUE=EUR              ENV=int
make opconfig-set KEY=TRADING_PAIRS         VALUE=BTC-EUR,ETH-EUR  ENV=int
make opconfig-set KEY=DEFAULT_STRATEGY      VALUE=momentum         ENV=int
make opconfig-set KEY=INITIAL_CAPITAL       VALUE=10000            ENV=int
make opconfig-set KEY=MAX_CAPITAL           VALUE=5000             ENV=int

# Verify
make opconfig-show ENV=int
```

______________________________________________________________________

## 5. Choosing a Strategy

Six strategies are available, each suited to different market conditions:

| Strategy            | Best market condition            | Trading pace    | Order type | Min confidence |
| ------------------- | -------------------------------- | --------------- | ---------- | -------------- |
| **market_making**   | Stable, high liquidity           | Very fast (5 s) | Limit      | 0.30           |
| **breakout**        | High volatility, price breakouts | Fast (5 s)      | Market     | 0.70           |
| **momentum**        | Trending (up or down)            | Medium (10 s)   | Market     | 0.60           |
| **multi_strategy**  | Mixed / unclear conditions       | Medium (10 s)   | Limit      | 0.55           |
| **mean_reversion**  | Range-bound (oscillating price)  | Slow (15 s)     | Limit      | 0.50           |
| **range_reversion** | Range-bound (uses 24 h high/low) | Slow (15 s)     | Limit      | 0.50           |

### Indicators each strategy uses

| Strategy            | Indicators                                 |
| ------------------- | ------------------------------------------ |
| **market_making**   | Bid-ask spread                             |
| **breakout**        | Rolling high/low, RSI                      |
| **momentum**        | EMA (12/26), RSI                           |
| **multi_strategy**  | Weighted consensus of all other strategies |
| **mean_reversion**  | Bollinger Bands                            |
| **range_reversion** | 24 h high/low range position               |

### Not sure which to choose?

- **Start with `momentum`** — straightforward and well-tested across trending markets.
- **Use `multi_strategy`** if you are unsure about market conditions; it adapts by combining signals.
- Run [backtests](#8-backtesting) to compare strategies on real historical data before committing.

### Per-strategy stop-loss / take-profit

These are applied automatically on top of the risk-level baseline:

| Strategy        | Stop-loss               | Take-profit             |
| --------------- | ----------------------- | ----------------------- |
| market_making   | 0.5%                    | 0.3%                    |
| momentum        | 2.5%                    | 4.0%                    |
| breakout        | 3.0%                    | 5.0%                    |
| mean_reversion  | 1.0%                    | 1.5%                    |
| range_reversion | 1.0%                    | 1.5%                    |
| multi_strategy  | *(risk-level baseline)* | *(risk-level baseline)* |

______________________________________________________________________

## 6. Choosing a Risk Level

The risk level controls how large each position is relative to your portfolio and how much the bot is allowed to lose in a day before it stops trading:

| Level            | Max position size | Max daily loss | Max open positions |
| ---------------- | ----------------- | -------------- | ------------------ |
| **conservative** | 1.5% of portfolio | 3% per day     | 3                  |
| **moderate**     | 3% of portfolio   | 5% per day     | 5                  |
| **aggressive**   | 5% of portfolio   | 10% per day    | 8                  |

**Recommendation:** Start with `conservative`, especially in paper-trading mode. Move to `moderate` only after observing stable performance across multiple backtesting runs and a full week of paper trading.

______________________________________________________________________

## 7. Running the Bot

The recommended way to run the bot is via the `revt` CLI, which is available after `uv sync`. It auto-detects the environment from your git branch (feature branch → `dev`, `main` → `int`, tagged release → `prod`) and can always be overridden with `--env`.

### Mode 1 — Mock trading (no credentials required)

Uses a built-in fake API. Prices are simulated. No 1Password access needed.

```bash
revt run                             # auto-detects dev when on a feature branch
revt run --env dev                   # explicit
```

### Mode 2 — Paper trading (real data, no real trades)

Connects to the real Revolut X API to get live market data but executes all orders as simulations. Your balance is never touched. **This is the recommended mode before going live.**

```bash
revt run --env int
revt run --env int --strategy momentum --risk moderate
```

### Mode 3 — Live trading (real money)

Sends real orders to Revolut X. Requires `prod` credentials in 1Password. You will be prompted to confirm before the bot starts.

```bash
revt run --env prod
```

> **The bot will prompt:** `Type 'I UNDERSTAND' to continue:` — type `I UNDERSTAND` to proceed.

### All `revt run` options

| Flag                 | Values                                                                                    | Notes                                         |
| -------------------- | ----------------------------------------------------------------------------------------- | --------------------------------------------- |
| `--env` / `-e`       | `dev` `int` `prod`                                                                        | Override auto-detected environment            |
| `--strategy` / `-s`  | `market_making` `momentum` `mean_reversion` `multi_strategy` `breakout` `range_reversion` | Override `DEFAULT_STRATEGY`                   |
| `--risk` / `-r`      | `conservative` `moderate` `aggressive`                                                    | Override `RISK_LEVEL` from 1Password          |
| `--pairs` / `-p`     | `BTC-EUR,ETH-EUR,...`                                                                     | Override `TRADING_PAIRS` from 1Password       |
| `--interval` / `-i`  | seconds                                                                                   | Override the strategy's default loop interval |
| `--log-level` / `-l` | `DEBUG` `INFO` `WARNING` `ERROR`                                                          | Verbosity of console output                   |

> **Environment override** — use `make run ENV=dev|int|prod` to force a specific environment instead of auto-detection.

### Stopping the bot

Press `Ctrl-C` — the bot performs a graceful shutdown:

1. Cancels all pending limit orders
1. Closes losing positions immediately at market price
1. Closes profitable positions via trailing stop (if configured) or immediately
1. Saves the final portfolio state to the encrypted database

**Guarantee:** every position opened by the bot is closed before the process exits.

______________________________________________________________________

## 8. Backtesting

Backtesting lets you test a strategy on real historical data before using real money. Results are stored in the encrypted database — no files are written to disk.

### Quick start

```bash
# Test the default strategy over 30 days
revt backtest

# Test a specific strategy and period
revt backtest --strategy momentum --days 90 --risk moderate

# High-frequency test: 1-minute candles (closest to live 5 s polling)
revt backtest --hf --strategy breakout --days 7

# Compare all strategies side-by-side
revt backtest --compare --days 30

# All strategies × all risk levels matrix
revt backtest --matrix --days 30
```

### Available backtest options

| Flag         | Default           | Example                   | Notes                        |
| ------------ | ----------------- | ------------------------- | ---------------------------- |
| `--strategy` | `market_making`   | `--strategy momentum`     | Single strategy name         |
| `--days`     | `30`              | `--days 90`               | Historical window            |
| `--risk`     | `conservative`    | `--risk moderate`         | Risk level                   |
| `--interval` | `60`              | `--interval 15`           | Candle interval in minutes   |
| `--pairs`    | `BTC-EUR,ETH-EUR` | `--pairs BTC-EUR,SOL-EUR` | Trading pairs                |
| `--capital`  | `10000`           | `--capital 5000`          | Starting capital (EUR)       |
| `--hf`       | off               | `--hf`                    | 1-min candles mode           |
| `--compare`  | off               | `--compare`               | All strategies side-by-side  |
| `--matrix`   | off               | `--matrix`                | All strategies × risk levels |

### Valid candle intervals (minutes)

`1`, `5`, `15`, `30`, `60`, `240`, `1440`, `2880`, `5760`, `10080`, `20160`, `40320`

### Understanding the results

After a backtest runs, the output shows:

```
Strategy     : momentum
Risk Level   : conservative
Period       : 30 days  (BTC-EUR, ETH-EUR)
Interval     : 60 min candles

Initial Capital : €10,000.00
Final Capital   : €10,847.50
Total P&L       : €847.50  (+8.48%)
Total Fees      : €12.30
Net P&L         : €835.20

Total Trades    : 42
Winning Trades  : 24  (57.1%)
Losing Trades   : 18
Win Rate        : 57.1%
Profit Factor   : 1.87
Max Drawdown    : €321.00  (3.2%)
Sharpe Ratio    : 1.42
```

| Metric            | What it means                                  | Target                   |
| ----------------- | ---------------------------------------------- | ------------------------ |
| **Return %**      | Percentage gain/loss on initial capital        | Positive                 |
| **Win Rate**      | Percentage of trades that were profitable      | > 50%                    |
| **Profit Factor** | Gross profit ÷ gross loss                      | > 1.5 (excellent: > 2.0) |
| **Sharpe Ratio**  | Risk-adjusted return                           | > 1.0 (strong: > 1.5)    |
| **Max Drawdown**  | Largest peak-to-trough decline                 | Lower is better          |
| **Total Fees**    | 0.09% taker fees deducted (market orders only) | Part of net P&L          |

### Viewing past backtest results

```bash
revt db backtests            # recent results (default: last 10)
revt db backtests --limit 20 # last 20 results
revt db export               # export all results to CSV
```

### Simulation accuracy

The backtesting engine mirrors the live bot as closely as possible:

- **Taker fees:** 0.09% deducted on every market order fill (limit orders: 0%)
- **Spread:** BUY at ask price, SELL at bid price (approx. 0.1% cost)
- **Signal filters:** same per-strategy confidence thresholds as live
- **SL/TP:** checked against candle high/low each bar (intra-bar detection)
- **Order type:** MARKET for momentum/breakout, LIMIT for all others

> Note: 1-minute candles are the finest granularity available from the API. The live bot polls every 5 seconds, so very short-lived price moves may not appear in backtests.

### Best practices

1. **Test multiple time windows** — 30, 90, 180 days — to check consistency
1. **Compare strategies** side-by-side with `make backtest-compare`
1. **Try all risk levels** with `make backtest-matrix` before choosing
1. **Use out-of-sample testing** — backtest on a period you did not use to choose the strategy
1. **Watch the fees** — a high trade count can eat into profits even with a high win rate

______________________________________________________________________

## 9. Monitoring Performance

All data is stored in an encrypted SQLite database (`data/dev.db`, `data/int.db`, `data/prod.db`).

```bash
make db               # overview: stats + recent analytics + backtest summary
make db-stats         # database statistics (snapshot count, last trade)
make db-analytics     # trading analytics (default: last 30 days)
make db-analytics DAYS=7   # last 7 days
make db-backtests     # list recent backtest runs with metrics
make db-export-csv    # export trades and snapshots to CSV files
make db-report        # comprehensive analytics report with charts (default: last 30 days)
make db-report DAYS=7 DIR=data/reports  # custom window and output directory
```

The basic `db-analytics` report shows:

- Total trades and win rate
- Total P&L and fees
- Portfolio return percentage over the period

### Comprehensive analytics report

`make db-report` produces a deeper analysis of all data in the database:

```bash
# Install chart dependencies first (one-time):
uv sync --extra analytics

# Generate the report (saves to data/reports/):
make db-report DAYS=30
```

The report includes:

- **Core metrics**: win rate, total P&L, return %, fees, Sharpe ratio, Sortino ratio, max drawdown, profit factor
- **Per-symbol breakdown**: trade count, win rate, P&L, and fee totals for every traded pair
- **Per-strategy breakdown**: same metrics grouped by strategy for live/paper trades
- **Backtest summary**: best strategy, success rate, and average return across all stored backtest runs
- **Improvement suggestions**: rule-based observations flagging low win rates, high fee drag, excessive drawdown, weak Sharpe, and consistently losing symbols
- **Charts** (requires `--extra analytics`):
  - `equity_curve.png` — portfolio value over time
  - `drawdown.png` — peak-to-trough drawdown percentage
  - `pnl_distribution.png` — histogram of individual trade P&Ls
  - `symbol_performance.png` — P&L bar chart by trading pair
  - `backtest_comparison.png` — best backtest return by strategy

A `report.md` markdown file is also written to the output directory, making it easy to paste into GitHub Actions job summaries or share with collaborators. If Telegram is configured and `fpdf2` is installed (included in `--extra analytics`), a PDF version of the report is sent directly to your Telegram chat; otherwise a compact text summary is sent.

### Verifying encryption

```bash
make db-encrypt-status
```

If encryption is not active, run `make db-encrypt-setup` to generate and store an encryption key in 1Password.

______________________________________________________________________

## 10. Graceful Shutdown

Press `Ctrl-C` at any time to stop the bot safely. The shutdown sequence is:

1. **Cancel orders** — all pending limit orders are cancelled via the API
1. **Close losing positions** — closed immediately at market price
1. **Close profitable positions** — if `SHUTDOWN_TRAILING_STOP_PCT` is set, the bot waits for the price to retreat by that percentage from its peak before closing; otherwise, positions are closed immediately
1. **Hard timeout** — if a trailing stop has not triggered within `SHUTDOWN_MAX_WAIT_SECONDS` (default: 120 s), the position is force-closed

Configure trailing stop on shutdown:

```bash
# Wait for a 0.5% pullback from peak before closing profitable positions
make opconfig-set KEY=SHUTDOWN_TRAILING_STOP_PCT VALUE=0.5 ENV=int

# Force-close after 3 minutes if trailing stop never triggers
make opconfig-set KEY=SHUTDOWN_MAX_WAIT_SECONDS VALUE=180 ENV=int
```

______________________________________________________________________

## 11. Telegram Notifications (Optional)

The bot can send real-time notifications to a Telegram chat whenever a trade executes, the bot starts or stops, a critical error occurs, or the daily loss limit is hit. When `make db-report` runs, a PDF analytics report is sent to Telegram (requires `--extra analytics` for `fpdf2`); if fpdf2 is not installed, a text summary is sent instead.

While the bot is running it also **listens for commands** you send directly in the chat, giving you on-demand access to live status and analytics without touching the server.

### Set up a bot

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
1. Send `/newbot` and follow the prompts — copy the **API token** you receive
1. Send a message to your new bot (needed to open the chat)
1. Retrieve your **chat ID**:
   ```bash
   curl "https://api.telegram.org/bot<TOKEN>/getUpdates"
   # Look for "chat":{"id": ...} in the response
   ```
   For a private channel, add the bot as admin and use the channel's negative ID (e.g. `-100123456789`).

### Store credentials in 1Password

The bot token is stored as a concealed credential via `make ops`; the chat ID is stored as a config value:

```bash
make ops ENV=prod                                          # prompts for Revolut API key and Telegram bot token
make opconfig-set KEY=TELEGRAM_CHAT_ID VALUE=<chat_id> ENV=prod
```

Both keys must be set — if either is missing, notifications are silently disabled.

### What you receive

| Event                  | Message                                                              |
| ---------------------- | -------------------------------------------------------------------- |
| Bot started            | Strategy, risk level, pairs, mode                                    |
| Order filled           | Side, symbol, quantity, price, fee, P&L (sells)                      |
| Shutdown complete      | Session ID, total realized P&L                                       |
| Analytics report ready | PDF file with key metrics (fpdf2 installed) or text summary fallback |
| Daily loss limit hit   | Current day P&L, suspended notice                                    |
| Critical error         | Error description                                                    |

### Bot commands (while the bot is running)

Send these commands to your bot in Telegram at any time while the bot is running:

| Command          | Response                                                                                        |
| ---------------- | ----------------------------------------------------------------------------------------------- |
| `/status`        | Strategy, risk level, mode, pairs, uptime, open positions, session P&L                          |
| `/balance`       | Cash balance, open positions with entry price and unrealised P&L, total portfolio value         |
| `/report [days]` | Analytics summary for the last N days (default 30): trades, win rate, net P&L, Sharpe, drawdown |
| `/help`          | List of available commands                                                                      |

The bot ignores commands from any chat other than the configured `TELEGRAM_CHAT_ID`.

Telegram failures never affect trading — errors are logged and discarded.

### Telegram Control Plane — start, stop, and monitor from Telegram

The **Telegram Control Plane** is an always-on background process that lets you control the trading bot entirely through Telegram commands — even when the bot is not running. Start it once and leave it running; all bot lifecycle management happens from your phone.

```bash
make telegram                  # start the control plane (env auto-detected)
make telegram ENV=prod         # force production environment

revt telegram start            # same via the revt binary
revt telegram start --env int  # paper trading
```

Additional commands available only through the control plane:

| Command                  | Response                                                                  |
| ------------------------ | ------------------------------------------------------------------------- |
| `/run`                   | Start the trading bot with default strategy and risk                      |
| `/run momentum moderate` | Start with a specific strategy and risk level                             |
| `/run BTC-EUR,ETH-EUR`   | Start trading specific pairs                                              |
| `/stop`                  | Gracefully stop the bot (cancels orders, closes positions, saves state)   |
| `/status`                | Bot status (delegates to running bot, or "not running" when idle)         |
| `/balance`               | Cash and positions (delegates to running bot, or "not running" when idle) |
| `/report [days]`         | Analytics (delegates to running bot, or queries database when idle)       |
| `/help`                  | List all available commands                                               |

The control plane and `make run` cannot both run at the same time with Telegram configured — both would try to read the same Telegram updates. Use either:

- `make run` — start the bot directly (command listener active while running), **or**
- `make telegram` — start the control plane and use `/run` to start/stop the bot

______________________________________________________________________

## 12. Deploying Unattended (Raspberry Pi / Server)

See [Raspberry Pi Deployment](RASPBERRY_PI_DEPLOYMENT.md) for the complete guide.

### Quick summary

**Supported hardware:** Raspberry Pi 3/4/5 with a 64-bit OS (ARM64). Pi Zero and Pi 2 are not supported.

**Authentication:** Use a 1Password service account:

```bash
# Add to ~/.bashrc
export OP_SERVICE_ACCOUNT_TOKEN=ops_xxxx...
```

**Run as a systemd service** for automatic startup and restart on failure:

```ini
# /etc/systemd/system/revolut-trader.service
[Unit]
Description=Revolut Trader Bot
After=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/revolut-trader
Environment=OP_SERVICE_ACCOUNT_TOKEN=ops_xxxx...
ExecStart=/home/pi/revolut-trader/.venv/bin/python cli/run.py
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable revolut-trader
sudo systemctl start revolut-trader
sudo systemctl status revolut-trader
```

______________________________________________________________________

## 13. Troubleshooting

### API connection issues

```bash
make opstatus           # check 1Password CLI is authenticated
make opshow ENV=int     # verify credentials are stored
make api-test ENV=int   # test the Revolut X connection
make api-ready ENV=int  # check view + trade permissions
```

### "1Password is required but not available"

The CLI is not signed in. Run:

```bash
op signin
# or for service accounts:
export OP_SERVICE_ACCOUNT_TOKEN=ops_xxxx...
op whoami
```

### "Config field missing" errors

A required 1Password config key is missing. The error message tells you which key and which `make opconfig-set` command to run to fix it. Example:

```
RuntimeError: INITIAL_CAPITAL is required for paper mode.
Fix: make opconfig-set KEY=INITIAL_CAPITAL VALUE=10000 ENV=int
```

### "No signals generated"

Strategies need a warm-up period to build indicator history (typically 10–30 trading loop iterations). Wait a minute or two. If signals never appear:

- Check `--log-level DEBUG` for details
- Verify your trading pairs are active: `make api-currency-pairs ENV=int`
- Ensure your pairs match your `BASE_CURRENCY`

### Currency mismatch error

All pairs must end with your `BASE_CURRENCY`. If `BASE_CURRENCY=EUR`:

```bash
# Wrong:
make opconfig-set KEY=TRADING_PAIRS VALUE=BTC-USD,ETH-USD ENV=int

# Correct:
make opconfig-set KEY=TRADING_PAIRS VALUE=BTC-EUR,ETH-EUR ENV=int
```

### Live trading is not available

Your API key must have **Trade** permission. Check:

```bash
make api-ready ENV=prod
```

If the output shows `Trade (place orders): FAIL`, re-generate your Revolut X API key with trading permission and re-run `make ops ENV=prod`.

### Candle interval invalid

Use only supported intervals (in minutes): `1`, `5`, `15`, `30`, `60`, `240`, `1440`, `2880`, `5760`, `10080`, `20160`, `40320`.

______________________________________________________________________

## 14. FAQ

**Q: Do I need the 1Password CLI for mock trading?**
No. `make run` (on a feature branch) or `revt run --env dev` uses a built-in simulated API with no credentials at all.

**Q: Can I run multiple strategies at the same time?**
The bot runs one strategy at a time. Use `multi_strategy` to get the benefits of multiple strategies in a single run — it combines signals from all strategies with weighted voting.

**Q: What happens if the bot crashes mid-trade?**
On the next start, the bot reads its position state from the database and resumes. Any positions tracked in the database will be included in the graceful shutdown sequence when you next stop the bot.

**Q: How do I limit how much money the bot trades with?**
Set `MAX_CAPITAL`. Even if your account holds €50,000, you can limit the bot to trading with only €5,000:

```bash
make opconfig-set KEY=MAX_CAPITAL VALUE=5000 ENV=prod
```

**Q: Are fees included in backtest results?**
Yes. Market orders are charged 0.09% taker fee. Limit orders are 0%. All fees are deducted from the P&L and shown in the summary under "Total Fees".

**Q: How do I see what the bot is doing in real time?**
Run with `--log-level INFO` (the default). For more detail, use `--log-level DEBUG`. Logs are also written to the encrypted database and can be reviewed later.

**Q: How often does the bot trade?**
It depends on the strategy:

- Fast strategies (market_making, breakout): every 5 seconds
- Medium strategies (momentum, multi_strategy): every 10 seconds
- Slow strategies (mean_reversion, range_reversion): every 15 seconds

These are overridable with `--interval <seconds>`.

**Q: Can I test the API without running the bot?**
Yes. Use the API testing commands:

```bash
make api-balance ENV=int
make api-ticker SYMBOL=BTC-EUR ENV=int
make api-order-book SYMBOL=BTC-EUR ENV=int
```

**Q: What is pre-existing crypto protection?**
The bot will never sell a cryptocurrency it did not purchase itself. If you hold BTC in your account from before you started the bot, the bot will not touch it.

**Q: Which environments use real money?**
Only `prod` (`make run ENV=prod` / `revt run`). Both `dev` and `int` are paper-trading only — no real orders are ever placed.

______________________________________________________________________

## 15. Trading Terminology

Plain-language definitions for every term that appears in this app's configuration, output, or reports. No prior trading knowledge needed.

______________________________________________________________________

### Portfolio & Positions

**Trading pair** (`TRADING_PAIRS`)
Written as `BASE-QUOTE` — for example `BTC-EUR`. The bot buys and sells the left side (BTC) using the right side (EUR) as the payment currency. All pairs in this app must end in your `BASE_CURRENCY`.

**Portfolio**
Everything the bot manages: your cash (EUR) plus the current value of any open holdings. Shown as **Total Value** in analytics output.

**Capital** (`INITIAL_CAPITAL`, `MAX_CAPITAL`)
The EUR the bot is allowed to trade with. `INITIAL_CAPITAL` sets the starting amount for paper/mock mode. `MAX_CAPITAL` caps spending even if your account holds more — useful when you want the bot to use only a portion of your balance.

**Position**
An active holding in one asset. When the bot buys BTC, it opens a BTC position. When it sells, it closes the position and returns to EUR.

**P&L (Profit and Loss)**
The money made or lost. Shown throughout the app as `Total P&L`, `Daily P&L`, etc.

- **Realised P&L** — locked-in gain or loss from already-closed positions. This is in your cash balance.
- **Unrealised P&L** — the paper gain or loss on positions you still hold. It changes every time the price moves and only becomes real when you sell.

**Return %**
Total gain or loss as a percentage of starting capital. `+8.5%` on €10,000 means you made €850.

**Fee**
The cost Revolut X charges per trade. Market orders: **0.09%** of the trade value. Limit orders: **0%**. Fees are deducted from your P&L and shown as `Total Fees` in every report.

______________________________________________________________________

### Orders & Signals

**Market order**
Executes immediately at the current market price. Guarantees a fast fill but costs the 0.09% taker fee. Used by `momentum` and `breakout` strategies where speed matters.

**Limit order**
Executes only at a price you specify (or better). Has no fee (0% maker). May not fill immediately. Used by `mean_reversion`, `range_reversion`, `market_making`, and `multi_strategy`.

**Spread**
The built-in gap between the buy price and sell price on any exchange. The backtesting engine models this as ~0.1% — meaning backtests deduct this cost on every trade to stay realistic.

**Signal**
The decision a strategy produces each loop: buy, sell, or do nothing. Comes with a confidence score between 0 and 1.

**Signal strength** (min confidence threshold)
How confident the strategy is in its signal. Each strategy has a minimum threshold — signals below it are discarded without placing an order. This prevents the bot from trading on weak, unreliable signals.

**Candle / interval** (`INTERVAL` in backtests)
A candle summarises price activity over a fixed time window: opening price, highest price, lowest price, closing price. The `INTERVAL` parameter sets how long each candle covers (in minutes). A 60-minute interval means the bot looks at one-hour snapshots of price data. Shorter intervals give more signals but more noise; longer intervals give cleaner trends but fewer trades.

______________________________________________________________________

### Indicators (used by the strategies)

The strategies use these calculations on recent price history to decide when to buy or sell. They are selected automatically by the strategy — you do not configure them directly.

| Indicator                            | Used by                | What it does                                                                                                                                                                                |
| ------------------------------------ | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **EMA** (Exponential Moving Average) | `momentum`             | Tracks the average price with more weight on recent data. A fast EMA crossing above a slow EMA suggests upward momentum.                                                                    |
| **RSI** (Relative Strength Index)    | `momentum`, `breakout` | A 0–100 score measuring how fast the price has been moving. Above 70 suggests the price may be overextended; below 30 suggests it may be undervalued.                                       |
| **Bollinger Bands**                  | `mean_reversion`       | Three lines around the price: a middle average and upper/lower boundaries. When price touches the upper band it may be stretched too high; lower band too low — both can signal a reversal. |

______________________________________________________________________

### Risk Controls

**Stop-loss** (per-strategy %, e.g. `2.5%`)
A safety exit. If a position's loss reaches this percentage, the bot sells immediately. For example, buying BTC at €50,000 with a 2.5% stop-loss means the bot sells automatically if the price drops to €48,750 — capping the loss.

**Take-profit** (per-strategy %, e.g. `4.0%`)
A gain-locking exit. When a position's profit reaches this percentage, the bot sells to secure the gain. With a 4% take-profit on the same BTC purchase, the bot sells at €52,000.

**Trailing stop** (`SHUTDOWN_TRAILING_STOP_PCT`)
A stop-loss that follows the price upward but never moves down. Used only during bot shutdown for profitable positions. If BTC rises to €55,000 and you set a 0.5% trailing stop, the bot waits until the price pulls back 0.5% from its peak (€54,725) before selling — locking in most of the gain rather than selling immediately.

**Position size** (set by `RISK_LEVEL`)
How much of your portfolio is committed to a single trade, as a percentage. Conservative: 1.5%, Moderate: 3%, Aggressive: 5%. Smaller = less risk per trade.

**Max daily loss** (set by `RISK_LEVEL`)
A daily circuit breaker. Once cumulative losses hit this percentage of the portfolio, the bot stops opening new trades for the rest of the day. Conservative: 3%, Moderate: 5%, Aggressive: 10%.

**Max open positions** (set by `RISK_LEVEL`)
The maximum number of different assets the bot holds at once. Conservative: 3, Moderate: 5, Aggressive: 8.

______________________________________________________________________

### Performance Metrics

Appear in backtest results (`make db-backtests`) and the analytics report (`make db-report`).

**Win rate**
Percentage of closed trades that made money. 24 wins out of 42 trades = 57% win rate. Always read alongside profit factor — a high win rate with tiny gains and large losses is still a losing strategy.

**Profit factor**
Total profit from winning trades ÷ total loss from losing trades. `1.87` means you earned €1.87 for every €1 lost. Above 1.0 = net profitable. Above 1.5 = solid. Above 2.0 = excellent.

**Max drawdown**
The largest peak-to-trough fall in portfolio value over a period, as a percentage. If your portfolio hit €11,500 then dropped to €10,350 before recovering, the drawdown was 10%. It shows the worst stretch you would have had to sit through. Lower is better.

**Sharpe ratio**
Return relative to overall volatility — "how much am I earning per unit of risk?" Higher is better.

| Value     | Meaning                         |
| --------- | ------------------------------- |
| Below 0   | Losing on a risk-adjusted basis |
| 0 – 0.5   | Weak                            |
| 0.5 – 1.0 | Acceptable                      |
| 1.0 – 2.0 | Good                            |
| Above 2.0 | Excellent                       |

**Sortino ratio**
Like Sharpe, but only penalises downward volatility (losses). Upward swings are not counted against the strategy. A Sortino higher than Sharpe means the strategy's volatility comes mostly from gains, not losses — which is a good sign.

**Equity curve**
The `equity_curve.png` chart in `make db-report`. A line showing portfolio total value over time. Steadily rising = healthy. Flat or declining = investigate.

______________________________________________________________________

### Bot Modes & Environments

**Mock mode** (`make run ENV=dev` / `revt run --env dev`, `ENVIRONMENT=dev`)
Fully simulated — fake prices, no API calls, no credentials needed. Use it to explore the interface and test configuration changes without connecting to anything.

**Paper trading** (`make run ENV=int` / `revt run --env int`, `ENVIRONMENT=int`)
Real live market data from Revolut X, but all orders are simulated in software. Your balance is never touched. Always paper-trade before going live.

**Live trading** (`make run ENV=prod` / `revt run`, `ENVIRONMENT=prod`)
Real orders sent to Revolut X. Real money. Requires prod credentials in 1Password and an explicit confirmation prompt.

**Backtesting** (`make backtest`, `make backtest-compare`)
Replaying a strategy against historical candle data to estimate how it would have performed. The engine applies the same fees, spread, stop-loss/take-profit logic, and signal filters as the live bot, so results are as realistic as possible.

**Session**
One complete run of the bot from start to graceful shutdown. The database records each session with its start time, end time, total trades, and final balance — visible in `make db-stats`.
