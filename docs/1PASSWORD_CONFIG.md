# 1Password Configuration Management

**Store trading bot configuration securely in 1Password alongside your credentials.**

______________________________________________________________________

## Overview

The Revolut Trader bot supports storing configuration settings in 1Password. This allows you to:

- ✅ **Centralize configuration** - Store everything in one secure location
- ✅ **Easy switching** - Change settings without editing code files
- ✅ **Environment-specific configs** - Different settings for different machines
- ✅ **Security** - Keep sensitive settings like live mode encrypted
- ✅ **Auto-initialized** - Setup automatically creates all fields with defaults
- ✅ **Optional** - If not set in 1Password, defaults from `src/config.py` are used

______________________________________________________________________

## Supported Configuration Fields

### Trading Configuration

| Field Name         | Type   | Default           | Description                                                               |
| ------------------ | ------ | ----------------- | ------------------------------------------------------------------------- |
| `TRADING_MODE`     | string | `paper`           | Trading mode: `paper` or `live`                                           |
| `DEFAULT_STRATEGY` | string | `market_making`   | Strategy: `market_making`, `momentum`, `mean_reversion`, `multi_strategy` |
| `RISK_LEVEL`       | string | `conservative`    | Risk level: `conservative`, `moderate`, `aggressive`                      |
| `BASE_CURRENCY`    | string | `EUR`             | Base currency: `EUR`, `USD`, `GBP`                                        |
| `TRADING_PAIRS`    | string | `BTC-EUR,ETH-EUR` | Comma-separated trading pairs                                             |
| `INITIAL_CAPITAL`  | number | `10000.0`         | Initial capital for paper trading                                         |

______________________________________________________________________

## Initial Setup

**Good news!** When you run `make ops` (the initial 1Password setup), all configuration fields are automatically created with default values:

```bash
make ops
```

This creates the following configuration fields in 1Password:

- `TRADING_MODE` = `paper`
- `RISK_LEVEL` = `conservative`
- `BASE_CURRENCY` = `EUR`
- `TRADING_PAIRS` = `BTC-EUR,ETH-EUR`
- `DEFAULT_STRATEGY` = `market_making`
- `INITIAL_CAPITAL` = `10000`

You can view them immediately with:

```bash
make opconfig-show
```

______________________________________________________________________

## How to Modify Configuration in 1Password

### Option 1: Using 1Password CLI (Recommended)

```bash
# Set trading mode to live
op item edit revolut-trader-credentials \
  --vault revolut-trader \
  TRADING_MODE[text]="live"

# Set base currency
op item edit revolut-trader-credentials \
  --vault revolut-trader \
  BASE_CURRENCY[text]="EUR"

# Set trading pairs
op item edit revolut-trader-credentials \
  --vault revolut-trader \
  TRADING_PAIRS[text]="BTC-EUR,ETH-EUR,SOL-EUR"

# Set risk level
op item edit revolut-trader-credentials \
  --vault revolut-trader \
  RISK_LEVEL[text]="moderate"

# Set default strategy
op item edit revolut-trader-credentials \
  --vault revolut-trader \
  DEFAULT_STRATEGY[text]="multi_strategy"

# Set initial capital
op item edit revolut-trader-credentials \
  --vault revolut-trader \
  INITIAL_CAPITAL[text]="50000"
```

### Option 2: Using 1Password App (GUI)

1. Open 1Password app
1. Navigate to `revolut-trader` vault
1. Open `revolut-trader-credentials` item
1. Click "Edit"
1. Add new fields:
   - Click "+ add more"
   - Choose "Text" type (not "Concealed")
   - Set field name (e.g., `TRADING_MODE`)
   - Set value (e.g., `live`)
1. Save

______________________________________________________________________

## Configuration Priority

The bot loads configuration in this order (later overrides earlier):

1. **Code defaults** in `src/config.py`
1. **1Password values** (if present)

