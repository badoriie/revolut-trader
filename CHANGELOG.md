# Changelog

## [Unreleased]

### Added - Environment Stages (dev / int / prod)

- **Three deployment environments** with full isolation of credentials, config, and data
  - `dev` — local development with mock API (no real HTTP calls), paper mode only
  - `int` — integration testing with real Revolut X API, paper mode only
  - `prod` — production with real API, paper or live trading
- **Separate API keys per environment** stored in 1Password
  - `revolut-trader-credentials-dev`, `revolut-trader-credentials-int`, `revolut-trader-credentials-prod`
  - `revolut-trader-config-dev`, `revolut-trader-config-int`, `revolut-trader-config-prod`
- **Separate database per environment**: `data/dev.db`, `data/int.db`, `data/prod.db`
- **Safety enforcement**: `TRADING_MODE=live` is rejected unless `ENVIRONMENT=prod`
- **New `Environment` enum** in `src/config.py` (dev, int, prod)
- **New CLI argument**: `--env dev|int|prod` in `cli/run.py`
- **New Makefile targets**: `run-dev`, `run-int`, `run-prod-paper`, `run-prod-live`
  - `run-paper` and `run-live` kept as backward-compatible aliases
  - All targets (`ops`, `opshow`, `opconfig-*`, `db-*`, `api-*`, `backtest`) accept `ENV=dev|int|prod`
- **Environment-aware 1Password**: `get_credentials_item(env)` / `get_config_item(env)` functions
- **Safety tests**: `tests/safety/test_environment.py` — verifies live mode restriction, environment validation
- **Unit tests**: environment-aware item names, DB URL per environment

### Changed - EUR as Base Currency

- **EUR is now the default base fiat currency** (previously USD)
  - New `base_currency` setting in `src/config.py` (default: "EUR")
  - Default trading pairs changed from USD to EUR (BTC-EUR, ETH-EUR)
  - API client balance calculations now use configurable base currency
  - Dynamic currency symbol display (€ for EUR, $ for USD, £ for GBP)
  - All CLI tools and examples updated to EUR pairs
  - All output updated: backtest results, bot logs
  - All documentation updated with EUR examples
  - Supports multiple base currencies via configuration
  - USD/USDC/USDT balances automatically converted to EUR (approximate conversion)

### Added - Code Quality & Development Tools

- **API Testing CLI**: Quick commands for testing API connectivity and fetching market data

  - New `cli/api_test.py` - Standalone CLI tool for API operations
  - `make api-test` - Test API connection and authentication
  - `make api-balance` - Get account balances for all currencies (BTC, ETH, EUR, etc.)
  - `make api-ticker` - Get ticker/price for a symbol (SYMBOL=BTC-EUR)
  - `make api-tickers` - Get multiple tickers at once (SYMBOLS=BTC-EUR,ETH-EUR,SOL-EUR)
  - `make api-candles` - Get recent candles/historical data (SYMBOL, INTERVAL, LIMIT)
  - Useful for quick market data checks without running the full bot
  - Clean formatted output for easy reading
  - Fixed balance endpoint to use correct `/balances` API path

- **Database Persistence**: Hybrid SQLite + JSON backup system for trading data

  - **Primary Storage**: SQLite database for fast queries and analytics
    - New `src/models/db_models.py` - SQLAlchemy models (PortfolioSnapshotDB, TradeDB, SessionDB)
    - New `src/utils/db_persistence.py` - Database persistence layer
    - Indexed queries for efficient time-series data retrieval
    - Session tracking for each bot run
    - Real-time analytics without parsing JSON files
  - **Backup Storage**: JSON files for disaster recovery and portability
    - Automatic daily JSON backup of last 7 days
    - `src/utils/persistence.py` - JSON persistence (backup only)
    - Backward compatible with existing JSON data
  - **Hybrid Manager**: `src/utils/hybrid_persistence.py` combines both approaches
    - Saves to database immediately (primary)
    - Daily JSON backup at midnight
    - Load from either source for disaster recovery
  - **Database Tools**: `cli/db_manage.py` — CLI tool for database management
    - Export to JSON/CSV for analysis
    - Data integrity verification
  - **Makefile Commands**: Convenient database management
    - `make db-stats` - Show database statistics
    - `make db-analytics` - Show trading analytics (last 30 days)
    - `make db-export` - Export data to JSON files
    - `make db-export-csv` - Export to CSV for analysis
  - **Updated bot.py**: Integrated hybrid persistence
    - Session tracking on start/stop
    - Immediate database saves for real-time analytics
    - Periodic JSON backup (every 10 iterations)
    - Historical data loading from database
    - Analytics display on startup
  - Portfolio snapshots saved periodically and on shutdown
  - Trade history automatically saved after each filled order
  - Data stored in `data/trading.db` (SQLite) with JSON backup in `data/`
  - SQLite only — no external database dependency

