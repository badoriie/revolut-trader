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
1. Log in to [Revolut X web app](https://www.revolut.com/business/merchant-api)
1. Navigate to API settings
1. Create new API key
1. Paste your public key
1. Copy the generated API key (64 characters)

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
1. **Position Limits**: Prevent over-exposure
1. **Daily Loss Limits**: Auto-stop on bad days
1. **Stop Loss/Take Profit**: Automatic exits
1. **Real-time Monitoring**: Telegram alerts
1. **Comprehensive Logging**: Full audit trail

## Monitoring

### Logs

Check `logs/trading.log` for detailed activity:

```bash
tail -f logs/trading.log
```

### Trading Data

The bot uses a **hybrid persistence system** combining SQLite database (primary) with JSON backup:

#### Database Storage (Primary)

- **Database File**: `data/trading.db` - SQLite database for fast queries
- **Portfolio Snapshots**: Time-series data saved immediately for real-time analytics
- **Trade History**: All completed trades with indexed queries
- **Session Tracking**: Each bot run is tracked with start/end metrics
- **Backtest Results**: All backtest runs with performance metrics and analytics
- **Log Entries** (optional): Critical events and errors stored for analysis

#### JSON Backup (Secondary)

- **Portfolio Snapshots**: `data/portfolio_snapshots.json` - Daily backup
- **Trade History**: `data/trade_history.json` - All completed trades
- **Session Data**: `data/current_session.json` - Current session state

#### Data Management Commands

```bash
# Show database statistics
make db-stats

# Show trading analytics (last 30 days)
make db-analytics

# Show backtest results (last 10 runs)
make db-backtests

# Export data to JSON files
make db-export

# Export to CSV for analysis
make db-export-csv

# Migrate to PostgreSQL (for production)
make db-migrate
```

#### Data Saving Schedule

- **Database**: Immediately after each trade, snapshot, and backtest run
- **JSON Backup**: Daily at midnight (last 7 days)
- **Periodic Save**: Every 10 iterations (~10 minutes)
- **On Shutdown**: Final state saved to both systems
- **Backtest Results**: Saved to database and JSON after each backtest run

#### Database Encryption

**Protect sensitive trading data** with application-level encryption:

```bash
# Setup encryption (one-time)
make db-encrypt-setup

# Check encryption status
make db-encrypt-status
```

**How it works:**

- 🔐 Generates Fernet encryption key using industry-standard cryptography
- 🔑 Stores key securely in 1Password vault (never in files or code)
- ✅ Automatically encrypts sensitive text fields before database storage
- 🔄 Transparently decrypts when loading data for bot operations
- 📊 Financial metrics remain queryable for analytics (not encrypted)
- ⚠️ Gracefully falls back to plaintext if encryption not enabled

**What gets encrypted:**

- Trading strategy names (e.g., "market_making", "momentum")
- Risk level settings (e.g., "conservative", "aggressive")
- Trading mode (e.g., "paper", "live")
- Symbol lists (e.g., ["BTC-USD", "ETH-USD"])
- Log messages and module names (may contain sensitive details)

**What is NOT encrypted (needed for SQL analytics):**

- Financial amounts (balances, P&L, prices, quantities)
- Timestamps and dates
- Trade counts and statistics
- Order IDs and status codes

**Key management:**

- Encryption key never stored in code, config files, or database
- Retrieved from 1Password on each bot startup
- If encryption key is lost, encrypted data becomes unreadable
- To regenerate key: run `make db-encrypt-setup` again (loses old data)

**Important notes:**

- This is **field-level encryption**, not full database encryption
- The database file itself is still readable in IDE tools (schema visible)
- Encrypted fields appear as gibberish in database browsers
- For full database encryption (entire .db file), use SQLCipher instead

#### Migration to PostgreSQL

The bot is designed for easy migration from SQLite to PostgreSQL:

```bash
# Export current data as backup
make db-export

# Migrate to PostgreSQL
make db-migrate
# Enter: postgresql://user:password@localhost/trading
```

This data persists across bot restarts and can be used for:

- Performance analysis with SQL queries
- Backtesting validation
- Trade journal and tax reporting
- Real-time analytics without parsing JSON files

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
make help               # Show all commands
make setup              # Complete project setup
make install            # Install/update dependencies
make pre-commit-install # Install pre-commit hooks
make pre-commit         # Run pre-commit hooks manually
make test               # Run tests with coverage
make lint               # Check code quality
make format             # Format code
make typecheck          # Run mypy type checking
make check              # Run all quality checks
make clean              # Remove cache files
```

### Pre-commit Hooks

The project uses pre-commit hooks to maintain code quality. Install them once:

```bash
make pre-commit-install
```

The hooks will automatically run on every commit and check:

- Code formatting (ruff)
- Linting (ruff)
- Type checking (mypy)
- Security issues (bandit)
- Common issues (trailing whitespace, merge conflicts, etc.)

To run hooks manually on all files:

```bash
make pre-commit
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
uv run ruff format src/ tests/ cli/
uv run ruff check --fix src/ tests/ cli/
```

### Type Checking

```bash
make typecheck

# Or directly
uv run mypy src/ cli/
```

## Performance Tips

1. Start with conservative risk in paper mode
1. Test each strategy separately before using multi-strategy
1. Monitor for at least 24 hours in paper mode
1. Start live trading with small amounts
1. Gradually increase position sizes as confidence grows

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

______________________________________________________________________

**Happy Trading! 🚀** (But seriously, start with paper mode!)
