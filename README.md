# Revolut Trader: Algorithmic Trading Bot

A production-ready algorithmic trading bot for Revolut X Crypto API with multiple strategies, robust risk management, and comprehensive monitoring.

## Features

- **4 Strategies**: Market Making, Momentum, Mean Reversion, Multi-Strategy (weighted consensus)
- **3 Risk Levels**: Conservative, Moderate, Aggressive — with position limits, stop-loss, daily loss limits
- **3 Trading Modes**: Backtesting, Paper Trading, Live Trading
- **Secure**: All credentials and config in 1Password — zero disk footprint for secrets
- **Encrypted DB**: Sensitive fields encrypted with Fernet, key in 1Password
- **Monitoring**: Telegram notifications, database analytics, CSV export

## Quick Start

```bash
# 1. Complete setup (uv + 1Password + keys + deps)
make setup

# 2. Store your Revolut API key
make ops

# 3. Verify
make opstatus
make opshow

# 4. Run in paper mode
make run-paper
```

See [1Password Setup](docs/1PASSWORD.md) for detailed credential configuration.

## Usage

### Backtesting

```bash
make backtest                              # 30 days, default strategy
make backtest STRATEGY=momentum DAYS=90    # specific strategy and period
make db-backtests                          # view stored results
make db-export-csv                         # export to CSV
```

See [Backtesting Guide](docs/BACKTESTING.md) for metrics, interpretation, and best practices.

### Paper Trading

```bash
make run-paper

# Or with options
uv run python cli/run.py --strategy momentum --risk moderate --mode paper
```

### Live Trading

**WARNING**: Uses real money. Test thoroughly in paper mode first!

```bash
make run-live   # with safety confirmation
```

### API Testing

```bash
make api-test                                          # connection check
make api-balance                                       # account balances
make api-ticker SYMBOL=BTC-EUR                         # single ticker
make api-tickers SYMBOLS=BTC-EUR,ETH-EUR,SOL-EUR      # multiple tickers
make api-candles SYMBOL=BTC-EUR INTERVAL=60 LIMIT=10   # historical candles
```

## Strategies

| Strategy           | Best For                       | Key Indicators     |
| ------------------ | ------------------------------ | ------------------ |
| **Market Making**  | Stable markets, high liquidity | Bid-ask spread     |
| **Momentum**       | Trending markets               | EMA(12/26), RSI    |
| **Mean Reversion** | Range-bound markets            | Bollinger Bands    |
| **Multi-Strategy** | Mixed conditions               | Weighted consensus |

## Risk Levels

| Level        | Max Position | Max Daily Loss | Max Open Positions | Stop Loss |
| ------------ | ------------ | -------------- | ------------------ | --------- |
| Conservative | 1.5%         | 3%             | 3                  | 1.5%      |
| Moderate     | 3%           | 5%             | 5                  | 2.5%      |
| Aggressive   | 5%           | 10%            | 8                  | 4%        |

## Project Structure

```
revolut-trader/
├── src/
│   ├── api/              # Revolut API client (Ed25519 auth)
│   ├── strategies/       # Trading strategies
│   ├── risk_management/  # Risk controls and position sizing
│   ├── execution/        # Order execution and position management
│   ├── notifications/    # Telegram alerts
│   ├── models/           # Domain models + SQLAlchemy ORM
│   ├── utils/            # 1Password, indicators, persistence, encryption
│   ├── backtest/         # Backtesting engine
│   ├── config.py         # Pydantic config (loaded from 1Password)
│   └── bot.py            # Main orchestrator
├── cli/                  # CLI entry points (run, backtest, api_test, db_manage)
├── tests/
│   ├── safety/           # Safety-critical tests
│   └── unit/             # Component unit tests
├── docs/                 # Documentation (see docs/README.md for index)
└── Makefile              # All project commands
```

## Database & Monitoring

Trading data is stored in an encrypted SQLite database (`data/trading.db`).

```bash
make db-stats         # database overview
make db-analytics     # trading analytics (DAYS=30)
make db-backtests     # backtest results
make db-export-csv    # export to CSV
make db-encrypt-status # check encryption status
```

See [Architecture](docs/ARCHITECTURE.md) for component details and data flow.

## Development

```bash
make test             # run tests with coverage
make lint             # ruff check
make format           # ruff format
make typecheck        # pyright
make check            # all of the above + tests
make pre-commit       # run all pre-commit hooks
```

See [Development Guidelines](docs/DEVELOPMENT_GUIDELINES.md) for TDD workflow, coding standards, and contribution rules.

## Troubleshooting

**API connection issues:**

```bash
make opstatus   # check 1Password auth
make opshow     # verify credentials
make api-test   # test API connectivity
```

**No signals generated:** Strategies need warmup time to collect data. Check logs and verify trading pairs.

**Telegram not working:** Verify credentials with `make opshow`, update with `make ops`.

## Documentation

See [docs/README.md](docs/README.md) for the full documentation index.

## Warnings

- Cryptocurrency trading is highly risky — you can lose your entire investment
- Past performance does not guarantee future results
- Start with paper trading, only invest what you can afford to lose
- This software is provided as-is with no guarantees

## License

MIT License — use at your own risk
