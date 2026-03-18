# Revolut X REST API Reference

Read `docs/revolut-x-api-docs.md` for the full documentation. Use the structured reference below as a precise quick-reference for all 17 endpoints.

If `$ARGUMENTS` is provided, show only the section(s) matching that keyword (e.g., `orders`, `trades`, `market`, `balance`, `config`, `auth`, `errors`, `models`).

______________________________________________________________________

## Base URL

```
https://revx.revolut.com/api/1.0
```

______________________________________________________________________

## Authentication

Every authenticated request requires three headers:

| Header             | Value                              |
| ------------------ | ---------------------------------- |
| `X-Revx-API-Key`   | 64-character alphanumeric API key  |
| `X-Revx-Timestamp` | Unix timestamp in **milliseconds** |
| `X-Revx-Signature` | Base64-encoded Ed25519 signature   |

**Signature construction** — concatenate without separators:

```
{timestamp}{HTTP_METHOD}{/api/1.0/path}{query_string_without_?}{minified_json_body}
```

Example:

```
1765360896219POST/api/1.0/orders{"client_order_id":"...","symbol":"BTC-USD","side":"BUY","order_configuration":{"limit":{"base_size":"0.1","price":"90000.1"}}}
```

Public endpoints (`/public/...`) do **not** require auth headers.

______________________________________________________________________

## Error Response Format

All errors return:

```json
{ "message": "string", "error_id": "string", "timestamp": 3318215482991 }
```

| Code  | Meaning                                         |
| ----- | ----------------------------------------------- |
| `400` | Bad Request — invalid pair, params, or body     |
| `401` | Unauthorized — deactivated or IP-restricted key |
| `403` | Forbidden — insufficient permissions            |
| `404` | Not Found — order/resource does not exist       |
| `409` | Conflict — timestamp in the future              |
| `429` | Rate Limit Exceeded                             |
| `5XX` | Server Error                                    |

______________________________________________________________________

## All 17 Endpoints

### 1. Balance

#### `GET /balances` — Get All Balances

- **Auth:** Required
- **Params:** None
- **Response:** Array of balance objects
  ```json
  [{ "currency": "BTC", "available": "1.25", "reserved": "0.10", "staked": "0", "total": "1.35" }]
  ```

______________________________________________________________________

### 2–3. Configuration

#### `GET /configuration/currencies` — Get All Currencies

- **Auth:** Required
- **Params:** None
- **Response:** Dict keyed by currency symbol
  ```json
  { "BTC": { "symbol": "BTC", "name": "Bitcoin", "scale": 8, "asset_type": "crypto", "status": "active" } }
  ```

#### `GET /configuration/pairs` — Get All Currency Pairs

- **Auth:** Required
- **Rate Limit:** 1000 req/min
- **Params:** None
- **Response:** Dict keyed by pair (`"BTC/USD"`)
  ```json
  { "BTC/USD": { "base": "BTC", "quote": "USD", "base_step": "0.0000001", "quote_step": "0.01",
    "min_order_size": "0.0000001", "max_order_size": "1000", "min_order_size_quote": "0.01", "status": "active" } }
  ```

______________________________________________________________________

### 4–5. Public Market Data (no auth)

#### `GET /public/last-trades` — Last 100 Public Trades

- **Auth:** Not required
- **Rate Limit:** 20 req / 10 seconds
- **Params:** None
- **Response:** `{ "data": [{ "tdt", "aid", "anm", "p", "pc", "pn", "q", "qc", "qn", "ve", "pdt", "vp", "tid" }], "metadata": { "timestamp" } }`
  - Fields are MiFID II / MiCA compliance fields: `aid`=asset ID, `p`=price, `q`=quantity, `tid`=transaction ID

#### `GET /public/order-book/{symbol}` — Public Order Book (max 5 levels)

