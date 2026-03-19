.PHONY: help setup install clean deep-clean test lint format typecheck check run-paper run-live backtest logs ops opshow opstatus opdelete opconfig-init opconfig-set opconfig-show opconfig-delete backup restore pre-commit-install pre-commit db db-stats db-analytics db-backtests db-export db-export-csv db-encrypt-setup db-encrypt-status api-ready api-test api-balance api-ticker api-tickers api-all-tickers api-currencies api-currency-pairs api-last-public-trades api-order-book api-candles api-open-orders api-historical-orders api-trades api-public-trades api-order

# ============================================================================
# 1Password vault/item names — must match src/utils/onepassword.py constants
# ============================================================================

OP_VAULT  := revolut-trader
OP_CREDS  := revolut-trader-credentials
OP_CONFIG := revolut-trader-config

# ============================================================================
# Help
# ============================================================================

help:
	@echo "Revolut Trading Bot - Make Commands"
	@echo ""
	@echo "Setup & Installation:"
	@echo "  make setup             - First-time project setup"
	@echo "  make install           - Install/update dependencies"
	@echo "  make clean             - Remove cache files and artifacts"
	@echo "  make deep-clean        - Remove ALL generated files (data, logs, venv)"
	@echo ""
	@echo "Credentials & Configuration (1Password vault: $(OP_VAULT)):"
	@echo "  make ops               - Set API credentials interactively"
	@echo "  make opshow            - Show stored credentials and config (masked)"
	@echo "  make opstatus          - Check 1Password CLI status"
	@echo "  make opdelete          - Delete credentials item from 1Password"
	@echo "  make opconfig-init     - Create config item with safe defaults"
	@echo "  make opconfig-set      - Set a config value (KEY=... VALUE=...)"
	@echo "  make opconfig-show     - Show current configuration"
	@echo "  make opconfig-delete   - Remove a config key (KEY=...)"
	@echo ""
	@echo "Trading & Analysis:"
	@echo "  make run-paper         - Run in paper mode (safe, simulated trading)"
	@echo "  make run-live          - Run in live mode (REAL MONEY)"
	@echo "  make backtest          - Run strategy backtesting (STRATEGY=... DAYS=...)"
	@echo ""
	@echo "API Testing:"
	@echo "  make api-ready                    - Check API permissions (view + trade)"
	@echo "  make api-test                     - Test authenticated connection"
	@echo "  make api-balance                  - Account balances"
	@echo "  make api-ticker SYMBOL=BTC-EUR    - Single ticker (via order book)"
	@echo "  make api-tickers SYMBOLS=BTC-EUR  - Multiple tickers"
	@echo "  make api-all-tickers              - All pairs (GET /tickers)"
	@echo "  make api-currencies               - All currencies (GET /configuration/currencies)"
	@echo "  make api-currency-pairs           - All pairs config (GET /configuration/pairs)"
	@echo "  make api-last-public-trades       - Last 100 public trades (unauthenticated)"
	@echo "  make api-order-book SYMBOL=BTC-EUR            - Raw order book snapshot (authenticated)"
	@echo "  make api-order-book SYMBOL=BTC-EUR DEPTH=5   - With custom depth (1-20)"
	@echo "  make api-candles SYMBOL=BTC-EUR                - Candles (60min, last 10)"
	@echo "  make api-candles SYMBOL=BTC-EUR INTERVAL=15 LIMIT=20"
	@echo "  make api-open-orders                          - All active orders"
	@echo "  make api-open-orders SYMBOL=BTC-EUR           - Active orders for one pair"
	@echo "  make api-historical-orders                    - Completed/cancelled orders"
	@echo "  make api-historical-orders SYMBOL=BTC-EUR LIMIT=50"
	@echo "  make api-trades SYMBOL=BTC-EUR                - Private trade history"
	@echo "  make api-trades SYMBOL=BTC-EUR LIMIT=50"
	@echo "  make api-public-trades SYMBOL=BTC-EUR         - Public trade history"
	@echo "  make api-order ORDER_ID=<uuid>                - Single order details"
	@echo ""
	@echo "Code Quality:"
	@echo "  make test              - Run tests with coverage"
	@echo "  make lint              - Check code with ruff"
	@echo "  make format            - Format code with ruff"
	@echo "  make typecheck         - Run mypy type checking"
	@echo "  make check             - Run all quality checks"
	@echo "  make pre-commit        - Run pre-commit hooks on all files"
	@echo ""
	@echo "Database:"
	@echo "  make db                - Show database overview"
	@echo "  make db-stats          - Show database statistics"
	@echo "  make db-analytics      - Trading analytics (DAYS=30)"
	@echo "  make db-backtests      - List recent backtest runs (LIMIT=10)"
	@echo "  make db-export         - Export data to JSON"
	@echo "  make db-export-csv     - Export data to CSV"
	@echo "  make db-encrypt-setup  - Generate and store encryption key in 1Password"
	@echo "  make db-encrypt-status - Check if database encryption is active"
	@echo ""
	@echo "Quick Start:"
	@echo "  1. make setup"
	@echo "  2. make ops"
	@echo "  3. make run-paper"

