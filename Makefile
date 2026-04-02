.PHONY: help setup install clean deep-clean test lint format typecheck security check pre-commit pre-commit-install run telegram backtest backtest-hf backtest-compare backtest-matrix logs ops opshow opstatus opdelete opconfig-init opconfig-set opconfig-show opconfig-delete backup restore db db-stats db-analytics db-backtests db-export db-export-csv db-encrypt-setup db-encrypt-status db-report api-ready api-test telegram-test

# ============================================================================
# Environment — auto-detected from git context, or explicit override
#   tagged commit → prod  (real API, live trading)
#   main branch   → int   (real API, paper trading)
#   other branch  → dev   (mock API, no credentials)
# ============================================================================

_GIT_DIR    := $(shell git rev-parse --git-dir 2>/dev/null)
_GIT_BRANCH := $(shell git rev-parse --abbrev-ref HEAD 2>/dev/null)
_GIT_TAG    := $(shell git describe --exact-match HEAD 2>/dev/null)
# No git repo (e.g. downloaded release zip) → prod
_DEFAULT_ENV := $(if $(_GIT_DIR),$(if $(_GIT_TAG),prod,$(if $(filter main,$(_GIT_BRANCH)),int,dev)),prod)

ENV ?= $(_DEFAULT_ENV)
BACKTEST_ENV ?= $(_DEFAULT_ENV)

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
	@echo "  make run               - Run the bot (env auto-detected)"
	@echo "                           STRATEGY=... RISK=... PAIRS=... INTERVAL=... MODE=live"
	@echo "  make telegram          - Start Telegram Control Plane (always-on process)"
	@echo "                           Control bot via Telegram: /run /stop /status /balance /report /help"
	@echo "  make backtest          - Backtest one strategy (env auto-detected from branch)"
	@echo "                           STRATEGY=... DAYS=... RISK=... INTERVAL=... PAIRS=..."
	@echo "  make backtest-hf       - High-frequency backtest (1-minute candles, closest to live 5s polling)"
	@echo "                           STRATEGY=... DAYS=... RISK=... PAIRS=..."
	@echo "  make backtest-compare  - Compare all strategies side-by-side (DAYS=... RISK=...)"
	@echo "  make backtest-matrix   - All strategies x all risk levels matrix"
	@echo ""
	@echo "API Testing (defaults to int — use ENV=prod for production):"
	@echo "  make api-test          - Test authenticated connection"
	@echo "  make api-ready         - Check API permissions (view + trade)"
	@echo "  make telegram-test     - Verify Telegram is configured"
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
	@echo "Logs (uses ENV for DB file selection):"
	@echo "  make logs              - View recent logs from database (LIMIT=50 LEVEL=...)"
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
	@echo "  2. make run              (mock API by default on feature branches — no API key needed)"
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
					"TELEGRAM_BOT_TOKEN[concealed]=<add-telegram-bot-token>" \
					>/dev/null && echo "  $$CREDS: created (dev uses mock API — no API key needed)"; \
			else \
				op item create \
					--category "Secure Note" \
					--vault $(OP_VAULT) \
					--title $$CREDS \
					"REVOLUT_API_KEY[concealed]=<add-your-$$env-api-key>" \
					"TELEGRAM_BOT_TOKEN[concealed]=<add-telegram-bot-token>" \
					>/dev/null && echo "  $$CREDS: created"; \
			fi; \
		fi; \
		op item get $$CREDS --vault $(OP_VAULT) --fields TELEGRAM_BOT_TOKEN >/dev/null 2>&1 \
			|| { op item edit $$CREDS --vault $(OP_VAULT) "TELEGRAM_BOT_TOKEN[concealed]=<add-telegram-bot-token>" >/dev/null \
			     && echo "  TELEGRAM_BOT_TOKEN: placeholder added"; }; \
		if [ "$$env" != "dev" ]; then \
			op item get $$CREDS --vault $(OP_VAULT) --fields REVOLUT_API_KEY >/dev/null 2>&1 \
				|| { op item edit $$CREDS --vault $(OP_VAULT) "REVOLUT_API_KEY[concealed]=<add-your-$$env-api-key>" >/dev/null \
				     && echo "  REVOLUT_API_KEY: placeholder added"; }; \
		fi; \
		if op item get $$CREDS --vault $(OP_VAULT) --fields DATABASE_ENCRYPTION_KEY >/dev/null 2>&1; then \
			echo "  DATABASE_ENCRYPTION_KEY: exists (preserving to protect encrypted data)"; \
		else \
			ENCRYPTION_KEY=$$(uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"); \
			op item edit $$CREDS --vault $(OP_VAULT) "DATABASE_ENCRYPTION_KEY[concealed]=$$ENCRYPTION_KEY" >/dev/null \
				&& echo "  DATABASE_ENCRYPTION_KEY: generated and stored"; \
		fi; \
		if op item get $$CONFIG --vault $(OP_VAULT) >/dev/null 2>&1; then \
			echo "  $$CONFIG: exists"; \
		else \
			if [ "$$env" = "prod" ]; then \
				op item create \
					--category "Secure Note" \
					--vault $(OP_VAULT) \
					--title $$CONFIG \
					"TRADING_MODE[text]=paper" \
					"RISK_LEVEL[text]=conservative" \
					"BASE_CURRENCY[text]=EUR" \
					"TRADING_PAIRS[text]=BTC-EUR,ETH-EUR" \
					"DEFAULT_STRATEGY[text]=market_making" \
					"INITIAL_CAPITAL[text]=10000" \
					"MAX_CAPITAL[text]=<optional-max-capital-eur>" \
					"SHUTDOWN_TRAILING_STOP_PCT[text]=<optional-e.g-0.5>" \
					"SHUTDOWN_MAX_WAIT_SECONDS[text]=<optional-e.g-120>" \
					"LOG_LEVEL[text]=<optional-e.g-INFO>" \
					"INTERVAL[text]=<optional-trading-loop-interval-seconds>" \
					"BACKTEST_DAYS[text]=<optional-e.g-30>" \
					"BACKTEST_INTERVAL[text]=<optional-e.g-60>" \
					"MAKER_FEE_PCT[text]=<optional-e.g-0>" \
					"TAKER_FEE_PCT[text]=<optional-e.g-0.0009>" \
					"MAX_ORDER_VALUE[text]=<optional-e.g-10000>" \
					"MIN_ORDER_VALUE[text]=<optional-e.g-10>" \
					"TELEGRAM_CHAT_ID[text]=<add-telegram-chat-id>" \
					>/dev/null && echo "  $$CONFIG: created (prod defaults to paper mode)"; \
				echo "  Note: TRADING_MODE=paper (safe default). Set 'live' only when ready."; \
			else \
				op item create \
					--category "Secure Note" \
					--vault $(OP_VAULT) \
					--title $$CONFIG \
					"TRADING_MODE[text]=paper" \
					"RISK_LEVEL[text]=conservative" \
					"BASE_CURRENCY[text]=EUR" \
					"TRADING_PAIRS[text]=BTC-EUR,ETH-EUR" \
					"DEFAULT_STRATEGY[text]=market_making" \
					"INITIAL_CAPITAL[text]=10000" \
					"MAX_CAPITAL[text]=<optional-max-capital-eur>" \
					"SHUTDOWN_TRAILING_STOP_PCT[text]=<optional-e.g-0.5>" \
					"SHUTDOWN_MAX_WAIT_SECONDS[text]=<optional-e.g-120>" \
					"LOG_LEVEL[text]=<optional-e.g-INFO>" \
					"INTERVAL[text]=<optional-trading-loop-interval-seconds>" \
					"BACKTEST_DAYS[text]=<optional-e.g-30>" \
					"BACKTEST_INTERVAL[text]=<optional-e.g-60>" \
					"MAKER_FEE_PCT[text]=<optional-e.g-0>" \
					"TAKER_FEE_PCT[text]=<optional-e.g-0.0009>" \
					"MAX_ORDER_VALUE[text]=<optional-e.g-10000>" \
					"MIN_ORDER_VALUE[text]=<optional-e.g-10>" \
					"TELEGRAM_CHAT_ID[text]=<add-telegram-chat-id>" \
					>/dev/null && echo "  $$CONFIG: created with safe defaults"; \
			fi; \
		fi; \
		op item get $$CONFIG --vault $(OP_VAULT) --fields TRADING_MODE >/dev/null 2>&1 \
			|| { op item edit $$CONFIG --vault $(OP_VAULT) "TRADING_MODE[text]=paper" >/dev/null \
			     && echo "  TRADING_MODE: set to paper (safe default)"; }; \
		op item get $$CONFIG --vault $(OP_VAULT) --fields RISK_LEVEL >/dev/null 2>&1 \
			|| { op item edit $$CONFIG --vault $(OP_VAULT) "RISK_LEVEL[text]=conservative" >/dev/null \
			     && echo "  RISK_LEVEL: added (required, default conservative)"; }; \
		op item get $$CONFIG --vault $(OP_VAULT) --fields BASE_CURRENCY >/dev/null 2>&1 \
			|| { op item edit $$CONFIG --vault $(OP_VAULT) "BASE_CURRENCY[text]=EUR" >/dev/null \
			     && echo "  BASE_CURRENCY: added (required, default EUR)"; }; \
		op item get $$CONFIG --vault $(OP_VAULT) --fields TRADING_PAIRS >/dev/null 2>&1 \
			|| { op item edit $$CONFIG --vault $(OP_VAULT) "TRADING_PAIRS[text]=BTC-EUR,ETH-EUR" >/dev/null \
			     && echo "  TRADING_PAIRS: added (required, default BTC-EUR,ETH-EUR)"; }; \
		op item get $$CONFIG --vault $(OP_VAULT) --fields DEFAULT_STRATEGY >/dev/null 2>&1 \
			|| { op item edit $$CONFIG --vault $(OP_VAULT) "DEFAULT_STRATEGY[text]=market_making" >/dev/null \
			     && echo "  DEFAULT_STRATEGY: added (required, default market_making)"; }; \
		op item get $$CONFIG --vault $(OP_VAULT) --fields INITIAL_CAPITAL >/dev/null 2>&1 \
			|| { op item edit $$CONFIG --vault $(OP_VAULT) "INITIAL_CAPITAL[text]=10000" >/dev/null \
			     && echo "  INITIAL_CAPITAL: added (required for paper mode, default 10000)"; }; \
		op item get $$CONFIG --vault $(OP_VAULT) --fields MAX_CAPITAL >/dev/null 2>&1 \
			|| { op item edit $$CONFIG --vault $(OP_VAULT) "MAX_CAPITAL[text]=<optional-max-capital-eur>" >/dev/null \
			     && echo "  MAX_CAPITAL: placeholder added"; }; \
		op item get $$CONFIG --vault $(OP_VAULT) --fields SHUTDOWN_TRAILING_STOP_PCT >/dev/null 2>&1 \
			|| { op item edit $$CONFIG --vault $(OP_VAULT) "SHUTDOWN_TRAILING_STOP_PCT[text]=<optional-e.g-0.5>" >/dev/null \
			     && echo "  SHUTDOWN_TRAILING_STOP_PCT: placeholder added"; }; \
		op item get $$CONFIG --vault $(OP_VAULT) --fields SHUTDOWN_MAX_WAIT_SECONDS >/dev/null 2>&1 \
			|| { op item edit $$CONFIG --vault $(OP_VAULT) "SHUTDOWN_MAX_WAIT_SECONDS[text]=<optional-e.g-120>" >/dev/null \
			     && echo "  SHUTDOWN_MAX_WAIT_SECONDS: placeholder added"; }; \
		op item get $$CONFIG --vault $(OP_VAULT) --fields LOG_LEVEL >/dev/null 2>&1 \
			|| { op item edit $$CONFIG --vault $(OP_VAULT) "LOG_LEVEL[text]=<optional-e.g-INFO>" >/dev/null \
			     && echo "  LOG_LEVEL: placeholder added"; }; \
		op item get $$CONFIG --vault $(OP_VAULT) --fields INTERVAL >/dev/null 2>&1 \
			|| { op item edit $$CONFIG --vault $(OP_VAULT) "INTERVAL[text]=<optional-trading-loop-interval-seconds>" >/dev/null \
			     && echo "  INTERVAL: placeholder added"; }; \
		op item get $$CONFIG --vault $(OP_VAULT) --fields BACKTEST_DAYS >/dev/null 2>&1 \
			|| { op item edit $$CONFIG --vault $(OP_VAULT) "BACKTEST_DAYS[text]=<optional-e.g-30>" >/dev/null \
			     && echo "  BACKTEST_DAYS: placeholder added"; }; \
		op item get $$CONFIG --vault $(OP_VAULT) --fields BACKTEST_INTERVAL >/dev/null 2>&1 \
			|| { op item edit $$CONFIG --vault $(OP_VAULT) "BACKTEST_INTERVAL[text]=<optional-e.g-60>" >/dev/null \
			     && echo "  BACKTEST_INTERVAL: placeholder added"; }; \
		op item get $$CONFIG --vault $(OP_VAULT) --fields TELEGRAM_CHAT_ID >/dev/null 2>&1 \
			|| { op item edit $$CONFIG --vault $(OP_VAULT) "TELEGRAM_CHAT_ID[text]=<add-telegram-chat-id>" >/dev/null \
			     && echo "  TELEGRAM_CHAT_ID: placeholder added"; }; \
		op item get $$CONFIG --vault $(OP_VAULT) --fields MAKER_FEE_PCT >/dev/null 2>&1 \
			|| { op item edit $$CONFIG --vault $(OP_VAULT) "MAKER_FEE_PCT[text]=<optional-e.g-0>" >/dev/null \
			     && echo "  MAKER_FEE_PCT: placeholder added"; }; \
		op item get $$CONFIG --vault $(OP_VAULT) --fields TAKER_FEE_PCT >/dev/null 2>&1 \
			|| { op item edit $$CONFIG --vault $(OP_VAULT) "TAKER_FEE_PCT[text]=<optional-e.g-0.0009>" >/dev/null \
			     && echo "  TAKER_FEE_PCT: placeholder added"; }; \
		op item get $$CONFIG --vault $(OP_VAULT) --fields MAX_ORDER_VALUE >/dev/null 2>&1 \
			|| { op item edit $$CONFIG --vault $(OP_VAULT) "MAX_ORDER_VALUE[text]=<optional-e.g-10000>" >/dev/null \
			     && echo "  MAX_ORDER_VALUE: placeholder added"; }; \
		op item get $$CONFIG --vault $(OP_VAULT) --fields MIN_ORDER_VALUE >/dev/null 2>&1 \
			|| { op item edit $$CONFIG --vault $(OP_VAULT) "MIN_ORDER_VALUE[text]=<optional-e.g-10>" >/dev/null \
			     && echo "  MIN_ORDER_VALUE: placeholder added"; }; \
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
	@# --- Create/update per-risk-level config items (no env suffix — shared across envs) ---
	@echo "Setting up risk level config items..."
	@for risk_info in \
		"conservative:1.5:3.0:1.5:2.5:3" \
		"moderate:3.0:5.0:2.5:4.0:5" \
		"aggressive:5.0:10.0:4.0:7.0:8"; \
	do \
		level=$$(echo $$risk_info | cut -d: -f1); \
		max_pos=$$(echo $$risk_info | cut -d: -f2); \
		max_loss=$$(echo $$risk_info | cut -d: -f3); \
		sl=$$(echo $$risk_info | cut -d: -f4); \
		tp=$$(echo $$risk_info | cut -d: -f5); \
		max_positions=$$(echo $$risk_info | cut -d: -f6); \
		item="revolut-trader-risk-$$level"; \
		if op item get $$item --vault $(OP_VAULT) >/dev/null 2>&1; then \
			echo "  $$item: exists"; \
		else \
			op item create --category "Secure Note" --vault $(OP_VAULT) --title $$item \
				"MAX_POSITION_SIZE_PCT[text]=$$max_pos" \
				"MAX_DAILY_LOSS_PCT[text]=$$max_loss" \
				"STOP_LOSS_PCT[text]=$$sl" \
				"TAKE_PROFIT_PCT[text]=$$tp" \
				"MAX_OPEN_POSITIONS[text]=$$max_positions" \
				>/dev/null && echo "  $$item: created with defaults"; \
		fi; \
		op item get $$item --vault $(OP_VAULT) --fields MAX_POSITION_SIZE_PCT >/dev/null 2>&1 \
			|| { op item edit $$item --vault $(OP_VAULT) "MAX_POSITION_SIZE_PCT[text]=$$max_pos" >/dev/null \
			     && echo "  $$level MAX_POSITION_SIZE_PCT: placeholder added"; }; \
		op item get $$item --vault $(OP_VAULT) --fields MAX_DAILY_LOSS_PCT >/dev/null 2>&1 \
			|| { op item edit $$item --vault $(OP_VAULT) "MAX_DAILY_LOSS_PCT[text]=$$max_loss" >/dev/null \
			     && echo "  $$level MAX_DAILY_LOSS_PCT: placeholder added"; }; \
		op item get $$item --vault $(OP_VAULT) --fields STOP_LOSS_PCT >/dev/null 2>&1 \
			|| { op item edit $$item --vault $(OP_VAULT) "STOP_LOSS_PCT[text]=$$sl" >/dev/null \
			     && echo "  $$level STOP_LOSS_PCT: placeholder added"; }; \
		op item get $$item --vault $(OP_VAULT) --fields TAKE_PROFIT_PCT >/dev/null 2>&1 \
			|| { op item edit $$item --vault $(OP_VAULT) "TAKE_PROFIT_PCT[text]=$$tp" >/dev/null \
			     && echo "  $$level TAKE_PROFIT_PCT: placeholder added"; }; \
		op item get $$item --vault $(OP_VAULT) --fields MAX_OPEN_POSITIONS >/dev/null 2>&1 \
			|| { op item edit $$item --vault $(OP_VAULT) "MAX_OPEN_POSITIONS[text]=$$max_positions" >/dev/null \
			     && echo "  $$level MAX_OPEN_POSITIONS: placeholder added"; }; \
		echo ""; \
	done
	@echo ""
	@# --- Create/update per-strategy config items (no env suffix — shared across envs) ---
	@echo "Setting up strategy config items..."
	@for strategy_info in \
		"market_making:5:0.3:limit:0.5:0.3" \
		"momentum:10:0.6:market:2.5:4.0" \
		"breakout:5:0.7:market:3.0:5.0" \
		"mean_reversion:15:0.5:limit:1.0:1.5" \
		"range_reversion:15:0.5:limit:1.0:1.5" \
		"multi_strategy:10:0.55:limit::"; \
	do \
		name=$$(echo $$strategy_info | cut -d: -f1); \
		interval=$$(echo $$strategy_info | cut -d: -f2); \
		min_signal=$$(echo $$strategy_info | cut -d: -f3); \
		order_type=$$(echo $$strategy_info | cut -d: -f4); \
		stop_loss=$$(echo $$strategy_info | cut -d: -f5); \
		take_profit=$$(echo $$strategy_info | cut -d: -f6); \
		item="revolut-trader-strategy-$$name"; \
		if op item get $$item --vault $(OP_VAULT) >/dev/null 2>&1; then \
			echo "  $$item: exists"; \
		else \
			fields="INTERVAL[text]=$$interval MIN_SIGNAL_STRENGTH[text]=$$min_signal ORDER_TYPE[text]=$$order_type"; \
			if [ -n "$$stop_loss" ]; then fields="$$fields STOP_LOSS_PCT[text]=$$stop_loss"; fi; \
			if [ -n "$$take_profit" ]; then fields="$$fields TAKE_PROFIT_PCT[text]=$$take_profit"; fi; \
			op item create --category "Secure Note" --vault $(OP_VAULT) --title $$item $$fields >/dev/null \
				&& echo "  $$item: created with defaults"; \
		fi; \
		op item get $$item --vault $(OP_VAULT) --fields INTERVAL >/dev/null 2>&1 \
			|| { op item edit $$item --vault $(OP_VAULT) "INTERVAL[text]=$$interval" >/dev/null \
			     && echo "  $$name INTERVAL: placeholder added"; }; \
		op item get $$item --vault $(OP_VAULT) --fields MIN_SIGNAL_STRENGTH >/dev/null 2>&1 \
			|| { op item edit $$item --vault $(OP_VAULT) "MIN_SIGNAL_STRENGTH[text]=$$min_signal" >/dev/null \
			     && echo "  $$name MIN_SIGNAL_STRENGTH: placeholder added"; }; \
		op item get $$item --vault $(OP_VAULT) --fields ORDER_TYPE >/dev/null 2>&1 \
			|| { op item edit $$item --vault $(OP_VAULT) "ORDER_TYPE[text]=$$order_type" >/dev/null \
			     && echo "  $$name ORDER_TYPE: placeholder added"; }; \
		if [ -n "$$stop_loss" ]; then \
			op item get $$item --vault $(OP_VAULT) --fields STOP_LOSS_PCT >/dev/null 2>&1 \
				|| { op item edit $$item --vault $(OP_VAULT) "STOP_LOSS_PCT[text]=$$stop_loss" >/dev/null \
				     && echo "  $$name STOP_LOSS_PCT: placeholder added"; }; \
		fi; \
		if [ -n "$$take_profit" ]; then \
			op item get $$item --vault $(OP_VAULT) --fields TAKE_PROFIT_PCT >/dev/null 2>&1 \
				|| { op item edit $$item --vault $(OP_VAULT) "TAKE_PROFIT_PCT[text]=$$take_profit" >/dev/null \
				     && echo "  $$name TAKE_PROFIT_PCT: placeholder added"; }; \
		fi; \
		echo ""; \
	done
	@echo ""
	@echo "Creating directories..."
	@mkdir -p data
	@echo "  data/ created"
	@echo ""
	@echo "Installing dependencies..."
	@uv sync --extra dev --extra analytics
	@echo ""
	@echo "Installing pre-commit hooks..."
	@uv run pre-commit install
	@uv run pre-commit install --hook-type commit-msg
	@echo "  Pre-commit hooks installed (pre-commit + commit-msg)"
	@echo ""
	@echo "=== Setup complete! ==="
	@echo ""
	@echo "Next steps:"
	@echo "  1. Run in mock mode:    make run  (uses mock API on feature branches — no API key needed)"
	@echo "  2. Add API keys for int/prod: make ops ENV=int  (and ENV=prod)"
	@echo "  3. View configuration:  make opconfig-show ENV=dev"

install:
	@echo "Installing dependencies with uv..."
	@uv sync --extra dev --extra analytics
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
	@echo "Updating credentials in 1Password ($(OP_VAULT)/$(OP_CREDS))"
	@echo ""
	@if [ "$(ENV)" = "dev" ]; then \
		echo "Dev environment uses mock API — no Revolut API key needed."; \
	else \
		printf "Revolut API Key (press Enter to skip): "; read api_key; \
		if [ -n "$$api_key" ]; then \
			op item edit $(OP_CREDS) --vault $(OP_VAULT) "REVOLUT_API_KEY[concealed]=$$api_key" >/dev/null \
				&& echo "  REVOLUT_API_KEY stored" || echo "  Failed to store REVOLUT_API_KEY"; \
		fi; \
	fi
	@echo ""
	@printf "Telegram Bot Token (optional — press Enter to skip): "; read tg_token; \
	if [ -n "$$tg_token" ]; then \
		op item edit $(OP_CREDS) --vault $(OP_VAULT) "TELEGRAM_BOT_TOKEN[concealed]=$$tg_token" >/dev/null \
			&& echo "  TELEGRAM_BOT_TOKEN stored" || echo "  Failed to store TELEGRAM_BOT_TOKEN"; \
	fi
	@echo ""
	@echo "Done. Run 'make opshow' to verify."

opshow:
	@op whoami >/dev/null 2>&1 || { echo "Error: 1Password not authenticated. Set OP_SERVICE_ACCOUNT_TOKEN."; exit 1; }
	@echo "=== Credentials ($(OP_CREDS)) ==="
	@if [ "$(ENV)" = "dev" ]; then \
		echo "  (dev uses mock API — no API credentials needed)"; \
	else \
		for field in REVOLUT_API_KEY REVOLUT_PRIVATE_KEY REVOLUT_PUBLIC_KEY TELEGRAM_BOT_TOKEN; do \
			value=$$(op item get $(OP_CREDS) --vault $(OP_VAULT) --fields $$field --reveal 2>/dev/null) || continue; \
			len=$$(expr length "$$value"); \
			if [ $$len -gt 100 ]; then masked="<set, $$len chars>"; \
			elif [ $$len -gt 8 ]; then masked="$${value:0:8}..."; \
			else masked="$${value:0:4}..."; fi; \
			printf "  %-25s = %s\n" "$$field" "$$masked"; \
		done; \
	fi
	@echo ""
	@echo "=== Configuration ($(OP_CONFIG)) ==="
	@echo "  TRADING_MODE              = (derived: dev/int → paper, prod → live)"
	@for field in RISK_LEVEL BASE_CURRENCY TRADING_PAIRS DEFAULT_STRATEGY INITIAL_CAPITAL MAX_CAPITAL SHUTDOWN_TRAILING_STOP_PCT SHUTDOWN_MAX_WAIT_SECONDS LOG_LEVEL INTERVAL BACKTEST_DAYS BACKTEST_INTERVAL MAKER_FEE_PCT TAKER_FEE_PCT MAX_ORDER_VALUE MIN_ORDER_VALUE TELEGRAM_CHAT_ID; do \
		value=$$(op item get $(OP_CONFIG) --vault $(OP_VAULT) --fields $$field 2>/dev/null) || continue; \
		printf "  %-25s = %s\n" "$$field" "$$value"; \
	done
	@echo ""
	@echo "=== Risk level configs ==="
	@for level in conservative moderate aggressive; do \
		item="revolut-trader-risk-$$level"; \
		echo "  [$$level]"; \
		for field in MAX_POSITION_SIZE_PCT MAX_DAILY_LOSS_PCT STOP_LOSS_PCT TAKE_PROFIT_PCT MAX_OPEN_POSITIONS; do \
			value=$$(op item get $$item --vault $(OP_VAULT) --fields $$field 2>/dev/null) || continue; \
			printf "    %-22s = %s\n" "$$field" "$$value"; \
		done; \
	done
	@echo ""
	@echo "=== Strategy configs ==="
	@for name in market_making momentum breakout mean_reversion range_reversion multi_strategy; do \
		item="revolut-trader-strategy-$$name"; \
		echo "  [$$name]"; \
		for field in INTERVAL MIN_SIGNAL_STRENGTH ORDER_TYPE STOP_LOSS_PCT TAKE_PROFIT_PCT SPREAD_THRESHOLD INVENTORY_TARGET FAST_PERIOD SLOW_PERIOD RSI_PERIOD RSI_OVERBOUGHT RSI_OVERSOLD LOOKBACK_PERIOD NUM_STD_DEV MIN_DEVIATION BREAKOUT_THRESHOLD BUY_ZONE SELL_ZONE RSI_CONFIRMATION_OVERSOLD RSI_CONFIRMATION_OVERBOUGHT MIN_RANGE_PCT MIN_CONSENSUS WEIGHT_MOMENTUM WEIGHT_BREAKOUT WEIGHT_MARKET_MAKING WEIGHT_MEAN_REVERSION WEIGHT_RANGE_REVERSION; do \
			value=$$(op item get $$item --vault $(OP_VAULT) --fields $$field 2>/dev/null) || continue; \
			printf "    %-32s = %s\n" "$$field" "$$value"; \
		done; \
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
	@for key in RISK_LEVEL BASE_CURRENCY TRADING_PAIRS DEFAULT_STRATEGY INITIAL_CAPITAL MAX_CAPITAL SHUTDOWN_TRAILING_STOP_PCT SHUTDOWN_MAX_WAIT_SECONDS TELEGRAM_CHAT_ID; do \
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

run:
	@STRATEGY=$${STRATEGY:-market_making}; \
	RISK=$${RISK:-conservative}; \
	echo "Starting bot (env: $(ENV) | strategy: $$STRATEGY | risk: $$RISK)"; \
	CMD="ENVIRONMENT=$(ENV) uv run python cli/run.py --env $(ENV) --strategy $$STRATEGY --risk $$RISK"; \
	[ -n "$${PAIRS:-}" ] && CMD="$$CMD --pairs $$PAIRS"; \
	[ -n "$${INTERVAL:-}" ] && CMD="$$CMD --interval $$INTERVAL"; \
	[ -n "$${MODE:-}" ] && CMD="$$CMD --mode $$MODE"; \
	eval $$CMD

telegram:
	@echo "Starting Telegram Control Plane (env: $(ENV))…"
	@echo "Control the bot via Telegram: /run /stop /status /balance /report /help"
	ENVIRONMENT=$(ENV) uv run python cli/telegram_control.py --env $(ENV)

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

telegram-test:
	@ENVIRONMENT=$(ENV) uv run revt telegram test

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
	@ENVIRONMENT=$(ENV) uv run python cli/view_logs.py --limit $${LIMIT:-50} $${LEVEL:+--level $$LEVEL} $${SESSION:+--session $$SESSION}

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
