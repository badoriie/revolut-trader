# Testing & Debugging Templates

Templates for testing, debugging, and troubleshooting the trading bot.

## Write Unit Tests

```
Write comprehensive unit tests for [MODULE/CLASS/FUNCTION]:

**Target**: src/[PATH]

**Test Coverage Needed**:
- [ ] Happy path scenarios
- [ ] Edge cases
- [ ] Error conditions
- [ ] Boundary values
- [ ] Invalid inputs

**Specific Tests**:
1. [Describe test scenario 1]
2. [Describe test scenario 2]
3. [Describe test scenario 3]

**Mocking Required**:
- API calls
- Market data
- Time/datetime
- Random values

Follow pytest conventions and use pytest-asyncio for async tests.
```

## Debug Trading Issue

```
Help me debug this trading issue:

**Problem Description**:
[Describe what's happening vs what should happen]

**When It Occurs**:
- Frequency: [Always/Sometimes/Rarely]
- Conditions: [Market conditions, specific pairs, etc.]
- First noticed: [Date/time]

**Relevant Logs**:
```

[Paste relevant log entries]

```

**Steps to Reproduce**:
1. [Step 1]
2. [Step 2]
3. [Step 3]

**Expected Behavior**:
[What should happen]

**Actual Behavior**:
[What actually happens]

**Impact**:
- Severity: [Critical/High/Medium/Low]
- Financial impact: [Description]

Analyze and provide:
1. Root cause analysis
2. Immediate fix
3. Long-term solution
4. Prevention measures
```

## Log Analysis

```
Analyze trading logs for issues:

**Time Period**: [Date/time range]

**Focus Areas**:
- [ ] Order execution
- [ ] Position management
- [ ] Risk limit triggers
- [ ] API errors
- [ ] Strategy signals
- [ ] Performance issues

**Specific Concerns**:
[Describe any specific issues to investigate]

**Log Files**:
- logs/[filename]

Provide:
1. Summary of trading activity
2. Any errors or warnings
3. Performance metrics
4. Recommendations
```

## Strategy Backtesting

```
Help me set up backtesting for [STRATEGY_NAME]:

**Requirements**:
- Historical data period: [Date range]
- Trading pairs: [List]
- Initial capital: $[AMOUNT]
- Risk parameters: [Specify]

**Metrics to Calculate**:
- Total return
- Sharpe ratio
- Maximum drawdown
- Win rate
- Average trade return
- Risk-adjusted return

**Implementation**:
1. Design data collection approach
2. Create backtesting framework
3. Implement metrics calculation
4. Add visualization (if applicable)

Provide code and implementation plan.
```

## Performance Profiling

```
Profile the trading bot for performance issues:

**Symptoms**:
[Describe performance issues - slow execution, high memory, etc.]

**Areas to Profile**:
- [ ] Strategy signal generation
- [ ] API calls
- [ ] Data processing
- [ ] Position calculations
- [ ] Risk management checks

**Tools**:
- Python profilers (cProfile, line_profiler)
- Memory profiling
- Async task monitoring

Identify bottlenecks and suggest optimizations.
```

## Integration Testing

```
Create integration tests for:

**Components to Test**:
- [ ] API client + Revolut API
- [ ] Strategy + Market data
- [ ] Risk manager + Order executor
- [ ] Full trading loop

**Test Scenarios**:
1. [Scenario 1]
2. [Scenario 2]
3. [Scenario 3]

**Mock vs Real**:
- API calls: [Mocked/Real sandbox]
- Market data: [Historical/Live]
- Order execution: [Simulated/Paper]

**Success Criteria**:
[Define what success looks like]

Provide test implementation.
```

## Error Handling Review

```
Review error handling in [MODULE]:

**Check For**:
- [ ] All exceptions caught appropriately
- [ ] Proper error propagation
- [ ] Graceful degradation
- [ ] Error logging with context
- [ ] Recovery procedures
- [ ] User notifications

**Critical Paths**:
- Order submission
- Position updates
- API authentication
- Risk limit checks

**Test Error Scenarios**:
- Network failures
- API errors
- Invalid data
- Calculation errors
- Timeout conditions

Provide recommendations for improvement.
```

## Race Condition Testing

```
Test for race conditions in:

**Areas of Concern**:
- [ ] Concurrent order execution
- [ ] Position updates
- [ ] Balance calculations
- [ ] Risk limit checks

**Test Approach**:
1. Identify shared state
2. Create concurrent test scenarios
3. Use stress testing
4. Verify synchronization

**Tools**:
- pytest-asyncio
- concurrent.futures
- stress testing scripts

Provide test cases that could expose race conditions.
```

## Chaos Testing

```
Implement chaos testing for the trading bot:

**Failure Scenarios to Test**:
- [ ] API becomes unavailable mid-trade
- [ ] Market data stops updating
- [ ] Orders fail to execute
- [ ] Partial fills occur
- [ ] Network intermittent issues
- [ ] Memory/CPU constraints

**Expected Behaviors**:
- Graceful degradation
- No data corruption
- No financial loss from errors
- Proper error reporting
- Automated recovery

**Implementation**:
Create tests that inject failures and verify bot behavior.
```

