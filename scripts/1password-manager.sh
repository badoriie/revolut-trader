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
ENV_FILE=".env"
ENV_TEMPLATE=".env.example"

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

# Store credentials in 1Password
store_credentials() {
    print_info "Storing credentials in 1Password..."

    if [ ! -f "$ENV_FILE" ]; then
        print_error ".env file not found"
        return 1
    fi

    ensure_op_ready || return 1
    ensure_vault_exists

    # Check if item already exists
    if op item get "$ITEM_NAME" --vault "$VAULT_NAME" &> /dev/null; then
        print_warning "Item already exists: $ITEM_NAME"
        read -p "Do you want to update it? (y/N): " confirm
        if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
            print_info "Cancelled"
            return 0
        fi

        # Delete existing item
        op item delete "$ITEM_NAME" --vault "$VAULT_NAME"
        print_info "Deleted existing item"
    fi

    # Read .env file and create 1Password item
    print_info "Creating 1Password item from .env..."

    # Build the template JSON
    cat > /tmp/op-template.json <<EOF
{
  "title": "$ITEM_NAME",
  "category": "SECURE_NOTE",
  "vault": {
    "name": "$VAULT_NAME"
  },
  "fields": [
EOF

    first_field=true
    while IFS= read -r line || [ -n "$line" ]; do
        # Skip empty lines and comments
        if [[ -z "$line" ]] || [[ "$line" =~ ^[[:space:]]*# ]]; then
            continue
        fi

        # Parse KEY=VALUE
        if [[ "$line" =~ ^([^=]+)=(.*)$ ]]; then
            key="${BASH_REMATCH[1]}"
            value="${BASH_REMATCH[2]}"

            # Remove quotes from value
            value="${value%\"}"
            value="${value#\"}"
            value="${value%\'}"
            value="${value#\'}"

            # Add comma if not first field
            if [ "$first_field" = false ]; then
                echo "," >> /tmp/op-template.json
            fi
            first_field=false

            # Add field to JSON
            cat >> /tmp/op-template.json <<EOF
    {
      "id": "$(echo $key | tr '[:upper:]' '[:lower:]')",
      "label": "$key",
      "type": "CONCEALED",
      "value": "$value"
    }
EOF
        fi
    done < "$ENV_FILE"

    # Close JSON
    cat >> /tmp/op-template.json <<EOF

  ]
}
EOF

    # Create the item
    op item create --template /tmp/op-template.json
    rm /tmp/op-template.json

    print_success "Credentials stored in 1Password"
    print_info "Vault: $VAULT_NAME"
    print_info "Item: $ITEM_NAME"
}

# Retrieve credentials from 1Password
retrieve_credentials() {
    print_info "Retrieving credentials from 1Password..."

    ensure_op_ready || return 1

    if ! op item get "$ITEM_NAME" --vault "$VAULT_NAME" &> /dev/null; then
        print_error "Item not found: $ITEM_NAME"
        print_info "Run: make 1password-store"
        return 1
    fi

    # Get all fields
    fields=$(op item get "$ITEM_NAME" --vault "$VAULT_NAME" --fields label)

    # Create .env file
    print_info "Writing credentials to $ENV_FILE..."
    echo "# Generated from 1Password on $(date)" > "$ENV_FILE"
    echo "# Vault: $VAULT_NAME" >> "$ENV_FILE"
    echo "# Item: $ITEM_NAME" >> "$ENV_FILE"
    echo "" >> "$ENV_FILE"

    for field in $fields; do
        value=$(op item get "$ITEM_NAME" --vault "$VAULT_NAME" --fields "$field" 2>/dev/null)
        if [ $? -eq 0 ] && [ -n "$value" ]; then
            echo "${field}=${value}" >> "$ENV_FILE"
        fi
    done

    print_success "Credentials retrieved and written to $ENV_FILE"
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

    # Get all fields and show them masked
    fields=$(op item get "$ITEM_NAME" --vault "$VAULT_NAME" --fields label)

    for field in $fields; do
        value=$(op item get "$ITEM_NAME" --vault "$VAULT_NAME" --fields "$field" 2>/dev/null)
        if [ $? -eq 0 ] && [ -n "$value" ]; then
            # Mask the value (show first 4 chars)
            masked_value="${value:0:4}***"
            echo "  ${field}=${masked_value}"
        fi
    done

    echo ""
    print_info "To see full values, use: op item get $ITEM_NAME --vault $VAULT_NAME"
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

# Setup wizard
setup_wizard() {
    echo ""
    print_info "1Password Setup Wizard for Revolut Trader"
    echo "=========================================="
    echo ""

    # Check 1Password CLI
    if ! check_op_installed; then
        print_error "1Password CLI is not installed"
        print_info "Please install from: https://developer.1password.com/docs/cli/get-started/"
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

    # Check if .env exists
    if [ -f "$ENV_FILE" ]; then
        print_info "Found existing .env file"
        read -p "Do you want to store these credentials in 1Password? (y/N): " confirm

        if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
            store_credentials
        fi
    else
        print_warning ".env file not found"
        print_info "Please create .env file first, then run: make 1password-store"
    fi

    echo ""
    print_success "Setup complete!"
    echo ""
    print_info "Next steps:"
    echo "  1. Store credentials: make 1password-store"
    echo "  2. Retrieve credentials: make 1password-retrieve"
    echo "  3. Check status: make 1password-status"
}

# Main command handler
case "${1:-}" in
    store)
        store_credentials
        ;;
    retrieve)
        retrieve_credentials
        ;;
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
    *)
        echo "Usage: $0 {store|retrieve|show|delete|status|setup}"
        echo ""
        echo "Commands:"
        echo "  store     - Store credentials from .env to 1Password"
        echo "  retrieve  - Retrieve credentials from 1Password to .env"
        echo "  show      - Show stored credentials (masked)"
        echo "  delete    - Delete credentials from 1Password"
        echo "  status    - Check 1Password status"
        echo "  setup     - Run setup wizard"
        exit 1
        ;;
esac