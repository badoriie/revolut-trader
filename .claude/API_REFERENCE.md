# Revolut X API Reference

## Official Documentation

**PRIMARY REFERENCE**: Always consult the official Revolut X API documentation when implementing or modifying API-related functionality:

🔗 **[Revolut X Crypto Exchange REST API Documentation](https://developer.revolut.com/docs/x-api/revolut-x-crypto-exchange-rest-api)**

## Critical Guidelines

### 1. Always Check Documentation First

Before implementing any API endpoint:

1. ✅ Search the official documentation for the endpoint
1. ✅ Verify the HTTP method (GET, POST, DELETE, etc.)
1. ✅ Check the exact path format
1. ✅ Review the request/response format
1. ✅ Understand authentication requirements

### 2. Known Endpoints

#### Account & Balance

- **Get All Balances**: `GET /balances`
  - Returns array of balance objects
  - Each balance: `{ currency, available, reserved, total }`
  - [Documentation](https://developer.revolut.com/docs/x-api/get-all-balances)

#### Market Data

- **Get Order Book**: `GET /public/order-book/{symbol}`

  - Requires authentication despite being "public"
  - Returns bid/ask arrays
  - [Documentation](https://developer.revolut.com/docs/x-api/get-order-book)

- **Get Candles**: `GET /candles/{symbol}`

  - Historical price data
  - Parameters: `interval`, `since`, `limit`
  - [Documentation](https://developer.revolut.com/docs/x-api/get-candles)

#### Trading

- **Create Order**: `POST /orders`

  - Body: `{ symbol, side, type, quantity, price?, timeInForce? }`
  - Returns order creation response
  - [Documentation](https://developer.revolut.com/docs/x-api/create-order)

- **Cancel Order**: `DELETE /orders/{orderId}`

  - [Documentation](https://developer.revolut.com/docs/x-api/cancel-order)

- **Get Order**: `GET /orders/{orderId}`

  - [Documentation](https://developer.revolut.com/docs/x-api/get-order)

- **Get Open Orders**: `GET /orders`

  - Optional parameter: `symbol`
  - [Documentation](https://developer.revolut.com/docs/x-api/get-open-orders)

- **Get Trades**: `GET /trades`

  - Parameters: `symbol?`, `limit?`
  - [Documentation](https://developer.revolut.com/docs/x-api/get-trades)

### 3. Authentication

All Revolut X API requests require Ed25519 signature authentication:

```python
# Headers required for ALL requests
{
    "X-Revx-Timestamp": str(int(time.time() * 1000)),  # Unix epoch milliseconds
    "X-Revx-Signature": signature,  # Ed25519 signature
    "Content-Type": "application/json",
}
```

**Signature Generation**:

1. Create payload: `{timestamp}{method}{path}{body}`
1. Sign with Ed25519 private key
1. Encode signature as base64

See `src/api/client.py:_generate_signature()` for implementation.

### 4. Base URL

```python
BASE_URL = "https://revx.revolut.com/api/1.0"
```

### 5. Response Formats

#### Success Responses

Most endpoints return data wrapped in a response object:

```json
{
  "data": { ... },
  "status": "success"
}
```

Some endpoints (like `/balances`) return arrays directly:

```json
[
  { "currency": "BTC", "available": "0.5", "reserved": "0", "total": "0.5" },
  ...
]
```

#### Error Responses

```json
{
  "message": "Error description",
  "error_id": "uuid",
  "timestamp": 1234567890
}
```

### 6. Common Pitfalls

❌ **DON'T**:

- Use `/balance` (singular) - endpoint doesn't exist
- Forget authentication headers on "public" endpoints
- Use `/api/1.0/api/1.0` (duplicate path)
- Send numeric values as numbers (use strings for precision)

✅ **DO**:

- Use `/balances` (plural) for account balances
- Always authenticate, even for public data
- Use correct base URL: `https://revx.revolut.com/api/1.0`
- Send monetary values as strings: `"10.5"` not `10.5`

### 7. Rate Limiting

The bot implements rate limiting to prevent API bans:

- Default: 60 requests per minute
- Implemented in: `src/utils/rate_limiter.py`
- Auto-wait on 429 responses

### 8. Validation

All API responses should be validated using Pydantic models:

- `OrderBookResponse` - Order book data
- `BalanceResponse` - Balance data (deprecated, use array)
- `CandleResponse` - Historical candles
- `OrderCreationResponse` - Order creation

See `src/data/models.py` for definitions.

## Implementation Guidelines

### When Adding New Endpoints

1. **Research**: Check official documentation
1. **Test**: Use `curl` or Postman to verify endpoint works
1. **Implement**: Add method to `src/api/client.py`
1. **Validate**: Create Pydantic model if needed
1. **Type**: Add proper type hints and guards
1. **Document**: Update this reference
1. **Test**: Add to `cli/api_test.py` if applicable

### Example: Adding a New Endpoint

```python
# 1. Check documentation for exact specification
# 2. Add to RevolutAPIClient


async def get_new_endpoint(self, param: str) -> dict[str, Any]:
    """Get new endpoint data.

    Reference: https://developer.revolut.com/docs/x-api/endpoint-name
    """
    response = await self._request("GET", f"/new-endpoint/{param}")

    # Type guard (response can be dict or list)
    if not isinstance(response, dict):
        raise ValueError(f"Expected dict response, got {type(response)}")

    # Validate if Pydantic model exists
    # validated = NewEndpointResponse(**response)

    return response
```

## Testing API Changes

Always test API changes with:

```bash
# Test connection
make api-test

# Test specific endpoints
make api-balance
make api-ticker SYMBOL=BTC-USD
make api-tickers

# Run all tests
make test
```

## Additional Resources

- **Main Documentation**: https://developer.revolut.com/docs/x-api/revolut-x-crypto-exchange-rest-api
- **API Reference**: https://developer.revolut.com/api-reference
- **Support**: https://developer.revolut.com/support

## Currently Used Endpoints

The bot actively uses these endpoints:

- ✅ `GET /balances` - Used in `src/bot.py` for portfolio management
- ✅ `GET /public/order-book/{symbol}` - Used via `get_ticker()` in `src/bot.py` for price data
- ✅ `GET /candles/{symbol}` - Used in `src/backtest/engine.py` for historical data
- ✅ `POST /orders` - Used in `src/execution/executor.py` for order creation

**Not Yet Used** (implemented but unused):

- ⚪ `GET /market-data/{symbol}` - Not documented, may be deprecated
- ⚪ `GET /orderbook/{symbol}` - Replaced by `/public/order-book/{symbol}`
- ⚪ `GET /orders` - Order management not yet implemented
- ⚪ `GET /orders/{orderId}` - Order management not yet implemented
- ⚪ `DELETE /orders/{orderId}` - Order management not yet implemented
- ⚪ `GET /trades` - Trade history features not yet implemented

## Version History

- **2025-12-29**: Comprehensive API review completed
  - Created API_REVIEW_REPORT.md with detailed analysis
  - Fixed `/balances` endpoint
  - Documented authentication requirements
  - Added common pitfalls and guidelines
  - Identified duplicate order book endpoints
  - Catalogued actively used vs unused endpoints