# ============================================================================
# Setup & Installation
# ============================================================================

setup:
	@echo "=== Revolut Trader Setup ==="
	@echo ""
	@echo "Checking prerequisites..."
	@command -v uv >/dev/null 2>&1 || { echo "Error: uv not installed. Run: brew install uv"; exit 1; }
	@echo "  uv: ok"
	@command -v op >/dev/null 2>&1 || { echo "Error: 1Password CLI not installed. Run: brew install --cask 1password-cli"; exit 1; }
	@echo "  op: ok"
	@op account list >/dev/null 2>&1 || { echo "Error: Not signed in to 1Password. Run: eval \$$(op signin)"; exit 1; }
	@echo "  1Password: signed in"
	@echo ""
	@echo "Setting up 1Password vault: $(OP_VAULT)"
	@op vault get $(OP_VAULT) >/dev/null 2>&1 \
		&& echo "  Vault exists" \
		|| { op vault create $(OP_VAULT) && echo "  Vault created: $(OP_VAULT)"; }
	@echo ""
	@echo "Setting up credentials item: $(OP_CREDS)"
	@if op item get $(OP_CREDS) --vault $(OP_VAULT) >/dev/null 2>&1; then \
		echo "  Item exists"; \
	else \
		op item create \
			--category "Secure Note" \
			--vault $(OP_VAULT) \
			--title $(OP_CREDS) \
			"REVOLUT_API_KEY[concealed]=<add-your-api-key>" \
			>/dev/null && echo "  Item created"; \
	fi
	@echo ""
	@echo "Checking Ed25519 keys..."
	@if op item get $(OP_CREDS) --vault $(OP_VAULT) --fields REVOLUT_PRIVATE_KEY >/dev/null 2>&1; then \
		echo "  Keys already in 1Password"; \
	else \
		echo "  Generating new Ed25519 key pair..."; \
		TMPDIR=$$(mktemp -d); \
		openssl genpkey -algorithm Ed25519 -out $$TMPDIR/private.pem 2>/dev/null || { echo "Error: openssl required"; exit 1; }; \
		openssl pkey -in $$TMPDIR/private.pem -pubout -out $$TMPDIR/public.pem 2>/dev/null; \
		op item edit $(OP_CREDS) --vault $(OP_VAULT) \
			"REVOLUT_PRIVATE_KEY[concealed]=$$(cat $$TMPDIR/private.pem)" \
			"REVOLUT_PUBLIC_KEY[concealed]=$$(cat $$TMPDIR/public.pem)" \
			>/dev/null; \
		echo "  Keys stored in 1Password"; \
		echo ""; \
		echo "  ======================================================"; \
		echo "  IMPORTANT: Register this public key with Revolut X:"; \
		echo "  ======================================================"; \
		cat $$TMPDIR/public.pem; \
		echo "  ======================================================"; \
		rm -rf $$TMPDIR; \
	fi
	@echo ""
	@echo "Setting up configuration item: $(OP_CONFIG)"
	@if op item get $(OP_CONFIG) --vault $(OP_VAULT) >/dev/null 2>&1; then \
		echo "  Item exists"; \
	else \
		op item create \
			--category "Secure Note" \
			--vault $(OP_VAULT) \
			--title $(OP_CONFIG) \
			"TRADING_MODE[text]=paper" \
			"RISK_LEVEL[text]=conservative" \
			"BASE_CURRENCY[text]=EUR" \
			"TRADING_PAIRS[text]=BTC-EUR,ETH-EUR" \
			"DEFAULT_STRATEGY[text]=market_making" \
			"INITIAL_CAPITAL[text]=10000" \
			>/dev/null && echo "  Item created with safe defaults"; \
	fi
	@echo ""
	@echo "Creating directories..."
	@mkdir -p logs data
	@echo "  logs/ data/ created"
	@echo ""
	@echo "Installing dependencies..."
	@uv sync --extra dev
	@echo ""
	@echo "Installing pre-commit hooks..."
	@uv run pre-commit install
	@echo "  Pre-commit hooks installed"
	@echo ""
	@echo "=== Setup complete! ==="
	@echo ""
	@echo "Next steps:"
	@echo "  1. Add your Revolut API key:  make ops"
	@echo "  2. Test in paper mode:        make run-paper"
	@echo "  3. View configuration:        make opconfig-show"

