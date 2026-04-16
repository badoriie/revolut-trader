# 1Password Setup & Configuration

All credentials and trading configuration are stored exclusively in 1Password.
No `.env` files, no code defaults, no local credential storage.

______________________________________________________________________

## Prerequisites

### Install 1Password CLI

**macOS:**

```bash
brew install --cask 1password-cli
op --version
```

**Linux / Raspberry Pi (ARM64):**

```bash
curl -sS https://downloads.1password.com/linux/debian/arm64/stable/1password-cli-arm64-latest.deb -o op.deb
sudo dpkg -i op.deb && rm op.deb
op --version
```

### Create a Service Account

1. Go to 1Password.com → **Integrations** → **Service Accounts**
1. Click **New Service Account**, name it (e.g. `revolut-trader`)
1. Grant it **Read + Write** access to the `revolut-trader` vault
1. Copy the generated token — shown **only once**

### Set the Token

```bash
# macOS — add to ~/.zshrc
echo 'export OP_SERVICE_ACCOUNT_TOKEN=ops_xxxx...' >> ~/.zshrc
source ~/.zshrc

# Linux / Pi — add to ~/.bashrc
echo 'export OP_SERVICE_ACCOUNT_TOKEN=ops_xxxx...' >> ~/.bashrc
source ~/.bashrc
```

Verify:

```bash
op whoami
revt ops --status
```

______________________________________________________________________

## Quick Start

```bash
revt ops init   # create vault, items, generate keys (int/prod only), install deps
revt run        # start with mock API on feature branches (no credentials needed)

# For real API (env is auto-detected from git context):
revt ops init   # store your Revolut API credentials
revt ops --show # verify stored values (masked)
revt run        # start with real API in paper mode
```

______________________________________________________________________

## Stored Items

The bot uses two 1Password items per environment plus shared risk-level items in the `revolut-trader` vault.

### Credentials (`revolut-trader-credentials-{env}`)

| Field                 | Type      | dev        | int / prod     |
| --------------------- | --------- | ---------- | -------------- |
| `REVOLUT_API_KEY`     | concealed | Not needed | Yes            |
| `REVOLUT_PRIVATE_KEY` | concealed | Not needed | Yes            |
| `REVOLUT_PUBLIC_KEY`  | concealed | Not needed | Yes            |
| `TELEGRAM_BOT_TOKEN`  | concealed | Optional   | Optional       |

> **Dev uses mock API** — no Revolut API key or Ed25519 keys are required. Only the Telegram bot token is stored in the dev credentials item (optional).

### Trading Configuration (`revolut-trader-config-{env}`)

| | Field | Type | Default | dev / int | prod | Valid Values |
| | \---------------------------- | ---- | -------------------- | --------- | ---------- | ------------------------------------------------------------------------------------------------------ |
| | `DEFAULT_STRATEGY` | text | `market_making` | Required | Required | `market_making`, `momentum`, `mean_reversion`, `multi_strategy`, `breakout`, `range_reversion` |
| | `RISK_LEVEL` | text | `conservative` | Required | Required | `conservative`, `moderate`, `aggressive` |
| | `BASE_CURRENCY` | text | `EUR` | Required | Required | `EUR`, `USD`, `GBP` |
| | `TRADING_PAIRS` | text | `BTC-EUR,ETH-EUR` | Required | Required | Comma-separated symbols |
| | `INITIAL_CAPITAL` | text | `10000` | Required | Not needed | Any positive number |
| | `MAX_CAPITAL` | text | _(not set)_ | Optional | Optional | Any positive number — caps how much cash the bot can use regardless of account balance |
| | `SHUTDOWN_TRAILING_STOP_PCT` | text | _(not set)_ | Optional | Optional | e.g. `0.5` for 0.5% — trailing stop % for profitable positions on shutdown; omit to close immediately |
| | `SHUTDOWN_MAX_WAIT_SECONDS` | text | `120` | Optional | Optional | Hard timeout before force-closing a profitable position whose trailing stop has not triggered |
| | `LOG_LEVEL` | text | `INFO` | Optional | Optional | `DEBUG`, `INFO`, `WARNING`, or `ERROR` — CLI `--log-level` overrides this per-run |
| | `INTERVAL` | text | _(strategy default)_ | Optional | Optional | Trading loop interval in seconds — overrides the per-strategy default; CLI `--interval` overrides this |
| | `BACKTEST_DAYS` | text | `30` | Optional | Optional | Default look-back window in days for all backtest commands; CLI `--days` overrides this |
| | `BACKTEST_INTERVAL` | text | `60` | Optional | Optional | Default candle width in minutes for backtests (must be a valid choice); CLI `--interval` overrides |
| | `MAKER_FEE_PCT` | text | `0.0` | Optional | Optional | Maker fee rate applied to LIMIT orders — update when Revolut changes its fee schedule |
| | `TAKER_FEE_PCT` | text | `0.0009` | Optional | Optional | Taker fee rate applied to MARKET orders (0.09% default) — update when Revolut changes its fee schedule |
| | `MAX_ORDER_VALUE` | text | `10000` | Optional | Optional | Absolute max order value in base currency (EUR) — prevents accidental oversized orders |
| | `MIN_ORDER_VALUE` | text | `10` | Optional | Optional | Minimum order value in base currency (EUR) — filters out dust trades |
| | `TELEGRAM_CHAT_ID` | text | _(not set)_ | Optional | Optional | Telegram chat ID (user or group) to receive notifications and reports |

