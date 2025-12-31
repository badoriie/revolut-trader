# Development Guidelines

## Test-Driven Development (TDD) - MANDATORY

**CRITICAL: All new functionality MUST follow Test-Driven Development.**

### The TDD Cycle

```
1. Write Test (based on scenario/requirement)
   ↓
2. Run Test - it FAILS (proves we're testing new functionality)
   ↓
3. Write minimal code to pass the test
   ↓
4. Run Test - it PASSES
   ↓
5. Refactor if needed (tests ensure nothing breaks)
```

### Why TDD is Critical for Trading Bots

This is a **financial trading system**. Wrong behavior = potential financial loss.

- ✅ **Safety requirements drive code** - Tests define safe behavior BEFORE implementation
- ✅ **No untested code** - Every function has tests proving it works correctly
- ✅ **Requirements are clear** - Tests document expected behavior
- ✅ **Prevents bugs** - Can't write code that violates safety requirements
- ✅ **Mathematical correctness** - Tests verify calculations with known values
- ✅ **Regression prevention** - Tests catch when changes break existing functionality

### Example: Adding New Risk Control

**❌ WRONG Approach:**

```python
# 1. Write code first
def validate_position_size(size, portfolio):
    return size < portfolio * 0.05


# 2. Write tests to verify existing code
def test_position_size():
    assert validate_position_size(100, 10000)  # Just tests current behavior
```

**✅ CORRECT Approach:**

```python
# 1. Write test FIRST based on requirement
def test_position_size_must_not_exceed_5_percent():
    """CRITICAL: Position size MUST be ≤5% of portfolio.

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
# 5. Now we KNOW it works correctly
```

## Test Categories and Requirements

### 1. Safety-Critical Tests (HIGHEST Priority)

Tests that prevent financial loss or dangerous operations.

**Requirements:**

- MUST document WHY the test is critical
- MUST include the safety requirement ID (e.g., SAF-01)
- MUST test both normal and edge cases
- MUST use exact Decimal arithmetic (no floats for money)

**Example:**

```python
def test_daily_loss_limit_stops_trading():
    """CRITICAL: Trading MUST stop when daily loss limit hit.

    Context: Safety requirement SAF-07
    Critical because: Prevents revenge trading, protects capital

    Scenario: Conservative = 3% loss limit on 10,000 EUR = 300 EUR
    After losing 300 EUR, all new orders must be rejected
    """
    # Test implementation...
```

### 2. Calculation Tests (CRITICAL)

Tests that verify mathematical correctness.

**Requirements:**

- MUST use Decimal type (not float)
- MUST test with known, manually verified values
- MUST test edge cases (zero, negative, very large/small)
- MUST verify no floating-point errors

**Example:**

```python
def test_pnl_calculation_long_position():
    """CRITICAL: PnL = (current_price - entry_price) * quantity

    Scenario:
    - Buy 1 BTC at 50,000 EUR
    - Price rises to 55,000 EUR
    - Expected PnL = (55,000 - 50,000) * 1 = 5,000 EUR
    """
    position = Position(
        side=OrderSide.BUY,
        quantity=Decimal("1"),
        entry_price=Decimal("50000"),
        current_price=Decimal("50000"),
    )

    position.update_price(Decimal("55000"))

    expected_pnl = Decimal("5000")
    assert position.unrealized_pnl == expected_pnl
```

### 3. Integration Tests

Tests that verify components work together correctly.

**Requirements:**

- Test realistic scenarios
- Use mock external dependencies (1Password, API)
- Test error handling and recovery

### 4. Unit Tests

Tests for individual functions/methods.

**Requirements:**

- One test per behavior
- Clear test names describing what's tested
- Fast execution (no I/O, no sleep)

## Code Quality Standards

### Use Decimal for Financial Calculations

**❌ NEVER:**

```python
price = 50000.12
quantity = 0.1
value = price * quantity  # Floating point errors!
```

**✅ ALWAYS:**

```python
price = Decimal("50000.12")
quantity = Decimal("0.1")
value = price * quantity  # Exact!
```

### Type Hints Required

All functions MUST have type hints:

```python
def calculate_position_size(
    portfolio_value: Decimal, price: Decimal, signal_strength: float = 1.0
) -> Decimal:
    """Calculate position size."""
    # Implementation...
```

### Error Messages Must Be Actionable

**❌ Bad:**

```python
raise RuntimeError("Invalid config")
```

