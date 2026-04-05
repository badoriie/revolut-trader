# CLAUDE.md

## Commands

**Package manager**: `uv` | **Dev tooling**: `just` | **Functional CLI**: `revt`

```bash
# Development
just install | test | lint | format | typecheck | security | check | clean

# Trading bot
revt run [--strategy S] [--risk R] [--mode live] [--confirm-live]
revt backtest [--compare] [--matrix] [--days N] [--interval N]
revt ops init | [--show|--status]
revt config show | set KEY VALUE | delete KEY
revt api test | ready
revt db stats | analytics | backtests | export | report
revt telegram test | start
revt update
```

## Architecture

- **Entry**: `cli/revt.py` → `cli/commands/{run,backtest,backtest_compare,api,db,telegram}.py`
- **Envs**: `dev` (mock API) | `int` (real API, paper) | `prod` (real API, paper/live)
- **Detection**: feature branch→dev, main→int, tagged commit→prod, frozen binary→prod. **No manual override.**
- **Trading mode**: Paper by default. Live requires `TRADING_MODE=live` in 1Password + confirmation
- **Loop**: `get_tickers()` → `strategy.analyze()` → `executor.execute_signal()` → `risk_manager.validate()` → place order → persist
- **Shutdown**: cancel orders → close losing → close profitable (trailing stop) → save
- **Strategies**: 6 types, tunable via 1Password (`revolut-trader-strategy-{name}`)
- **Config**: Pydantic + 1Password. `ENVIRONMENT` from env var. Fails fast on missing fields
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

### Security

- DB encryption always on. Encrypt sensitive fields only.
- Logs/backtest → encrypted DB only. Export via `revt db export`.
- No plaintext credentials in code, logs, tests, or error messages.

### Code Quality

- All public functions: type hints + docstring
- Cognitive complexity ≤15. Extract helpers, early returns, flat flow.

### Documentation

Every change updates: `README.md`, docstrings, `CLAUDE.md`, `docs/{END_USER_GUIDE,DEVELOPER_GUIDE}.md`. Run `just sync-copilot` after CLAUDE.md changes.

## Key Files

| File                                  | Purpose                                                                                                              |
| ------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `src/bot.py`                          | Main orchestrator                                                                                                    |
| `src/config.py`                       | Pydantic config + 1Password                                                                                          |
| `src/api/{client,mock_client}.py`     | Real/mock API                                                                                                        |
| `src/models/{domain,db}.py`           | Domain models, ORM                                                                                                   |
| `src/risk_management/risk_manager.py` | Risk validation                                                                                                      |
| `src/execution/executor.py`           | Order execution                                                                                                      |
| `src/strategies/`                     | 6 strategy implementations                                                                                           |
| `src/utils/`                          | 1Password, DB, encryption, indicators, fees, telegram, rate limiter                                                  |
| `src/backtest/engine.py`              | Backtest engine                                                                                                      |
| `cli/revt.py`                         | CLI entry point (`revt` command)                                                                                     |
| `cli/commands/`                       | Command handlers (run, backtest, backtest_compare, api, db, telegram)                                                |
| `cli/utils/`                          | env_detect, validators, analytics_report, view_logs                                                                  |
| `tests/`                              | Tests (≥97% coverage)                                                                                                |
| `docs/revolut-x-api-docs.md`          | **API reference**                                                                                                    |
| `docs/`                               | ARCHITECTURE, DEVELOPMENT_GUIDELINES, BACKTESTING, END_USER_GUIDE, DEVELOPER_GUIDE, 1PASSWORD, TELEGRAM_BOT_COMMANDS |
