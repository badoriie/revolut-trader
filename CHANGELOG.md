# Changelog

## [0.1.0] - 2025-12-25

### Initial Release

#### Core Features
- 4 trading strategies: Market Making, Momentum, Mean Reversion, Multi-Strategy
- 3 configurable risk levels: Conservative, Moderate, Aggressive
- Paper trading mode for safe testing
- Live trading mode with Revolut X API
- Ed25519 signature-based API authentication
- Comprehensive risk management system
- Telegram notifications and alerts
- Real-time position monitoring

#### Technical Stack
- Python 3.11+ support
- Async/await architecture
- Type hints with Pydantic models
- Secure credential management
- Comprehensive logging with Loguru

#### Security
- Environment-based configuration
- Secure API key storage
- .gitignore for sensitive files
- No hardcoded credentials

### Cleaned Up
- Removed unused dependencies (pandas, numpy, fastapi, etc.)
- Removed unimplemented features (database, dashboard, backtesting modules)
- Streamlined configuration
- Removed empty directories
- Added basic test suite
