# Architecture

## Component Hierarchy

```
cli/run.py  (entry point)
    └── TradingBot  (src/bot.py)  — orchestrator
        ├── RevolutAPIClient  (src/api/client.py)
        │   └── RateLimiter  (src/utils/rate_limiter.py)
        ├── RiskManager  (src/risk_management/risk_manager.py)
        ├── OrderExecutor  (src/execution/executor.py)
        │   ├── RevolutAPIClient
        │   └── RiskManager
        ├── BaseStrategy  (src/strategies/)
        │   ├── MomentumStrategy         — EMA(12/26) + RSI
        │   ├── MarketMakingStrategy     — bid/ask spread
        │   ├── MeanReversionStrategy    — Bollinger Bands
        │   ├── BreakoutStrategy         — rolling high/low + RSI
        │   ├── RangeReversionStrategy   — 24h range position + RSI
        │   └── MultiStrategy            — weighted voting across all
        ├── DatabasePersistence  (src/utils/db_persistence.py)
        │   ├── SQLAlchemy ORM  (src/models/db.py)
        │   └── DatabaseEncryption  (src/utils/db_encryption.py)
        └── Config  (src/config.py)
            └── 1Password  (src/utils/onepassword.py)
```

______________________________________________________________________

## Main Data Flow (every 60s)

```
run_trading_loop()
    └── [parallel for each symbol]
        ├── RevolutAPIClient.get_ticker()       → MarketData
        ├── strategy.analyze()                  → Signal (BUY/SELL/HOLD)
        ├── executor.execute_signal()
        │   ├── RiskManager.calculate_position_size()
        │   ├── RiskManager.validate_order()    → two-layer check
        │   └── Paper: simulate fill
        │       Live:  API.create_order()
        └── persistence.save_trade()            → encrypted SQLite
    └── save_portfolio_snapshot()
    └── RiskManager.update_daily_pnl()          → suspend if limit hit

stop()  (graceful shutdown on Ctrl-C or error)
    └── executor.graceful_shutdown(trailing_stop_pct, max_wait_seconds)
        ├── Phase 1: cancel_all_orders()           → cancel unmonitored orders
        ├── Phase 2: for each position (unrealized_pnl < 0):
        │   └── close immediately via market order
        ├── Phase 3: for each position (unrealized_pnl ≥ 0):
        │   ├── if SHUTDOWN_TRAILING_STOP_PCT set:
        │   │   ├── poll get_ticker() every 2s
        │   │   ├── track high-watermark, trailing_stop = watermark × (1 - pct%)
        │   │   ├── close when price ≤ trailing_stop OR timeout expires
        │   └── else: close immediately via market order
        └── return ShutdownSummary             → bot updates cash balance
            GUARANTEE: executor.positions == {} after return
    └── persistence.save_data()                → final snapshot to DB
    └── persistence.end_session()              → record final metrics
```

______________________________________________________________________

## Key Files

| Layer        | File                                  | Responsibility                           |
| ------------ | ------------------------------------- | ---------------------------------------- |
| Entry        | `cli/run.py`                          | CLI args, starts async loop              |
| Orchestrator | `src/bot.py`                          | Ties all components together             |
| Config       | `src/config.py`                       | Pydantic settings, loaded from 1Password |
| API          | `src/api/client.py`                   | 17 Revolut X endpoints, Ed25519 auth     |
| Risk         | `src/risk_management/risk_manager.py` | Position sizing, limits, SL/TP           |
| Execution    | `src/execution/executor.py`           | Order lifecycle, position tracking       |
| Strategies   | `src/strategies/`                     | Signal generation                        |
| Models       | `src/models/domain.py`                | Order, Position, Signal, MarketData      |
| DB models    | `src/models/db.py`                    | SQLAlchemy ORM (SQLite, WAL mode)        |
| Persistence  | `src/utils/db_persistence.py`         | All CRUD operations                      |
| Encryption   | `src/utils/db_encryption.py`          | Fernet encryption, key in 1Password      |
| Indicators   | `src/utils/indicators.py`             | SMA/EMA/RSI/BB — all O(1) incremental    |

______________________________________________________________________

## Safety Layers

1. **Two-layer order validation** — sanity check (absolute limits) → risk check (portfolio-relative)
1. **Daily loss limit** — suspends all trading if P&L threshold hit
1. **Stop-loss / take-profit** — auto-closes positions at price levels
1. **No leverage** — order value ≤ portfolio value enforced
1. **Rate limiting** — 60 API calls/min
1. **Encrypted DB** — sensitive fields (trading pairs, log messages) encrypted with Fernet key from 1Password
1. **No plaintext files** — logs go to encrypted SQLite, never to disk
1. **Graceful shutdown** — cancels all pending orders, closes losing positions immediately, and closes profitable positions via trailing stop (or immediately); **guarantee: no bot-opened position is left open after shutdown** (EUR → trade → EUR contract)
1. **Pre-existing crypto protection** — SELL guard in `execute_signal` blocks any sell for a symbol the bot did not open; pre-existing crypto is never touched
1. **Currency mismatch validation** — all trading pairs must end with `-{BASE_CURRENCY}`; bot refuses to start if there is a mismatch
1. **Capital cap** — optional `MAX_CAPITAL` in 1Password limits how much the bot can trade with, regardless of account balance
1. **Shutdown trailing stop** — optional `SHUTDOWN_TRAILING_STOP_PCT` and `SHUTDOWN_MAX_WAIT_SECONDS` in 1Password control how long the bot waits for the best exit on profitable positions before force-closing
