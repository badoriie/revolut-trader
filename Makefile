.PHONY: help setup install clean deep-clean test lint format typecheck check run-paper run-live backtest dashboard logs ops opshow opstatus opdelete backup restore pre-commit-install pre-commit db db-stats db-analytics db-backtests db-export db-export-csv db-migrate db-encrypt-setup db-encrypt-status api-test api-balance api-ticker api-tickers api-candles

# Default target - show help
help:
	@echo "🤖 Revolut Trading Bot - Make Commands"
	@echo ""
	@echo "📦 Setup & Installation:"
	@echo "  make setup             - Complete project setup (uv + 1Password + dependencies)"
	@echo "  make install           - Install/update dependencies with uv"
	@echo "  make clean             - Remove cache files and artifacts"
	@echo "  make deep-clean        - ⚠️  Remove ALL generated files (data, logs, venv)"
	@echo ""
	@echo "🔐 Credentials (1Password):"
	@echo "  make ops               - Setup and store credentials in 1Password"
	@echo "  make opshow            - Show credentials (masked)"
	@echo "  make opstatus          - Check 1Password status"
	@echo "  make opdelete          - Delete credentials from 1Password"
	@echo ""
	@echo "🚀 Trading & Analysis:"
	@echo "  make run-paper         - Run in paper mode (safe, simulated trading)"
	@echo "  make run-live          - Run in live mode (⚠️  REAL MONEY!)"
	@echo "  make backtest          - Run strategy backtesting on historical data"
	@echo "  make dashboard         - Launch web dashboard for visualization"
	@echo ""
	@echo "🔌 API Testing:"
	@echo "  make api-test          - Test API connection"
	@echo "  make api-balance       - Get account balance"
	@echo "  make api-ticker        - Get ticker for symbol (SYMBOL=BTC-USD)"
	@echo "  make api-tickers       - Get multiple tickers (SYMBOLS=BTC-USD,ETH-USD,SOL-USD)"
	@echo "  make api-candles       - Get recent candles (SYMBOL=BTC-USD INTERVAL=60 LIMIT=10)"
	@echo ""
	@echo "✅ Code Quality:"
	@echo "  make pre-commit-install - Install pre-commit hooks"
	@echo "  make pre-commit        - Run pre-commit hooks manually on all files"
	@echo "  make test              - Run tests with coverage"
	@echo "  make lint              - Check code with ruff"
	@echo "  make format            - Format code with ruff"
	@echo "  make typecheck         - Run mypy type checking"
	@echo "  make check             - Run all quality checks (test + lint + typecheck)"
	@echo ""
	@echo "📋 Utilities:"
	@echo "  make logs              - View recent logs"
	@echo "  make backup            - Backup data and logs"
	@echo ""
	@echo "💾 Database Management:"
	@echo "  make db                - 📊 Show database overview (stats + analytics + backtests)"
	@echo "  make db-stats          - Show database statistics"
	@echo "  make db-analytics      - Show trading analytics (DAYS=30 to customize)"
	@echo "  make db-backtests      - Show backtest results (LIMIT=10 to customize)"
	@echo "  make db-export         - Export data to JSON (DIR=data/exports to customize)"
	@echo "  make db-export-csv     - Export data to CSV for analysis"
	@echo ""
	@echo "🔐 Database Encryption:"
	@echo "  make db-encrypt-setup  - Setup database encryption (1Password key storage)"
	@echo "  make db-encrypt-status - Check encryption status"
	@echo ""
	@echo "💡 Quick Start:"
	@echo "  1. make setup          (one-time setup)"
	@echo "  2. make ops            (add credentials)"
	@echo "  3. make run-paper      (test bot safely)"

# ============================================================================
# Setup & Installation
# ============================================================================

# Complete project setup
setup:
	@echo "🚀 Running complete project setup..."
	@bash scripts/setup.sh

# Install/update dependencies
install:
	@echo "📦 Installing dependencies with uv..."
	@uv sync --extra dev
	@echo "✅ Dependencies installed"

# Clean Python cache and build artifacts
clean:
	@echo "🧹 Cleaning cache files..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name ".coverage" -delete 2>/dev/null || true
	@find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ Clean complete"

