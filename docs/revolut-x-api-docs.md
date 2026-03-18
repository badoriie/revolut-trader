# Revolut X Crypto Exchange REST API — Complete Documentation

**Version:** 1.0.0  
**Base URL:** `https://revx.revolut.com/api/1.0`  
**Source:** [developer.revolut.com](https://developer.revolut.com/docs/x-api/revolut-x-crypto-exchange-rest-api)

---

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
   - [Generate an Ed25519 Key Pair](#generate-an-ed25519-key-pair)
   - [Create Your API Key](#create-your-api-key)
   - [Authentication Headers](#authentication-headers)
   - [Signing a Request](#signing-a-request)
   - [Code Examples (Python, Node.js)](#code-examples)
3. [Common Error Response Format](#common-error-response-format)
4. [Balance](#balance)
   - [GET Get All Balances](#get-all-balances)
5. [Configuration](#configuration)
   - [GET Get All Currencies](#get-all-currencies)
   - [GET Get All Currency Pairs](#get-all-currency-pairs)
6. [Public Market Data](#public-market-data)
   - [GET Get Last Trades](#get-last-trades-public)
   - [GET Get Order Book (Public)](#get-order-book-public)
7. [Orders](#orders)
   - [POST Place Order](#place-order)
   - [DELETE Cancel All Active Orders](#cancel-all-active-orders)
   - [GET Get Active Orders](#get-active-orders)
   - [GET Get Historical Orders](#get-historical-orders)
   - [GET Get Order by ID](#get-order-by-id)
   - [DELETE Cancel Order by ID](#cancel-order-by-id)
   - [GET Get Fills of Order by ID](#get-fills-of-order-by-id)
8. [Trades](#trades)
   - [GET Get All Public Trades (Market History)](#get-all-public-trades)
   - [GET Get Client Trades (Private)](#get-client-trades)
9. [Market Data](#market-data)
   - [GET Get Order Book Snapshot](#get-order-book-snapshot)
   - [GET Get Historical OHLCV Candles](#get-historical-ohlcv-candles)
   - [GET Get All Tickers](#get-all-tickers)
10. [Common Data Models](#common-data-models)
11. [Endpoint Summary](#endpoint-summary)

---

## Overview

The Revolut X Crypto Exchange REST API allows Revolut X customers to programmatically manage their trading experience. It supports placing and managing orders, retrieving balances, accessing market data, and querying trade history.

All monetary values are returned as **strings** to prevent floating-point rounding errors.

---

## Authentication

### Security Scheme

| Property | Value |
|---|---|
| Type | `apiKey` |
| Header | `X-Revx-API-Key` |
| Format | 64-character alphanumeric string |

Each API key directly maps to a user account (Business or Retail).

**Sample API key:**
```
M1VKFtwB0M9C9QJO7goPlwrOytrJsSNE19txsmpsWIKz7xYu3f8aNucIyynAhYBy
```

---

### Generate an Ed25519 Key Pair

Before creating your API key in the Revolut X web app, generate an Ed25519 key pair using `openssl`.

#### Step 1: Generate the Private Key

```bash
openssl genpkey -algorithm ed25519 -out private.pem
```

Output file `private.pem`:
```
-----BEGIN PRIVATE KEY-----
{YOUR BASE64-ENCODED PRIVATE KEY}
-----END PRIVATE KEY-----
```

> **WARNING:** Your private key is a secret. Never share it with anyone and never send it as part of any request.

#### Step 2: Generate the Public Key

```bash
openssl pkey -in private.pem -pubout -out public.pem
```

Output file `public.pem`:
```
-----BEGIN PUBLIC KEY-----
{YOUR BASE64-ENCODED PUBLIC KEY}
-----END PUBLIC KEY-----
```

> When providing the public key to Revolut X, copy all of it, including the `-----BEGIN PUBLIC KEY-----` and `-----END PUBLIC KEY-----` lines.

### Create Your API Key

Once you have your public key (`public.pem`), go to the **Revolut X web app → Profile** to create your API key.

---

### Authentication Headers

Every authenticated request must include these three headers:

| Header | Type | Description |
|---|---|---|
| `X-Revx-API-Key` | string | Your API key (64-character alphanumeric string). |
| `X-Revx-Timestamp` | integer | Unix timestamp of the request in **milliseconds**. |
| `X-Revx-Signature` | string | The request digest string signed with your private key (Base64-encoded). |

---

### Signing a Request

#### Step 1: Construct the Message String

Concatenate the following values **without any separators** (no spaces, newlines, or commas):

| # | Component | Description |
|---|---|---|
| 1 | Timestamp | Same value as `X-Revx-Timestamp` header |
| 2 | HTTP Method | Uppercase: `GET`, `POST`, `DELETE` |
| 3 | Request Path | Starting from `/api` (e.g., `/api/1.0/orders/active`) |
| 4 | Query String | URL query string if present (without the leading `?`) |
| 5 | Request Body | Minified JSON body string, if present |

**Example message:**
```
1765360896219POST/api/1.0/orders{"client_order_id":"3b364427-1f4f-4f66-9935-86b6fb115d26","symbol":"BTC-USD","side":"BUY","order_configuration":{"limit":{"base_size":"0.1","price":"90000.1"}}}
```

#### Step 2: Sign and Encode

1. Sign the constructed string using your **Ed25519 private key**.
2. **Base64-encode** the resulting signature.
3. Send this value in the `X-Revx-Signature` header.

---

### Code Examples

#### Python

```python
import base64
from pathlib import Path
from nacl.signing import SigningKey
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

# 1. Load your Private Key
pem_data = Path("private.pem").read_bytes()
private_key_obj = serialization.load_pem_private_key(
    pem_data,
    password=None,
    backend=default_backend()
)

# Extract raw bytes for PyNaCl
raw_private = private_key_obj.private_bytes(
    encoding=serialization.Encoding.Raw,
    format=serialization.PrivateFormat.Raw,
    encryption_algorithm=serialization.NoEncryption()
)

# 2. Prepare the message
timestamp = "1746007718237"
method = "GET"
path = "/api/1.0/orders/active"
query = "status=open&limit=10"
body = ""  # Empty for GET

# Concatenate without separators
message = f"{timestamp}{method}{path}{query}{body}".encode('utf-8')

# 3. Sign and Encode
signing_key = SigningKey(raw_private)
signed = signing_key.sign(message)
signature = base64.b64encode(signed.signature).decode()

print(f"X-Revx-Signature: {signature}")
```

#### Node.js

```javascript
const crypto = require('crypto');
const fs = require('fs');

// 1. Load your Private Key
const privateKey = fs.readFileSync('private.pem', 'utf8');

// 2. Prepare the message
const timestamp = Date.now().toString();
const method = 'POST';
const path = '/api/1.0/orders';
const body = JSON.stringify({
    client_order_id: "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    symbol: "BTC-USD",
    side: "buy",
    order_configuration: {
        limit: {
            base_size: "0.1",
            price: "90000.1"
        }
    }
});

// Concatenate without separators
const message = timestamp + method + path + body;

// 3. Sign and Encode
// Use crypto.sign with null for pure Ed25519 signing (no hashing algorithm)
const signatureBuffer = crypto.sign(null, Buffer.from(message), privateKey);
const signature = signatureBuffer.toString('base64');

console.log(`X-Revx-Timestamp: ${timestamp}`);
console.log(`X-Revx-Signature: ${signature}`);
```

---

## Common Error Response Format

All error responses follow this structure:

```json
{
  "message": "string",
  "error_id": "string",
  "timestamp": 3318215482991
}
```

| Field | Type | Description |
|---|---|---|
| `message` | string | Human-readable error description. |
| `error_id` | string | Unique identifier for the error instance. |
| `timestamp` | integer | Timestamp in Unix epoch milliseconds. |

### Standard Error Codes

| Code | Name | Example Message |
|---|---|---|
| `400` | Bad Request | `"No such pair: BTC-BTC"` |
| `401` | Unauthorized | `"API key can only be used for authentication from whitelisted IP"` |
| `403` | Forbidden | `"Forbidden"` |
| `404` | Not Found | `"Order with ID '...' not found"` |
| `409` | Conflict | `"Request timestamp is in the future"` |
| `429` | Rate Limit Exceeded | `"Rate Limit Exceeded"` |
| `5XX` | Server Error | `"Something went wrong!"` |

---

## Balance

Get your Revolut X crypto exchange balances, including both crypto and fiat.

### Get All Balances

Retrieve crypto exchange account balances for the requesting user. The user is resolved by the provided API key.

| Property | Value |
|---|---|
| **Method** | `GET` |
| **Path** | `/api/1.0/balances` |
| **Auth** | Required |

#### cURL Example

```bash
curl -L -X GET 'https://revx.revolut.com/api/1.0/balances' \
  -H 'Accept: application/json' \
  -H 'X-Revx-API-Key: <API_KEY_VALUE>'
```

#### Request

No query parameters or body. Standard authentication headers required.

#### Response Fields

| Field | Type | Description |
|---|---|---|
| `currency` | string | Currency code (e.g., `"BTC"`). |
| `available` | string | Available (free) funds amount. |
| `staked` | string | Staked funds currently earning rewards. |
| `reserved` | string | Reserved (locked) funds amount. |
| `total` | string | Sum of available, reserved, and staked funds. |

> All amounts are returned as strings to prevent floating-point rounding errors.

#### Response `200 OK`

```json
[
  {
    "currency": "BTC",
    "available": "1.25000000",
    "reserved": "0.10000000",
    "total": "1.35000000"
  },
  {
    "currency": "ETH",
    "available": "10.00000000",
    "reserved": "0.00000000",
    "staked": "32.00000000",
    "total": "42.00000000"
  },
  {
    "currency": "USD",
    "available": "5400.50",
    "reserved": "100.00",
    "total": "5500.50"
  }
]
```

#### Response `401 Unauthorized`

```json
{
  "message": "API key can only be used for authentication from whitelisted IP",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a5e",
  "timestamp": 3318215482991
}
```

#### Response `403 Forbidden`

```json
{
  "message": "Forbidden",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a5e",
  "timestamp": 3318215482991
}
```

#### Response `409 Conflict`

```json
{
  "message": "Request timestamp is in the future",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a5e",
  "timestamp": 3318215482991
}
```

#### Response `429 Rate Limit Exceeded`

```json
{
  "message": "Rate Limit Exceeded",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a5e",
  "timestamp": 3318215482991
}
```

#### Response `5XX Server Error`

```json
{
  "message": "Something went wrong!",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a5e",
  "timestamp": 3318215482991
}
```

---

## Configuration

Get Revolut X configuration for traded assets and pairs.

### Get All Currencies

Get configuration for all currencies used on the exchange.

| Property | Value |
|---|---|
| **Method** | `GET` |
| **Path** | `/api/1.0/configuration/currencies` |
| **Auth** | Required |

#### cURL Example

```bash
curl -L -X GET 'https://revx.revolut.com/api/1.0/configuration/currencies' \
  -H 'Accept: application/json' \
  -H 'X-Revx-API-Key: <API_KEY_VALUE>'
```

#### Request

No query parameters. Standard authentication headers required.

#### Response Fields

Each currency entry contains:

| Field | Type | Description |
|---|---|---|
| `symbol` | string | Symbol of the currency (e.g., `"BTC"`). |
| `name` | string | Full name (e.g., `"Bitcoin"`). |
| `scale` | integer | Number of decimal places for the currency's smallest unit (e.g., `8` for BTC = `0.00000001`). |
| `asset_type` | string | `"fiat"` or `"crypto"`. |
| `status` | string | `"active"` or `"inactive"`. |

#### Response `200 OK`

```json
{
  "BTC": {
    "symbol": "BTC",
    "name": "Bitcoin",
    "scale": 8,
    "asset_type": "crypto",
    "status": "active"
  },
  "ETH": {
    "symbol": "ETH",
    "name": "Ethereum",
    "scale": 8,
    "asset_type": "crypto",
    "status": "active"
  }
}
```

#### Response `401 Unauthorized`

```json
{
  "message": "API key can only be used for authentication from whitelisted IP",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `403 Forbidden`

```json
{
  "message": "Forbidden",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `409 Conflict`

```json
{
  "message": "Request timestamp is in the future",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `429 Rate Limit Exceeded`

```json
{
  "message": "Rate Limit Exceeded",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `5XX Server Error`

```json
{
  "message": "Something went wrong!",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d0d03a",
  "timestamp": 3318215482991
}
```

---

### Get All Currency Pairs

Get configuration for all traded currency pairs.

| Property | Value |
|---|---|
| **Method** | `GET` |
| **Path** | `/api/1.0/configuration/pairs` |
| **Auth** | Required |
| **Rate Limit** | 1000 requests/minute |

#### cURL Example

```bash
curl -L -X GET 'https://revx.revolut.com/api/1.0/configuration/pairs' \
  -H 'Accept: application/json' \
  -H 'X-Revx-API-Key: <API_KEY_VALUE>'
```

#### Request

No query parameters. Standard authentication headers required.

#### Response Fields

Each currency pair entry contains:

| Field | Type | Description |
|---|---|---|
| `base` | string | Base currency (e.g., `"BTC"`). |
| `quote` | string | Quote currency (e.g., `"USD"`). |
| `base_step` | string | Minimal step for changing quantity in base currency. |
| `quote_step` | string | Minimal step for changing amount in quote currency. |
| `min_order_size` | string | Minimum order quantity in base currency. |
| `max_order_size` | string | Maximum order quantity in base currency. |
| `min_order_size_quote` | string | Minimum order quantity in quote currency. |
| `status` | string | `"active"` or `"inactive"`. |

#### Response `200 OK`

```json
{
  "BTC/USD": {
    "base": "BTC",
    "quote": "USD",
    "base_step": "0.0000001",
    "quote_step": "0.01",
    "min_order_size": "0.0000001",
    "max_order_size": "1000",
    "min_order_size_quote": "0.01",
    "status": "active"
  },
  "ETH/EUR": {
    "base": "ETH",
    "quote": "EUR",
    "base_step": "0.0000001",
    "quote_step": "0.01",
    "min_order_size": "0.00001",
    "max_order_size": "9000",
    "min_order_size_quote": "0.01",
    "status": "active"
  }
}
```

#### Response `401 Unauthorized`

```json
{
  "message": "API key can only be used for authentication from whitelisted IP",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `403 Forbidden`

```json
{
  "message": "Forbidden",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `409 Conflict`

```json
{
  "message": "Request timestamp is in the future",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `429 Rate Limit Exceeded`

```json
{
  "message": "Rate Limit Exceeded",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `5XX Server Error`

```json
{
  "message": "Something went wrong!",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a5e",
  "timestamp": 3318215482991
}
```

---

## Public Market Data

Get Revolut X real-time public market data. These endpoints do **not** require authentication.

> **Note:** Public Market Data endpoints return data structured for MiFID II / MiCA regulatory compliance (fields like `aid`, `anm`, `p`, `pc`, `pn`, `q`, `qc`, `qn`, `ve`, `vp`, `tid`, `pdt`).

### Get Last Trades (Public)

Get the list of the latest 100 trades executed on the Revolut X crypto exchange.

| Property | Value |
|---|---|
| **Method** | `GET` |
| **Path** | `/api/1.0/public/last-trades` |
| **Auth** | Not required (public) |
| **Rate Limit** | 20 requests per 10 seconds |

#### cURL Example

```bash
curl -L -X GET 'https://revx.revolut.com/api/1.0/public/last-trades' \
  -H 'Accept: application/json'
```

#### Request

No query parameters or authentication headers.

#### Response Fields

| Field | Type | Description |
|---|---|---|
| `data` | array | List of trade records. |
| `data[].tdt` | string (date-time) | Trading date and time (ISO-8601). |
| `data[].aid` | string | Crypto-asset ID code (e.g., `"BTC"`). |
| `data[].anm` | string | Crypto-asset full name (e.g., `"Bitcoin"`). |
| `data[].p` | string | Price in major currency units. |
| `data[].pc` | string | Price currency (e.g., `"USD"`). |
| `data[].pn` | string | Price notation (e.g., `"MONE"`). |
| `data[].q` | string | Quantity. |
| `data[].qc` | string | Quantity currency (e.g., `"BTC"`). |
| `data[].qn` | string | Quantity notation (e.g., `"UNIT"`). |
| `data[].ve` | string | Venue of execution. Always `"REVX"`. |
| `data[].pdt` | string (date-time) | Publication date and time (ISO-8601). |
| `data[].vp` | string | Venue of publication. Always `"REVX"`. |
| `data[].tid` | string | Transaction identification code. |
| `metadata.timestamp` | string (date-time) | Timestamp when data was generated. |

#### Response `200 OK`

```json
{
  "data": [
    {
      "tdt": "2025-08-08T21:40:35.133962Z",
      "aid": "BTC",
      "anm": "Bitcoin",
      "p": "116243.32",
      "pc": "USD",
      "pn": "MONE",
      "q": "0.24521000",
      "qc": "BTC",
      "qn": "UNIT",
      "ve": "REVX",
      "pdt": "2025-08-08T21:40:35.133962Z",
      "vp": "REVX",
      "tid": "5ef9648f658149f7ababedc97a6401f8"
    },
    {
      "tdt": "2025-08-08T21:40:34.132465Z",
      "aid": "ETH",
      "anm": "Ethereum",
      "p": "4028.23",
      "pc": "USDC",
      "pn": "MONE",
      "q": "12.00000000",
      "qc": "ETH",
      "qn": "UNIT",
      "ve": "REVX",
      "pdt": "2025-08-08T21:40:34.132465Z",
      "vp": "REVX",
      "tid": "3b2b202b766843cfa6c8b3354e7f4c52"
    }
  ],
  "metadata": {
    "timestamp": "2025-08-08T21:40:36.684333Z"
  }
}
```

#### Response `429 Rate Limit Exceeded`

```json
{
  "message": "Rate Limit Exceeded",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `5XX Server Error`

```json
{
  "message": "Something went wrong!",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

---

### Get Order Book (Public)

Fetch the current order book (bids and asks) for a given trading pair (maximum 5 price levels).

| Property | Value |
|---|---|
| **Method** | `GET` |
| **Path** | `/api/1.0/public/order-book/{symbol}` |
| **Auth** | Not required (public) |

#### cURL Example

```bash
curl -L -g -X GET 'https://revx.revolut.com/api/1.0/public/order-book/{symbol}' \
  -H 'Accept: application/json'
```

#### Path Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `symbol` | string | Yes | Trading pair (e.g., `"BTC-USD"`). |

#### Response `200 OK`

```json
{
  "data": {
    "asks": [
      {
        "aid": "ETH",
        "anm": "Ethereum",
        "s": "SELL",
        "p": "4600",
        "pc": "USD",
        "pn": "MONE",
        "q": "17",
        "qc": "ETH",
        "qn": "UNIT",
        "ve": "REVX",
        "no": "3",
        "ts": "CLOB",
        "pdt": "2025-08-08T21:40:36.124538Z"
      },
      {
        "aid": "ETH",
        "anm": "Ethereum",
        "s": "SELL",
        "p": "4555",
        "pc": "USD",
        "pn": "MONE",
        "q": "2.1234",
        "qc": "ETH",
        "qn": "UNIT",
        "ve": "REVX",
        "no": "2",
        "ts": "CLOB",
        "pdt": "2025-08-08T21:40:36.124538Z"
      }
    ],
    "bids": [
      {
        "aid": "ETH",
        "anm": "Ethereum",
        "s": "BUYI",
        "p": "4550",
        "pc": "USD",
        "pn": "MONE",
        "q": "0.25",
        "qc": "ETH",
        "qn": "UNIT",
        "ve": "REVX",
        "no": "1",
        "ts": "CLOB",
        "pdt": "2025-08-08T21:40:36.124538Z"
      },
      {
        "aid": "ETH",
        "anm": "Ethereum",
        "s": "BUYI",
        "p": "4500",
        "pc": "USD",
        "pn": "MONE",
        "q": "24.42",
        "qc": "ETH",
        "qn": "UNIT",
        "ve": "REVX",
        "no": "5",
        "ts": "CLOB",
        "pdt": "2025-08-08T21:40:36.124538Z"
      }
    ]
  },
  "metadata": {
    "timestamp": "2025-08-08T21:40:36.124538Z"
  }
}
```

#### Response `429 Rate Limit Exceeded`

```json
{
  "message": "Rate Limit Exceeded",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `5XX Server Error`

```json
{
  "message": "Something went wrong!",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

#### Order Book Entry Fields

| Field | Type | Description |
|---|---|---|
| `aid` | string | Crypto-asset ID code. |
| `anm` | string | Crypto-asset full name. |
| `s` | string | Side: `"SELL"` or `"BUYI"`. |
| `p` | string | Price in major currency units. |
| `pc` | string | Price currency. |
| `pn` | string | Price notation (`"MONE"`). |
| `q` | string | Aggregated quantity at this price level. |
| `qc` | string | Quantity currency. |
| `qn` | string | Quantity notation (`"UNIT"`). |
| `ve` | string | Venue of execution (`"REVX"`). |
| `no` | string | Number of orders at the price level. |
| `ts` | string | Trading system (`"CLOB"`). |
| `pdt` | string (date-time) | Publication date and time. |

---

## Orders

Manage Revolut X orders: place new orders, cancel active ones, and retrieve order history.

### Place Order

Place a new order. The user is resolved by the provided API key.

| Property | Value |
|---|---|
| **Method** | `POST` |
| **Path** | `/api/1.0/orders` |
| **Auth** | Required |
| **Rate Limit** | 1000 requests/minute |

#### cURL Example

```bash
curl -L -X POST 'https://revx.revolut.com/api/1.0/orders' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -H 'X-Revx-API-Key: <API_KEY_VALUE>' \
  --data-raw '{
    "client_order_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "symbol": "BTC-USD",
    "side": "sell",
    "order_configuration": {
      "limit": {
        "base_size": "0.1",
        "price": "50000.50",
        "execution_instructions": ["post_only"]
      }
    }
  }'
```

#### Request Body

| Parameter | Type | Required | Description |
|---|---|---|---|
| `client_order_id` | string (uuid) | Yes | Unique identifier for idempotency. |
| `symbol` | string | Yes | Trading pair symbol (e.g., `"BTC-USD"`). |
| `side` | string | Yes | Order direction: `"buy"` or `"sell"`. |
| `order_configuration` | object | Yes | Must contain exactly one of `limit` or `market`. |

##### `order_configuration.limit` Object

A limit order is executed only if the asset reaches the specified price.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `base_size` | string (decimal) | One of `base_size` or `quote_size` | Amount of base currency. |
| `quote_size` | string (decimal) | One of `base_size` or `quote_size` | Amount of quote currency. |
| `price` | string (decimal) | Yes | The limit price. |
| `execution_instructions` | array of strings | No | Default: `["allow_taker"]`. Values: `"allow_taker"`, `"post_only"`. |

##### `order_configuration.market` Object

A market order is executed immediately at the current market price.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `base_size` | string (decimal) | One of `base_size` or `quote_size` | Amount of base currency. |
| `quote_size` | string (decimal) | One of `base_size` or `quote_size` | Amount of quote currency. |

#### Response `200 OK`

```json
{
  "data": [
    {
      "venue_order_id": "7a52e92e-8639-4fe1-abaa-68d3a2d5234b",
      "client_order_id": "984a4d8a-2a9b-4950-822f-2a40037f02bd",
      "state": "new"
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `data[].venue_order_id` | string (uuid) | System-generated order ID. |
| `data[].client_order_id` | string (uuid) | Client-provided order ID. |
| `data[].state` | string | Order state. See [Order Statuses](#order-statuses). |

#### Response `400 Bad Request`

```json
{
  "message": "No such pair: BTC-BTC",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `401 Unauthorized`

```json
{
  "message": "API key can only be used for authentication from whitelisted IP",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `403 Forbidden`

```json
{
  "message": "Forbidden",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `409 Conflict`

```json
{
  "message": "Request timestamp is in the future",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `429 Rate Limit Exceeded`

```json
{
  "message": "Rate Limit Exceeded",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `5XX Server Error`

```json
{
  "message": "Something went wrong!",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d0d03a",
  "timestamp": 3318215482991
}
```

---

### Cancel All Active Orders

Cancel all open limit, conditional, and Take Profit/Stop Loss (TPSL) orders associated with the authenticated account.

| Property | Value |
|---|---|
| **Method** | `DELETE` |
| **Path** | `/api/1.0/orders` |
| **Auth** | Required |

#### cURL Example

```bash
curl -L -X DELETE 'https://revx.revolut.com/api/1.0/orders' \
  -H 'X-Revx-API-Key: <API_KEY_VALUE>'
```

#### Request

No query parameters or body. Standard authentication headers required.

#### Response `204 No Content`

This response does not have a body. Orders cancelled successfully.

#### Response `401 Unauthorized`

```json
{
  "message": "API key can only be used for authentication from whitelisted IP",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `403 Forbidden`

```json
{
  "message": "Forbidden",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `409 Conflict`

```json
{
  "message": "Request timestamp is in the future",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `429 Rate Limit Exceeded`

```json
{
  "message": "Rate Limit Exceeded",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `5XX Server Error`

```json
{
  "message": "Something went wrong!",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

---

### Get Active Orders

Get active crypto exchange orders for the requesting user.

| Property | Value |
|---|---|
| **Method** | `GET` |
| **Path** | `/api/1.0/orders/active` |
| **Auth** | Required |

#### cURL Example

```bash
curl -L -X GET 'https://revx.revolut.com/api/1.0/orders/active' \
  -H 'Accept: application/json' \
  -H 'X-Revx-API-Key: <API_KEY_VALUE>'
```

#### Query Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `symbols` | string | No | Filter by currency pairs (comma-separated, e.g., `"BTC-USD,ETH-USD"`). |
| `states` | string | No | Filter by states. Values: `pending_new`, `new`, `partially_filled`. |
| `types` | string | No | Filter by order types. Values: `limit`, `conditional`, `tpsl`. |
| `sides` | string | No | Filter by direction. Values: `buy`, `sell`. |
| `cursor` | string | No | Pagination cursor from `metadata.next_cursor`. |
| `limit` | integer | No | Max records. Range: 1–100. Default: `100`. |

#### Response `200 OK`

```json
{
  "data": [
    {
      "id": "7a52e92e-8639-4fe1-abaa-68d3a2d5234b",
      "client_order_id": "984a4d8a-2a9b-4950-822f-2a40037f02bd",
      "symbol": "BTC/USD",
      "side": "buy",
      "type": "limit",
      "quantity": "0.002",
      "filled_quantity": "0",
      "leaves_quantity": "0.002",
      "price": "98745",
      "status": "new",
      "time_in_force": "gtc",
      "execution_instructions": ["allow_taker"],
      "created_date": 3318215482991,
      "updated_date": 3318215482991
    }
  ],
  "metadata": {
    "timestamp": 3318215482991,
    "next_cursor": "GF0ZT0xNzY0OTMxNTAyODU0O2lkPTM3YjExMWJlLTcwMzYtNGYzNC1hYWYyLTM4ZDVjYTEyN2M1Yw=="
  }
}
```

#### Order Object Fields

| Field | Type | Description |
|---|---|---|
| `id` | string (uuid) | System-generated order ID. |
| `replaced_by` | string | ID of the replacement order (if replaced). |
| `client_order_id` | string (uuid) | Client-provided order ID. |
| `symbol` | string | Trading pair symbol. |
| `side` | string | `"buy"` or `"sell"`. |
| `type` | string | `"market"`, `"limit"`, `"conditional"`, or `"tpsl"`. |
| `quantity` | string | Order quantity in base currency. |
| `filled_quantity` | string | Amount already executed. |
| `leaves_quantity` | string | Amount remaining. |
| `quote_quantity` | string | Order amount in quote currency. |
| `price` | string | Limit price (worst acceptable price). |
| `average_fill_price` | string | Quantity-weighted average fill price. |
| `status` | string | See [Order Statuses](#order-statuses). |
| `reject_reason` | string | Rejection reason (only when `status=rejected`). |
| `time_in_force` | string | See [Time in Force](#time-in-force). |
| `execution_instructions` | array | `["allow_taker"]` (default) or `["post_only"]`. |
| `trigger` | object | Trigger conditions (only for `type=conditional`). See [Trigger Object](#trigger-object). |
| `take_profit` | object | Take Profit details (only for `type=tpsl`). See [Trigger Object](#trigger-object). |
| `stop_loss` | object | Stop Loss details (only for `type=tpsl`). See [Trigger Object](#trigger-object). |
| `created_date` | integer | Creation timestamp (Unix epoch ms). |
| `updated_date` | integer | Last update timestamp (Unix epoch ms). |
| `completed_date` | integer | Completion timestamp (Unix epoch ms). |

#### Response `400 Bad Request`

```json
{
  "message": "No such pair: BTC-BTC",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `401 Unauthorized`

```json
{
  "message": "API key can only be used for authentication from whitelisted IP",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `403 Forbidden`

```json
{
  "message": "Forbidden",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `409 Conflict`

```json
{
  "message": "Request timestamp is in the future",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `429 Too Many Requests`

```json
{
  "message": "Rate Limit Exceeded",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `5XX Server Error`

```json
{
  "message": "Something went wrong!",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d0d03a",
  "timestamp": 3318215482991
}
```

---

### Get Historical Orders

Get historical (completed) crypto exchange orders for the requesting user.

| Property | Value |
|---|---|
| **Method** | `GET` |
| **Path** | `/api/1.0/orders/historical` |
| **Auth** | Required |

#### cURL Example

```bash
curl -L -X GET 'https://revx.revolut.com/api/1.0/orders/historical' \
  -H 'Accept: application/json' \
  -H 'X-Revx-API-Key: <API_KEY_VALUE>'
```

#### Query Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `symbols` | string | No | Filter by currency pairs (comma-separated). |
| `states` | string | No | Filter by states. Values: `filled`, `cancelled`, `rejected`, `replaced`. |
| `types` | string | No | Filter by types. Values: `market`, `limit`. |
| `start_date` | integer | No | Start timestamp (Unix epoch ms). Defaults to 7 days before `end_date`. |
| `end_date` | integer | No | End timestamp (Unix epoch ms). Defaults to current time or `start_date` + 7 days. |
| `cursor` | string | No | Pagination cursor. |
| `limit` | integer | No | Max records. Range: 1–100. Default: `100`. |

> The difference between `start_date` and `end_date` must be <= 30 days.

#### Response `200 OK`

```json
{
  "data": [
    {
      "id": "7a52e92e-8639-4fe1-abaa-68d3a2d5234b",
      "client_order_id": "984a4d8a-2a9b-4950-822f-2a40037f02bd",
      "symbol": "BTC/USD",
      "side": "buy",
      "type": "limit",
      "quantity": "0.002",
      "filled_quantity": "0",
      "leaves_quantity": "0.002",
      "price": "98745",
      "status": "filled",
      "time_in_force": "gtc",
      "execution_instructions": ["allow_taker"],
      "created_date": 3318215482991,
      "updated_date": 3318215482991
    }
  ],
  "metadata": {
    "timestamp": 3318215482991,
    "next_cursor": "GF0ZT0xNzY0OTMxNTAyODU0O2lkPTM3YjExMWJlLTcwMzYtNGYzNC1hYWYyLTM4ZDVjYTEyN2M1Yw=="
  }
}
```

Same order object structure as [Get Active Orders](#get-active-orders).

#### Response `400 Bad Request`

```json
{
  "message": "No such pair: BTC-BTC",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `401 Unauthorized`

```json
{
  "message": "API key can only be used for authentication from whitelisted IP",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `403 Forbidden`

```json
{
  "message": "Forbidden",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `409 Conflict`

```json
{
  "message": "Request timestamp is in the future",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `429 Rate Limit Exceeded`

```json
{
  "message": "Rate Limit Exceeded",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `5XX Server Error`

```json
{
  "message": "Something went wrong!",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

---

### Get Order by ID

Retrieve specific order details by ID.

| Property | Value |
|---|---|
| **Method** | `GET` |
| **Path** | `/api/1.0/orders/{venue_order_id}` |
| **Auth** | Required |

#### cURL Example

```bash
curl -L -g -X GET 'https://revx.revolut.com/api/1.0/orders/{venue_order_id}' \
  -H 'Accept: application/json' \
  -H 'X-Revx-API-Key: <API_KEY_VALUE>'
```

#### Path Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `venue_order_id` | string (uuid) | Yes | Unique identifier of the venue order. |

#### Response `200 OK`

```json
{
  "data": {
    "id": "7a52e92e-8639-4fe1-abaa-68d3a2d5234b",
    "client_order_id": "984a4d8a-2a9b-4950-822f-2a40037f02bd",
    "symbol": "BTC/USD",
    "side": "buy",
    "type": "limit",
    "quantity": "0.002",
    "filled_quantity": "0",
    "leaves_quantity": "0.002",
    "price": "98745",
    "average_fill_price": "89794.51",
    "status": "new",
    "time_in_force": "gtc",
    "execution_instructions": ["allow_taker"],
    "created_date": 3318215482991,
    "updated_date": 3318215482991
  }
}
```

> Note: Single order response wraps in `data` object (not array).

#### Response `400 Bad Request`

```json
{
  "message": "No such pair: BTC-BTC",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a5e",
  "timestamp": 3318215482991
}
```

#### Response `401 Unauthorized`

```json
{
  "message": "API key can only be used for authentication from whitelisted IP",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a5e",
  "timestamp": 3318215482991
}
```

#### Response `403 Forbidden`

```json
{
  "message": "Forbidden",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a5e",
  "timestamp": 3318215482991
}
```

#### Response `404 Not Found`

```json
{
  "message": "Order with ID '7d85b5e7-d0f0-4696-b7b5-a300d0d03a5e' not found",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a5e",
  "timestamp": 3318215482991
}
```

#### Response `409 Conflict`

```json
{
  "message": "Request timestamp is in the future",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a5e",
  "timestamp": 3318215482991
}
```

#### Response `429 Rate Limit Exceeded`

```json
{
  "message": "Rate Limit Exceeded",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a5e",
  "timestamp": 3318215482991
}
```

#### Response `5XX Server Error`

```json
{
  "message": "Something went wrong!",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a5e",
  "timestamp": 3318215482991
}
```

---

### Cancel Order by ID

Cancel an active order by its Venue ID.

| Property | Value |
|---|---|
| **Method** | `DELETE` |
| **Path** | `/api/1.0/orders/{venue_order_id}` |
| **Auth** | Required |

#### cURL Example

```bash
curl -L -g -X DELETE 'https://revx.revolut.com/api/1.0/orders/{venue_order_id}' \
  -H 'X-Revx-API-Key: <API_KEY_VALUE>'
```

#### Path Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `venue_order_id` | string (uuid) | Yes | Unique identifier of the venue order. |

#### Response `204 No Content`

This response does not have a body. Order deleted successfully.

#### Response `400 Bad Request`

```json
{
  "message": "No such pair: BTC-BTC",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `401 Unauthorized`

```json
{
  "message": "API key can only be used for authentication from whitelisted IP",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `403 Forbidden`

```json
{
  "message": "Forbidden",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `404 Not Found`

```json
{
  "message": "Order with ID '7d85b5e7-d0f0-4696-b7b5-a300d0d03a' not found",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `409 Conflict`

```json
{
  "message": "Request timestamp is in the future",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `429 Rate Limit Exceeded`

```json
{
  "message": "Rate Limit Exceeded",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `5XX Server Error`

```json
{
  "message": "Something went wrong!",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

---

### Get Fills of Order by ID

Retrieve the fills (trades) associated with a specific order belonging to the client.

| Property | Value |
|---|---|
| **Method** | `GET` |
| **Path** | `/api/1.0/orders/fills/{venue_order_id}` |
| **Auth** | Required |

#### cURL Example

```bash
curl -L -g -X GET 'https://revx.revolut.com/api/1.0/orders/fills/{venue_order_id}' \
  -H 'Accept: application/json' \
  -H 'X-Revx-API-Key: <API_KEY_VALUE>'
```

#### Path Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `venue_order_id` | string (uuid) | Yes | Unique identifier of the venue order. |

#### Response `200 OK`

```json
{
  "data": [
    {
      "tdt": 3318215482991,
      "aid": "BTC",
      "anm": "Bitcoin",
      "p": "91686.16",
      "pc": "USD",
      "pn": "MONE",
      "q": "24.90000000",
      "qc": "BTC",
      "qn": "UNIT",
      "ve": "REVX",
      "pdt": 3318215482991,
      "vp": "REVX",
      "tid": "ad3e8787ab623ba5a1dfea53819be6f9",
      "oid": "2affb2ac-4cf7-4bbf-b7b2-fc1e885bdc2c",
      "s": "buy",
      "im": false
    }
  ]
}
```

#### Fill Object Fields

| Field | Type | Description |
|---|---|---|
| `tdt` | integer | Trade date/time (Unix epoch ms). |
| `aid` | string | Crypto-asset ID code (e.g., `"BTC"`). |
| `anm` | string | Crypto-asset full name. |
| `p` | string | Price in major currency units. |
| `pc` | string | Price currency. |
| `pn` | string | Price notation (`"MONE"`). |
| `q` | string | Quantity. |
| `qc` | string | Quantity currency. |
| `qn` | string | Quantity notation (`"UNIT"`). |
| `ve` | string | Venue of execution (`"REVX"`). |
| `pdt` | integer | Publication date/time (Unix epoch ms). |
| `vp` | string | Venue of publication (`"REVX"`). |
| `tid` | string | Transaction identification code. |
| `oid` | string (uuid) | Order ID associated with the trade. |
| `s` | string | Trade direction: `"buy"` or `"sell"`. |
| `im` | boolean | Maker indicator. `true` = maker, `false` = taker. |

#### Response `400 Bad Request`

```json
{
  "message": "No such pair: BTC-BTC",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `401 Unauthorized`

```json
{
  "message": "API key can only be used for authentication from whitelisted IP",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `403 Forbidden`

```json
{
  "message": "Forbidden",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `404 Not Found`

```json
{
  "message": "Order with ID '7d85b5e7-d0f0-4696-b7b5-a300d0d0d03a' not found",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `409 Conflict`

```json
{
  "message": "Request timestamp is in the future",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `429 Rate Limit Exceeded`

```json
{
  "message": "Rate Limit Exceeded",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `5XX Server Error`

```json
{
  "message": "Something went wrong!",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d0d03a",
  "timestamp": 3318215482991
}
```

---

## Trades

Retrieve Revolut X trade history and execution details.

### Get All Public Trades

Retrieve a list of all trades for a specific symbol (not limited to the current client).

| Property | Value |
|---|---|
| **Method** | `GET` |
| **Path** | `/api/1.0/trades/all/{symbol}` |
| **Auth** | Required |

#### cURL Example

```bash
curl -L -g -X GET 'https://revx.revolut.com/api/1.0/trades/all/{symbol}' \
  -H 'Accept: application/json' \
  -H 'X-Revx-API-Key: <API_KEY_VALUE>'
```

#### Path Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `symbol` | string | Yes | Trading pair symbol (e.g., `"BTC-USD"`). |

#### Query Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `start_date` | integer | No | Start timestamp (Unix epoch ms). Defaults to 7 days before `end_date`. |
| `end_date` | integer | No | End timestamp (Unix epoch ms). Max range: 30 days. |
| `cursor` | string | No | Pagination cursor. |
| `limit` | integer | No | Max records. Range: 1–100. Default: `100`. |

#### Response `200 OK`

```json
{
  "data": [
    {
      "tdt": 3318215482991,
      "aid": "BTC",
      "anm": "Bitcoin",
      "p": "125056.76",
      "pc": "USD",
      "pn": "MONE",
      "q": "0.00003999",
      "qc": "BTC",
      "qn": "UNIT",
      "ve": "REVX",
      "pdt": 3318215482991,
      "vp": "REVX",
      "tid": "80654a036323311cb0ea28462b42db6d"
    }
  ],
  "metadata": {
    "timestamp": 3318215482991,
    "next_cursor": "GF0ZT0xNzY0OTMxNTAyODU0O2lkPTM3YjExMWJlLTcwMzYtNGYzNC1hYWYyLTM4ZDVjYTEyN2M1Yw=="
  }
}
```

#### Trade Object Fields

| Field | Type | Description |
|---|---|---|
| `tdt` | integer | Trade date/time (Unix epoch ms). |
| `aid` | string | Crypto-asset ID code. |
| `anm` | string | Crypto-asset full name. |
| `p` | string | Price in major currency units. |
| `pc` | string | Price currency. |
| `pn` | string | Price notation. |
| `q` | string | Quantity. |
| `qc` | string | Quantity currency. |
| `qn` | string | Quantity notation. |
| `ve` | string | Venue of execution (`"REVX"`). |
| `pdt` | integer | Publication date/time (Unix epoch ms). |
| `vp` | string | Venue of publication (`"REVX"`). |
| `tid` | string | Transaction identification code. |

#### Response `400 Bad Request`

```json
{
  "message": "No such pair: BTC-BTC",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a5e",
  "timestamp": 3318215482991
}
```

#### Response `401 Unauthorized`

```json
{
  "message": "API key can only be used for authentication from whitelisted IP",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a5e",
  "timestamp": 3318215482991
}
```

#### Response `403 Forbidden`

```json
{
  "message": "Forbidden",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a5e",
  "timestamp": 3318215482991
}
```

#### Response `409 Conflict`

```json
{
  "message": "Request timestamp is in the future",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a5e",
  "timestamp": 3318215482991
}
```

#### Response `429 Rate Limit Exceeded`

```json
{
  "message": "Rate Limit Exceeded",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a5e",
  "timestamp": 3318215482991
}
```

#### Response `5XX Server Error`

```json
{
  "message": "Something went wrong!",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a5e",
  "timestamp": 3318215482991
}
```

---

### Get Client Trades

Retrieve the trade history (fills) for the authenticated client.

| Property | Value |
|---|---|
| **Method** | `GET` |
| **Path** | `/api/1.0/trades/private/{symbol}` |
| **Auth** | Required |

#### cURL Example

```bash
curl -L -g -X GET 'https://revx.revolut.com/api/1.0/trades/private/{symbol}' \
  -H 'Accept: application/json' \
  -H 'X-Revx-API-Key: <API_KEY_VALUE>'
```

#### Path Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `symbol` | string | Yes | Trading pair symbol (e.g., `"BTC-USD"`). |

#### Query Parameters

Same as [Get All Public Trades](#get-all-public-trades).

#### Response `200 OK`

```json
{
  "data": [
    {
      "tdt": 3318215482991,
      "aid": "BTC",
      "anm": "Bitcoin",
      "p": "125056.76",
      "pc": "USD",
      "pn": "MONE",
      "q": "0.00003999",
      "qc": "BTC",
      "qn": "UNIT",
      "ve": "REVX",
      "pdt": 3318215482991,
      "vp": "REVX",
      "tid": "80654a036323311cb0ea28462b42db6d",
      "oid": "2affb2ac-4cf7-4bbf-b7b2-fc1e885bdc2c",
      "s": "buy",
      "im": false
    }
  ],
  "metadata": {
    "timestamp": 3318215482991,
    "next_cursor": "GF0ZT0xNzY0OTMxNTAyODU0O2lkPTM3YjExMWJlLTcwMzYtNGYzNC1hYWYyLTM4ZDVjYTEyN2M1Yw=="
  }
}
```

Same fields as public trades, plus:

| Field | Type | Description |
|---|---|---|
| `oid` | string (uuid) | Order ID associated with the trade. |
| `s` | string | Trade direction: `"buy"` or `"sell"`. |
| `im` | boolean | Maker indicator. `true` = maker, `false` = taker. |

#### Response `400 Bad Request`

```json
{
  "message": "No such pair: BTC-BTC",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a5e",
  "timestamp": 3318215482991
}
```

#### Response `401 Unauthorized`

```json
{
  "message": "API key can only be used for authentication from whitelisted IP",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a5e",
  "timestamp": 3318215482991
}
```

#### Response `403 Forbidden`

```json
{
  "message": "Forbidden",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a5e",
  "timestamp": 3318215482991
}
```

#### Response `409 Conflict`

```json
{
  "message": "Request timestamp is in the future",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a5e",
  "timestamp": 3318215482991
}
```

#### Response `429 Rate Limit Exceeded`

```json
{
  "message": "Rate Limit Exceeded",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a5e",
  "timestamp": 3318215482991
}
```

#### Response `5XX Server Error`

```json
{
  "message": "Something went wrong!",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a5e",
  "timestamp": 3318215482991
}
```

---

## Market Data

Retrieve real-time and historical market data for Revolut X (authenticated endpoints).

### Get Order Book Snapshot

Retrieve the current order book snapshot (bids and asks) for a specific trading pair.

| Property | Value |
|---|---|
| **Method** | `GET` |
| **Path** | `/api/1.0/order-book/{symbol}` |
| **Auth** | Required |
| **Rate Limit** | 1000 requests/minute |

#### cURL Example

```bash
curl -L -g -X GET 'https://revx.revolut.com/api/1.0/order-book/{symbol}' \
  -H 'Accept: application/json' \
  -H 'X-Revx-API-Key: <API_KEY_VALUE>'
```

#### Path Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `symbol` | string | Yes | Trading pair (e.g., `"BTC-USD"`). |

#### Query Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `depth` | integer | No | Depth of order book (1–20). Default: `20`. |

#### Response `200 OK`

```json
{
  "data": {
    "asks": [
      {
        "aid": "ETH",
        "anm": "Ethereum",
        "s": "SELL",
        "p": "4600",
        "pc": "USD",
        "pn": "MONE",
        "q": "17",
        "qc": "ETH",
        "qn": "UNIT",
        "ve": "REVX",
        "no": "3",
        "ts": "CLOB",
        "pdt": 3318215482991
      },
      {
        "aid": "ETH",
        "anm": "Ethereum",
        "s": "SELL",
        "p": "4555",
        "pc": "USD",
        "pn": "MONE",
        "q": "2.1234",
        "qc": "ETH",
        "qn": "UNIT",
        "ve": "REVX",
        "no": "2",
        "ts": "CLOB",
        "pdt": 3318215482991
      }
    ],
    "bids": [
      {
        "aid": "ETH",
        "anm": "Ethereum",
        "s": "BUY",
        "p": "4500",
        "pc": "USD",
        "pn": "MONE",
        "q": "1.5",
        "qc": "ETH",
        "qn": "UNIT",
        "ve": "REVX",
        "no": "1",
        "ts": "CLOB",
        "pdt": 3318215482991
      }
    ]
  },
  "metadata": {
    "ts": 3318215482991
  }
}
```

#### Response `400 Bad Request`

```json
{
  "message": "No such pair: BTC-BTC",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `401 Unauthorized`

```json
{
  "message": "API key can only be used for authentication from whitelisted IP",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `403 Forbidden`

```json
{
  "message": "Forbidden",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `409 Conflict`

```json
{
  "message": "Request timestamp is in the future",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `429 Rate Limit Exceeded`

```json
{
  "message": "Rate Limit Exceeded",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `5XX Server Error`

```json
{
  "message": "Something went wrong!",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

---

### Get Historical OHLCV Candles

Retrieve historical market data (Open, High, Low, Close, Volume) for a specific symbol.

If there is trading volume, the view is based on recent trades. If there is no volume, the view is based on the Mid Price (Bid/Ask average).

| Property | Value |
|---|---|
| **Method** | `GET` |
| **Path** | `/api/1.0/candles/{symbol}` |
| **Auth** | Required |

#### cURL Example

```bash
curl -L -g -X GET 'https://revx.revolut.com/api/1.0/candles/{symbol}' \
  -H 'Accept: application/json' \
  -H 'X-Revx-API-Key: <API_KEY_VALUE>'
```

#### Path Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `symbol` | string | Yes | Trading pair (e.g., `"BTC-USD"`). |

#### Query Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `interval` | integer | No | Candle interval in minutes. Default: `5`. Possible values: `1`, `5`, `15`, `30`, `60`, `240`, `1440`, `2880`, `5760`, `10080`, `20160`, `40320`. |
| `since` | integer | No | Start timestamp (Unix epoch ms). Default: `end - (interval * 100)`. |
| `until` | integer | No | End timestamp (Unix epoch ms). Default: current timestamp. |

> The total number of candles calculated by `(until - since) / interval` must not exceed 1000.

#### Interval Reference

| Value | Meaning |
|---|---|
| `1` | 1 minute |
| `5` | 5 minutes |
| `15` | 15 minutes |
| `30` | 30 minutes |
| `60` | 1 hour |
| `240` | 4 hours |
| `1440` | 1 day |
| `2880` | 2 days |
| `5760` | 4 days |
| `10080` | 1 week |
| `20160` | 2 weeks |
| `40320` | 4 weeks |

#### Response `200 OK`

```json
{
  "data": [
    {
      "start": 3318215482991,
      "open": "92087.81",
      "high": "92133.89",
      "low": "92052.39",
      "close": "92067.31",
      "volume": "0.00067964"
    },
    {
      "start": 3318215782991,
      "open": "90390.46",
      "high": "90395",
      "low": "90358.84",
      "close": "90395",
      "volume": "0.00230816"
    }
  ]
}
```

#### Candle Object Fields

| Field | Type | Description |
|---|---|---|
| `start` | integer | Start timestamp of the candle (Unix epoch ms). |
| `open` | string | Opening price. |
| `high` | string | Highest price during the interval. |
| `low` | string | Lowest price during the interval. |
| `close` | string | Closing price. |
| `volume` | string | Total trading volume during the interval. |

#### Response `400 Bad Request`

```json
{
  "message": "No such pair: BTC-BTC",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `401 Unauthorized`

```json
{
  "message": "API key can only be used for authentication from whitelisted IP",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `403 Forbidden`

```json
{
  "message": "Forbidden",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `409 Conflict`

```json
{
  "message": "Request timestamp is in the future",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `429 Rate Limit Exceeded`

```json
{
  "message": "Rate Limit Exceeded",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `5XX Server Error`

```json
{
  "message": "Something went wrong!",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d0d03a",
  "timestamp": 3318215482991
}
```

---

### Get All Tickers

Retrieve the latest market data snapshots for all supported currency pairs.

| Property | Value |
|---|---|
| **Method** | `GET` |
| **Path** | `/api/1.0/tickers` |
| **Auth** | Required |

#### cURL Example

```bash
curl -L -X GET 'https://revx.revolut.com/api/1.0/tickers' \
  -H 'Accept: application/json' \
  -H 'X-Revx-API-Key: <API_KEY_VALUE>'
```

#### Query Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `symbols` | string | No | Filter by currency pairs (comma-separated). |

#### Response `200 OK`

```json
{
  "data": [
    {
      "symbol": "BTC/USD",
      "bid": "65100.50",
      "ask": "65101.00",
      "mid": "65100.75",
      "last_price": "65101.00"
    },
    {
      "symbol": "ETH/USD",
      "bid": "4028.10",
      "ask": "4028.50",
      "mid": "4028.30",
      "last_price": "4028.50"
    }
  ],
  "metadata": {
    "timestamp": 1770201294631
  }
}
```

#### Ticker Object Fields

| Field | Type | Description |
|---|---|---|
| `symbol` | string | Currency pair (e.g., `"BTC/USD"`). |
| `bid` | string | Best bid price (highest buy). |
| `ask` | string | Best ask price (lowest sell). |
| `mid` | string | Mid-price: `(bid + ask) / 2`. |
| `last_price` | string | Last traded price. |

#### Response `400 Bad Request`

```json
{
  "message": "No such pair: BTC-BTC",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `401 Unauthorized`

```json
{
  "message": "API key can only be used for authentication from whitelisted IP",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `403 Forbidden`

```json
{
  "message": "Forbidden",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `429 Rate Limit Exceeded`

```json
{
  "message": "Rate Limit Exceeded",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

#### Response `5XX Server Error`

```json
{
  "message": "Something went wrong!",
  "error_id": "7d85b5e7-d0f0-4696-b7b5-a300d0d03a",
  "timestamp": 3318215482991
}
```

---

## Common Data Models

### Order Statuses

| Status | Description |
|---|---|
| `pending_new` | Accepted by matching engine but not yet working. |
| `new` | Working order. |
| `partially_filled` | Partially filled order. |
| `filled` | Fully filled order. |
| `cancelled` | Cancelled order. |
| `rejected` | Rejected order. |
| `replaced` | Replaced order. |

### Time in Force

| Value | Description |
|---|---|
| `gtc` | Good Till Cancelled — stays active until filled or manually cancelled. |
| `ioc` | Immediate or Cancel — any portion not filled immediately is cancelled. |
| `fok` | Fill or Kill — must be filled entirely and immediately, or cancelled (no partial fills). |

### Execution Instructions

| Value | Description |
|---|---|
| `allow_taker` | Default. Order may be filled as taker. |
| `post_only` | Order will only be placed as a maker order. Rejected if it would match immediately. |

### Order Types

| Type | Description |
|---|---|
| `market` | Executed immediately at the current market price. |
| `limit` | Executed only if the asset reaches the specified price. |
| `conditional` | Submitted only when a specific trigger price is reached. |
| `tpsl` | Sets or adjusts Take Profit and Stop Loss settings for a position. |

### Trigger Object

Used in `conditional`, `take_profit`, and `stop_loss` fields:

| Field | Type | Description |
|---|---|---|
| `trigger_price` | string | The price that activates the order. |
| `type` | string | `"market"` or `"limit"`. |
| `trigger_direction` | string | `"ge"` (greater than or equal) or `"le"` (less than or equal). |
| `price` | string | Execution price (required for limit orders). |
| `time_in_force` | string | `"gtc"` or `"ioc"`. |
| `execution_instructions` | array | `["allow_taker"]` or `["post_only"]`. |

---

## Endpoint Summary

| Method | Path | Description | Auth | Rate Limit |
|---|---|---|---|---|
| `GET` | `/balances` | Get all balances | Yes | — |
| `GET` | `/configuration/currencies` | Get all currencies | Yes | — |
| `GET` | `/configuration/pairs` | Get all currency pairs | Yes | 1000/min |
| `GET` | `/public/last-trades` | Get last 100 public trades | No | 20/10s |
| `GET` | `/public/order-book/{symbol}` | Get public order book (5 levels) | No | — |
| `POST` | `/orders` | Place order | Yes | 1000/min |
| `DELETE` | `/orders` | Cancel all active orders | Yes | — |
| `GET` | `/orders/active` | Get active orders | Yes | — |
| `GET` | `/orders/historical` | Get historical orders | Yes | — |
| `GET` | `/orders/{venue_order_id}` | Get order by ID | Yes | — |
| `DELETE` | `/orders/{venue_order_id}` | Cancel order by ID | Yes | — |
| `GET` | `/orders/fills/{venue_order_id}` | Get fills of order by ID | Yes | — |
| `GET` | `/trades/all/{symbol}` | Get all public trades | Yes | — |
| `GET` | `/trades/private/{symbol}` | Get client trades | Yes | — |
| `GET` | `/order-book/{symbol}` | Get order book snapshot (20 levels) | Yes | 1000/min |
| `GET` | `/candles/{symbol}` | Get historical OHLCV candles | Yes | — |
| `GET` | `/tickers` | Get all tickers | Yes | — |

> All paths are relative to the base URL: `https://revx.revolut.com/api/1.0`

---

**Source:** [Revolut X Crypto Exchange REST API Documentation](https://developer.revolut.com/docs/x-api/revolut-x-crypto-exchange-rest-api)  
**Fetched:** March 18, 2026
