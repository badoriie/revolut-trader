# Deployment Checklist Template

Use these templates when preparing for deployment or validating configuration.

## Pre-Paper Trading Checklist

```
Validate my setup before starting paper trading:

**Configuration**
- Review .env file configuration
- Verify TRADING_MODE is set to "paper"
- Check PAPER_INITIAL_CAPITAL is appropriate
- Validate TRADING_PAIRS are correct
- Review DEFAULT_STRATEGY selection

**Risk Parameters**
- Check RISK_LEVEL setting
- Verify position size limits are reasonable
- Review stop loss percentages
- Check take profit settings
- Validate max open positions

**API Setup**
- Verify API key is valid
- Check private key path is correct
- Validate API authentication works
- Test API connectivity

**Notifications**
- Verify Telegram bot token (if configured)
- Check Telegram chat ID
- Test notification delivery

**Testing**
- Confirm all tests pass
- Verify type checking passes
- Check code formatting

**Monitoring**
- Verify logging is configured
- Check log directory exists
- Review log rotation settings

Confirm all items and suggest any missing steps.
```

## Pre-Live Trading Checklist

```
I'm ready to deploy to LIVE trading. Perform final validation:

**CRITICAL SAFETY CHECKS**
- [ ] Paper trading completed successfully for at least 24-48 hours
- [ ] Strategy performance meets expectations
- [ ] No critical bugs or issues observed
- [ ] Risk parameters validated with real market data
- [ ] Emergency shutdown procedure documented and tested

**Configuration Validation**
- [ ] .env file: TRADING_MODE = "live"
- [ ] API credentials are for PRODUCTION (not sandbox)
- [ ] Trading pairs are correct
- [ ] Risk level appropriate for live trading
- [ ] Position sizes appropriate for account balance

**Account Validation**
- [ ] Revolut account funded appropriately
- [ ] Account balance matches expected capital
- [ ] API key has correct permissions
- [ ] API rate limits understood
- [ ] Trading fees considered in strategy

**Risk Management**
- [ ] Position size limits are conservative
- [ ] Stop loss percentages are appropriate
- [ ] Daily loss limit is set and tested
- [ ] Maximum positions limit is reasonable
- [ ] Total exposure limit is safe

**Code Quality**
- [ ] All tests pass (pytest --cov)
- [ ] Type checking passes (mypy src/)
- [ ] Code is formatted (black, ruff)
- [ ] No security vulnerabilities identified
- [ ] Recent commits reviewed

**Monitoring Setup**
- [ ] Telegram notifications configured and tested
- [ ] Logging level set appropriately (INFO recommended)
- [ ] Log rotation configured
- [ ] Monitoring dashboard ready (if applicable)
- [ ] Alert thresholds configured

**Emergency Procedures**
- [ ] Know how to stop the bot immediately
- [ ] Emergency contact information available
- [ ] Backup of configuration saved
- [ ] Rollback plan documented
- [ ] Recovery procedures documented

**Incremental Deployment**
- [ ] Start with single trading pair
- [ ] Use minimum position sizes initially
- [ ] Monitor for first few hours continuously
- [ ] Gradually increase position sizes
- [ ] Add additional pairs one at a time

**Documentation**
- [ ] Current configuration documented
- [ ] Strategy parameters recorded
- [ ] Risk limits documented
- [ ] Deployment date/time recorded
- [ ] Initial conditions noted

Review each item carefully. This is REAL MONEY at risk.
```

## Configuration Validation

```
Validate my configuration before deployment:

**Current Configuration**:
```
[Paste your .env content, replacing sensitive values with [REDACTED]]
```

**Account Details**:
- Account balance: $[AMOUNT]
- Desired risk level: [conservative/moderate/aggressive]
- Trading experience: [beginner/intermediate/advanced]
- Time commitment: [hours per day monitoring]

**Questions**:
1. Are risk parameters appropriate for my account size?
2. Are position sizes safe for my risk tolerance?
3. Are stop losses set correctly?
4. Is the strategy selection appropriate?
5. Are trading pairs suitable for my strategy?
6. Is the trading interval appropriate?

Provide detailed recommendations for each configuration parameter.
```

## Environment File Review

```
Review my .env configuration for issues:

```
[Paste .env content with sensitive values redacted]
```

Check for:
1. All required variables present
2. Values in correct format
3. Risk parameters appropriate
4. Trading mode correctly set
5. API credentials valid format
6. Paths exist and are accessible
7. Numerical values in valid ranges

Highlight any issues or recommendations.
```

## Gradual Rollout Plan

```
Help me create a gradual rollout plan for live trading:

**Starting Conditions**:
- Account size: $[AMOUNT]
- Strategy: [STRATEGY_NAME]
- Risk level: [LEVEL]

**Rollout Phases**:

Phase 1 (Days 1-3):
- Trading pairs: [List 1-2 pairs]
- Position size: [X]% of normal
- Monitoring: Continuous
- Success criteria: No critical errors, strategy performing as expected

Phase 2 (Days 4-7):
- Trading pairs: [Add 1-2 more]
- Position size: [X]% of normal
- Monitoring: [Frequency]
- Success criteria: [Define]

Phase 3 (Days 8-14):
- Trading pairs: [Full set]
- Position size: [Full]
- Monitoring: [Frequency]
- Success criteria: [Define]

Create a detailed rollout plan with specific criteria for advancing between phases.
```

