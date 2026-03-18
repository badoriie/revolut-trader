# Revolut X API Reference

## Primary Sources of Truth

1. **Quick reference (slash command)**: `/revolut-api` — run this in Claude Code for the full structured endpoint table
1. **Full documentation**: `docs/revolut-x-api-docs.md` — complete API docs with request/response examples
1. **Official docs**: https://developer.revolut.com/docs/x-api/revolut-x-crypto-exchange-rest-api

## Base URL

```
https://revx.revolut.com/api/1.0
```

## Implementation

All 17 endpoints are implemented in `src/api/client.py`. See the `/revolut-api` command for the mapping of each endpoint to its client method.

## Authentication

Every authenticated request requires three headers. The `/public/...` endpoints do **not** require auth.

```
X-Revx-API-Key      → 64-character API key
X-Revx-Timestamp    → Unix timestamp in milliseconds
X-Revx-Signature    → Base64-encoded Ed25519 signature
```

Signature = Ed25519 sign of `{timestamp}{METHOD}{/api/1.0/path}{query_string}{json_body}` (no separators).

See `src/api/client.py:_generate_signature()` for the implementation.

## Error Response

All errors return:

```json
{ "message": "string", "error_id": "string", "timestamp": 1234567890 }
```

Errors are raised as `RevolutAPIError(status_code, message)` — catch this, not `httpx.HTTPStatusError`.

## Critical Rules

- All monetary values are **strings** in both requests and responses — never floats
- Use `Decimal` for all financial math in Python code
- Public endpoints (`/public/...`) skip auth headers; use `_public_request()`, not `_request()`
- `DELETE` endpoints return `204 No Content` — client returns `None`, not empty dict
- Single-order responses are wrapped in `{"data": {...}}` (object); list responses in `{"data": [...]}`

## Testing API Changes

```bash
make api-test              # connectivity + auth check
make api-balance           # GET /balances
make api-ticker SYMBOL=BTC-EUR
make api-tickers
make api-order-book SYMBOL=BTC-EUR
make api-candles SYMBOL=BTC-EUR
make api-open-orders
make api-historical-orders
make api-currencies
make api-currency-pairs
make api-last-public-trades
```

## Adding a New Endpoint

1. Check `docs/revolut-x-api-docs.md` for exact path, method, params, and response shape
1. Add method to `src/api/client.py` following the existing pattern
1. Use `_request()` for authenticated, `_public_request()` for public endpoints
1. Raise `ValueError` on malformed responses; `RevolutAPIError` is raised automatically on HTTP errors
1. Add a `make` target in `Makefile` if it's useful for manual testing
1. Add tests to `tests/unit/test_api_client.py`
