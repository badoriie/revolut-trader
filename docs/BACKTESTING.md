# Backtesting Guide

Test your trading strategies on historical data before risking real money.

## Overview

The backtesting system allows you to:

- **Validate strategies** using real historical market data from Revolut X
- **Measure performance** with comprehensive metrics (win rate, profit factor, Sharpe ratio, max drawdown, fees)
- **Test different configurations** (risk levels, trading pairs, time periods)
- **Store results securely** in the encrypted SQLite database

Results are persisted **exclusively to the encrypted database** — no plaintext JSON or log files are written.
Use `make db-backtests` to view results and `make db-export-csv` to export when needed.

## Quick Start

```bash
# Test market making strategy on BTC-EUR for 30 days
make backtest STRATEGY=market_making DAYS=30

# Test momentum strategy with moderate risk
make backtest STRATEGY=momentum DAYS=60

# High-frequency backtest with 1-minute candles (closest to live 5s polling)
make backtest-hf STRATEGY=breakout DAYS=7

# View stored results
make db-backtests

# Export to CSV for spreadsheet analysis
make db-export-csv
```

## High-Frequency Backtesting

The live bot polls the Revolut X API every 5 seconds to make trading decisions based on the latest ticker data. However, the API's historical candle data is only available at specific intervals (1, 5, 15, 30, 60, 240, 1440+ minutes).

To simulate the live bot's behavior as closely as possible, use **1-minute candles** — the highest granularity available:

```bash
make backtest-hf                           # 1-min candles, 7 days default
make backtest-hf STRATEGY=breakout DAYS=14 # specific strategy and period
```

**Important differences between live and backtest:**

| Aspect               | Live Bot                                     | Backtest (1-min candles)                                 |
| -------------------- | -------------------------------------------- | -------------------------------------------------------- |
| **Data granularity** | 5-second polling, latest ticker              | 1-minute OHLCV candles (highest available from API)      |
| **Decision points**  | Every 5 seconds                              | Every 1 minute (at candle close)                         |
| **Intra-candle**     | Sees all price movements within 1-min window | Only sees open, high, low, close, volume summary         |
| **Stop-loss / TP**   | Checked every 5 seconds against latest price | Checked against candle high/low (intra-bar simulation)   |
| **Fill realism**     | Real order book, actual slippage             | Simulated bid/ask spread (0.1%), conservative fill rules |
| **Cost simulation**  | Real fees (0.09% taker)                      | Same fee (0.09% taker) deducted per fill                 |

**When to use high-frequency backtesting:**

- Testing strategies that rely on rapid price movements (e.g., breakout, momentum)
- Evaluating short-term performance (7-14 days)
- Validating stop-loss behavior with higher precision
- Comparing backtest results closely to live paper trading runs

**Trade-offs:**

- **More data, slower execution**: 1-minute candles generate ~1,440 bars per day (vs. 24 for hourly). Backtests take longer and consume more API quota.
- **API limits**: Revolut X limits candle requests to 1,000 candles per call. The engine automatically paginates, but many requests may be needed for long periods.
- **Not a perfect match**: 5-second polling can react to micro-movements that don't appear in 1-minute candle summaries. Backtest results remain an approximation.

For longer-term strategy validation (30+ days), use hourly candles (`INTERVAL=60`) or the default settings. For short-term / high-frequency validation, use `make backtest-hf`.

## Command Line Options

```
--strategy, -s    Trading strategy to test
                  Choices: market_making, momentum, mean_reversion, multi_strategy, breakout, range_reversion
                  Default: market_making

--risk, -r        Risk management level
                  Choices: conservative, moderate, aggressive
                  Default: conservative

--pairs, -p       Comma-separated trading pairs
                  Example: BTC-EUR,ETH-EUR,SOL-EUR
                  Default: BTC-EUR,ETH-EUR

--days, -d        Number of days of historical data
                  Default: 30

--interval, -i    Candle interval in minutes
                  Choices: 1, 5, 15, 30, 60, 240, 1440
                  Default: 60 (1 hour)
                  Note: Use 1 for highest granularity (closest to live 5s polling)

--capital, -c     Initial capital in EUR
                  Default: 10000

--log-level, -l   Logging verbosity
                  Choices: DEBUG, INFO, WARNING, ERROR
                  Default: INFO
```

## Performance Metrics

The backtest provides comprehensive performance analysis:

### Core Metrics

- **Initial Capital**: Starting balance
- **Final Capital**: Ending balance after all trades
- **Total P&L**: Net profit/loss in EUR
- **Return %**: Percentage return on initial capital

### Trade Statistics

- **Total Trades**: Number of completed round-trip trades
- **Winning Trades**: Trades that closed with profit
- **Losing Trades**: Trades that closed with loss
- **Win Rate**: Percentage of winning trades

### Risk Metrics

- **Profit Factor**: Gross profit / Gross loss (higher is better)
- **Max Drawdown**: Largest peak-to-trough decline (running O(1) calculation)
- **Sharpe Ratio**: Risk-adjusted return (annualised)
- **Total Fees**: Taker fees paid (0.09% per fill)

## Simulation Realism

The engine models real trading costs and execution behaviour to match live trading:

