# Copilot Instructions

> The authoritative project instructions live in `CLAUDE.md` at the repo root.
> This file mirrors the tool-agnostic sections for GitHub Copilot.

## Package Manager & Commands

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

# Lint, format, type-check, security
make lint                    # ruff check
make format                  # ruff format + ruff check --fix
make typecheck               # pyright src/ cli/
make security                # bandit static security analysis
make check                   # all of the above + tests

# Run pre-commit hooks on all files
make pre-commit

# Run the bot (env auto-detected: tagged commit→prod, main→int, other branch→dev)
make run                     # env auto-detected; STRATEGY=... RISK=... PAIRS=... INTERVAL=...
make run ENV=dev             # force dev (mock API, no credentials needed)
make run ENV=int             # force int (paper trading, real API, no real trades)
make run ENV=prod            # force prod (REAL MONEY — requires confirmation)

# Backtesting (results saved to encrypted DB, not files)
make backtest                # STRATEGY=momentum DAYS=30 (env auto-detected: main→int, other branches→dev)
make backtest-hf             # high-frequency: 1-min candles (closest to live 5s polling)
make backtest-compare        # compare all strategies side-by-side (DAYS=... RISK=...)
make backtest-matrix         # all strategies × all risk levels matrix
make db-backtests            # view stored results (uses ENV)
make db-export-csv           # export results to CSV

# Database (per environment: data/dev.db, data/int.db, data/prod.db)
make db                      # show database overview (ENV=dev)
make db-stats                # show database statistics
make db-analytics            # trading analytics (DAYS=30)
make db-encrypt-setup        # generate and store encryption key in 1Password
make db-encrypt-status       # check if encryption is active
make db-report               # comprehensive analytics report with charts (DAYS=30, DIR=data/reports)

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

**Entry point**: `cli/run.py` → `TradingBot` (`src/bot.py`) → async main loop over trading pairs.

**Environments**: Three environments — `dev`, `int`, `prod`.

- `dev` → mock API (no credentials), paper trading
- `int` → real API, paper trading
- `prod` → real API, live trading (REAL MONEY)
- `ENVIRONMENT` env var (or `--env` CLI arg) determines which 1Password items and DB file to use.
- `TRADING_MODE` is derived from environment (dev/int → paper, prod → live).

**Component hierarchy:**

- `TradingBot` (orchestrator) owns: API client, `RiskManager`, `OrderExecutor`, `BaseStrategy`, `DatabasePersistence`
- Each loop: batch-fetch tickers → `strategy.analyze()` → `executor.execute_signal()` → `risk_manager.validate()` → place order → persist
- Portfolio state is saved every 60 seconds of wall-clock time (time-based, not iteration-based)
- Graceful shutdown: cancel orders → close losing positions immediately → close profitable positions via trailing stop or immediately. **Guarantee: all bot-opened positions are closed before exit.**

**Strategies** (`src/strategies/`): All inherit `BaseStrategy`. Six implementations:
`MarketMakingStrategy`, `MomentumStrategy`, `MeanReversionStrategy`, `MultiStrategy`, `BreakoutStrategy`, `RangeReversionStrategy`.
Adding a strategy only requires a new file implementing `BaseStrategy`.

**Configuration** (`src/config.py`): Pydantic-based. All trading config comes from 1Password — no code-level defaults. Config fails fast with actionable errors if fields are missing. Optional config: `MAX_CAPITAL` caps the cash balance at startup; `SHUTDOWN_TRAILING_STOP_PCT` sets a trailing stop percentage for profitable positions on shutdown; `SHUTDOWN_MAX_WAIT_SECONDS` sets a hard timeout before force-closing.

**Persistence** (`src/utils/db_persistence.py`): SQLite via SQLAlchemy. Per-environment DB files (`data/dev.db`, `data/int.db`, `data/prod.db`). All sensitive fields encrypted with Fernet before storage.

**Mock API** (`src/api/mock_client.py`): Used in `dev` — in-process mock of all 17 API endpoints. No network calls, no credentials needed. The `create_api_client()` factory in `src/api/__init__.py` selects mock vs real client based on environment. The API client uses `RateLimiter` (`src/utils/rate_limiter.py`) to respect API rate limits.

**Safety**: Pre-existing crypto is never touched — the SELL guard in `execute_signal` blocks any sell for a symbol the bot did not open. All trading pairs must end with `-{BASE_CURRENCY}` (currency mismatch validation). Separate API keys per environment in 1Password.

**Tests** (`tests/`):

