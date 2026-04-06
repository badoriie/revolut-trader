---
applyTo: "src/api/**,src/execution/**,src/risk_management/**,src/utils/**"
---
# Security Audit Guide

## Quick Check

Review recent changes for: credential exposure, order validation gaps, race conditions in execution, missing input validation, and improper error handling in financial operations.

## Comprehensive Audit

Audit across these areas and report issues by severity (critical / high / medium / low):

**API Security** — Ed25519 auth, request signing, nonce handling, key management (never logged), rate limiting, HTTPS.

**Order Execution** — Size limits, duplicate prevention, price validation, partial fill handling, retry safety.

**Risk Controls** — Position size enforcement, stop-loss integrity, daily loss limits, max positions, bypass prevention.

**Credentials** — All secrets in 1Password only. No credentials in code, logs, errors, tests, or local files.

**Data Validation** — API response validation, numeric overflow/underflow, market data sanity checks, injection prevention.

**Async Safety** — Proper await usage, task cancellation handling, shared state access, lock/semaphore correctness.

## Pre-Deployment Checklist

- [ ] 1Password credentials valid and tested (`revt ops --status`, `revt api ready`)
- [ ] No credentials in code or logs
- [ ] All financial calculations use `Decimal`, not `float`
- [ ] Order size limits enforced (MIN_ORDER_VALUE, MAX_ORDER_VALUE)
- [ ] Stop losses and risk limits tested and cannot be bypassed
- [ ] Error handling comprehensive in critical paths
- [ ] API auth tested, rate limits respected, timeouts handled
- [ ] All tests pass (`just check`)
- [ ] Paper mode validated, emergency shutdown tested

## Component Reviews

**API Client** (`src/api/client.py`) — Ed25519 key handling, signature generation, nonce/timestamp, request signing, response validation, key never logged.

**Order Executor** (`src/execution/executor.py`) — Order size min/max, price validation, duplicate detection, position limit enforcement, partial fill handling, Decimal precision, negative value handling.

**Risk Manager** (`src/risk_management/risk_manager.py`) — Position sizing calculations, stop-loss trigger logic, daily loss limit enforcement, fail-safe defaults, emergency shutdown, error propagation.