install:
	@echo "Installing dependencies with uv..."
	@uv sync --extra dev
	@echo "Done"

clean:
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name ".coverage" -delete 2>/dev/null || true
	@find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	@echo "Clean complete"

deep-clean:
	@echo "WARNING: This will delete ALL generated files including database, logs, backups, and venv."
	@read -p "Type 'YES' to confirm: " confirm && [ "$$confirm" = "YES" ] || (echo "Cancelled" && exit 1)
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name ".coverage" -delete 2>/dev/null || true
	@find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	@rm -rf data logs results backups .venv .uv 2>/dev/null || true
	@echo "Deep clean complete. Run 'make install' to reinstall dependencies."

# ============================================================================
# 1Password — Credentials & Configuration
# ============================================================================

ops:
	@op account list >/dev/null 2>&1 || { echo "Not signed in. Run: eval \$$(op signin)"; exit 1; }
	@echo "Updating credentials in 1Password ($(OP_VAULT)/$(OP_CREDS))"
	@echo ""
	@read -p "Revolut API Key: " api_key; \
	if [ -n "$$api_key" ]; then \
		op item edit $(OP_CREDS) --vault $(OP_VAULT) "REVOLUT_API_KEY[concealed]=$$api_key" >/dev/null \
			&& echo "  REVOLUT_API_KEY stored" || echo "  Failed to store REVOLUT_API_KEY"; \
	fi
	@echo ""
	@echo "Done. Run 'make opshow' to verify."

