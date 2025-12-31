# Mandatory Project Rules for Claude Code

**CRITICAL: These rules MUST be followed in EVERY session.**

## Primary Reference Document

All development work MUST follow the guidelines in:
**`docs/DEVELOPMENT_GUIDELINES.md`**

## Mandatory Rules

### 1. Test-Driven Development (TDD) - NON-NEGOTIABLE

**NEVER write code before writing tests.**

Every single time you implement ANY new functionality or fix:

1. ✅ Write the test FIRST based on the requirement/scenario
1. ✅ Run the test - it MUST fail (proves test is valid)
1. ✅ Write minimal code to make the test pass
1. ✅ Run the test - it MUST pass
1. ✅ Refactor if needed (with tests protecting you)

**Example workflow:**

```
User: "Add validation that position size can't exceed 10% of portfolio"

Claude MUST:
1. First write test in tests/safety/ that creates a position > 10% and asserts it's rejected
2. Run test - confirm it fails
3. Then add validation code
4. Run test - confirm it passes
```

### 2. Financial Calculation Standards

- ✅ **ALWAYS use Decimal** - NEVER use float for money/prices
- ✅ **Type hints required** on all functions
- ✅ **Verify calculations** with known values in tests
- ✅ **Document WHY** in test docstrings (not just WHAT)

**Example:**

```python
# ❌ NEVER
def calculate_pnl(entry: float, current: float, qty: float) -> float:
    return (current - entry) * qty


# ✅ ALWAYS
def calculate_pnl(
    entry_price: Decimal, current_price: Decimal, quantity: Decimal
) -> Decimal:
    """Calculate position PnL.

    Critical because: Core metric for portfolio value
    Formula: (current_price - entry_price) * quantity
    """
    return (current_price - entry_price) * quantity
```

### 3. Test Categories - Know the Difference

When writing tests, categorize correctly:

1. **Safety-Critical** (`tests/safety/`) - Prevents financial loss

   - MUST include: WHY critical, safety requirement ID, scenario with values
   - Examples: order limits, loss limits, position size validation

1. **Calculation Tests** (`tests/unit/test_calculations.py`) - Mathematical correctness

   - MUST use Decimal, verify with known values, test edge cases
   - Examples: PnL, position value, stop loss/take profit

1. **Unit Tests** (`tests/unit/`) - Component functionality

   - Examples: indicators, risk manager, individual functions

### 4. Configuration Management

- ✅ **NO code defaults** - All trading config MUST be in 1Password
- ✅ **Bot MUST fail** if required config missing
- ✅ **Mocks required** for testing (use `tests/mocks/mock_onepassword.py`)

**Example:**

```python
# ❌ WRONG - has code default
trading_mode: TradingMode = TradingMode.PAPER  # Dangerous!

# ✅ RIGHT - fails if not in 1Password
trading_mode_str = get_config("TRADING_MODE", None)
if not trading_mode_str:
    raise RuntimeError(
        "TRADING_MODE not found in 1Password config.\n" "Run: make opconfig-init"
    )
```

### 5. Before ANY Commit

Run this checklist:

- [ ] All tests written BEFORE code implementation
- [ ] All tests pass (`pytest tests/`)
- [ ] No floating-point arithmetic for financial calculations
- [ ] Type hints on all new functions
- [ ] Critical tests have docstrings explaining WHY
- [ ] No secrets in code (use 1Password)

### 6. Error Messages Must Be Actionable

**Bad:**

```python
raise RuntimeError("Invalid config")
```

**Good:**

```python
raise RuntimeError(
    "TRADING_MODE not found in 1Password config.\n"
    "Run: make opconfig-init\n"
    "Or manually set: make opconfig-set KEY=TRADING_MODE VALUE=paper"
)
```

## What to Do When User Asks for New Feature

**REQUIRED WORKFLOW:**

1. **Understand the requirement** - Ask clarifying questions if needed
1. **Plan the tests** - What scenarios need to be tested? What are the edge cases?
1. **Write tests FIRST** - Create test file/function with detailed docstring
1. **Run tests** - Verify they fail (if they pass, the test is wrong!)
1. **Implement code** - Minimal code to make tests pass
1. **Run tests** - Verify they pass
1. **Refactor** - Clean up if needed, tests ensure nothing breaks

**Example:**

```
User: "Add feature to prevent trading if portfolio drops below $1000"

Claude response:
"I'll implement this using TDD. First, let me write a test that verifies
trading is blocked when portfolio < $1000."

[Writes test first]
[Runs test - it fails]
[Implements feature]
[Runs test - it passes]
"Done! Test passes. The safety check is now enforced."
```

## Performance Requirements

- ✅ Indicators MUST be O(1) update (no recalculation of history)
- ✅ Use incremental formulas (EMA, Wilder's smoothing for RSI)
- ✅ Verify with tests (`tests/unit/test_indicators.py::TestIndicatorPerformance`)

## Documentation Standards

Every new function MUST have:

```python
def calculate_something(param1: Decimal, param2: OrderSide) -> Decimal:
    """One-line summary.

    Context: Why this function exists
    Critical because: Impact if it's wrong (for critical functions)

    Args:
        param1: Description
        param2: Description

    Returns:
        Description

    Example:
        >>> calculate_something(Decimal("100"), OrderSide.BUY)
        Decimal("150.00")
    """
```

## When in Doubt

1. **Check DEVELOPMENT_GUIDELINES.md** for detailed guidance
1. **Follow existing test patterns** in the codebase
1. **Ask user for clarification** rather than assume
1. **Write tests first** - always safer

## Remember

This is a **financial trading system**. Every line of code could impact real money.

- ⚠️ Wrong PnL calculation = wrong trading decisions
- ⚠️ Missing safety check = potential total loss
- ⚠️ Untested code = unknown behavior with real money

**When unsure: TEST FIRST. Fail safe.**

______________________________________________________________________

**These rules are MANDATORY and MUST be followed in every Claude Code session.**
