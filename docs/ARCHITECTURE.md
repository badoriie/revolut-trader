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

## Main Data Flow (strategy-dependent interval: 5s / 10s / 15s)

```
run_trading_loop()
    └── RevolutAPIClient.get_tickers()          → dict[symbol, MarketData]  (1 batch call)
    └── [parallel for each symbol]
        ├── MarketData (from batch)             → pre-fetched, no per-symbol call
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

## Per-Strategy Optimizations

Every strategy ships with tuned defaults across four dimensions. All are applied automatically; none require manual configuration.

### Trading Interval

How often the main loop runs. Faster strategies poll more aggressively:

| Strategy        | Interval | Rationale                                   |
| --------------- | -------- | ------------------------------------------- |
| Market Making   | 5s       | Spread opportunities vanish in seconds      |
| Breakout        | 5s       | Price explosions need immediate reaction    |
| Momentum        | 10s      | Trend signals need a few seconds to confirm |
| Multi-Strategy  | 10s      | Consensus voting already smooths noise      |
| Mean Reversion  | 15s      | Reversion unfolds over minutes, not seconds |
| Range Reversion | 15s      | Same as mean reversion — patience pays      |

Override with `--interval N` or `ENVIRONMENT=int uv run python cli/run.py --interval 3`.

### Order Type

Speed-critical strategies use MARKET orders; patient strategies use LIMIT:

| Strategy        | Order Type | Rationale                                   |
| --------------- | ---------- | ------------------------------------------- |
| Market Making   | LIMIT      | Must control the exact spread capture price |
| Momentum        | MARKET     | Speed matters more than price precision     |
| Breakout        | MARKET     | Miss the breakout = miss the trade          |
| Mean Reversion  | LIMIT      | Wait for the fill at the reversion price    |
| Range Reversion | LIMIT      | Same logic as mean reversion                |
| Multi-Strategy  | LIMIT      | Consensus signals are not time-critical     |

### Minimum Signal Strength

Confidence floor [0.0–1.0] below which signals are discarded before any order is placed:

| Strategy        | Min Strength | Rationale                                       |
| --------------- | ------------ | ----------------------------------------------- |
| Market Making   | 0.30         | Small spreads still profitable at low certainty |
| Momentum        | 0.60         | Trend signals need moderate conviction          |
| Breakout        | 0.70         | Breakout false-positives are costly — be sure   |
| Mean Reversion  | 0.50         | Default: moderate confidence required           |
| Range Reversion | 0.50         | Default: moderate confidence required           |
| Multi-Strategy  | 0.55         | Consensus already filters noise slightly        |

### Stop-Loss / Take-Profit Overrides

Applied on top of the risk-level baseline. Reflect each strategy's typical holding period and volatility tolerance. **Position sizing (`max_position_size_pct`) is always controlled by the risk level** — this is intentional so that conservative/moderate/aggressive produce meaningfully different trade sizes in the backtest matrix and in live trading.

| Strategy        | Stop Loss    | Take Profit  | Notes                                |
| --------------- | ------------ | ------------ | ------------------------------------ |
| Market Making   | 0.5%         | 0.3%         | Tight: short-lived spread trades     |
| Momentum        | 2.5%         | 4.0%         | Wider: trends need room to develop   |
| Breakout        | 3.0%         | 5.0%         | Widest: breakouts have large targets |
| Mean Reversion  | 1.0%         | 1.5%         | Tight: if no revert quickly, exit    |
| Range Reversion | 1.0%         | 1.5%         | Same as mean reversion               |
| Multi-Strategy  | *(baseline)* | *(baseline)* | Sub-strategy mix varies too much     |

`*(baseline)*` = value comes from the selected risk level (Conservative / Moderate / Aggressive). Position size always comes from the risk level for every strategy.

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
1. **Rate limiting** — 200 API calls/min (API allows 1000/min; 200 leaves a 5× safety buffer)
1. **Encrypted DB** — sensitive fields (trading pairs, log messages) encrypted with Fernet key from 1Password
1. **No plaintext files** — logs go to encrypted SQLite, never to disk
1. **Graceful shutdown** — cancels all pending orders, closes losing positions immediately, and closes profitable positions via trailing stop (or immediately); **guarantee: no bot-opened position is left open after shutdown** (EUR → trade → EUR contract)
1. **Pre-existing crypto protection** — SELL guard in `execute_signal` blocks any sell for a symbol the bot did not open; pre-existing crypto is never touched
1. **Currency mismatch validation** — all trading pairs must end with `-{BASE_CURRENCY}`; bot refuses to start if there is a mismatch
1. **Capital cap** — optional `MAX_CAPITAL` in 1Password limits how much the bot can trade with, regardless of account balance
1. **Shutdown trailing stop** — optional `SHUTDOWN_TRAILING_STOP_PCT` and `SHUTDOWN_MAX_WAIT_SECONDS` in 1Password control how long the bot waits for the best exit on profitable positions before force-closing
