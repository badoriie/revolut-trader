.PHONY: help setup install clean deep-clean test lint format typecheck security check run-mock run-paper run-live run-dev run-int run-prod backtest backtest-hf backtest-compare backtest-matrix logs logs-follow ops opshow opstatus opdelete opconfig-init opconfig-set opconfig-show opconfig-delete backup restore pre-commit-install pre-commit db db-stats db-analytics db-backtests db-export db-export-csv db-encrypt-setup db-encrypt-status db-report api-ready api-test api-balance api-ticker api-tickers api-all-tickers api-currencies api-currency-pairs api-last-public-trades api-order-book api-candles api-open-orders api-historical-orders api-trades api-public-trades api-order

# ============================================================================
# Environment — dev (default), int, prod
# ============================================================================

ENV ?= dev

# Backtest targets default to int (real historical data).
# Override with: make backtest BACKTEST_ENV=dev
BACKTEST_ENV ?= int

# ============================================================================
# 1Password vault/item names — environment-suffixed
# ============================================================================

OP_VAULT  := revolut-trader
OP_CREDS  := revolut-trader-credentials-$(ENV)
OP_CONFIG := revolut-trader-config-$(ENV)

# ============================================================================
# Help
# ============================================================================

help:
	@echo "Revolut Trading Bot - Make Commands"
	@echo ""
	@echo "Current environment: $(ENV)  (override with ENV=dev|int|prod)"
	@echo "  1Password items: $(OP_CREDS) / $(OP_CONFIG)"
	@echo ""
	@echo "Setup & Installation:"
	@echo "  make setup             - First-time project setup (creates all env items)"
	@echo "  make install           - Install/update dependencies"
	@echo "  make clean             - Remove cache files and artifacts"
	@echo "  make deep-clean        - Remove ALL generated files (data, venv)"
	@echo ""
	@echo "Credentials & Configuration (use ENV=dev|int|prod to target an environment):"
	@echo "  make ops               - Set API credentials for ENV (default: dev)"
	@echo "  make opshow            - Show stored credentials and config (masked)"
	@echo "  make opstatus          - Check 1Password CLI status"
	@echo "  make opdelete          - Delete credentials item from 1Password"
	@echo "  make opconfig-init     - Create config item with safe defaults"
	@echo "  make opconfig-set      - Set a config value (KEY=... VALUE=...)"
	@echo "  make opconfig-show     - Show current configuration"
	@echo "  make opconfig-delete   - Remove a config key (KEY=...)"
	@echo ""
	@echo "Trading & Analysis:"
	@echo "  make run-mock          - Run with mock API (dev env, no credentials needed)"
	@echo "  make run-paper         - Run paper trading (int env, real API, no real trades)"
	@echo "  make run-live          - Run live trading (prod env, REAL MONEY)"
	@echo "  make backtest          - Backtest one strategy using real data (int env by default)"
	@echo "                           STRATEGY=... DAYS=... RISK=... INTERVAL=... PAIRS=..."
	@echo "                           Override env: make backtest BACKTEST_ENV=dev"
	@echo "  make backtest-hf       - High-frequency backtest (1-minute candles, closest to live 5s polling)"
	@echo "                           STRATEGY=... DAYS=... RISK=... PAIRS=..."
	@echo "  make backtest-compare  - Compare all strategies side-by-side (DAYS=... RISK=...)"
	@echo "  make backtest-matrix   - All strategies x all risk levels matrix"
	@echo ""
	@echo "API Testing (defaults to int — use ENV=prod for production):"
	@echo "  make api-test                             - Test authenticated connection"
	@echo "  make api-ready                            - Check API permissions (view + trade)"
	@echo "  make api-balance                          - Account balances"
	@echo "  make api-ticker SYMBOL=BTC-EUR            - Single ticker (via order book)"
	@echo "  make api-tickers SYMBOLS=BTC-EUR          - Multiple tickers"
	@echo "  make api-all-tickers                      - All pairs (GET /tickers)"
	@echo "  make api-currencies                       - All currencies"
	@echo "  make api-currency-pairs                   - All pairs config"
	@echo "  make api-last-public-trades               - Last 100 public trades"
	@echo "  make api-order-book SYMBOL=BTC-EUR        - Order book snapshot"
	@echo "  make api-candles SYMBOL=BTC-EUR           - Candles (60min, last 10)"
	@echo "  make api-open-orders                      - All active orders"
	@echo "  make api-historical-orders                - Completed/cancelled orders"
	@echo "  make api-trades SYMBOL=BTC-EUR            - Private trade history"
	@echo "  make api-public-trades SYMBOL=BTC-EUR     - Public trade history"
	@echo "  make api-order ORDER_ID=<uuid>            - Single order details"
	@echo ""
	@echo "Code Quality:"
	@echo "  make test              - Run tests with coverage"
	@echo "  make lint              - Check code with ruff"
	@echo "  make format            - Format code with ruff"
	@echo "  make typecheck         - Run pyright type checking"
	@echo "  make security          - Run bandit static security analysis"
	@echo "  make check             - Run all quality checks (lint, format, typecheck, security, test)"
	@echo "  make pre-commit        - Run pre-commit hooks on all files"
	@echo "  make pre-commit-install - Install pre-commit + commit-msg hooks"
	@echo ""
	@echo "Logs & Backup:"
	@echo "  make logs              - Redirect: logs are in the encrypted database"
	@echo "  make logs-follow       - Redirect: logs are in the encrypted database"
	@echo "  make backup            - Create a timestamped backup of data/ to backups/"
	@echo "  make restore           - Interactively restore data/ from a backup"
	@echo ""
	@echo "Database (uses ENV for DB file selection):"
	@echo "  make db                - Show database overview"
	@echo "  make db-stats          - Show database statistics"
	@echo "  make db-analytics      - Trading analytics (DAYS=30)"
	@echo "  make db-backtests      - List recent backtest runs (LIMIT=10)"
	@echo "  make db-export         - Export data to JSON"
	@echo "  make db-export-csv     - Export data to CSV"
	@echo "  make db-encrypt-setup  - Generate and store encryption key in 1Password"
	@echo "  make db-encrypt-status - Check if database encryption is active"
	@echo "  make db-report         - Comprehensive analytics report with charts (DAYS=30)"
	@echo ""
	@echo "Quick Start:"
	@echo "  1. make setup"
	@echo "  2. make run-mock         (mock API — no API key needed)"
	@echo "  3. make ops ENV=int      (for real API testing)"

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
	@op whoami >/dev/null 2>&1 || { echo "Error: 1Password not authenticated. Set OP_SERVICE_ACCOUNT_TOKEN."; exit 1; }
	@echo "  1Password: authenticated"
	@echo ""
	@echo "Setting up 1Password vault: $(OP_VAULT)"
	@op vault get $(OP_VAULT) >/dev/null 2>&1 \
		&& echo "  Vault exists" \
		|| { op vault create $(OP_VAULT) && echo "  Vault created: $(OP_VAULT)"; }
	@echo ""
	@# --- Create credentials + config + Ed25519 keys for each environment ---
	@for env in dev int prod; do \
		CREDS="revolut-trader-credentials-$$env"; \
		CONFIG="revolut-trader-config-$$env"; \
		echo "Setting up $$env environment..."; \
		if op item get $$CREDS --vault $(OP_VAULT) >/dev/null 2>&1; then \
			echo "  $$CREDS: exists"; \
		else \
			if [ "$$env" = "dev" ]; then \
				op item create \
					--category "Secure Note" \
					--vault $(OP_VAULT) \
					--title $$CREDS \
					>/dev/null && echo "  $$CREDS: created (dev uses mock API — no API key needed)"; \
			else \
				op item create \
					--category "Secure Note" \
					--vault $(OP_VAULT) \
					--title $$CREDS \
					"REVOLUT_API_KEY[concealed]=<add-your-$$env-api-key>" \
					>/dev/null && echo "  $$CREDS: created"; \
			fi; \
		fi; \
		if op item get $$CONFIG --vault $(OP_VAULT) >/dev/null 2>&1; then \
			echo "  $$CONFIG: exists"; \
		else \
			if [ "$$env" = "prod" ]; then \
				op item create \
					--category "Secure Note" \
					--vault $(OP_VAULT) \
					--title $$CONFIG \
					"RISK_LEVEL[text]=conservative" \
					"BASE_CURRENCY[text]=EUR" \
					"TRADING_PAIRS[text]=BTC-EUR,ETH-EUR" \
					"DEFAULT_STRATEGY[text]=market_making" \
					>/dev/null && echo "  $$CONFIG: created (prod — no INITIAL_CAPITAL needed)"; \
				echo "  Tip: limit trading capital with: make opconfig-set KEY=MAX_CAPITAL VALUE=5000 ENV=prod"; \
			else \
				op item create \
					--category "Secure Note" \
					--vault $(OP_VAULT) \
					--title $$CONFIG \
					"RISK_LEVEL[text]=conservative" \
					"BASE_CURRENCY[text]=EUR" \
					"TRADING_PAIRS[text]=BTC-EUR,ETH-EUR" \
					"DEFAULT_STRATEGY[text]=market_making" \
					"INITIAL_CAPITAL[text]=10000" \
					>/dev/null && echo "  $$CONFIG: created with safe defaults"; \
			fi; \
		fi; \
		if [ "$$env" = "dev" ]; then \
			echo "  $$env: mock API — skipping Ed25519 key generation"; \
		else \
			echo "  Checking Ed25519 keys for $$env..."; \
			if op item get $$CREDS --vault $(OP_VAULT) --fields REVOLUT_PRIVATE_KEY >/dev/null 2>&1; then \
				echo "  $$env keys: already in 1Password"; \
			else \
				echo "  Generating Ed25519 key pair for $$env..."; \
				TMPDIR=$$(mktemp -d); \
				openssl genpkey -algorithm Ed25519 -out $$TMPDIR/private.pem 2>/dev/null || { echo "Error: openssl required"; exit 1; }; \
				openssl pkey -in $$TMPDIR/private.pem -pubout -out $$TMPDIR/public.pem 2>/dev/null; \
				op item edit $$CREDS --vault $(OP_VAULT) \
					"REVOLUT_PRIVATE_KEY[concealed]=$$(cat $$TMPDIR/private.pem)" \
					"REVOLUT_PUBLIC_KEY[concealed]=$$(cat $$TMPDIR/public.pem)" \
					>/dev/null; \
				echo "  $$env keys: stored in $$CREDS"; \
				echo ""; \
				echo "  ======================================================"; \
				echo "  Register this $$env public key with Revolut X:"; \
				echo "  ======================================================"; \
				cat $$TMPDIR/public.pem; \
				echo "  ======================================================"; \
				rm -rf $$TMPDIR; \
			fi; \
		fi; \
		echo ""; \
	done
	@echo ""
	@echo "Creating directories..."
	@mkdir -p data
	@echo "  data/ created"
	@echo ""
	@echo "Installing dependencies..."
	@uv sync --extra dev
	@echo ""
	@echo "Installing pre-commit hooks..."
	@uv run pre-commit install
	@uv run pre-commit install --hook-type commit-msg
	@echo "  Pre-commit hooks installed (pre-commit + commit-msg)"
	@echo ""
	@echo "=== Setup complete! ==="
	@echo ""
	@echo "Next steps:"
	@echo "  1. Run in mock mode:    make run-mock  (uses mock API — no API key needed)"
	@echo "  2. Add API keys for int/prod: make ops ENV=int  (and ENV=prod)"
	@echo "  3. View configuration:  make opconfig-show ENV=dev"

