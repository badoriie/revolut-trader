# Revolut Trader: Professional Algorithmic Trading Bot

A sophisticated, production-ready algorithmic trading bot for Revolut Crypto API with multiple strategies, robust risk management, and comprehensive monitoring.

## Features

### Trading Strategies
- **Market Making**: Profit from bid-ask spreads with intelligent inventory management
- **Momentum**: Follow trends using moving averages and RSI indicators
- **Mean Reversion**: Trade price deviations using Bollinger Bands
- **Multi-Strategy**: Combine multiple strategies with weighted consensus

### Risk Management
- Configurable risk levels (Conservative, Moderate, Aggressive)
- Position size limits based on portfolio percentage
- Stop loss and take profit automation
- Daily loss limits with automatic trading suspension
- Concentration risk controls

### Trading Modes
- **Paper Trading**: Test strategies with simulated trading (no real money)
- **Live Trading**: Execute real trades on Revolut X exchange

### Monitoring & Notifications
- Telegram notifications for signals, orders, and alerts
- Comprehensive logging system
- Portfolio tracking and performance metrics
- Real-time position monitoring
- Daily trading summaries

## Quick Start

### 1. Installation

```bash
# Clone the repository
cd revolut-trader

# Install dependencies
pip install -e .

# Or install with dev dependencies
pip install -e ".[dev]"
```

### 2. Generate Revolut API Keys

#### Step 1: Generate Ed25519 Key Pair

```bash
# Create config directory
mkdir -p config

# Generate private key
openssl genpkey -algorithm Ed25519 -out config/revolut_private.pem

# Extract public key
openssl pkey -in config/revolut_private.pem -pubout -out config/revolut_public.pem

# Display public key (you'll need this for Revolut)
cat config/revolut_public.pem
```

#### Step 2: Register API Key on Revolut X

