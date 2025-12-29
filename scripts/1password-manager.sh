#!/bin/bash
# 1Password Manager for Revolut Trader
# Manages credentials using 1Password CLI (op)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
VAULT_NAME="${OP_VAULT_NAME:-revolut-trader}"
ITEM_NAME="revolut-trader-credentials"
CONFIG_ITEM_NAME="revolut-trader-config"

# Function to print colored messages
print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Check if 1Password CLI is installed
check_op_installed() {
    if ! command -v op &> /dev/null; then
        return 1
    fi
    return 0
}

# Check if 1Password CLI is signed in
check_op_signin() {
    if ! op account list &> /dev/null; then
        return 1
    fi
    return 0
}

# Ensure 1Password CLI is available and signed in
ensure_op_ready() {
    if ! check_op_installed; then
        print_error "1Password CLI (op) is not installed"
        print_info "Install from: https://developer.1password.com/docs/cli/get-started/"
        return 1
    fi

    if ! check_op_signin; then
        print_warning "Not signed in to 1Password CLI"
        print_info "Running: op signin"
        eval $(op signin)
    fi

    print_success "1Password CLI is ready"
    return 0
}

# Create vault if it doesn't exist
ensure_vault_exists() {
    if ! op vault get "$VAULT_NAME" &> /dev/null; then
        print_info "Creating vault: $VAULT_NAME"
        op vault create "$VAULT_NAME"
        print_success "Vault created: $VAULT_NAME"
    else
        print_success "Vault exists: $VAULT_NAME"
    fi
}