- `tests/conftest.py` — shared fixtures, sets `ENVIRONMENT=dev` before `Settings` singleton is created
- `tests/test_config.py` — configuration loading and validation tests
- `tests/safety/` — safety-critical tests (order limits, position sizing, loss limits, environment restrictions, graceful shutdown)
- `tests/safety/test_environment.py` — environment stage safety tests (live mode restricted to prod)
- `tests/safety/test_graceful_shutdown.py` — graceful shutdown safety tests (order cancellation, all-positions closure, trailing stop logic, timeout force-close)
- `tests/safety/test_pre_existing_crypto.py` — pre-existing crypto protection tests (SELL guard, shutdown scope)
- `tests/safety/test_currency_mismatch.py` — trading pair / BASE_CURRENCY mismatch validation tests
- `tests/safety/test_config_required.py` — required config field validation tests (fail-fast on missing 1Password fields)
- `tests/safety/test_max_capital.py` — MAX_CAPITAL cap enforcement tests
- `tests/safety/test_order_limits.py` — order size and position limit safety tests
- `tests/unit/` — component unit tests (calculations, indicators, risk manager, executor, strategies, backtest engine)
- `tests/mocks/` — mock 1Password for testing (supports per-environment mocks)
- Coverage must be ≥ 97% (enforced by CI and pre-commit)

**CI/CD** (`.github/workflows/`): `ci.yml` (lint, typecheck, security, tests — triggers on PRs to `main` with `ENVIRONMENT=dev` and on post-merge pushes to `main` with `ENVIRONMENT=int`), `sonarcloud.yml` (code scanning on PRs and post-merge pushes to `main`), `backtest.yml` (manual backtest matrix on `int`), `release.yml` (manual production release with `ENVIRONMENT=prod` — commitizen determines next semver from conventional commits, updates `pyproject.toml`, generates `CHANGELOG.md` incrementally, creates the git tag, and publishes a GitHub Release; inputs: `confirm: "I UNDERSTAND"` + optional `increment` override `patch/minor/major`), `diagrams.yml` (auto-generates architecture class diagrams using pyreverse on pushes to `main` or manual trigger; uploads diagrams as artifacts with 90-day retention).

## Key Files