**✅ Good:**

```python
raise RuntimeError(
    "TRADING_MODE not found in 1Password config.\n"
    "Run: make opconfig-init\n"
    "Or manually set: make opconfig-set KEY=TRADING_MODE VALUE=paper"
)
```

## Testing Best Practices

### Test Structure

Use the AAA pattern (Arrange, Act, Assert):

```python
def test_stop_loss_calculation():
    """Test description."""
    # Arrange - Set up test data
    entry_price = Decimal("50000")
    side = OrderSide.BUY

    # Act - Perform the action
    stop_loss = calculate_stop_loss(entry_price, side)

    # Assert - Verify the result
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

### Document Test Context

Every critical test MUST include:

- **What** is being tested
- **Why** it's critical (link to requirement)
- **Scenario** with example values
- **Expected behavior**

```python
def test_order_value_exceeds_portfolio_rejected():
    """CRITICAL: Order worth more than entire portfolio MUST be rejected.

    Context: Safety requirement SAF-03
    Critical because: Could attempt to use leverage or cause massive loss

    Scenario: Portfolio = 10,000 EUR, try to buy 100 BTC @ 50,000 EUR
    Expected: Order rejected with clear error message
    """
```

## Pre-commit Checklist

Before committing code:

- [ ] All tests written BEFORE code implementation
- [ ] All tests pass (`pytest tests/`)
- [ ] No floating-point arithmetic for financial calculations
- [ ] Type hints on all functions
- [ ] Critical tests documented with WHY and context
- [ ] Pre-commit hooks pass (`make pre-commit`)
- [ ] No secrets in code (use 1Password)

## Configuration Management

### All Trading Config MUST Be in 1Password

**No code defaults** - Bot MUST fail if config missing.

```python
# ❌ WRONG - has code default
trading_mode: TradingMode = TradingMode.PAPER  # Risky!

# ✅ RIGHT - fails if not in 1Password
trading_mode_str = get_config("TRADING_MODE", None)
if not trading_mode_str:
    raise RuntimeError(
        "TRADING_MODE not found in 1Password config.\n" "Run: make opconfig-init"
    )
```

## Performance Guidelines

### Indicators MUST Be O(1) Update

Use incremental calculations, not recalculation:

```python
# ❌ WRONG - O(n) recalculation
class SMA:
    def __init__(self, period):
        self.prices = []

    def update(self, price):
        self.prices.append(price)
        if len(self.prices) > self.period:
            self.prices.pop(0)
        return sum(self.prices) / len(self.prices)  # O(n) every time!


# ✅ RIGHT - O(1) update
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

## Documentation Standards

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

    Example:
        >>> calculate_stop_loss(Decimal("50000"), OrderSide.BUY)
        Decimal("49250.00")
    """
```

### Inline Comments for Complex Logic

```python
# Standard EMA calculation: EMA = Price * k + EMA(previous) * (1 - k)
# where k = 2 / (period + 1)
self.ema = (price * self.multiplier) + (self.ema * (1 - self.multiplier))
```

## Git Commit Guidelines

### Commit Message Format

```
<type>: <short description>

<optional detailed description>

<optional test results>
```

**Types:**

- `feat`: New feature
- `fix`: Bug fix
- `test`: Add or update tests
- `refactor`: Code refactoring
- `docs`: Documentation changes
- `chore`: Maintenance tasks

**Example:**

```
test: Add PnL calculation tests for long/short positions

- Test long position profit/loss scenarios
- Test short position profit/loss scenarios
- Test fractional quantities
- Test decimal precision

All 21 calculation tests pass.
```

## Safety Reminders

### Never Trade in Live Mode Without Testing

1. Test in paper mode FIRST
1. Verify all safety limits work
1. Monitor for at least 24 hours
1. Only then consider live mode

### Configuration Checklist

- [ ] TRADING_MODE set in 1Password
- [ ] RISK_LEVEL appropriate for capital
- [ ] INITIAL_CAPITAL matches actual capital
- [ ] Daily loss limits configured
- [ ] Max position size tested
- [ ] Stop losses working

### Review Critical Changes

Changes to these areas require extra review:

- Risk management (position sizing, limits)
- PnL calculations
- Order execution logic
- Stop loss/take profit triggers
- Configuration loading

______________________________________________________________________

**Remember: This is a financial trading system. Every line of code could impact real money. Test thoroughly. Be conservative. Fail fast and safely.**
