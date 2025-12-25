# Security Audit Template

Use these templates when requesting security reviews of the trading bot.

## Quick Security Check

```
Perform a quick security check on recent changes:

Files changed:
- [List modified files]

Check for:
1. API credential exposure or logging
2. Order validation and size limits
3. Proper error handling in financial operations
4. Race conditions in order execution
5. Input validation

Highlight any security concerns.
```

## Comprehensive Security Audit

```
Perform a comprehensive security audit of the trading bot:

**API Security**
- Verify Ed25519 authentication implementation
- Check request signing and nonce handling
- Validate API key management (no hardcoding, no logging)
- Review rate limiting and retry logic
- Check for proper HTTPS usage

**Order Execution Security**
- Validate order size calculations and limits
- Check for duplicate order prevention
- Verify price validation before order submission
- Review timeout and error handling
- Check for race conditions in position management

**Risk Controls**
- Verify position size limits are enforced
- Check stop loss implementation
- Validate daily loss limits
- Review maximum position constraints
- Ensure risk limits cannot be bypassed

**Credential Management**
- Verify .env file is in .gitignore
- Check no credentials in logs
- Validate private key file permissions
- Review environment variable usage
- Check for any hardcoded secrets

**Data Validation**
- Verify all API responses are validated
- Check numerical calculations for overflow/underflow
- Validate market data before use
- Review error handling and fallbacks
- Check for injection vulnerabilities

**Code Quality & Safety**
- Review exception handling in critical sections
- Check for proper async/await usage
- Validate thread safety (if applicable)
- Review logging practices (no sensitive data)
- Check for proper cleanup in error cases

Provide:
1. Critical issues (fix immediately)
2. High priority issues (fix before live deployment)
3. Medium priority issues (fix soon)
4. Recommendations for improvement
```

## Pre-Deployment Security Checklist

```
I'm preparing to deploy to live trading. Validate security:

**Environment**
- [ ] .env file configured correctly
- [ ] No credentials in code or logs
- [ ] Private keys secured and not in git
- [ ] API keys valid and tested
- [ ] File permissions set correctly

**Code Review**
- [ ] All financial calculations validated
- [ ] Order size limits enforced
- [ ] Stop losses implemented correctly
- [ ] Risk limits cannot be bypassed
- [ ] Error handling comprehensive

**API Integration**
- [ ] Authentication tested and working
- [ ] Request signing validated
- [ ] Rate limits respected
- [ ] Timeout handling implemented
- [ ] API errors handled gracefully

**Risk Management**
- [ ] Position limits configured appropriately
- [ ] Stop loss tested in paper mode
- [ ] Daily loss limit tested
- [ ] Maximum positions enforced
- [ ] Risk calculations verified

**Testing**
- [ ] All tests pass
- [ ] Security tests added
- [ ] Edge cases tested
- [ ] Paper mode validated
- [ ] Emergency shutdown tested

Review and confirm each item is satisfied.
```

## API Client Security Review

```
Review the API client security in src/api/client.py:

**Ed25519 Authentication**
- Verify private key loading and handling
- Check signature generation
- Validate nonce implementation
- Review timestamp handling

**Request Security**
- Check request signing process
- Validate header construction
- Review payload serialization
- Check for request tampering prevention

**Response Validation**
- Verify response authentication
- Check data integrity validation
- Review error response handling
- Validate unexpected response handling

**Key Management**
- Check private key never logged
- Verify secure key storage
- Review key file permissions
- Check for key exposure in errors

Highlight any vulnerabilities or improvements.
```

## Order Execution Security Review

```
Review order execution security in src/execution/executor.py:

**Order Validation**
- Check order size limits (min/max)
- Verify price validation
- Check quantity calculations
- Validate symbol/pair format
- Review order type validation

**Duplicate Prevention**
- Check for duplicate order detection
- Verify order ID uniqueness
- Review order state management
- Check for race conditions

**Position Management**
- Verify position limit enforcement
- Check position update atomicity
- Review position calculation accuracy
- Validate exposure calculations

**Error Handling**
- Check failed order handling
- Verify partial fill handling
- Review timeout handling
- Check retry logic safety

**Financial Safety**
- Verify calculations use proper decimal precision
- Check for arithmetic overflow/underflow
- Review rounding behavior
- Validate negative value handling

Report any critical issues that could cause financial loss.
```

## Risk Manager Security Review

```
Review risk management security in src/risk_management/risk_manager.py:

**Position Sizing**
- Verify position size calculations
- Check for calculation errors
- Review edge case handling (zero balance, etc.)
- Validate maximum position enforcement

**Stop Loss Implementation**
- Check stop loss trigger logic
- Verify stop loss cannot be bypassed
- Review stop loss calculation accuracy
- Check for stop loss order execution

**Portfolio Limits**
- Verify daily loss limit enforcement
- Check maximum position limits
- Review total exposure calculations
- Validate limit bypass prevention

**Risk Calculations**
- Check for mathematical errors
- Verify decimal precision
- Review percentage calculations
- Validate risk/reward calculations

**Safety Mechanisms**
- Check for fail-safe defaults
- Verify emergency shutdown capability
- Review graceful degradation
- Check for proper error propagation

Identify any gaps in risk controls.
```

## Credential Exposure Check

```
Scan the codebase for potential credential exposure:

Check:
1. No API keys in code files
2. No private keys in code files
3. .env file in .gitignore
4. No credentials in logs
5. No credentials in error messages
6. No credentials in test files
7. Secure handling of environment variables

Files to check:
- src/**/*.py
- tests/**/*.py
- config.py
- .env.example (should have placeholders only)
- README.md and docs (no real credentials)

Report any credential exposure immediately.
```

## Race Condition Analysis

```
Analyze the codebase for potential race conditions:

**Critical Sections**
- Order execution and position updates
- Risk limit checking and order submission
- Portfolio balance updates
- Position opening/closing

**Areas to Review**
- Concurrent order execution
- Shared state access (positions, balance)
- API request/response handling
- Signal generation and execution timing

**Async/Await Patterns**
- Verify proper use of async/await
- Check for missing await keywords
- Review concurrent task management
- Validate lock/semaphore usage

Identify any race conditions that could cause:
- Duplicate orders
- Incorrect position sizes
- Risk limit violations
- Balance calculation errors
```

## Input Validation Review

```
Review input validation across the codebase:

**API Responses**
- Validate all fields before use
- Check for missing or null values
- Verify data types
- Review range checking

**Configuration**
- Validate .env values
- Check risk parameters
- Verify trading pairs format
- Review all user inputs

**Market Data**
- Validate price data
- Check volume data
- Verify timestamp handling
- Review order book data

**Order Parameters**
- Validate quantities
- Check prices
- Verify symbols
- Review order types

Report any missing or insufficient validation.
```

## Logging Security Review

```
Review logging practices for security issues:

**Check for Sensitive Data**
- API keys or tokens
- Private keys
- Passwords or secrets
- Full API responses with sensitive data
- User credentials

**Verify Proper Logging**
- Errors logged appropriately
- No over-logging of sensitive operations
- Log rotation configured
- Log retention appropriate
- Logs secured with proper permissions

**Review Log Levels**
- DEBUG: Safe for development, not production
- INFO: No sensitive data
- WARNING: Appropriate for issues
- ERROR: Includes sufficient context

Files to review:
- src/**/*.py (all logging statements)
- config.py (logging configuration)

Report any sensitive data in logs.
```
