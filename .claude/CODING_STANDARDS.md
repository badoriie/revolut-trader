# Coding Standards for Revolut Trading Bot

## Why Code Quality Matters

**This is a financial trading system handling real money.** Code quality is not a "nice to have" - it's a critical requirement for:

- **Financial Safety**: Bugs can cause immediate monetary losses
- **System Reliability**: Trading must be consistent and predictable 24/7
- **Regulatory Compliance**: Code must be auditable and explainable
- **Emergency Response**: You need to debug issues quickly, often under pressure
- **Risk Management**: Poor code = unpredictable behavior = unmanageable risk

## Core Principles

### 1. Readability First

Code is read 10x more than it's written. Optimize for the reader, not the writer.

**Good:**

```python
def calculate_position_size(
    account_balance: float,
    risk_percentage: float,
    entry_price: float,
    stop_loss_price: float,
) -> float:
    """Calculate position size based on risk parameters.

    Args:
        account_balance: Current account balance in USD
        risk_percentage: Percentage of account to risk (0.0-1.0)
        entry_price: Planned entry price
        stop_loss_price: Stop loss price

    Returns:
        Number of shares/units to buy
    """
    risk_amount = account_balance * risk_percentage
    price_risk_per_unit = abs(entry_price - stop_loss_price)

    if price_risk_per_unit == 0:
        raise ValueError("Entry and stop loss prices cannot be equal")

    return risk_amount / price_risk_per_unit
```

**Bad:**

```python
def calc_pos(bal, risk, entry, sl):  # What units? What's the logic?
    r = bal * risk
    pr = abs(entry - sl)
    return r / pr  # What if pr is 0?
```

### 2. Explicit Over Clever

Simple, obvious code beats clever one-liners. If you need to think hard to understand it, it's too clever.

**Good:**

```python
def should_execute_trade(signal: Signal, risk_manager: RiskManager) -> bool:
    """Determine if trade should be executed based on risk rules."""
    if not signal.is_valid():
        logger.info("Rejecting invalid signal")
        return False

    if not risk_manager.can_open_position():
        logger.info("Rejecting trade: risk limits exceeded")
        return False

    if not risk_manager.validate_position_size(signal.size):
        logger.info("Rejecting trade: position size too large")
        return False

    return True
```

**Bad:**

```python
def should_execute_trade(s, rm):
    return s.is_valid() and rm.can_open_position() and rm.validate_position_size(s.size)
    # Good luck debugging which condition failed!
```

### 3. Type Safety

Use type hints everywhere. They're documentation, IDE support, and bug prevention rolled into one.

**Good:**

```python
from typing import List, Optional
from decimal import Decimal


def calculate_total_exposure(
    positions: List[Position], market_prices: dict[str, Decimal]
) -> Decimal:
    """Calculate total portfolio exposure in USD."""
    total = Decimal("0")

    for position in positions:
        price = market_prices.get(position.symbol)
        if price is None:
            raise ValueError(f"Missing price for {position.symbol}")

        total += position.quantity * price

    return total
```

**Bad:**

```python
def calculate_total_exposure(positions, prices):  # What types? What's returned?
    total = 0
    for p in positions:
        total += p.quantity * prices[p.symbol]  # KeyError waiting to happen
    return total
```

### 4. Error Handling

Handle errors explicitly. Never swallow exceptions silently.

**Good:**

```python
async def execute_order(self, order: Order) -> OrderResult:
    """Execute order with proper error handling."""
    try:
        response = await self.api_client.place_order(order)

        if not response.success:
            logger.error(
                f"Order rejected: {response.error_message}",
                extra={"order_id": order.id, "symbol": order.symbol},
            )
            raise OrderRejectionError(response.error_message)

        logger.info(
            f"Order executed successfully",
            extra={"order_id": response.order_id, "fill_price": response.fill_price},
        )

        return OrderResult(
            success=True, order_id=response.order_id, fill_price=response.fill_price
        )

    except NetworkError as e:
        logger.error(f"Network error during order execution: {e}")
        raise OrderExecutionError(f"Network failure: {e}") from e

    except ValidationError as e:
        logger.error(f"Invalid order parameters: {e}")
        raise OrderValidationError(f"Order validation failed: {e}") from e
```

**Bad:**

```python
async def execute_order(self, order):
    try:
        response = await self.api_client.place_order(order)
        return response
    except:  # Catching everything and hiding errors!
        return None  # Silent failure - disaster waiting to happen
```

### 5. Testing is Mandatory

No code goes to production without tests. Period.

**Required:**

