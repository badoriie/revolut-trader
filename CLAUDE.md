# CLAUDE.md

> **GitHub Copilot users:** see `.github/copilot-instructions.md`. Keep both files in sync.

## Commands

**Package manager: `uv`** — always prefix Python commands with `uv run`.

```bash
uv sync --extra dev          # install dependencies
make test                    # run tests with coverage
make lint / format / typecheck / security / check
make pre-commit              # run all pre-commit hooks

# Bot (env auto-detected: tagged→prod, main→int, branch→dev; always paper by default)
make run                     # STRATEGY=... RISK=... PAIRS=... INTERVAL=...
make run ENV=prod MODE=live  # LIVE TRADING — requires confirmation

make telegram                # start always-on Telegram Control Plane

# Backtesting
make backtest                # STRATEGY=momentum DAYS=30
make backtest-hf / backtest-compare / backtest-matrix

# Database
make db / db-stats / db-analytics / db-backtests / db-export-csv
make db-encrypt-setup / db-encrypt-status
make db-report               # analytics report + charts (DAYS=30, DIR=data/reports)
make logs                    # view WARNING+ logs from DB

# 1Password / credentials
make setup                   # first-time setup (idempotent)
make ops ENV=dev             # set API key interactively
make opshow / opstatus / opconfig-show / opconfig-set

# API utilities
make api-test / api-ready ENV=int
```

### `revt` CLI

Production binary (Linux x86_64 / ARM64) shipped with every GitHub release. After `uv sync`, also available as a source runner. Run `revt --help` or `revt <cmd> --help` for full usage. Key commands: `run`, `backtest`, `telegram`, `ops`, `config`, `api`, `db`. Defaults to `prod` when run as a frozen binary.

## Architecture

See `docs/ARCHITECTURE.md` for full detail. Summary:

- **Entry**: `cli/run.py` → `TradingBot` (`src/bot.py`) → async loop per trading pair
- **Environments**: `dev` (mock API, no creds) | `int` (real API, paper) | `prod` (real API, paper or live). Branch auto-detection: feature→dev, main→int, tag→prod. Override with `--env`.
- **Trading mode**: Paper by default everywhere. Live only in prod — requires `TRADING_MODE=live` in 1Password + explicit confirmation. Bypass with `--confirm-live`.
- **API client**: `create_api_client()` returns `MockRevolutAPIClient` (dev) or `RevolutAPIClient` (int/prod). Both implement identical interfaces.
- **Loop**: `get_tickers()` (1 call) → `strategy.analyze()` → `executor.execute_signal()` (signal filter + order type) → `risk_manager.validate()` → place order → persist. Portfolio saved every 60 s.
- **Shutdown**: cancel orders → close losing positions → close profitable via trailing stop (or immediately) → save state. **Guarantee: all bot-opened positions closed before exit.**
- **Strategies**: 6 implementations (`MarketMaking`, `Momentum`, `MeanReversion`, `MultiStrategy`, `Breakout`, `RangeReversion`). All tunable via 1Password items (`revolut-trader-strategy-{name}`).
- **Config** (`src/config.py`): Pydantic. `ENVIRONMENT` from `os.environ`. Everything else from 1Password. CLI flags override per-run. Fails fast with actionable errors on missing fields.
- **Persistence**: SQLite via SQLAlchemy, per-env DB (`data/{env}.db`). Fernet encryption on sensitive fields. WARNING+ logs auto-persisted via loguru sink.
- **1Password**: `revolut-trader-credentials-{env}`, `revolut-trader-config-{env}`, `revolut-trader-risk-{level}`, `revolut-trader-strategy-{name}`.
- **Tests**: `tests/conftest.py` sets `ENVIRONMENT=dev`. Safety-critical in `tests/safety/`, financial math in `tests/unit/test_calculations.py`. Coverage ≥ 97% enforced by CI.
- **CI/CD**: `ci.yml` (lint+test), `sonarcloud.yml`, `backtest.yml`, `release.yml` (commitizen semver + changelog), `diagrams.yml`.

## Commit Convention

