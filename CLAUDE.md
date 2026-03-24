# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Package manager: `uv`** — always prefix Python commands with `uv run`.

```bash
# Install dependencies
uv sync --extra dev

# Run tests with coverage
make test                    # or: uv run pytest --cov=src --cov-report=term-missing

# Run a single test file
uv run pytest tests/unit/test_risk_manager.py -v

# Run a single test
uv run pytest tests/unit/test_risk_manager.py::TestClassName::test_name -v

# Lint, format, type-check
make lint                    # ruff check
make format                  # ruff format + ruff check --fix
make typecheck               # pyright src/ cli/
make check                   # all of the above + tests

# Run pre-commit hooks on all files
make pre-commit

# Run the bot
make run-mock                # mock API (dev env, no credentials needed)
make run-paper               # paper trading (int env, real API, no real trades)
make run-live                # live trading (prod env, REAL MONEY — requires confirmation)

# Backtesting (results saved to encrypted DB, not files)
make backtest                # STRATEGY=momentum DAYS=30 ENV=dev
make db-backtests            # view stored results (uses ENV)
make db-export-csv           # export results to CSV

# Database (per environment: data/dev.db, data/int.db, data/prod.db)
make db                      # show database overview (ENV=dev)
make db-stats                # show database statistics
make db-analytics            # trading analytics (DAYS=30)
make db-encrypt-setup        # generate and store encryption key in 1Password
make db-encrypt-status       # check if encryption is active

# API utilities (use ENV to select API keys)
make api-test ENV=int
make api-balance ENV=int
make api-ticker SYMBOL=BTC-EUR ENV=int

# 1Password / credential management (per environment)
make setup                   # first-time setup: creates items for dev/int/prod
make ops ENV=dev             # interactively set API key for dev environment
make opshow ENV=dev          # show stored values for dev (masked)
make opstatus                # check 1Password CLI status
make opconfig-show ENV=dev   # show trading configuration for dev
make opconfig-set KEY=RISK_LEVEL VALUE=moderate ENV=dev
```

## Architecture

**Entry point**: `cli/run.py` (sets `ENVIRONMENT` early) → creates `TradingBot` (`src/bot.py`) → async main loop over trading pairs.

**Environments & Branches** (`src/config.py`): Three environments (dev, int, prod) with a single `main` branch. Branch flow: `feature branches → PR to main`. Dev checks are handled by pre-commit hooks locally. CI runs on PRs to `main` with `ENVIRONMENT=int`. Production release is a manual workflow with `ENVIRONMENT=prod`. The `ENVIRONMENT` env var (or `--env` CLI arg) determines which 1Password items and DB file to use. `TRADING_MODE` is derived from environment (dev/int → paper, prod → live) and is not stored in 1Password. `INITIAL_CAPITAL` is only required for paper mode (dev/int); prod fetches real balance from the API. Each environment has separate credentials (`revolut-trader-credentials-{env}`) and config (`revolut-trader-config-{env}`) items in 1Password, and a separate database (`data/{env}.db`).

**Mock API** (`src/api/mock_client.py`): `ENVIRONMENT=dev` uses `MockRevolutAPIClient` — an in-process mock of all 17 API endpoints returning realistic fake data matching `docs/revolut-x-api-docs.md`. No network calls, no credentials, no Ed25519 keys. The `create_api_client()` factory in `src/api/__init__.py` selects mock vs real client based on environment. `int` and `prod` use the real `RevolutAPIClient`. The API client uses `RateLimiter` (`src/utils/rate_limiter.py`) to respect API rate limits.

**Component hierarchy:**

- `TradingBot` (orchestrator) owns: `RevolutAPIClient` or `MockRevolutAPIClient`, `RiskManager`, `OrderExecutor`, `BaseStrategy`, `DatabasePersistence`
- Each trading loop iteration: fetch market data → `strategy.analyze()` → `risk_manager.validate()` → `executor.execute()` → persist
- Graceful shutdown: `bot.stop()` → `executor.graceful_shutdown(trailing_stop_pct, max_wait_seconds)` (cancel orders → close losing positions immediately → close profitable positions via trailing stop or immediately) → save final state → end DB session. **Guarantee: all bot-opened positions are closed before the bot exits (EUR → trade → EUR contract).**

