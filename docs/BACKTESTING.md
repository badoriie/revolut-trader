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

# View stored results
make db-backtests

# Export to CSV for spreadsheet analysis
make db-export-csv
```

## Command Line Options

```
--strategy, -s    Trading strategy to test
                  Choices: market_making, momentum, mean_reversion, multi_strategy
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
                  Choices: 5, 15, 30, 60, 240, 1440
                  Default: 60 (1 hour)

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

The engine models real trading costs:

- **Taker fee**: 0.09% deducted per fill
- **Slippage**: BUY fills at ask price, SELL fills at bid price (0.3% spread)
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
for strategy in market_making momentum mean_reversion multi_strategy; do
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
