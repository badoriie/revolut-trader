"""Unit tests for RevolutAPIClient — all 17 endpoints.

Coverage goals per endpoint:
  ✓ Correct HTTP method + URL path
  ✓ All optional params included when provided, omitted when absent
  ✓ Default param values sent correctly
  ✓ Response correctly parsed / data-envelope unwrapped
  ✓ HTTP errors raised as RevolutAPIError with correct status_code + message
  ✓ Malformed response shapes raise ValueError
  ✓ Symbol/ID appears in path (not query) for path-param endpoints
  ✓ Edge-cases specific to each endpoint
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src.api.client import RevolutAPIClient, RevolutAPIError

BASE_URL = "https://revx.revolut.com/api/1.0"


# ---------------------------------------------------------------------------
# URL-parsing helpers
# ---------------------------------------------------------------------------


def _url_params(mock_call) -> dict[str, str]:
    """Flat dict of query params from the URL embedded in a mock call."""
    url = mock_call.kwargs["url"]
    parsed = urlparse(url)
    return {k: v[0] for k, v in parse_qs(parsed.query).items()}


def _base_url(mock_call) -> str:
    """URL with query string stripped."""
    return urlparse(mock_call.kwargs["url"])._replace(query="").geturl()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def client():
    """RevolutAPIClient with a generated Ed25519 key — no 1Password."""
    c = RevolutAPIClient()
    c._private_key = Ed25519PrivateKey.generate()
    yield c
    await c.close()


# ---------------------------------------------------------------------------
# HTTP mock helpers
# ---------------------------------------------------------------------------


def _mock_http(client: RevolutAPIClient, json_data, status_code: int = 200) -> AsyncMock:
    """Replace HTTP transport with a mock that returns json_data."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.content = b"content"
    mock_resp.json.return_value = json_data
    mock_resp.raise_for_status = MagicMock()
    client.client.request = AsyncMock(return_value=mock_resp)
    return client.client.request


def _mock_http_error(
    client: RevolutAPIClient,
    status_code: int,
    message: str = "Error",
    error_id: str = "test-error-id",
) -> AsyncMock:
    """Mock an HTTP error.  raise_for_status raises HTTPStatusError; the client
    converts it to RevolutAPIError."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.content = b"error"
    mock_resp.json.return_value = {
        "message": message,
        "error_id": error_id,
        "timestamp": 0,
    }
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        f"HTTP {status_code}",
        request=MagicMock(),
        response=mock_resp,
    )
    client.client.request = AsyncMock(return_value=mock_resp)
    return client.client.request


# ---------------------------------------------------------------------------
# Sample API payloads  (match exact shapes from docs/revolut-x-api-docs.md)
# ---------------------------------------------------------------------------

BALANCE_RESPONSE = [
    {
        "currency": "BTC",
        "available": "0.5",
        "staked": "0",
        "reserved": "0.01",
        "total": "0.51",
    },
    {
        "currency": "EUR",
        "available": "5000.00",
        "staked": "0",
        "reserved": "0",
        "total": "5000.00",
    },
]

CURRENCIES_RESPONSE = {
    "BTC": {
        "symbol": "BTC",
        "name": "Bitcoin",
        "scale": 8,
        "asset_type": "crypto",
        "status": "active",
    },
    "EUR": {
        "symbol": "EUR",
        "name": "Euro",
        "scale": 2,
        "asset_type": "fiat",
        "status": "active",
    },
}

PAIRS_RESPONSE = {
    "BTC/USD": {
        "base": "BTC",
        "quote": "USD",
        "base_step": "0.0000001",
        "quote_step": "0.01",
        "min_order_size": "0.0000001",
        "max_order_size": "1000",
        "min_order_size_quote": "0.01",
        "status": "active",
    },
    "ETH/EUR": {
        "base": "ETH",
        "quote": "EUR",
        "base_step": "0.0000001",
        "quote_step": "0.01",
        "min_order_size": "0.00001",
        "max_order_size": "9000",
        "min_order_size_quote": "0.01",
        "status": "active",
    },
}

LAST_PUBLIC_TRADES_RESPONSE = {
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
            "tid": "5ef9648f658149f7ababedc97a6401f8",
        }
    ],
    "metadata": {"timestamp": "2025-08-08T21:40:36.684333Z"},
}

ORDER_BOOK_RESPONSE = {
    "data": {
        "asks": [
            {
                "aid": "BTC",
                "anm": "Bitcoin",
                "s": "SELL",
                "p": "51000.00",
                "pc": "EUR",
                "pn": "MONE",
                "q": "0.1",
                "qc": "BTC",
                "qn": "UNIT",
                "ve": "REVX",
                "no": "1",
                "ts": "CLOB",
                "pdt": 1700000000000,
            }
        ],
        "bids": [
            {
                "aid": "BTC",
                "anm": "Bitcoin",
                "s": "BUY",
                "p": "50000.00",
                "pc": "EUR",
                "pn": "MONE",
                "q": "0.2",
                "qc": "BTC",
                "qn": "UNIT",
                "ve": "REVX",
                "no": "1",
                "ts": "CLOB",
                "pdt": 1700000000000,
            }
        ],
    },
    "metadata": {"ts": 1700000000000},
}

ORDER_CREATION_RESPONSE = {
    "data": [
        {
            "venue_order_id": "7a52e92e-8639-4fe1-abaa-68d3a2d5234b",
            "client_order_id": "984a4d8a-2a9b-4950-822f-2a40037f02bd",
            "state": "new",
        }
    ]
}

CANDLE_RESPONSE = {
    "data": [
        {
            "start": 1700000000000,
            "open": "49000.00",
            "high": "51000.00",
            "low": "48500.00",
            "close": "50500.00",
            "volume": "10.5",
        },
        {
            "start": 1700003600000,
            "open": "50500.00",
            "high": "52000.00",
            "low": "50000.00",
            "close": "51500.00",
            "volume": "8.2",
        },
    ]
}

ORDERS_RESPONSE = {
    "data": [
        {
            "id": "order-1",
            "client_order_id": "client-1",
            "symbol": "BTC/USD",
            "side": "buy",
            "type": "limit",
            "quantity": "0.01",
            "filled_quantity": "0",
            "leaves_quantity": "0.01",
            "price": "50000.00",
            "status": "new",
            "time_in_force": "gtc",
            "execution_instructions": ["allow_taker"],
            "created_date": 1700000000000,
            "updated_date": 1700000000000,
        }
    ],
    "metadata": {
        "timestamp": 1700000000000,
        "next_cursor": "GF0ZT0xNzY0OTMxNTAyODU0O2lkPTM3Yj==",
    },
}

FILLS_RESPONSE = {
    "data": [
        {
            "tdt": 1700000000000,
            "aid": "BTC",
            "anm": "Bitcoin",
            "p": "50000.00",
            "pc": "EUR",
            "pn": "MONE",
            "q": "0.01",
            "qc": "BTC",
            "qn": "UNIT",
            "ve": "REVX",
            "pdt": 1700000000000,
            "vp": "REVX",
            "tid": "trade-1",
            "oid": "order-1",
            "s": "buy",
            "im": False,
        }
    ]
}

TICKERS_RESPONSE = {
    "data": [
        {
            "symbol": "BTC/EUR",
            "bid": "49900.00",
            "ask": "50100.00",
            "mid": "50000.00",
            "last_price": "50000.00",
        },
        {
            "symbol": "ETH/EUR",
            "bid": "2990.00",
            "ask": "3010.00",
            "mid": "3000.00",
            "last_price": "3000.00",
        },
    ],
    "metadata": {"timestamp": 1700000000000},
}

TRADES_RESPONSE = {
    "data": [
        {
            "tdt": 1700000000000,
            "aid": "BTC",
            "anm": "Bitcoin",
            "p": "50000.00",
            "pc": "EUR",
            "pn": "MONE",
            "q": "0.01",
            "qc": "BTC",
            "qn": "UNIT",
            "ve": "REVX",
            "pdt": 1700000000000,
            "vp": "REVX",
            "tid": "trade-1",
        }
    ],
    "metadata": {"timestamp": 1700000000000, "next_cursor": None},
}

PRIVATE_TRADES_RESPONSE = {
    "data": [
        {
            **TRADES_RESPONSE["data"][0],
            "oid": "order-1",
            "s": "buy",
            "im": False,
        }
    ],
    "metadata": {"timestamp": 1700000000000, "next_cursor": None},
}


# ===========================================================================
# 1. GET /balances
# ===========================================================================


class TestGetBalance:
    async def test_calls_balances_endpoint(self, client):
        mock = _mock_http(client, BALANCE_RESPONSE)
        client.get_ticker = AsyncMock(side_effect=ValueError("no pair"))
        await client.get_balance()
        first_call = mock.call_args_list[0]
        assert first_call.kwargs["method"] == "GET"
        assert first_call.kwargs["url"] == f"{BASE_URL}/balances"

    async def test_returns_currency_keyed_dict(self, client):
        _mock_http(client, BALANCE_RESPONSE)
        client.get_ticker = AsyncMock(side_effect=ValueError("no pair"))
        result = await client.get_balance()
        assert "BTC" in result["balances"]
        assert "EUR" in result["balances"]

    async def test_balance_values_parsed_correctly(self, client):
        _mock_http(client, BALANCE_RESPONSE)
        client.get_ticker = AsyncMock(side_effect=ValueError("no pair"))
        result = await client.get_balance()
        btc = result["balances"]["BTC"]
        assert btc["available"] == Decimal("0.5")
        assert btc["reserved"] == Decimal("0.01")
        assert btc["total"] == Decimal("0.51")

    async def test_staked_field_included(self, client):
        _mock_http(client, BALANCE_RESPONSE)
        client.get_ticker = AsyncMock(side_effect=ValueError("no pair"))
        result = await client.get_balance()
        assert "staked" in result["balances"]["BTC"]
        assert result["balances"]["BTC"]["staked"] == Decimal("0")

    async def test_includes_currencies_list(self, client):
        _mock_http(client, BALANCE_RESPONSE)
        client.get_ticker = AsyncMock(side_effect=ValueError("no pair"))
        result = await client.get_balance()
        assert set(result["currencies"]) == {"BTC", "EUR"}

    async def test_includes_total_base_currency(self, client):
        _mock_http(client, BALANCE_RESPONSE)
        client.get_ticker = AsyncMock(side_effect=ValueError("no pair"))
        result = await client.get_balance()
        assert "total_eur" in result
        assert result["total_eur"] == Decimal("5000.00")

    async def test_fx_conversion_uses_live_rate(self, client):
        """Non-base currencies are converted using a live ticker rate."""
        response = [
            {
                "currency": "EUR",
                "available": "1000.00",
                "staked": "0",
                "reserved": "0",
                "total": "1000.00",
            },
            {
                "currency": "USD",
                "available": "500.00",
                "staked": "0",
                "reserved": "0",
                "total": "500.00",
            },
        ]
        _mock_http(client, response)
        client.get_ticker = AsyncMock(
            return_value={
                "last": Decimal("0.91"),
                "bid": Decimal("0.90"),
                "ask": Decimal("0.92"),
                "symbol": "USD-EUR",
            }
        )
        result = await client.get_balance()
        expected = Decimal("1000.00") + Decimal("500.00") * Decimal("0.91")
        assert result["total_eur"] == expected
        client.get_ticker.assert_awaited_once_with("USD-EUR")

    async def test_fx_conversion_skipped_on_ticker_failure(self, client):
        """If ticker lookup fails for a currency, its value is excluded (not an error)."""
        response = [
            {
                "currency": "EUR",
                "available": "2000.00",
                "staked": "0",
                "reserved": "0",
                "total": "2000.00",
            },
            {"currency": "BTC", "available": "1.0", "staked": "0", "reserved": "0", "total": "1.0"},
        ]
        _mock_http(client, response)
        client.get_ticker = AsyncMock(side_effect=ValueError("no order book"))
        result = await client.get_balance()
        assert result["total_eur"] == Decimal("2000.00")  # BTC excluded, no error raised

    async def test_zero_balance_currencies_skipped_for_fx(self, client):
        """Currencies with zero total don't trigger a ticker lookup."""
        response = [
            {
                "currency": "EUR",
                "available": "3000.00",
                "staked": "0",
                "reserved": "0",
                "total": "3000.00",
            },
            {"currency": "USD", "available": "0", "staked": "0", "reserved": "0", "total": "0"},
        ]
        _mock_http(client, response)
        client.get_ticker = AsyncMock()
        result = await client.get_balance()
        assert result["total_eur"] == Decimal("3000.00")
        client.get_ticker.assert_not_awaited()

    async def test_raises_value_error_on_non_list_response(self, client):
        _mock_http(client, {"error": "unexpected dict"})
        with pytest.raises(ValueError, match="Invalid balance response"):
            await client.get_balance()

    async def test_raises_revolut_api_error_on_401(self, client):
        _mock_http_error(client, 401, "API key can only be used from whitelisted IP")
        with pytest.raises(RevolutAPIError) as exc:
            await client.get_balance()
        assert exc.value.status_code == 401
        assert "whitelisted" in exc.value.message

    async def test_raises_revolut_api_error_on_429(self, client):
        _mock_http_error(client, 429, "Rate Limit Exceeded")
        with pytest.raises(RevolutAPIError) as exc:
            await client.get_balance()
        assert exc.value.status_code == 429


