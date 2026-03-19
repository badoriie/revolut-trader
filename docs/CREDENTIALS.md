# Credential Management

## 1Password Required

This trading bot uses **1Password exclusively** for credential storage.
There is no `.env` file support. All credentials are fetched at runtime via the
1Password CLI authenticated with a service account token.

______________________________________________________________________

## Quick Start

### 1. Install 1Password CLI

```bash
# macOS
brew install --cask 1password-cli

# Linux / Raspberry Pi (ARM64)
curl -sS https://downloads.1password.com/linux/debian/arm64/stable/1password-cli-arm64-latest.deb -o op.deb
sudo dpkg -i op.deb && rm op.deb

op --version
```

### 2. Set Service Account Token

```bash
export OP_SERVICE_ACCOUNT_TOKEN=ops_xxxx...

# Verify
op whoami
```

Add to `~/.zshrc` (macOS) or `~/.bashrc` (Linux/Pi) for persistence.

### 3. Setup Credentials

```bash
make ops   # creates vault + item, prompts for your Revolut API key
```

### 4. Verify

```bash
make opstatus   # check authentication and vault status
make opshow     # show stored values (masked)
```

### 5. Run Bot

```bash
make run-paper
```

______________________________________________________________________

## Commands

| Command         | Description                                |
| --------------- | ------------------------------------------ |
| `make ops`      | Store API key and Telegram credentials     |
| `make opshow`   | Show stored credentials (masked)           |
| `make opstatus` | Check 1Password status                     |
| `make opdelete` | Delete credentials (requires confirmation) |

______________________________________________________________________

## Stored Fields

| Field                     | Item                         | Required       |
| ------------------------- | ---------------------------- | -------------- |
| `REVOLUT_API_KEY`         | `revolut-trader-credentials` | Yes            |
| `REVOLUT_PRIVATE_KEY`     | `revolut-trader-credentials` | Yes            |
| `TELEGRAM_BOT_TOKEN`      | `revolut-trader-credentials` | No             |
| `TELEGRAM_CHAT_ID`        | `revolut-trader-credentials` | No             |
| `DATABASE_ENCRYPTION_KEY` | `revolut-trader-credentials` | Auto-generated |

______________________________________________________________________

## Troubleshooting

**`1Password not authenticated`**

```bash
export OP_SERVICE_ACCOUNT_TOKEN=ops_xxxx...
op whoami   # should print your service account name
```

**`op: command not found`**
Install the CLI (see step 1 above).

**Credentials not found**

```bash
make opstatus   # diagnose
make ops        # re-run setup
```

**Bot fails with "1Password required"**

1. Verify token is set: `echo $OP_SERVICE_ACCOUNT_TOKEN`
1. Verify CLI works: `op whoami`
1. Verify credentials exist: `make opstatus`

______________________________________________________________________

## Security Best Practices

### ✅ DO

- Use 1Password for ALL credentials
- Keep `OP_SERVICE_ACCOUNT_TOKEN` in your shell profile (not in code)
- Rotate the service account token periodically
- Grant the service account only the minimum required vault permissions

### ❌ DON'T

- Create `.env` files (not supported)
- Store credentials in code or config files
- Commit secrets to git
- Share the service account token in plaintext messages

______________________________________________________________________

## Rotating Credentials

```bash
# Update API key
op item edit revolut-trader-credentials \
  --vault revolut-trader \
  REVOLUT_API_KEY[concealed]="new-api-key"

# Verify update
make opshow
```
