# 1Password Integration

Secure credential management using 1Password CLI for the Revolut Trading Bot.

## Overview

This project integrates with 1Password CLI (`op`) to provide secure credential storage and retrieval. When 1Password is available, credentials are automatically synced from your vault instead of using plain text `.env` files.

## Benefits

- **Security**: Credentials stored in encrypted 1Password vault
- **Convenience**: Auto-sync credentials across machines
- **Audit Trail**: 1Password tracks access to credentials
- **Team Collaboration**: Share credentials securely with team members
- **Fallback**: Automatically falls back to `.env` if 1Password unavailable

## Prerequisites

### 1. Install 1Password CLI

**macOS (via Homebrew):**
```bash
brew install --cask 1password-cli
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

### Option 1: Setup Wizard (Recommended)

Run the interactive setup wizard:

```bash
make 1password-setup
```

This will:
1. Check if 1Password CLI is installed and signed in
2. Create a vault for the trading bot (or use existing)
3. Import credentials from your existing `.env` file
4. Verify the setup

### Option 2: Manual Setup

1. **Store existing credentials:**
   ```bash
   # Make sure you have a .env file with your credentials
   make 1password-store
   ```

2. **Verify storage:**
   ```bash
   make 1password-show
   ```

3. **Retrieve credentials:**
   ```bash
   make 1password-retrieve
   ```

## Usage

### Store Credentials in 1Password

```bash
# Store all credentials from .env file
make 1password-store
```

This reads your `.env` file and stores all credentials in 1Password vault `revolut-trader` under item `revolut-trader-credentials`.

### Store Private Key in 1Password (Recommended)

For enhanced security, store your Revolut private key PEM file in 1Password instead of keeping it in the `config/` folder:

```bash
# Store the private key in 1Password
op item edit revolut-trader-credentials \
  --vault revolut-trader \
  REVOLUT_PRIVATE_KEY[concealed]="$(cat config/revolut_private.pem)"
```

Or use the 1Password CLI to create a document field:

```bash
# Add private key as a concealed text field
cat config/revolut_private.pem | op item edit revolut-trader-credentials \
  --vault revolut-trader \
  "REVOLUT_PRIVATE_KEY[concealed]=-"
```

**Benefits:**
- Private key never stored in filesystem (more secure)
- Encrypted in 1Password vault
- Easy to rotate/update
- Audit trail of access
- No risk of accidental git commit

**Note:** After storing in 1Password, you can safely delete the PEM file from `config/` folder. The application will automatically retrieve it from 1Password.

### Retrieve Credentials from 1Password

```bash
# Retrieve and write to .env file
make 1password-retrieve
```

This fetches all credentials from 1Password and creates/updates your `.env` file.

### Auto-Sync (Recommended for Team Use)

```bash
# Sync from 1Password if available, otherwise use existing .env
make 1password-sync
```

This is the safest option as it:
- Uses 1Password if available and signed in
- Falls back to existing `.env` if 1Password not available
- Never fails if 1Password unavailable

**Add to your workflow:**
```bash
# Before running the bot
make 1password-sync && make run-paper
```

### View Stored Credentials (Masked)

```bash
# Show credential keys with masked values
make 1password-show
```

Output example:
```
REVOLUT_API_KEY=sk_l***
TRADING_MODE=pape***
TELEGRAM_BOT_TOKEN=6891***
```

### Check 1Password Status

```bash
make 1password-status
```

Shows:
- 1Password CLI installation status
- Sign-in status
- Vault existence
- Stored credentials status

### Delete Credentials from 1Password

```bash
# Remove credentials from 1Password (requires confirmation)
make 1password-delete
```

⚠️ **Warning**: This deletes credentials from 1Password vault. Your local `.env` file remains unchanged.

## Configuration

### Environment Variables

Customize 1Password integration using environment variables:

```bash
# Set custom vault name
export OP_VAULT_NAME="my-trading-vault"

# Then run commands
make 1password-store
```

### Default Configuration

- **Vault Name**: `revolut-trader`
- **Item Name**: `revolut-trader-credentials`
- **Item Category**: Secure Note with concealed fields

## Python API

You can also use 1Password integration in your Python code:

```python
from src.utils.onepassword import OnePasswordClient, get_credential, ensure_env_file

# Check if 1Password is available
client = OnePasswordClient()
if client.is_available():
    print("1Password CLI is ready!")

# Get a specific credential
api_key = get_credential("REVOLUT_API_KEY", use_1password=True)

# Get all credentials
fields = client.get_all_fields()
for key, value in fields.items():
    print(f"{key}={value[:4]}***")

# Ensure .env file exists (creates from 1Password if needed)
ensure_env_file()
```

### Private Key Automatic Retrieval

The Revolut API client automatically retrieves the private key from 1Password with the following priority:

1. **1Password** (most secure): Retrieves from `REVOLUT_PRIVATE_KEY` field
2. **File fallback**: Falls back to `config/revolut_private.pem` if 1Password unavailable

```python
from src.api.client import RevolutAPIClient

