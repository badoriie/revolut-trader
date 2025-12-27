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
- **Backtesting**: Validate strategies on historical data before deploying
- **Paper Trading**: Test strategies with real-time data and simulated execution
- **Live Trading**: Execute real trades on Revolut X exchange

### Monitoring & Notifications
- **Interactive Web Dashboard**: Visualize backtests, compare strategies, monitor performance
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

# Complete setup (uv + 1Password + dependencies + key generation)
make setup
```

This single command will:
- Install/verify uv (modern Python package manager)
- Create Python 3.11+ virtual environment
- Install 1Password CLI (if needed)
- Generate Ed25519 keys securely
- Store keys in 1Password
- Install all dependencies

### 2. Configure Credentials

After running `make setup`, you'll have keys auto-generated and stored in 1Password. Now configure your Revolut API:

#### Register Public Key on Revolut X

1. Copy the public key displayed during setup (or get it with `make opshow`)
2. Log in to [Revolut X web app](https://www.revolut.com/business/merchant-api)
3. Navigate to API settings
4. Create new API key
5. Paste your public key
6. Copy the generated API key (64 characters)

#### Store API Key in 1Password

```bash
# Store your Revolut API key
op item edit revolut-trader-credentials \
  --vault revolut-trader \
  REVOLUT_API_KEY[concealed]="your-api-key-from-revolut"
```

**Security Benefits:**
- ✅ Private keys NEVER stored on disk
- ✅ Generated in temp directory, immediately stored in 1Password
- ✅ Auto-deleted after storage (zero disk footprint)
- ✅ Encrypted vault storage with audit trail
- ✅ No risk of accidental git commits

See [1Password Integration Guide](docs/1PASSWORD_INTEGRATION.md) for full details.

### 3. Setup Telegram Notifications (Optional)

```bash
# Get bot token from @BotFather and chat ID from @userinfobot
op item edit revolut-trader-credentials \
  --vault revolut-trader \
  TELEGRAM_BOT_TOKEN[concealed]="your-telegram-bot-token" \
  TELEGRAM_CHAT_ID[concealed]="your-telegram-chat-id"
```

### 4. Verify Setup

```bash
# Check 1Password status
make opstatus

# View credentials (masked)
make opshow
```

### 5. Run the Bot

```bash
# Paper trading with market making (RECOMMENDED for testing)
uv run python run.py --strategy market_making --mode paper

# View all options
uv run python run.py --help
```

## Usage Examples

### Backtesting (Historical Data Validation)

Test strategies on historical data before deploying:

```bash
# Basic backtest: 30 days of BTC-USD data
python backtest.py --strategy market_making --pairs BTC-USD --days 30

# Test multiple pairs over 90 days
python backtest.py --strategy momentum --pairs BTC-USD,ETH-USD --days 90

# Test with different risk levels and save results
python backtest.py --strategy mean_reversion --risk moderate \
  --days 60 --output ./results/backtest.json

# Test different candle intervals
python backtest.py --strategy multi_strategy --interval 60 --days 180

# Custom initial capital
python backtest.py --strategy momentum --capital 50000 --days 90
```

See [Backtesting Guide](docs/BACKTESTING.md) for detailed documentation.

### Visualization Dashboard

Launch the interactive web dashboard to visualize your results:

```bash
# Start the dashboard
streamlit run dashboard.py
```

Features:
- 📊 View backtest results with interactive charts
- 🔬 Compare multiple strategies side-by-side
- 📈 Analyze equity curves and P&L
- 📝 Review trade history

See [Dashboard Guide](docs/DASHBOARD.md) for full documentation.

### Paper Trading (Safe Testing)

```bash
# Test market making strategy
uv run python run.py --strategy market_making --mode paper

# Test momentum strategy with moderate risk
uv run python run.py --strategy momentum --risk moderate --mode paper

# Test mean reversion
uv run python run.py --strategy mean_reversion --mode paper

# Test multi-strategy (combines all strategies)
uv run python run.py --strategy multi_strategy --mode paper

# OR use Makefile shortcut
make run-paper
```

### Live Trading (Real Money)

⚠️ **WARNING**: Live trading uses real money. Test thoroughly in paper mode first!

```bash
# Live trading with conservative risk (recommended)
uv run python run.py --strategy market_making --risk conservative --mode live

# Live momentum trading with moderate risk
uv run python run.py --strategy momentum --risk moderate --mode live

# OR use Makefile (with safety confirmation)
make run-live
```

### Advanced Options

```bash
# Custom trading pairs
uv run python run.py --strategy momentum --pairs BTC-USD,ETH-USD,SOL-USD

# Faster update interval (30 seconds)
uv run python run.py --strategy market_making --interval 30

# Debug logging
uv run python run.py --strategy momentum --log-level DEBUG
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
│   ├── api/              # Revolut API client (Ed25519 auth)
│   ├── strategies/       # Trading strategies
│   ├── risk_management/  # Risk controls
│   ├── execution/        # Order execution
│   ├── notifications/    # Telegram alerts
│   ├── data/             # Data models
│   ├── utils/            # 1Password integration
│   ├── config.py         # Configuration
│   └── bot.py            # Main bot logic
├── tests/                # Unit tests
├── scripts/              # Setup and management scripts
│   ├── setup.sh          # Complete project setup
│   └── 1password-manager.sh  # Credential management
├── .claude/              # Claude Code agent configuration
├── docs/                 # Documentation
├── logs/                 # Runtime logs (gitignored)
├── data/                 # Runtime trading data (gitignored)
├── run.py                # CLI entry point
├── Makefile              # All project commands
└── README.md             # This file
```

**Note:** No `.env` or `config/*.pem` files - all credentials in 1Password only.

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
- **1Password Required**: All credentials stored exclusively in 1Password
- **Zero Disk Footprint**: Private keys never written to disk
- **Sign In First**: Always run `eval $(op signin)` before using the bot
- **Strong Password**: Use a strong 1Password master password
- **2FA**: Enable 2FA on your Revolut account
- **Never Bypass**: Don't create .env files or store keys locally

## Troubleshooting

### API Connection Issues
```bash
# Verify 1Password is signed in
make opstatus

# View credentials (masked)
make opshow

# Check credentials in 1Password
op item get revolut-trader-credentials --vault revolut-trader --format json

# Ensure public key is registered on Revolut X
```

### No Signals Generated
- Strategies need time to collect data (especially Momentum/Mean Reversion)
- Check if market conditions match strategy (e.g., trends for Momentum)
- Verify trading pairs are correct
- Check logs for specific errors: `make logs`

### Telegram Not Working
```bash
# Verify credentials are in 1Password
make opshow

# Update Telegram credentials
op item edit revolut-trader-credentials --vault revolut-trader \
  TELEGRAM_BOT_TOKEN[concealed]="your-bot-token" \
  TELEGRAM_CHAT_ID[concealed]="your-chat-id"
```

## Development

### Available Make Commands

```bash
make help      # Show all commands
make setup     # Complete project setup
make install   # Install/update dependencies
make test      # Run tests with coverage
make lint      # Check code quality
make format    # Format code
make check     # Run all quality checks
make clean     # Remove cache files
```

### Running Tests
```bash
make test

# Or directly with uv
uv run pytest --cov=src
```

### Code Formatting
```bash
make format

# Or directly
uv run ruff format src/ tests/
uv run ruff check --fix src/ tests/
```

### Type Checking
```bash
uv run mypy src/
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