## Paper Trading Analysis

```
Analyze my paper trading results before going live:

**Paper Trading Period**: [Date range]

**Performance Metrics**:
- Total return: [X]%
- Number of trades: [N]
- Win rate: [X]%
- Average winning trade: [X]%
- Average losing trade: [X]%
- Largest drawdown: [X]%
- Sharpe ratio: [X] (if calculated)

**Observations**:
[List any notable patterns or issues]

**Questions**:
1. Are these results realistic for live trading?
2. Are there any red flags?
3. Is the strategy robust enough?
4. What adjustments should I make?
5. Am I ready for live trading?

Provide honest assessment and recommendations.
```

## Risk Parameter Optimization

```
Help me optimize risk parameters for live trading:

**Account Profile**:
- Total capital: $[AMOUNT]
- Risk tolerance: [Low/Medium/High]
- Max acceptable drawdown: [X]%
- Target annual return: [X]%
- Trading experience: [Beginner/Intermediate/Advanced]

**Current Parameters**:
- Position size: [X]%
- Stop loss: [X]%
- Take profit: [X]%
- Max positions: [N]
- Daily loss limit: [X]%

**Trading Style**:
- Strategy: [STRATEGY_NAME]
- Holding period: [Intraday/Swing/Position]
- Trading pairs: [List]

Suggest optimized parameters with reasoning for each.
```

## Strategy Selection Guidance

```
Help me choose the best strategy for my situation:

**Market Conditions**:
- Current trend: [Bullish/Bearish/Sideways]
- Volatility: [High/Medium/Low]
- My outlook: [Your market view]

**Account Details**:
- Capital: $[AMOUNT]
- Risk level: [conservative/moderate/aggressive]
- Time availability: [How much monitoring time]

**Experience**:
- Trading experience: [Beginner/Intermediate/Advanced]
- Familiarity with crypto: [Low/Medium/High]
- Technical analysis knowledge: [Low/Medium/High]

**Available Strategies**:
1. Market Making - Profits from bid-ask spread
2. Momentum - Follows trends
3. Mean Reversion - Trades reversals
4. Multi-Strategy - Combines multiple approaches

Recommend:
1. Best strategy for my situation
2. Appropriate risk parameters
3. Trading pairs to start with
4. Expected performance characteristics
5. Key risks to monitor
```

## System Health Check

```
Perform a system health check before deployment:

**Code Quality**
- Run: pytest --cov
- Run: mypy src/
- Run: black src/ --check
- Run: ruff check src/

**API Connectivity**
- Test API authentication
- Verify market data fetching
- Check order submission (paper mode)
- Validate position querying

**Monitoring**
- Test Telegram notifications
- Verify logging working
- Check log rotation
- Test error alerts

**Data Storage**
- Verify data/ directory writable
- Check logs/ directory writable
- Test portfolio snapshot saving

**Risk Controls**
- Test stop loss triggering
- Verify position limit enforcement
- Check daily loss limit
- Validate emergency shutdown

Run all checks and report any failures.
```

## Post-Deployment Monitoring

```
Help me set up post-deployment monitoring:

**Immediate Monitoring (First 24 hours)**:
- Check every: [Frequency]
- Watch for: [Key metrics]
- Alert on: [Conditions]

**Short-term Monitoring (First week)**:
- Check every: [Frequency]
- Review: [Metrics to review]
- Adjust if: [Conditions]

**Long-term Monitoring (Ongoing)**:
- Daily checks: [What to check]
- Weekly review: [What to analyze]
- Monthly review: [What to assess]

**Key Metrics to Track**:
- [ ] Total return
- [ ] Win rate
- [ ] Average trade size
- [ ] Risk-adjusted returns
- [ ] Drawdown
- [ ] Position count
- [ ] API errors
- [ ] Failed orders
- [ ] Strategy performance

**Alert Conditions**:
- [ ] Daily loss > [X]%
- [ ] Drawdown > [X]%
- [ ] Failed orders > [N]
- [ ] API errors > [N]
- [ ] Unusual position sizes
- [ ] Strategy stopped generating signals

Create a detailed monitoring plan.
```

## Rollback Procedure

```
Help me document rollback procedures:

**When to Rollback**:
- [ ] Daily loss exceeds [X]%
- [ ] Multiple failed orders
- [ ] API connectivity issues
- [ ] Strategy behaving unexpectedly
- [ ] Risk limits being violated
- [ ] Other critical issues: [Specify]

**Rollback Steps**:
1. [How to stop the bot immediately]
2. [How to cancel open orders]
3. [How to close positions]
4. [How to verify shutdown]
5. [How to preserve logs/data]
6. [Who to notify]

**Recovery Steps**:
1. [How to analyze what went wrong]
2. [How to test fixes in paper mode]
3. [How to gradually restart]

Document complete rollback and recovery procedures.
```
