# Backtesting Guide

Test your trading strategies on historical data before risking real money.

## Overview

The backtesting system allows you to:
- **Validate strategies** using real historical market data from Revolut X
- **Measure performance** with comprehensive metrics (win rate, profit factor, Sharpe ratio, etc.)
- **Test different configurations** (risk levels, trading pairs, time periods)
- **Export results** to JSON for further analysis

## Quick Start

### Basic Backtest

```bash
# Test market making strategy on BTC-USD for 30 days
python backtest.py --strategy market_making --pairs BTC-USD --days 30
```

### Advanced Examples

```bash
# Test momentum strategy with moderate risk on multiple pairs
python backtest.py --strategy momentum --risk moderate \
  --pairs BTC-USD,ETH-USD,SOL-USD --days 60

# Use 1-hour candles for 90 days and save results
python backtest.py --strategy mean_reversion \
  --interval 60 --days 90 \
  --output ./results/backtest_$(date +%Y%m%d).json

# Test with custom initial capital
python backtest.py --strategy multi_strategy \
  --capital 50000 --days 180
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
                  Example: BTC-USD,ETH-USD,SOL-USD
                  Default: BTC-USD,ETH-USD

--days, -d        Number of days of historical data
                  Default: 30

--interval, -i    Candle interval in minutes
                  Choices: 5, 15, 30, 60, 240, 1440
                  Default: 60 (1 hour)

--capital, -c     Initial capital in USD
                  Default: 10000

--output, -o      Save results to JSON file (optional)

--log-level, -l   Logging verbosity
                  Choices: DEBUG, INFO, WARNING, ERROR
                  Default: INFO
```

## Performance Metrics

The backtest provides comprehensive performance analysis:

### Core Metrics
- **Initial Capital**: Starting balance
- **Final Capital**: Ending balance after all trades
- **Total P&L**: Net profit/loss in USD
- **Return %**: Percentage return on initial capital

### Trade Statistics
- **Total Trades**: Number of completed round-trip trades
- **Winning Trades**: Trades that closed with profit
- **Losing Trades**: Trades that closed with loss
- **Win Rate**: Percentage of winning trades

### Risk Metrics
- **Profit Factor**: Gross profit / Gross loss (higher is better)
- **Max Drawdown**: Largest peak-to-trough decline
- **Sharpe Ratio**: Risk-adjusted return

## Example Output

```
============================================================
BACKTEST RESULTS
============================================================
Initial Capital:    $10,000.00
Final Capital:      $10,847.23
Total P&L:          $847.23
Return:             8.47%
Total Trades:       45
Winning Trades:     28
Losing Trades:      17
Win Rate:           62.22%
Profit Factor:      1.89
Max Drawdown:       $342.15
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

## Exporting Results

Save results for further analysis:

```bash
python backtest.py --strategy momentum \
  --output ./results/momentum_backtest.json
```

The JSON file includes:
- Configuration settings
- Performance metrics
- Individual trade details
- Timestamp

### Example JSON Output

```json
{
  "timestamp": "2025-12-27T18:45:00.000Z",
  "config": {
    "strategy": "momentum",
    "risk_level": "moderate",
    "symbols": ["BTC-USD", "ETH-USD"],
    "days": 30,
    "interval": 60,
    "initial_capital": 10000.0
  },
  "results": {
    "final_capital": 10847.23,
    "total_pnl": 847.23,
    "return_pct": 8.47,
    "total_trades": 45,
    "winning_trades": 28,
    "losing_trades": 17,
    "win_rate": 62.22,
    "profit_factor": 1.89,
    "max_drawdown": 342.15
  },
  "trades": [...]
}
```

## Best Practices

### 1. Test Multiple Time Periods
```bash
# Test different periods
python backtest.py --days 30    # Recent performance
python backtest.py --days 90    # Quarterly
python backtest.py --days 180   # Semi-annual
python backtest.py --days 365   # Annual
```

### 2. Compare Different Strategies
```bash
# Run all strategies on same data
for strategy in market_making momentum mean_reversion multi_strategy; do
  python backtest.py --strategy $strategy --days 90 \
    --output "./results/${strategy}_90d.json"
done
```

### 3. Test Different Risk Levels
```bash
# Compare risk levels
python backtest.py --risk conservative --output ./results/conservative.json
python backtest.py --risk moderate --output ./results/moderate.json
python backtest.py --risk aggressive --output ./results/aggressive.json
```

### 4. Optimize Timeframes
```bash
# Test different candle intervals
python backtest.py --interval 15   # 15-minute candles
python backtest.py --interval 60   # 1-hour candles
python backtest.py --interval 240  # 4-hour candles
```

## Limitations & Considerations

### Data Limitations
- **Maximum History**: Limited by Revolut X API (typically 100 candles per request)
- **Candle Gaps**: Some periods may have missing data
- **Slippage Not Modeled**: Assumes instant fills at exact prices

### Execution Differences
- **No Market Impact**: Assumes orders don't move the market
- **Perfect Fills**: All orders execute immediately
- **No Latency**: Instant data and execution
- **No Fees**: Trading fees not included (add manually if needed)

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
**Solution**: Check your API credentials and ensure the symbol is correct

### API Endpoint Not Found
```
ERROR | Failed to fetch candles: 404 Not Found
```
**Solution**: The candles endpoint may use a different path. Check the implementation notes.

### Insufficient Data
```
WARNING | Retrieved only 50 candles
```
**Solution**: The API may have limited historical data. Try a shorter time period or different interval.

## Next Steps

After backtesting:

1. **Analyze Results**: Review metrics and trade details
2. **Optimize Parameters**: Adjust strategy settings if needed
3. **Paper Trade**: Test with live data in paper mode
4. **Live Trade**: Only after consistent positive results

```bash
# After successful backtest, test in paper mode
python run.py --mode paper --strategy momentum --risk moderate
```

## Additional Resources

- [Strategy Documentation](../src/strategies/)
- [Risk Management Guide](../src/risk_management/)
- [API Client Documentation](../src/api/)
- [Implementation Notes](./IMPLEMENTATION_NOTES_2025-12-27.md)

---

**Note**: Past performance does not guarantee future results. Always start with paper trading before risking real capital.