# ===========================================================================
# 2. GET /configuration/currencies
# ===========================================================================


class TestGetCurrencies:
    async def test_calls_configuration_currencies(self, client):
        mock = _mock_http(client, CURRENCIES_RESPONSE)
        await client.get_currencies()
        assert mock.call_args.kwargs["method"] == "GET"
        assert mock.call_args.kwargs["url"] == f"{BASE_URL}/configuration/currencies"

    async def test_no_query_params_sent(self, client):
        mock = _mock_http(client, CURRENCIES_RESPONSE)
        await client.get_currencies()
        assert _url_params(mock.call_args) == {}

    async def test_returns_dict_keyed_by_symbol(self, client):
        _mock_http(client, CURRENCIES_RESPONSE)
        result = await client.get_currencies()
        assert "BTC" in result
        assert "EUR" in result

    async def test_currency_fields_present(self, client):
        _mock_http(client, CURRENCIES_RESPONSE)
        result = await client.get_currencies()
        btc = result["BTC"]
        assert btc["name"] == "Bitcoin"
        assert btc["scale"] == 8
        assert btc["asset_type"] == "crypto"
        assert btc["status"] == "active"

    async def test_raises_value_error_on_non_dict_response(self, client):
        _mock_http(client, [{"unexpected": "list"}])
        with pytest.raises(ValueError, match="Invalid currencies response"):
            await client.get_currencies()

    async def test_raises_revolut_api_error_on_401(self, client):
        _mock_http_error(client, 401, "Unauthorized")
        with pytest.raises(RevolutAPIError) as exc:
            await client.get_currencies()
        assert exc.value.status_code == 401

    async def test_raises_revolut_api_error_on_403(self, client):
        _mock_http_error(client, 403, "Forbidden")
        with pytest.raises(RevolutAPIError) as exc:
            await client.get_currencies()
        assert exc.value.status_code == 403


# ===========================================================================
# 3. GET /configuration/pairs
# ===========================================================================


