#!/bin/bash
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "================================================="
echo "Revolut Trader Setup Script"
echo "================================================="
echo ""

# Check if uv is installed
echo "Checking uv installation..."
if ! command -v uv &> /dev/null; then
    echo -e "${RED}❌ uv is not installed${NC}"
    echo ""
    echo "Please install uv first:"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo ""
    echo "Or on macOS:"
    echo "  brew install uv"
    exit 1
fi

echo -e "${GREEN}✓${NC} uv is installed"

# Check if uv project exists
echo ""
echo "Checking uv project..."
if [ ! -f "pyproject.toml" ]; then
    echo -e "${RED}❌ No pyproject.toml found${NC}"
    echo "Are you in the project directory?"
    exit 1
fi

# Check if venv exists, create if not
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}⚠${NC}  Virtual environment not found"
    echo "Creating venv with uv..."
    uv venv
    echo -e "${GREEN}✓${NC} Virtual environment created"
else
    echo -e "${GREEN}✓${NC} Virtual environment exists"
fi

# Check Python version in uv project
echo ""
echo "Checking Python version in uv project..."
python_version=$(uv run python --version 2>&1 | awk '{print $2}')
required_version="3.11"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo -e "${RED}❌ Python $python_version is too old${NC}"
    echo "This project requires Python $required_version or higher"
    exit 1
fi

echo -e "${GREEN}✓${NC} Python $python_version (meets requirement >= $required_version)"

# Check if 1Password CLI is installed
echo ""
echo "Checking 1Password CLI..."
if ! command -v op &> /dev/null; then
    echo -e "${RED}❌ 1Password CLI is not installed${NC}"
    echo ""
    echo "Please install it first:"
    echo "  brew install --cask 1password-cli"
    echo ""
    echo "Or visit: https://developer.1password.com/docs/cli/get-started/"
    exit 1
fi

echo -e "${GREEN}✓${NC} 1Password CLI is installed"

# Check if signed in to 1Password
echo ""
echo "Checking 1Password authentication..."
if ! op account list &> /dev/null; then
    echo -e "${YELLOW}⚠${NC}  Not signed in to 1Password"
    echo ""
    echo "Please sign in to 1Password:"
    echo "  eval \$(op signin)"
    echo ""
    exit 1
fi

echo -e "${GREEN}✓${NC} Signed in to 1Password"

# Configuration
VAULT_NAME="revolut-trader"
ITEM_NAME="revolut-trader-credentials"
CONFIG_ITEM_NAME="revolut-trader-config"

# Check if vault exists
echo ""
echo "Checking 1Password vault: $VAULT_NAME..."

if ! op vault get "$VAULT_NAME" &> /dev/null; then
    echo -e "${YELLOW}⚠${NC}  Vault '$VAULT_NAME' does not exist"
    echo ""
    read -p "Do you want to create the vault? (y/N): " create_vault

    if [ "$create_vault" = "y" ] || [ "$create_vault" = "Y" ]; then
        echo "Creating vault..."
        op vault create "$VAULT_NAME"
        echo -e "${GREEN}✓${NC} Vault created: $VAULT_NAME"
    else
        echo -e "${RED}❌ Vault is required. Exiting.${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✓${NC} Vault exists: $VAULT_NAME"
fi

# Check if credentials item exists
echo ""
echo "Checking 1Password item: $ITEM_NAME..."

if ! op item get "$ITEM_NAME" --vault "$VAULT_NAME" &> /dev/null; then
    echo -e "${YELLOW}⚠${NC}  Credentials item does not exist"
    echo "Creating credentials item with placeholders..."

    # Create item with all required fields as placeholders
    op item create \
        --category="Secure Note" \
        --title="$ITEM_NAME" \
        --vault="$VAULT_NAME" \
        "REVOLUT_API_KEY[concealed]=<your-revolut-api-key-here>" \
        "TELEGRAM_BOT_TOKEN[concealed]=<your-telegram-bot-token-optional>" \
        "TELEGRAM_CHAT_ID[concealed]=<your-telegram-chat-id-optional>" \
        &> /dev/null

    echo -e "${GREEN}✓${NC} Credentials item created with placeholder fields"
    echo ""
    echo "The following fields were created:"
    echo "  • REVOLUT_API_KEY (required - add your API key)"
    echo "  • REVOLUT_PRIVATE_KEY (will be auto-generated)"
    echo "  • REVOLUT_PUBLIC_KEY (will be auto-generated)"
    echo "  • TELEGRAM_BOT_TOKEN (optional)"
    echo "  • TELEGRAM_CHAT_ID (optional)"