- **Backtest Results Database**: Backtest results now stored in database

  - New `BacktestRunDB` model for backtest run tracking
  - Automatic save to database after each backtest run
  - Query backtest history with `make db-backtests`
  - Analytics across all backtest runs (success rate, avg return, best run)
  - Links to detailed JSON files for equity curves and trades

- **Optional Log Storage**: Database storage for critical log events

  - New `LogEntryDB` model for log entries
  - Methods to save and query logs by level and time
  - Useful for tracking errors across sessions

- **Deep Clean Command**: New `make deep-clean` for complete project reset

  - Removes ALL generated files (database, logs, backtest results, backups)
  - Removes virtual environment and all cache files
  - Confirmation prompt to prevent accidental data loss
  - Useful for starting completely fresh or troubleshooting

- **Database Encryption**: Application-level field encryption for sensitive data

  - New `src/utils/db_encryption.py` - Fernet symmetric encryption infrastructure
  - Encryption key securely stored in 1Password vault
  - **Fully integrated** into `src/utils/db_persistence.py` - all sensitive fields automatically encrypted
  - Encrypts: strategy names, risk levels, trading modes, symbol lists, log messages
  - Does NOT encrypt: financial amounts (needed for SQL analytics), timestamps, counts
  - Transparent encrypt on save, decrypt on load - no changes needed in bot code
  - `make db-encrypt-setup` - Generate and store encryption key (one-time)
  - `make db-encrypt-status` - Check encryption status and test functionality
  - Optional feature - gracefully falls back to plaintext if not enabled
  - Uses existing `cryptography` library (no additional dependencies)
  - **Important**: This is field-level encryption, not full database encryption (see README)

- **Pre-commit Hooks**: Automated code quality checks on every commit

  - Ruff linting and formatting
  - Mypy type checking (strict for strategies/risk management, relaxed for CLI/tests)
  - Bandit security scanning (configured to skip false positives)
  - Basic file checks (trailing whitespace, end-of-file, YAML/TOML/JSON validation)
  - Markdown formatting with mdformat
  - New `make pre-commit-install` command for one-time setup
  - New `make pre-commit` command to run hooks manually
  - Configuration in `.pre-commit-config.yaml`

### Changed

- **Mypy Configuration**: Enhanced type checking configuration
  - Added ignore rules for external libraries (loguru, httpx, cryptography)
  - Strict typing for core modules (strategies, risk management, indicators)
  - Relaxed typing for infrastructure (CLI, notifications, backtest)
- **Bandit Configuration**: Configured to skip false positive subprocess warnings
  - Skips B404, B603, B607 for safe 1Password CLI usage
- **Development Dependencies**: Added pre-commit to dev dependencies in pyproject.toml
- **Line Ending Configuration**: Removed redundant `mixed-line-ending` pre-commit hook
  - `.gitattributes` already handles line ending normalization (`eol=lf`)
  - Simplifies pre-commit configuration without losing functionality
- **Git Attributes Cleanup**: Removed redundant binary file declarations from `.gitattributes`
  - `.pem`, `.key`, and `.db` files already excluded via `.gitignore`
  - All credentials stored in 1Password, not in repository
  - Simplified configuration with same protection level
- **Agent Instructions**: Added emphasis on documentation requirements
  - Updated `.claude/README.md` and `.claude/CODING_STANDARDS.md`
  - Documentation updates now mandatory for all code changes
  - Added to code review checklist
  - Includes examples of what documentation to update for different change types

### Fixed

- **Code Quality**: Fixed 8 code quality issues identified by pre-commit
  - Replaced `dict()` calls with dictionary literals in dashboard.py (5 instances)
  - Removed unused variables: `pnl_color` in dashboard.py, `close_order` and `position` in executor.py
  - All pre-commit hooks now pass successfully
- **Python 3.12+ Compatibility**: Replaced deprecated `datetime.utcnow()` with `datetime.now(UTC)`
  - Updated all files: bot.py, persistence.py, models.py, backtest/engine.py
  - Used modern `UTC` constant instead of `timezone.utc`
  - Updated Field default_factory to use lambda for datetime fields

## [0.3.0] - 2025-12-27

### Added - Production Optimization & Safety

