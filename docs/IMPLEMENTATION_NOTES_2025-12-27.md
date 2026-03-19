# Implementation Notes - December 27, 2025

## Overview

This document details the critical fixes and improvements made to the Revolut Trading Bot on December 27, 2025.

## Issues Fixed

### 1. 1Password CLI Integration (--reveal Flag)

**Problem:**

- The bot was failing to load private keys from 1Password
- Error: "MalformedFraming" when trying to parse PEM content
- Root cause: 1Password CLI v2 returns placeholder text instead of actual values for concealed fields

**Diagnosis:**

```bash
$ op item get revolut-trader-credentials --vault revolut-trader --fields REVOLUT_PRIVATE_KEY
[use 'op item get x67qzfd4cd23zaqmavquh42yli --reveal' to reveal]
```

The CLI was returning instructions instead of the actual private key value.

**Solution:**
Added `--reveal` flag to the `get_field()` method in `src/utils/onepassword.py`:

```python
# Line 86-97
result = subprocess.run(
    [
        "op",
        "item",
        "get",
        self.item_name,
        "--vault",
        self.vault_name,
        "--fields",
        field_name,
        "--reveal",  # ← Added this line
    ],
    capture_output=True,
    text=True,
    timeout=10,
)
```

**Impact:**

- Private keys now load correctly from 1Password
- Secure credential management works as intended
- No need for local credential files

______________________________________________________________________

### 2. Paper Mode Using Fake Data

**Problem:**

- Paper mode was generating random fake prices instead of using real market data
- This made backtesting and strategy validation unrealistic

**Original Code (bot.py:224-241):**

```python
if self.trading_mode == TradingMode.PAPER:
    # In paper mode, simulate with random-ish data
    import random

    base_price = Decimal(str(random.uniform(40000, 50000)))
    spread = base_price * Decimal("0.001")

    return MarketData(
        symbol=symbol,
        timestamp=datetime.utcnow(),
        bid=base_price - spread,
        ask=base_price + spread,
        last=base_price,
        volume_24h=Decimal("1000000"),
        high_24h=base_price * Decimal("1.05"),
        low_24h=base_price * Decimal("0.95"),
    )
```

**Solution:**
Modified `_fetch_market_data()` to use real API data in both modes:

```python
async def _fetch_market_data(self, symbol: str) -> MarketData | None:
    """Fetch current market data for a symbol.

    Both paper and live modes use real market data from the Revolut API.
    The difference is in execution: paper mode simulates orders, live mode executes them.
    """
    try:
        # Fetch real market data from API (used in both paper and live modes)
        ticker_data = await self.api_client.get_ticker(symbol)

        return MarketData(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            bid=Decimal(str(ticker_data.get("bid", 0))),
            ask=Decimal(str(ticker_data.get("ask", 0))),
            last=Decimal(str(ticker_data.get("last", 0))),
            volume_24h=Decimal(str(ticker_data.get("volume", 0))),
            high_24h=Decimal(str(ticker_data.get("high", 0))),
            low_24h=Decimal(str(ticker_data.get("low", 0))),
        )
```

**Impact:**

- Paper mode now provides realistic testing with actual market conditions
- Strategy backtesting is more accurate
- Both paper and live modes use identical data sources

______________________________________________________________________

### 3. Incorrect API Base URL

**Problem:**

- Base URL was set to `https://api.revolut.com/api/1.0`
- Revolut X API actually uses `https://revx.revolut.com/api/1.0`
- All API calls were returning 404 errors

**Solution:**
Updated `src/config.py`:

```python
# Line 38
revolut_api_base_url: str = Field(default="https://revx.revolut.com/api/1.0")
```

**Verification:**

```bash
# Correct URL structure
curl -s "https://revx.revolut.com/api/1.0/balances"

# Old incorrect URL
curl -s "https://api.revolut.com/api/1.0/balances"  # 404
```

**Impact:**

- All API endpoints now accessible
- Authentication working correctly
- Market data loading successfully

______________________________________________________________________

### 4. Duplicate /api/1.0 Path Construction

**Problem:**

- Base URL included `/api/1.0`
- Request method was also adding `/api/1.0` to the path
- Result: URLs like `https://revx.revolut.com/api/1.0/api/1.0/public/order-book/BTC-USD`

**Original Code (client.py:148-149):**

```python
path = f"/api/1.0{endpoint}"
url = f"{self.base_url}{path}"  # Double /api/1.0!
```

**Solution:**

```python
path = f"/api/1.0{endpoint}"  # Used for signature
url = f"{self.base_url}{endpoint}"  # Correct URL construction
```

**Impact:**

- URLs now correctly formatted
- API requests successful

______________________________________________________________________

### 5. Missing Market Data Endpoint

**Problem:**

- Code was trying to use `/ticker/{symbol}` endpoint
- Revolut X API doesn't have this endpoint
- Documentation shows `/public/order-book/{symbol}` for market data

**Solution:**
Implemented new `get_ticker()` method using order book data:

```python
async def get_ticker(self, symbol: str) -> dict[str, Any]:
    """Get current market data from public order book.

    Returns a normalized ticker format with bid, ask, and last price.
    Uses the /public/order-book endpoint (requires authentication despite being "public").
    """
    # Get order book data - requires authentication even though it's a "public" endpoint
    order_book = await self._request("GET", f"/public/order-book/{symbol}")

    # Extract data from response
    data = order_book.get("data", {})
    asks = data.get("asks", [])
    bids = data.get("bids", [])

    # Get best bid and ask prices
    best_bid = float(bids[0]["p"]) if bids else 0.0
    best_ask = float(asks[0]["p"]) if asks else 0.0

    # Calculate mid price as "last"
    last = (best_bid + best_ask) / 2 if (best_bid and best_ask) else 0.0

    # Calculate 24h volume (sum of quantities from bids and asks)
    volume = sum(float(bid.get("q", 0)) for bid in bids) + sum(
        float(ask.get("q", 0)) for ask in asks
    )

    # Return normalized ticker format compatible with existing code
    return {
        "bid": best_bid,
        "ask": best_ask,
        "last": last,
        "volume": volume,
        "high": last * 1.05,  # Estimated, not available in order book
        "low": last * 0.95,  # Estimated, not available in order book
        "symbol": symbol,
    }
```

**API Response Format:**

```json
{
  "data": {
    "asks": [{
      "p": "4600",      // price
      "q": "17",        // quantity
      "pc": "USD",      // price currency
      "qc": "ETH",      // quantity currency
      "s": "SELL"       // side
    }],
    "bids": [{
      "p": "4599",
      "q": "15",
      "pc": "USD",
      "qc": "ETH",
      "s": "BUY"
    }]
  },
  "metadata": {
    "timestamp": "2025-12-27T18:37:21.124538Z"
  }
}
```

**Impact:**

- Real-time bid/ask prices available
- Market data flowing correctly
- Normalized response format works with existing strategies

______________________________________________________________________

## Revolut X API Insights

### Base URLs

- **Production**: `https://revx.revolut.com`
- **Alternative**: `https://revx.revolut.codes` (also works)
- **NOT**: `https://api.revolut.com` (different service)

### Authentication

All endpoints require Ed25519 signature authentication, even "public" ones:

- Header: `X-Revx-API-Key`
- Header: `X-Revx-Timestamp`
- Header: `X-Revx-Signature`

### Key Endpoints

- **Order Book**: `GET /public/order-book/{symbol}`
- **Balances**: `GET /api/1.0/balances`
- **Orders**: `POST /api/1.0/orders`

### Symbol Format

Use hyphenated format: `BTC-USD`, `ETH-USD`, etc.

______________________________________________________________________

## Testing Results

### Before Fixes

```
ERROR | HTTP error 404: {"message":"The requested resource was not found"}
ERROR | Failed to fetch market data for BTC-USD
ERROR | Failed to load private key: MalformedFraming
```

### After Fixes

```
INFO | ✓ 1Password configured and available (secure mode)
INFO | ✓ Using private key from 1Password (secure storage)
INFO | Revolut API client initialized successfully
INFO | Trading bot started successfully!
INFO | === Trading Iteration 1 ===
INFO | Portfolio: $10000.00 | Cash: $10000.00 | Positions: $0.00 | P&L: $0.00
```

______________________________________________________________________

## Files Modified

1. `src/utils/onepassword.py` - Added `--reveal` flag
1. `src/bot.py` - Real data for paper mode
1. `src/config.py` - Correct API base URL
1. `src/api/client.py` - Fixed URL construction and added order book endpoint
1. `CHANGELOG.md` - Documented all changes
1. `docs/1PASSWORD_INTEGRATION.md` - Added CLI v2 requirements

______________________________________________________________________

## Migration Notes

### For Existing Users

1. **Update 1Password CLI** (if needed):

   ```bash
   brew upgrade 1password-cli
   op --version  # Should be v2.0+
   ```

1. **No config changes needed** - The base URL is updated in code

1. **Test paper mode**:

   ```bash
   python run.py --mode paper
   ```

1. **Verify real data**:

   - Check logs for market data fetching (no errors)
   - Confirm prices are realistic (not random 40k-50k range)

______________________________________________________________________

## Key Learnings

1. **1Password CLI v2 Changes**: Concealed fields require `--reveal` flag
1. **Revolut X vs Revolut Business**: Different APIs with different base URLs
1. **Public Endpoints Aren't Public**: "Public" endpoints still need authentication
1. **Order Book for Prices**: No dedicated ticker endpoint; use order book
1. **Paper Mode Best Practice**: Always use real data for realistic testing

______________________________________________________________________

## Future Considerations

### Potential Improvements

1. **Caching**: Add short-lived cache for order book data to reduce API calls
1. **Fallback Data Source**: Consider adding CoinGecko/Binance as backup for paper mode
1. **Better Volume Calculation**: Current method sums order book quantities (not 24h volume)
1. **Error Handling**: Add retry logic for transient API failures
1. **Rate Limiting**: Implement request throttling to avoid hitting API limits

### Monitoring

- Watch for changes in Revolut X API documentation
- Monitor 1Password CLI updates (breaking changes)
- Track API response times and add alerting

______________________________________________________________________

## Contact & Support

For issues related to these changes:

- Check database logs: `make db-stats` (logs are stored encrypted in the database)
- Verify 1Password CLI version: `op --version`
- Test API connectivity: `curl https://revx.revolut.com/api/1.0/balances`
- Review this document for troubleshooting steps

______________________________________________________________________

**Document Version**: 1.0
**Date**: December 27, 2025
**Author**: Claude (AI Assistant)
**Reviewed By**: User