# No code changes needed - automatically uses 1Password if available
async with RevolutAPIClient() as client:
    balance = await client.get_balance()
    print(balance)
```

The private key is **never** written to disk when using 1Password, providing maximum security.

## Workflows

### Development Workflow

```bash
# 1. Setup 1Password (one-time)
make 1password-setup

# 2. Store your credentials
make 1password-store

# 3. On each new machine or session
make 1password-sync

# 4. Run the bot
make run-paper
```

### Team Collaboration Workflow

1. **Team Lead**: Store credentials in shared 1Password vault
   ```bash
   export OP_VAULT_NAME="team-trading-bot"
   make 1password-store
   ```

2. **Team Members**: Retrieve credentials from shared vault
   ```bash
   export OP_VAULT_NAME="team-trading-bot"
   make 1password-retrieve
   ```

3. **Everyone**: Run bot with synced credentials
   ```bash
   make 1password-sync && make run-paper
   ```

### CI/CD Workflow

For automated deployments:

```bash
# In your CI/CD pipeline
# 1. Sign in to 1Password using service account
eval $(op signin --account my-company.1password.com)

# 2. Retrieve credentials
make 1password-retrieve

# 3. Run tests or deploy
make test
make deploy
```

**1Password Service Accounts**: https://developer.1password.com/docs/service-accounts/

## Security Best Practices

### ✅ DO

- **Store private key PEM file in 1Password** (not in config folder)
- Use 1Password for all production credentials
- Store credentials once, retrieve as needed
- Use `1password-sync` in scripts for automatic fallback
- Set up 1Password service accounts for CI/CD
- Enable 1Password audit logging
- Use shared vaults for team collaboration
- Delete local PEM file after storing in 1Password

### ❌ DON'T

- **Keep private key PEM files in config folder** (use 1Password instead)
- Commit `.env` files or `.pem` files to git (already in `.gitignore`)
- Share credentials via Slack/email
- Keep credentials in plain text files
- Use same credentials for dev/staging/production
- Share your personal 1Password account
- Email or message private keys to team members

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
make 1password-setup
```

### Item not found

```bash
# Check status
make 1password-status

# Store credentials
make 1password-store
```

### Permission denied

```bash
# Check vault permissions
op vault get revolut-trader

# Ensure you have access to the vault
# Ask vault owner to grant access
```

### Rate limiting

```bash
# 1Password CLI has rate limits
# Wait a few seconds between commands

# Check rate limit status
op account get
```

## Advanced Usage

### Custom Vault and Item Names

```bash
# Use custom names
OP_VAULT_NAME="my-vault" bash scripts/1password-manager.sh store
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
    print("1Password not available, using fallback")
    exit(1)

# Get specific fields
api_key = client.get_field("REVOLUT_API_KEY")
mode = client.get_field("TRADING_MODE")

# Get all fields
all_creds = client.get_all_fields()

# Create .env file
client.create_env_file(Path(".env"))
```

## Integration with Existing Setup

The 1Password integration is designed to be **non-intrusive**:

- If 1Password unavailable, falls back to `.env` file
- No changes required to existing code
- Optional feature, not required
- Can be enabled/disabled anytime

## FAQ

**Q: Do I need 1Password to run the bot?**
A: No, 1Password is optional. The bot works fine with `.env` files and local PEM file.

**Q: What happens if 1Password is unavailable?**
A: The bot automatically falls back to using the `.env` file and local PEM file from `config/` folder.

**Q: Should I store the private key PEM file in 1Password or config folder?**
A: **Always store in 1Password for production.** Storing in config folder is only acceptable for local development. 1Password provides encryption, audit trails, and eliminates risk of accidental commits.

**Q: How do I store my private key in 1Password?**
A: Use: `op item edit revolut-trader-credentials --vault revolut-trader REVOLUT_PRIVATE_KEY[concealed]="$(cat config/revolut_private.pem)"`. See "Store Private Key in 1Password" section above.

**Q: Can I delete the PEM file from config folder after storing in 1Password?**
A: Yes! Once stored in 1Password, the application will automatically retrieve it from there. You can safely delete the local PEM file.

**Q: Can I use 1Password for some credentials and .env for others?**
A: Yes, `get_credential()` tries 1Password first, then falls back to environment variables.

**Q: Is my 1Password master password stored?**
A: No, you authenticate with 1Password separately using `op signin`.

**Q: Can I share credentials with my team?**
A: Yes, use a shared vault in 1Password and all team members can access it (including the private key).

**Q: How often should I sync credentials?**
A: Use `make 1password-sync` before each run, or at the start of your session.

**Q: What if someone updates credentials in 1Password?**
A: Run `make 1password-retrieve` to get the latest credentials. For the private key, it's retrieved automatically on each run.

## Resources

- [1Password CLI Documentation](https://developer.1password.com/docs/cli/)
- [1Password Service Accounts](https://developer.1password.com/docs/service-accounts/)
- [1Password Security Model](https://1password.com/security/)

## Support

For issues related to:
- **1Password CLI**: https://support.1password.com/
- **This Integration**: Create an issue in the project repository
