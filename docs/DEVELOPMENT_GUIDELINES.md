# Development Guidelines

This is a **financial trading system**. Wrong behavior = potential financial loss.
Every rule below exists to protect real money.

______________________________________________________________________

## Test-Driven Development (TDD) — Mandatory

**Never write code before writing tests.**

```
1. Write Test (based on requirement)  →  it FAILS
2. Write minimal code                 →  it PASSES
3. Refactor if needed                 →  tests protect you
```

### Example: Adding a New Risk Control

```python
# 1. Write test FIRST based on requirement
def test_position_size_must_not_exceed_5_percent():
    """CRITICAL: Position size MUST be <= 5% of portfolio.

    Context: Risk requirement RM-05
    Critical because: Prevents overexposure

    Scenario:
    - Portfolio = 10,000 EUR
    - Max position = 5% = 500 EUR
    - Position of 600 EUR MUST be rejected
    """
    portfolio = Decimal("10000")
    position_size = Decimal("600")  # 6% - too large

    is_valid = validate_position_size(position_size, portfolio)

    assert not is_valid  # MUST reject


# 2. Run test - it FAILS (function doesn't exist yet)
# 3. Write code to pass test
def validate_position_size(size: Decimal, portfolio: Decimal) -> bool:
    max_size = portfolio * Decimal("0.05")
    return size <= max_size


# 4. Run test - it PASSES
```

______________________________________________________________________

## Test Categories

### 1. Safety-Critical Tests (`tests/safety/`) — Highest Priority

Tests that prevent financial loss. MUST include:

- **WHY** the test is critical (link to safety requirement ID, e.g. SAF-01)
- **Scenario** with concrete values
- **Both** normal and edge cases
- **Decimal** arithmetic (no floats for money)

### 2. Calculation Tests (`tests/unit/test_calculations.py`)

Mathematical correctness — verify with known, manually computed values.
Test edge cases: zero, negative, very large/small.

### 3. Unit Tests (`tests/unit/`)

Component functionality. One test per behavior, fast execution (no I/O, no sleep).

### Test Structure

Use AAA pattern (Arrange, Act, Assert):

```python
def test_stop_loss_calculation():
    """Test description."""
    # Arrange
    entry_price = Decimal("50000")
    side = OrderSide.BUY

    # Act
    stop_loss = calculate_stop_loss(entry_price, side)

    # Assert
    expected = Decimal("49250")
    assert stop_loss == expected
```

### Test Naming Convention

```python
# Pattern: test_<what>_<scenario>_<expected>
test_position_size_exceeds_limit_rejected()
test_pnl_long_position_profit()
test_ema_warmup_period_not_ready()
```

______________________________________________________________________

## Financial Calculations — Always `Decimal`

```python
# NEVER
price: float = 100.5

# ALWAYS
from decimal import Decimal

price: Decimal = Decimal("100.5")
```

All monetary columns in the ORM use `Numeric(20, 10)` — never `Float`.
Never cast financial values with `float()` before storing.

______________________________________________________________________

## Code Quality Standards

### Type Hints Required

All functions MUST have type hints on all parameters and return value:

```python
def calculate_position_size(
    portfolio_value: Decimal, price: Decimal, signal_strength: float = 1.0
) -> Decimal:
    """Calculate position size."""
```

### Error Messages Must Be Actionable

```python
# BAD
raise RuntimeError("Invalid config")

# GOOD
raise RuntimeError(
    "RISK_LEVEL not found in 1Password config.\n"
    "Run: make opconfig-set KEY=RISK_LEVEL VALUE=conservative ENV=dev"
)
```

### Docstrings Required

Every module, class, and public function needs a docstring:

```python
def calculate_stop_loss(
    entry_price: Decimal, side: OrderSide, custom_pct: float | None = None
) -> Decimal:
    """Calculate stop loss price.

    Args:
        entry_price: Entry price of position
        side: BUY or SELL
        custom_pct: Optional custom stop loss percentage

    Returns:
        Stop loss price (quantized to 2 decimals)
    """
```

### Naming Conventions

