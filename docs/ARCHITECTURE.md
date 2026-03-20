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
        │   ├── MomentumStrategy       — EMA(12/26) + RSI
        │   ├── MarketMakingStrategy   — bid/ask spread
        │   ├── MeanReversionStrategy  — Bollinger Bands
        │   └── MultiStrategy          — weighted voting across all 3
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