- **Taker fee**: 0.09% deducted per fill
- **Slippage**: BUY fills at ask price, SELL fills at bid price (0.1% spread — matches real Revolut X bid-ask spreads)
- **Signal strength filter**: Weak signals are discarded using the same per-strategy thresholds as live trading (e.g. momentum requires ≥ 0.6)
- **Per-strategy risk parameters**: Stop-loss and take-profit levels use the same strategy-specific overrides as live trading (e.g. market_making uses 0.5% SL, breakout uses 3.0% SL)
- **Intra-bar SL/TP**: Stop-loss and take-profit are checked against the candle's low/high, not just the closing price. This mirrors the live bot's frequent polling — a position that would have been stopped out mid-candle is correctly closed even when the close price is outside the SL/TP range. When both SL and TP are triggered by the same candle (whipsaw), the stop-loss wins (conservative/worst-case).
- **Per-strategy order type**: Momentum and breakout strategies use MARKET orders (fills immediately at ask/bid). All other strategies use LIMIT orders (fills only when the candle's price range includes the limit price). This mirrors `_STRATEGY_ORDER_TYPE` in the live executor and prevents over-optimistic fill assumptions for patient strategies.
- **Pagination**: Fetches up to 1,000 candles per API request, chunked across the date range
- **Stop-loss / Take-profit**: Checked against candle high/low before signal processing

## Example Output

```
============================================================
BACKTEST RESULTS
============================================================
Strategy:           momentum
Initial Capital:    €10,000.00
Final Capital:      €10,847.23
Total P&L:          €847.23
Return:             8.47%
Total Trades:       45
Winning Trades:     28
Losing Trades:      17
Win Rate:           62.22%
Profit Factor:      1.89
Max Drawdown:       €342.15
Sharpe Ratio:       1.24
Total Fees:         €38.50
============================================================
```

## Understanding Results

### Win Rate

- **> 50%**: Strategy has positive edge
- **40-50%**: Acceptable with good profit factor
- **< 40%**: Needs improvement

### Profit Factor

- **> 2.0**: Excellent
- **1.5-2.0**: Good
- **1.0-1.5**: Break-even to marginal
- **< 1.0**: Losing strategy

### Sharpe Ratio

- **> 1.5**: Strong risk-adjusted return
- **1.0-1.5**: Acceptable
- **< 1.0**: Insufficient return for risk taken

### Max Drawdown

- Lower is better
- Should be acceptable relative to returns
- Consider your risk tolerance

## Interpreting Different Strategies

### Market Making

- **Expected**: High trade volume, lower profit per trade
- **Good Win Rate**: 55-65%
- **Profit Factor**: 1.3-1.8
- **Works Best**: In ranging markets with tight spreads

### Momentum

- **Expected**: Moderate trade volume, larger wins
- **Good Win Rate**: 45-55%
- **Profit Factor**: 1.8-2.5
- **Works Best**: In trending markets

### Mean Reversion

- **Expected**: High trade frequency, quick profits
- **Good Win Rate**: 60-70%
- **Profit Factor**: 1.5-2.0
- **Works Best**: In sideways/oscillating markets

### Breakout

- **Expected**: Fewer trades, larger moves
- **Good Win Rate**: 40-50%
- **Profit Factor**: 2.0-3.0
- **Works Best**: In volatile markets with clear consolidation patterns

### Range Reversion

- **Expected**: Frequent trades near daily extremes
- **Good Win Rate**: 55-65%
- **Profit Factor**: 1.4-2.0
- **Works Best**: In ranging markets with well-defined 24h high/low

### Multi-Strategy

- **Expected**: Balanced performance
- **Good Win Rate**: 55-60%
- **Profit Factor**: 1.6-2.2
- **Works Best**: In varying market conditions

## Viewing and Exporting Results

All results are stored in the encrypted database:

```bash
# View last 10 backtest runs
make db-backtests

# Export all data to dated CSV files in data/exports/
make db-export-csv

# Analytics summary
make db-analytics
```

## Best Practices

### 1. Test Multiple Time Periods

```bash
make backtest STRATEGY=momentum DAYS=30    # Recent performance
make backtest STRATEGY=momentum DAYS=90    # Quarterly
make backtest STRATEGY=momentum DAYS=180   # Semi-annual
```

### 2. Compare Different Strategies

```bash
for strategy in market_making momentum mean_reversion multi_strategy breakout range_reversion; do
  make backtest STRATEGY=$strategy DAYS=90
done
make db-backtests LIMIT=20
```

### 3. Test Different Risk Levels

```bash
make backtest STRATEGY=momentum DAYS=60
# Then change risk via: make opconfig-set KEY=RISK_LEVEL VALUE=aggressive
make backtest STRATEGY=momentum DAYS=60
```

### 4. Optimize Timeframes

```bash
# Test different candle intervals
uv run python cli/backtest.py --interval 15   # 15-minute candles
uv run python cli/backtest.py --interval 60   # 1-hour candles
uv run python cli/backtest.py --interval 240  # 4-hour candles
```

## Limitations & Considerations

### Data Limitations

- **Maximum per request**: 1,000 candles (engine paginates automatically across date ranges)
- **Candle gaps**: Some periods may have missing data
- **Market impact**: Assumes orders don't move the market

### Execution Differences

- **No latency**: Instant data and execution
- **Partial fills**: Not modelled — orders always fill fully

### Overfitting Risk

- Don't over-optimize to historical data
- Test on multiple time periods
- Use out-of-sample testing
- Consider walk-forward analysis

## Troubleshooting

### No Historical Data Available

```
ERROR | No historical data available
```

**Solution**: Check your API credentials and ensure the symbol is correct (`make api-test`).

### Invalid Interval

```
ValueError: Invalid interval
```

**Solution**: Use one of the supported intervals: 5, 15, 30, 60, 240, 1440.

### Insufficient Data

```
WARNING | Retrieved only 50 candles
```

**Solution**: The API may have limited historical data for that period. Try a shorter time window or a larger interval.

## Next Steps

After backtesting:

1. **Review results**: `make db-backtests`
1. **Export for analysis**: `make db-export-csv`
1. **Paper trade**: Test with live data in paper mode — `make run-paper`
1. **Live trade**: Only after consistent positive results — `make run-live`

______________________________________________________________________

**Note**: Past performance does not guarantee future results. Always start with paper trading before risking real capital.