- **Auth:** Not required
- **Path param:** `symbol` — e.g., `BTC-USD`
- **Response:** `{ "data": { "asks": [...], "bids": [...] }, "metadata": { "timestamp" } }`
  - Each level: `{ "aid", "anm", "s" (SELL/BUYI), "p", "pc", "q", "qc", "no" (order count), "ts" (CLOB), "pdt" }`

______________________________________________________________________

### 6–12. Orders

#### `POST /orders` — Place Order

- **Auth:** Required
- **Rate Limit:** 1000 req/min
- **Body:**
  ```json
  {
    "client_order_id": "<uuid>",
    "symbol": "BTC-USD",
    "side": "buy|sell",
    "order_configuration": {
      "limit": { "base_size": "0.1", "price": "50000", "execution_instructions": ["allow_taker|post_only"] }
      // OR
      "market": { "base_size": "0.1" }
      // base_size XOR quote_size required
    }
  }
  ```
- **Response:** `{ "data": [{ "venue_order_id": "<uuid>", "client_order_id": "<uuid>", "state": "new" }] }`

#### `DELETE /orders` — Cancel All Active Orders

- **Auth:** Required
- **Response:** `204 No Content` (no body)

#### `GET /orders/active` — Get Active Orders

- **Auth:** Required
- **Query params:**

| Param     | Type    | Description                                     |
| --------- | ------- | ----------------------------------------------- |
| `symbols` | string  | Comma-separated pairs (e.g., `BTC-USD,ETH-USD`) |
| `states`  | string  | `pending_new`, `new`, `partially_filled`        |
| `types`   | string  | `limit`, `conditional`, `tpsl`                  |
| `sides`   | string  | `buy`, `sell`                                   |
| `cursor`  | string  | Pagination cursor from `metadata.next_cursor`   |
| `limit`   | integer | 1–100, default `100`                            |

- **Response:** `{ "data": [<order>], "metadata": { "timestamp", "next_cursor" } }`

#### `GET /orders/historical` — Get Historical Orders

- **Auth:** Required
- **Query params:**

| Param        | Type    | Description                                      |
| ------------ | ------- | ------------------------------------------------ |
| `symbols`    | string  | Comma-separated pairs                            |
| `states`     | string  | `filled`, `cancelled`, `rejected`, `replaced`    |
| `types`      | string  | `market`, `limit`                                |
| `start_date` | integer | Unix epoch ms. Default: 7 days before `end_date` |
| `end_date`   | integer | Unix epoch ms. Default: now                      |
| `cursor`     | string  | Pagination cursor                                |
| `limit`      | integer | 1–100, default `100`                             |

> `end_date - start_date` must be ≤ 30 days.

- **Response:** Same shape as active orders.

#### `GET /orders/{venue_order_id}` — Get Order by ID

- **Auth:** Required
- **Path param:** `venue_order_id` (uuid)
- **Response:** `{ "data": { <order object> } }` — note: single object, not array

#### `DELETE /orders/{venue_order_id}` — Cancel Order by ID

- **Auth:** Required
- **Path param:** `venue_order_id` (uuid)
- **Response:** `204 No Content` (no body)

#### `GET /orders/fills/{venue_order_id}` — Get Fills of Order

- **Auth:** Required
- **Path param:** `venue_order_id` (uuid)
- **Response:** `{ "data": [{ "tdt", "aid", "anm", "p", "pc", "q", "qc", "ve", "tid", "oid", "s" (buy/sell), "im" (maker bool) }] }`

______________________________________________________________________

### 13–14. Trades

#### `GET /trades/all/{symbol}` — All Public Trades for Symbol

- **Auth:** Required
- **Path param:** `symbol`
- **Query params:**

| Param        | Description                                      |
| ------------ | ------------------------------------------------ |
| `start_date` | Unix epoch ms, default: 7 days before `end_date` |
| `end_date`   | Unix epoch ms, max range 30 days                 |
| `cursor`     | Pagination cursor                                |
| `limit`      | 1–100, default `100`                             |

