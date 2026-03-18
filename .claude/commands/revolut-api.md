# Revolut X REST API Reference

Fetch the latest Revolut X REST API documentation and provide a precise, structured view of all endpoints.

## Instructions

1. Fetch the official documentation from: https://developer.revolut.com/docs/x-api/revolut-x-crypto-exchange-rest-api
2. Parse all endpoints across all sections (balances, orders, trades, market data, configuration)
3. Present them in the structured format below
4. If `$ARGUMENTS` is provided, filter to show only endpoints matching that category or keyword (e.g., "orders", "trades", "market", "balance", "config")

## Output Format

### Authentication

Summarize the auth mechanism (headers, signature algorithm).

### Endpoints Table

| Method | Path | Category | Description |
|--------|------|----------|-------------|
| ...    | ...  | ...      | ...         |

### Detailed Endpoint Reference

For each endpoint, show:
- **Method + Path**
- Description
- Request parameters (path, query, body)
- Response schema (key fields)
- Any rate limits or constraints

### Key Notes

Summarize important technical constraints:
- Numeric types (string-encoded decimals)
- Rate limits
- Pagination mechanics
- Date range limits
- Order states lifecycle

## Base URL

`https://trading.revolut.com/api/1.0`

## Known Endpoints (from docs — always re-fetch to confirm latest)

### Balance
- `GET /api/v1/balances` — all account balances

### Orders
- `POST /orders` — place a limit or market order (rate-limited: 1000 req/day)
- `GET /orders` — active orders (filter by symbol, state, type, side; paginated)
- `GET /orders?start_date=&end_date=` — historical orders (filled, cancelled, rejected, replaced)
- `GET /orders/{venue_order_id}` — single order by ID
- `DELETE /venue_orders/{venue_order_id}` — cancel order by ID
- `DELETE /orders` — cancel all active orders
- `GET /orders/{venue_order_id}/fills` — fills for a specific order

### Trades
- `GET /private/trades/{symbol}` — client trade history (max 30-day range; paginated)
- `GET /trades/public` — last 100 public trades

### Market Data (Public)
- `GET /orders/books/{symbol}` — order book snapshot (bids + asks; depth 1–20)
- `GET /tickers` — all ticker snapshots
- `GET /candles/{symbol}` — historical OHLCV candles

### Configuration (Public)
- `GET /get-all-currencies` — all supported currencies with scale/precision
- `GET /get-all-currency-pairs` — all traded pairs with min/max order sizes

## Authentication Headers (required on all requests)

| Header | Value |
|--------|-------|
| `X-Revx-API-Key` | 64-character API key |
| `X-Revx-Timestamp` | Unix timestamp in milliseconds |
| `X-Revx-Signature` | Base64-encoded Ed25519 signature |

Signature input: `timestamp + HTTP_METHOD + path + query_string + json_body`

## Order States Lifecycle

```
pending_new → new → partially_filled → filled
                 ↘ cancelled
                 ↘ rejected
                 ↘ replaced
```