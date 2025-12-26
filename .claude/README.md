# Claude Code Agent for Revolut Trading Bot

This directory contains a specialized Claude Code agent configuration optimized for the Revolut algorithmic trading bot project.

## Overview

The **Trading Bot Specialist** agent is designed to assist with:

- **Strategy Development**: Implement and optimize trading strategies
- **Risk Management**: Validate and configure risk parameters
- **Security Audits**: Review code for financial vulnerabilities
- **Testing**: Write comprehensive tests and perform backtesting
- **Deployment**: Ensure safe deployment with proper validation
- **Debugging**: Analyze logs and troubleshoot issues

## Quick Start

### Using the Skill

The trading bot skill is automatically available when working in this project directory. Claude Code will be aware of the project context and can provide specialized assistance.

### Common Commands

```bash
# Strategy Development
"Help me implement a new RSI-based mean reversion strategy"
"Review the momentum strategy and suggest improvements"
"What parameters should I use for conservative market making?"

# Security & Risk
"Audit the order execution code for security issues"
"Validate my risk parameters for a $10,000 account"
"Review changes before I deploy to live trading"

# Testing & Validation
"Write unit tests for the new strategy"
"Help me set up backtesting for the mean reversion strategy"
"Run all tests and validate the bot is ready for paper trading"

# Debugging & Monitoring
"Analyze today's trading logs for errors"
"Why are my stop losses not triggering?"
"Debug the position sizing calculation"

# Deployment
"Walk me through the pre-deployment checklist"
"Help me configure the bot for paper trading"
"Validate my 1Password credentials before going live"
```

## Project Structure

```
.claude/
├── README.md                 # This file (agent overview)
├── agent-config.json         # Agent configuration
├── CODING_STANDARDS.md       # Code quality standards (CRITICAL)
├── QUICK_START.md            # Quick start guide
├── skills/
│   └── trading-bot.md       # Trading bot specialist skill
└── prompts/
    ├── strategy-review.md   # Strategy review template
    ├── security-audit.md    # Security audit template
    ├── deployment-check.md  # Deployment checklist template
    └── testing-debug.md     # Testing and debugging template
```

## Safety Guidelines

### Critical Safety Rules

1. **Always test in paper mode first** before live trading
2. **Never bypass risk limits** in code or configuration
3. **Validate all financial calculations** before deployment
4. **Protect API credentials** - never commit to git
5. **Review security implications** of all changes

### Pre-Deployment Checklist

Before deploying to live trading:

- [ ] All tests pass (`make test`)
- [ ] Code quality checks pass (`make check`)
- [ ] Code follows CODING_STANDARDS.md
- [ ] Paper mode tested successfully for at least 24 hours
- [ ] Risk parameters validated for account size
- [ ] 1Password signed in (`make opstatus`)
- [ ] API credentials verified (`make opshow`)
- [ ] Telegram notifications working (if enabled)
- [ ] Stop loss and position limits tested
- [ ] Emergency shutdown procedure documented
- [ ] Backup of current configuration saved (`make backup`)

## Agent Capabilities

### 1. Strategy Development

The agent can help you:
- Implement new trading strategies following the `BaseStrategy` pattern
- Optimize existing strategy parameters
- Add technical indicators (RSI, MACD, Bollinger Bands, etc.)
- Validate signal generation logic
- Suggest improvements based on market conditions

Example:
```
"I want to add a Bollinger Bands strategy. Help me implement it following
the existing strategy pattern, with proper risk controls and tests."
```

### 2. Risk Management

The agent validates:
- Position sizing calculations
- Stop loss and take profit logic
- Maximum daily loss limits
- Portfolio exposure limits
- Risk-adjusted position sizing

Example:
```
"Review my risk parameters for a $50,000 account. I want to use
moderate risk level but be extra conservative on stop losses."
```

### 3. Security Auditing

The agent checks for:
- API authentication vulnerabilities
- Order validation and size limits
- Race conditions in order execution
- Credential exposure or logging
- Error handling in financial operations
- Cryptographic implementation (Ed25519)