install:
	@echo "Installing dependencies with uv..."
	@uv sync --extra dev
	@echo "Done"

clean:
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pyright" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name ".coverage" -delete 2>/dev/null || true
	@find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	@echo "Clean complete"

deep-clean:
	@echo "WARNING: This will delete ALL generated files including database, backups, and venv."
	@read -p "Type 'YES' to confirm: " confirm && [ "$$confirm" = "YES" ] || (echo "Cancelled" && exit 1)
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pyright" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name ".coverage" -delete 2>/dev/null || true
	@find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	@rm -rf data results backups .venv .uv 2>/dev/null || true
	@echo "Deep clean complete. Run 'make install' to reinstall dependencies."

# ============================================================================
# 1Password — Credentials & Configuration
# ============================================================================

ops:
	@op whoami >/dev/null 2>&1 || { echo "Error: 1Password not authenticated. Set OP_SERVICE_ACCOUNT_TOKEN."; exit 1; }
	@if [ "$(ENV)" = "dev" ]; then \
		echo "Dev environment uses mock API — no API credentials needed."; \
		echo "Run 'make run-mock' to start with the mock API."; \
	else \
		echo "Updating credentials in 1Password ($(OP_VAULT)/$(OP_CREDS))"; \
		echo ""; \
		printf "Revolut API Key: "; read api_key; \
		if [ -n "$$api_key" ]; then \
			op item edit $(OP_CREDS) --vault $(OP_VAULT) "REVOLUT_API_KEY[concealed]=$$api_key" >/dev/null \
				&& echo "  REVOLUT_API_KEY stored" || echo "  Failed to store REVOLUT_API_KEY"; \
		fi; \
		echo ""; \
		echo "Done. Run 'make opshow' to verify."; \
	fi