```python
# tests/test_risk_manager.py


def test_position_size_respects_max_risk():
    """Test that position sizing never exceeds maximum risk per trade."""
    risk_manager = RiskManager(
        max_risk_per_trade=0.02, account_balance=10000  # 2% max risk
    )

    # Should limit position to $200 risk (2% of $10,000)
    position_size = risk_manager.calculate_position_size(
        entry_price=100.0, stop_loss_price=90.0  # $10 risk per share
    )

    # Max risk is $200, so max 20 shares ($200 / $10 per share)
    assert position_size == 20


def test_position_size_rejects_zero_stop_loss_distance():
    """Test that position sizing fails when entry equals stop loss."""
    risk_manager = RiskManager(max_risk_per_trade=0.02, account_balance=10000)

    with pytest.raises(ValueError, match="Stop loss must differ from entry"):
        risk_manager.calculate_position_size(
            entry_price=100.0, stop_loss_price=100.0  # Same as entry - invalid!
        )
```

### 6. Documentation

All public functions need docstrings. Complex logic needs comments explaining WHY, not WHAT.

**Good:**

```python
def adjust_position_for_correlation(
    position_size: float,
    existing_positions: List[Position],
    correlation_matrix: dict[tuple[str, str], float],
) -> float:
    """Adjust position size based on correlation with existing positions.

    Reduces position size when adding a highly correlated position to avoid
    concentration risk. For example, if we already hold AAPL and are adding
    MSFT (tech stocks, often correlated), we reduce the MSFT position size.

    Args:
        position_size: Initial calculated position size
        existing_positions: Current portfolio positions
        correlation_matrix: Pairwise correlations between symbols

    Returns:
        Adjusted position size (reduced if high correlation detected)

    Example:
        >>> positions = [Position("AAPL", 100)]
        >>> correlations = {("AAPL", "MSFT"): 0.8}  # High correlation
        >>> adjust_position_for_correlation(50, positions, correlations)
        25.0  # Reduced by 50% due to high correlation
    """
    # Implementation...
```

## Code Organization

### File Structure

Keep files focused and reasonably sized (< 500 lines):

```
src/
├── strategies/
│   ├── base_strategy.py      # Abstract base (< 200 lines)
│   ├── market_making.py      # One strategy per file
│   └── momentum.py
├── risk_management/
│   ├── risk_manager.py       # Core risk logic
│   └── position_sizer.py     # Position sizing logic
└── execution/
    ├── executor.py            # Order execution
    └── order_validator.py     # Order validation
```

### Function Size

Keep functions focused on one thing:

- Ideal: 10-20 lines
- Maximum: 50 lines
- If longer, break into smaller functions

### Class Design

Follow Single Responsibility Principle:

**Good:**

```python
class OrderExecutor:
    """Handles order execution only."""


class RiskValidator:
    """Validates risk parameters only."""


class PositionManager:
    """Manages position tracking only."""
```

**Bad:**

```python
class TradingSystem:
    """Does everything - executes, validates, manages, logs, etc."""

    # 2000 lines of mixed responsibilities
```

## Naming Conventions

### Variables and Functions

```python
# Good - descriptive, unambiguous
max_position_size: float
daily_loss_limit: Decimal
calculate_sharpe_ratio()
validate_order_parameters()

# Bad - ambiguous, unclear
max_pos: float  # Max what? Size, count, value?
limit: Decimal  # What kind of limit?
calc_sr()  # What's sr?
validate()  # Validate what?
```

### Constants

```python
# Use UPPER_CASE for constants
MAX_POSITION_SIZE_USD = 10000
DEFAULT_STOP_LOSS_PERCENTAGE = 0.02
API_TIMEOUT_SECONDS = 30
```

### Classes

```python
# Use PascalCase for classes
class RiskManager:
    pass


class MarketMakingStrategy:
    pass
```

## Common Patterns

### Dependency Injection

Make dependencies explicit:

**Good:**

```python
class TradingBot:
    def __init__(
        self,
        strategy: BaseStrategy,
        risk_manager: RiskManager,
        executor: OrderExecutor,
        notifier: TelegramNotifier,
    ):
        self.strategy = strategy
        self.risk_manager = risk_manager
        self.executor = executor
        self.notifier = notifier
```

**Bad:**

```python
class TradingBot:
    def __init__(self):
        self.strategy = MarketMakingStrategy()  # Hard-coded dependency
        self.risk_manager = RiskManager()  # Can't inject mocks for testing
```

### Configuration

Use Pydantic for configuration:

```python
from pydantic import BaseSettings, Field


class TradingConfig(BaseSettings):
    """Trading bot configuration with validation."""

    max_position_size: float = Field(
        ..., gt=0, description="Maximum position size in USD"
    )

    max_daily_loss: float = Field(
        ...,
        gt=0,
        lt=1,
        description="Maximum daily loss as fraction of account (0.0-1.0)",
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
```

