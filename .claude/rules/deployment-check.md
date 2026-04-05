# Deployment Checklists

## Pre-Paper Trading

- [ ] `revt config show` — review settings, verify TRADING_PAIRS, DEFAULT_STRATEGY, INITIAL_CAPITAL
- [ ] Risk parameters reasonable (RISK_LEVEL, position sizes, stop losses, max positions)
- [ ] API key valid (`revt ops --status`, `revt api test`, `revt api ready`)
- [ ] All tests pass (`just test`), type check (`just typecheck`), lint (`just lint`)

## Pre-Live Trading

**Safety (must all be true):**

- [ ] Paper trading completed 24-48h with no critical issues
- [ ] Strategy performance meets expectations in backtest (`revt backtest --compare`)
- [ ] Emergency shutdown tested and documented
- [ ] Risk parameters validated with real market data

**Configuration:**

- [ ] API credentials valid for prod (switch to tagged commit; `revt api test`, `revt api ready`)
- [ ] Account funded, balance matches expected capital (`revt api ready`)
- [ ] Risk level, position sizes, and trading pairs appropriate for account size
- [ ] Trading fees factored into strategy (MAKER_FEE_PCT, TAKER_FEE_PCT in 1Password)

**Code Quality:**

- [ ] All tests, type checks, lint, and security scans pass (`just check`)
- [ ] No security vulnerabilities, recent commits reviewed

**Incremental Rollout:**

1. Start with single pair, minimum positions, monitor continuously
1. After 3 days: add 1-2 pairs if stable
1. After 7 days: full pairs and position sizes if metrics are healthy

## Post-Deployment Monitoring

- First 24h: check every 1-2 hours, watch for errors and unexpected behavior
- First week: `revt db analytics --days 7` daily
- Ongoing: `revt db analytics --days 30` weekly, `revt db report` monthly
- Track: total return, win rate, drawdown, API errors, failed orders
