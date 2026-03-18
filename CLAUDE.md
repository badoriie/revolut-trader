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
make typecheck               # mypy src/ cli/
make check                   # all of the above + tests

# Run pre-commit hooks on all files
make pre-commit

# Run the bot
make run-paper               # paper trading (safe)
make run-live                # live trading (real money — requires confirmation)

# Backtesting
make backtest                # STRATEGY=momentum DAYS=30

# API utilities
make api-test
make api-balance
make api-ticker SYMBOL=BTC-EUR

# 1Password / credential management (vault/item names defined in Makefile + src/utils/onepassword.py)
make setup                   # first-time setup: vault, items, key generation, deps
make ops                     # interactively set API key / Telegram credentials
make opshow                  # show all stored values (credentials + config, masked)
make opstatus                # check 1Password CLI status
make opconfig-show           # show trading configuration
make opconfig-set KEY=TRADING_MODE VALUE=paper
```

## Architecture

**Entry point**: `cli/run.py` → creates `TradingBot` (`src/bot.py`) → async main loop over trading pairs.

**Component hierarchy:**

- `TradingBot` (orchestrator) owns: `RevolutAPIClient`, `RiskManager`, `OrderExecutor`, `BaseStrategy`, `TelegramNotifier`, `HybridPersistence`
- Each trading loop iteration: fetch market data → `strategy.analyze()` → `risk_manager.validate()` → `executor.execute()` → persist

**Strategies** (`src/strategies/`): All inherit `BaseStrategy`. Four implementations: `MarketMakingStrategy`, `MomentumStrategy`, `MeanReversionStrategy`, `MultiStrategy` (weighted voting across all three). Adding a strategy only requires a new file implementing `BaseStrategy`.

**Configuration** (`src/config.py`): Pydantic-based. All trading config (mode, strategy, risk level, pairs, capital) is fetched from 1Password at startup — there are no code-level defaults. Config fails fast with actionable error messages if 1Password fields are missing.

**Persistence** (`src/utils/hybrid_persistence.py`): SQLite primary (SQLAlchemy ORM via `src/models/db_models.py`) + JSON backup secondary. Writes immediately after each trade, periodically every 10 iterations, and on shutdown.

**1Password** (`src/utils/onepassword.py`): Wraps the `op` CLI. Retrieves API keys, private keys, bot tokens, and all trading configuration. Tests use `tests/mocks/mock_onepassword.py` to avoid real 1Password calls.

**Technical indicators** (`src/utils/indicators.py`): SMA, EMA, RSI, Bollinger Bands — all O(1) incremental updates (no history recalculation).

**Tests** (`tests/`):

- `tests/safety/` — safety-critical tests (order limits, position sizing, loss limits)
- `tests/unit/` — component unit tests (calculations, indicators, risk manager)
- `tests/mocks/` — mock 1Password for testing

## Mandatory Rules

These are enforced by pre-commit hooks and must be followed:

### TDD — Non-Negotiable

Write tests **first**, then code. Every new feature or fix:

1. Write the test → confirm it fails
1. Write minimal code → confirm it passes
1. Refactor if needed

Safety-critical tests go in `tests/safety/`, financial math in `tests/unit/test_calculations.py`, everything else in `tests/unit/`.

### Financial Calculations — Always `Decimal`

```python
# NEVER
price: float = 100.5

# ALWAYS
from decimal import Decimal

price: Decimal = Decimal("100.5")
```

### Configuration — No Code Defaults

Trading config must come from 1Password exclusively. If a required field is missing, raise a `RuntimeError` with instructions on how to fix it (e.g., `make opconfig-set KEY=... VALUE=...`). Never silently fall back to a hardcoded default.

### All Functions — Type Hints + Docstrings

Every public function needs type annotations on all parameters and return value, plus a docstring explaining what it does and (for critical functions) why it matters.

### Documentation Updates

When changing code, update the relevant docs: `README.md` for features/config changes, `CHANGELOG.md` for bug fixes, inline docstrings for logic changes.

## Key Files

| File                                  | Purpose                                                   |
| ------------------------------------- | --------------------------------------------------------- |
| `src/bot.py`                          | Main orchestrator — start here to understand flow         |
| `src/config.py`                       | Pydantic config + 1Password loading                       |
| `src/data/models.py`                  | Core domain models (Position, Order, Trade, Signal, etc.) |
| `src/risk_management/risk_manager.py` | Risk validation and position sizing                       |
| `src/strategies/base_strategy.py`     | Abstract base all strategies implement                    |
| `src/utils/onepassword.py`            | 1Password CLI wrapper                                     |
| `src/utils/hybrid_persistence.py`     | SQLite + JSON persistence                                 |
| `tests/mocks/mock_onepassword.py`     | Use this in tests instead of real 1Password               |
| `docs/DEVELOPMENT_GUIDELINES.md`      | Detailed development guidelines                           |
| `.claude/PROJECT_RULES.md`            | Mandatory rules reference                                 |
