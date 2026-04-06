# Revolut Trader — End User Guide

Welcome! This guide is for **end users** who want to run the Revolut Trader bot with minimal setup. No coding or developer steps required.

> **Risk disclaimer:** Cryptocurrency trading carries significant financial risk. You can lose your entire investment. Always paper-trade first, test on small amounts, and never invest money you cannot afford to lose.

______________________________________________________________________

## 1. Download the Bot

### Quick Install (One-Liner)

**Linux x86_64:**

```bash
curl -L https://github.com/badoriie/revolut-trader/releases/latest/download/revt-linux-x86_64 -o revt && chmod +x revt && sudo mv revt /usr/local/bin/
```

**Raspberry Pi / ARM64:**

```bash
curl -L https://github.com/badoriie/revolut-trader/releases/latest/download/revt-linux-arm64 -o revt && chmod +x revt && sudo mv revt /usr/local/bin/
```

Verify installation:

```bash
revt --version
```

### Manual Installation

1. Go to the [latest GitHub Release](https://github.com/badoriie/revolut-trader/releases)

1. Download the `revt` binary for your system:

   - Linux x86_64: `revt-linux-x86_64`
   - Raspberry Pi / ARM64: `revt-linux-arm64`
   - **No macOS binary** — macOS is for development only

1. Make it executable:

   ```bash
   chmod +x revt-linux-x86_64
   # or for ARM64
   chmod +x revt-linux-arm64
   ```

1. Move it to your PATH:

   ```bash
   sudo mv revt-linux-x86_64 /usr/local/bin/revt
   # or for ARM64
   sudo mv revt-linux-arm64 /usr/local/bin/revt
   ```

______________________________________________________________________

## 2. Set Up 1Password

All credentials and trading settings are securely stored in 1Password.

### Install 1Password CLI

**Linux (x86_64):**

```bash
curl -sS https://downloads.1password.com/linux/debian/amd64/stable/1password-cli-amd64-latest.deb -o op.deb
sudo dpkg -i op.deb && rm op.deb
op --version
```

**Raspberry Pi (ARM64):**

```bash
curl -sS https://downloads.1password.com/linux/debian/arm64/stable/1password-cli-arm64-latest.deb -o op.deb
sudo dpkg -i op.deb && rm op.deb
op --version
```

### Set Up Service Account

For unattended operation (servers, Raspberry Pi), use a service account:

1. Go to [1Password.com](https://1password.com) → your account → **Integrations** → **Service Accounts**

1. Click **New Service Account**, name it (e.g. `revolut-trader-server`)

1. Grant it access to the `revolut-trader` vault:

   - **Read** — required
   - **Write** — optional (only if configuring from the server)

1. Copy the token (shown only once)

1. Store it:

   ```bash
   echo 'export OP_SERVICE_ACCOUNT_TOKEN=ops_xxxx...' >> ~/.bashrc
   source ~/.bashrc
   op whoami  # verify
   ```

______________________________________________________________________

## 3. Initialize Configuration

Create the configuration with safe defaults:

```bash
revt ops init
```

This creates:

- `TRADING_MODE = paper` (safe default — no real money)
- `RISK_LEVEL = conservative`
- `BASE_CURRENCY = EUR`
- `TRADING_PAIRS = BTC-EUR,ETH-EUR`
- `INITIAL_CAPITAL = 10000` (for paper mode)

View your settings:

```bash
revt config show
```

Customize as needed:

```bash
revt config set TRADING_PAIRS BTC-EUR,ETH-EUR,SOL-EUR
revt config set RISK_LEVEL moderate
revt config set MAX_CAPITAL 5000  # cap trading at €5,000
```

______________________________________________________________________

## 4. Set Up Telegram (Optional, but Recommended)

Get notifications and control the bot from your phone:

1. Create a bot with [@BotFather](https://t.me/BotFather) → get token

1. **Set up bot commands** (in @BotFather, select your bot and run `/setcommands`, then paste):

   ```
   run - Start the trading bot (optional: strategy, risk, pairs)
   stop - Stop the trading bot gracefully
   status - Show bot status and session P&L
   balance - Show cash balance and open positions
   report - Generate analytics report (optional: days, default 30)
   backtest - Run a backtest (optional: strategy, risk, days, pairs)
   help - Show list of available commands
   ```

   This enables autocomplete in Telegram when typing `/`.

1. Get your chat ID with [@getidsbot](https://t.me/getidsbot)

1. Store them:

   ```bash
   revt ops                              # enter bot token when prompted
   revt config set TELEGRAM_CHAT_ID 123456789
   ```

1. Test:

   ```bash
   revt telegram test
   ```

### Telegram Commands

- `/run` — start the bot
- `/stop` — graceful shutdown
- `/status` — current status and P&L
- `/balance` — account balance and positions
- `/report [days]` — analytics summary
- `/backtest [strategy] [risk] [days] [pairs,...]` — run a backtest
- `/help` — command list

______________________________________________________________________

## 5. Start Trading

### Paper Trading (Safe, No Real Money)

The bot defaults to paper mode — no configuration needed:

```bash
revt run
```

This uses real market data but simulates all trades (no real money).

### Live Trading (Real Money)

**⚠️ WARNING**: Live mode uses real funds. Only enable after thorough testing in paper mode.

**Before enabling:**

- [ ] Paper-traded successfully for at least 7 days
- [ ] Reviewed all trades and verified strategy performance
- [ ] Set `MAX_CAPITAL` to limit exposure (e.g., 5000 EUR)
- [ ] Understand you can lose your entire investment

**Enable live mode:**

```bash
revt config set TRADING_MODE live
```

**Start the bot:**

```bash
revt run
```

You'll be prompted to type **"I UNDERSTAND"** before it starts.

**Go back to paper mode:**

```bash
revt config set TRADING_MODE paper
```

______________________________________________________________________

## 6. Running Unattended (24/7)

### Option A: Systemd Service (Recommended)

Create `/etc/systemd/system/revolut-trader.service`:

```ini
[Unit]
Description=Revolut Trader Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi
Environment=OP_SERVICE_ACCOUNT_TOKEN=ops_xxxx...
ExecStart=/home/pi/revt run
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable revolut-trader
sudo systemctl start revolut-trader
sudo systemctl status revolut-trader
```

View logs:

```bash
sudo journalctl -u revolut-trader -f
```

### Option B: Telegram Control Plane

Run the control plane continuously — control trading via Telegram:

```bash
revt telegram start --env prod
```

Then use `/run` and `/stop` commands in Telegram.

______________________________________________________________________

## 7. Monitoring

### Database Analytics

```bash
revt db stats --env prod                # overview
revt db analytics --days 30 --env prod  # trading metrics
revt db report --days 60 --env prod     # full report with charts
```

### Logs

```bash
revt logs --env prod --limit 100
```

### Telegram Notifications

Real-time alerts for:

- Trades opened/closed
- Stop-loss/take-profit triggers
- Daily P&L summaries
- Errors and warnings

______________________________________________________________________

## 8. Updating

To update to the latest version:

```bash
revt update
```

This downloads the latest binary while preserving your data and configuration.

Verify:

```bash
revt --version
```

______________________________________________________________________

## Troubleshooting

### 1Password Issues

**Authentication fails:**

```bash
echo $OP_SERVICE_ACCOUNT_TOKEN  # check it's set
op whoami                        # verify
```

**Config not found:**

```bash
revt ops init  # create with defaults
```

### Bot Won't Start

Check configuration:

```bash
revt config show --env prod
revt ops --show --env prod
```

Common issues:

- TRADING_PAIRS don't match BASE_CURRENCY (must be `BTC-EUR` not `BTC-USD`)
- INITIAL_CAPITAL not set (required for paper mode)
- REVOLUT_API_KEY not stored (required for live mode)

### Telegram Not Working

```bash
revt telegram test --env prod
```

Both `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` must be set.

### Raspberry Pi Specific

**Architecture mismatch:**

```bash
uname -m  # must return "aarch64"
```

If it returns `armv7l`, reinstall with a 64-bit OS.

**1Password CLI not found:**

- Download the ARM64 version (not x86_64)
- Use installation steps from section 2

______________________________________________________________________

## Supported Hardware

| Device                  | Architecture | Supported                           |
| ----------------------- | ------------ | ----------------------------------- |
| Linux x86_64            | AMD64        | ✓ Yes                               |
| Raspberry Pi 4 / 5      | ARM64        | ✓ Yes                               |
| Raspberry Pi 3 (64-bit) | ARM64        | ✓ Yes (use Pi OS Lite 64-bit)       |
| Raspberry Pi 3 (32-bit) | ARMv7        | ✗ No (1Password CLI requires ARM64) |
| Raspberry Pi Zero / 2   | ARMv6/ARMv7  | ✗ No                                |

______________________________________________________________________

For developer documentation, see [`DEVELOPMENT_GUIDELINES.md`](DEVELOPMENT_GUIDELINES.md).
