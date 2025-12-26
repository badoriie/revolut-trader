.PHONY: help clean deep-clean install test format lint type-check run-paper run-live 1password-setup 1password-status 1password-show 1password-delete ops opshow opstatus opdelete

# Default target
help:
	@echo "Available commands:"
	@echo ""
	@echo "Development:"
	@echo "  make install           - Install dependencies"
	@echo "  make install-dev       - Install with development dependencies"
	@echo "  make clean             - Remove Python cache files and test artifacts"
	@echo "  make deep-clean        - Remove all generated files including logs and data"
	@echo ""
	@echo "Code Quality:"
	@echo "  make test              - Run tests with coverage"
	@echo "  make test-fast         - Run tests without coverage"
	@echo "  make format            - Format code with ruff"
	@echo "  make format-check      - Check code formatting"
	@echo "  make lint              - Lint code with ruff"
	@echo "  make lint-fix          - Auto-fix linting issues"
	@echo "  make type-check        - Run type checking with mypy"
	@echo "  make check-all         - Run all quality checks"
	@echo ""
	@echo "Trading Bot:"
	@echo "  make run-paper         - Run bot in paper trading mode"
	@echo "  make run-live          - Run bot in live trading mode (USE WITH CAUTION)"
	@echo "  make setup             - Initial project setup"
	@echo ""
	@echo "1Password (required - short commands):"
	@echo "  make ops               - Setup 1Password and store credentials"
	@echo "  make opshow            - Show stored credentials (masked)"
	@echo "  make opstatus          - Check 1Password status"
	@echo "  make opdelete          - Delete credentials from 1Password"
	@echo ""
	@echo "Security & Maintenance:"
	@echo "  make backup            - Backup configuration and data"
	@echo "  make security-check    - Run security checks"
	@echo "  make validate-config   - Validate configuration"
	@echo "  make status            - Show project status"

# Clean Python cache files, test artifacts, and build files
clean:
	@echo "🧹 Cleaning Python cache files and test artifacts..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type f -name "*.py,cover" -delete 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".tox" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "build" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "dist" -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ Clean complete!"