# Show stored credentials (masked)
show_credentials() {
    print_info "Stored credentials in 1Password:"
    echo ""

    ensure_op_ready || return 1

    if ! op item get "$ITEM_NAME" --vault "$VAULT_NAME" &> /dev/null; then
        print_error "Item not found: $ITEM_NAME"
        return 1
    fi

    # Get item in JSON format
    item_json=$(op item get "$ITEM_NAME" --vault "$VAULT_NAME" --format json)

    # Parse fields using jq if available, otherwise use grep/sed
    if command -v jq &> /dev/null; then
        # Use jq to extract label and value pairs
        echo "$item_json" | jq -r '.fields[] | select(.label and .value) | "\(.label)|\(.value)"' | while IFS='|' read -r label value; do
            if [ -n "$label" ] && [ -n "$value" ]; then
                # Determine masking based on value length
                value_length=${#value}
                if [ $value_length -gt 100 ]; then
                    # Very long value (like PEM keys) - show it's set
                    masked_value="<set, ${value_length} chars>"
                elif [ $value_length -gt 20 ]; then
                    # Long value - show first 8 chars
                    masked_value="${value:0:8}***"
                else
                    # Short value - show first 4 chars
                    masked_value="${value:0:4}***"
                fi
                printf "  %-25s = %s\n" "$label" "$masked_value"
            fi
        done
    else
        # Fallback without jq - basic parsing
        print_warning "jq not found, showing field names only (install jq for better output)"
        echo "$item_json" | grep -o '"label":"[^"]*"' | sed 's/"label":"\([^"]*\)"/  \1 = <value hidden>/g'
    fi

    echo ""
    print_info "To see full values, use: op item get $ITEM_NAME --vault $VAULT_NAME --format json"
}

# Create configuration item (separate from credentials)
create_config_item() {
    print_info "Creating configuration item in 1Password..."
    echo ""

    ensure_op_ready || return 1

    # Check if config item already exists
    if op item get "$CONFIG_ITEM_NAME" --vault "$VAULT_NAME" &> /dev/null; then
        print_warning "Configuration item already exists: $CONFIG_ITEM_NAME"
        read -p "Do you want to replace it with defaults? (y/N): " confirm
        if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
            print_info "Keeping existing configuration"
            return 0
        fi

        # Delete existing config item
        op item delete "$CONFIG_ITEM_NAME" --vault "$VAULT_NAME"
        print_info "Deleted existing configuration"
    fi

    print_info "Creating configuration item with defaults..."

    # Create config item with default values
    op item create \
        --category "Secure Note" \
        --vault "$VAULT_NAME" \
        --title "$CONFIG_ITEM_NAME" \
        "TRADING_MODE[text]=paper" \
        "RISK_LEVEL[text]=conservative" \
        "BASE_CURRENCY[text]=EUR" \
        "TRADING_PAIRS[text]=BTC-EUR,ETH-EUR" \
        "DEFAULT_STRATEGY[text]=market_making" \
        "INITIAL_CAPITAL[text]=10000" \
        "notesPlain=Revolut Trading Bot Configuration - See docs/1PASSWORD_CONFIG.md"

    if [ $? -eq 0 ]; then
        print_success "Configuration item created in 1Password!"
        echo ""
        print_info "Item: $CONFIG_ITEM_NAME"
        print_info "Vault: $VAULT_NAME"
        echo ""
        print_info "Default configuration:"
        echo "  ⚙️  Trading Settings:"
        echo "     - TRADING_MODE: paper (safe simulation mode)"
        echo "     - RISK_LEVEL: conservative"
        echo "     - BASE_CURRENCY: EUR"
        echo "  📊 Trading Pairs:"
        echo "     - TRADING_PAIRS: BTC-EUR,ETH-EUR"
        echo "  🎯 Strategy:"
        echo "     - DEFAULT_STRATEGY: market_making"
        echo "  💰 Capital:"
        echo "     - INITIAL_CAPITAL: 10000"
        echo ""
        print_warning "Next steps:"
        echo "  1. View configuration:"
        echo "     make opconfig-show"
        echo ""
        echo "  2. Modify as needed:"
        echo "     make opconfig-set KEY=TRADING_MODE VALUE=live"
        echo "     make opconfig-set KEY=RISK_LEVEL VALUE=moderate"
        echo ""
        echo "  3. Documentation:"
        echo "     docs/1PASSWORD_CONFIG.md"
        echo ""
    else
        print_error "Failed to create configuration item"
        return 1
    fi
}

# Delete credentials from 1Password
delete_credentials() {
    print_warning "This will delete credentials from 1Password"
    print_info "Vault: $VAULT_NAME"
    print_info "Item: $ITEM_NAME"
    echo ""
    read -p "Are you sure? (type 'yes' to confirm): " confirm

    if [ "$confirm" != "yes" ]; then
        print_info "Cancelled"
        return 0
    fi

    ensure_op_ready || return 1

    if ! op item get "$ITEM_NAME" --vault "$VAULT_NAME" &> /dev/null; then
        print_error "Item not found: $ITEM_NAME"
        return 1
    fi

    op item delete "$ITEM_NAME" --vault "$VAULT_NAME"
    print_success "Credentials deleted from 1Password"
}

# Check 1Password status
check_status() {
    echo ""
    print_info "1Password CLI Status"
    echo "===================="
    echo ""

    if check_op_installed; then
        print_success "1Password CLI installed"
        op --version
    else
        print_error "1Password CLI not installed"
        echo ""
        return 1
    fi

    echo ""

    if check_op_signin; then
        print_success "Signed in to 1Password"
        op account list
    else
        print_warning "Not signed in to 1Password"
        echo ""
    fi

    echo ""
    print_info "Vault: $VAULT_NAME"

    if op vault get "$VAULT_NAME" &> /dev/null; then
        print_success "Vault exists"
    else
        print_warning "Vault does not exist"
    fi

    echo ""
    print_info "Item: $ITEM_NAME"

    if op item get "$ITEM_NAME" --vault "$VAULT_NAME" &> /dev/null; then
        print_success "Credentials stored in 1Password"
    else
        print_warning "Credentials not found in 1Password"
    fi

    echo ""
}

# Create sample item with placeholder values
create_sample_item() {
    print_info "Creating sample credentials item in 1Password..."

    # Check if item already exists
    if op item get "$ITEM_NAME" --vault "$VAULT_NAME" &> /dev/null; then
        print_warning "Item already exists: $ITEM_NAME"
        read -p "Do you want to replace it with a new sample? (y/N): " confirm
        if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
            print_info "Keeping existing item"
            return 0
        fi

        # Delete existing item
        op item delete "$ITEM_NAME" --vault "$VAULT_NAME"
        print_info "Deleted existing item"
    fi

    # Read PEM file if it exists
    PEM_CONTENT=""
    if [ -f "config/revolut_private.pem" ]; then
        PEM_CONTENT=$(cat config/revolut_private.pem)
        print_success "Found local PEM file - will include in 1Password"
    fi

    # Create item with sample values using op item create
    print_info "Creating credentials item..."

    if [ -n "$PEM_CONTENT" ]; then
        # If we have a PEM file, use it
        op item create \
            --category "Secure Note" \
            --vault "$VAULT_NAME" \
            --title "$ITEM_NAME" \
            "REVOLUT_API_KEY[concealed]=your-revolut-api-key-here" \
            "REVOLUT_PRIVATE_KEY[concealed]=$PEM_CONTENT" \
            "TELEGRAM_BOT_TOKEN[concealed]=your-telegram-bot-token-here" \
            "TELEGRAM_CHAT_ID[concealed]=your-telegram-chat-id-here" \
            "notesPlain=Revolut Trading Bot Credentials - API keys and tokens"
    else
        # Otherwise use placeholder for PEM too
        op item create \
            --category "Secure Note" \
            --vault "$VAULT_NAME" \
            --title "$ITEM_NAME" \
            "REVOLUT_API_KEY[concealed]=your-revolut-api-key-here" \
            "REVOLUT_PRIVATE_KEY[concealed]=paste-your-pem-file-content-here" \
            "TELEGRAM_BOT_TOKEN[concealed]=your-telegram-bot-token-here" \
            "TELEGRAM_CHAT_ID[concealed]=your-telegram-chat-id-here" \
            "notesPlain=Revolut Trading Bot Credentials - API keys and tokens"
    fi

    print_success "Credentials item created in 1Password!"
    echo ""
    print_info "Item: $ITEM_NAME"
    print_info "Vault: $VAULT_NAME"
    echo ""
    print_info "Created credentials:"
    echo "  📋 Required:"
    echo "     - REVOLUT_API_KEY: (placeholder - update with your key)"
    if [ -n "$PEM_CONTENT" ]; then
        echo "     - REVOLUT_PRIVATE_KEY: ✓ Loaded from config/revolut_private.pem"
    else
        echo "     - REVOLUT_PRIVATE_KEY: (placeholder - update with PEM content)"
    fi
    echo "  📱 Optional (for notifications):"
    echo "     - TELEGRAM_BOT_TOKEN"
    echo "     - TELEGRAM_CHAT_ID"
    echo ""
    print_warning "Next steps:"
    echo "  1. Update your credentials:"
    echo "     op item edit $ITEM_NAME --vault $VAULT_NAME"
    echo ""
    echo "  2. View stored values:"
    echo "     make opshow"
    echo ""
}

# Setup wizard
setup_wizard() {
    echo ""
    print_info "1Password Setup Wizard for Revolut Trader"
    echo "=========================================="
    echo ""

    # Check 1Password CLI
    if ! check_op_installed; then
        print_error "1Password CLI is not installed"
        echo ""
        print_info "Install with: brew install --cask 1password-cli"
        print_info "Or visit: https://developer.1password.com/docs/cli/get-started/"
        return 1
    fi

    print_success "1Password CLI is installed"
    echo ""

    # Sign in
    if ! check_op_signin; then
        print_info "Signing in to 1Password..."
        eval $(op signin)
    fi

    print_success "Signed in to 1Password"
    echo ""

    # Ask for vault name
    read -p "Vault name (default: revolut-trader): " vault_input
    if [ -n "$vault_input" ]; then
        VAULT_NAME="$vault_input"
    fi

    # Create vault if needed
    ensure_vault_exists
    echo ""

    # Create sample item
    create_sample_item

    echo ""
    print_success "Setup complete!"
    echo ""
    print_info "You can now:"
    echo "  1. Edit credentials in 1Password app"
    echo "  2. Or use CLI: op item edit $ITEM_NAME --vault $VAULT_NAME"
    echo "  3. View credentials: make 1password-show"
    echo "  4. Check status: make 1password-status"
    echo ""
}

# Main command handler
case "${1:-}" in
    show)
        show_credentials
        ;;
    delete)
        delete_credentials
        ;;
    status)
        check_status
        ;;
    setup)
        setup_wizard
        ;;
    create-config)
        create_config_item
        ;;
    *)
        echo "Usage: $0 {setup|show|status|delete|create-config}"
        echo ""
        echo "Commands:"
        echo "  setup         - Run setup wizard (create vault and store credentials)"
        echo "  show          - Show stored credentials (masked)"
        echo "  status        - Check 1Password CLI status and credentials"
        echo "  delete        - Delete credentials from 1Password"
        echo "  create-config - Create configuration item (separate from credentials)"
        echo ""
        echo "Note: This project uses 1Password for credentials and configuration."
        echo "See CREDENTIALS.md and docs/1PASSWORD_CONFIG.md for more information."
        exit 1
        ;;
esac