- **Response:** `{ "data": [{ "tdt", "aid", "anm", "p", "pc", "q", "qc", "ve", "tid" }], "metadata": { "timestamp", "next_cursor" } }`

#### `GET /trades/private/{symbol}` — Client Trade History

- **Auth:** Required
- **Path param:** `symbol`
- **Query params:** Same as `/trades/all/{symbol}`
- **Response:** Same as public trades, plus `oid` (order id), `s` (buy/sell), `im` (maker bool)

______________________________________________________________________

### 15–17. Market Data (authenticated)

#### `GET /order-book/{symbol}` — Authenticated Order Book Snapshot (up to 20 levels)

- **Auth:** Required
- **Rate Limit:** 1000 req/min
- **Path param:** `symbol`
- **Query params:** `depth` (integer, 1–20, default `20`)
- **Response:** `{ "data": { "asks": [...], "bids": [...] }, "metadata": { "ts" } }`
  - Each level: `{ "aid", "anm", "s" (SELL/BUY), "p", "pc", "q", "qc", "no", "ts" (CLOB), "pdt" }`

#### `GET /candles/{symbol}` — Historical OHLCV Candles

- **Auth:** Required
- **Path param:** `symbol`
- **Query params:**

| Param      | Description                                                                                                 |
| ---------- | ----------------------------------------------------------------------------------------------------------- |
| `interval` | Minutes: `1`, `5`, `15`, `30`, `60`, `240`, `1440`, `2880`, `5760`, `10080`, `20160`, `40320`. Default: `5` |
| `since`    | Unix epoch ms. Default: `until - (interval * 100 minutes)`                                                  |
| `until`    | Unix epoch ms. Default: now                                                                                 |

> `(until - since) / interval` must not exceed 1000 candles.

- **Response:** `{ "data": [{ "start", "open", "high", "low", "close", "volume" }] }`
  - No volume periods use mid-price (bid/ask average) instead of trades.

#### `GET /tickers` — All Tickers

- **Auth:** Required
- **Query params:** `symbols` (comma-separated, optional filter)
- **Response:** `{ "data": [{ "symbol": "BTC/USD", "bid", "ask", "mid", "last_price" }], "metadata": { "timestamp" } }`

______________________________________________________________________

## Order Object Fields

| Field                    | Type    | Description                                      |
| ------------------------ | ------- | ------------------------------------------------ |
| `id`                     | uuid    | System order ID (`venue_order_id`)               |
| `client_order_id`        | uuid    | Client-provided ID                               |
| `symbol`                 | string  | e.g., `"BTC/USD"`                                |
| `side`                   | string  | `"buy"` or `"sell"`                              |
| `type`                   | string  | `"market"`, `"limit"`, `"conditional"`, `"tpsl"` |
| `quantity`               | string  | Order qty in base currency                       |
| `filled_quantity`        | string  | Amount executed                                  |
| `leaves_quantity`        | string  | Amount remaining                                 |
| `quote_quantity`         | string  | Order amount in quote currency                   |
| `price`                  | string  | Limit price                                      |
| `average_fill_price`     | string  | Qty-weighted average fill price                  |
| `status`                 | string  | See Order Statuses below                         |
| `reject_reason`          | string  | Only when `status=rejected`                      |
| `time_in_force`          | string  | `gtc`, `ioc`, `fok`                              |
| `execution_instructions` | array   | `["allow_taker"]` or `["post_only"]`             |
| `created_date`           | integer | Unix epoch ms                                    |
| `updated_date`           | integer | Unix epoch ms                                    |
| `completed_date`         | integer | Unix epoch ms                                    |

______________________________________________________________________

## Common Data Models

### Order Statuses