class TestGetCurrencyPairs:
    async def test_calls_configuration_pairs(self, client):
        mock = _mock_http(client, PAIRS_RESPONSE)
        await client.get_currency_pairs()
        assert mock.call_args.kwargs["method"] == "GET"
        assert mock.call_args.kwargs["url"] == f"{BASE_URL}/configuration/pairs"

    async def test_no_query_params_sent(self, client):
        mock = _mock_http(client, PAIRS_RESPONSE)
        await client.get_currency_pairs()
        assert _url_params(mock.call_args) == {}

    async def test_returns_dict_keyed_by_pair(self, client):
        _mock_http(client, PAIRS_RESPONSE)
        result = await client.get_currency_pairs()
        assert "BTC/USD" in result
        assert "ETH/EUR" in result

    async def test_pair_fields_present(self, client):
        _mock_http(client, PAIRS_RESPONSE)
        result = await client.get_currency_pairs()
        pair = result["BTC/USD"]
        assert pair["base"] == "BTC"
        assert pair["quote"] == "USD"
        assert "min_order_size" in pair
        assert "max_order_size" in pair
        assert pair["status"] == "active"

    async def test_raises_value_error_on_non_dict_response(self, client):
        _mock_http(client, [{"unexpected": "list"}])
        with pytest.raises(ValueError, match="Invalid pairs response"):
            await client.get_currency_pairs()

    async def test_raises_revolut_api_error_on_401(self, client):
        _mock_http_error(client, 401, "Unauthorized")
        with pytest.raises(RevolutAPIError) as exc:
            await client.get_currency_pairs()
        assert exc.value.status_code == 401


# ===========================================================================
# 4. GET /public/last-trades  (unauthenticated)
# ===========================================================================


class TestGetLastPublicTrades:
    async def test_calls_public_last_trades(self, client):
        mock = _mock_http(client, LAST_PUBLIC_TRADES_RESPONSE)
        await client.get_last_public_trades()
        assert mock.call_args.kwargs["url"] == f"{BASE_URL}/public/last-trades"

    async def test_no_query_params_sent(self, client):
        mock = _mock_http(client, LAST_PUBLIC_TRADES_RESPONSE)
        await client.get_last_public_trades()
        assert _url_params(mock.call_args) == {}

    async def test_returns_dict_with_data_and_metadata(self, client):
        _mock_http(client, LAST_PUBLIC_TRADES_RESPONSE)
        result = await client.get_last_public_trades()
        assert "data" in result
        assert "metadata" in result

    async def test_trade_mifid_fields_present(self, client):
        _mock_http(client, LAST_PUBLIC_TRADES_RESPONSE)
        result = await client.get_last_public_trades()
        trade = result["data"][0]
        for field in ("tdt", "aid", "anm", "p", "pc", "q", "qc", "ve", "tid"):
            assert field in trade, f"Missing MiFID field: {field}"

    async def test_raises_value_error_on_non_dict_response(self, client):
        _mock_http(client, [{"unexpected": "list"}])
        with pytest.raises(ValueError, match="Invalid last-trades response"):
            await client.get_last_public_trades()

    async def test_raises_revolut_api_error_on_429(self, client):
        """Public endpoint is rate-limited at 20 req/10s."""
        _mock_http_error(client, 429, "Rate Limit Exceeded")
        with pytest.raises(RevolutAPIError) as exc:
            await client.get_last_public_trades()
        assert exc.value.status_code == 429


# ===========================================================================
# 5. GET /public/order-book/{symbol}  (unauthenticated, max 5 levels)
# ===========================================================================


class TestGetPublicOrderBook:
    async def test_calls_public_order_book_endpoint(self, client):
        mock = _mock_http(client, ORDER_BOOK_RESPONSE)
        await client.get_public_order_book("BTC-EUR")
        assert mock.call_args.kwargs["url"] == f"{BASE_URL}/public/order-book/BTC-EUR"

    async def test_symbol_appears_in_path_not_query(self, client):
        mock = _mock_http(client, ORDER_BOOK_RESPONSE)
        await client.get_public_order_book("ETH-USD")
        assert _base_url(mock.call_args) == f"{BASE_URL}/public/order-book/ETH-USD"
        assert "symbol" not in _url_params(mock.call_args)

    async def test_no_query_params_sent(self, client):
        """Public order book takes no query parameters."""
        mock = _mock_http(client, ORDER_BOOK_RESPONSE)
        await client.get_public_order_book("BTC-EUR")
        assert _url_params(mock.call_args) == {}

    async def test_returns_dict_with_bids_and_asks(self, client):
        _mock_http(client, ORDER_BOOK_RESPONSE)
        result = await client.get_public_order_book("BTC-EUR")
        assert "data" in result
        assert "asks" in result["data"]
        assert "bids" in result["data"]

    async def test_returns_metadata(self, client):
        _mock_http(client, ORDER_BOOK_RESPONSE)
        result = await client.get_public_order_book("BTC-EUR")
        assert "metadata" in result

    async def test_order_book_entry_fields_present(self, client):
        _mock_http(client, ORDER_BOOK_RESPONSE)
        result = await client.get_public_order_book("BTC-EUR")
        ask = result["data"]["asks"][0]
        for field in ("aid", "anm", "s", "p", "q", "pc", "qc", "ve", "no"):
            assert field in ask, f"Missing order book entry field: {field}"

    async def test_raises_value_error_on_non_dict_response(self, client):
        _mock_http(client, [{"unexpected": "list"}])
        with pytest.raises(ValueError, match="Invalid public order book response"):
            await client.get_public_order_book("BTC-EUR")

    async def test_raises_revolut_api_error_on_429(self, client):
        _mock_http_error(client, 429, "Rate Limit Exceeded")
        with pytest.raises(RevolutAPIError) as exc:
            await client.get_public_order_book("BTC-EUR")
        assert exc.value.status_code == 429


# ===========================================================================
# 6. POST /orders  — place order
# ===========================================================================