```python
# Example flow:
# 1. Code default: trading_mode = "paper"
# 2. 1Password has: TRADING_MODE = "live"
# 3. Final value: trading_mode = "live" ✓
```

______________________________________________________________________

## Examples

### Example 1: Conservative Paper Trading (Default)

**No 1Password config needed - uses code defaults:**

```python
trading_mode = "paper"
risk_level = "conservative"
base_currency = "EUR"
trading_pairs = ["BTC-EUR", "ETH-EUR"]
initial_capital = 10000.0
```

### Example 2: Live Trading Setup

**Set in 1Password:**

```bash
op item edit revolut-trader-credentials --vault revolut-trader \
  TRADING_MODE[text]="live" \
  RISK_LEVEL[text]="moderate" \
  TRADING_PAIRS[text]="BTC-EUR,ETH-EUR,SOL-EUR,MATIC-EUR"
```

**Result:**

```python
trading_mode = "live"  # From 1Password ✓
risk_level = "moderate"  # From 1Password ✓
base_currency = "EUR"  # Default (not in 1Password)
trading_pairs = ["BTC-EUR", "ETH-EUR", "SOL-EUR", "MATIC-EUR"]  # From 1Password ✓
initial_capital = 10000.0  # Default (not in 1Password)
```

### Example 3: High-Risk Aggressive Trading

**Set in 1Password:**

```bash
op item edit revolut-trader-credentials --vault revolut-trader \
  RISK_LEVEL[text]="aggressive" \
  DEFAULT_STRATEGY[text]="momentum" \
  INITIAL_CAPITAL[text]="25000"
```

**Result:**

```python
risk_level = "aggressive"  # From 1Password ✓
default_strategy = "momentum"  # From 1Password ✓
initial_capital = 25000.0  # From 1Password ✓
# All other settings use defaults
```

______________________________________________________________________

## Viewing Current Configuration

### Check what's loaded

```bash
# Run the bot in debug mode to see config
uv run python cli/run.py --help
```

The bot logs will show:

```
2025-12-29 | INFO | Config loaded: trading_mode=live (from 1Password)
2025-12-29 | INFO | Config loaded: base_currency=EUR (default)
```

### View 1Password config values

```bash
# Get all fields from 1Password
op item get revolut-trader-credentials --vault revolut-trader --format json | jq '.fields[] | select(.type=="STRING") | {label, value}'
```

______________________________________________________________________

## Best Practices

### ✅ DO

- **Use text fields** (not concealed) for configuration values
- **Use uppercase** field names (e.g., `TRADING_MODE`)
- **Test in paper mode** before setting `TRADING_MODE=live`
- **Document your config** in your personal notes
- **Use conservative settings** by default

### ❌ DON'T

- **Don't use concealed fields** for config (use text fields)
- **Don't set TRADING_MODE=live** without testing first
- **Don't use invalid values** (they'll be ignored and defaults used)
- **Don't forget to sign in** to 1Password: `eval $(op signin)`

______________________________________________________________________

## Validation

The bot automatically validates all configuration values:

```python
# Valid values
TRADING_MODE: "paper" or "live"
DEFAULT_STRATEGY: "market_making", "momentum", "mean_reversion", "multi_strategy"
RISK_LEVEL: "conservative", "moderate", "aggressive"
BASE_CURRENCY: Any string (e.g., "EUR", "USD", "GBP")
TRADING_PAIRS: Comma-separated symbols (e.g., "BTC-EUR,ETH-EUR")
INITIAL_CAPITAL: Any positive number

# Invalid values are ignored and defaults are used
TRADING_MODE: "invalid" → Falls back to "paper" ✓
RISK_LEVEL: "extreme" → Falls back to "conservative" ✓
```

______________________________________________________________________

## Safety Features

### Automatic Safeguards

1. **Validation** - Invalid values ignored, defaults used
1. **Graceful degradation** - If 1Password unavailable, uses defaults
1. **No errors** - Config loading never crashes the bot
1. **Logging** - All config sources logged for transparency