### Logging

Log with context:

```python
logger.info(
    "Order executed",
    extra={
        "order_id": order.id,
        "symbol": order.symbol,
        "quantity": order.quantity,
        "price": order.price,
        "timestamp": datetime.utcnow().isoformat(),
    },
)
```

## Performance vs. Readability

**Rule of thumb:** Optimize for readability first, performance second.

Only optimize for performance when:

1. Profiling shows it's actually a bottleneck
1. The optimization doesn't sacrifice much readability
1. You add comments explaining the optimization

```python
# OK to optimize hot paths if necessary
def calculate_portfolio_value_optimized(positions: List[Position]) -> Decimal:
    """Calculate portfolio value.

    Note: Using list comprehension instead of loop for performance.
    This is called 1000s of times per second in backtesting.
    """
    return sum(p.quantity * p.current_price for p in positions)
```

## Code Review Checklist

Before submitting code, verify:

- [ ] All functions have type hints
- [ ] All public functions have docstrings
- [ ] No magic numbers (use named constants)
- [ ] Error handling is explicit and logged
- [ ] Tests exist and pass
- [ ] No TODO/FIXME comments (create issues instead)
- [ ] Code follows project structure
- [ ] No sensitive data (API keys, passwords) in code
- [ ] Logging is appropriate (not too verbose, not too sparse)
- [ ] Complex logic has explanatory comments

## Anti-Patterns to Avoid

### 1. God Classes

Classes that do everything. Split them up.

### 2. Magic Numbers

```python
# Bad
if position_size > 10000:  # Why 10000?

# Good
if position_size > MAX_POSITION_SIZE_USD:
```

### 3. Swallowing Exceptions

```python
# Bad
try:
    execute_order()
except:
    pass  # Silent failure!

# Good
try:
    execute_order()
except OrderError as e:
    logger.error(f"Order failed: {e}")
    raise
```

### 4. Premature Optimization

Don't optimize until you've proven it's a problem.

### 5. Copy-Paste Code

If you're copying code, extract a function instead.

## Tools and Enforcement

### Required Tools

```bash
# Type checking
make typecheck  # or: uv run mypy src/ cli/

# Code formatting
make format     # or: uv run ruff format src/ tests/ cli/

# Linting
make lint       # or: uv run ruff check src/ tests/ cli/

# Testing
make test       # or: uv run pytest --cov=src --cov-report=term-missing

# Run all checks
make check
```

### Pre-commit Hooks

Pre-commit hooks are configured to enforce code quality standards automatically.

#### Setup (One-time)

```bash
make pre-commit-install
```

#### What Gets Checked

The pre-commit hooks will automatically check on every commit:

1. **Basic Checks**

   - Trailing whitespace removal
   - End-of-file fixer
   - YAML/TOML/JSON validation
   - Large file detection
   - Merge conflict detection
   - Private key detection

1. **Code Quality**

   - **Ruff**: Linting and auto-formatting
   - **Ruff Format**: Code formatting (replaces black)

1. **Type Safety**

   - **Mypy**: Type checking (excludes tests/ and cli/)

1. **Security**

   - **Bandit**: Security vulnerability scanning

1. **Documentation**

   - **Mdformat**: Markdown file formatting

#### Manual Execution

Run hooks on all files without committing:

```bash
make pre-commit
```

#### Configuration

The hooks are configured in `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    # Basic checks
  - repo: https://github.com/astral-sh/ruff-pre-commit
    # Linting and formatting
  - repo: https://github.com/pre-commit/mirrors-mypy
    # Type checking
  - repo: https://github.com/PyCQA/bandit
    # Security scanning
  - repo: https://github.com/executablebooks/mdformat
    # Markdown formatting
```

#### Skipping Hooks (Use Sparingly)

Only when absolutely necessary:

```bash
git commit --no-verify -m "Emergency hotfix"
```

**Note**: This bypasses all quality checks. Use only for emergencies.

## Learning Resources

- [Clean Code by Robert C. Martin](https://www.amazon.com/Clean-Code-Handbook-Software-Craftsmanship/dp/0132350882)
- [Python Type Hints](https://docs.python.org/3/library/typing.html)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [pytest Documentation](https://docs.pytest.org/)

## Remember

**You're writing code that handles real money. Every line matters.**

When in doubt, ask yourself:

- "If this code fails at 3 AM, can I debug it quickly?"
- "Would a new team member understand this?"
- "If this loses money, can I explain what went wrong?"

If the answer is no, refactor until it's yes.