class TestCreateOrder:
    async def test_posts_to_orders_endpoint(self, client):
        mock = _mock_http(client, ORDER_CREATION_RESPONSE)
        await client.create_order("BTC-EUR", "buy", "limit", 0.01, price=50000.0)
        assert mock.call_args.kwargs["method"] == "POST"
        assert mock.call_args.kwargs["url"] == f"{BASE_URL}/orders"

    async def test_limit_order_body_structure(self, client):
        mock = _mock_http(client, ORDER_CREATION_RESPONSE)
        await client.create_order("BTC-EUR", "buy", "limit", 0.01, price=50000.0)
        body = mock.call_args.kwargs["json"]
        assert body["symbol"] == "BTC-EUR"
        assert body["side"] == "buy"
        assert "limit" in body["order_configuration"]
        assert body["order_configuration"]["limit"]["price"] == "50000.0"
        assert body["order_configuration"]["limit"]["base_size"] == "0.01"

    async def test_limit_order_has_post_only_execution_instruction(self, client):
        mock = _mock_http(client, ORDER_CREATION_RESPONSE)
        await client.create_order("BTC-EUR", "buy", "limit", 0.01, price=50000.0)
        body = mock.call_args.kwargs["json"]
        assert body["order_configuration"]["limit"]["execution_instructions"] == ["post_only"]

    async def test_market_order_body_structure(self, client):
        mock = _mock_http(client, ORDER_CREATION_RESPONSE)
        await client.create_order("BTC-EUR", "buy", "market", 0.01)
        body = mock.call_args.kwargs["json"]
        assert "market" in body["order_configuration"]
        assert body["order_configuration"]["market"]["base_size"] == "0.01"
        assert "limit" not in body["order_configuration"]

    async def test_client_order_id_is_uuid(self, client):
        import uuid as _uuid

        mock = _mock_http(client, ORDER_CREATION_RESPONSE)
        await client.create_order("BTC-EUR", "buy", "limit", 0.01, price=50000.0)
        _uuid.UUID(mock.call_args.kwargs["json"]["client_order_id"])

    async def test_side_buy_is_lowercased(self, client):
        mock = _mock_http(client, ORDER_CREATION_RESPONSE)
        await client.create_order("BTC-EUR", "BUY", "limit", 0.01, price=50000.0)
        assert mock.call_args.kwargs["json"]["side"] == "buy"

    async def test_side_sell_is_lowercased(self, client):
        mock = _mock_http(client, ORDER_CREATION_RESPONSE)
        await client.create_order("BTC-EUR", "SELL", "market", 0.01)
        assert mock.call_args.kwargs["json"]["side"] == "sell"

    async def test_limit_order_requires_price(self, client):
        with pytest.raises(ValueError, match="price is required"):
            await client.create_order("BTC-EUR", "buy", "limit", 0.01)

    async def test_unsupported_order_type_raises(self, client):
        with pytest.raises(ValueError, match="Unsupported order_type"):
            await client.create_order("BTC-EUR", "buy", "stop_loss", 0.01)

    async def test_returns_venue_order_id_client_order_id_and_state(self, client):
        _mock_http(client, ORDER_CREATION_RESPONSE)
        result = await client.create_order("BTC-EUR", "buy", "limit", 0.01, price=50000.0)
        assert result["venue_order_id"] == "7a52e92e-8639-4fe1-abaa-68d3a2d5234b"
        assert result["client_order_id"] == "984a4d8a-2a9b-4950-822f-2a40037f02bd"
        assert result["state"] == "new"

    async def test_raises_value_error_on_missing_data_key(self, client):
        _mock_http(client, {"unexpected": "no data key"})
        with pytest.raises(ValueError, match="Unexpected create_order response"):
            await client.create_order("BTC-EUR", "buy", "limit", 0.01, price=50000.0)

    async def test_raises_value_error_on_empty_data_list(self, client):
        _mock_http(client, {"data": []})
        with pytest.raises(ValueError, match="Empty data"):
            await client.create_order("BTC-EUR", "buy", "limit", 0.01, price=50000.0)

    async def test_raises_revolut_api_error_on_400_bad_pair(self, client):
        _mock_http_error(client, 400, "No such pair: BTC-BTC")
        with pytest.raises(RevolutAPIError) as exc:
            await client.create_order("BTC-BTC", "buy", "limit", 0.01, price=1.0)
        assert exc.value.status_code == 400
        assert "No such pair" in exc.value.message

    async def test_raises_revolut_api_error_on_401(self, client):
        _mock_http_error(client, 401, "Unauthorized")
        with pytest.raises(RevolutAPIError) as exc:
            await client.create_order("BTC-EUR", "buy", "limit", 0.01, price=50000.0)
        assert exc.value.status_code == 401

    async def test_raises_revolut_api_error_on_429(self, client):
        _mock_http_error(client, 429, "Rate Limit Exceeded")
        with pytest.raises(RevolutAPIError) as exc:
            await client.create_order("BTC-EUR", "buy", "market", 0.01)
        assert exc.value.status_code == 429


# ===========================================================================
# 7. DELETE /orders  — cancel all active orders
# ===========================================================================


class TestCancelAllOrders:
    async def test_sends_delete_to_orders_endpoint(self, client):
        mock = _mock_http(client, {})
        await client.cancel_all_orders()
        assert mock.call_args.kwargs["method"] == "DELETE"
        assert mock.call_args.kwargs["url"] == f"{BASE_URL}/orders"

    async def test_no_body_sent(self, client):
        mock = _mock_http(client, {})
        await client.cancel_all_orders()
        assert mock.call_args.kwargs.get("json") is None

    async def test_returns_none_on_204(self, client):
        _mock_http(client, {})
        result = await client.cancel_all_orders()
        assert result is None

    async def test_raises_revolut_api_error_on_401(self, client):
        _mock_http_error(client, 401, "Unauthorized")
        with pytest.raises(RevolutAPIError) as exc:
            await client.cancel_all_orders()
        assert exc.value.status_code == 401

    async def test_raises_revolut_api_error_on_403(self, client):
        _mock_http_error(client, 403, "Forbidden")
        with pytest.raises(RevolutAPIError) as exc:
            await client.cancel_all_orders()
        assert exc.value.status_code == 403


# ===========================================================================
# 8. GET /orders/active
# ===========================================================================