### Paper Mode Protection

Even if you set `TRADING_MODE=live` in 1Password, the bot will:

1. ⚠️ **Warn you** before starting
1. ⚠️ **Verify credentials** are valid
1. ⚠️ **Check account balance** before trading
1. ⚠️ **Send Telegram notification** about live mode

______________________________________________________________________

## Troubleshooting

### Config not loading from 1Password

**Issue:** Settings from 1Password are not being used

**Solutions:**

1. **Check 1Password sign-in:**

   ```bash
   op account list
   # If not signed in:
   eval $(op signin)
   ```

1. **Verify field names are correct:**

   ```bash
   op item get revolut-trader-credentials --vault revolut-trader --fields TRADING_MODE
   ```

1. **Check field type is "text" not "concealed"**

1. **Look at bot logs:**

   ```
   DEBUG | Config TRADING_MODE not in 1Password, using default: paper
   ```

### Invalid value ignored

**Issue:** Set a config value but bot uses default

**Cause:** Value is invalid for that field type

**Solution:**

```bash
# Check what you set
op item get revolut-trader-credentials --vault revolut-trader --fields RISK_LEVEL

# Must be one of: conservative, moderate, aggressive (lowercase)
op item edit revolut-trader-credentials --vault revolut-trader \
  RISK_LEVEL[text]="moderate"
```

______________________________________________________________________

## Migration from Code Defaults

### Step 1: Review Current Settings

Check `src/config.py` for your current defaults.

### Step 2: Decide What to Move

Only move settings that:

- Change frequently
- Differ between environments
- Are sensitive (like `TRADING_MODE`)

### Step 3: Set in 1Password

```bash
# Example: Move to live trading
op item edit revolut-trader-credentials --vault revolut-trader \
  TRADING_MODE[text]="live" \
  RISK_LEVEL[text]="moderate"
```

### Step 4: Test

```bash
# Run in paper mode first
make run-paper

# Check logs to verify config loaded from 1Password
grep "Config loaded" logs/trading.log
```

______________________________________________________________________

## Security Considerations

### Why Store Config in 1Password?

1. **Centralized security** - One encrypted vault
1. **Access control** - 1Password manages permissions
1. **Audit trail** - 1Password logs all access
1. **No plaintext files** - No `.env` files on disk
1. **Easy rotation** - Change settings without code changes

### What to Store

**Store in 1Password:**

- Trading mode (paper/live)
- Risk settings for production
- Capital amounts
- Live trading pairs

**Keep in code (defaults):**

- Development settings
- Test configurations
- Documentation examples

______________________________________________________________________

## Quick Reference

```bash
# View current config from 1Password
op item get revolut-trader-credentials --vault revolut-trader

# Set trading mode to live
op item edit revolut-trader-credentials --vault revolut-trader TRADING_MODE[text]="live"

# Set multiple values at once
op item edit revolut-trader-credentials --vault revolut-trader \
  TRADING_MODE[text]="live" \
  RISK_LEVEL[text]="moderate" \
  BASE_CURRENCY[text]="EUR" \
  TRADING_PAIRS[text]="BTC-EUR,ETH-EUR,SOL-EUR"

# Remove a config value (fall back to default)
op item edit revolut-trader-credentials --vault revolut-trader TRADING_MODE[delete]

# Check what's being used
make run-paper  # Check logs for "Config loaded from 1Password"
```

______________________________________________________________________

## Summary

✅ **Auto-initialized** - `make ops` creates all config fields with defaults
✅ **1Password config is optional** - Defaults always work
✅ **Override any setting** - Fine-grained control
✅ **Secure and centralized** - Everything in one vault
✅ **Environment-specific** - Different configs per machine
✅ **Safe** - Invalid values ignored, no crashes
✅ **Transparent** - All sources logged

**Setup once, modify as needed! 🚀**