opshow:
	@op account list >/dev/null 2>&1 || { echo "Not signed in. Run: eval \$$(op signin)"; exit 1; }
	@echo "=== Credentials ($(OP_CREDS)) ==="
	@for field in REVOLUT_API_KEY REVOLUT_PRIVATE_KEY REVOLUT_PUBLIC_KEY; do \
		value=$$(op item get $(OP_CREDS) --vault $(OP_VAULT) --fields $$field --reveal 2>/dev/null) || continue; \
		len=$${#value}; \
		if [ $$len -gt 100 ]; then masked="<set, $$len chars>"; \
		elif [ $$len -gt 8 ]; then masked="$${value:0:8}..."; \
		else masked="$${value:0:4}..."; fi; \
		printf "  %-25s = %s\n" "$$field" "$$masked"; \
	done
	@echo ""
	@echo "=== Configuration ($(OP_CONFIG)) ==="
	@for field in TRADING_MODE RISK_LEVEL BASE_CURRENCY TRADING_PAIRS DEFAULT_STRATEGY INITIAL_CAPITAL; do \
		value=$$(op item get $(OP_CONFIG) --vault $(OP_VAULT) --fields $$field 2>/dev/null) || continue; \
		printf "  %-25s = %s\n" "$$field" "$$value"; \
	done

opstatus:
	@echo "=== 1Password Status ==="
	@command -v op >/dev/null 2>&1 \
		&& echo "  CLI installed: $$(op --version)" \
		|| { echo "  CLI: not installed (brew install --cask 1password-cli)"; exit 0; }
	@op account list >/dev/null 2>&1 \
		&& echo "  Signed in:  yes" \
		|| { echo "  Signed in:  no  (run: eval \$$(op signin))"; exit 0; }
	@op vault get $(OP_VAULT) >/dev/null 2>&1 \
		&& echo "  Vault:      $(OP_VAULT) (exists)" \
		|| echo "  Vault:      $(OP_VAULT) (missing — run: make setup)"
	@op item get $(OP_CREDS) --vault $(OP_VAULT) >/dev/null 2>&1 \
		&& echo "  Creds item: $(OP_CREDS) (exists)" \
		|| echo "  Creds item: $(OP_CREDS) (missing — run: make setup)"
	@op item get $(OP_CONFIG) --vault $(OP_VAULT) >/dev/null 2>&1 \
		&& echo "  Config item:$(OP_CONFIG) (exists)" \
		|| echo "  Config item:$(OP_CONFIG) (missing — run: make setup)"

opdelete:
	@op account list >/dev/null 2>&1 || { echo "Not signed in. Run: eval \$$(op signin)"; exit 1; }
	@echo "This will delete the credentials item from 1Password."
	@echo "Vault: $(OP_VAULT)  Item: $(OP_CREDS)"
	@read -p "Type 'yes' to confirm: " confirm && [ "$$confirm" = "yes" ] || (echo "Cancelled" && exit 1)
	@op item delete $(OP_CREDS) --vault $(OP_VAULT) && echo "Deleted $(OP_CREDS)"

opconfig-init:
	@op account list >/dev/null 2>&1 || { echo "Not signed in. Run: eval \$$(op signin)"; exit 1; }
	@if op item get $(OP_CONFIG) --vault $(OP_VAULT) >/dev/null 2>&1; then \
		echo "Config item already exists: $(OP_CONFIG)"; \
		read -p "Reset to defaults? (y/N): " confirm; \
		[ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ] || (echo "Cancelled" && exit 1); \
		op item delete $(OP_CONFIG) --vault $(OP_VAULT) >/dev/null; \
	fi
	@op item create \
		--category "Secure Note" \
		--vault $(OP_VAULT) \
		--title $(OP_CONFIG) \
		"TRADING_MODE[text]=paper" \
		"RISK_LEVEL[text]=conservative" \
		"BASE_CURRENCY[text]=EUR" \
		"TRADING_PAIRS[text]=BTC-EUR,ETH-EUR" \
		"DEFAULT_STRATEGY[text]=market_making" \
		"INITIAL_CAPITAL[text]=10000" \
		>/dev/null
	@echo "Config item created with safe defaults:"
	@echo "  TRADING_MODE=paper  RISK_LEVEL=conservative  INITIAL_CAPITAL=10000"
	@echo "  Use 'make opconfig-set KEY=... VALUE=...' to change values"

opconfig-set:
	@if [ -z "$(KEY)" ] || [ -z "$(VALUE)" ]; then \
		echo "Usage: make opconfig-set KEY=TRADING_MODE VALUE=live"; \
		exit 1; \
	fi
	@op item edit $(OP_CONFIG) --vault $(OP_VAULT) "$(KEY)[text]=$(VALUE)" >/dev/null \
		&& echo "$(KEY) = $(VALUE)" \
		|| echo "Failed. Run 'make opconfig-init' first."

opconfig-show:
	@echo "Configuration ($(OP_VAULT)/$(OP_CONFIG)):"
	@for key in TRADING_MODE RISK_LEVEL BASE_CURRENCY TRADING_PAIRS DEFAULT_STRATEGY INITIAL_CAPITAL; do \
		value=$$(op item get $(OP_CONFIG) --vault $(OP_VAULT) --fields $$key 2>/dev/null || echo "(not set)"); \
		printf "  %-22s %s\n" "$$key:" "$$value"; \
	done

opconfig-delete:
	@if [ -z "$(KEY)" ]; then \
		echo "Usage: make opconfig-delete KEY=TRADING_MODE"; \
		exit 1; \
	fi
	@op item edit $(OP_CONFIG) --vault $(OP_VAULT) "$(KEY)[delete]" >/dev/null \
		&& echo "$(KEY) removed" \
		|| echo "Failed to remove $(KEY)"

# ============================================================================
# Trading Bot
# ============================================================================

run-paper:
	@echo "Starting bot in PAPER mode (simulated trading)"
	@uv run python cli/run.py --mode paper --strategy market_making --risk conservative

run-live:
	@echo ""
	@echo "LIVE TRADING MODE - REAL MONEY AT RISK"
	@echo ""
	@read -p "Type 'I UNDERSTAND' to continue: " confirm && [ "$$confirm" = "I UNDERSTAND" ] || (echo "Cancelled" && exit 1)
	@uv run python cli/run.py --mode live --strategy market_making --risk conservative

backtest:
	@mkdir -p results
	@STRATEGY=$${STRATEGY:-market_making}; \
	DAYS=$${DAYS:-30}; \
	OUTPUT=./results/backtest_$$(date +%Y%m%d_%H%M%S).json; \
	echo "Strategy: $$STRATEGY | Days: $$DAYS"; \
	uv run python cli/backtest.py --strategy $$STRATEGY --days $$DAYS --output $$OUTPUT \
		&& echo "Backtest complete: $$OUTPUT" \
		|| echo "Backtest failed - check logs above"

# ============================================================================
# API Testing
# ============================================================================

api-ready:
	@uv run python cli/api_test.py trade-ready

api-test:
	@uv run python cli/api_test.py test

api-balance:
	@uv run python cli/api_test.py balance

api-ticker:
	@SYMBOL=$${SYMBOL:-BTC-EUR}; \
	uv run python cli/api_test.py ticker --symbol $$SYMBOL

api-tickers:
	@SYMBOLS=$${SYMBOLS:-BTC-EUR,ETH-EUR,SOL-EUR}; \
	uv run python cli/api_test.py tickers --symbols $$SYMBOLS

api-candles:
	@SYMBOL=$${SYMBOL:-BTC-EUR}; \
	INTERVAL=$${INTERVAL:-60}; \
	LIMIT=$${LIMIT:-10}; \
	uv run python cli/api_test.py candles --symbol $$SYMBOL --interval $$INTERVAL --limit $$LIMIT

api-all-tickers:
	@uv run python cli/api_test.py all-tickers

api-currencies:
	@uv run python cli/api_test.py currencies

api-currency-pairs:
	@uv run python cli/api_test.py currency-pairs

api-last-public-trades:
	@uv run python cli/api_test.py last-public-trades

api-order-book:
	@if [ -z "$(SYMBOL)" ]; then echo "Usage: make api-order-book SYMBOL=BTC-EUR [DEPTH=20]"; exit 1; fi
	@DEPTH=$${DEPTH:-20}; \
	uv run python cli/api_test.py order-book --symbol $(SYMBOL) --depth $$DEPTH

api-open-orders:
	@ARGS=""; \
	[ -n "$(SYMBOL)" ] && ARGS="--symbol $(SYMBOL)"; \
	uv run python cli/api_test.py open-orders $$ARGS

api-historical-orders:
	@LIMIT=$${LIMIT:-20}; \
	ARGS="--limit $$LIMIT"; \
	[ -n "$(SYMBOL)" ] && ARGS="$$ARGS --symbol $(SYMBOL)"; \
	uv run python cli/api_test.py historical-orders $$ARGS

api-trades:
	@if [ -z "$(SYMBOL)" ]; then echo "Usage: make api-trades SYMBOL=BTC-EUR"; exit 1; fi
	@LIMIT=$${LIMIT:-20}; \
	uv run python cli/api_test.py trades --symbol $(SYMBOL) --limit $$LIMIT

api-public-trades:
	@if [ -z "$(SYMBOL)" ]; then echo "Usage: make api-public-trades SYMBOL=BTC-EUR"; exit 1; fi
	@uv run python cli/api_test.py public-trades --symbol $(SYMBOL)

api-order:
	@if [ -z "$(ORDER_ID)" ]; then echo "Usage: make api-order ORDER_ID=<uuid>"; exit 1; fi
	@uv run python cli/api_test.py order --order-id $(ORDER_ID)

# ============================================================================
# Code Quality
# ============================================================================

pre-commit-install:
	@uv sync --extra dev --quiet
	@uv run pre-commit install
	@echo "Pre-commit hooks installed"

pre-commit:
	@uv run pre-commit run --all-files

test:
	@uv run pytest --cov=src --cov-report=term-missing --cov-report=html
	@echo "Coverage report: htmlcov/index.html"

lint:
	@uv run ruff check src/ tests/ cli/

format:
	@uv run ruff format src/ tests/ cli/
	@uv run ruff check --fix src/ tests/ cli/

typecheck:
	@uv run mypy src/ cli/

check: lint format typecheck test
	@echo "All quality checks passed"

# ============================================================================
# Logs
# ============================================================================

logs:
	@if [ -d "logs" ] && [ "$$(ls -A logs 2>/dev/null)" ]; then \
		tail -n 50 logs/$$(ls -t logs | head -1); \
	else \
		echo "No logs found. Run the bot first."; \
	fi

logs-follow:
	@if [ -d "logs" ] && [ "$$(ls -A logs 2>/dev/null)" ]; then \
		tail -f logs/$$(ls -t logs | head -1); \
	else \
		echo "No logs found. Run the bot first."; \
	fi

# ============================================================================
# Backup & Restore
# ============================================================================

backup:
	@mkdir -p backups
	@BACKUP_NAME=backup_$$(date +%Y%m%d_%H%M%S); \
	mkdir -p backups/$$BACKUP_NAME; \
	[ -d "data" ] && cp -r data backups/$$BACKUP_NAME/ || true; \
	[ -d "logs" ] && cp -r logs backups/$$BACKUP_NAME/ || true; \
	echo "Backup created: backups/$$BACKUP_NAME"

restore:
	@echo "Available backups:"; ls -1 backups/ 2>/dev/null || echo "None"
	@read -p "Enter backup name to restore: " backup && \
	if [ -d "backups/$$backup" ]; then \
		[ -d "backups/$$backup/data" ] && cp -r backups/$$backup/data . || true; \
		echo "Restored from $$backup"; \
	else \
		echo "Backup not found"; \
	fi

# ============================================================================
# Database Management
# ============================================================================

DB_CMD = @uv run python cli/db_manage.py

db:
	$(DB_CMD) stats
	@echo ""
	$(DB_CMD) analytics 7
	@echo ""
	$(DB_CMD) backtests 5

db-stats:
	$(DB_CMD) stats

db-analytics:
	$(DB_CMD) analytics $${DAYS:-30}

db-backtests:
	$(DB_CMD) backtests $${LIMIT:-10}

db-export:
	$(DB_CMD) export $${DIR:-data/exports}

db-export-csv:
	$(DB_CMD) export-csv

db-encrypt-setup:
	@uv run python -c "from src.utils.db_encryption import setup_database_encryption; setup_database_encryption()"

db-encrypt-status:
	@uv run python -c "from src.utils.db_encryption import DatabaseEncryption; e = DatabaseEncryption(); print('Encryption enabled:', e.is_enabled)"