opshow:
	@op whoami >/dev/null 2>&1 || { echo "Error: 1Password not authenticated. Set OP_SERVICE_ACCOUNT_TOKEN."; exit 1; }
	@echo "=== Credentials ($(OP_CREDS)) ==="
	@if [ "$(ENV)" = "dev" ]; then \
		echo "  (dev uses mock API — no API credentials needed)"; \
	else \
		for field in REVOLUT_API_KEY REVOLUT_PRIVATE_KEY REVOLUT_PUBLIC_KEY; do \
			value=$$(op item get $(OP_CREDS) --vault $(OP_VAULT) --fields $$field --reveal 2>/dev/null) || continue; \
			len=$${#value}; \
			if [ $$len -gt 100 ]; then masked="<set, $$len chars>"; \
			elif [ $$len -gt 8 ]; then masked="$${value:0:8}..."; \
			else masked="$${value:0:4}..."; fi; \
			printf "  %-25s = %s\n" "$$field" "$$masked"; \
		done; \
	fi
	@echo ""
	@echo "=== Configuration ($(OP_CONFIG)) ==="
	@echo "  TRADING_MODE              = (derived: dev/int → paper, prod → live)"
	@for field in RISK_LEVEL BASE_CURRENCY TRADING_PAIRS DEFAULT_STRATEGY INITIAL_CAPITAL MAX_CAPITAL; do \
		value=$$(op item get $(OP_CONFIG) --vault $(OP_VAULT) --fields $$field 2>/dev/null) || continue; \
		printf "  %-25s = %s\n" "$$field" "$$value"; \
	done

opstatus:
	@echo "=== 1Password Status ==="
	@command -v op >/dev/null 2>&1 \
		&& echo "  CLI installed: $$(op --version)" \
		|| { echo "  CLI: not installed (brew install --cask 1password-cli)"; exit 0; }
	@op whoami >/dev/null 2>&1 \
		&& echo "  Authenticated: yes (service account)" \
		|| { echo "  Authenticated: no  (set OP_SERVICE_ACCOUNT_TOKEN)"; exit 0; }
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
	@op whoami >/dev/null 2>&1 || { echo "Error: 1Password not authenticated. Set OP_SERVICE_ACCOUNT_TOKEN."; exit 1; }
	@echo "This will delete the credentials item from 1Password."
	@echo "Vault: $(OP_VAULT)  Item: $(OP_CREDS)"
	@read -p "Type 'yes' to confirm: " confirm && [ "$$confirm" = "yes" ] || (echo "Cancelled" && exit 1)
	@op item delete $(OP_CREDS) --vault $(OP_VAULT) && echo "Deleted $(OP_CREDS)"

opconfig-init:
	@op whoami >/dev/null 2>&1 || { echo "Error: 1Password not authenticated. Set OP_SERVICE_ACCOUNT_TOKEN."; exit 1; }
	@if op item get $(OP_CONFIG) --vault $(OP_VAULT) >/dev/null 2>&1; then \
		echo "Config item already exists: $(OP_CONFIG)"; \
		read -p "Reset to defaults? (y/N): " confirm; \
		[ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ] || (echo "Cancelled" && exit 1); \
		op item delete $(OP_CONFIG) --vault $(OP_VAULT) >/dev/null; \
	fi
	@if [ "$(ENV)" = "prod" ]; then \
		op item create \
			--category "Secure Note" \
			--vault $(OP_VAULT) \
			--title $(OP_CONFIG) \
			"RISK_LEVEL[text]=conservative" \
			"BASE_CURRENCY[text]=EUR" \
			"TRADING_PAIRS[text]=BTC-EUR,ETH-EUR" \
			"DEFAULT_STRATEGY[text]=market_making" \
			>/dev/null; \
		echo "Config item created (prod — no INITIAL_CAPITAL needed, real balance from API)"; \
		echo "  Tip: limit trading capital with: make opconfig-set KEY=MAX_CAPITAL VALUE=5000 ENV=prod"; \
	else \
		op item create \
			--category "Secure Note" \
			--vault $(OP_VAULT) \
			--title $(OP_CONFIG) \
			"RISK_LEVEL[text]=conservative" \
			"BASE_CURRENCY[text]=EUR" \
			"TRADING_PAIRS[text]=BTC-EUR,ETH-EUR" \
			"DEFAULT_STRATEGY[text]=market_making" \
			"INITIAL_CAPITAL[text]=10000" \
			>/dev/null; \
		echo "Config item created with safe defaults:"; \
		echo "  RISK_LEVEL=conservative  INITIAL_CAPITAL=10000"; \
	fi
	@echo "  Trading mode: derived from environment (dev/int → paper, prod → live)"
	@echo "  MAX_CAPITAL: optional — limits how much the bot can trade with"
	@echo "  Use 'make opconfig-set KEY=... VALUE=...' to change values"

opconfig-set:
	@if [ -z "$(KEY)" ] || [ -z "$(VALUE)" ]; then \
		echo "Usage: make opconfig-set KEY=RISK_LEVEL VALUE=moderate"; \
		exit 1; \
	fi
	@op item edit $(OP_CONFIG) --vault $(OP_VAULT) "$(KEY)[text]=$(VALUE)" >/dev/null \
		&& echo "$(KEY) = $(VALUE)" \
		|| echo "Failed. Run 'make opconfig-init' first."

opconfig-show:
	@echo "Configuration ($(OP_VAULT)/$(OP_CONFIG)):"
	@echo "  TRADING_MODE:            (derived: dev/int → paper, prod → live)"
	@for key in RISK_LEVEL BASE_CURRENCY TRADING_PAIRS DEFAULT_STRATEGY INITIAL_CAPITAL MAX_CAPITAL; do \
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

run-mock:
	@echo "Starting bot in DEV environment (mock API, no credentials needed)"
	@ENVIRONMENT=dev uv run python cli/run.py --env dev --strategy market_making --risk conservative

run-paper:
	@echo "Starting bot in INT environment (paper trading, real API)"
	@ENVIRONMENT=int uv run python cli/run.py --env int --strategy market_making --risk conservative

run-live:
	@echo ""
	@echo "LIVE TRADING MODE - PRODUCTION - REAL MONEY AT RISK"
	@echo ""
	@read -p "Type 'I UNDERSTAND' to continue: " confirm && [ "$$confirm" = "I UNDERSTAND" ] || (echo "Cancelled" && exit 1)
	@ENVIRONMENT=prod uv run python cli/run.py --env prod --strategy market_making --risk conservative

# Backward-compatible aliases
run-dev: run-mock
run-int: run-paper
run-prod: run-live

backtest:
	@STRATEGY=$${STRATEGY:-market_making}; \
	DAYS=$${DAYS:-30}; \
	INTERVAL=$${INTERVAL:-60}; \
	PAIRS=$${PAIRS:-BTC-EUR,ETH-EUR}; \
	CAPITAL=$${CAPITAL:-10000}; \
	RISK=$${RISK:-conservative}; \
	echo "Environment: $(BACKTEST_ENV) | Strategy: $$STRATEGY | Risk: $$RISK | Days: $$DAYS | Interval: $$INTERVAL min | Pairs: $$PAIRS"; \
	ENVIRONMENT=$(BACKTEST_ENV) uv run python cli/backtest.py --strategy $$STRATEGY --risk $$RISK --days $$DAYS \
		--interval $$INTERVAL --pairs $$PAIRS --capital $$CAPITAL \
		&& echo "Backtest complete — results saved to database (make db-backtests ENV=$(BACKTEST_ENV))" \
		|| echo "Backtest failed - check logs above"

backtest-hf:
	@STRATEGY=$${STRATEGY:-market_making}; \
	DAYS=$${DAYS:-7}; \
	PAIRS=$${PAIRS:-BTC-EUR,ETH-EUR}; \
	CAPITAL=$${CAPITAL:-10000}; \
	RISK=$${RISK:-conservative}; \
	echo ""; \
	echo "============================================================"; \
	echo "  HIGH-FREQUENCY BACKTEST (1-minute candles)"; \
	echo "  Note: Live bot polls every 5s; 1-min candles are the"; \
	echo "        highest granularity available from Revolut X API."; \
	echo "============================================================"; \
	echo "Environment: $(BACKTEST_ENV) | Strategy: $$STRATEGY | Risk: $$RISK | Days: $$DAYS | Interval: 1 min | Pairs: $$PAIRS"; \
	ENVIRONMENT=$(BACKTEST_ENV) uv run python cli/backtest.py --strategy $$STRATEGY --risk $$RISK --days $$DAYS \
		--interval 1 --pairs $$PAIRS --capital $$CAPITAL \
		&& echo "Backtest complete — results saved to database (make db-backtests ENV=$(BACKTEST_ENV))" \
		|| echo "Backtest failed - check logs above"


backtest-compare:
	@echo ""; \
	echo "============================================================"; \
	echo "  STRATEGY COMPARISON BACKTEST ($(BACKTEST_ENV))"; \
	echo "============================================================"; \
	DAYS=$${DAYS:-30}; \
	INTERVAL=$${INTERVAL:-60}; \
	PAIRS=$${PAIRS:-BTC-EUR,ETH-EUR}; \
	CAPITAL=$${CAPITAL:-10000}; \
	RISK=$${RISK:-conservative}; \
	STRATEGIES=$${STRATEGIES:-}; \
	CMD="ENVIRONMENT=$(BACKTEST_ENV) uv run python cli/backtest_compare.py --days $$DAYS --interval $$INTERVAL --pairs $$PAIRS --capital $$CAPITAL --risk $$RISK"; \
	if [ -n "$$STRATEGIES" ]; then CMD="$$CMD --strategies $$STRATEGIES"; fi; \
	eval $$CMD

backtest-matrix:
	@echo ""; \
	echo "============================================================"; \
	echo "  STRATEGY × RISK LEVEL MATRIX BACKTEST ($(BACKTEST_ENV))"; \
	echo "============================================================"; \
	DAYS=$${DAYS:-30}; \
	INTERVAL=$${INTERVAL:-60}; \
	PAIRS=$${PAIRS:-BTC-EUR,ETH-EUR}; \
	CAPITAL=$${CAPITAL:-10000}; \
	ENVIRONMENT=$(BACKTEST_ENV) uv run python cli/backtest_compare.py --days $$DAYS --interval $$INTERVAL \
		--pairs $$PAIRS --capital $$CAPITAL \
		--risk-levels conservative,moderate,aggressive

# ============================================================================
# API Testing (defaults to int — dev uses mock API, so api-* targets skip it)
# ============================================================================

# API_ENV defaults to int (real API).  Override with ENV=prod to target prod.
# Dev is blocked because it uses mock API with no real endpoints.
API_ENV ?= $(if $(filter dev,$(ENV)),int,$(ENV))

define require_real_api
	@if [ "$(API_ENV)" = "dev" ]; then \
		echo "Error: API commands require a real API (ENV=int or ENV=prod)."; \
		echo "Dev environment uses mock API — no real endpoints available."; \
		echo ""; \
		echo "Usage: make $(1) ENV=int"; \
		exit 1; \
	fi
endef

api-ready:
	$(call require_real_api,$@)
	@ENVIRONMENT=$(API_ENV) uv run python cli/api_test.py trade-ready

api-test:
	$(call require_real_api,$@)
	@ENVIRONMENT=$(API_ENV) uv run python cli/api_test.py test

api-balance:
	$(call require_real_api,$@)
	@ENVIRONMENT=$(API_ENV) uv run python cli/api_test.py balance

api-ticker:
	$(call require_real_api,$@)
	@SYMBOL=$${SYMBOL:-BTC-EUR}; \
	ENVIRONMENT=$(API_ENV) uv run python cli/api_test.py ticker --symbol $$SYMBOL

api-tickers:
	$(call require_real_api,$@)
	@SYMBOLS=$${SYMBOLS:-BTC-EUR,ETH-EUR,SOL-EUR}; \
	ENVIRONMENT=$(API_ENV) uv run python cli/api_test.py tickers --symbols $$SYMBOLS

api-candles:
	$(call require_real_api,$@)
	@SYMBOL=$${SYMBOL:-BTC-EUR}; \
	INTERVAL=$${INTERVAL:-60}; \
	LIMIT=$${LIMIT:-10}; \
	ENVIRONMENT=$(API_ENV) uv run python cli/api_test.py candles --symbol $$SYMBOL --interval $$INTERVAL --limit $$LIMIT

api-all-tickers:
	$(call require_real_api,$@)
	@ENVIRONMENT=$(API_ENV) uv run python cli/api_test.py all-tickers

api-currencies:
	$(call require_real_api,$@)
	@ENVIRONMENT=$(API_ENV) uv run python cli/api_test.py currencies

api-currency-pairs:
	$(call require_real_api,$@)
	@ENVIRONMENT=$(API_ENV) uv run python cli/api_test.py currency-pairs

api-last-public-trades:
	$(call require_real_api,$@)
	@ENVIRONMENT=$(API_ENV) uv run python cli/api_test.py last-public-trades

api-order-book:
	$(call require_real_api,$@)
	@if [ -z "$(SYMBOL)" ]; then echo "Usage: make api-order-book SYMBOL=BTC-EUR [DEPTH=20]"; exit 1; fi
	@DEPTH=$${DEPTH:-20}; \
	ENVIRONMENT=$(API_ENV) uv run python cli/api_test.py order-book --symbol $(SYMBOL) --depth $$DEPTH

api-open-orders:
	$(call require_real_api,$@)
	@ARGS=""; \
	[ -n "$(SYMBOL)" ] && ARGS="--symbol $(SYMBOL)"; \
	ENVIRONMENT=$(API_ENV) uv run python cli/api_test.py open-orders $$ARGS

api-historical-orders:
	$(call require_real_api,$@)
	@LIMIT=$${LIMIT:-20}; \
	ARGS="--limit $$LIMIT"; \
	[ -n "$(SYMBOL)" ] && ARGS="$$ARGS --symbol $(SYMBOL)"; \
	ENVIRONMENT=$(API_ENV) uv run python cli/api_test.py historical-orders $$ARGS

api-trades:
	$(call require_real_api,$@)
	@if [ -z "$(SYMBOL)" ]; then echo "Usage: make api-trades SYMBOL=BTC-EUR"; exit 1; fi
	@LIMIT=$${LIMIT:-20}; \
	ENVIRONMENT=$(API_ENV) uv run python cli/api_test.py trades --symbol $(SYMBOL) --limit $$LIMIT

api-public-trades:
	$(call require_real_api,$@)
	@if [ -z "$(SYMBOL)" ]; then echo "Usage: make api-public-trades SYMBOL=BTC-EUR"; exit 1; fi
	@ENVIRONMENT=$(API_ENV) uv run python cli/api_test.py public-trades --symbol $(SYMBOL)

api-order:
	$(call require_real_api,$@)
	@if [ -z "$(ORDER_ID)" ]; then echo "Usage: make api-order ORDER_ID=<uuid>"; exit 1; fi
	@ENVIRONMENT=$(API_ENV) uv run python cli/api_test.py order --order-id $(ORDER_ID)

# ============================================================================
# Code Quality
# ============================================================================

pre-commit-install:
	@uv sync --extra dev --quiet
	@uv run pre-commit install
	@uv run pre-commit install --hook-type commit-msg
	@echo "Pre-commit hooks installed (pre-commit + commit-msg)"

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
	@uv run pyright src/ cli/

security:
	@uv run bandit -c pyproject.toml -r src/ cli/

check: lint format typecheck security test
	@echo "All quality checks passed"

# ============================================================================
# Logs
# ============================================================================

logs:
	@echo "Logs are stored in the encrypted database. Use: make db-stats"

logs-follow:
	@echo "Logs are stored in the encrypted database. Use: make db-stats"

# ============================================================================
# Backup & Restore
# ============================================================================

backup:
	@mkdir -p backups
	@BACKUP_NAME=backup_$$(date +%Y%m%d_%H%M%S); \
	mkdir -p backups/$$BACKUP_NAME; \
	[ -d "data" ] && cp -r data backups/$$BACKUP_NAME/ || true; \
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

DB_CMD = @ENVIRONMENT=$(ENV) uv run python cli/db_manage.py

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
	@ENVIRONMENT=$(ENV) uv run python -c "from src.utils.db_encryption import setup_database_encryption; setup_database_encryption()"

db-encrypt-status:
	@ENVIRONMENT=$(ENV) uv run python -c "from src.utils.db_encryption import DatabaseEncryption; e = DatabaseEncryption(); print('Encryption enabled:', e.is_enabled)"

db-report:
	ENVIRONMENT=$(ENV) uv run python cli/analytics_report.py --days $${DAYS:-30} --output-dir $${DIR:-data/reports}
