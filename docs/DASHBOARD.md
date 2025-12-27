# Trading Dashboard

Interactive web dashboard for visualizing backtest results, monitoring live trading, and analyzing performance.

## Features

### 📊 Backtest Results Viewer
- Interactive equity curves
- Profit & Loss charts
- Performance metrics display
- Trade history table
- Compare different backtests

### 🔬 Strategy Comparison
- Side-by-side strategy comparison
- Performance metrics comparison
- Visual charts comparing returns
- Filter by risk level, time period

### 🔴 Live Monitor (Coming Soon)
- Real-time portfolio tracking
- Open positions display
- Live P&L updates
- Recent trades feed

## Quick Start

### 1. Launch Dashboard

```bash
streamlit run dashboard.py
```

The dashboard will open in your browser at `http://localhost:8501`

### 2. Generate Backtest Data

Run backtests with the `--output` flag to save results:

```bash
# Run a backtest and save results
python backtest.py \
  --strategy multi_strategy \
  --risk moderate \
  --days 30 \
  --output ./results/multi_strategy.json
```

### 3. View Results

The dashboard automatically loads all JSON files from the `./results/` directory.

## Dashboard Pages

### Backtest Results

**What it shows:**
- Strategy configuration (strategy type, risk level, days, interval)
- Performance metrics (P&L, return %, win rate, profit factor, max drawdown)
- Equity curve chart (portfolio value over time)
- P&L chart (cumulative and per-trade profit/loss)
- Trade history table (all executed trades)

**How to use:**
1. Select a backtest file from the sidebar dropdown
2. View performance metrics at the top
3. Analyze equity curve and P&L charts
4. Review individual trades in the table

### Strategy Comparison

**What it shows:**
- Comparison table of all backtests
- Side-by-side performance metrics
- Returns comparison chart

**How to use:**
1. Run multiple backtests with different strategies/parameters
2. Navigate to "Strategy Comparison" page
3. Compare metrics across all runs
4. Identify best-performing strategy

### Live Monitor

**What it shows (Placeholder):**
- Real-time portfolio value
- Open positions
- Today's P&L
- Recent trades

**Status:** Coming in future update

## Examples

### Compare Multiple Strategies

```bash
# Run backtests for all strategies
for strategy in market_making momentum mean_reversion multi_strategy; do
  python backtest.py \
    --strategy $strategy \
    --risk moderate \
    --days 30 \
    --output "./results/${strategy}_30d.json"
done

# Launch dashboard
streamlit run dashboard.py
# Go to "Strategy Comparison" page
```

### Test Different Risk Levels

```bash
# Test same strategy with different risk levels
for risk in conservative moderate aggressive; do
  python backtest.py \
    --strategy momentum \
    --risk $risk \
    --days 30 \
    --output "./results/momentum_${risk}.json"
done

# Launch dashboard
streamlit run dashboard.py
```

### Analyze Different Time Periods

```bash
# Test different time periods
for days in 7 14 30 60 90; do
  python backtest.py \
    --strategy multi_strategy \
    --days $days \
    --output "./results/multi_${days}d.json"
done

# Launch dashboard
streamlit run dashboard.py
```

## Dashboard Features

### Interactive Charts

**Equity Curve:**
- Shows portfolio value over time
- Hover to see exact values
- Zoom and pan controls
- Fill area shows growth visually

**P&L Chart:**
- Dual-axis chart
- Line: Cumulative P&L
- Bars: Individual trade P&L
- Green bars = winning trades
- Red bars = losing trades

### Performance Metrics

**Key Metrics Displayed:**
- **Total P&L**: Net profit/loss
- **Return %**: Percentage return on capital
- **Total Trades**: Number of completed trades
- **Win Rate**: Percentage of winning trades
- **Profit Factor**: Gross profit / Gross loss
- **Max Drawdown**: Largest peak-to-trough decline

### Trade History

**Columns:**
- Timestamp: When trade was executed
- Symbol: Trading pair (BTC-USD, ETH-USD)
- Side: BUY or SELL
- Quantity: Amount traded
- Price: Execution price
- P&L: Profit/loss on trade

## Keyboard Shortcuts

While the dashboard is running:

- `Ctrl+C` in terminal: Stop dashboard
- Browser `F5` or `Ctrl+R`: Refresh page
- Sidebar "Refresh Data" button: Reload backtest files

## Troubleshooting

### Dashboard shows "No backtest results found"

**Solution:** Run a backtest with `--output` flag:
```bash
python backtest.py --strategy momentum --output ./results/test.json
```

### Dashboard doesn't update with new results

**Solution:** Click "Refresh Data" button in sidebar or refresh browser page

### Charts not displaying

**Solution:** Ensure JSON file contains `equity_curve` and `trades` data

### Port 8501 already in use

**Solution:** Stop other Streamlit apps or use different port:
```bash
streamlit run dashboard.py --server.port 8502
```

## Advanced Usage

### Custom Port

```bash
streamlit run dashboard.py --server.port 8080
```

### Open in Specific Browser

```bash
streamlit run dashboard.py --browser.serverAddress localhost
```

### Run in Background

```bash
nohup streamlit run dashboard.py &
```

### Network Access

To access from other devices on your network:

```bash
streamlit run dashboard.py --server.address 0.0.0.0
```

Then access at `http://YOUR_IP:8501`

## Future Enhancements

Planned features for live monitoring:

- [ ] Real-time portfolio value updates
- [ ] Live position tracking
- [ ] Order execution feed
- [ ] Strategy performance metrics
- [ ] Risk metrics monitoring
- [ ] Alert notifications
- [ ] Export charts as images
- [ ] PDF report generation
- [ ] Historical vs current comparison
- [ ] Machine learning insights

## Best Practices

1. **Organize Results**: Use descriptive filenames
   ```bash
   ./results/momentum_moderate_30d_btc.json
   ./results/market_making_conservative_7d.json
   ```

2. **Regular Cleanup**: Remove old backtest files to keep dashboard fast
   ```bash
   rm ./results/old_*.json
   ```

3. **Compare Fairly**: Use same time period and pairs when comparing strategies

4. **Document Parameters**: Include strategy/risk/period in filename

## Tips

- **Use filters**: Sidebar allows filtering backtest results
- **Hover charts**: Hover over charts for detailed values
- **Download data**: Right-click charts to save as image
- **Multi-window**: Open multiple browser tabs for side-by-side comparison

## Support

For issues or feature requests:
- Check logs: `tail -f logs/dashboard.log`
- Review backtest JSON files for data issues
- Ensure all dependencies installed: `uv pip install streamlit plotly pandas`

---

**Dashboard Version**: 1.0
**Last Updated**: December 27, 2025
