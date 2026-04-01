# Deployment Checklists

## Pre-Paper Trading

- [ ] `make opconfig-show` — review settings, verify TRADING_PAIRS, DEFAULT_STRATEGY, INITIAL_CAPITAL
- [ ] Risk parameters reasonable (RISK_LEVEL, position sizes, stop losses, max positions)
- [ ] API key valid (`make opstatus`, `make api-test`, `make api-ready`)
- [ ] All tests pass (`make test`), type check (`make typecheck`), lint (`make lint`)
- [ ] Database encryption active (`make db-encrypt-status`)

## Pre-Live Trading

**Safety (must all be true):**

- [ ] Paper trading completed 24-48h with no critical issues
- [ ] Strategy performance meets expectations
- [ ] Emergency shutdown tested and documented
- [ ] Risk parameters validated with real market data

**Configuration:**

- [ ] API credentials valid for prod (`make api-test ENV=prod`, `make api-ready ENV=prod`)
- [ ] Account funded, balance matches expected capital (`make api-ready ENV=prod`)
- [ ] Risk level, position sizes, and trading pairs appropriate for account size
- [ ] Trading fees factored into strategy

**Code Quality:**

- [ ] All tests, type checks, lint, and security scans pass (`make check`)
- [ ] No security vulnerabilities, recent commits reviewed

**Incremental Rollout:**

1. Start with single pair, minimum positions, monitor continuously
1. After 3 days: add 1-2 pairs if stable
1. After 7 days: full pairs and position sizes if metrics are healthy

## Post-Deployment Monitoring

- First 24h: check every 1-2 hours, watch for errors and unexpected behavior
- First week: `make db-analytics DAYS=7` daily
- Ongoing: `make db-analytics DAYS=30` weekly, `make db-report` monthly
- Track: total return, win rate, drawdown, API errors, failed orders
