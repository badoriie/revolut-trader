# Revolut Trader Agents

This document describes all available specialized agents for the Revolut Trader project. These agents are designed to help with specific tasks related to development, testing, documentation, and analysis.

## Essential Project Context

Before using any agent, familiarize yourself with these key documents:

- **`CLAUDE.md`** — Core development rules, commands, architecture overview
- **`docs/revolut-x-api-docs.md`** — API reference (source of truth for all API code)
- **`docs/ARCHITECTURE.md`** — Component hierarchy, data flows, shutdown sequence
- **`docs/DEVELOPMENT_GUIDELINES.md`** — TDD workflow, coding standards, contribution rules

### Critical Rules (enforced across all agents)

1. **Financial Calculations** — Always `Decimal("100.5")`, never `float`. ORM uses `Numeric(20, 10)`.
2. **Environment Parity** — Identical code paths across dev/int/prod. Only data source differs. Never `if environment == "dev"`.
3. **API Docs Are Law** — `docs/revolut-x-api-docs.md` is the source of truth. Hierarchy: API docs → tests → code.
4. **TDD** — Check API docs → write failing test → minimal code to pass → refactor.
5. **Configuration** — All user values in 1Password. No code defaults except `ENVIRONMENT` from env var.
6. **Security** — DB encryption always on. No secrets in code, logs, tests, or errors. Export only via `revt db export`.

## Available Agents

### 1. Audit Docs

**Name:** `audit-docs`

**Description:** Documentation audit agent. Explores codebase, finds inaccuracies in README.md, CLAUDE.md, and docs/, then fixes them. Use when docs may be stale or out of sync with code.

**Tools:** Read, Glob, Grep, Bash, Write, Edit

**Capabilities:**
- Verify project structure against documentation
- Review README.md for accuracy (badges, commands, features, links)
- Review `CLAUDE.md` for accuracy (commands, architecture, key files, rules)
- Review `.github/copilot-instructions.md` (synced from CLAUDE.md)
- Review all docs/ files for validity and accuracy
- Review GitHub workflows for deprecated actions and correct configuration
- Automatically fix inaccuracies and outdated information

**When to Use:**
- After major codebase changes
- Before releases
- When documentation seems outdated
- During periodic maintenance reviews

---

### 2. Backtest Analyst

**Name:** `backtest-analyst`

**Description:** Analyzes backtest results, compares strategies, and recommends configuration. Use when evaluating strategy performance, interpreting backtest output, or tuning parameters.

**Model:** claude-haiku-4-5-20251001

**Tools:** Read, Glob, Grep, Bash

**Capabilities:**
- Run and interpret `revt backtest`, `revt backtest --compare`, `revt backtest --matrix`
- Read and analyze backtest results from database
- Evaluate performance metrics: return, Sharpe ratio, max drawdown, win rate, avg trade
- Compare strategies across risk levels and trading pairs
- Identify overfitting, data snooping bias, and cherry-picked results
- Recommend 1Password config changes to improve performance

**Analysis Framework:**
1. **Return** — absolute and annualized, compare against buy-and-hold
2. **Risk-adjusted** — Sharpe ratio > 1 acceptable, > 2 good
3. **Drawdown** — max drawdown should stay within STOP_LOSS_PCT bounds
4. **Win rate** — context-dependent per strategy
5. **Robustness** — performance across pairs, intervals, and time periods

**Key Context:**
- 6 strategies: `market_making`, `momentum`, `mean_reversion`, `breakout`, `range_reversion`, `multi_strategy`
- 3 risk levels: `conservative`, `moderate`, `aggressive`
- Candle intervals: 1, 5, 15, 30, 60, 240, 1440 minutes
- All strategies tunable via 1Password items

**When to Use:**
- Evaluating strategy performance
- Comparing strategies
- Tuning trading parameters
- Before enabling live trading

---

### 3. Code Improvement

**Name:** `code-improvement`

**Description:** Code quality and modernization review. Checks dependencies, reviews patterns, identifies security issues, produces a prioritized improvement backlog. Use for periodic quality reviews or before releases.

**Tools:** Read, Glob, Grep, Bash, WebFetch, WebSearch

