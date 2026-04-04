# Security Policy

## Supported Versions

We release patches for security vulnerabilities. The following versions are currently supported with security updates:

| Version | Supported          |
| ------- | ------------------ |
| 0.5.x   | :white_check_mark: |
| < 0.5.0 | :x:                |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

We take the security of Revolut Trader seriously. If you believe you have found a security vulnerability, please report it to us as described below.

### How to Report a Security Vulnerability

**Option 1: GitHub Security Advisories (Preferred)**

1. Go to the [Security Advisories](https://github.com/badoriie/revolut-trader/security/advisories) page
1. Click "Report a vulnerability"
1. Fill out the form with:
   - A description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if you have one)

**Option 2: Private Disclosure via Email**

If you prefer email, you can report vulnerabilities by creating a private issue and requesting contact information from a maintainer.

### What to Include in Your Report

Please include the following information to help us understand and resolve the issue quickly:

- **Type of issue** (e.g., buffer overflow, SQL injection, cross-site scripting, credential exposure, etc.)
- **Full paths of source file(s)** related to the manifestation of the issue
- **Location of the affected source code** (tag/branch/commit or direct URL)
- **Any special configuration** required to reproduce the issue
- **Step-by-step instructions** to reproduce the issue
- **Proof-of-concept or exploit code** (if possible)
- **Impact of the issue**, including how an attacker might exploit it

### Response Timeline

- **Initial Response**: We will acknowledge your report within 48 hours
- **Status Updates**: We will provide updates on the progress of fixing the issue at least every 7 days
- **Resolution**: We aim to resolve critical vulnerabilities within 30 days of acknowledgment

### What to Expect

After you submit a report, we will:

1. **Confirm receipt** of your vulnerability report
1. **Investigate** the issue and determine its impact
1. **Develop a fix** for the vulnerability
1. **Release a security update** following our release process
1. **Credit you** in the release notes (if you wish) after the issue is resolved

## Security Best Practices

When using Revolut Trader, we recommend:

### Credential Management

- **Never commit credentials** to version control
- **Use 1Password** or another secure vault for credential storage (required by this application)
- **Rotate API keys** regularly
- **Use separate API keys** for dev, integration, and production environments

### Environment Isolation

- **Keep environments separate**: Use dedicated API keys and vault items for `dev`, `int`, and `prod`
- **Test in paper mode first**: Always validate strategies in paper trading before enabling live mode
- **Production requires confirmation**: Live trading in production requires explicit confirmation

### Network Security

- **Use HTTPS only**: All API communication uses TLS/HTTPS
- **Protect your 1Password vault**: Use a strong master password and 2FA
- **Secure your server**: If running on a remote server, use SSH keys and firewall rules

### Operational Security

- **Monitor logs**: Check `make logs` regularly for warnings and errors
- **Enable Telegram notifications**: Get real-time alerts for trading activity
- **Review analytics**: Use `make db-analytics` and `make db-report` to monitor performance
- **Backup your database**: The encrypted database in `data/{env}.db` contains your trading history

### Code Security

- **Keep dependencies updated**: We use Dependabot to monitor for vulnerable dependencies
- **Review backtest results**: Test new strategies thoroughly before live trading
- **Respect rate limits**: The built-in rate limiter protects against API throttling
- **Validate configuration**: Required fields in 1Password fail fast with actionable error messages

## Security Features

This project implements several security features:

### Encryption at Rest

- **Database encryption**: All sensitive data (trades, balances, API responses) is encrypted using Fernet (symmetric encryption)
- **Encryption key storage**: Keys are stored securely in 1Password, auto-generated if missing
- **No plaintext logs**: Logs are stored encrypted in the database, not on disk

### Secure Credential Handling

- **1Password integration**: All credentials and configuration managed via 1Password CLI
- **No hardcoded secrets**: Configuration fails fast if required fields are missing from 1Password
- **Masked output**: Secrets are masked in `revt ops --show` with aggressive redaction
- **TTY detection**: Prevents accidental credential leakage via piping/redirection

### API Security

- **Ed25519 authentication**: Uses cryptographic signatures for Revolut X API authentication
- **Rate limiting**: Respects API rate limits to prevent throttling and account issues
- **Environment validation**: API keys are scoped per environment (dev/int/prod)

### Trading Safety

- **Paper mode by default**: All environments default to paper trading
- **Live mode restrictions**: Live trading only allowed in production environment
- **Confirmation required**: Live trading requires explicit `"I UNDERSTAND"` confirmation
- **Position limits**: Configurable max order value and position size limits
- **Risk management**: Built-in risk checks before every order execution
- **Pre-existing crypto protection**: Bot will never sell crypto it didn't buy

## Known Limitations

### Not a Security Tool

This application is **not** designed for:

- High-frequency trading (HFT) below 5-second intervals
- Guaranteed profit or risk-free trading
- Replacing professional financial advice

### Cryptocurrency Trading Risks

Trading cryptocurrency carries inherent risks:

- **Market volatility**: Crypto markets can be extremely volatile
- **API outages**: Revolut X API downtime can affect order execution
- **Strategy risk**: Backtested strategies may not perform in live markets
- **Liquidation risk**: Losses can exceed initial capital in leveraged positions (this bot does not use leverage)

### Third-Party Dependencies

This application relies on:

- **Revolut X API**: Availability and reliability of the Revolut trading platform
- **1Password CLI**: Secure credential storage and retrieval
- **Python ecosystem**: Security updates to cryptography, httpx, SQLAlchemy, and other dependencies

We use Dependabot and regular security scans to monitor dependencies.

## Disclosure Policy

When we receive a security bug report, we will:

1. **Confirm the vulnerability** and determine its severity
1. **Develop and test a fix** in a private development branch
1. **Prepare a security advisory** with CVE assignment (if applicable)
1. **Release a patched version** following our standard release process
1. **Publish the security advisory** with details, workarounds, and affected versions
1. **Notify users** via GitHub Release notes and (if opted in) Telegram notifications

We follow **responsible disclosure** principles and will credit security researchers who follow this policy.

## Compliance

### No Financial Advice

This software is provided as-is and does not constitute financial advice. Users are responsible for:

- Understanding the risks of cryptocurrency trading
- Complying with local regulations and tax laws
- Using appropriate risk management for their financial situation

### Open Source License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

______________________________________________________________________

**Last Updated**: April 2026
**Security Contact**: Use GitHub Security Advisories
**Project**: [Revolut Trader](https://github.com/badoriie/revolut-trader)