```python
# Variables and functions — descriptive, unambiguous
max_position_size: float  # not: max_pos
daily_loss_limit: Decimal  # not: limit
calculate_sharpe_ratio()  # not: calc_sr()

# Constants — UPPER_CASE
MAX_POSITION_SIZE_USD = 10000
DEFAULT_STOP_LOSS_PERCENTAGE = 0.02


# Classes — PascalCase
class RiskManager: ...


class MarketMakingStrategy: ...
```

______________________________________________________________________

## Code Organization

### File Size and Focus

- Keep files focused and under ~500 lines
- One strategy per file, one concern per class
- Ideal function length: 10–20 lines, max: 50 lines

### Anti-Patterns to Avoid

1. **God classes** — split classes that do everything
1. **Magic numbers** — use named constants (`MAX_POSITION_SIZE_USD` not `10000`)
1. **Swallowing exceptions** — never `except: pass`; always log and re-raise
1. **Premature optimization** — don't optimize until profiling proves it's a bottleneck
1. **Copy-paste code** — extract a function instead

______________________________________________________________________

## Performance Guidelines

### Indicators MUST Be O(1) Update

Use incremental calculations, not recalculation:

```python
# WRONG - O(n) recalculation every tick
def _calculate_sma(self, prices: deque, period: int) -> Decimal:
    return sum(prices[-period:]) / Decimal(period)


# RIGHT - O(1) update
class EMA:
    def __init__(self, period):
        self.multiplier = Decimal(2) / Decimal(period + 1)
        self.current_ema = None

    def update(self, price):
        if self.current_ema is None:
            self.current_ema = price
        else:
            self.current_ema = (price * self.multiplier) + (
                self.current_ema * (1 - self.multiplier)
            )
        return self.current_ema  # O(1)!
```

______________________________________________________________________

## Configuration Management

All trading config MUST be in 1Password. No code defaults.

**Exception:** `TRADING_MODE` defaults to `paper` in all environments and is stored in 1Password (set `TRADING_MODE=live` for prod to enable live trading). `INITIAL_CAPITAL` is only required for paper mode.

```python
# WRONG - has code default
risk_level: RiskLevel = RiskLevel.CONSERVATIVE  # Risky!

# RIGHT - fails if not in 1Password
risk_level_str = get_config("RISK_LEVEL", None)
if not risk_level_str:
    raise RuntimeError(
        "RISK_LEVEL not found in 1Password config.\n" "Run: make opconfig-init"
    )
```

See [1Password docs](1PASSWORD.md) for details on config fields and commands.

______________________________________________________________________

## Git Commit Guidelines

```
<type>: <short description>

<optional detailed description>
```

**Types:** `feat`, `fix`, `test`, `refactor`, `docs`, `chore`, `perf`, `ci`, `style`

______________________________________________________________________

## Pre-commit Checklist

Before committing code:

- [ ] Tests written BEFORE code implementation
- [ ] All tests pass (`just test`)
- [ ] No floating-point arithmetic for financial calculations
- [ ] Type hints on all functions
- [ ] Critical tests documented with WHY and context
- [ ] Pre-commit hooks pass (`just pre-commit`)
- [ ] No secrets in code (use 1Password)
- [ ] Documentation updated if needed

### Review Critical Changes

Changes to these areas require extra review:

- Risk management (position sizing, limits)
- PnL calculations
- Order execution logic
- Stop loss/take profit triggers
- Configuration loading

______________________________________________________________________

## Environment Stages (dev / int / prod)

The project uses three deployment environments with full isolation:

| Environment | API                  | Trading Mode           | DB File             | 1Password Items                        |
| ----------- | -------------------- | ---------------------- | ------------------- | -------------------------------------- |
| `dev`       | Mock (no real calls) | Paper only             | `revt-data/dev.db`  | `*-credentials-dev` / `*-config-dev`   |
| `int`       | Real Revolut X API   | Paper only             | `revt-data/int.db`  | `*-credentials-int` / `*-config-int`   |
| `prod`      | Real Revolut X API   | Paper (default) / Live | `revt-data/prod.db` | `*-credentials-prod` / `*-config-prod` |