| File                                  | Purpose                                                                                                                                                                                                                                  |
| ------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/bot.py`                          | Main orchestrator — start here to understand flow                                                                                                                                                                                        |
| `src/config.py`                       | Pydantic config + 1Password loading                                                                                                                                                                                                      |
| `src/api/client.py`                   | Real Revolut X API client (Ed25519 auth, httpx)                                                                                                                                                                                          |
| `src/api/mock_client.py`              | Mock API client for dev environment (no real API calls)                                                                                                                                                                                  |
| `src/models/domain.py`                | Core domain models (Position, Order, Trade, Signal, etc.)                                                                                                                                                                                |
| `src/models/db.py`                    | SQLAlchemy 2.0 ORM models (SQLite, Numeric columns, WAL mode)                                                                                                                                                                            |
| `src/risk_management/risk_manager.py` | Risk validation and position sizing                                                                                                                                                                                                      |
| `src/execution/executor.py`           | Order execution and position management                                                                                                                                                                                                  |
| `src/strategies/base_strategy.py`     | Abstract base all strategies implement                                                                                                                                                                                                   |
| `src/utils/onepassword.py`            | 1Password CLI wrapper (environment-aware item names)                                                                                                                                                                                     |
| `src/utils/db_persistence.py`         | SQLAlchemy session management, all CRUD operations + CSV export                                                                                                                                                                          |
| `src/utils/db_encryption.py`          | Fernet encryption; key auto-generated in 1Password                                                                                                                                                                                       |
| `src/utils/indicators.py`             | Technical indicators (SMA, EMA, RSI, Bollinger Bands)                                                                                                                                                                                    |
| `src/utils/rate_limiter.py`           | API rate limiting                                                                                                                                                                                                                        |
| `src/utils/fees.py`                   | Trading fee constants and `calculate_fee()` — single source of truth for the Revolut X fee schedule (0% maker / 0.09% taker)                                                                                                             |
| `src/backtest/engine.py`              | Backtest engine — mirrors live trading: per-strategy risk overrides, signal strength filter, per-strategy order type (MARKET/LIMIT), intra-bar SL/TP via candle high/low, LIMIT fill verification, 0.1% spread, taker fees, Sharpe ratio |
| `tests/conftest.py`                   | Shared fixtures, ENVIRONMENT=dev setup                                                                                                                                                                                                   |
| `tests/test_config.py`                | Configuration loading and validation tests                                                                                                                                                                                               |
| `tests/mocks/mock_onepassword.py`     | Use this in tests instead of real 1Password                                                                                                                                                                                              |
| `docs/revolut-x-api-docs.md`          | Revolut X API reference (source of truth for all API code)                                                                                                                                                                               |
| `docs/USER_GUIDE.md`                  | End-to-end user guide: setup, configuration, running, monitoring                                                                                                                                                                         |
| `docs/DEVELOPMENT_GUIDELINES.md`      | TDD workflow, coding standards, contribution rules                                                                                                                                                                                       |
| `docs/ARCHITECTURE.md`                | Component details and data flow                                                                                                                                                                                                          |
| `docs/BACKTESTING.md`                 | Backtesting guide, metrics, interpretation                                                                                                                                                                                               |
| `docs/1PASSWORD.md`                   | Credential and configuration setup via 1Password CLI                                                                                                                                                                                     |
| `docs/RASPBERRY_PI_DEPLOYMENT.md`     | Running the bot unattended on Raspberry Pi / ARM64 servers                                                                                                                                                                               |
| `cli/analytics_report.py`             | Comprehensive analytics report: Sharpe/Sortino/drawdown/profit factor, per-symbol/strategy tables, rule-based suggestions, PNG charts (matplotlib optional), optional Telegram notification                                              |
| `cli/revt.py`                         | `revt` CLI entry point — polished user-facing command replacing all non-development make targets; defaults to `prod` when running as a frozen binary; delegates to existing CLI modules without subprocess overhead                      |
| `build/revt.spec`                     | PyInstaller spec for building the standalone `revt` binary; used by the `build-revt` CI job to produce `revt-macos-arm64` and `revt-linux-arm64` release assets                                                                          |

## Commit Message Convention

All commits **must** follow [Conventional Commits](https://www.conventionalcommits.org/).

**Format:** `<type>[optional scope]: <description>`

| Type       | When to use                               |
| ---------- | ----------------------------------------- |
| `feat`     | New feature (triggers minor version bump) |
| `fix`      | Bug fix (triggers patch version bump)     |
| `docs`     | Documentation only                        |
| `refactor` | Code restructuring, no behaviour change   |
| `test`     | Adding or updating tests                  |
| `chore`    | Build process, dependencies, tooling      |
| `perf`     | Performance improvement                   |
| `ci`       | CI/CD workflow changes                    |
| `style`    | Formatting, no logic change               |

**Breaking change:** append `!` after the type (`feat!:`) or add `BREAKING CHANGE:` footer.

**Examples:**

```
feat(strategy): add breakout strategy with ATR-based stops
fix(executor): prevent duplicate orders on rapid signal changes
docs: add backtesting guide to README
chore(deps): upgrade httpx to 0.28
feat!: replace REST polling with WebSocket feed
```

**Interactive commit helper:** `uv run cz commit` — prompts for type, scope, and description.

## Mandatory Rules

### Revolut X API Docs — The Single Source of Truth

`docs/revolut-x-api-docs.md` is the authoritative reference for **all** API behaviour.
Every endpoint path, request body shape, response shape, field name, field type, and valid
enum value must be taken from that document — never guessed or inferred from existing code.

**The hierarchy is strict:**

```
Revolut X API docs  →  tests  →  code
```

1. **API docs define reality.** Do not let existing code shapes influence what you believe the API returns.
1. **Tests encode the API contract.** Every field name, enum string, and response envelope must match the docs exactly.
1. **Code must pass the tests.** Never update tests to match wrong code — fix the code.

**Before touching any API-related code:**

- Open `docs/revolut-x-api-docs.md` and locate the relevant endpoint.
- Verify HTTP method, path, required/optional params, and exact response shape.
- Confirm every enum value appears verbatim in the docs.
- If existing code or tests contradict the docs, the docs win.

### TDD — Non-Negotiable

Write tests **first**, then code. Every new feature or fix:

1. Consult `docs/revolut-x-api-docs.md` to establish the API contract.
1. Write the test against the API contract → confirm it fails.
1. Write minimal code → confirm it passes.
1. Refactor if needed.

Test locations:

- `tests/safety/` — safety-critical tests
- `tests/unit/test_calculations.py` — financial math
- `tests/unit/` — everything else

Coverage must be ≥ 97% (enforced by CI and pre-commit).

### Financial Calculations — Always `Decimal`

```python
# NEVER
price: float = 100.5

# ALWAYS
from decimal import Decimal

price: Decimal = Decimal("100.5")
```

- All monetary ORM columns use `Numeric(20, 10)` — never `Float`.
- Never cast financial values with `float()` before storing.

### Configuration — No Code Defaults

Trading config must come from 1Password exclusively. Two exceptions:

- `ENVIRONMENT` — from `os.environ` (infrastructure-level).
- `TRADING_MODE` — derived from environment, not stored in 1Password.

If a required field is missing, raise a `RuntimeError` with instructions. Never silently fall back to a hardcoded default.

### Database Encryption — Always On

Database encryption is mandatory. Never disable it or add a plaintext fallback. Only encrypt genuinely sensitive fields — not categoricals that need SQL filtering.

### No Plaintext Files for Sensitive Data

- No log files on disk — logs go to the encrypted database via `save_log_entry()`.
- No JSON result exports — backtest results go to the encrypted database.
- Use `make db-export-csv` for on-demand exports.

### All Functions — Type Hints + Docstrings

Every public function needs type annotations on all parameters and return value, plus a docstring explaining what it does.

### Documentation Updates — Always, No Exceptions

Every code change **must** include corresponding documentation updates:

- `README.md` — feature additions, configuration changes, usage instructions
- `CHANGELOG.md` — auto-generated by release workflow (do not edit manually)
- Inline docstrings — logic changes, new functions, modified behaviour
- `CLAUDE.md` and this file — architectural changes, new components
- `docs/USER_GUIDE.md` — user-facing changes: new config keys, new commands, changed behavior
- `docs/` files — API changes, strategy changes, development guidelines