# Deep clean - remove ALL generated files (data, logs, cache, venv)
deep-clean:
	@echo "🚨 WARNING: This will delete ALL generated files including:"
	@echo "  - Database (data/trading.db)"
	@echo "  - All logs (logs/)"
	@echo "  - Backtest results (results/)"
	@echo "  - Backups (backups/)"
	@echo "  - Data files (data/)"
	@echo "  - Virtual environment (.venv/)"
	@echo "  - All cache and build files"
	@echo ""
	@read -p "Type 'YES' to confirm deep clean: " confirm && [ "$$confirm" = "YES" ] || (echo "❌ Cancelled" && exit 1)
	@echo ""
	@echo "🧹 Performing deep clean..."
	@# Python cache and build artifacts
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name ".coverage" -delete 2>/dev/null || true
	@find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	@# Data and runtime files (completely remove directories)
	@rm -rf data 2>/dev/null || true
	@rm -rf logs 2>/dev/null || true
	@rm -rf results 2>/dev/null || true
	@rm -rf backups 2>/dev/null || true
	@# Virtual environment
	@rm -rf .venv 2>/dev/null || true
	@# uv cache
	@rm -rf .uv 2>/dev/null || true
	@echo ""
	@echo "✅ Deep clean complete - project is now in fresh state"
	@echo "ℹ️  Run 'make install' to reinstall dependencies"

# ============================================================================
# 1Password Credentials
# ============================================================================

ops:
	@bash scripts/1password-manager.sh setup

opshow:
	@bash scripts/1password-manager.sh show

opstatus:
	@bash scripts/1password-manager.sh status

opdelete:
	@bash scripts/1password-manager.sh delete

# ============================================================================
# Trading Bot
# ============================================================================

# Run in paper trading mode (safe)
run-paper:
	@echo "📊 Starting bot in PAPER mode (simulated trading)"
	@uv run python cli/run.py --mode paper --strategy market_making --risk conservative

# Run in live trading mode (real money!)
run-live:
	@echo ""
	@echo "⚠️  =================================================="
	@echo "⚠️  LIVE TRADING MODE - REAL MONEY AT RISK!"
	@echo "⚠️  =================================================="
	@echo ""
	@read -p "Type 'I UNDERSTAND' to continue: " confirm && [ "$$confirm" = "I UNDERSTAND" ] || (echo "Cancelled" && exit 1)
	@uv run python cli/run.py --mode live --strategy market_making --risk conservative

# Run backtesting
backtest:
	@echo "🔬 Running strategy backtesting..."
	@mkdir -p results
	@STRATEGY=$${STRATEGY:-market_making}; \
	DAYS=$${DAYS:-30}; \
	OUTPUT=./results/backtest_$$(date +%Y%m%d_%H%M%S).json; \
	echo "Strategy: $$STRATEGY | Days: $$DAYS"; \
	uv run python cli/backtest.py --strategy $$STRATEGY --days $$DAYS --output $$OUTPUT && \
	echo "✅ Backtest complete: $$OUTPUT" && \
	echo "📊 View results: make dashboard" || \
	echo "❌ Backtest failed - check logs above"

# Launch dashboard
dashboard:
	@echo "📊 Launching web dashboard..."
	@echo "Dashboard will open at http://localhost:8501"
	@uv run streamlit run cli/dashboard.py

# ============================================================================
# API Testing
# ============================================================================

# Test API connection
api-test:
	@echo "🔌 Testing API connection..."
	@uv run python cli/api_test.py test

# Get account balance
api-balance:
	@echo "💰 Getting account balance..."
	@uv run python cli/api_test.py balance

# Get ticker for a symbol
api-ticker:
	@SYMBOL=$${SYMBOL:-BTC-USD}; \
	echo "📊 Getting ticker for $$SYMBOL..."; \
	uv run python cli/api_test.py ticker --symbol $$SYMBOL

# Get multiple tickers
api-tickers:
	@SYMBOLS=$${SYMBOLS:-BTC-USD,ETH-USD,SOL-USD}; \
	echo "📊 Getting tickers for $$SYMBOLS..."; \
	uv run python cli/api_test.py tickers --symbols $$SYMBOLS

# Get recent candles
api-candles:
	@SYMBOL=$${SYMBOL:-BTC-USD}; \
	INTERVAL=$${INTERVAL:-60}; \
	LIMIT=$${LIMIT:-10}; \
	echo "📈 Getting $$LIMIT candles for $$SYMBOL ($$INTERVAL min)..."; \
	uv run python cli/api_test.py candles --symbol $$SYMBOL --interval $$INTERVAL --limit $$LIMIT

# ============================================================================
# Code Quality
# ============================================================================

# Install pre-commit hooks
pre-commit-install:
	@echo "🔧 Installing pre-commit hooks..."
	@echo "📦 Ensuring dev dependencies are installed..."
	@uv sync --extra dev --quiet
	@uv run pre-commit install
	@echo "✅ Pre-commit hooks installed"
	@echo "ℹ️  Hooks will now run automatically on git commit"
	@echo "ℹ️  To run manually: make pre-commit"