Example:
```
"Perform a comprehensive security audit before I deploy to live trading.
Focus on order execution and API authentication."
```

### 4. Testing & Quality

The agent helps with:
- Writing unit tests for strategies and risk management
- Creating integration tests for API client
- Setting up backtesting frameworks
- Generating edge case tests
- Improving test coverage

Example:
```
"Write comprehensive tests for the MultiStrategy class, including
edge cases like conflicting signals and risk limit violations."
```

### 5. Deployment Support

The agent assists with:
- Configuration validation (1Password, config.py)
- Pre-deployment checklist verification
- Paper trading validation
- Live deployment gradual rollout
- Monitoring setup

Example:
```
"I'm ready to deploy to live trading. Walk me through the deployment
checklist and validate my configuration."
```

### 6. Debugging & Analysis

The agent can:
- Analyze log files for errors and issues
- Debug trading logic and execution problems
- Investigate position management issues
- Monitor API interactions
- Identify performance bottlenecks

Example:
```
"The bot placed duplicate orders this morning. Help me analyze the
logs and find the root cause."
```

## Code Quality Standards

### Clean and Maintainable Code is CRITICAL

**This is a financial trading system handling real money. Code quality is not optional - it's essential for:**
- **Safety**: Bugs can cause financial losses
- **Reliability**: Trading systems must be dependable 24/7
- **Auditability**: Code must be reviewable for compliance
- **Maintainability**: You'll need to debug at 2 AM when issues occur

📖 **See [CODING_STANDARDS.md](.claude/CODING_STANDARDS.md) for detailed guidelines and examples.**

### Core Principles

1. **Readability First**
   - Code is read 10x more than it's written
   - Use descriptive variable names (`position_size` not `ps`)
   - Keep functions short and focused (< 50 lines)
   - Avoid nested complexity (max 3 levels)

2. **Explicit Over Clever**
   - Simple, obvious code beats clever one-liners
   - Prefer clarity over performance micro-optimizations
   - Document "why" not "what" in comments

3. **Type Safety**
   - Use type hints for all function signatures
   - Leverage Pydantic models for data validation
   - Run mypy type checking before commits

4. **Error Handling**
   - Handle errors explicitly, never swallow exceptions
   - Use specific exception types
   - Log errors with context for debugging

5. **Testing is Mandatory**
   - Write tests before deploying to production
   - Test edge cases and failure scenarios
   - Maintain >80% code coverage

6. **Documentation**
   - All public functions must have docstrings
   - Document assumptions and constraints
   - Keep README and docs up to date

## Best Practices

### When Developing Strategies

1. Always inherit from `BaseStrategy` in `src/strategies/base_strategy.py`
2. Implement required methods: `analyze()`, `initialize()`, `cleanup()`
3. Use the `Signal` model for consistency
4. Include proper logging at DEBUG and INFO levels
5. Add comprehensive docstrings
6. Write unit tests before deploying
7. **Keep code clean and maintainable** - follow the Code Quality Standards above

### When Modifying Risk Management

1. Never reduce safety limits without thorough testing
2. Validate calculations with multiple test cases
3. Consider edge cases (market gaps, flash crashes)
4. Test with small positions first
5. Document reasoning for parameter changes

### When Working with API Client

1. Never log API keys or private keys
2. Always validate responses before using data
3. Handle rate limits gracefully
4. Implement proper retry logic with exponential backoff
5. Test authentication thoroughly

## File Organization

### Critical Files (Require Extra Review)

- `src/bot.py` - Main trading loop and orchestration
- `src/execution/executor.py` - Order execution and position management
- `src/risk_management/risk_manager.py` - Risk controls
- `src/api/client.py` - Revolut API authentication and requests

### Strategy Files

- `src/strategies/base_strategy.py` - Abstract base class
- `src/strategies/market_making.py` - Market making implementation
- `src/strategies/momentum.py` - Momentum/trend following
- `src/strategies/mean_reversion.py` - Mean reversion
- `src/strategies/multi_strategy.py` - Combined strategies

### Configuration Files

