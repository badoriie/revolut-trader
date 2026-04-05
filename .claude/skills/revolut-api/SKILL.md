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

Public endpoints (`/public/...`) do **not** require auth headers.

______________________________________________________________________

## Error Response Format

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

> For full schema details, response examples, and cURL samples → `docs/revolut-x-api-docs.md`