### Key rules

- **`ENVIRONMENT` is auto-detected** from the git branch (`main` → `int`, feature branch → `dev`, tagged commit → `prod`) or from the frozen binary (`prod`). Override with `--env` or `export ENVIRONMENT=dev|int|prod`.
- **`TRADING_MODE` is stored in 1Password** and defaults to `paper` if not set. Must be explicitly set to `live` for real-money trading.
- **`INITIAL_CAPITAL` is required for paper mode**, not required for live mode (fetches real balance from API).
- **Separate API keys per environment** — if a dev key leaks, prod is unaffected.
- **Tests always run with `ENVIRONMENT=dev`** — set in `conftest.py` before the `Settings` singleton is created.

### Running in each environment

```bash
revt run              # env auto-detected from git branch (feature → dev, main → int)
revt run ENV=dev      # mock API, no credentials needed
revt run ENV=int      # real API, paper mode (no real trades)
revt run ENV=prod     # real API, live trading (requires confirmation)
```

### Branches & CI flow

Single `main` branch. Pre-commit hooks handle dev checks locally; CI runs on PRs to `main`:

| Stage                     | Environment | Checks                                                        |
| ------------------------- | ----------- | ------------------------------------------------------------- |
| Pre-commit (local)        | dev         | Lint, typecheck, security, tests (before each commit)         |
| PR to `main`              | dev         | CI: same checks, `ENVIRONMENT=dev`, merge blocked until green |
| Post-merge push to `main` | int         | CI: same checks, `ENVIRONMENT=int`, real API validation       |
| Manual release workflow   | prod        | CI: same checks, `ENVIRONMENT=prod`, creates semver tag       |

```
feature branch → PR to main
```

- **Pre-commit hooks** run lint, typecheck, security, and tests locally before each commit.
- PR to `main` triggers CI with `ENVIRONMENT=dev` — merge is blocked until all checks pass.
- **Backtest matrix** — manual `workflow_dispatch` with configurable parameters via Actions console.
- **Release workflow** — manual `workflow_dispatch` for production release. Commitizen auto-detects the next semver from conventional commits since the last tag, updates `pyproject.toml`, generates `CHANGELOG.md` incrementally, creates the git tag, and publishes a GitHub Release with release notes. Inputs: confirm `"I UNDERSTAND"` + optional `increment` override (`patch`/`minor`/`major`) for when auto-detection isn't sufficient.
- Dependabot PRs target `main` — dependency updates trigger int CI automatically.
- **CHANGELOG.md** is auto-generated from conventional commits by the release workflow — do not edit manually.

______________________________________________________________________

## Safety Reminders

### Never Trade in Live Mode Without Testing

1. Start in `dev` environment — validate with mock API
1. Promote to `int` environment — paper trade with real market data
1. Verify all safety limits work in `int` for at least 24 hours
1. **Enable live mode explicitly:**
   ```bash
   revt config set TRADING_MODE live --env prod
   ```
1. Start with small capital: `revt config set MAX_CAPITAL 500 --env prod`
1. Go live: `revt run --env prod` (prompts "I UNDERSTAND")

### Environment Parity — Critical Rule

All three environments execute **identical code paths**. Only the data source differs:

- `dev` → Mock API (synthetic data)
- `int` → Real API (live market data)
- `prod` → Real API (live market data)

**The rule:** If behavior X works in `dev` or `int`, it must work exactly the same in `prod`.

**Never add environment-specific branches** that skip logic (e.g., fee calculation, position tracking). Paper mode simulates fills locally, but all accounting must use the same formulas as live mode.

### Documentation Structure

The project has two primary user-facing guides:

- **docs/END_USER_GUIDE.md** — For binary users: download, configure, start trading (no source needed)
- **docs/DEVELOPER_GUIDE.md** — For developers: source setup, make commands, advanced usage

Update the appropriate guide when making user-facing changes.

______________________________________________________________________

**Remember: This is a financial trading system. Every line of code could impact real money. Test thoroughly. Be conservative. Fail fast and safely.**