| Status             | Description               |
| ------------------ | ------------------------- |
| `pending_new`      | Accepted, not yet working |
| `new`              | Working order             |
| `partially_filled` | Partially executed        |
| `filled`           | Fully executed            |
| `cancelled`        | Cancelled                 |
| `rejected`         | Rejected                  |
| `replaced`         | Replaced by another order |

### Time in Force

| Value | Description         |
| ----- | ------------------- |
| `gtc` | Good Till Cancelled |
| `ioc` | Immediate or Cancel |
| `fok` | Fill or Kill        |

### Execution Instructions

| Value         | Description                                         |
| ------------- | --------------------------------------------------- |
| `allow_taker` | Default — may fill as taker                         |
| `post_only`   | Maker only — rejected if it would match immediately |

### Order Types

| Type          | Description                                |
| ------------- | ------------------------------------------ |
| `market`      | Immediate execution at market price        |
| `limit`       | Executes only at specified price or better |
| `conditional` | Submitted when trigger price is reached    |
| `tpsl`        | Sets Take Profit / Stop Loss on a position |

### Trigger Object (conditional / tpsl)

| Field                    | Type   | Description                          |
| ------------------------ | ------ | ------------------------------------ |
| `trigger_price`          | string | Price that activates the order       |
| `type`                   | string | `"market"` or `"limit"`              |
| `trigger_direction`      | string | `"ge"` (≥) or `"le"` (≤)             |
| `price`                  | string | Execution price (limit orders only)  |
| `time_in_force`          | string | `"gtc"` or `"ioc"`                   |
| `execution_instructions` | array  | `["allow_taker"]` or `["post_only"]` |

______________________________________________________________________

## Endpoint Summary

| #   | Method   | Path                             | Auth | Rate Limit | Client method                   |
| --- | -------- | -------------------------------- | ---- | ---------- | ------------------------------- |
| 1   | `GET`    | `/balances`                      | Yes  | —          | `get_balance()`                 |
| 2   | `GET`    | `/configuration/currencies`      | Yes  | —          | `get_currencies()`              |
| 3   | `GET`    | `/configuration/pairs`           | Yes  | 1000/min   | `get_currency_pairs()`          |
| 4   | `GET`    | `/public/last-trades`            | No   | 20/10s     | `get_last_public_trades()`      |
| 5   | `GET`    | `/public/order-book/{symbol}`    | No   | —          | `get_public_order_book(symbol)` |
| 6   | `POST`   | `/orders`                        | Yes  | 1000/min   | `create_order(...)`             |
| 7   | `DELETE` | `/orders`                        | Yes  | —          | `cancel_all_orders()`           |
| 8   | `GET`    | `/orders/active`                 | Yes  | —          | `get_open_orders(...)`          |
| 9   | `GET`    | `/orders/historical`             | Yes  | —          | `get_historical_orders(...)`    |
| 10  | `GET`    | `/orders/{venue_order_id}`       | Yes  | —          | `get_order(id)`                 |
| 11  | `DELETE` | `/orders/{venue_order_id}`       | Yes  | —          | `cancel_order(id)`              |
| 12  | `GET`    | `/orders/fills/{venue_order_id}` | Yes  | —          | `get_order_fills(id)`           |
| 13  | `GET`    | `/trades/all/{symbol}`           | Yes  | —          | `get_public_trades(symbol)`     |
| 14  | `GET`    | `/trades/private/{symbol}`       | Yes  | —          | `get_trades(symbol)`            |
| 15  | `GET`    | `/order-book/{symbol}`           | Yes  | 1000/min   | `get_order_book(symbol, depth)` |
| 16  | `GET`    | `/candles/{symbol}`              | Yes  | —          | `get_candles(symbol, ...)`      |
| 17  | `GET`    | `/tickers`                       | Yes  | —          | `get_tickers(symbols)`          |

> All paths are relative to `https://revx.revolut.com/api/1.0`

> For full schema details, response examples, and cURL samples → `docs/revolut-x-api-docs.md`