1. Log in to [Revolut X web app](https://www.revolut.com/business/revolut-x/)
2. Navigate to API settings
3. Create new API key
4. Paste your public key from `config/revolut_public.pem`
5. Copy the generated API key (64 characters)

### 3. Secure Credential Storage (Recommended: 1Password)

**For Production**: Use 1Password to store credentials securely (no .env file needed)

```bash
# Install 1Password CLI
brew install --cask 1password-cli

# Sign in
eval $(op signin)

# Store API key in 1Password
op item edit revolut-trader-credentials \
  --vault revolut-trader \
  REVOLUT_API_KEY[concealed]="your-api-key"

# Store private key in 1Password (more secure than config folder)
op item edit revolut-trader-credentials \
  --vault revolut-trader \
  REVOLUT_PRIVATE_KEY[concealed]="$(cat config/revolut_private.pem)"

# Delete local PEM file for security
rm config/revolut_private.pem config/revolut_public.pem
```

**Benefits:**
- ✅ Private keys never stored on disk
- ✅ Encrypted vault storage
- ✅ No risk of accidental git commits
- ✅ Audit trail of access
- ✅ Easy credential rotation

See [1Password Integration Guide](docs/1PASSWORD_INTEGRATION.md) for details.

**Note**: `.env` file is NOT used for credentials. All sensitive data is in 1Password only.

### 4. Setup Telegram Notifications (Optional)

Store your Telegram credentials in 1Password:

```bash
# Get bot token from @BotFather and chat ID from @userinfobot
op item edit revolut-trader-credentials \
  --vault revolut-trader \
  TELEGRAM_BOT_TOKEN[concealed]="your-telegram-bot-token" \
  TELEGRAM_CHAT_ID[concealed]="your-telegram-chat-id"
```

### 5. Run the Bot

```bash
# Paper trading with market making (RECOMMENDED for testing)
python run.py --strategy market_making --mode paper

# View all options
python run.py --help
```

## Usage Examples

### Paper Trading (Safe Testing)

```bash
# Test market making strategy
python run.py --strategy market_making --mode paper

# Test momentum strategy with moderate risk
python run.py --strategy momentum --risk moderate --mode paper

# Test mean reversion
python run.py --strategy mean_reversion --mode paper

# Test multi-strategy (combines all strategies)
python run.py --strategy multi_strategy --mode paper
```

### Live Trading (Real Money)

⚠️ **WARNING**: Live trading uses real money. Test thoroughly in paper mode first!

```bash
# Live trading with conservative risk (recommended)
python run.py --strategy market_making --risk conservative --mode live

# Live momentum trading with moderate risk
python run.py --strategy momentum --risk moderate --mode live
```

### Advanced Options

```bash
# Custom trading pairs
python run.py --strategy momentum --pairs BTC-USD,ETH-USD,SOL-USD

# Faster update interval (30 seconds)
python run.py --strategy market_making --interval 30

# Debug logging
python run.py --strategy momentum --log-level DEBUG
```

## Strategy Details

### Market Making
- Places limit orders on both sides of order book
- Profits from bid-ask spread
- Best for: High liquidity pairs, stable markets
- Parameters: spread threshold, inventory target

### Momentum
- Follows price trends using technical indicators
- Uses fast/slow moving averages and RSI
- Best for: Trending markets
- Parameters: MA periods, RSI thresholds

### Mean Reversion
- Buys oversold, sells overbought
- Uses Bollinger Bands for entry/exit
- Best for: Range-bound markets
- Parameters: lookback period, standard deviations

### Multi-Strategy
- Combines all strategies with weighted voting
- Requires consensus before trading
- Best for: Diverse market conditions
- Parameters: strategy weights, consensus threshold

## Risk Management

### Conservative (Recommended for Beginners)
- Max 1.5% per position
- Max 3% daily loss
- Max 3 open positions
- Tight stop losses (1.5%)

### Moderate
- Max 3% per position
- Max 5% daily loss
- Max 5 open positions
- Balanced stops (2.5%)

### Aggressive
- Max 5% per position
- Max 10% daily loss
- Max 8 open positions
- Wider stops (4%)

## Project Structure

```
revolut-trader/
├── src/
│   ├── api/              # Revolut API client
│   ├── strategies/       # Trading strategies
│   ├── risk_management/  # Risk controls
│   ├── execution/        # Order execution
│   ├── notifications/    # Telegram alerts
│   ├── data/            # Data models
│   ├── config.py        # Configuration
│   └── bot.py           # Main bot logic
├── tests/               # Unit tests
├── config/              # API keys
├── logs/                # Log files
├── run.py              # CLI entry point
├── .env                # Configuration
└── README.md           # This file
```

## Safety Features

1. **Paper Trading Mode**: Test without risking real money
2. **Position Limits**: Prevent over-exposure
3. **Daily Loss Limits**: Auto-stop on bad days
4. **Stop Loss/Take Profit**: Automatic exits
5. **Real-time Monitoring**: Telegram alerts
6. **Comprehensive Logging**: Full audit trail

## Monitoring

### Logs
Check `logs/trading.log` for detailed activity:

```bash
tail -f logs/trading.log
```

### Telegram Alerts
Receive real-time notifications for:
- Trading signals generated
- Orders placed/filled
- Position updates
- Risk alerts
- Daily summaries

## Important Warnings

⚠️ **LIVE TRADING RISKS**:
- Cryptocurrency trading is highly risky
- You can lose your entire investment
- Past performance doesn't guarantee future results
- Start with paper trading
- Only invest what you can afford to lose
- This software is provided as-is with no guarantees

⚠️ **SECURITY**:
- All credentials must be in 1Password (never in files)
- Never commit PEM files or API keys
- Use strong 1Password master password
- Enable 2FA on your Revolut account
- Sign in to 1Password before running: `eval $(op signin)`

## Troubleshooting

### API Connection Issues
```bash
# Verify credentials are in 1Password
op item get revolut-trader-credentials --vault revolut-trader

# Check 1Password is signed in
op account list

# Ensure public key is registered on Revolut X
```

### No Signals Generated
- Strategies need time to collect data (especially Momentum/Mean Reversion)
- Check if market conditions match strategy (e.g., trends for Momentum)
- Verify trading pairs are correct
- Check logs for specific errors

### Telegram Not Working
```bash
# Verify bot token and chat ID in .env
# Test bot independently: python -c "from telegram import Bot; Bot('YOUR_TOKEN').send_message('YOUR_CHAT_ID', 'Test')"
```

## Development

### Running Tests
```bash
pytest
```

### Code Formatting
```bash
black src/ tests/
ruff check src/ tests/
```

### Type Checking
```bash
mypy src/
```

## Performance Tips

1. Start with conservative risk in paper mode
2. Test each strategy separately before using multi-strategy
3. Monitor for at least 24 hours in paper mode
4. Start live trading with small amounts
5. Gradually increase position sizes as confidence grows

## Future Enhancements

Potential additions:
- Web dashboard for visual monitoring
- Backtesting engine with historical data
- Advanced strategies (arbitrage, grid trading)
- Database persistence for trade history
- Multi-exchange support
- WebSocket real-time price feeds

## Support

For issues and questions:
- Check logs: `logs/trading.log`
- Review Revolut API docs: https://developer.revolut.com/docs/x-api/
- File issues on GitHub

## License

MIT License - use at your own risk

## Disclaimer

This software is for educational purposes. Cryptocurrency trading carries substantial risk of loss. The authors and contributors are not responsible for any financial losses incurred through use of this software. Always do your own research and consult with financial advisors before trading.

---

**Happy Trading! 🚀** (But seriously, start with paper mode!)