______________________________________________________________________

## Telegram Integration

The bot supports Telegram notifications and a control plane for remote management and analytics report delivery. All Telegram credentials and configuration are stored in 1Password under the trading config item (`revolut-trader-config-{env}`).

### Required Fields

| Field                | Item                                         | Type      | Description                                                  |
| -------------------- | -------------------------------------------- | --------- | ------------------------------------------------------------ |
| `TELEGRAM_BOT_TOKEN` | `revolut-trader-credentials-{env}`           | concealed | Telegram bot token (from @BotFather)                         |
| `TELEGRAM_CHAT_ID`   | `revolut-trader-config-{env}`                | text      | Chat ID (user or group) to receive notifications and reports |

### How to Set Up

1. **Create a Telegram Bot:**

   - Open Telegram and search for [@BotFather](https://t.me/BotFather)
   - Run `/newbot` and follow the instructions
   - Copy the bot token (starts with `6xxxxxx:...`)

1. **Set Up Bot Commands (Optional but Recommended):**

   - In your chat with @BotFather, select your bot and run `/setcommands`
   - Paste the following command list:

   ```
   run - Start the trading bot (optional: strategy, risk, pairs)
   stop - Stop the trading bot gracefully
   status - Show bot status and session P&L
   balance - Show cash balance and open positions
   report - Generate analytics report (optional: days, default 30)
   backtest - Run a backtest (optional: strategy, risk, days, pairs)
   help - Show list of available commands
   ```

   - This enables autocomplete in Telegram when typing `/` — users can see all available commands with descriptions

1. **Get Your Chat ID:**

   - Add your bot to the desired group or start a chat with it
   - Send a message to the bot
   - Use a tool like [@userinfobot](https://t.me/userinfobot) or [@getidsbot](https://t.me/getidsbot) to get your chat ID, or check the logs after running the bot (it will log unknown chat IDs)

1. **Store in 1Password:**

   - Store the bot token in the credentials item and chat ID in the config item:

```bash
# Store bot token in credentials item
op item edit revolut-trader-credentials-int \
  --vault revolut-trader \
  TELEGRAM_BOT_TOKEN[concealed]="6xxxxxx:yourbottoken"

# Store chat ID in config item
op item edit revolut-trader-config-int \
  --vault revolut-trader \
  TELEGRAM_CHAT_ID[text]="123456789"
```

5. **Verify:**
   - Run `revt telegram start` to start the Telegram control plane
   - Run `revt run` and check for Telegram notifications
   - Use `/status`, `/balance`, `/report` commands in your Telegram chat
   - Type `/` in your Telegram chat to see the autocomplete menu with all bot commands

### How the Bot Uses Telegram Config

- Sends trade notifications, analytics reports, and error alerts to the configured chat
- Enables the always-on Telegram Control Plane (`revt telegram start`)
- Delivers analytics reports as PDF (if `fpdf2` is installed) or as a text summary
- Both `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` must be set; if either is missing, notifications are silently disabled

### Troubleshooting

- **No notifications received:**
  - Check that the bot is running and `TELEGRAM_BOT_TOKEN` (in credentials item) and `TELEGRAM_CHAT_ID` (in config item) are set correctly
  - Check logs for errors related to Telegram
- **Bot not responding to commands:**
  - Make sure the bot is added to the group and is not blocked
  - Verify the chat ID matches the group or user
- **Field not found:**
  - Run `revt ops` to store the bot token in 1Password (prompted interactively)
  - Run `revt config set TELEGRAM_CHAT_ID <chat_id>`

For more details, see [`END_USER_GUIDE.md`](END_USER_GUIDE.md) and [`DEVELOPER_GUIDE.md`](DEVELOPER_GUIDE.md).

> **TRADING_MODE** defaults to `paper` in all environments (dev, int, and prod). To enable live trading, set `TRADING_MODE=live` in 1Password for the `prod` environment. Live trading is rejected in dev and int regardless of this setting.
>
> **INITIAL_CAPITAL** is only needed for paper mode (dev/int). In prod the real balance is fetched from the Revolut API.

If any required field is missing, the bot refuses to start with an actionable error:

```
RuntimeError: RISK_LEVEL not found in 1Password config.
Run: revt ops init
```

### Risk Level Configuration (`revolut-trader-risk-{level}`)

Three environment-agnostic items — one per risk level — hold the numerical parameters for each profile. These items are shared across all environments (dev / int / prod), because the risk profile is a property of the user's strategy, not the deployment environment.

Items: `revolut-trader-risk-conservative`, `revolut-trader-risk-moderate`, `revolut-trader-risk-aggressive`

| Field                   | Type | conservative | moderate | aggressive | Notes                              |
| ----------------------- | ---- | ------------ | -------- | ---------- | ---------------------------------- |
| `MAX_POSITION_SIZE_PCT` | text | `1.5`        | `3.0`    | `5.0`      | Max position as % of portfolio     |
| `MAX_DAILY_LOSS_PCT`    | text | `3.0`        | `5.0`    | `10.0`     | Daily loss limit as % of portfolio |
| `STOP_LOSS_PCT`         | text | `1.5`        | `2.5`    | `4.0`      | Stop-loss % per position           |
| `TAKE_PROFIT_PCT`       | text | `2.5`        | `4.0`    | `7.0`      | Take-profit % per position         |
| `MAX_OPEN_POSITIONS`    | text | `3`          | `5`      | `8`        | Maximum concurrent open positions  |

`revt ops` creates all three items with the defaults shown above. To customise:

```bash
# Tighten the conservative stop-loss to 1%
op item edit revolut-trader-risk-conservative --vault revolut-trader \
  STOP_LOSS_PCT[text]="1.0"

# Increase max open positions for moderate risk
op item edit revolut-trader-risk-moderate --vault revolut-trader \
  MAX_OPEN_POSITIONS[text]="7"
```

______________________________________________________________________

## Commands

| Command                    | Description                                      |
| -------------------------- | ------------------------------------------------ |
| `revt ops init`            | Full first-time setup (vault, items, keys, deps) |
| `revt ops --show`          | Show all stored values (masked)                  |
| `revt ops --status`        | Check 1Password authentication and vault status  |
| `revt config show`         | Show trading configuration                       |
| `revt config set KEY VALUE`| Update a config field                            |
| `revt config delete KEY`   | Remove a config field                            |

### Using the CLI directly

```bash
# Set a single config value
op item edit revolut-trader-config-int \
  --vault revolut-trader \
  RISK_LEVEL[text]="moderate"

# Set multiple values at once
op item edit revolut-trader-config-int \
  --vault revolut-trader \
  RISK_LEVEL[text]="moderate" \
  TRADING_PAIRS[text]="BTC-EUR,ETH-EUR,SOL-EUR"

# Rotate API key
op item edit revolut-trader-credentials-int \
  --vault revolut-trader \
  REVOLUT_API_KEY[concealed]="new-api-key"
```

______________________________________________________________________

## How the Bot Uses 1Password

1. On startup, `is_available()` calls `op whoami` — fails fast if the token is missing or invalid
1. `_refresh()` batch-fetches both vault items in one cycle
1. Values are cached for 29 minutes; the next refresh happens automatically
1. Private keys are loaded directly into memory — never written to disk

### Python API

```python
import src.utils.onepassword as op

if op.is_available():
    api_key = op.get("REVOLUT_API_KEY")  # raises if missing
    op.invalidate_cache()  # force refresh
```

______________________________________________________________________

## Safety Features

- **No code defaults** — the bot will not start without explicit 1Password config
- **Fail fast** — missing or invalid config raises a clear error immediately
- **Validation** — invalid enum values (e.g., `RISK_LEVEL=extreme`) cause an immediate `ValueError`
- **Live mode protection** — warns before starting, verifies credentials and balance
- **Audit trail** — 1Password logs all credential access

______________________________________________________________________

## Security Best Practices

**DO:**

- Use 1Password for ALL credentials and config
- Keep `OP_SERVICE_ACCOUNT_TOKEN` in your shell profile (not in code)
- Rotate the service account token periodically
- Grant the service account only the minimum required vault permissions
- Use `text` fields for config, `concealed` fields for secrets

**DON'T:**

- Create `.env` files (not supported)
- Store credentials in code or config files
- Commit secrets to git
- Share the service account token in plaintext messages

______________________________________________________________________

## Troubleshooting

**`1Password not authenticated`**
Set `OP_SERVICE_ACCOUNT_TOKEN` and run `op whoami` to verify.

**`op: command not found`**
Install the CLI (see Prerequisites above).

**Vault or item not found**
Run `revt ops --status` to diagnose, then `revt ops init` to recreate.

**Field not found at runtime**
Run `revt config set <field> <value>` to add the missing field,
or `revt ops init` to recreate the full config item with defaults.

**Bot fails with "1Password required"**

1. Verify token is set: `echo $OP_SERVICE_ACCOUNT_TOKEN`
1. Verify CLI works: `op whoami`
1. Verify credentials exist: `revt ops --status`

______________________________________________________________________

## FAQ

**Q: Do I need 1Password to run the bot?**
Yes — trading configuration is always loaded from 1Password. However, **dev** mode does not require API credentials (REVOLUT_API_KEY, REVOLUT_PRIVATE_KEY) since it uses the mock API.

**Q: What if 1Password is unavailable?**
The bot fails to start immediately with a clear error message.

**Q: Are private keys ever written to disk?**
No. They are loaded directly into memory from 1Password.

**Q: How do I switch back to USD?**
`revt config set BASE_CURRENCY USD` and update your trading pairs accordingly.