**Capabilities:**
- Check for dependency updates and security vulnerabilities
- Review Python version and suggest modern features
- Analyze code quality and patterns
- Identify testing improvements
- Review CI/CD automation
- Find performance opportunities
- Audit security and safety practices
- Produce prioritized improvement backlog

**Review Areas:**
1. **Dependency Updates** — Check PyPI for latest versions, security vulnerabilities
2. **Python Version & Features** — Identify newer Python features to use
3. **Code Quality & Patterns** — Type hints, error handling, constants, complexity, docs
4. **Testing Improvements** — Coverage analysis, edge cases, weak tests
5. **CI/CD & Automation** — Outdated actions, missing checks, security best practices
6. **Performance Opportunities** — Database queries, async calls, caching
7. **Security & Safety** — Hardcoded secrets, Decimal usage, error message leakage

**When to Use:**
- Before major releases
- Periodic quality reviews
- After adding major features
- When planning refactoring work

---

### 4. Security Reviewer

**Name:** `security-reviewer`

**Description:** Security review for financial trading code. Reviews API auth, order execution, risk controls, credential handling, and encryption. Use when reviewing security-sensitive changes.

**Tools:** Read, Glob, Grep, Bash

**Focus Areas:**

**Authentication & Signing** (`src/api/client.py`)
- Ed25519 key generation, storage, and usage
- Request signature construction
- Keys must never appear in logs, errors, or test output

**Order Execution Safety** (`src/execution/executor.py`)
- MIN_ORDER_VALUE / MAX_ORDER_VALUE bounds enforcement
- No duplicate order submission (idempotency via `client_order_id`)
- All monetary values use `Decimal`, never `float`
- Partial fill handling correctness

**Risk Controls** (`src/risk_management/risk_manager.py`)
- Position size limits cannot be bypassed
- Daily loss limits enforced before every order
- Stop-loss triggers are reliable under all market conditions
- Emergency shutdown closes all positions cleanly

**Credential & Secret Management**
- All secrets in 1Password only
- No secrets in: source code, logs, test fixtures, error messages, or `revt-data/`
- Secrets properly masked in output

**Data & Encryption**
- SQLite DBs use Fernet encryption
- Sensitive fields encrypted at rest
- Export path is the only safe CSV output

**Severity Levels:**
- **Critical** — live money at risk, credentials exposed, bypass of risk controls
- **High** — data integrity issues, incomplete position tracking, auth weaknesses
- **Medium** — missing validation, error message leakage, incomplete test coverage
- **Low** — code quality, logging improvements, defensive checks

**When to Use:**
- Before deploying to production
- When modifying authentication code
- When changing order execution logic
- When updating risk management
- During security audits

---

### 5. Strategy Review

**Name:** `strategy-review`

**Description:** Trading strategy analysis. Reviews strategy code, runs backtests, compares performance, and recommends configuration. Use when evaluating a strategy or tuning parameters.

**Tools:** Read, Glob, Grep, Bash

**Basic Review:**
- Signal generation logic — entry/exit clearly defined?
- Risk parameter adherence — respects limits and stop losses?
- Edge case handling — zero volume, extreme prices, API errors?
- BaseStrategy integration — correct interface, no missing overrides?

**Comprehensive Analysis:**
- **Signal Logic** — Entry/exit clarity, volatility handling, contradictions
- **Risk Management** — Position size limits, stop losses, max position limits
- **Performance** — Bottlenecks, overtrading tendencies, market condition adaptability
- **Testing** — Identify tests to add, untested edge cases

**Backtest Workflow:**
1. Run `revt backtest --strategy {name}` for single strategy
2. Run `revt backtest --compare` for side-by-side comparison
3. Run `revt backtest --matrix` for all strategies × all risk levels
4. View saved results: `revt db backtests`

**Evaluation Criteria:**
- Return percentage
- Sharpe ratio (> 1 acceptable, > 2 good)
- Max drawdown
- Win rate
- Average trade size
- Sample size and pair diversity

**New Strategy Design:**
When designing a new strategy, provide:
- Concept and target market conditions
- Entry/exit criteria
- Risk parameters (position size, SL, TP)
- `BaseStrategy` implementation outline
- Test cases

