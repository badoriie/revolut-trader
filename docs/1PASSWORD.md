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
make opstatus
```

______________________________________________________________________

## Quick Start

```bash
make setup       # create vault, items, generate keys (int/prod only), install deps
make run-dev     # start in dev mode (mock API — no API key needed)

# For int/prod environments (real API):
make ops ENV=int # store your Revolut API credentials
make opshow      # verify stored values (masked)
make run-int     # start with real API in paper mode
```

______________________________________________________________________

## Stored Items

The bot uses two 1Password items per environment in the `revolut-trader` vault.

### Credentials (`revolut-trader-credentials-{env}`)

| Field                     | Type      | dev            | int / prod     |
| ------------------------- | --------- | -------------- | -------------- |
| `REVOLUT_API_KEY`         | concealed | Not needed     | Yes            |
| `REVOLUT_PRIVATE_KEY`     | concealed | Not needed     | Yes            |
| `REVOLUT_PUBLIC_KEY`      | concealed | Not needed     | Yes            |
| `DATABASE_ENCRYPTION_KEY` | concealed | Auto-generated | Auto-generated |

> **Dev uses mock API** — no Revolut API key or Ed25519 keys are required. Only the database encryption key (auto-generated) is stored in the dev credentials item.

### Trading Configuration (`revolut-trader-config`)

| Field              | Type | Default           | Valid Values                                                                                   |
| ------------------ | ---- | ----------------- | ---------------------------------------------------------------------------------------------- |
| `TRADING_MODE`     | text | `paper`           | `paper`, `live`                                                                                |
| `DEFAULT_STRATEGY` | text | `market_making`   | `market_making`, `momentum`, `mean_reversion`, `multi_strategy`, `breakout`, `range_reversion` |
| `RISK_LEVEL`       | text | `conservative`    | `conservative`, `moderate`, `aggressive`                                                       |
| `BASE_CURRENCY`    | text | `EUR`             | `EUR`, `USD`, `GBP`                                                                            |
| `TRADING_PAIRS`    | text | `BTC-EUR,ETH-EUR` | Comma-separated symbols                                                                        |
| `INITIAL_CAPITAL`  | text | `10000`           | Any positive number                                                                            |

All six config fields are **required**. If any field is missing, the bot refuses to start with an actionable error:

```
RuntimeError: TRADING_MODE not found in 1Password config.
Run: make opconfig-init
```

______________________________________________________________________

## Commands

| Command                           | Description                                      |
| --------------------------------- | ------------------------------------------------ |
| `make setup`                      | Full first-time setup (vault, items, keys, deps) |
| `make ops`                        | Store API key credentials                        |
| `make opshow`                     | Show all stored values (masked)                  |
| `make opstatus`                   | Check 1Password authentication and vault status  |
| `make opdelete`                   | Delete credentials item (requires confirmation)  |
| `make opconfig-show`              | Show trading configuration                       |
| `make opconfig-set KEY=X VALUE=Y` | Update a config field                            |
| `make opconfig-init`              | (Re-)create config item with defaults            |

### Using the CLI directly

```bash
# Set a single config value
op item edit revolut-trader-config \
  --vault revolut-trader \
  TRADING_MODE[text]="live"

# Set multiple values at once
op item edit revolut-trader-config \
  --vault revolut-trader \
  TRADING_MODE[text]="live" \
  RISK_LEVEL[text]="moderate" \
  TRADING_PAIRS[text]="BTC-EUR,ETH-EUR,SOL-EUR"

# Rotate API key
op item edit revolut-trader-credentials \
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
Run `make opstatus` to diagnose, then `make setup` or `make ops` to recreate.

**Field not found at runtime**
Run `make opconfig-set KEY=<field> VALUE=<value>` to add the missing field,
or `make opconfig-init` to recreate the full config item with defaults.

**Bot fails with "1Password required"**

1. Verify token is set: `echo $OP_SERVICE_ACCOUNT_TOKEN`
1. Verify CLI works: `op whoami`
1. Verify credentials exist: `make opstatus`

______________________________________________________________________

## FAQ

**Q: Do I need 1Password to run the bot?**
Yes — trading configuration is always loaded from 1Password. However, **dev** mode does not require API credentials (REVOLUT_API_KEY, REVOLUT_PRIVATE_KEY) since it uses the mock API.

**Q: What if 1Password is unavailable?**
The bot fails to start immediately with a clear error message.

**Q: Are private keys ever written to disk?**
No. They are loaded directly into memory from 1Password.

**Q: How do I switch back to USD?**
`make opconfig-set KEY=BASE_CURRENCY VALUE=USD` and update your trading pairs accordingly.