# Run pre-commit hooks manually on all files
pre-commit:
	@echo "🔍 Running pre-commit hooks on all files..."
	@uv run pre-commit run --all-files

# Run tests with coverage
test:
	@echo "🧪 Running tests with coverage..."
	@uv run pytest --cov=src --cov-report=term-missing --cov-report=html
	@echo "✅ Tests complete (see htmlcov/index.html for coverage report)"

# Lint code (check only)
lint:
	@echo "🔍 Checking code with ruff..."
	@uv run ruff check src/ tests/ cli/
	@echo "✅ Lint check complete"

# Format code (auto-fix)
format:
	@echo "🎨 Formatting code with ruff..."
	@uv run ruff format src/ tests/ cli/
	@uv run ruff check --fix src/ tests/ cli/
	@echo "✅ Code formatted"

# Type checking with mypy
typecheck:
	@echo "🔍 Running type checks with mypy..."
	@uv run mypy src/ cli/
	@echo "✅ Type checking complete"

# Run all quality checks
check: lint format typecheck test
	@echo ""
	@echo "✅ All quality checks passed!"

# ============================================================================
# Logs & Monitoring
# ============================================================================

# View recent logs
logs:
	@echo "📋 Recent logs:"
	@if [ -d "logs" ] && [ "$$(ls -A logs 2>/dev/null)" ]; then \
		tail -n 50 logs/$$(ls -t logs | head -1); \
	else \
		echo "No logs found. Run the bot first."; \
	fi

# Follow logs in real-time
logs-follow:
	@echo "📋 Following logs (Ctrl+C to stop)..."
	@if [ -d "logs" ] && [ "$$(ls -A logs 2>/dev/null)" ]; then \
		tail -f logs/$$(ls -t logs | head -1); \
	else \
		echo "No logs found. Run the bot first."; \
	fi

# ============================================================================
# Backup & Restore
# ============================================================================

# Backup data and logs
backup:
	@echo "💾 Creating backup..."
	@mkdir -p backups
	@BACKUP_NAME=backup_$$(date +%Y%m%d_%H%M%S); \
	mkdir -p backups/$$BACKUP_NAME; \
	[ -d "data" ] && cp -r data backups/$$BACKUP_NAME/ || true; \
	[ -d "logs" ] && cp -r logs backups/$$BACKUP_NAME/ || true; \
	echo "✅ Backup created: backups/$$BACKUP_NAME"
	@echo "ℹ️  Credentials are in 1Password (not backed up locally)"

# Restore from backup
restore:
	@echo "📥 Available backups:"
	@ls -1 backups/ 2>/dev/null || echo "No backups found"
	@echo ""
	@read -p "Enter backup name to restore: " backup && \
	if [ -d "backups/$$backup" ]; then \
		echo "Restoring from $$backup..."; \
		[ -d "backups/$$backup/data" ] && cp -r backups/$$backup/data . || true; \
		echo "✅ Restore complete"; \
	else \
		echo "❌ Backup not found"; \
	fi

# ============================================================================
# Database Management
# ============================================================================

# Define DB management command (DRY principle)
DB_CMD = @uv run python cli/db_manage.py

# Show comprehensive database overview
db:
	$(DB_CMD) stats
	@echo ""
	$(DB_CMD) analytics 7
	@echo ""
	$(DB_CMD) backtests 5

# Show database statistics
db-stats:
	$(DB_CMD) stats

# Show trading analytics (DAYS=30 to customize)
db-analytics:
	$(DB_CMD) analytics $${DAYS:-30}

# Show backtest results (LIMIT=10 to customize)
db-backtests:
	$(DB_CMD) backtests $${LIMIT:-10}

# Export data to JSON (DIR=data/exports to customize)
db-export:
	$(DB_CMD) export $${DIR:-data/exports}

# Export data to CSV
db-export-csv:
	$(DB_CMD) export-csv

# Migrate SQLite to PostgreSQL
db-migrate:
	@echo "🔄 Migrate SQLite to PostgreSQL"
	@echo ""
	@read -p "Enter PostgreSQL URL (e.g., postgresql://user:pass@localhost/trading): " pgurl && \
	if [ -n "$$pgurl" ]; then \
		$(DB_CMD) migrate "$$pgurl"; \
	else \
		echo "❌ Migration cancelled"; \
	fi

# Setup database encryption
db-encrypt-setup:
	@uv run python cli/db_encrypt.py setup

# Check database encryption status
db-encrypt-status:
	@uv run python cli/db_encrypt.py status
