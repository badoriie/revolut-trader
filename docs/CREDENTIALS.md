# Credential Management

## 1Password Required

This trading bot uses **1Password exclusively** for credential storage. There is no `.env` file support.

### Why 1Password Only?

- **Security**: Encrypted credential storage
- **Auditability**: Track who accesses credentials
- **No local storage**: Credentials never written to disk
- **Team sharing**: Secure credential sharing across team members
- **Compliance**: Meet security requirements for financial applications

## Quick Start

### 1. Install 1Password CLI

```bash
# macOS
brew install --cask 1password-cli

# Verify installation
op --version
```

### 2. Sign In

```bash
eval $(op signin)

# Verify
op account list
```

### 3. Setup Credentials

```bash
# Run setup wizard (creates vault and item)
make ops

# Follow prompts to enter your credentials:
# - REVOLUT_API_KEY
# - REVOLUT_PRIVATE_KEY (PEM content)
# - TELEGRAM_BOT_TOKEN
# - TELEGRAM_CHAT_ID
# - TRADING_MODE
```

### 4. Verify

```bash
# Check status
make opstatus

# Show credentials (masked)
make opshow
```

### 5. Run Bot

```bash
# Bot automatically retrieves credentials from 1Password
make run-paper
```

## Commands

| Command         | Description                           |
| --------------- | ------------------------------------- |
| `make ops`      | Setup 1Password and store credentials |
| `make opshow`   | Show stored credentials (masked)      |
| `make opstatus` | Check 1Password connection status     |
| `make opdelete` | Delete credentials from 1Password     |

## How It Works

1. **No .env File**: The bot reads credentials directly from 1Password at runtime
1. **Private Key**: Retrieved from 1Password field `REVOLUT_PRIVATE_KEY` (never touches disk)
1. **API Key**: Retrieved from field `REVOLUT_API_KEY`
1. **Telegram**: Retrieved from `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`

## Configuration

### Default Vault and Item

- **Vault**: `revolut-trader`
- **Item**: `revolut-trader-credentials`

### Custom Names

Set environment variables before running commands:

```bash
export OP_VAULT_NAME="my-custom-vault"
export OP_ITEM_NAME="my-credentials"

make ops
```

## Troubleshooting

### 1Password CLI Not Found

```bash
# Install it
brew install --cask 1password-cli
```

### Not Signed In

```bash
# Sign in
eval $(op signin)

# Check
op account list
```

### Credentials Not Found

```bash
# Run setup again
make ops

# Or check status
make opstatus
```

### Bot Can't Start

If bot fails with "1Password required" error:

1. Check 1Password CLI is installed: `op --version`
1. Check you're signed in: `op account list`
1. Check credentials exist: `make opstatus`
1. Re-run setup if needed: `make ops`

## Security Best Practices

### ✅ DO

- Use 1Password for ALL credentials
- Store private key in 1Password
- Keep 1Password CLI updated
- Use secure vault passwords
- Enable 2FA on 1Password account

### ❌ DON'T

- Create `.env` files (not supported)
- Store credentials in code
- Commit secrets to git
- Share credentials via email/Slack
- Keep local copies of private keys

## Team Collaboration

### Sharing Credentials

1. Create shared vault in 1Password
1. Store credentials in shared vault
1. Team members can access via their 1Password accounts

```bash
# Team lead stores credentials
export OP_VAULT_NAME="team-revolut-bot"
make ops

# Team members can access automatically
# (if they have permission to the vault)
make run-paper
```

## Migration from .env

If you previously used `.env` files:

### Option 1: Manual Entry

```bash
# Run setup and enter values manually
make ops
```

### Option 2: Import from Existing .env

```bash
# If you still have .env file, values can be copied manually
# DO NOT commit .env file to git
# Delete .env file after importing to 1Password
```

## FAQ

**Q: Can I use .env files?**
A: No. 1Password is required for security.

**Q: What if 1Password is down?**
A: The bot cannot start without 1Password. This is intentional for security.

**Q: Can I run locally without 1Password?**
A: No. Install 1Password CLI even for local development.

**Q: How do I rotate credentials?**
A: Update values in 1Password, bot will use new values on next run.

```bash
# Update specific field
op item edit revolut-trader-credentials \
  --vault revolut-trader \
  REVOLUT_API_KEY[concealed]=new-api-key-here
```

**Q: Can CI/CD access credentials?**
A: Yes, use 1Password Service Accounts for automated access.

## Support

- Setup issues: Run `make opstatus` to diagnose
- 1Password CLI docs: https://developer.1password.com/docs/cli/
- Service Accounts: https://developer.1password.com/docs/service-accounts/
