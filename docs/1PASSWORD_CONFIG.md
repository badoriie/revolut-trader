# 1Password Configuration Management

**Store trading bot configuration securely in 1Password - REQUIRED for all config.**

______________________________________________________________________

## Overview

The Revolut Trader bot **requires** all configuration to be stored in 1Password. This ensures:

- ✅ **Safety first** - No accidental use of hardcoded defaults
- ✅ **Explicit configuration** - All settings are visible and intentional
- ✅ **Centralized management** - One secure source of truth
- ✅ **Easy switching** - Change settings without editing code
- ✅ **Environment-specific configs** - Different settings per machine
- ✅ **Auto-initialized** - `make setup` creates all fields with safe defaults

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

## Initial Setup (REQUIRED)

**The configuration item is automatically created during setup.**

When you run `make setup`, a separate 1Password item `revolut-trader-config` is created with safe defaults:

```bash
make setup
```

This creates the **required** configuration item with these values:

- `TRADING_MODE` = `paper` (safe simulation mode)
- `RISK_LEVEL` = `conservative` (minimal risk)
- `BASE_CURRENCY` = `EUR`
- `TRADING_PAIRS` = `BTC-EUR,ETH-EUR`
- `DEFAULT_STRATEGY` = `market_making`
- `INITIAL_CAPITAL` = `10000`

**These values are REQUIRED.** The bot will not start without a valid 1Password config item.

View your configuration:

```bash
make opconfig-show
```

If the config item is missing, create it:

```bash
make opconfig-init
```

______________________________________________________________________

## How to Modify Configuration in 1Password

### Option 1: Using Makefile Commands (Recommended)

```bash
# Set trading mode to live
make opconfig-set KEY=TRADING_MODE VALUE=live

# Set base currency
make opconfig-set KEY=BASE_CURRENCY VALUE=EUR

# Set trading pairs
make opconfig-set KEY=TRADING_PAIRS VALUE="BTC-EUR,ETH-EUR,SOL-EUR"

# Set risk level
make opconfig-set KEY=RISK_LEVEL VALUE=moderate

# Set default strategy
make opconfig-set KEY=DEFAULT_STRATEGY VALUE=multi_strategy

# Set initial capital
make opconfig-set KEY=INITIAL_CAPITAL VALUE=50000
```

### Option 2: Using 1Password CLI Directly

```bash
# Set trading mode to live
op item edit revolut-trader-config \
  --vault revolut-trader \
  TRADING_MODE[text]="live"

# Set multiple values at once
op item edit revolut-trader-config \
  --vault revolut-trader \
  TRADING_MODE[text]="live" \
  RISK_LEVEL[text]="moderate" \
  BASE_CURRENCY[text]="EUR"
```

### Option 3: Using 1Password App (GUI)

1. Open 1Password app
1. Navigate to `revolut-trader` vault
1. Open `revolut-trader-config` item
1. Click "Edit"
1. Modify existing fields:
   - Find the field (e.g., `TRADING_MODE`)
   - Change the value (e.g., from `paper` to `live`)
1. Save

______________________________________________________________________

## Configuration Loading

**All configuration is loaded from 1Password - there are no code defaults.**

The bot requires these fields in the `revolut-trader-config` item:

- TRADING_MODE
- RISK_LEVEL
- BASE_CURRENCY
- TRADING_PAIRS
- DEFAULT_STRATEGY
- INITIAL_CAPITAL

If any field is missing, the bot will raise a clear error:

```python
RuntimeError: TRADING_MODE not found in 1Password config.
Run: make opconfig-init
```

This ensures you **always know** what configuration is being used.

______________________________________________________________________

## Examples

### Example 1: Conservative Paper Trading (Default Setup)

**After `make setup`, 1Password is pre-populated with these defaults:**

```python
trading_mode = "paper"  # From 1Password ✓
risk_level = "conservative"  # From 1Password ✓
base_currency = "EUR"  # From 1Password ✓
trading_pairs = ["BTC-EUR", "ETH-EUR"]  # From 1Password ✓
initial_capital = 10000.0  # From 1Password ✓
```

### Example 2: Live Trading Setup

**Set in 1Password:**

```bash
make opconfig-set KEY=TRADING_MODE VALUE=live
make opconfig-set KEY=RISK_LEVEL VALUE=moderate
make opconfig-set KEY=TRADING_PAIRS VALUE="BTC-EUR,ETH-EUR,SOL-EUR,MATIC-EUR"
```

**Result:**

```python
trading_mode = "live"  # From 1Password ✓
risk_level = "moderate"  # From 1Password ✓
base_currency = "EUR"  # From 1Password (unchanged)
trading_pairs = ["BTC-EUR", "ETH-EUR", "SOL-EUR", "MATIC-EUR"]  # From 1Password ✓
initial_capital = 10000.0  # From 1Password (unchanged)
```