else
    echo -e "${GREEN}✓${NC} Credentials item exists"

    # Ensure all required fields exist (for existing items)
    echo "Ensuring all required fields are present..."

    # Check and add missing fields
    if ! op item get "$ITEM_NAME" --vault "$VAULT_NAME" --fields REVOLUT_API_KEY &> /dev/null; then
        op item edit "$ITEM_NAME" --vault "$VAULT_NAME" \
            "REVOLUT_API_KEY[concealed]=<your-revolut-api-key-here>" &> /dev/null
    fi

    if ! op item get "$ITEM_NAME" --vault "$VAULT_NAME" --fields TELEGRAM_BOT_TOKEN &> /dev/null; then
        op item edit "$ITEM_NAME" --vault "$VAULT_NAME" \
            "TELEGRAM_BOT_TOKEN[concealed]=<your-telegram-bot-token-optional>" &> /dev/null
    fi

    if ! op item get "$ITEM_NAME" --vault "$VAULT_NAME" --fields TELEGRAM_CHAT_ID &> /dev/null; then
        op item edit "$ITEM_NAME" --vault "$VAULT_NAME" \
            "TELEGRAM_CHAT_ID[concealed]=<your-telegram-chat-id-optional>" &> /dev/null
    fi

    echo -e "${GREEN}✓${NC} All required credential fields are present"
fi

# Check if config item exists (separate from credentials)
echo ""
echo "Checking 1Password configuration item: $CONFIG_ITEM_NAME..."

if ! op item get "$CONFIG_ITEM_NAME" --vault "$VAULT_NAME" &> /dev/null; then
    echo -e "${YELLOW}⚠${NC}  Configuration item does not exist"
    echo "Creating configuration item with defaults..."

    # Create config item with default values
    op item create \
        --category="Secure Note" \
        --title="$CONFIG_ITEM_NAME" \
        --vault="$VAULT_NAME" \
        "TRADING_MODE[text]=paper" \
        "RISK_LEVEL[text]=conservative" \
        "BASE_CURRENCY[text]=EUR" \
        "TRADING_PAIRS[text]=BTC-EUR,ETH-EUR" \
        "DEFAULT_STRATEGY[text]=market_making" \
        "INITIAL_CAPITAL[text]=10000" \
        &> /dev/null

    echo -e "${GREEN}✓${NC} Configuration item created with defaults"
    echo ""
    echo "Default configuration:"
    echo "  • TRADING_MODE: paper"
    echo "  • RISK_LEVEL: conservative"
    echo "  • BASE_CURRENCY: EUR"
    echo "  • TRADING_PAIRS: BTC-EUR,ETH-EUR"
    echo "  • DEFAULT_STRATEGY: market_making"
    echo "  • INITIAL_CAPITAL: 10000"
else
    echo -e "${GREEN}✓${NC} Configuration item exists"
fi

# Check if private key exists in 1Password
echo ""
echo "Checking for Ed25519 keys in 1Password..."

private_key_exists=false
public_key_exists=false

if op item get "$ITEM_NAME" --vault "$VAULT_NAME" --fields REVOLUT_PRIVATE_KEY &> /dev/null; then
    private_key_exists=true
fi

if op item get "$ITEM_NAME" --vault "$VAULT_NAME" --fields REVOLUT_PUBLIC_KEY &> /dev/null; then
    public_key_exists=true
fi

if [ "$private_key_exists" = true ] && [ "$public_key_exists" = true ]; then
    echo -e "${GREEN}✓${NC} Ed25519 keys already exist in 1Password"
else
    echo -e "${YELLOW}⚠${NC}  Ed25519 keys not found in 1Password"
    echo ""
    echo "Generating new Ed25519 key pair..."

    # Create temporary directory for keys
    TEMP_DIR=$(mktemp -d)
    trap 'rm -rf "$TEMP_DIR"' EXIT

    # Generate keys to temp location
    if ! openssl genpkey -algorithm Ed25519 -out "$TEMP_DIR/revolut_private.pem" 2>/dev/null; then
        echo -e "${RED}✗${NC} Failed to generate Ed25519 private key" >&2
        exit 1
    fi

    if ! openssl pkey -in "$TEMP_DIR/revolut_private.pem" -pubout -out "$TEMP_DIR/revolut_public.pem" 2>/dev/null; then
        echo -e "${RED}✗${NC} Failed to derive Ed25519 public key from private key" >&2
        exit 1
    fi
    echo -e "${GREEN}✓${NC} Keys generated"

    # Read key contents
    private_key_content=$(cat "$TEMP_DIR/revolut_private.pem")
    public_key_content=$(cat "$TEMP_DIR/revolut_public.pem")

    # Store in 1Password
    echo "Storing private key in 1Password..."
    op item edit "$ITEM_NAME" --vault "$VAULT_NAME" \
        "REVOLUT_PRIVATE_KEY[concealed]=$private_key_content" \
        &> /dev/null

    echo "Storing public key in 1Password..."
    op item edit "$ITEM_NAME" --vault "$VAULT_NAME" \
        "REVOLUT_PUBLIC_KEY[concealed]=$public_key_content" \
        &> /dev/null

    echo -e "${GREEN}✓${NC} Keys stored securely in 1Password"
    echo ""
    echo "================================================="
    echo "IMPORTANT: Your Public Key"
    echo "================================================="
    echo "Copy this public key and register it on Revolut X:"
    echo ""
    echo "$public_key_content"
    echo ""
    echo "================================================="
    echo ""

    # Temp directory and keys will be automatically deleted by trap
