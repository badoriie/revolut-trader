# 1Password Integration

Secure credential management using 1Password CLI for the Revolut Trading Bot.

## Overview

This project uses **1Password exclusively** for credential storage and retrieval. All sensitive data (API keys, private keys) are stored in your encrypted 1Password vault. **No .env files or local credential storage** is used.

## Benefits

- **Security**: All credentials stored in encrypted 1Password vault only
- **No Disk Storage**: Private keys never written to disk
- **Convenience**: Auto-sync credentials across machines
- **Audit Trail**: 1Password tracks all credential access
- **Team Collaboration**: Share credentials securely with team members
- **No Risk of Leaks**: No local files to accidentally commit to git

## Prerequisites

### 1. Install 1Password CLI

**Requirements:**
- 1Password CLI v2.0 or higher (the bot uses the `--reveal` flag for concealed fields)

**macOS (via Homebrew):**
```bash
brew install --cask 1password-cli
# Verify version
op --version
```

**Linux:**
```bash
# Download from https://developer.1password.com/docs/cli/get-started/
wget https://downloads.1password.com/linux/tar/stable/x86_64/op_linux_amd64_latest.tar.gz
tar -xvf op_linux_amd64_latest.tar.gz
sudo mv op /usr/local/bin/
```

**Windows:**
Download from [1Password CLI Downloads](https://developer.1password.com/docs/cli/get-started/)

### 2. Sign In to 1Password CLI

```bash
# Sign in to your 1Password account
eval $(op signin)

# Verify sign-in
op account list
```

## Quick Start

### Available Commands

All credential management is done through Makefile commands:

```bash
make ops        # Setup (one-time: create vault, generate keys, store in 1Password)
make opshow     # Show credentials (masked)
make opstatus   # Check 1Password status
make opdelete   # Delete credentials (requires confirmation)
```

### Setup Wizard (One Command)

Run the complete project setup:

```bash
make setup
```

This will:
1. Check and install uv (Python package manager)
2. Verify Python 3.11+ in uv virtual environment
3. Check if 1Password CLI is installed and signed in
4. Create a vault `revolut-trader` (or use existing)
5. **Generate Ed25519 key pair in temporary directory**
6. **Store keys in 1Password immediately**
7. **Automatically delete temporary key files** (zero disk footprint)
8. Create item `revolut-trader-credentials` with all required placeholder fields:
   - **REVOLUT_API_KEY** (placeholder: `<your-revolut-api-key-here>`)
   - **REVOLUT_PRIVATE_KEY** (auto-generated Ed25519 private key)
   - **REVOLUT_PUBLIC_KEY** (auto-generated Ed25519 public key)
   - **TELEGRAM_BOT_TOKEN** (placeholder: `<your-telegram-bot-token-optional>`)
   - **TELEGRAM_CHAT_ID** (placeholder: `<your-telegram-chat-id-optional>`)
   - **TRADING_MODE** (default: `paper`)

**After setup:**
1. Copy the public key displayed in terminal
2. Register it on Revolut X: https://revolut.com/business/merchant-api
3. Get your API key from Revolut X
4. Store your API key: `op item edit revolut-trader-credentials --vault revolut-trader REVOLUT_API_KEY[concealed]="your-api-key"`
5. Done! The bot will now use 1Password automatically

**Security Note:** Keys are generated in a temporary directory and immediately stored in 1Password. The temporary files are automatically deleted. No credentials ever touch your project directory.

### Verify Setup

```bash
# Check 1Password status
make opstatus

# View stored credentials (masked)
make opshow
```

## Usage

### View Stored Credentials

View credentials with masked values for verification:

```bash
make opshow
```

Output example:
```
ℹ Stored credentials in 1Password:

✓ 1Password CLI is ready
  REVOLUT_PRIVATE_KEY       = -----BEG***
  REVOLUT_PUBLIC_KEY        = -----BEG***
  REVOLUT_API_KEY           = <your-re***
  TELEGRAM_BOT_TOKEN        = <your-te***
  TELEGRAM_CHAT_ID          = <your-te***
  TRADING_MODE              = pape***
```

### Update Credentials

Update individual credentials using 1Password CLI:

```bash
# Update API key
op item edit revolut-trader-credentials \
  --vault revolut-trader \
  REVOLUT_API_KEY[concealed]="your-new-api-key"

# Update Telegram credentials (optional)
op item edit revolut-trader-credentials \
  --vault revolut-trader \
  TELEGRAM_BOT_TOKEN[concealed]="your-bot-token" \
  TELEGRAM_CHAT_ID[concealed]="your-chat-id"

# Update trading mode
op item edit revolut-trader-credentials \
  --vault revolut-trader \
  TRADING_MODE[text]="live"
```

### Check Status

Check 1Password CLI and credentials status:

```bash
make opstatus
```

Shows:
- 1Password CLI installation status
- Sign-in status
- Vault existence
- Stored credentials status

### Delete Credentials

Remove credentials from 1Password (requires confirmation):

```bash
make opdelete
```

⚠️ **Warning**: This deletes credentials from 1Password vault permanently.

## How the Bot Uses 1Password

The bot automatically retrieves credentials from 1Password when it starts:

1. **On initialization**, the bot checks if 1Password is available
2. **If 1Password is signed in**, credentials are retrieved from the vault
3. **Private key is loaded directly into memory** (never written to disk)
4. **If 1Password is unavailable**, the bot will fail with clear instructions

**No fallback to .env files** - 1Password is required for this project.

## Configuration

### Environment Variables

Customize 1Password integration using environment variables:

```bash
# Set custom vault name (default: revolut-trader)
export OP_VAULT_NAME="my-trading-vault"

# Then run commands
make opstatus
```

### Default Configuration

- **Vault Name**: `revolut-trader`
- **Item Name**: `revolut-trader-credentials`
- **Item Category**: Secure Note with concealed fields

## Python API

You can also use 1Password integration in your Python code:

```python
from src.utils.onepassword import OnePasswordClient, get_credential

# Check if 1Password is available
client = OnePasswordClient()
if client.is_available():
    print("1Password CLI is ready!")

# Get a specific credential
api_key = get_credential("REVOLUT_API_KEY")

# Get all credentials
fields = client.get_all_fields()
for key, value in fields.items():
    print(f"{key}={value[:4]}***")
```

### Private Key Automatic Retrieval

The Revolut API client automatically retrieves the private key from 1Password:

```python
from src.api.client import RevolutAPIClient

# Private key automatically loaded from 1Password
async with RevolutAPIClient() as client:
    balance = await client.get_balance()
    print(balance)
```

The private key is **never** written to disk when using 1Password, providing maximum security.

## Workflows

### Development Workflow

```bash
# 1. Setup project (one-time)
make setup

# 2. Add your Revolut API credentials
op item edit revolut-trader-credentials --vault revolut-trader \
  REVOLUT_API_KEY[concealed]="your-api-key"

# 3. Run the bot
make run-paper
```

### Team Collaboration Workflow

1. **Team Lead**: Share the 1Password vault with team members
   ```bash
   # Team members get access to shared vault "revolut-trader"
   ```

2. **Team Members**: Just run the bot
   ```bash
   # Ensure signed in to 1Password
   eval $(op signin)

   # Run the bot (credentials auto-retrieved)
   make run-paper
   ```

3. **Everyone**: Credentials automatically synced from shared vault

### CI/CD Workflow

For automated deployments using 1Password Service Accounts:

```bash
# In your CI/CD pipeline
# 1. Sign in to 1Password using service account
export OP_SERVICE_ACCOUNT_TOKEN="your-service-account-token"

# 2. Run tests or deploy
make test
make run-paper
```

**1Password Service Accounts**: https://developer.1password.com/docs/service-accounts/

## Security Best Practices

### ✅ DO

- Use 1Password for all credentials (production and development)
- Store credentials once in 1Password, retrieve as needed
- Enable 1Password audit logging
- Use shared vaults for team collaboration
- Set up 1Password service accounts for CI/CD
- Sign in before running: `eval $(op signin)`

### ❌ DON'T

- Never create .env files with credentials
- Never commit keys or secrets to git
- Never share credentials via Slack/email/message
- Never keep credentials in plain text files
- Never use same credentials for dev/staging/production
- Never bypass 1Password requirement

## Troubleshooting

### 1Password CLI not found

```bash
# Check installation
which op

# Install if missing
brew install --cask 1password-cli
```

### Not signed in

```bash
# Sign in
eval $(op signin)

# Verify
op account list
```

### Vault not found

```bash
# Check existing vaults
op vault list

# Create vault if needed
make setup
```

### Item not found

```bash
# Check status
make opstatus

# Re-run setup
make ops
```

### Permission denied

```bash
# Check vault permissions
op vault get revolut-trader

# Ensure you have access to the vault
# Ask vault owner to grant access
```

## Advanced Usage

### Custom Vault and Item Names

```bash
# Use custom names
OP_VAULT_NAME="my-vault" bash scripts/1password-manager.sh status
```

### Update Single Credential

```python
from src.utils.onepassword import OnePasswordClient

client = OnePasswordClient()
client.set_field("REVOLUT_API_KEY", "new-api-key-value")
```

### Programmatic Access

```python
from src.utils.onepassword import OnePasswordClient

# Initialize client
client = OnePasswordClient(
    vault_name="my-vault",
    item_name="my-credentials"
)

# Check availability
if not client.is_available():
    print("1Password not available")
    exit(1)

# Get specific fields
api_key = client.get_field("REVOLUT_API_KEY")
mode = client.get_field("TRADING_MODE")

# Get all fields
all_creds = client.get_all_fields()
```

## FAQ

**Q: Do I need 1Password to run the bot?**
A: Yes, 1Password is required. All credentials are stored exclusively in 1Password.

**Q: What happens if 1Password is unavailable?**
A: The bot will fail to start and provide instructions to sign in to 1Password.

**Q: Can I use .env files instead?**
A: No, this project uses 1Password exclusively for security. No .env file fallback exists.

**Q: How do I rotate my API key?**
A: Use: `op item edit revolut-trader-credentials --vault revolut-trader REVOLUT_API_KEY[concealed]="new-key"`

**Q: Is my 1Password master password stored?**
A: No, you authenticate with 1Password separately using `op signin`.

**Q: Can I share credentials with my team?**
A: Yes, use a shared vault in 1Password and all team members can access it.

**Q: Are private keys ever written to disk?**
A: No, private keys are generated in temporary directories (automatically deleted) and stored only in 1Password. They're loaded directly into memory when needed.

**Q: How do I verify my credentials are set correctly?**
A: Run `make opshow` to see masked values, or `op item get revolut-trader-credentials --vault revolut-trader --format json` for full details.

## Resources

- [1Password CLI Documentation](https://developer.1password.com/docs/cli/)
- [1Password Service Accounts](https://developer.1password.com/docs/service-accounts/)
- [1Password Security Model](https://1password.com/security/)

## Support

For issues related to:
- **1Password CLI**: https://support.1password.com/
- **This Integration**: Create an issue in the project repository