### Example 3: High-Risk Aggressive Trading

**Set in 1Password:**

```bash
make opconfig-set KEY=RISK_LEVEL VALUE=aggressive
make opconfig-set KEY=DEFAULT_STRATEGY VALUE=momentum
make opconfig-set KEY=INITIAL_CAPITAL VALUE=25000
```

**Result:**

```python
risk_level = "aggressive"  # From 1Password ✓
default_strategy = "momentum"  # From 1Password ✓
initial_capital = 25000.0  # From 1Password ✓
# Other settings remain whatever is stored in 1Password (unchanged)
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
2025-12-29 | INFO | Config loaded: base_currency=EUR (from 1Password)
```

### View 1Password config values

```bash
# View all config using make
make opconfig-show

# Or get all fields from 1Password directly
op item get revolut-trader-config --vault revolut-trader --format json | jq '.fields[] | select(.type=="STRING") | {label, value}'
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
- **Don't use invalid values** (the bot will raise a `ValueError` and refuse to start)
- **Don't forget to set** `OP_SERVICE_ACCOUNT_TOKEN` before running the bot

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

# Invalid values cause the bot to fail immediately with a clear error
TRADING_MODE: "invalid" → ValueError: invalid value for 'trading_mode'
RISK_LEVEL: "extreme"  → ValueError: invalid value for 'risk_level'
```

______________________________________________________________________

## Safety Features

### Automatic Safeguards

1. **Validation** - Invalid values raise a `ValueError` immediately with a clear message
1. **Fail fast** - If 1Password is unavailable or a field is missing, the bot refuses to start
1. **Actionable errors** - Every failure tells you exactly what command to run to fix it
1. **Logging** - All config values logged on startup for transparency

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

1. **Check 1Password authentication:**

   ```bash
   op whoami
   # If not authenticated:
   export OP_SERVICE_ACCOUNT_TOKEN=ops_xxxx...
   ```

1. **Verify field names are correct:**

   ```bash
   make opconfig-show
   # Or directly:
   op item get revolut-trader-config --vault revolut-trader --fields TRADING_MODE
   ```

1. **Check field type is "text" not "concealed"**

1. **Look at bot logs:**

   ```
   RuntimeError: TRADING_MODE not found in 1Password config.
   Run: make opconfig-init
   ```

### Invalid value error

**Issue:** Bot fails to start with invalid config value

**Cause:** Value is invalid for that field type

**Solution:**

```bash
# Check what you set
make opconfig-show

# Must be valid values (see field documentation)
make opconfig-set KEY=RISK_LEVEL VALUE=moderate
```

______________________________________________________________________

## No Code Defaults - 1Password Required

**This bot has NO code defaults for trading configuration.**

All configuration MUST be in 1Password. This ensures:

### ✅ Safety Benefits

1. **No accidental trading** - Can't start without explicit config
1. **Visible settings** - All config is in one place
1. **Intentional changes** - Must explicitly set each value
1. **Environment isolation** - Each machine has its own config

### If Config is Missing

The bot will immediately fail with a clear error:

```
RuntimeError: TRADING_MODE not found in 1Password config.
Run: make opconfig-init
```

This is **intentional** - better to fail fast than trade with unknown settings.

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

**Do NOT keep in code:**

- No hardcoded defaults for trading settings
- No `.env` fallbacks
- Tests use `tests/mocks/mock_onepassword.py` — never real 1Password calls

______________________________________________________________________

## Quick Reference

```bash
# Create config item (if missing)
make opconfig-init

# View all configuration
make opconfig-show

# Set single values
make opconfig-set KEY=TRADING_MODE VALUE=live
make opconfig-set KEY=RISK_LEVEL VALUE=moderate
make opconfig-set KEY=BASE_CURRENCY VALUE=EUR

# Using 1Password CLI directly
op item get revolut-trader-config --vault revolut-trader
op item edit revolut-trader-config --vault revolut-trader TRADING_MODE[text]="live"

# Set multiple values at once
op item edit revolut-trader-config --vault revolut-trader \
  TRADING_MODE[text]="live" \
  RISK_LEVEL[text]="moderate" \
  TRADING_PAIRS[text]="BTC-EUR,ETH-EUR,SOL-EUR"

# Test with paper mode
make run-paper
```

______________________________________________________________________

## Summary

✅ **Auto-initialized** - `make setup` creates config item with safe defaults
✅ **Required, not optional** - No accidental use of hardcoded values
✅ **Fail fast** - Missing or invalid config raises a clear error immediately
✅ **Explicit configuration** - All settings visible in 1Password
✅ **Separate from credentials** - Clean organization
✅ **Secure and centralized** - One source of truth
✅ **Environment-specific** - Different configs per machine
✅ **Transparent** - All values logged on startup

**Setup once, modify as needed! 🚀**
