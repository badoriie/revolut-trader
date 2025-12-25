#!/bin/bash

echo "================================================="
echo "Revolut Trader Setup Script"
echo "================================================="
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.11 or higher."
    exit 1
fi

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Found Python $python_version"

# Create config directory
echo ""
echo "Creating config directory..."
mkdir -p config

# Generate Ed25519 key pair if not exists
if [ ! -f "config/revolut_private.pem" ]; then
    echo ""
    echo "Generating Ed25519 key pair..."
    openssl genpkey -algorithm Ed25519 -out config/revolut_private.pem
    openssl pkey -in config/revolut_private.pem -pubout -out config/revolut_public.pem

    echo ""
    echo "✓ Key pair generated successfully!"
    echo ""
    echo "================================================="
    echo "IMPORTANT: Your Public Key"
    echo "================================================="
    echo "Copy this public key and register it on Revolut X:"
    echo ""
    cat config/revolut_public.pem
    echo ""
    echo "================================================="
else
    echo "✓ Key pair already exists"
fi

# Note: .env file NOT needed - credentials stored in 1Password
echo ""
echo "================================================="
echo "IMPORTANT: Credential Storage"
echo "================================================="
echo "This bot uses 1Password for secure credential storage."
echo "No .env file is needed or used."
echo ""
echo "After key generation, store credentials in 1Password:"
echo "  make 1password-setup"
echo ""

# Create necessary directories
echo ""
echo "Creating required directories..."
mkdir -p logs data

echo ""
echo "================================================="
echo "Setup Complete!"
echo "================================================="
echo ""
echo "Next steps:"
echo "1. Register your public key on Revolut X web app"
echo ""
echo "2. Install and configure 1Password CLI:"
echo "   brew install --cask 1password-cli"
echo "   eval \$(op signin)"
echo ""
echo "3. Store credentials in 1Password:"
echo "   make 1password-setup"
echo ""
echo "4. Test in paper mode (RECOMMENDED):"
echo "   python run.py --strategy market_making --mode paper"
echo ""
echo "5. View all options:"
echo "   python run.py --help"
echo ""
echo "⚠️  ALWAYS test in paper mode before live trading!"
echo "⚠️  All credentials are stored in 1Password (no .env file)"
echo "================================================="
