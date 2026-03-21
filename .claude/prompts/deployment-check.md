# Deployment Checklist Template

Templates for preparing for deployment or validating configuration.

## Pre-Paper Trading Checklist

```
Validate my setup before starting paper trading:

**Configuration (1Password)**
- Run `make opconfig-show` and review settings
- Verify TRADING_MODE is set to "paper"
- Validate TRADING_PAIRS are correct
- Review DEFAULT_STRATEGY selection
- Check INITIAL_CAPITAL is appropriate

**Risk Parameters**
- Check RISK_LEVEL setting
- Verify position size limits are reasonable
- Review stop loss percentages
- Validate max open positions

**API Setup**
- Verify API key is valid (`make opstatus`)
- Validate API authentication works (`make api-test`)
- Test API connectivity (`make api-balance`)

**Testing**
- Confirm all tests pass (`make test`)
- Verify type checking passes (`make typecheck`)
- Check code formatting (`make lint`)

**Database**
- Verify encryption is active (`make db-encrypt-status`)

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

**Configuration Validation (1Password)**
- [ ] `make opconfig-set KEY=TRADING_MODE VALUE=live`
- [ ] API credentials are valid (`make opstatus`, `make api-test`)
- [ ] Trading pairs are correct (`make opconfig-show`)
- [ ] Risk level appropriate for live trading
- [ ] Position sizes appropriate for account balance

**Account Validation**
- [ ] Revolut account funded appropriately
- [ ] Account balance matches expected capital (`make api-balance`)
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
- [ ] All tests pass (`make test`)
- [ ] Type checking passes (`make typecheck`)
- [ ] Code is formatted (`make lint`)
- [ ] No security vulnerabilities identified
- [ ] Recent commits reviewed

**Emergency Procedures**
- [ ] Know how to stop the bot immediately
- [ ] Backup of configuration saved
- [ ] Rollback plan documented
- [ ] Recovery procedures documented

**Incremental Deployment**
- [ ] Start with single trading pair
- [ ] Use minimum position sizes initially
- [ ] Monitor for first few hours continuously
- [ ] Gradually increase position sizes
- [ ] Add additional pairs one at a time

Review each item carefully. This is REAL MONEY at risk.
```

## Configuration Validation

```
Validate my 1Password configuration before deployment:

**Current Configuration**:
Run `make opconfig-show` and share the output.

**Account Details**:
- Account balance: €[AMOUNT]
- Desired risk level: [conservative/moderate/aggressive]
- Trading experience: [beginner/intermediate/advanced]

**Questions**:
1. Are risk parameters appropriate for my account size?
2. Are position sizes safe for my risk tolerance?
3. Is the strategy selection appropriate?
4. Are trading pairs suitable for my strategy?

Provide detailed recommendations for each configuration parameter.
```

## Gradual Rollout Plan

```
Help me create a gradual rollout plan for live trading:

**Starting Conditions**:
- Account size: €[AMOUNT]
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

## Risk Parameter Optimization

```
Help me optimize risk parameters for live trading:

**Account Profile**:
- Total capital: €[AMOUNT]
- Risk tolerance: [Low/Medium/High]
- Max acceptable drawdown: [X]%
- Target annual return: [X]%

**Current Parameters** (from `make opconfig-show`):
- Strategy: [STRATEGY_NAME]
- Risk level: [LEVEL]
- Trading pairs: [List]

Suggest optimized parameters with reasoning for each.
```

## Strategy Selection Guidance

```
Help me choose the best strategy for my situation:

**Market Conditions**:
- Current trend: [Bullish/Bearish/Sideways]
- Volatility: [High/Medium/Low]

**Account Details**:
- Capital: €[AMOUNT]
- Risk level: [conservative/moderate/aggressive]

**Available Strategies**:
1. Market Making - Profits from bid-ask spread
2. Momentum - Follows trends with EMA/RSI
3. Mean Reversion - Trades reversals with Bollinger Bands
4. Breakout - Trades range breakouts with RSI confirmation
5. Range Reversion - Buys near 24h low, sells near 24h high
6. Multi-Strategy - Weighted consensus of all above

Recommend the best strategy with appropriate risk parameters.
```

## System Health Check

```
Perform a system health check before deployment:

**Code Quality**
- Run: make test
- Run: make typecheck
- Run: make lint

**API Connectivity**
- Run: make api-test
- Run: make api-balance
- Run: make api-ticker SYMBOL=BTC-EUR

**Database**
- Run: make db-encrypt-status
- Run: make db-stats

**1Password**
- Run: make opstatus
- Run: make opconfig-show

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
- Review: `make db-analytics DAYS=7`
- Adjust if: [Conditions]

**Long-term Monitoring (Ongoing)**:
- Daily: `make db-analytics DAYS=1`
- Weekly: `make db-analytics DAYS=7`
- Monthly: `make db-analytics DAYS=30`

**Key Metrics to Track**:
- [ ] Total return
- [ ] Win rate
- [ ] Risk-adjusted returns
- [ ] Drawdown
- [ ] API errors
- [ ] Failed orders

Create a detailed monitoring plan.
```