## Debug API Issues

```
Debug API integration issues:

**Problem**:
[Describe API issue - auth failures, rejected orders, etc.]

**API Endpoint**:
[Which endpoint]

**Request Details**:
```

[Paste sanitized request details - NO API KEYS]

```

**Response**:
```

[Paste response]

```

**Expected**:
[What should happen]

**Actual**:
[What actually happens]

Analyze and provide:
1. Root cause
2. Fix
3. Test case to prevent regression
```

## Debug Position Management

```
Debug position management issue:

**Problem**:
[Describe issue - incorrect positions, duplicate positions, etc.]

**Current State**:
- Positions in bot: [List]
- Positions in Revolut: [List]
- Discrepancies: [Describe]

**Recent Activity**:
```

[Paste relevant logs showing position changes]

```

**Questions**:
1. Why are positions out of sync?
2. How did this happen?
3. How to reconcile?
4. How to prevent?

Provide analysis and fix.
```

## Debug Risk Limits

```
Debug risk limit issue:

**Problem**:
[Risk limit not triggering / triggering incorrectly]

**Configuration**:
- Risk level: [Level]
- Position size limit: [X]%
- Daily loss limit: [X]%
- Stop loss: [X]%

**Observed Behavior**:
[What happened]

**Expected Behavior**:
[What should happen]

**Relevant Code**:
src/risk_management/risk_manager.py

Analyze risk calculation logic and identify issues.
```

## Test Coverage Analysis

```
Analyze test coverage and suggest improvements:

**Current Coverage**:
```

[Paste pytest --cov output]

```

**Uncovered Critical Areas**:
[Identify important code without tests]

**Suggestions**:
1. Which tests to add first (prioritized)
2. Test scenarios to cover
3. Mocking strategies
4. Integration test needs

Provide specific test cases to implement.
```

## Debug Signal Generation

```
Debug strategy signal generation:

**Strategy**: [STRATEGY_NAME]

**Problem**:
[No signals / Too many signals / Wrong signals]

**Market Conditions**:
- Pair: [BTC-USD, etc.]
- Price: $[PRICE]
- Trend: [Up/Down/Sideways]
- Volatility: [High/Low]

**Expected Signal**:
[BUY/SELL/HOLD and why]

**Actual Signal**:
[What the strategy produced]

**Strategy Parameters**:
[List current parameter values]

Analyze strategy logic and identify why signals are incorrect.
```

## Memory Leak Detection

```
Investigate potential memory leak:

**Symptoms**:
- Memory usage: [Growing over time / Stable / Spikes]
- Duration running: [Hours/Days]
- Memory growth rate: [MB per hour]

**Suspected Areas**:
- [ ] Market data collection
- [ ] Log accumulation
- [ ] Position tracking
- [ ] API response caching

**Profiling Tools**:
- memory_profiler
- tracemalloc
- objgraph

Help identify and fix memory leaks.
```

## Load Testing

```
Design load tests for the trading bot:

**Scenarios**:
1. High-frequency trading (many signals)
2. Multiple trading pairs simultaneously
3. Volatile market conditions (rapid price changes)
4. Maximum position count
5. API rate limiting

**Metrics to Measure**:
- Response time
- CPU usage
- Memory usage
- API call efficiency
- Order execution latency

**Tools**:
- pytest-benchmark
- Custom load generators

Create load test implementation.
```

## Regression Testing

```
Create regression test suite:

**Critical Functionality**:
- [ ] Order execution
- [ ] Position management
- [ ] Risk limits
- [ ] Signal generation
- [ ] API authentication

**Test Data**:
- Historical market data
- Known edge cases
- Previous bug scenarios

**Automation**:
- Run on every commit
- Include in CI/CD (if applicable)

Provide regression test implementation.
```

## Debug Telegram Notifications

```
Debug Telegram notification issues:

**Problem**:
[Notifications not sending / Delayed / Wrong format]

**Configuration**:
- Bot token: [Configured? Yes/No]
- Chat ID: [Configured? Yes/No]

**Error Messages**:
```

[Paste any error messages]

```

**Expected**:
[What notifications should be sent]

**Actual**:
[What's happening]

Diagnose and fix notification issues.
```

## Async Code Review

```
Review async/await code for issues:

**File**: src/[PATH]

**Check For**:
- [ ] Missing await keywords
- [ ] Blocking calls in async functions
- [ ] Proper exception handling in async
- [ ] Correct use of asyncio.gather
- [ ] Task cancellation handling
- [ ] Event loop management

**Common Issues**:
- Deadlocks
- Race conditions
- Unhandled task exceptions
- Resource leaks

Identify and fix async issues.
```

## Data Validation Testing

```
Test data validation across the system:

**API Response Validation**:
- [ ] Price data
- [ ] Volume data
- [ ] Order responses
- [ ] Position data

**Configuration Validation**:
- [ ] .env values
- [ ] Risk parameters
- [ ] Trading pairs

**Input Validation**:
- [ ] Order quantities
- [ ] Prices
- [ ] Percentages

Create tests that attempt invalid data and verify proper rejection.
```
