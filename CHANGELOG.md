# Changelog

## [0.2.0] - 2025-12-27

### Added
- **Backtesting System**: Complete backtesting engine for strategy validation on historical data
  - `backtest.py` CLI tool for running backtests
  - `src/backtest/engine.py` - Backtesting engine with comprehensive metrics
  - Historical data fetching via `get_candles()` API method
  - Performance metrics: win rate, profit factor, max drawdown, Sharpe ratio
  - JSON export for results analysis
  - Support for multiple trading pairs and time periods
  - Configurable candle intervals (5m, 15m, 30m, 1h, 4h, 1d)

### Documentation
- Created `docs/BACKTESTING.md` - Complete backtesting guide
- Updated `README.md` with backtesting examples
- Added usage examples for all backtesting scenarios

## [0.1.1] - 2025-12-27

### Fixed
- **1Password CLI Integration**: Added `--reveal` flag to `get_field()` method in `src/utils/onepassword.py` to properly retrieve concealed fields from 1Password CLI v2
- **Paper Mode Real Data**: Modified paper trading mode to use real market data from Revolut X API instead of generating fake random prices
- **API Base URL**: Updated Revolut X API base URL from `https://api.revolut.com/api/1.0` to `https://revx.revolut.com/api/1.0`
- **Market Data Endpoint**: Implemented `/public/order-book/{symbol}` endpoint for fetching real-time bid/ask prices
- **API Client**: Fixed duplicate `/api/1.0` path construction in authenticated requests

### Changed
- Paper mode now fetches real market data while simulating order executions
- `get_ticker()` method now uses public order book endpoint and normalizes response format
- Both paper and live modes use identical market data source (only execution differs)

### Technical Details
- Paper mode provides realistic testing with actual market conditions
- Order book data includes bid, ask, and calculated mid-price
- Authentication required even for "public" endpoints on Revolut X API

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