**Strategies** (`src/strategies/`): All inherit `BaseStrategy`. Six implementations: `MarketMakingStrategy`, `MomentumStrategy`, `MeanReversionStrategy`, `MultiStrategy` (weighted voting), `BreakoutStrategy`, `RangeReversionStrategy`. Adding a strategy only requires a new file implementing `BaseStrategy`.

**Configuration** (`src/config.py`): Pydantic-based. `ENVIRONMENT` comes from `os.environ` (infrastructure-level). `TRADING_MODE` is derived from environment (not stored in 1Password). All other trading config (strategy, risk level, pairs, capital) is fetched from the environment-specific 1Password items at startup — there are no code-level defaults. `INITIAL_CAPITAL` is only required for paper mode (dev/int). `MAX_CAPITAL` is optional for all environments — when set, it caps the cash balance at startup so the bot never trades with more than this amount (e.g., account holds 50,000 EUR but MAX_CAPITAL=5,000 → bot uses 5,000). `SHUTDOWN_TRAILING_STOP_PCT` is optional — when set (e.g., `0.5` for 0.5%), profitable positions on shutdown wait for a trailing stop before closing; when absent, profitable positions are closed immediately. `SHUTDOWN_MAX_WAIT_SECONDS` is optional — hard timeout (default 120s) before force-closing a profitable position whose trailing stop has not triggered. Config fails fast with actionable error messages if 1Password fields are missing.

**Persistence** (`src/utils/db_persistence.py`): SQLite via SQLAlchemy. Each environment uses its own DB file (`data/dev.db`, `data/int.db`, `data/prod.db`). All data stays in the encrypted database. Writes immediately after each trade and on shutdown. Use `make db-export-csv ENV=prod` for on-demand exports.

**Security**: Separate API keys per environment in 1Password. All sensitive fields are encrypted at the application layer using Fernet symmetric encryption before being written to the database. The encryption key is stored exclusively in 1Password (`DATABASE_ENCRYPTION_KEY` in the environment-specific credentials item). If no key exists, one is auto-generated on first run. Encrypted fields: `SessionDB.trading_pairs`, `LogEntryDB.message`. Categorical fields (`strategy`, `risk_level`, `trading_mode`) are plaintext for SQL filterability — they are not sensitive. No plaintext log files are written to disk.

**1Password** (`src/utils/onepassword.py`): Wraps the `op` CLI. Environment-aware via `get_credentials_item(env)` / `get_config_item(env)` functions. Retrieves API keys, private keys, bot tokens, trading configuration, and the database encryption key from the environment-specific items. Tests use `tests/mocks/mock_onepassword.py` to avoid real 1Password calls.

**Technical indicators** (`src/utils/indicators.py`): SMA, EMA, RSI, Bollinger Bands — all O(1) incremental updates (no history recalculation).

**Execution** (`src/execution/executor.py`): `OrderExecutor` handles order placement, fill tracking, position management, and graceful shutdown via the API client. On shutdown, `graceful_shutdown(trailing_stop_pct, max_wait_seconds)` runs three phases: (1) cancel all pending orders; (2) close losing positions immediately at market; (3) close profitable/breakeven positions via trailing stop wait then market close (or immediately if no trailing stop configured). **Guarantee: `self.positions` is empty when `graceful_shutdown` returns — no bot-opened position is ever left open.** Returns a `ShutdownSummary` so the bot can update its cash balance. Pre-existing crypto (not opened by the bot) is never touched: the SELL guard in `execute_signal` blocks any sell for a symbol with no tracked position.

**Tests** (`tests/`):