**When to Use:**
- Developing new strategies
- Tuning existing strategies
- Comparing strategy performance
- Optimizing multi-strategy configuration

---

### 6. Testing Debug

**Name:** `testing-debug`

**Description:** Testing and debugging specialist. Writes unit tests, traces bugs to root cause, reviews async safety, and analyzes coverage gaps. Use when adding tests, diagnosing issues, or fixing failing tests.

**Tools:** Read, Glob, Grep, Bash, Write, Edit

**Write Unit Tests:**
- Target any component in `src/`
- Cover: happy path, edge cases, error conditions, boundary values, invalid inputs
- Mock: API calls, market data, time, and random values
- Use pytest + pytest-asyncio
- All monetary values must use `Decimal`

**Debug Trading Issue:**
Gather:
- Problem description
- Frequency and conditions
- Relevant logs
- Steps to reproduce
- Expected vs actual behavior
- Financial impact

Analyze:
- Root cause in code
- Immediate fix
- Long-term solution
- Prevention via tests

**Debug by Component:**
- **API issues** — check auth headers, signature construction, rate limits
- **Position management** — compare bot state vs Revolut, check sync logic
- **Risk limits** — verify config values, trace through risk_manager.py
- **Signal generation** — check strategy parameters, market data, thresholds

**Testing Checklists:**

**Integration:**
- API client + API
- Strategy + market data
- Risk manager + executor
- Full trading loop

**Error Handling:**
- All exceptions caught
- Proper propagation
- Graceful degradation
- Error logging with context

**Race Conditions:**
- Concurrent order execution
- Position updates
- Balance calculations
- Identify shared state

**Async Safety:**
- Missing awaits
- Blocking calls in async functions
- Task cancellation
- Resource leaks

**Coverage Analysis:**
- Run `just test`
- Target ≥ 97% coverage
- Review `tests/safety/` — encode invariants that must never break (e.g., `test_order_limits.py`, `test_risk_config.py`, `test_graceful_shutdown.py`)
- Review `tests/unit/test_calculations.py` — financial math must be exact
- Identify uncovered critical paths
- Add tests before merging

**When to Use:**
- Writing new tests
- Debugging production issues
- Fixing failing tests
- Improving test coverage
- Investigating race conditions
- Reviewing async code safety

---

## How to Use Agents

Agents are specialized assistants designed for specific tasks. To use an agent effectively:

1. **Choose the right agent** based on your task
2. **Provide clear context** about what you need
3. **Let the agent work autonomously** — they have the tools and knowledge to complete the task
4. **Review the results** and provide feedback if needed

### Example Usage

```bash
# Use audit-docs agent to review documentation
"Use the audit-docs agent to review and update all documentation"

# Use backtest-analyst to evaluate strategies
"Use the backtest-analyst agent to compare all strategies and recommend the best configuration"

# Use security-reviewer before production deployment
"Use the security-reviewer agent to audit the order execution and risk management code"

# Use testing-debug to fix a failing test
"Use the testing-debug agent to debug why test_momentum_strategy is failing"
```

## Agent File Locations

All agent configurations are stored in `.claude/agents/`:

- `.claude/agents/audit-docs.md`
- `.claude/agents/backtest-analyst.md`
- `.claude/agents/code-improvement.md`
- `.claude/agents/security-reviewer.md`
- `.claude/agents/strategy-review.md`
- `.claude/agents/testing-debug.md`

## Key Documentation Files

- **`CLAUDE.md`** — Core development rules, architecture, commands (root directory)
- **`.github/copilot-instructions.md`** — GitHub Copilot instructions (synced from CLAUDE.md)
- **`AGENTS.md`** — This file: agent descriptions and usage
- **`README.md`** — Main project documentation
- **`docs/`** — Detailed guides and API reference

## Contributing

When adding new agents:

1. Create a new `.md` file in `.claude/agents/`
2. Follow the frontmatter format (name, description, tools, model)
3. Clearly define capabilities and when to use the agent
4. Update this AGENTS.md file with the new agent details
5. Test the agent to ensure it works as expected