fi

# Check if API credentials exist
echo ""
echo "Checking for API credentials in 1Password..."

api_key_exists=false
if op item get "$ITEM_NAME" --vault "$VAULT_NAME" --fields REVOLUT_API_KEY &> /dev/null; then
    api_key=$(op item get "$ITEM_NAME" --vault "$VAULT_NAME" --fields REVOLUT_API_KEY)
    if [ -n "$api_key" ] && [ "$api_key" != "" ] && [ "$api_key" != "<your-revolut-api-key-here>" ]; then
        api_key_exists=true
    fi
fi

if [ "$api_key_exists" = true ]; then
    echo -e "${GREEN}✓${NC} API credentials found in 1Password"
else
    echo -e "${YELLOW}⚠${NC}  API credentials not configured"
    echo ""
    echo "You'll need to add your Revolut API credentials manually:"
    echo ""
    echo "  op item edit $ITEM_NAME --vault $VAULT_NAME \\"
    echo "    REVOLUT_API_KEY[concealed]=\"your-api-key\""
    echo ""
    echo "Or use the interactive setup:"
    echo "  make ops"
    echo ""
fi

# Create necessary directories
echo ""
echo "Creating required directories..."
mkdir -p logs data
echo -e "${GREEN}✓${NC} Directories created: logs/, data/"

# Install dependencies
echo ""
echo "Installing dependencies with uv..."
uv sync
echo -e "${GREEN}✓${NC} Dependencies installed"

echo ""
echo "================================================="
echo "Setup Complete!"
echo "================================================="
echo ""
echo -e "${GREEN}✓${NC} uv virtual environment ready"
echo -e "${GREEN}✓${NC} Python $python_version configured"
echo -e "${GREEN}✓${NC} 1Password vault configured"
echo -e "${GREEN}✓${NC} Credentials item created: $ITEM_NAME"
echo -e "${GREEN}✓${NC} Configuration item created: $CONFIG_ITEM_NAME"
echo -e "${GREEN}✓${NC} Ed25519 keys stored securely in 1Password"
echo -e "${GREEN}✓${NC} Dependencies installed"
echo ""
echo "Next steps:"
echo ""
echo "1. Register your public key on Revolut X:"
echo "   https://revolut.com/business/merchant-api"
echo ""
echo "2. Add your Revolut API credentials:"
echo ""
echo "   Option A - Interactive setup (recommended):"
echo "     make ops"
echo ""
echo "   Option B - Direct CLI:"
echo "     op item edit $ITEM_NAME --vault $VAULT_NAME \\"
echo "       REVOLUT_API_KEY[concealed]=\"your-api-key-here\""
echo ""
echo "   Option C - Use 1Password app:"
echo "     Open 1Password → $VAULT_NAME → $ITEM_NAME"
echo "     Replace the placeholder values with your actual credentials"
echo ""
echo "3. (Optional) Configure Telegram notifications:"
echo "   op item edit $ITEM_NAME --vault $VAULT_NAME \\"
echo "     TELEGRAM_BOT_TOKEN[concealed]=\"your-bot-token\" \\"
echo "     TELEGRAM_CHAT_ID[concealed]=\"your-chat-id\""
echo ""
echo "4. (Optional) Modify trading configuration:"
echo "   make opconfig-show    # View current config"
echo "   make opconfig-set KEY=TRADING_MODE VALUE=live"
echo "   make opconfig-set KEY=RISK_LEVEL VALUE=moderate"
echo ""
echo "5. View your credentials (to verify):"
echo "   make opshow"
echo ""
echo "6. Test in paper mode (REQUIRED before live trading):"
echo "   uv run python run.py --strategy market_making --mode paper"
echo ""
echo "7. View all bot options:"
echo "   uv run python run.py --help"
echo ""
echo "8. Check 1Password status anytime:"
echo "   make opstatus"
echo ""
echo "================================================="
echo -e "${YELLOW}⚠️  IMPORTANT SECURITY NOTES${NC}"
echo "================================================="
echo "• All credentials are stored in 1Password ONLY"
echo "• No keys or credentials are stored on disk"
echo "• ALWAYS test in paper mode before live trading"
echo "• Never commit credentials to version control"
echo "================================================="
echo ""