- `tests/conftest.py` — shared fixtures, sets `ENVIRONMENT=dev` before `Settings` singleton is created
- `tests/safety/` — safety-critical tests (order limits, position sizing, loss limits, environment restrictions, graceful shutdown)
- `tests/safety/test_environment.py` — environment stage safety tests (live mode restricted to prod)
- `tests/safety/test_graceful_shutdown.py` — graceful shutdown safety tests (order cancellation, all-positions closure, trailing stop logic, timeout force-close)
- `tests/safety/test_pre_existing_crypto.py` — pre-existing crypto protection tests (SELL guard, shutdown scope)
- `tests/safety/test_currency_mismatch.py` — trading pair / BASE_CURRENCY mismatch validation tests
- `tests/unit/` — component unit tests (calculations, indicators, risk manager)
- `tests/mocks/` — mock 1Password for testing (supports per-environment mocks)
- Coverage must be as high as possible (currently ≥ 97%, enforced by CI and pre-commit)

**CLI** (`cli/`): Entry points for all operations — `run.py` (bot runner), `backtest.py` (single strategy), `backtest_compare.py` (multi-strategy comparison + matrix), `api_test.py` (API connectivity), `db_manage.py` (database management and export).

**CI/CD** (`.github/workflows/`): `ci.yml` (lint, typecheck, security, tests on PRs), `sonarcloud.yml` (code scanning on PRs), `backtest.yml` (manual backtest matrix), `release.yml` (manual production release with semver tag and auto-generated changelog).

## Mandatory Rules

These are enforced by pre-commit hooks and must be followed:

### Revolut X API Docs — The Single Source of Truth

`docs/revolut-x-api-docs.md` is the authoritative reference for **all** API behaviour.
Every endpoint path, request body shape, response shape, field name, field type, and valid
enum value must be taken from that document — never guessed, inferred from existing code, or
assumed from another source.

**The hierarchy is strict and non-negotiable:**

```
Revolut X API docs  →  tests  →  code
```

1. **API docs define reality.** If the docs say the order creation response is
   `{"data": [{"venue_order_id": ..., "state": "new"}]}`, that is what the tests must assert
   and what the code must produce. Do not let existing code shapes influence what you believe
   the API returns.

1. **Tests encode the API contract.** Every field name, every valid enum string, every
   response envelope must appear in tests exactly as the docs describe them. A test that uses
   `"state": "open"` when the API only allows `"new" | "pending_new" | "partially_filled" | "filled" | "cancelled" | "rejected" | "replaced"` is a wrong test — fix the test first.

1. **Code must pass the tests.** Implementation details (domain models, mappers, client
   methods) are written or corrected to make the API-aligned tests pass — never the reverse.

**Practical checklist before touching any API-related code or test:**

- Open `docs/revolut-x-api-docs.md` and locate the relevant endpoint section.
- Verify the HTTP method, path, required/optional params, and exact response shape.
- Confirm every enum value used in tests (`"new"`, `"buy"`, `"limit"`, …) appears verbatim
  in the docs.
- If existing code or tests contradict the docs, the docs win — update code and tests.

### TDD — Non-Negotiable

Write tests **first**, then code. Every new feature or fix:

1. Consult `docs/revolut-x-api-docs.md` to establish the API contract.
1. Write the test against the API contract → confirm it fails.
1. Write minimal code → confirm it passes.
1. Refactor if needed.

Safety-critical tests go in `tests/safety/`, financial math in `tests/unit/test_calculations.py`, everything else in `tests/unit/`.

### Financial Calculations — Always `Decimal`

```python
# NEVER
price: float = 100.5

# ALWAYS
from decimal import Decimal

price: Decimal = Decimal("100.5")
```

All monetary columns in the ORM use `Numeric(20, 10)` — never `Float`. Never cast financial values with `float()` before storing.

### Configuration — No Code Defaults

Trading config must come from 1Password exclusively. Two exceptions:

- `ENVIRONMENT` — comes from `os.environ` (set by the Makefile or `--env` CLI arg) because it must be known before 1Password items can be resolved.
- `TRADING_MODE` — derived from environment (dev/int → paper, prod → live). Not stored in 1Password.

