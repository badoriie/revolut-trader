# CLAUDE.md

## Commands

**Package manager**: `uv` — prefix Python commands with `uv run`

**Development**: `just` | **Functional**: `revt` CLI

```bash
just install/test/lint/format/typecheck/security/check/pre-commit/clean/env
revt run [--mode live] | backtest | telegram start | ops | config | db | api
```

## Architecture

- **Entry**: `cli/run.py` → `TradingBot` → async loop per pair
- **Envs**: `dev` (mock API) | `int` (real API, paper) | `prod` (real API, paper/live)
- **Detection**: feature→dev, main→int, tag→prod. Override: `--env`
- **Trading mode**: Paper default. Live requires `TRADING_MODE=live` in 1Password + confirmation
- **Loop**: `get_tickers()` → `strategy.analyze()` → `executor.execute_signal()` → `risk_manager.validate()` → place order → persist
- **Shutdown**: cancel orders → close losing → close profitable (trailing stop) → save. All bot positions closed
- **Strategies**: 6 types, tunable via 1Password (`revolut-trader-strategy-{name}`)
- **Config**: Pydantic + 1Password. `ENVIRONMENT` from env. Fails fast on missing fields
- **Persistence**: SQLite per env (`revt-data/{env}.db`), Fernet encryption
- **1Password items**: `revolut-trader-{credentials|config|risk|strategy}-*`
- **Tests**: Coverage ≥97%. Safety in `tests/safety/`, math in `tests/unit/test_calculations.py`

## Commit Convention

`<type>[scope]: <description>` — types: `feat|fix|docs|refactor|test|chore|perf|ci|style`
Breaking: `feat!:` or `BREAKING CHANGE:` footer. Helper: `uv run cz commit`

## Rules

### Environment Parity

Identical code paths across all envs. Only data source differs. Never `if environment == "dev"`. `if trading_mode == "paper"` only for execution, not logic/fees/accounting.

### API Docs Are Law

`docs/revolut-x-api-docs.md` = source of truth. Hierarchy: API docs → tests → code. If code contradicts docs, fix code.

### TDD

1. Check `docs/revolut-x-api-docs.md`
1. Write failing test
1. Minimal code to pass
1. Refactor

### Financial Calculations

```python
# NEVER: price: float = 100.5
# ALWAYS: price: Decimal = Decimal("100.5")
```

ORM: `Numeric(20, 10)`, never `Float`

### Configuration

All user values → 1Password. No code defaults (except `ENVIRONMENT` from env). Required fields → `RuntimeError` with fix command.

### Database Encryption

Always on. Auto-generates key. Encrypt sensitive fields only.

### No Plaintext Sensitive Data

Logs/backtest → encrypted DB. Export via `make db-export-csv`.

### Code Quality

- All public functions: type hints + docstring
- Cognitive complexity ≤15. Extract helpers, early returns, flat flow.

### Documentation

Every change updates relevant docs: `README.md`, docstrings, `CLAUDE.md`, `.github/copilot-instructions.md`, `docs/{END_USER_GUIDE,DEVELOPER_GUIDE}.md`

## Key Files

| File                                                                                                 | Purpose                                                             |
| ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| `src/bot.py`                                                                                         | Main orchestrator                                                   |
| `src/config.py`                                                                                      | Pydantic config + 1Password                                         |
| `src/api/{client,mock_client}.py`                                                                    | Real/mock API                                                       |
| `src/models/{domain,db}.py`                                                                          | Domain models, ORM                                                  |
| `src/risk_management/risk_manager.py`                                                                | Risk validation                                                     |
| `src/execution/executor.py`                                                                          | Order execution                                                     |
| `src/strategies/`                                                                                    | Strategy implementations                                            |
| `src/utils/`                                                                                         | 1Password, DB, encryption, indicators, fees, telegram, rate limiter |
| `src/backtest/engine.py`                                                                             | Backtest engine                                                     |
| `tests/`                                                                                             | Tests (≥97% coverage)                                               |
| `cli/`                                                                                               | CLI commands                                                        |
| `docs/revolut-x-api-docs.md`                                                                         | **API reference**                                                   |
| `docs/{ARCHITECTURE,DEVELOPMENT_GUIDELINES,BACKTESTING,END_USER_GUIDE,DEVELOPER_GUIDE,1PASSWORD}.md` | Documentation                                                       |
