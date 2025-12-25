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

# Copy .env.example to .env if not exists
if [ ! -f ".env" ]; then
    echo ""
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "✓ .env file created. Please edit it with your settings:"
    echo "  - Add your Revolut API key"
    echo "  - Configure trading pairs"
    echo "  - (Optional) Add Telegram credentials"
else
    echo "✓ .env file already exists"
fi

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
echo "2. Edit .env file with your API key:"
echo "   nano .env"
echo ""
echo "3. Test in paper mode (RECOMMENDED):"
echo "   python run.py --strategy market_making --mode paper"
echo ""
echo "4. View all options:"
echo "   python run.py --help"
echo ""
echo "⚠️  ALWAYS test in paper mode before live trading!"
echo "================================================="