- `src/config.py` - Risk parameters and trading settings
- **1Password Vault** - All credentials stored securely (REQUIRED)
  - See `docs/1PASSWORD_INTEGRATION.md` for details
  - See `CREDENTIALS.md` for quick reference
- `Makefile` - All project commands
- `scripts/` - Setup and credential management scripts

## Monitoring & Logs

### Log Locations

- `logs/` - Trading bot logs (rotated daily, 30-day retention)
- `data/` - Portfolio snapshots and trading history

### Log Analysis

Ask the agent to help analyze logs:
```
"Analyze the last 24 hours of logs and summarize trading activity"
"Find any ERROR level logs from today"
"Show me all executed orders from this week"
```

## Advanced Usage

### Custom Strategy Development Workflow

1. **Design Phase**
   ```
   "I want to create a strategy that trades based on order flow imbalance.
   Help me design the signal generation logic and risk parameters."
   ```

2. **Implementation Phase**
   ```
   "Implement the order flow imbalance strategy we designed, following
   the BaseStrategy pattern."
   ```

3. **Testing Phase**
   ```
   "Write comprehensive unit tests for the new strategy and create
   test cases for edge conditions."
   ```

4. **Backtesting Phase**
   ```
   "Help me set up a backtesting framework to validate the strategy
   on historical data."
   ```

5. **Paper Trading Phase**
   ```
   "Configure the bot to run the new strategy in paper mode and
   set up monitoring."
   ```

6. **Live Deployment Phase**
   ```
   "Review the paper trading results and help me deploy to live
   with conservative position sizing."
   ```

### Risk Parameter Optimization

```
"I want to optimize risk parameters for my account:
- Account size: $25,000
- Risk tolerance: Moderate
- Max drawdown acceptable: 7%
- Target return: 15% annually

Suggest appropriate position sizing, stop losses, and position limits."
```

### Security Review Workflow

```
"I made changes to the order execution logic. Please:
1. Review for security vulnerabilities
2. Check for race conditions
3. Validate order size calculations
4. Ensure proper error handling
5. Suggest test cases for edge conditions"
```

## Troubleshooting

### Common Issues

**Issue**: Strategy not generating signals
```
"Debug why my mean reversion strategy isn't generating any signals.
Check the analyze() method and market data processing."
```

**Issue**: Orders being rejected
```
"My orders are being rejected by the Revolut API. Help me analyze
the API responses and validate order formatting."
```

**Issue**: Risk limits triggering unexpectedly
```
"The daily loss limit is triggering even though I'm profitable.
Debug the risk calculation logic."
```

**Issue**: Telegram notifications not working
```
"Telegram notifications aren't being sent. Validate my configuration
and test the notification system."
```

## Contributing to Agent Capabilities

The agent configuration can be extended. Common additions:

1. **New Strategy Templates**: Add strategy templates to `prompts/`
2. **Custom Indicators**: Document custom technical indicators
3. **Backtest Frameworks**: Add backtesting utilities
4. **Performance Metrics**: Add profit/loss analysis tools

## Security Notes

### What NOT to Share

- **Never** create `.env` files with credentials (use 1Password only)
- **Never** log private keys or API secrets
- **Never** share Telegram bot tokens publicly
- **Never** store keys in files (use 1Password exclusively)
- **Never** bypass 1Password requirement

### What's Safe to Share

- Strategy logic (without your specific parameters)
- Code structure and architecture
- Test cases and testing frameworks
- Configuration templates (without actual credentials)

### Security Architecture

- **All credentials in 1Password**: No local storage
- **Zero disk footprint**: Keys generated in temp, stored in vault, auto-deleted
- **1Password required**: No fallback to .env or local files
- **Audit trail**: All credential access logged in 1Password

## Support

For issues or questions:
1. Ask the Claude Code agent for help
2. Review the main README.md for project documentation
3. Check CHANGELOG.md for recent changes
4. Review Revolut API documentation: https://developer.revolut.com

## Version History

- **v1.0.0** - Initial agent configuration
  - Strategy development support
  - Risk management validation
  - Security auditing
  - Testing and deployment assistance
