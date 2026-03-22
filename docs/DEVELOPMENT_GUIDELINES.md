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
    "TRADING_MODE not found in 1Password config.\n"
    "Run: make opconfig-init\n"
    "Or manually set: make opconfig-set KEY=TRADING_MODE VALUE=paper"
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
        self.ema = None

    def update(self, price):
        if self.ema is None:
            self.ema = price
        else:
            self.ema = (price * self.multiplier) + (self.ema * (1 - self.multiplier))
        return self.ema  # O(1)!
```

______________________________________________________________________

## Configuration Management

All trading config MUST be in 1Password. No code defaults.

```python
# WRONG - has code default
trading_mode: TradingMode = TradingMode.PAPER  # Risky!

# RIGHT - fails if not in 1Password
trading_mode_str = get_config("TRADING_MODE", None)
if not trading_mode_str:
    raise RuntimeError(
        "TRADING_MODE not found in 1Password config.\n" "Run: make opconfig-init"
    )
```

See [1Password docs](1PASSWORD.md) for details on config fields and commands.

______________________________________________________________________

## Git Commit Guidelines

```
<type>: <short description>

<optional detailed description>
```

**Types:** `feat`, `fix`, `test`, `refactor`, `docs`, `chore`

______________________________________________________________________

## Pre-commit Checklist

Before committing code:

- [ ] Tests written BEFORE code implementation
- [ ] All tests pass (`make test`)
- [ ] No floating-point arithmetic for financial calculations
- [ ] Type hints on all functions
- [ ] Critical tests documented with WHY and context
- [ ] Pre-commit hooks pass (`make pre-commit`)
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

| Environment | API                  | Trading Mode  | DB File        | 1Password Items                        |
| ----------- | -------------------- | ------------- | -------------- | -------------------------------------- |
| `dev`       | Mock (no real calls) | Paper only    | `data/dev.db`  | `*-credentials-dev` / `*-config-dev`   |
| `int`       | Real Revolut X API   | Paper only    | `data/int.db`  | `*-credentials-int` / `*-config-int`   |
| `prod`      | Real Revolut X API   | Paper or Live | `data/prod.db` | `*-credentials-prod` / `*-config-prod` |

### Key rules

- **`ENVIRONMENT` must be set** before any Python process that imports `src.config`. The Makefile sets it automatically; for manual runs use `--env` or `export ENVIRONMENT=dev`.
- **`TRADING_MODE=live` is only allowed in `ENVIRONMENT=prod`** — enforced in `Settings.model_post_init`.
- **Separate API keys per environment** — if a dev key leaks, prod is unaffected.
- **Tests always run with `ENVIRONMENT=dev`** — set in `conftest.py` before the `Settings` singleton is created.

### Running in each environment

```bash
make run-dev          # mock API, paper mode
make run-int          # real API, paper mode
make run-prod-paper   # real API, paper mode
make run-prod-live    # real API, live trading (requires confirmation)
```

### Promotion flow

```
feature branch → PR → main (dev)
                         ↓
                   run-int (paper trade with real API for N hours)
                         ↓
                   tag release → run-prod-paper → run-prod-live
```

______________________________________________________________________

## Safety Reminders

### Never Trade in Live Mode Without Testing

1. Start in `dev` environment — validate with mock API
1. Promote to `int` environment — paper trade with real market data
1. Verify all safety limits work in `int` for at least 24 hours
1. Only then move to `prod` with `make run-prod-paper` first
1. After thorough validation, use `make run-prod-live`

______________________________________________________________________

**Remember: This is a financial trading system. Every line of code could impact real money. Test thoroughly. Be conservative. Fail fast and safely.**
