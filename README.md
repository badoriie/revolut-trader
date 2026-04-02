# Revolut Trader: Algorithmic Trading Bot

![Beta](https://img.shields.io/badge/status-beta-orange)
[![CI](https://github.com/badoriie/revolut-trader/actions/workflows/ci.yml/badge.svg)](https://github.com/badoriie/revolut-trader/actions/workflows/ci.yml)
[![Quality Gate](https://sonarcloud.io/api/project_badges/measure?project=badoriie_revolut-trader&metric=alert_status&token=88e993a3010057e454d15b0ab129bdf4f710e675)](https://sonarcloud.io/summary/new_code?id=badoriie_revolut-trader)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=badoriie_revolut-trader&metric=coverage&token=88e993a3010057e454d15b0ab129bdf4f710e675)](https://sonarcloud.io/summary/new_code?id=badoriie_revolut-trader)
[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=badoriie_revolut-trader&metric=security_rating&token=88e993a3010057e454d15b0ab129bdf4f710e675)](https://sonarcloud.io/summary/new_code?id=badoriie_revolut-trader)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A production-ready algorithmic trading bot for Revolut X Crypto API with multiple strategies, robust risk management, and comprehensive monitoring.

## Architecture

See [Architecture Overview](docs/ARCHITECTURE.md) for component hierarchy, trading loop data flow, and graceful shutdown diagrams.

## Features

- **6 Strategies**: Market Making, Momentum, Mean Reversion, Multi-Strategy, Breakout, Range Reversion
- **3 Risk Levels**: Conservative, Moderate, Aggressive — with position limits, stop-loss, daily loss limits
- **Safe by Default**: Paper trading mode for all environments unless explicitly enabled to LIVE
- **3 Environments**: Dev (mock API), Int (real API), Prod (real API) — separate credentials & DBs
- **Backtesting**: Strategy comparison with real historical data, configurable via Actions console
- **Secure**: Separate API keys per environment in 1Password — zero disk footprint for secrets
- **Encrypted DB**: Separate DB per environment, sensitive fields encrypted with Fernet, key in 1Password
- **Graceful Shutdown**: Cancels pending orders, closes losing positions immediately, and closes profitable positions via trailing stop (or immediately); guarantee: all bot-opened positions are closed before exit
- **Monitoring**: Database analytics, CSV export, optional Telegram notifications (analytics report)

## Trading Modes

The bot supports two trading modes:

- **Paper Trading** (default) — simulates trades without real money; safe for testing
- **Live Trading** — uses real funds from your Revolut account

**All environments default to paper mode.** To enable live trading:

```bash
# Option 1: Set in 1Password config (permanent)
revt config set TRADING_MODE live

# Option 2: Override per-run (temporary)
revt run --mode live
```

Both methods require confirmation before proceeding. See [Enabling Live Trading](#enabling-live-trading) for safety checklist.

## Quick Start

### Download the binary (recommended)

Download `revt` for your platform from the [latest release](../../releases/latest):

| Platform                                 | File                |
| ---------------------------------------- | ------------------- |
| Linux x86_64 (Standard servers/desktops) | `revt-linux-x86_64` |
| Linux ARM64 (Raspberry Pi 4+, Graviton)  | `revt-linux-arm64`  |

```bash
# Linux x86_64
curl -L https://github.com/badoriie/revolut-trader/releases/latest/download/revt-linux-x86_64 \
  -o revt && chmod +x revt && sudo mv revt /usr/local/bin/

# Linux ARM64 (Raspberry Pi 4+ / ARM servers)
curl -L https://github.com/badoriie/revolut-trader/releases/latest/download/revt-linux-arm64 \
  -o revt && chmod +x revt && sudo mv revt /usr/local/bin/
```

Then:

```bash
revt ops                  # store your Revolut API key in 1Password
revt config show          # verify your trading configuration
revt run                  # start paper trading (safe default)
```

See [1Password Setup](docs/1PASSWORD.md) for credential configuration.

### Updating

Keep `revt` up to date (preserves your data and configuration):

```bash
revt update               # updates binary or pulls latest code
```

The `update` command:

- **Binary users**: Downloads and replaces the binary with the latest release
- **Source users**: Pulls latest changes from git and updates dependencies
- **Safe**: Never touches `data/` folder or 1Password configuration

### Run from source (developers)

```bash
uv sync --extra dev
make run              # paper trading (env auto-detected from git context)
make run MODE=live    # live trading (requires confirmation)
```

## Usage

### Backtesting

```bash
make backtest                              # 30 days, default strategy
make backtest STRATEGY=momentum DAYS=90    # specific strategy and period
make backtest-hf                           # high-frequency: 1-min candles (closest to live 5s polling)
make backtest-hf STRATEGY=breakout DAYS=7  # high-frequency with specific strategy
make db-backtests                          # view stored results
make db-export-csv                         # export to CSV
```

See [Backtesting Guide](docs/BACKTESTING.md) for metrics, interpretation, and best practices.

## Environments

The project uses three environments, each with separate credentials and databases:

| Environment | API                  | Default Mode | DB File        | Purpose                          |
| ----------- | -------------------- | ------------ | -------------- | -------------------------------- |
| **dev**     | Mock (no real calls) | Paper        | `data/dev.db`  | Development & testing            |
| **int**     | Real Revolut X API   | Paper        | `data/int.db`  | Pre-production validation        |
| **prod**    | Real Revolut X API   | Paper        | `data/prod.db` | Production (live opt-in allowed) |

Each environment has its own 1Password items:

- `revolut-trader-credentials-{env}` — API keys, encryption key
- `revolut-trader-config-{env}` — trading configuration

**Environment is auto-detected** from git context:

- Tagged commit → `prod`
- `main` branch → `int`
- Other branches → `dev`
- Binary → `prod` (always)

Override with `--env dev|int|prod` or `ENV=...` make variable when needed.

### Mock Trading (dev)

```bash
make run             # on a feature branch, env auto-detects to dev — mock API, no credentials needed
```

### Paper Trading (int)

```bash
make run             # on main branch, env auto-detects to int — real API, simulated trades
```

### Enabling Live Trading

**CRITICAL**: Live mode uses real money from your Revolut account. Only enable after thorough paper trading.

**Safety Checklist:**

- [ ] Paper-traded successfully for at least 7 days
- [ ] Reviewed all trades and verified strategy performance
- [ ] Set `MAX_CAPITAL` to limit exposure (e.g., 5000 EUR)
- [ ] Use conservative risk level initially
- [ ] Understand you can lose your entire investment

**Enable live trading:**

```bash
# Option 1: Set permanently in 1Password
revt config set TRADING_MODE live

# Option 2: Override per-run (for testing)
revt run --mode live

# Both require confirmation: Type "I UNDERSTAND" to proceed
```

**Disable live trading:**

```bash
revt config set TRADING_MODE paper   # back to safe default
```

### API Testing

```bash
make api-test            # authenticated connection test
make api-ready           # check API permissions (view + trade)
make telegram-test       # verify Telegram is configured

# Via revt CLI (for additional endpoints):
revt api balance                           # account balances
revt api ticker --symbol BTC-EUR           # single ticker
revt api tickers --symbols BTC-EUR,ETH-EUR # multiple tickers
revt api candles --symbol BTC-EUR          # historical candles
```

## Strategies

| Strategy            | Best For                       | Key Indicators                  | Interval | Order Type | Min Signal |
| ------------------- | ------------------------------ | ------------------------------- | -------- | ---------- | ---------- |
| **Market Making**   | Stable markets, high liquidity | Bid-ask spread                  | 5s       | Limit      | 0.30       |
| **Breakout**        | Volatile markets, breakouts    | Rolling high/low, RSI           | 5s       | Market     | 0.70       |
| **Momentum**        | Trending markets               | EMA(12/26), RSI                 | 10s      | Market     | 0.60       |
| **Multi-Strategy**  | Mixed conditions               | Weighted consensus of all above | 10s      | Limit      | 0.55       |
| **Mean Reversion**  | Range-bound markets            | Bollinger Bands                 | 15s      | Limit      | 0.50       |
| **Range Reversion** | Ranging markets                | 24h high/low range position     | 15s      | Limit      | 0.50       |

**Interval** — how often the trading loop runs for this strategy (overridable via `--interval`).
**Order Type** — MARKET for speed-sensitive strategies (momentum, breakout); LIMIT for patience-oriented strategies.
**Min Signal** — minimum confidence score [0.0–1.0] required before executing a trade; filters noise-driven signals.

## Risk Levels

Risk parameters are set per level and further refined per strategy (stop-loss and take-profit shown below are the strategy overrides):

| Level        | Max Position | Max Daily Loss | Max Open Positions | Stop Loss |
| ------------ | ------------ | -------------- | ------------------ | --------- |
| Conservative | 1.5%         | 3%             | 3                  | 1.5%      |
| Moderate     | 3%           | 5%             | 5                  | 2.5%      |
| Aggressive   | 5%           | 10%            | 8                  | 4%        |

Per-strategy stop-loss / take-profit overrides (applied on top of the risk-level baseline). Position size always comes from the risk level — this ensures conservative/moderate/aggressive produce different trade sizes:

| Strategy            | Stop Loss    | Take Profit  |
| ------------------- | ------------ | ------------ |
| **Market Making**   | 0.5%         | 0.3%         |
| **Momentum**        | 2.5%         | 4.0%         |
| **Breakout**        | 3.0%         | 5.0%         |
| **Mean Reversion**  | 1.0%         | 1.5%         |
| **Range Reversion** | 1.0%         | 1.5%         |
| **Multi-Strategy**  | *(baseline)* | *(baseline)* |

Additionally, you can set `MAX_CAPITAL` to limit how much money the bot can trade with, regardless of your account balance:

```bash
make opconfig-set KEY=MAX_CAPITAL VALUE=5000 ENV=prod
```

## Trading Fees

Fee tracking is built into every trade. Fees are deducted from the cash balance in real-time and stored alongside each trade record for accurate P&L reporting.

| Order Type | Role  | Fee   |
| ---------- | ----- | ----- |
| LIMIT      | Maker | 0%    |
| MARKET     | Taker | 0.09% |

- **LIMIT orders** (market making, mean reversion, range reversion, multi-strategy) — no fee.
- **MARKET orders** (momentum, breakout, and all SL/TP close orders) — 0.09% taker fee deducted from realized P&L and cash balance.

Fee data is available in trade history exports and the analytics report (`total_fees`, `losing_trades` fields).

## Project Structure

```
revolut-trader/
├── .github/
│   ├── workflows/
│   │   ├── ci.yml            # CI pipeline (lint, typecheck, security, tests)
│   │   ├── sonarcloud.yml    # SonarCloud code scanning
│   │   ├── backtest.yml      # Manual backtest matrix (via Actions console)
│   │   ├── release.yml       # Manual production release workflow
│   │   └── diagrams.yml      # Auto-generate architecture diagrams (pyreverse)
│   ├── copilot-instructions.md  # GitHub Copilot instructions (mirrors CLAUDE.md)
│   └── dependabot.yml        # Automated dependency updates
├── src/
│   ├── api/                  # Revolut API client (Ed25519 auth) + mock client
│   ├── strategies/           # 6 trading strategies (base + implementations)
│   ├── risk_management/      # Risk controls and position sizing
│   ├── execution/            # Order execution and position management
│   ├── backtest/             # Backtesting engine
│   ├── models/               # Domain models (domain.py) + SQLAlchemy ORM (db.py)
│   ├── utils/                # 1Password, indicators, persistence, encryption, rate limiter
│   ├── config.py             # Pydantic config (loaded from 1Password)
│   └── bot.py                # Main orchestrator
├── cli/                      # CLI entry points
│   ├── revt.py               # Main CLI tool (revt command)
│   ├── run.py                # Bot runner (--env, --strategy, --risk)
│   ├── backtest.py           # Single strategy backtest
│   ├── backtest_compare.py   # Multi-strategy comparison + matrix
│   ├── api_test.py           # API connectivity and endpoint testing
│   ├── db_manage.py          # Database management and export
│   ├── analytics_report.py   # Comprehensive analytics report with charts
│   ├── telegram_control.py   # Telegram Control Plane (always-on bot commands)
│   └── view_logs.py          # View decrypted logs from database
├── build/                    # Build configuration
│   └── revt.spec             # PyInstaller spec for revt binary
├── tests/
│   ├── conftest.py           # Fixtures, ENVIRONMENT=dev setup
│   ├── test_config.py        # Configuration loading and validation tests
│   ├── safety/               # Safety-critical tests (order limits, position sizing)
│   ├── unit/                 # Component unit tests
│   └── mocks/                # Mock 1Password for testing
├── docs/                     # Documentation
│   ├── END_USER_GUIDE.md         # Quick start: download binary, configure, trade
│   ├── DEVELOPER_GUIDE.md        # Development setup, advanced usage, make commands
│   ├── ARCHITECTURE.md           # Component details and data flow
│   ├── BACKTESTING.md            # Backtesting guide
│   ├── DEVELOPMENT_GUIDELINES.md # TDD, coding standards, contribution rules
│   ├── 1PASSWORD.md              # Credential and config setup
│   ├── revolut-x-api-docs.md     # Revolut X API reference (source of truth)
│   └── README.md                 # Documentation index
└── Makefile                  # All project commands
```

## Database & Monitoring

Trading data is stored in an encrypted SQLite database per environment (`data/dev.db`, `data/int.db`, `data/prod.db`).

```bash
make db               # database overview (stats + analytics + recent backtests)
make db-stats         # database statistics
make db-analytics     # trading analytics (DAYS=30)
make db-backtests     # backtest results
make db-report        # comprehensive analytics report with charts (DAYS=30)
make db-export        # export data to a directory
make db-export-csv    # export to CSV
make db-encrypt-setup  # generate and store encryption key in 1Password
make db-encrypt-status # check encryption status
```

See [Architecture](docs/ARCHITECTURE.md) for component details and data flow.

## Development

```bash
make test             # run tests with coverage
make lint             # ruff check
make format           # ruff format + ruff check --fix
make typecheck        # pyright src/ cli/
make check            # all of the above + tests
make pre-commit       # run all pre-commit hooks
```

### CI Pipeline

GitHub Actions workflows:

- **CI** (`.github/workflows/ci.yml`) — runs on PRs to `main` (`ENVIRONMENT=dev`, merge blocked until all pass) and on post-merge pushes to `main` (`ENVIRONMENT=int`):
  - Lint & Format — ruff check + format verification
  - Type Check — pyright strict checking on `src/` and `cli/`
  - Security Scan — bandit static analysis
  - Tests — pytest with coverage (≥ 97%)
- **SonarCloud** (`.github/workflows/sonarcloud.yml`) — code scanning on PRs and post-merge pushes to `main`: bugs, vulnerabilities, code smells, coverage tracking
- **Backtest Matrix** (`.github/workflows/backtest.yml`) — manual workflow with configurable parameters (strategies, risk levels, days, interval, pairs, capital) via Actions console
- **Release** (`.github/workflows/release.yml`) — manual workflow for production release from `main`. Commitizen auto-detects the next semver from conventional commits since the last tag, updates `pyproject.toml`, generates `CHANGELOG.md` incrementally, creates the git tag, and publishes a GitHub Release with the new changelog section as release notes. Inputs: confirm `"I UNDERSTAND"` + optional `increment` override (`patch`/`minor`/`major`) for when auto-detection isn't sufficient
- **Diagrams** (`.github/workflows/diagrams.yml`) — auto-generates architecture class diagrams using pyreverse on pushes to `main` or manual trigger; uploads diagrams as artifacts (90-day retention)

Dependabot targets `main` — dependency PRs trigger int CI automatically.

#### Required GitHub Secrets

```bash
# Add to GitHub repo → Settings → Secrets and variables → Actions:

# 1Password service account token (backtest workflow — real market data):
#   Name:  OP_SERVICE_ACCOUNT_TOKEN
#   Value: ops_xxxx...

# Personal access token (release workflow — push CHANGELOG.md past branch protection):
#   Name:  RELEASE_PAT
#   Value: github_pat_xxxx... (fine-grained PAT with Contents: Read and write)

# SonarCloud token (code scanning):
#   Name:  SONAR_TOKEN
#   Value: (generate at sonarcloud.io → My Account → Security)
```

### Commit Messages

All commits must follow [Conventional Commits](https://www.conventionalcommits.org/), enforced by a `commit-msg` pre-commit hook:

```
feat(strategy): add breakout strategy with ATR-based stops
fix(executor): prevent duplicate orders on rapid signal changes
docs: add backtesting guide to README
chore(deps): upgrade httpx to 0.28
feat!: replace REST polling with WebSocket feed   ← breaking change
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `ci`, `style`.

Use `uv run cz commit` for an interactive prompt, or write the message manually — the hook validates it on `git commit`.

After cloning, run `make pre-commit-install` to register both the `pre-commit` and `commit-msg` hooks.

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

| Document                                                 | Purpose                                                |
| -------------------------------------------------------- | ------------------------------------------------------ |
| [End User Guide](docs/END_USER_GUIDE.md)                 | Quick start: download binary, configure, start trading |
| [Developer Guide](docs/DEVELOPER_GUIDE.md)               | Development setup, advanced usage, make commands       |
| [Architecture](docs/ARCHITECTURE.md)                     | Component details and data flow                        |
| [Backtesting Guide](docs/BACKTESTING.md)                 | Metrics, interpretation, best practices                |
| [Development Guidelines](docs/DEVELOPMENT_GUIDELINES.md) | TDD workflow, coding standards, contribution rules     |
| [1Password Setup](docs/1PASSWORD.md)                     | Credential and configuration management                |
| [Revolut X API Docs](docs/revolut-x-api-docs.md)         | API reference (source of truth for all API code)       |

## Warnings

- Cryptocurrency trading is highly risky — you can lose your entire investment
- Past performance does not guarantee future results
- Start with paper trading, only invest what you can afford to lose
- This software is provided as-is with no guarantees

## License

MIT License — use at your own risk