`INITIAL_CAPITAL` is only required for paper mode (dev/int); prod fetches the real balance from the API. `MAX_CAPITAL` is optional for all environments — when set, it caps the cash balance at startup so the bot never uses more than this amount. `SHUTDOWN_TRAILING_STOP_PCT` (optional, e.g. `0.5`) — trailing stop percentage for profitable positions on shutdown. `SHUTDOWN_MAX_WAIT_SECONDS` (optional, e.g. `120`) — hard timeout before force-closing profitable positions on shutdown. If a required field is missing, raise a `RuntimeError` with instructions on how to fix it (e.g., `make opconfig-set KEY=... VALUE=... ENV=dev`). Never silently fall back to a hardcoded default.

### Database Encryption — Always On

Database encryption is mandatory. `DatabaseEncryption` auto-generates a key in 1Password if none exists. Never disable encryption or add a plaintext fallback. Only encrypt genuinely sensitive fields — not categoricals that need SQL filtering.

### No Plaintext Files for Sensitive Data

- No log files on disk — logs go to the encrypted database via `save_log_entry()`
- No JSON result exports — backtest results go to the encrypted database
- Use `make db-export-csv` for on-demand exports when needed

### All Functions — Type Hints + Docstrings

Every public function needs type annotations on all parameters and return value, plus a docstring explaining what it does and (for critical functions) why it matters.

### Documentation Updates — Always, No Exceptions

Every code change **must** include corresponding documentation updates. This is not optional — treat documentation as part of task completion. A change is not done until the docs are updated.

- `README.md` — feature additions, configuration changes, usage instructions
- `CHANGELOG.md` — auto-generated from GitHub Releases by the release workflow (do not edit manually)
- Inline docstrings — logic changes, new functions, modified behavior
- `CLAUDE.md` — architectural changes, new components, workflow changes
- `docs/` files — API changes, strategy changes, development guidelines

Claude Code must handle this proactively without being asked.

## Key Files

| File                                  | Purpose                                                         |
| ------------------------------------- | --------------------------------------------------------------- |
| `src/bot.py`                          | Main orchestrator — start here to understand flow               |
| `src/config.py`                       | Pydantic config + 1Password loading                             |
| `src/api/client.py`                   | Real Revolut X API client (Ed25519 auth, httpx)                 |
| `src/api/mock_client.py`              | Mock API client for dev environment (no real API calls)         |
| `src/models/domain.py`                | Core domain models (Position, Order, Trade, Signal, etc.)       |
| `src/models/db.py`                    | SQLAlchemy 2.0 ORM models (SQLite, Numeric columns, WAL mode)   |
| `src/risk_management/risk_manager.py` | Risk validation and position sizing                             |
| `src/execution/executor.py`           | Order execution and position management                         |
| `src/strategies/base_strategy.py`     | Abstract base all strategies implement                          |
| `src/utils/onepassword.py`            | 1Password CLI wrapper (environment-aware item names)            |
| `src/utils/db_persistence.py`         | SQLAlchemy session management, all CRUD operations + CSV export |
| `src/utils/db_encryption.py`          | Fernet encryption; key auto-generated in 1Password              |
| `src/utils/indicators.py`             | Technical indicators (SMA, EMA, RSI, Bollinger Bands)           |
| `src/utils/rate_limiter.py`           | API rate limiting                                               |
| `src/backtest/engine.py`              | Backtest engine with pagination, slippage, fees, Sharpe ratio   |
| `tests/conftest.py`                   | Shared fixtures, ENVIRONMENT=dev setup                          |
| `tests/mocks/mock_onepassword.py`     | Use this in tests instead of real 1Password                     |
| `docs/revolut-x-api-docs.md`          | Revolut X API reference (source of truth for all API code)      |
| `docs/DEVELOPMENT_GUIDELINES.md`      | TDD workflow, coding standards, contribution rules              |
| `docs/ARCHITECTURE.md`                | Component details and data flow                                 |
| `docs/BACKTESTING.md`                 | Backtesting guide, metrics, interpretation                      |
