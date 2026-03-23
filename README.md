# Revolut Trader: Algorithmic Trading Bot

[![CI](https://github.com/badoriie/revolut-trader/actions/workflows/ci.yml/badge.svg)](https://github.com/badoriie/revolut-trader/actions/workflows/ci.yml)

A production-ready algorithmic trading bot for Revolut X Crypto API with multiple strategies, robust risk management, and comprehensive monitoring.

## Features

- **6 Strategies**: Market Making, Momentum, Mean Reversion, Multi-Strategy, Breakout, Range Reversion
- **3 Risk Levels**: Conservative, Moderate, Aggressive — with position limits, stop-loss, daily loss limits
- **3 Environments**: Dev (mock API), Int (real API, paper only), Prod (real API, paper or live)
- **3 Trading Modes**: Backtesting, Paper Trading, Live Trading
- **Secure**: Separate API keys per environment in 1Password — zero disk footprint for secrets
- **Encrypted DB**: Separate DB per environment, sensitive fields encrypted with Fernet, key in 1Password
- **Monitoring**: Database analytics, CSV export

## Quick Start

```bash
# 1. Complete setup (creates 1Password items for dev/int/prod)
make setup

# 2. Run in dev environment (paper mode, mock API — no API key needed)
make run-dev

# For int/prod (real API):
make ops ENV=int          # store your Revolut API credentials
make opshow ENV=int       # verify stored values
make run-int              # run with real API in paper mode
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

## Environments & Branches

The project uses three environments with a single `main` branch. CI selects the environment based on the trigger:

| Environment | CI Trigger              | API                  | Trading Mode | DB File        | Make Target     |
| ----------- | ----------------------- | -------------------- | ------------ | -------------- | --------------- |
| **dev**     | Push to feature branch  | Mock (no real calls) | Paper only   | `data/dev.db`  | `make run-dev`  |
| **int**     | PR to `main`            | Real Revolut X API   | Paper only   | `data/int.db`  | `make run-int`  |
| **prod**    | Manual release workflow | Real Revolut X API   | Live only    | `data/prod.db` | `make run-prod` |

### Branch Flow

```
feature branches → PR to main
```

- **Feature branches** — all development happens here, pushes trigger dev CI
- **PR to `main`** — integration testing with int environment (real API, paper mode)
- **Manual release** — production validation via Actions console (requires "I UNDERSTAND" confirmation)

Each environment has its own 1Password items:

- `revolut-trader-credentials-{env}` — API keys
- `revolut-trader-config-{env}` — trading configuration

**Trading mode** is derived from the environment (not configurable separately):

- dev/int → paper (simulated trading)
- prod → live (real money)

### Paper Trading

```bash
make run-dev     # dev environment (mock API, paper mode)
make run-int     # int environment (real API, paper mode — staging ground)

# Or with options
ENVIRONMENT=dev uv run python cli/run.py --env dev --strategy momentum --risk moderate
```

### Live Trading

**WARNING**: Uses real money. Only available in prod environment. Test thoroughly in paper mode first!

```bash
make run-prod   # with safety confirmation
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

| Strategy            | Best For                       | Key Indicators                  |
| ------------------- | ------------------------------ | ------------------------------- |
| **Market Making**   | Stable markets, high liquidity | Bid-ask spread                  |
| **Momentum**        | Trending markets               | EMA(12/26), RSI                 |
| **Mean Reversion**  | Range-bound markets            | Bollinger Bands                 |
| **Breakout**        | Volatile markets, breakouts    | Rolling high/low, RSI           |
| **Range Reversion** | Ranging markets                | 24h high/low range position     |
| **Multi-Strategy**  | Mixed conditions               | Weighted consensus of all above |

## Risk Levels

| Level        | Max Position | Max Daily Loss | Max Open Positions | Stop Loss |
| ------------ | ------------ | -------------- | ------------------ | --------- |
| Conservative | 1.5%         | 3%             | 3                  | 1.5%      |
| Moderate     | 3%           | 5%             | 5                  | 2.5%      |
| Aggressive   | 5%           | 10%            | 8                  | 4%        |

## Project Structure

```
revolut-trader/
├── .github/
│   ├── workflows/
│   │   ├── ci.yml        # CI pipeline (lint, typecheck, security, tests)
│   │   ├── backtest.yml  # Manual backtest matrix (configurable via Actions console)
│   │   └── release.yml   # Manual production release workflow
│   ├── dependabot.yml    # Automated dependency updates
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── ISSUE_TEMPLATE/   # Bug report & feature request forms
├── src/
│   ├── api/              # Revolut API client (Ed25519 auth)
│   ├── strategies/       # 6 trading strategies
│   ├── risk_management/  # Risk controls and position sizing
│   ├── execution/        # Order execution and position management
│   ├── backtest/         # Backtesting engine
│   ├── models/           # Domain models + SQLAlchemy ORM
│   ├── utils/            # 1Password, indicators, persistence, encryption
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

Trading data is stored in an encrypted SQLite database per environment (`data/dev.db`, `data/int.db`, `data/prod.db`).

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
make typecheck        # pyright src/ cli/
make check            # all of the above + tests
make pre-commit       # run all pre-commit hooks
```

### CI Pipeline

GitHub Actions workflows:

- **CI** (`.github/workflows/ci.yml`) — runs on push to feature branches (dev) and PRs to `main` (int):
  - Lint & Format — ruff check + format verification
  - Type Check — pyright strict checking on `src/` and `cli/`
  - Security Scan — bandit static analysis
  - Tests — pytest with coverage as high as possible (currently ≥ 97%)
- **Backtest Matrix** (`.github/workflows/backtest.yml`) — manual workflow with configurable parameters (strategies, risk levels, days, interval, pairs, capital) via Actions console
- **Release** (`.github/workflows/release.yml`) — manual workflow for production validation from `main` (requires "I UNDERSTAND" confirmation)

Dependabot targets `main` — dependency PRs trigger int CI automatically.

#### Required GitHub Secret

The backtest matrix workflow requires a 1Password service account token to fetch real market data:

```bash
# Add to GitHub repo → Settings → Secrets and variables → Actions:
#   Name:  OP_SERVICE_ACCOUNT_TOKEN
#   Value: ops_xxxx... (1Password service account token with read access to revolut-trader vault)
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

## Documentation

See [docs/README.md](docs/README.md) for the full documentation index.

## Warnings

- Cryptocurrency trading is highly risky — you can lose your entire investment
- Past performance does not guarantee future results
- Start with paper trading, only invest what you can afford to lose
- This software is provided as-is with no guarantees

## License

MIT License — use at your own risk