# Deep clean - removes logs, data, and virtual environments
deep-clean: clean
	@echo "🗑️  Deep cleaning project..."
	@echo "⚠️  This will remove logs and data directories!"
	@read -p "Are you sure? (y/N): " confirm && [ "$$confirm" = "y" ] || exit 1
	rm -rf logs/* 2>/dev/null || true
	rm -rf data/* 2>/dev/null || true
	rm -rf venv/ 2>/dev/null || true
	rm -rf .venv/ 2>/dev/null || true
	rm -rf env/ 2>/dev/null || true
	@echo "✅ Deep clean complete!"

# Install dependencies
install:
	@echo "📦 Installing dependencies..."
	pip install -e .
	@echo "✅ Installation complete!"

# Install development dependencies
install-dev:
	@echo "📦 Installing development dependencies..."
	pip install -e ".[dev]"
	@echo "✅ Development installation complete!"

# Run tests
test:
	@echo "🧪 Running tests..."
	pytest --cov=src --cov-report=term-missing --cov-report=html
	@echo "✅ Tests complete!"

# Run tests without coverage
test-fast:
	@echo "🧪 Running tests (fast mode)..."
	pytest -v
	@echo "✅ Tests complete!"

# Format code
format:
	@echo "🎨 Formatting code..."
	ruff format src/ tests/ run.py
	@echo "✅ Formatting complete!"

# Check formatting without making changes
format-check:
	@echo "🎨 Checking code formatting..."
	ruff format --check src/ tests/ run.py
	@echo "✅ Format check complete!"

# Lint code
lint:
	@echo "🔍 Linting code..."
	ruff check src/ tests/ run.py
	@echo "✅ Linting complete!"

# Fix linting issues automatically
lint-fix:
	@echo "🔧 Fixing linting issues..."
	ruff check --fix src/ tests/ run.py
	@echo "✅ Linting fixes complete!"

# Type checking
type-check:
	@echo "🔎 Running type checks..."
	mypy src/
	@echo "✅ Type checking complete!"

# Run all quality checks
check-all: format-check lint type-check test
	@echo "✅ All checks passed!"

# Initial project setup
setup:
	@echo "🚀 Setting up project..."
	@if [ -f "./setup.sh" ]; then \
		bash setup.sh; \
	else \
		echo "⚠️  setup.sh not found"; \
	fi
	@echo "✅ Setup complete!"

# Run bot in paper trading mode
run-paper:
	@echo "📊 Starting bot in PAPER trading mode..."
	python run.py --mode paper --strategy market_making --risk conservative

# Run bot in live trading mode (dangerous!)
run-live:
	@echo "⚠️  STARTING BOT IN LIVE TRADING MODE!"
	@echo "⚠️  THIS USES REAL MONEY!"
	@read -p "Are you absolutely sure? (type 'yes' to continue): " confirm && [ "$$confirm" = "yes" ] || exit 1
	python run.py --mode live --strategy market_making --risk conservative

# Start bot with custom parameters
run:
	@echo "Starting bot..."
	python run.py $(ARGS)

# View recent logs
logs:
	@echo "📋 Recent logs:"
	@if [ -d "logs" ] && [ "$$(ls -A logs 2>/dev/null)" ]; then \
		tail -n 50 logs/$$(ls -t logs | head -1); \
	else \
		echo "No logs found"; \
	fi

# Follow logs in real-time
logs-follow:
	@echo "📋 Following logs (Ctrl+C to stop)..."
	@if [ -d "logs" ] && [ "$$(ls -A logs 2>/dev/null)" ]; then \
		tail -f logs/$$(ls -t logs | head -1); \
	else \
		echo "No logs found"; \
	fi

# Show project status
status:
	@echo "📊 Project Status"
	@echo "================"
	@echo ""
	@echo "Python version:"
	@python --version
	@echo ""
	@echo "Dependencies installed:"
	@pip list | grep -E "httpx|pydantic|cryptography|python-telegram-bot" || echo "Dependencies not installed"
	@echo ""
	@echo "Logs directory:"
	@if [ -d "logs" ]; then \
		echo "  Exists ($(ls logs 2>/dev/null | wc -l | tr -d ' ') files)"; \
	else \
		echo "  Not created"; \
	fi
	@echo ""
	@echo "Data directory:"
	@if [ -d "data" ]; then \
		echo "  Exists ($(ls data 2>/dev/null | wc -l | tr -d ' ') files)"; \
	else \
		echo "  Not created"; \
	fi
	@echo ""
	@echo "1Password Status:"
	@if command -v op &> /dev/null && op account list &> /dev/null; then \
		if op item get revolut-trader-credentials --vault revolut-trader &> /dev/null; then \
			echo "  Credentials stored in 1Password ✓"; \
		else \
			echo "  Credentials not found in 1Password ✗"; \
		fi \
	else \
		echo "  1Password not available ✗"; \
	fi

# Backup configuration and data
backup:
	@echo "💾 Creating backup..."
	@mkdir -p backups
	@BACKUP_NAME=backup_$$(date +%Y%m%d_%H%M%S); \
	mkdir -p backups/$$BACKUP_NAME; \
	[ -d "config" ] && cp -r config backups/$$BACKUP_NAME/ || true; \
	[ -d "data" ] && cp -r data backups/$$BACKUP_NAME/ || true; \
	[ -d "logs" ] && cp -r logs backups/$$BACKUP_NAME/ || true; \
	echo "✅ Backup created: backups/$$BACKUP_NAME"
	@echo "ℹ️  Credentials are stored in 1Password, not backed up locally"

# Restore from backup
restore:
	@echo "📥 Available backups:"
	@ls -1 backups/ 2>/dev/null || echo "No backups found"
	@echo ""
	@read -p "Enter backup name to restore: " backup && \
	if [ -d "backups/$$backup" ]; then \
		echo "Restoring from $$backup..."; \
		[ -d "backups/$$backup/config" ] && cp -r backups/$$backup/config . || true; \
		[ -d "backups/$$backup/data" ] && cp -r backups/$$backup/data . || true; \
		echo "✅ Restore complete!"; \
		echo "ℹ️  Credentials must be retrieved from 1Password separately"; \
	else \
		echo "❌ Backup not found"; \
	fi

# Generate new API keys (Ed25519)
generate-keys:
	@echo "🔑 Generating new Ed25519 key pair..."
	@mkdir -p config
	openssl genpkey -algorithm ed25519 -out config/revolut_private.pem
	openssl pkey -in config/revolut_private.pem -pubout -out config/revolut_public.pem
	@echo "✅ Keys generated:"
	@echo "  Private: config/revolut_private.pem"
	@echo "  Public:  config/revolut_public.pem"
	@echo ""
	@echo "⚠️  Remember to:"
	@echo "  1. Keep private key secure"
	@echo "  2. Register public key with Revolut"

# Validate configuration
validate-config:
	@echo "🔍 Validating configuration..."
	@python -c "from src.config import Settings; s = Settings(); print('✅ Configuration valid!')" || echo "❌ Configuration invalid"

# Security check
security-check:
	@echo "🔒 Running security checks..."
	@echo "Checking for exposed secrets..."
	@! git grep -i "api.*key.*=" -- '*.py' '*.md' || echo "⚠️  Found potential API key in code"
	@! git grep -i "private.*key" -- '*.py' '*.md' || echo "⚠️  Found potential private key reference"
	@echo "Checking .gitignore..."
	@grep -q "^\.env$$" .gitignore && echo "✅ .env in .gitignore" || echo "❌ .env not in .gitignore"
	@grep -q "revolut_private.pem" .gitignore && echo "✅ private key in .gitignore" || echo "⚠️  private key not in .gitignore"
	@echo "✅ Security check complete!"

# 1Password Integration Commands (Required)

# Setup 1Password and store credentials
1password-setup:
	@bash scripts/1password-manager.sh setup

# Show stored credentials (masked)
1password-show:
	@bash scripts/1password-manager.sh show

# Check 1Password status
1password-status:
	@bash scripts/1password-manager.sh status

# Delete credentials from 1Password
1password-delete:
	@bash scripts/1password-manager.sh delete

# Short aliases
ops: 1password-setup
opshow: 1password-show
opstatus: 1password-status
opdelete: 1password-delete