[Conventional Commits](https://www.conventionalcommits.org/) — enforced by commitizen pre-commit hook.

`<type>[scope]: <description>` — types: `feat` `fix` `docs` `refactor` `test` `chore` `perf` `ci` `style`. Breaking change: `feat!:` or `BREAKING CHANGE:` footer. Use `uv run cz commit` for interactive helper.

## Mandatory Rules

### Environment Parity

All environments run **identical code paths** — only data source differs. Never add `if environment == "dev"` logic branches. `if trading_mode == "paper"` is allowed **only** for order execution calls, never for business logic, fee calculation, or accounting. `_execute_paper_order` and `_execute_live_order` must populate identical fields.

### API Docs Are Law

`docs/revolut-x-api-docs.md` is the **single source of truth**. Hierarchy: `API docs → tests → code`. Every field name, enum value, and response shape must match the docs exactly. If code contradicts docs, fix the code.

### TDD — Non-Negotiable

1. Consult `docs/revolut-x-api-docs.md` for the contract
1. Write failing test
1. Write minimal code to pass
1. Refactor if needed

### Financial Calculations — Always `Decimal`

```python
# NEVER: price: float = 100.5
# ALWAYS: price: Decimal = Decimal("100.5")
```

ORM monetary columns: `Numeric(20, 10)` — never `Float`. Never `float()` before storing.

### Configuration — No Code Defaults

All user-controllable values live in 1Password. `make setup` must create every field (idempotent). `config.py` validates all fields — required fields raise `RuntimeError` with a fix command; optional fields fall back gracefully. `ENVIRONMENT` is the only exception (from `os.environ`).

### Database Encryption — Always On

`DatabaseEncryption` auto-generates a key in 1Password if none exists. Never disable or add plaintext fallback. Encrypt only sensitive fields — not categoricals used for SQL filtering.

### No Plaintext Files for Sensitive Data

Logs → encrypted DB (`save_log_entry()`). Backtest results → encrypted DB. Use `make db-export-csv` for on-demand exports.

### Code Quality

- All public functions: type hints + docstring
- Cognitive complexity ≤ 15 (SonarCloud). Extract helpers, use early returns, avoid deep nesting.

### Documentation — Always Updated

Every change must update relevant docs. Not optional — a change is not done until docs are updated.

- `README.md`, inline docstrings, `CLAUDE.md`, `.github/copilot-instructions.md`
- `docs/END_USER_GUIDE.md` (user-facing changes), `docs/DEVELOPER_GUIDE.md` (dev changes)

## Key Files

| File                                  | Purpose                                                    |
| ------------------------------------- | ---------------------------------------------------------- |
| `src/bot.py`                          | Main orchestrator                                          |
| `src/config.py`                       | Pydantic config + 1Password loading                        |
| `src/api/client.py`                   | Real Revolut X API client                                  |
| `src/api/mock_client.py`              | Mock client for dev                                        |
| `src/models/domain.py`                | Core domain models                                         |
| `src/models/db.py`                    | SQLAlchemy ORM models                                      |
| `src/risk_management/risk_manager.py` | Risk validation + position sizing                          |
| `src/execution/executor.py`           | Order execution + position management                      |
| `src/strategies/base_strategy.py`     | Abstract base for strategies                               |
| `src/utils/onepassword.py`            | 1Password CLI wrapper                                      |
| `src/utils/db_persistence.py`         | SQLAlchemy CRUD + CSV export                               |
| `src/utils/db_encryption.py`          | Fernet encryption                                          |
| `src/utils/indicators.py`             | SMA, EMA, RSI, Bollinger Bands (O(1) incremental)          |
| `src/utils/fees.py`                   | Fee constants + `calculate_fee()` (0% maker / 0.09% taker) |
| `src/utils/telegram.py`               | Telegram notifier + command listener                       |
| `src/utils/rate_limiter.py`           | API rate limiting                                          |
| `src/backtest/engine.py`              | Backtest engine (mirrors live trading)                     |
| `tests/conftest.py`                   | Shared fixtures, `ENVIRONMENT=dev`                         |
| `tests/mocks/mock_onepassword.py`     | Mock 1Password for tests                                   |
| `cli/revt.py`                         | `revt` CLI entry point                                     |
| `cli/analytics_report.py`             | Analytics report (Sharpe, drawdown, charts, Telegram PDF)  |
| `cli/telegram_control.py`             | Always-on Telegram Control Plane                           |
| `cli/view_logs.py`                    | View decrypted logs from DB                                |
| `build/revt.spec`                     | PyInstaller spec for `revt` binary                         |
| `docs/revolut-x-api-docs.md`          | **API reference — source of truth**                        |
| `docs/ARCHITECTURE.md`                | Component details and data flow                            |
| `docs/DEVELOPMENT_GUIDELINES.md`      | TDD workflow, coding standards                             |
| `docs/BACKTESTING.md`                 | Backtesting guide                                          |
| `docs/END_USER_GUIDE.md`              | End-user quick start                                       |
| `docs/DEVELOPER_GUIDE.md`             | Developer setup + advanced usage                           |
| `docs/1PASSWORD.md`                   | Credential setup + troubleshooting                         |
