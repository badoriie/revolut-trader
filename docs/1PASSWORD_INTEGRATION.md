# 1Password Integration

Secure credential management using the 1Password CLI and a service account.

## Overview

This project uses **1Password exclusively** for all credentials and configuration.
Authentication is handled via a **service account token** (`OP_SERVICE_ACCOUNT_TOKEN`).
No `.env` files, no interactive sign-in, no biometric prompts.

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

Verify authentication:

```bash
op whoami
make opstatus
```

______________________________________________________________________

## Quick Start

```bash
make setup       # create vault, items, install deps
make ops         # store your Revolut API credentials
make opshow      # verify stored values (masked)
make run-paper   # start trading bot
```

______________________________________________________________________

## Commands

| Command                           | Description                                     |
| --------------------------------- | ----------------------------------------------- |
| `make ops`                        | Store API key and Telegram credentials          |
| `make opshow`                     | Show all stored values (masked)                 |
| `make opstatus`                   | Check 1Password authentication and vault status |
| `make opdelete`                   | Delete credentials item (requires confirmation) |
| `make opconfig-show`              | Show trading configuration                      |
| `make opconfig-set KEY=X VALUE=Y` | Update a config field                           |
| `make opconfig-init`              | (Re-)create config item with defaults           |

______________________________________________________________________

## Python API

```python
import src.utils.onepassword as op

# Check authentication
if op.is_available():
    print("1Password ready")

# Get a required field (raises RuntimeError if missing)
api_key = op.get("REVOLUT_API_KEY")

# Get an optional field (returns None if missing)
token = op.get_optional("TELEGRAM_BOT_TOKEN")

# Store a value
op.set_credential("revolut-trader-credentials", "REVOLUT_API_KEY", "new-key")

# Force cache refresh
op.invalidate_cache()
```

______________________________________________________________________

## How the Bot Uses 1Password

1. On startup, `is_available()` calls `op whoami` — fails fast if the token is missing or invalid
1. `_refresh()` batch-fetches both vault items (`revolut-trader-credentials` and `revolut-trader-config`) in one cycle
1. Values are cached for 29 minutes; the next refresh happens automatically
1. Private keys are loaded directly into memory — never written to disk

______________________________________________________________________

## Troubleshooting

**`1Password not authenticated`**
Set `OP_SERVICE_ACCOUNT_TOKEN` and run `op whoami` to verify.

**`op: command not found`**
Install the CLI (see Prerequisites above).

**Vault or item not found**
Run `make opstatus` to diagnose, then `make setup` or `make ops` to recreate.

**Field not found at runtime**
Run `make opconfig-set KEY=<field> VALUE=<value>` to add the missing field.

______________________________________________________________________

## FAQ

**Q: Do I need 1Password to run the bot?**
Yes — it is the only credential source. No `.env` fallback exists.

**Q: What if 1Password is unavailable?**
The bot fails to start immediately with a clear error message.

**Q: How do I rotate my API key?**
`op item edit revolut-trader-credentials --vault revolut-trader REVOLUT_API_KEY[concealed]="new-key"`

**Q: Are private keys ever written to disk?**
No. They are loaded directly into memory from 1Password.