class TestGetOpenOrders:
    async def test_calls_orders_active_endpoint(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_open_orders()
        assert mock.call_args.kwargs["method"] == "GET"
        assert _base_url(mock.call_args) == f"{BASE_URL}/orders/active"

    async def test_default_limit_is_100(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_open_orders()
        assert _url_params(mock.call_args)["limit"] == "100"

    async def test_custom_limit(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_open_orders(limit=10)
        assert _url_params(mock.call_args)["limit"] == "10"

    async def test_symbols_filter(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_open_orders(symbols=["BTC-USD", "ETH-USD"])
        assert _url_params(mock.call_args)["symbols"] == "BTC-USD,ETH-USD"

    async def test_sides_filter_plural(self, client):
        """Filter param is 'sides' (plural), not 'side'."""
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_open_orders(sides=["buy"])
        params = _url_params(mock.call_args)
        assert params["sides"] == "buy"
        assert "side" not in params

    async def test_states_filter(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_open_orders(states=["new", "partially_filled"])
        assert set(_url_params(mock.call_args)["states"].split(",")) == {"new", "partially_filled"}

    async def test_types_filter(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_open_orders(types=["limit", "conditional"])
        assert set(_url_params(mock.call_args)["types"].split(",")) == {"limit", "conditional"}

    async def test_cursor_pagination(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_open_orders(cursor="next-page-token")
        assert _url_params(mock.call_args)["cursor"] == "next-page-token"

    async def test_optional_params_omitted_when_not_provided(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_open_orders()
        params = _url_params(mock.call_args)
        for key in ("symbols", "sides", "states", "types", "cursor"):
            assert key not in params, f"Unexpected param: {key}"

    async def test_returns_data_and_metadata(self, client):
        _mock_http(client, ORDERS_RESPONSE)
        result = await client.get_open_orders()
        assert "data" in result
        assert "metadata" in result

    async def test_order_fields_present(self, client):
        _mock_http(client, ORDERS_RESPONSE)
        result = await client.get_open_orders()
        order = result["data"][0]
        for field in ("id", "client_order_id", "symbol", "side", "type", "quantity", "status"):
            assert field in order, f"Missing field: {field}"

    async def test_raises_value_error_on_non_dict_response(self, client):
        _mock_http(client, [{"unexpected": "list"}])
        with pytest.raises(ValueError, match="Invalid active orders response"):
            await client.get_open_orders()

    async def test_raises_revolut_api_error_on_401(self, client):
        _mock_http_error(client, 401, "Unauthorized")
        with pytest.raises(RevolutAPIError) as exc:
            await client.get_open_orders()
        assert exc.value.status_code == 401


# ===========================================================================
# 9. GET /orders/historical
# ===========================================================================


class TestGetHistoricalOrders:
    async def test_calls_orders_historical_endpoint(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_historical_orders()
        assert mock.call_args.kwargs["method"] == "GET"
        assert _base_url(mock.call_args) == f"{BASE_URL}/orders/historical"

    async def test_default_limit_is_100(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_historical_orders()
        assert _url_params(mock.call_args)["limit"] == "100"

    async def test_date_params_omitted_when_not_provided(self, client):
        """Server handles date defaults — client must NOT inject start_date."""
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_historical_orders()
        params = _url_params(mock.call_args)
        assert "start_date" not in params
        assert "end_date" not in params

    async def test_passes_date_range(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_historical_orders(start_date=1700000000000, end_date=1700086400000)
        params = _url_params(mock.call_args)
        assert params["start_date"] == "1700000000000"
        assert params["end_date"] == "1700086400000"

    async def test_symbols_filter(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_historical_orders(symbols=["BTC-USD", "ETH-EUR"])
        assert set(_url_params(mock.call_args)["symbols"].split(",")) == {"BTC-USD", "ETH-EUR"}

    async def test_states_filter(self, client):
        """Valid states: filled, cancelled, rejected, replaced."""
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_historical_orders(states=["filled", "cancelled"])
        assert set(_url_params(mock.call_args)["states"].split(",")) == {"filled", "cancelled"}

    async def test_types_filter(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_historical_orders(types=["limit"])
        assert _url_params(mock.call_args)["types"] == "limit"

    async def test_cursor_pagination(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_historical_orders(cursor="cursor-token")
        assert _url_params(mock.call_args)["cursor"] == "cursor-token"

    async def test_optional_params_omitted_when_not_provided(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_historical_orders()
        params = _url_params(mock.call_args)
        for key in ("symbols", "states", "types", "cursor", "start_date", "end_date"):
            assert key not in params, f"Unexpected param: {key}"

    async def test_raises_value_error_on_non_dict_response(self, client):
        _mock_http(client, [{"unexpected": "list"}])
        with pytest.raises(ValueError, match="Invalid historical orders response"):
            await client.get_historical_orders()

    async def test_raises_revolut_api_error_on_401(self, client):
        _mock_http_error(client, 401, "Unauthorized")
        with pytest.raises(RevolutAPIError) as exc:
            await client.get_historical_orders()
        assert exc.value.status_code == 401


# ===========================================================================
# 10. GET /orders/{venue_order_id}
# ===========================================================================


class TestGetOrder:
    async def test_calls_correct_endpoint(self, client):
        mock = _mock_http(client, {"data": {"id": "order-1", "status": "new"}})
        await client.get_order("venue-order-uuid-123")
        assert mock.call_args.kwargs["method"] == "GET"
        assert mock.call_args.kwargs["url"] == f"{BASE_URL}/orders/venue-order-uuid-123"

    async def test_id_in_path_not_query(self, client):
        mock = _mock_http(client, {"data": {"id": "abc"}})
        await client.get_order("abc")
        assert _base_url(mock.call_args) == f"{BASE_URL}/orders/abc"
        assert "id" not in _url_params(mock.call_args)

    async def test_unwraps_data_envelope(self, client):
        """API wraps single order in {"data": {...}} — client must unwrap it."""
        _mock_http(client, {"data": {"id": "order-1", "status": "filled", "symbol": "BTC/USD"}})
        result = await client.get_order("order-1")
        assert result["id"] == "order-1"
        assert result["status"] == "filled"
        assert "data" not in result

    async def test_raises_revolut_api_error_on_404(self, client):
        _mock_http_error(client, 404, "Order with ID 'xyz' not found")
        with pytest.raises(RevolutAPIError) as exc:
            await client.get_order("xyz")
        assert exc.value.status_code == 404
        assert "not found" in exc.value.message

    async def test_raises_revolut_api_error_on_401(self, client):
        _mock_http_error(client, 401, "Unauthorized")
        with pytest.raises(RevolutAPIError) as exc:
            await client.get_order("order-1")
        assert exc.value.status_code == 401

    async def test_raises_value_error_on_non_dict_response(self, client):
        _mock_http(client, ["not", "a", "dict"])
        with pytest.raises(ValueError, match="Invalid order response"):
            await client.get_order("order-1")


# ===========================================================================
# 11. DELETE /orders/{venue_order_id}
# ===========================================================================


class TestCancelOrder:
    async def test_sends_delete_to_order_path(self, client):
        mock = _mock_http(client, {})
        await client.cancel_order("venue-order-uuid-123")
        assert mock.call_args.kwargs["method"] == "DELETE"
        assert mock.call_args.kwargs["url"] == f"{BASE_URL}/orders/venue-order-uuid-123"

    async def test_id_in_path_not_query(self, client):
        mock = _mock_http(client, {})
        await client.cancel_order("my-order-id")
        assert _base_url(mock.call_args) == f"{BASE_URL}/orders/my-order-id"
        assert "id" not in _url_params(mock.call_args)

    async def test_returns_none_on_204(self, client):
        _mock_http(client, {})
        result = await client.cancel_order("venue-order-uuid-123")
        assert result is None

    async def test_raises_revolut_api_error_on_404(self, client):
        _mock_http_error(client, 404, "Order with ID 'xyz' not found")
        with pytest.raises(RevolutAPIError) as exc:
            await client.cancel_order("xyz")
        assert exc.value.status_code == 404

    async def test_raises_revolut_api_error_on_401(self, client):
        _mock_http_error(client, 401, "Unauthorized")
        with pytest.raises(RevolutAPIError) as exc:
            await client.cancel_order("order-1")
        assert exc.value.status_code == 401


# ===========================================================================
# 12. GET /orders/fills/{venue_order_id}
# ===========================================================================


class TestGetOrderFills:
    async def test_calls_correct_path(self, client):
        """Path is /orders/fills/{id} — NOT /orders/{id}/fills."""
        mock = _mock_http(client, FILLS_RESPONSE)
        await client.get_order_fills("venue-order-uuid-123")
        assert mock.call_args.kwargs["method"] == "GET"
        assert mock.call_args.kwargs["url"] == f"{BASE_URL}/orders/fills/venue-order-uuid-123"

    async def test_id_in_path_not_query(self, client):
        mock = _mock_http(client, FILLS_RESPONSE)
        await client.get_order_fills("my-order")
        assert _base_url(mock.call_args) == f"{BASE_URL}/orders/fills/my-order"
        assert "id" not in _url_params(mock.call_args)

    async def test_different_order_ids_hit_different_paths(self, client):
        mock = _mock_http(client, FILLS_RESPONSE)
        await client.get_order_fills("order-abc")
        assert _base_url(mock.call_args) == f"{BASE_URL}/orders/fills/order-abc"

    async def test_returns_data_with_fill_fields(self, client):
        _mock_http(client, FILLS_RESPONSE)
        result = await client.get_order_fills("venue-order-uuid-123")
        assert "data" in result
        fill = result["data"][0]
        for field in ("tdt", "aid", "p", "q", "tid", "oid", "s", "im"):
            assert field in fill, f"Missing fill field: {field}"

    async def test_fill_maker_flag_is_boolean(self, client):
        _mock_http(client, FILLS_RESPONSE)
        result = await client.get_order_fills("venue-order-uuid-123")
        assert isinstance(result["data"][0]["im"], bool)

    async def test_raises_value_error_on_non_dict_response(self, client):
        _mock_http(client, [{"unexpected": "list"}])
        with pytest.raises(ValueError, match="Invalid fills response"):
            await client.get_order_fills("order-1")

    async def test_raises_revolut_api_error_on_404(self, client):
        _mock_http_error(client, 404, "Order with ID 'xyz' not found")
        with pytest.raises(RevolutAPIError) as exc:
            await client.get_order_fills("xyz")
        assert exc.value.status_code == 404

    async def test_raises_revolut_api_error_on_401(self, client):
        _mock_http_error(client, 401, "Unauthorized")
        with pytest.raises(RevolutAPIError) as exc:
            await client.get_order_fills("order-1")
        assert exc.value.status_code == 401


# ===========================================================================
# 13. GET /trades/all/{symbol}
# ===========================================================================


class TestGetPublicTrades:
    async def test_calls_trades_all_endpoint(self, client):
        mock = _mock_http(client, TRADES_RESPONSE)
        await client.get_public_trades("BTC-EUR")
        assert mock.call_args.kwargs["method"] == "GET"
        assert _base_url(mock.call_args) == f"{BASE_URL}/trades/all/BTC-EUR"

    async def test_symbol_in_path_not_query(self, client):
        mock = _mock_http(client, TRADES_RESPONSE)
        await client.get_public_trades("BTC-EUR")
        assert "symbol" not in _url_params(mock.call_args)

    async def test_different_symbols_hit_different_paths(self, client):
        mock = _mock_http(client, TRADES_RESPONSE)
        await client.get_public_trades("ETH-USD")
        assert _base_url(mock.call_args) == f"{BASE_URL}/trades/all/ETH-USD"

    async def test_default_limit_is_100(self, client):
        mock = _mock_http(client, TRADES_RESPONSE)
        await client.get_public_trades("BTC-EUR")
        assert _url_params(mock.call_args)["limit"] == "100"

    async def test_date_range_params(self, client):
        mock = _mock_http(client, TRADES_RESPONSE)
        await client.get_public_trades("BTC-EUR", start_date=1700000000000, end_date=1700086400000)
        params = _url_params(mock.call_args)
        assert params["start_date"] == "1700000000000"
        assert params["end_date"] == "1700086400000"

    async def test_cursor_pagination(self, client):
        mock = _mock_http(client, TRADES_RESPONSE)
        await client.get_public_trades("BTC-EUR", cursor="next-page-token")
        assert _url_params(mock.call_args)["cursor"] == "next-page-token"

    async def test_date_params_omitted_when_not_provided(self, client):
        mock = _mock_http(client, TRADES_RESPONSE)
        await client.get_public_trades("BTC-EUR")
        params = _url_params(mock.call_args)
        assert "start_date" not in params
        assert "end_date" not in params

    async def test_returns_data_and_metadata(self, client):
        _mock_http(client, TRADES_RESPONSE)
        result = await client.get_public_trades("BTC-EUR")
        assert "data" in result
        assert "metadata" in result

    async def test_raises_value_error_on_non_dict_response(self, client):
        _mock_http(client, [{"unexpected": "list"}])
        with pytest.raises(ValueError, match="Invalid public trades response"):
            await client.get_public_trades("BTC-EUR")

    async def test_raises_revolut_api_error_on_400_bad_symbol(self, client):
        _mock_http_error(client, 400, "No such pair: BTC-BTC")
        with pytest.raises(RevolutAPIError) as exc:
            await client.get_public_trades("BTC-BTC")
        assert exc.value.status_code == 400

    async def test_raises_revolut_api_error_on_401(self, client):
        _mock_http_error(client, 401, "Unauthorized")
        with pytest.raises(RevolutAPIError) as exc:
            await client.get_public_trades("BTC-EUR")
        assert exc.value.status_code == 401


# ===========================================================================
# 14. GET /trades/private/{symbol}
# ===========================================================================


class TestGetTrades:
    async def test_calls_trades_private_endpoint(self, client):
        mock = _mock_http(client, PRIVATE_TRADES_RESPONSE)
        await client.get_trades("BTC-EUR")
        assert mock.call_args.kwargs["method"] == "GET"
        assert _base_url(mock.call_args) == f"{BASE_URL}/trades/private/BTC-EUR"

    async def test_symbol_in_path_not_query(self, client):
        mock = _mock_http(client, PRIVATE_TRADES_RESPONSE)
        await client.get_trades("BTC-EUR")
        assert "symbol" not in _url_params(mock.call_args)

    async def test_different_symbols_hit_different_paths(self, client):
        mock = _mock_http(client, PRIVATE_TRADES_RESPONSE)
        await client.get_trades("ETH-USD")
        assert _base_url(mock.call_args) == f"{BASE_URL}/trades/private/ETH-USD"

    async def test_default_limit_is_100(self, client):
        mock = _mock_http(client, PRIVATE_TRADES_RESPONSE)
        await client.get_trades("BTC-EUR")
        assert _url_params(mock.call_args)["limit"] == "100"

    async def test_date_range_params(self, client):
        mock = _mock_http(client, PRIVATE_TRADES_RESPONSE)
        await client.get_trades("BTC-EUR", start_date=1700000000000, end_date=1700086400000)
        params = _url_params(mock.call_args)
        assert params["start_date"] == "1700000000000"
        assert params["end_date"] == "1700086400000"

    async def test_cursor_pagination(self, client):
        mock = _mock_http(client, PRIVATE_TRADES_RESPONSE)
        await client.get_trades("BTC-EUR", cursor="next-page-token")
        assert _url_params(mock.call_args)["cursor"] == "next-page-token"

    async def test_date_params_omitted_when_not_provided(self, client):
        mock = _mock_http(client, PRIVATE_TRADES_RESPONSE)
        await client.get_trades("BTC-EUR")
        params = _url_params(mock.call_args)
        assert "start_date" not in params
        assert "end_date" not in params

    async def test_private_fields_present_in_response(self, client):
        """Private trades include oid, s (side), and im (maker flag)."""
        _mock_http(client, PRIVATE_TRADES_RESPONSE)
        result = await client.get_trades("BTC-EUR")
        trade = result["data"][0]
        assert trade["s"] == "buy"
        assert trade["oid"] == "order-1"
        assert trade["im"] is False

    async def test_raises_value_error_on_non_dict_response(self, client):
        _mock_http(client, [{"unexpected": "list"}])
        with pytest.raises(ValueError, match="Invalid private trades response"):
            await client.get_trades("BTC-EUR")

    async def test_raises_revolut_api_error_on_401(self, client):
        _mock_http_error(client, 401, "Unauthorized")
        with pytest.raises(RevolutAPIError) as exc:
            await client.get_trades("BTC-EUR")
        assert exc.value.status_code == 401

    async def test_raises_revolut_api_error_on_403(self, client):
        _mock_http_error(client, 403, "Forbidden")
        with pytest.raises(RevolutAPIError) as exc:
            await client.get_trades("BTC-EUR")
        assert exc.value.status_code == 403


# ===========================================================================
# 15. GET /order-book/{symbol}  (authenticated, up to 20 levels)
# ===========================================================================


class TestGetOrderBook:
    async def test_calls_authenticated_order_book_endpoint(self, client):
        """Must use /order-book/ (authenticated), NOT /public/order-book/."""
        mock = _mock_http(client, ORDER_BOOK_RESPONSE)
        await client.get_order_book("BTC-EUR")
        assert mock.call_args.kwargs["method"] == "GET"
        assert _base_url(mock.call_args) == f"{BASE_URL}/order-book/BTC-EUR"
        assert "/public/" not in mock.call_args.kwargs["url"]

    async def test_symbol_in_path_not_query(self, client):
        mock = _mock_http(client, ORDER_BOOK_RESPONSE)
        await client.get_order_book("ETH-USD")
        assert _base_url(mock.call_args) == f"{BASE_URL}/order-book/ETH-USD"
        assert "symbol" not in _url_params(mock.call_args)

    async def test_passes_depth_param_not_limit(self, client):
        """Query param is 'depth', not 'limit'."""
        mock = _mock_http(client, ORDER_BOOK_RESPONSE)
        await client.get_order_book("BTC-EUR", depth=5)
        params = _url_params(mock.call_args)
        assert params["depth"] == "5"
        assert "limit" not in params

    async def test_default_depth_is_20(self, client):
        mock = _mock_http(client, ORDER_BOOK_RESPONSE)
        await client.get_order_book("BTC-EUR")
        assert _url_params(mock.call_args)["depth"] == "20"

    async def test_returns_bids_and_asks(self, client):
        _mock_http(client, ORDER_BOOK_RESPONSE)
        result = await client.get_order_book("BTC-EUR")
        assert "data" in result
        assert "asks" in result["data"]
        assert "bids" in result["data"]

    async def test_returns_metadata(self, client):
        _mock_http(client, ORDER_BOOK_RESPONSE)
        result = await client.get_order_book("BTC-EUR")
        assert "metadata" in result

    async def test_raises_value_error_on_non_dict_response(self, client):
        _mock_http(client, [{"unexpected": "list"}])
        with pytest.raises(ValueError, match="Invalid order book response"):
            await client.get_order_book("BTC-EUR")

    async def test_raises_revolut_api_error_on_400_bad_symbol(self, client):
        _mock_http_error(client, 400, "No such pair: BTC-BTC")
        with pytest.raises(RevolutAPIError) as exc:
            await client.get_order_book("BTC-BTC")
        assert exc.value.status_code == 400

    async def test_raises_revolut_api_error_on_401(self, client):
        _mock_http_error(client, 401, "Unauthorized")
        with pytest.raises(RevolutAPIError) as exc:
            await client.get_order_book("BTC-EUR")
        assert exc.value.status_code == 401

    async def test_raises_revolut_api_error_on_429(self, client):
        """Rate limit: 1000 req/min."""
        _mock_http_error(client, 429, "Rate Limit Exceeded")
        with pytest.raises(RevolutAPIError) as exc:
            await client.get_order_book("BTC-EUR")
        assert exc.value.status_code == 429


# ===========================================================================
# 16. GET /candles/{symbol}
# ===========================================================================


class TestGetCandles:
    async def test_calls_candles_endpoint(self, client):
        mock = _mock_http(client, CANDLE_RESPONSE)
        await client.get_candles("BTC-EUR")
        assert mock.call_args.kwargs["method"] == "GET"
        assert _base_url(mock.call_args) == f"{BASE_URL}/candles/BTC-EUR"

    async def test_symbol_in_path_not_query(self, client):
        mock = _mock_http(client, CANDLE_RESPONSE)
        await client.get_candles("ETH-USD")
        assert _base_url(mock.call_args) == f"{BASE_URL}/candles/ETH-USD"
        assert "symbol" not in _url_params(mock.call_args)

    async def test_interval_param_sent(self, client):
        mock = _mock_http(client, CANDLE_RESPONSE)
        await client.get_candles("BTC-EUR", interval=15)
        assert _url_params(mock.call_args)["interval"] == "15"

    async def test_default_interval_is_60(self, client):
        mock = _mock_http(client, CANDLE_RESPONSE)
        await client.get_candles("BTC-EUR")
        assert _url_params(mock.call_args)["interval"] == "60"

    async def test_since_param_sent(self, client):
        mock = _mock_http(client, CANDLE_RESPONSE)
        await client.get_candles("BTC-EUR", since=1700000000000)
        assert _url_params(mock.call_args)["since"] == "1700000000000"

    async def test_until_param_sent(self, client):
        mock = _mock_http(client, CANDLE_RESPONSE)
        await client.get_candles("BTC-EUR", until=1700086400000)
        assert _url_params(mock.call_args)["until"] == "1700086400000"

    async def test_since_omitted_when_not_provided(self, client):
        mock = _mock_http(client, CANDLE_RESPONSE)
        await client.get_candles("BTC-EUR")
        assert "since" not in _url_params(mock.call_args)

    async def test_until_omitted_when_not_provided(self, client):
        mock = _mock_http(client, CANDLE_RESPONSE)
        await client.get_candles("BTC-EUR")
        assert "until" not in _url_params(mock.call_args)

    async def test_limit_applied_client_side_not_as_query_param(self, client):
        mock = _mock_http(client, CANDLE_RESPONSE)
        result = await client.get_candles("BTC-EUR", limit=1)
        assert len(result) == 1
        assert "limit" not in _url_params(mock.call_args)

    async def test_returns_list_of_candle_dicts(self, client):
        _mock_http(client, CANDLE_RESPONSE)
        result = await client.get_candles("BTC-EUR")
        assert isinstance(result, list)
        assert len(result) == 2

    async def test_candle_fields_present(self, client):
        _mock_http(client, CANDLE_RESPONSE)
        result = await client.get_candles("BTC-EUR")
        candle = result[0]
        for field in ("start", "open", "high", "low", "close", "volume"):
            assert field in candle, f"Missing candle field: {field}"

    async def test_returns_empty_list_on_http_error(self, client):
        """get_candles swallows exceptions and returns [] to keep the bot alive."""
        _mock_http_error(client, 500, "Something went wrong!")
        result = await client.get_candles("BTC-EUR")
        assert result == []

    async def test_returns_empty_list_on_non_dict_response(self, client):
        _mock_http(client, [{"not": "a dict"}])
        result = await client.get_candles("BTC-EUR")
        assert result == []


# ===========================================================================
# 17. GET /tickers
# ===========================================================================


class TestGetTickers:
    async def test_calls_tickers_endpoint(self, client):
        mock = _mock_http(client, TICKERS_RESPONSE)
        await client.get_tickers()
        assert mock.call_args.kwargs["method"] == "GET"
        assert mock.call_args.kwargs["url"] == f"{BASE_URL}/tickers"

    async def test_no_symbols_param_sent_when_not_provided(self, client):
        mock = _mock_http(client, TICKERS_RESPONSE)
        await client.get_tickers()
        assert "symbols" not in _url_params(mock.call_args)

    async def test_symbols_filter_param(self, client):
        mock = _mock_http(client, TICKERS_RESPONSE)
        await client.get_tickers(symbols=["BTC-EUR", "ETH-EUR"])
        assert _url_params(mock.call_args)["symbols"] == "BTC-EUR,ETH-EUR"

    async def test_returns_list_from_data_envelope(self, client):
        _mock_http(client, TICKERS_RESPONSE)
        result = await client.get_tickers()
        assert isinstance(result, list)
        assert len(result) == 2

    async def test_ticker_fields_match_docs(self, client):
        _mock_http(client, TICKERS_RESPONSE)
        result = await client.get_tickers()
        t = result[0]
        for field in ("symbol", "bid", "ask", "mid", "last_price"):
            assert field in t, f"Missing ticker field: {field}"

    async def test_handles_bare_list_fallback(self, client):
        """Defensive: if API returns a bare list (no envelope), return it directly."""
        bare_list = [
            {
                "symbol": "BTC/EUR",
                "bid": "49900",
                "ask": "50100",
                "mid": "50000",
                "last_price": "50000",
            },
        ]
        _mock_http(client, bare_list)
        result = await client.get_tickers()
        assert isinstance(result, list)
        assert result[0]["symbol"] == "BTC/EUR"

    async def test_raises_value_error_on_dict_without_data_key(self, client):
        _mock_http(client, {"unexpected": "no data key"})
        with pytest.raises(ValueError, match="Unexpected /tickers response shape"):
            await client.get_tickers()

    async def test_raises_revolut_api_error_on_401(self, client):
        _mock_http_error(client, 401, "Unauthorized")
        with pytest.raises(RevolutAPIError) as exc:
            await client.get_tickers()
        assert exc.value.status_code == 401

    async def test_raises_revolut_api_error_on_429(self, client):
        _mock_http_error(client, 429, "Rate Limit Exceeded")
        with pytest.raises(RevolutAPIError) as exc:
            await client.get_tickers()
        assert exc.value.status_code == 429


# ===========================================================================
# Derived helper: get_ticker  (uses /order-book/{symbol})
# ===========================================================================


class TestGetTicker:
    async def test_uses_authenticated_order_book_endpoint(self, client):
        mock = _mock_http(client, ORDER_BOOK_RESPONSE)
        await client.get_ticker("BTC-EUR")
        assert "/order-book/BTC-EUR" in mock.call_args.kwargs["url"]
        assert "/public/" not in mock.call_args.kwargs["url"]

    async def test_returns_best_bid(self, client):
        _mock_http(client, ORDER_BOOK_RESPONSE)
        result = await client.get_ticker("BTC-EUR")
        assert result["bid"] == Decimal("50000.00")

    async def test_returns_best_ask(self, client):
        _mock_http(client, ORDER_BOOK_RESPONSE)
        result = await client.get_ticker("BTC-EUR")
        assert result["ask"] == Decimal("51000.00")

    async def test_last_is_midprice(self, client):
        _mock_http(client, ORDER_BOOK_RESPONSE)
        result = await client.get_ticker("BTC-EUR")
        assert result["last"] == (Decimal("50000.00") + Decimal("51000.00")) / 2

    async def test_volume_is_sum_of_bid_and_ask_quantities(self, client):
        _mock_http(client, ORDER_BOOK_RESPONSE)
        result = await client.get_ticker("BTC-EUR")
        # bids qty 0.2 + asks qty 0.1 = 0.3
        assert result["volume"] == Decimal("0.3")

    async def test_includes_symbol(self, client):
        _mock_http(client, ORDER_BOOK_RESPONSE)
        result = await client.get_ticker("BTC-EUR")
        assert result["symbol"] == "BTC-EUR"

    async def test_raises_value_error_on_empty_order_book(self, client):
        empty = {"data": {"asks": [], "bids": []}, "metadata": {"ts": 0}}
        _mock_http(client, empty)
        with pytest.raises(ValueError, match="Empty order book"):
            await client.get_ticker("BTC-EUR")

    async def test_raises_revolut_api_error_on_400(self, client):
        _mock_http_error(client, 400, "No such pair: BTC-BTC")
        with pytest.raises(RevolutAPIError) as exc:
            await client.get_ticker("BTC-BTC")
        assert exc.value.status_code == 400


# ===========================================================================
# check_permissions
# ===========================================================================


class TestCheckPermissions:
    def _balance_ok_resp(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.content = b"content"
        resp.json.return_value = BALANCE_RESPONSE
        resp.raise_for_status = MagicMock()
        return resp

    def _http_error_resp(self, status_code: int):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = {"message": "Test error", "error_id": "x", "timestamp": 0}
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}", request=MagicMock(), response=resp
        )
        return resp

    def _setup(self, client, balance_resp, order_status: int):
        order_resp = self._http_error_resp(order_status)
        client.client.request = AsyncMock(side_effect=[balance_resp, order_resp])
        # Prevent get_balance's FX ticker lookups from consuming side_effect slots
        client.get_ticker = AsyncMock(side_effect=ValueError("no pair"))

    async def test_view_true_when_balance_succeeds(self, client):
        self._setup(client, self._balance_ok_resp(), order_status=400)
        result = await client.check_permissions()
        assert result["view"] is True
        assert result["view_error"] is None

    async def test_view_false_error_deactivated_on_401(self, client):
        self._setup(client, self._http_error_resp(401), order_status=401)
        result = await client.check_permissions()
        assert result["view"] is False
        assert result["view_error"] == "deactivated"

    async def test_view_false_error_forbidden_on_403(self, client):
        self._setup(client, self._http_error_resp(403), order_status=403)
        result = await client.check_permissions()
        assert result["view"] is False
        assert result["view_error"] == "forbidden"

    async def test_view_false_error_http_code_on_other_status(self, client):
        self._setup(client, self._http_error_resp(500), order_status=401)
        result = await client.check_permissions()
        assert result["view"] is False
        assert result["view_error"] == "http_500"

    async def test_view_false_error_unreachable_on_connect_error(self, client):
        order_resp = self._http_error_resp(401)
        client.client.request = AsyncMock(
            side_effect=[
                httpx.ConnectError("connection refused"),  # balance - primary URL
                httpx.ConnectError("connection refused"),  # balance - fallback URL
                order_resp,  # order probe
            ]
        )
        result = await client.check_permissions()
        assert result["view"] is False
        assert result["view_error"] == "unreachable"

    async def test_trade_true_when_order_probe_returns_400(self, client):
        """400 = passed auth, failed payload validation → key can trade."""
        self._setup(client, self._balance_ok_resp(), order_status=400)
        result = await client.check_permissions()
        assert result["trade"] is True

    async def test_trade_true_when_order_probe_returns_422(self, client):
        self._setup(client, self._balance_ok_resp(), order_status=422)
        result = await client.check_permissions()
        assert result["trade"] is True

    async def test_trade_false_when_order_probe_returns_401(self, client):
        self._setup(client, self._balance_ok_resp(), order_status=401)
        result = await client.check_permissions()
        assert result["trade"] is False

    async def test_trade_false_when_order_probe_returns_403(self, client):
        self._setup(client, self._balance_ok_resp(), order_status=403)
        result = await client.check_permissions()
        assert result["trade"] is False

    async def test_never_raises(self, client):
        """check_permissions must never raise regardless of error type."""
        client.client.request = AsyncMock(side_effect=Exception("Unexpected"))
        result = await client.check_permissions()
        assert "view" in result
        assert "trade" in result
        assert "view_error" in result


# ===========================================================================
# RevolutAPIError exception
# ===========================================================================


class TestRevolutAPIError:
    async def test_http_error_converted_to_revolut_api_error(self, client):
        """_request must wrap httpx.HTTPStatusError as RevolutAPIError."""
        _mock_http_error(client, 400, "No such pair: BTC-BTC")
        with pytest.raises(RevolutAPIError) as exc:
            await client.get_balance()
        assert exc.value.status_code == 400
        assert "No such pair" in exc.value.message

    async def test_error_message_extracted_from_api_body(self, client):
        _mock_http_error(client, 404, "Order with ID 'xyz' not found", "err-id-456")
        with pytest.raises(RevolutAPIError) as exc:
            await client.get_order("xyz")
        assert exc.value.message == "Order with ID 'xyz' not found"

    async def test_str_representation_includes_status_and_message(self, client):
        err = RevolutAPIError(404, "Not found", "some-id")
        assert "404" in str(err)
        assert "Not found" in str(err)

    async def test_error_id_stored_on_exception(self, client):
        err = RevolutAPIError(400, "Bad request", "test-error-id")
        assert err.error_id == "test-error-id"

    async def test_httpx_transport_errors_not_swallowed(self, client):
        """Network errors (ConnectError) propagate after all URLs are exhausted."""
        client.client.request = AsyncMock(side_effect=httpx.ConnectError("timeout"))
        with pytest.raises(httpx.ConnectError):
            await client.get_balance()


# ===========================================================================
# Base URL fallback
# ===========================================================================


class TestBaseUrlFallback:
    """Client retries with the secondary base URL on connection failure."""

    async def test_authenticated_request_falls_back_on_connect_error(self, client):
        """_request retries with fallback URL when primary raises ConnectError."""
        success_resp = MagicMock()
        success_resp.status_code = 200
        success_resp.content = b"content"
        success_resp.json.return_value = CURRENCIES_RESPONSE
        success_resp.raise_for_status = MagicMock()

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ConnectError("primary unreachable")
            return success_resp

        client.client.request = AsyncMock(side_effect=side_effect)
        result = await client.get_currencies()
        assert result == CURRENCIES_RESPONSE
        assert call_count == 2

    async def test_fallback_url_is_remembered(self, client):
        """After fallback succeeds, base_url is updated to the fallback URL."""
        from src.config import REVOLUT_API_BASE_URLS

        success_resp = MagicMock()
        success_resp.status_code = 200
        success_resp.content = b"content"
        success_resp.json.return_value = CURRENCIES_RESPONSE
        success_resp.raise_for_status = MagicMock()

        async def side_effect(*args, **kwargs):
            url = kwargs.get("url", "")
            if REVOLUT_API_BASE_URLS[0].rstrip("/") in url:
                raise httpx.ConnectError("primary unreachable")
            return success_resp

        client.client.request = AsyncMock(side_effect=side_effect)
        await client.get_currencies()
        assert client.base_url == REVOLUT_API_BASE_URLS[1].rstrip("/")

    async def test_no_fallback_on_api_error(self, client):
        """HTTP 4xx errors are not retried with the fallback URL."""
        _mock_http_error(client, 401, "Unauthorized")
        with pytest.raises(RevolutAPIError) as exc_info:
            await client.get_balance()
        assert exc_info.value.status_code == 401
        assert client.client.request.call_count == 1

    async def test_public_request_falls_back_on_connect_error(self, client):
        """_public_request retries with fallback URL when primary raises ConnectError."""
        success_resp = MagicMock()
        success_resp.status_code = 200
        success_resp.content = b"content"
        success_resp.json.return_value = {"data": []}
        success_resp.raise_for_status = MagicMock()

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ConnectError("primary unreachable")
            return success_resp

        client.client.request = AsyncMock(side_effect=side_effect)
        result = await client.get_last_public_trades()
        assert result == {"data": []}
        assert call_count == 2