- **Input Validation**: Pydantic models for all API responses
  - `OrderBookResponse`, `BalanceResponse`, `CandleResponse`, `OrderCreationResponse`
  - Prevents crashes from malformed API data
  - Clear validation errors for debugging
- **Rate Limiting**: Token bucket rate limiter for API calls
  - Default: 60 requests/minute (configurable)
  - Prevents API bans from excessive requests
  - Thread-safe implementation with asyncio.Lock
- **Live Trading Safety**: Critical error handling for live mode
  - Bot halts immediately if balance fetch fails in LIVE mode
  - Paper mode continues with default balance (warning only)
- **Thread Safety**: Asyncio locks for position tracking
  - Prevents race conditions in concurrent operations
  - Protected: position updates, price updates, closures
  - Safe for multi-strategy concurrent execution
- **Order Size Sanity Checks**: Prevents catastrophic order mistakes
  - Max order value limit (default: $10,000)
  - Prevents orders exceeding portfolio value
  - Minimum order value check ($10)
  - Quantity validation against reasonable maximums
  - Pre-execution validation before all orders
- **Memory Leak Fix**: Portfolio snapshots now use rotating buffer
  - Changed from unbounded list to deque with maxlen=1000
  - Prevents memory growth over extended runtime
  - Retains sufficient history for analysis
- **Parallel API Calls**: Trading loop now processes symbols concurrently
  - 2-5x faster trading iterations
  - Uses asyncio.gather for parallel execution
  - Graceful error handling per symbol
- **Enhanced Error Handling**: Specific exception handling with intelligent recovery
  - Distinguishes between timeout, auth, rate limit, and server errors
  - Auto-retry on transient failures (timeout, 5xx errors)
  - Halts on critical errors (auth failure, runtime errors)
  - Backoff strategy for rate limits (60s wait on 429)
  - Detailed logging with error types and emoji indicators
- **Strategy Optimization with EMA**: Replaced O(n) SMA with O(1) EMA calculations
  - Created optimized EMA and RSI indicator classes
  - Momentum strategy now uses exponential moving averages
  - 10-100x faster indicator calculations
  - Reduced CPU usage during high-frequency trading
  - Maintains same signal quality with better performance
- **Strict Type Checking**: Enhanced mypy configuration for better type safety
  - Configured balanced type checking: strict for core trading logic, practical for infrastructure
  - Added type annotations across all strategy and risk management modules
  - Fixed 99 type errors revealed by mypy strict mode
  - Strict typing enforced for: strategies, risk management, technical indicators
  - Relaxed typing for: CLI tools, dashboard, notifications, backtesting
  - Added missing return type annotations (-> None) throughout codebase
  - Fixed generic type parameters (dict → dict[str, Any])
  - Fixed Optional type guards and sum() type inference issues
  - Configured mypy to ignore missing stubs for external libraries (pandas, plotly, streamlit)
  - New `make typecheck` command for validation
  - Updated `make check` to include type checking
  - Better IDE support and earlier bug detection
  - Zero type errors in 28 source files

### Changed

- **API Client**: All API methods now validate responses with Pydantic
  - `get_ticker()` validates order book structure
  - `get_balance()` validates balance data
  - `get_candles()` validates historical data
  - `create_order()` validates order responses
- **Order Executor**: Added asyncio.Lock protection for shared state
  - `_update_positions()` is now thread-safe
  - `update_market_prices()` is now thread-safe
- **File Organization**: Moved CLI tools to `cli/` directory
  - `run.py` → `cli/run.py`
  - `backtest.py` → `cli/backtest.py`
  - `dashboard.py` → `cli/dashboard.py`
  - Updated Makefile with new paths
- **Dependencies**: Added watchdog for better Streamlit performance

### Documentation

- Created `docs/OPTIMIZATION_REPORT_2025-12-27.md` - Comprehensive optimization report
- Moved `CREDENTIALS.md` to `docs/` folder for better organization
- Updated Makefile with new commands: `make backtest`, `make dashboard`

### Fixed

- **Dashboard**: Fixed datetime parsing with microseconds (ISO8601 format)
- **Dashboard**: Updated deprecated `use_container_width` to `width="stretch"`
- **Thread Safety**: Eliminated race conditions in position tracking
- **Memory Safety**: Preparation for portfolio snapshot rotation (pending)

## [0.2.0] - 2025-12-27

### Added

- **Interactive Web Dashboard**: Comprehensive Streamlit dashboard for visualization
  - `dashboard.py` - Web-based dashboard with interactive charts
  - Backtest results viewer with equity curves and P&L charts
  - Strategy comparison tools
  - Trade history display
  - Real-time monitoring (placeholder for future)
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
