# Copilot Instructions

## Commands

**Package manager**: `uv` — prefix with `uv run`

```bash
# Development
just install/test/lint/format/typecheck/security/check/pre-commit/env
uv run pytest tests/unit/test_risk_manager.py -v  # single test file
uv run pytest tests/unit/test_risk_manager.py::TestClass::test_name -v  # single test

# Trading
revt run [--strategy momentum] [--risk moderate] [--pairs BTC-EUR,ETH-EUR]
revt run --env dev|int|prod [--mode live]  # env auto-detected from git

# Backtest
revt backtest [--strategy momentum] [--days 30] [--hf] [--compare] [--matrix]
revt db backtests  # view results
revt db export     # export CSV

# Database
revt db stats | analytics --days 30 | encrypt-setup | encrypt-status | report --days 30

# API
revt api test | ready

# Config
revt ops [--show|--status]
revt config show | set KEY value

# Telegram
revt telegram start
```

## Architecture

**Entry**: `cli/run.py` → `TradingBot` → async loop per pair

**Envs**: `dev` (mock API, paper only) | `int` (real API, paper only) | `prod` (real API, paper default, live allowed)

**Trading Mode**: Paper default. Live only in prod, requires `TRADING_MODE=live` in 1Password + confirmation (`--confirm-live` bypasses). `INITIAL_CAPITAL` required for paper; live fetches real balance.

**Flow**: batch tickers → `strategy.analyze()` → `executor.execute_signal()` → `risk_manager.validate()` → place order → persist. Portfolio saved every 60s.

**Shutdown**: cancel orders → close losing → close profitable (trailing stop) → save. All bot positions closed.

**Strategies**: 6 types inherit `BaseStrategy`. Config in 1Password (`revolut-trader-strategy-{name}`). Optional calibration fields per strategy.

**Config**: Pydantic + 1Password. Required fields → `RuntimeError`. Optional: `MAX_CAPITAL`, `SHUTDOWN_TRAILING_STOP_PCT`, `SHUTDOWN_MAX_WAIT_SECONDS`, `LOG_LEVEL`, `INTERVAL`, `BACKTEST_DAYS`, `BACKTEST_INTERVAL`, `MAKER_FEE_PCT`, `TAKER_FEE_PCT`, `MAX_ORDER_VALUE`, `MIN_ORDER_VALUE`.

**Persistence**: SQLite per env (`revt-data/{env}.db`). Fernet encryption. WARNING+ logs auto-saved.

**Mock API**: `dev` uses `MockRevolutAPIClient`. No network, no creds. Factory: `create_api_client()`.

**Safety**: Pre-existing crypto never touched. SELL guard. Trading pairs must end `-{BASE_CURRENCY}`. Separate API keys per env.

**Tests**: Coverage ≥97%. `tests/conftest.py` sets `ENVIRONMENT=dev`. Safety in `tests/safety/`, math in `tests/unit/test_calculations.py`.

**CI/CD**: `ci.yml` (lint/test), `sonarcloud.yml`, `backtest.yml`, `release.yml` (commitizen semver), `diagrams.yml`.

## Key Files

| File                                  | Purpose                                                             |
| ------------------------------------- | ------------------------------------------------------------------- |
| `src/bot.py`                          | Main orchestrator                                                   |
| `src/config.py`                       | Pydantic + 1Password                                                |
| `src/api/{client,mock_client}.py`     | Real/mock API (Ed25519 auth)                                        |
| `src/models/{domain,db}.py`           | Domain models, SQLAlchemy ORM                                       |
| `src/risk_management/risk_manager.py` | Risk validation                                                     |
| `src/execution/executor.py`           | Order execution                                                     |
| `src/strategies/`                     | Strategy implementations                                            |
| `src/utils/`                          | 1Password, DB, encryption, indicators, fees, telegram, rate limiter |
| `src/backtest/engine.py`              | Backtest (mirrors live)                                             |
| `tests/`                              | Tests (≥97% coverage)                                               |
| `cli/`                                | CLI commands                                                        |
| `docs/revolut-x-api-docs.md`          | **API reference**                                                   |
| `docs/`                               | Documentation                                                       |

## Commit Convention

`<type>[scope]: <description>` — types: `feat|fix|docs|refactor|test|chore|perf|ci|style`
Breaking: `feat!:` or `BREAKING CHANGE:` footer
Helper: `uv run cz commit`

## Rules

### Environment Parity

Identical code paths. Only data source differs. Never `if environment == "dev"`. `if trading_mode == "paper"` only for execution, not logic/fees/accounting. `_execute_paper_order` and `_execute_live_order` populate same fields.

### API Docs — Source of Truth

`docs/revolut-x-api-docs.md` = reality. Hierarchy: API docs → tests → code. Check docs before touching API code. If code contradicts docs, fix code.

### TDD

1. Check `docs/revolut-x-api-docs.md`
1. Write failing test
1. Minimal code to pass
1. Refactor

Coverage ≥97% in `tests/safety/` (critical), `tests/unit/test_calculations.py` (math), `tests/unit/` (other).

### Financial Calculations

```python
# NEVER: price: float = 100.5
# ALWAYS: price: Decimal = Decimal("100.5")
```

ORM: `Numeric(20, 10)`, never `Float`. Never `float()` before storing.

### Configuration

User values → 1Password only. No code defaults (except `ENVIRONMENT` from env). Required fields → `RuntimeError` with fix command. `make setup` creates all fields (idempotent).

### Database Encryption

Always on. Auto-generates key. Encrypt sensitive fields only (not categoricals for SQL filtering).

### No Plaintext Sensitive Data

Logs/backtest → encrypted DB. Export via `make db-export-csv`.

### Code Quality

- All public functions: type hints + docstring
- Cognitive complexity ≤15. Extract helpers, early returns, flat flow.

### Documentation

Every change updates: `README.md`, docstrings, `CLAUDE.md`, this file, `docs/{END_USER_GUIDE,DEVELOPER_GUIDE}.md`
