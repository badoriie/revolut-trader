"""Unit tests for RevolutAPIClient — all 17 endpoints.

Mocks the HTTP transport layer (httpx) to verify:
- Correct endpoint paths and HTTP methods
- Request parameters and body structure
- Response parsing and normalization
- Error handling (malformed responses, HTTP errors → RevolutAPIError)
"""

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlparse

from src.api.client import RevolutAPIClient, RevolutAPIError

BASE_URL = "https://revx.revolut.com/api/1.0"


# ---------------------------------------------------------------------------
# URL-parsing helpers
# ---------------------------------------------------------------------------


def _url_params(mock_call) -> dict[str, str]:
    """Extract query parameters from the URL embedded in a mock call."""
    url = mock_call.kwargs["url"]
    parsed = urlparse(url)
    return {k: v[0] for k, v in parse_qs(parsed.query).items()}


def _base_url(mock_call) -> str:
    """Return the URL without the query string."""
    return urlparse(mock_call.kwargs["url"])._replace(query="").geturl()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def client():
    """RevolutAPIClient with a real (test-only) Ed25519 key — no 1Password."""
    c = RevolutAPIClient()
    c._private_key = Ed25519PrivateKey.generate()
    yield c
    await c.close()


# ---------------------------------------------------------------------------
# HTTP mock helpers
# ---------------------------------------------------------------------------


def _mock_http(client: RevolutAPIClient, json_data, status_code: int = 200) -> AsyncMock:
    """Replace the HTTP transport with a mock returning json_data."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.content = b"content"
    mock_resp.json.return_value = json_data
    mock_resp.raise_for_status = MagicMock()
    client.client.request = AsyncMock(return_value=mock_resp)
    return client.client.request


def _mock_http_error(client: RevolutAPIClient, status_code: int, message: str = "Error") -> AsyncMock:
    """Mock an HTTP error — raise_for_status raises HTTPStatusError."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.content = b"error"
    mock_resp.json.return_value = {"message": message, "error_id": "test-id", "timestamp": 0}
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        f"HTTP {status_code}",
        request=MagicMock(),
        response=mock_resp,
    )
    client.client.request = AsyncMock(return_value=mock_resp)
    return client.client.request


# ---------------------------------------------------------------------------
# Sample API payloads (mirrors real Revolut X response shapes from the docs)
# ---------------------------------------------------------------------------

BALANCE_RESPONSE = [
    {"currency": "BTC", "available": "0.5", "staked": "0", "reserved": "0.01", "total": "0.51"},
    {"currency": "EUR", "available": "5000.00", "staked": "0", "reserved": "0", "total": "5000.00"},
]

CURRENCIES_RESPONSE = {
    "BTC": {"symbol": "BTC", "name": "Bitcoin", "scale": 8, "asset_type": "crypto", "status": "active"},
    "EUR": {"symbol": "EUR", "name": "Euro", "scale": 2, "asset_type": "fiat", "status": "active"},
}

PAIRS_RESPONSE = {
    "BTC/EUR": {
        "base": "BTC", "quote": "EUR", "base_step": "0.0000001", "quote_step": "0.01",
        "min_order_size": "0.0000001", "max_order_size": "1000",
        "min_order_size_quote": "0.01", "status": "active",
    }
}

LAST_PUBLIC_TRADES_RESPONSE = {
    "data": [
        {
            "tdt": "2025-08-08T21:40:35.133962Z", "aid": "BTC", "anm": "Bitcoin",
            "p": "116243.32", "pc": "USD", "pn": "MONE", "q": "0.24521000",
            "qc": "BTC", "qn": "UNIT", "ve": "REVX",
            "pdt": "2025-08-08T21:40:35.133962Z", "vp": "REVX",
            "tid": "5ef9648f658149f7ababedc97a6401f8",
        }
    ],
    "metadata": {"timestamp": "2025-08-08T21:40:36.684333Z"},
}

ORDER_BOOK_RESPONSE = {
    "data": {
        "asks": [{"aid": "BTC", "anm": "Bitcoin", "s": "SELL", "p": "51000.00",
                  "pc": "EUR", "pn": "MONE", "q": "0.1", "qc": "BTC", "qn": "UNIT",
                  "ve": "REVX", "no": "1", "ts": "CLOB", "pdt": 1700000000000}],
        "bids": [{"aid": "BTC", "anm": "Bitcoin", "s": "BUY", "p": "50000.00",
                  "pc": "EUR", "pn": "MONE", "q": "0.2", "qc": "BTC", "qn": "UNIT",
                  "ve": "REVX", "no": "1", "ts": "CLOB", "pdt": 1700000000000}],
    },
    "metadata": {"ts": 1700000000000},
}

# create_order response: {"data": [{"venue_order_id", "client_order_id", "state"}]}
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
        {"start": 1700000000000, "open": "49000.00", "high": "51000.00",
         "low": "48500.00", "close": "50500.00", "volume": "10.5"},
        {"start": 1700003600000, "open": "50500.00", "high": "52000.00",
         "low": "50000.00", "close": "51500.00", "volume": "8.2"},
    ]
}

ORDERS_RESPONSE = {
    "data": [
        {
            "id": "order-1", "client_order_id": "client-1", "symbol": "BTC/EUR",
            "side": "buy", "type": "limit", "quantity": "0.01",
            "filled_quantity": "0", "leaves_quantity": "0.01",
            "price": "50000.00", "status": "new",
            "created_date": 1700000000000, "updated_date": 1700000000000,
        }
    ],
    "metadata": {"timestamp": 1700000000000, "next_cursor": None},
}

FILLS_RESPONSE = {
    "data": [
        {
            "tdt": 1700000000000, "aid": "BTC", "anm": "Bitcoin",
            "p": "50000.00", "pc": "EUR", "pn": "MONE",
            "q": "0.01", "qc": "BTC", "qn": "UNIT", "ve": "REVX",
            "pdt": 1700000000000, "vp": "REVX",
            "tid": "trade-1", "oid": "order-1", "s": "buy", "im": False,
        }
    ]
}

TICKERS_RESPONSE = {
    "data": [
        {"symbol": "BTC/EUR", "bid": "49900.00", "ask": "50100.00",
         "mid": "50000.00", "last_price": "50000.00"},
        {"symbol": "ETH/EUR", "bid": "2990.00", "ask": "3010.00",
         "mid": "3000.00", "last_price": "3000.00"},
    ],
    "metadata": {"timestamp": 1700000000000},
}

TRADES_RESPONSE = {
    "data": [
        {
            "tdt": 1700000000000, "aid": "BTC", "anm": "Bitcoin",
            "p": "50000.00", "pc": "EUR", "pn": "MONE",
            "q": "0.01", "qc": "BTC", "qn": "UNIT", "ve": "REVX",
            "pdt": 1700000000000, "vp": "REVX", "tid": "trade-1",
        }
    ],
    "metadata": {"timestamp": 1700000000000, "next_cursor": None},
}

PRIVATE_TRADES_RESPONSE = {
    "data": [
        {
            **TRADES_RESPONSE["data"][0],
            "oid": "order-1", "s": "buy", "im": False,
        }
    ],
    "metadata": {"timestamp": 1700000000000, "next_cursor": None},
}


# ===========================================================================
# Tests — one class per client method
# ===========================================================================


class TestGetBalance:
    async def test_calls_balances_endpoint(self, client):
        mock = _mock_http(client, BALANCE_RESPONSE)
        await client.get_balance()
        assert mock.call_args.kwargs["method"] == "GET"
        assert mock.call_args.kwargs["url"] == f"{BASE_URL}/balances"

    async def test_returns_currency_keyed_dict(self, client):
        _mock_http(client, BALANCE_RESPONSE)
        result = await client.get_balance()
        assert "BTC" in result["balances"]
        assert "EUR" in result["balances"]

    async def test_balance_values_parsed_correctly(self, client):
        _mock_http(client, BALANCE_RESPONSE)
        result = await client.get_balance()
        btc = result["balances"]["BTC"]
        assert btc["available"] == 0.5
        assert btc["reserved"] == 0.01
        assert btc["total"] == 0.51

    async def test_includes_currencies_list(self, client):
        _mock_http(client, BALANCE_RESPONSE)
        result = await client.get_balance()
        assert set(result["currencies"]) == {"BTC", "EUR"}

    async def test_raises_on_non_list_response(self, client):
        _mock_http(client, {"error": "unexpected dict"})
        with pytest.raises(ValueError, match="Invalid balance response"):
            await client.get_balance()


class TestGetCurrencies:
    async def test_calls_configuration_currencies(self, client):
        mock = _mock_http(client, CURRENCIES_RESPONSE)
        await client.get_currencies()
        assert mock.call_args.kwargs["method"] == "GET"
        assert mock.call_args.kwargs["url"] == f"{BASE_URL}/configuration/currencies"

    async def test_returns_dict_keyed_by_symbol(self, client):
        _mock_http(client, CURRENCIES_RESPONSE)
        result = await client.get_currencies()
        assert "BTC" in result
        assert result["BTC"]["name"] == "Bitcoin"
        assert result["BTC"]["scale"] == 8

    async def test_raises_on_non_dict_response(self, client):
        _mock_http(client, [{"unexpected": "list"}])
        with pytest.raises(ValueError, match="Invalid currencies response"):
            await client.get_currencies()


class TestGetCurrencyPairs:
    async def test_calls_configuration_pairs(self, client):
        mock = _mock_http(client, PAIRS_RESPONSE)
        await client.get_currency_pairs()
        assert mock.call_args.kwargs["method"] == "GET"
        assert mock.call_args.kwargs["url"] == f"{BASE_URL}/configuration/pairs"

    async def test_returns_dict_keyed_by_pair(self, client):
        _mock_http(client, PAIRS_RESPONSE)
        result = await client.get_currency_pairs()
        assert "BTC/EUR" in result
        assert result["BTC/EUR"]["base"] == "BTC"

    async def test_raises_on_non_dict_response(self, client):
        _mock_http(client, [{"unexpected": "list"}])
        with pytest.raises(ValueError, match="Invalid pairs response"):
            await client.get_currency_pairs()


class TestGetLastPublicTrades:
    async def test_calls_public_last_trades(self, client):
        mock = _mock_http(client, LAST_PUBLIC_TRADES_RESPONSE)
        await client.get_last_public_trades()
        assert mock.call_args.kwargs["url"] == f"{BASE_URL}/public/last-trades"

    async def test_returns_dict_with_data(self, client):
        _mock_http(client, LAST_PUBLIC_TRADES_RESPONSE)
        result = await client.get_last_public_trades()
        assert "data" in result
        assert len(result["data"]) == 1
        assert result["data"][0]["aid"] == "BTC"

    async def test_raises_on_non_dict_response(self, client):
        _mock_http(client, [{"unexpected": "list"}])
        with pytest.raises(ValueError, match="Invalid last-trades response"):
            await client.get_last_public_trades()


class TestGetPublicOrderBook:
    async def test_calls_public_order_book_endpoint(self, client):
        mock = _mock_http(client, ORDER_BOOK_RESPONSE)
        await client.get_public_order_book("BTC-EUR")
        assert mock.call_args.kwargs["url"] == f"{BASE_URL}/public/order-book/BTC-EUR"

    async def test_no_query_params_sent(self, client):
        """Public order book endpoint has no query parameters."""
        mock = _mock_http(client, ORDER_BOOK_RESPONSE)
        await client.get_public_order_book("BTC-EUR")
        assert _url_params(mock.call_args) == {}

    async def test_returns_dict_with_bids_and_asks(self, client):
        _mock_http(client, ORDER_BOOK_RESPONSE)
        result = await client.get_public_order_book("BTC-EUR")
        assert "data" in result
        assert "asks" in result["data"]
        assert "bids" in result["data"]

    async def test_raises_on_non_dict_response(self, client):
        _mock_http(client, [{"unexpected": "list"}])
        with pytest.raises(ValueError, match="Invalid public order book response"):
            await client.get_public_order_book("BTC-EUR")


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
        body = mock.call_args.kwargs["json"]
        _uuid.UUID(body["client_order_id"])  # raises if not valid UUID

    async def test_limit_order_requires_price(self, client):
        with pytest.raises(ValueError, match="price is required"):
            await client.create_order("BTC-EUR", "buy", "limit", 0.01)

    async def test_invalid_order_type_raises(self, client):
        with pytest.raises(ValueError, match="Unsupported order_type"):
            await client.create_order("BTC-EUR", "buy", "stop_loss", 0.01)

    async def test_returns_venue_order_id_and_state(self, client):
        _mock_http(client, ORDER_CREATION_RESPONSE)
        result = await client.create_order("BTC-EUR", "buy", "limit", 0.01, price=50000.0)
        assert result["venue_order_id"] == "7a52e92e-8639-4fe1-abaa-68d3a2d5234b"
        assert result["client_order_id"] == "984a4d8a-2a9b-4950-822f-2a40037f02bd"
        assert result["state"] == "new"

    async def test_side_is_lowercased(self, client):
        mock = _mock_http(client, ORDER_CREATION_RESPONSE)
        await client.create_order("BTC-EUR", "BUY", "limit", 0.01, price=50000.0)
        body = mock.call_args.kwargs["json"]
        assert body["side"] == "buy"

    async def test_raises_on_missing_data_key(self, client):
        _mock_http(client, {"unexpected": "no data key"})
        with pytest.raises(ValueError, match="Unexpected create_order response"):
            await client.create_order("BTC-EUR", "buy", "limit", 0.01, price=50000.0)

    async def test_raises_on_empty_data_list(self, client):
        _mock_http(client, {"data": []})
        with pytest.raises(ValueError, match="Empty data"):
            await client.create_order("BTC-EUR", "buy", "limit", 0.01, price=50000.0)


class TestCancelAllOrders:
    async def test_calls_delete_on_orders_endpoint(self, client):
        mock = _mock_http(client, {})
        await client.cancel_all_orders()
        assert mock.call_args.kwargs["method"] == "DELETE"
        assert mock.call_args.kwargs["url"] == f"{BASE_URL}/orders"

    async def test_returns_none(self, client):
        _mock_http(client, {})
        result = await client.cancel_all_orders()
        assert result is None


class TestGetOpenOrders:
    async def test_calls_orders_active_endpoint(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_open_orders()
        assert mock.call_args.kwargs["method"] == "GET"
        assert _base_url(mock.call_args) == f"{BASE_URL}/orders/active"

    async def test_optional_symbols_filter(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_open_orders(symbols=["BTC-EUR", "ETH-EUR"])
        assert _url_params(mock.call_args)["symbols"] == "BTC-EUR,ETH-EUR"

    async def test_optional_sides_filter(self, client):
        """Filter param is 'sides' (plural), not 'side'."""
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_open_orders(sides=["buy"])
        assert _url_params(mock.call_args)["sides"] == "buy"

    async def test_optional_states_filter(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_open_orders(states=["new", "partially_filled"])
        assert _url_params(mock.call_args)["states"] == "new,partially_filled"

    async def test_optional_types_filter(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_open_orders(types=["limit"])
        assert _url_params(mock.call_args)["types"] == "limit"

    async def test_symbols_omitted_when_not_provided(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_open_orders()
        assert "symbols" not in _url_params(mock.call_args)

    async def test_cursor_pagination(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_open_orders(cursor="next-page-token")
        assert _url_params(mock.call_args)["cursor"] == "next-page-token"

    async def test_raises_on_non_dict_response(self, client):
        _mock_http(client, [{"unexpected": "list"}])
        with pytest.raises(ValueError, match="Invalid active orders response"):
            await client.get_open_orders()


class TestGetHistoricalOrders:
    async def test_calls_orders_historical_endpoint(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_historical_orders()
        assert mock.call_args.kwargs["method"] == "GET"
        assert _base_url(mock.call_args) == f"{BASE_URL}/orders/historical"

    async def test_passes_date_range_params(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_historical_orders(start_date=1700000000000, end_date=1700086400000)
        params = _url_params(mock.call_args)
        assert params["start_date"] == "1700000000000"
        assert params["end_date"] == "1700086400000"

    async def test_date_params_omitted_when_not_provided(self, client):
        """Server handles date defaults; client must NOT inject start_date automatically."""
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_historical_orders()
        params = _url_params(mock.call_args)
        assert "start_date" not in params
        assert "end_date" not in params

    async def test_symbols_filter(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_historical_orders(symbols=["ETH-EUR"])
        assert _url_params(mock.call_args)["symbols"] == "ETH-EUR"

    async def test_states_filter(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_historical_orders(states=["filled", "cancelled"])
        assert set(_url_params(mock.call_args)["states"].split(",")) == {"filled", "cancelled"}


class TestGetOrder:
    async def test_calls_correct_endpoint(self, client):
        mock = _mock_http(client, {"data": {"id": "order-1", "status": "new"}})
        await client.get_order("venue-order-uuid-123")
        assert mock.call_args.kwargs["method"] == "GET"
        assert mock.call_args.kwargs["url"] == f"{BASE_URL}/orders/venue-order-uuid-123"

    async def test_unwraps_data_envelope(self, client):
        """API wraps single order in {"data": {...}} — client unwraps it."""
        _mock_http(client, {"data": {"id": "order-1", "status": "filled", "symbol": "BTC/EUR"}})
        result = await client.get_order("venue-order-uuid-123")
        assert result["id"] == "order-1"
        assert result["status"] == "filled"
        assert "data" not in result  # envelope removed


class TestCancelOrder:
    async def test_calls_delete_on_order_path(self, client):
        mock = _mock_http(client, {})
        await client.cancel_order("venue-order-uuid-123")
        assert mock.call_args.kwargs["method"] == "DELETE"
        assert mock.call_args.kwargs["url"] == f"{BASE_URL}/orders/venue-order-uuid-123"

    async def test_returns_none(self, client):
        _mock_http(client, {})
        result = await client.cancel_order("venue-order-uuid-123")
        assert result is None


class TestGetOrderFills:
    async def test_calls_fills_endpoint_correct_path(self, client):
        """Path is /orders/fills/{id} — NOT /orders/{id}/fills."""
        mock = _mock_http(client, FILLS_RESPONSE)
        await client.get_order_fills("venue-order-uuid-123")
        assert mock.call_args.kwargs["method"] == "GET"
        assert mock.call_args.kwargs["url"] == f"{BASE_URL}/orders/fills/venue-order-uuid-123"

    async def test_returns_fills_data(self, client):
        _mock_http(client, FILLS_RESPONSE)
        result = await client.get_order_fills("venue-order-uuid-123")
        assert "data" in result
        assert result["data"][0]["tid"] == "trade-1"
        assert result["data"][0]["p"] == "50000.00"
        assert result["data"][0]["s"] == "buy"
        assert result["data"][0]["im"] is False

    async def test_raises_on_non_dict_response(self, client):
        _mock_http(client, [{"unexpected": "list"}])
        with pytest.raises(ValueError, match="Invalid fills response"):
            await client.get_order_fills("venue-order-uuid-123")


class TestGetPublicTrades:
    async def test_calls_trades_all_endpoint(self, client):
        mock = _mock_http(client, TRADES_RESPONSE)
        await client.get_public_trades("BTC-EUR")
        assert mock.call_args.kwargs["method"] == "GET"
        assert _base_url(mock.call_args) == f"{BASE_URL}/trades/all/BTC-EUR"

    async def test_symbol_is_path_param_not_query_param(self, client):
        mock = _mock_http(client, TRADES_RESPONSE)
        await client.get_public_trades("BTC-EUR")
        assert "symbol" not in _url_params(mock.call_args)

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

    async def test_different_symbols_hit_different_paths(self, client):
        mock = _mock_http(client, TRADES_RESPONSE)
        await client.get_public_trades("ETH-EUR")
        assert _base_url(mock.call_args) == f"{BASE_URL}/trades/all/ETH-EUR"


class TestGetTrades:
    async def test_calls_trades_private_endpoint(self, client):
        mock = _mock_http(client, PRIVATE_TRADES_RESPONSE)
        await client.get_trades("BTC-EUR")
        assert mock.call_args.kwargs["method"] == "GET"
        assert _base_url(mock.call_args) == f"{BASE_URL}/trades/private/BTC-EUR"

    async def test_symbol_is_path_param_not_query_param(self, client):
        mock = _mock_http(client, PRIVATE_TRADES_RESPONSE)
        await client.get_trades("BTC-EUR")
        assert "symbol" not in _url_params(mock.call_args)

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

    async def test_different_symbols_hit_different_paths(self, client):
        mock = _mock_http(client, PRIVATE_TRADES_RESPONSE)
        await client.get_trades("ETH-EUR")
        assert _base_url(mock.call_args) == f"{BASE_URL}/trades/private/ETH-EUR"

    async def test_private_trades_include_side_and_order_id(self, client):
        _mock_http(client, PRIVATE_TRADES_RESPONSE)
        result = await client.get_trades("BTC-EUR")
        trade = result["data"][0]
        assert trade["s"] == "buy"
        assert trade["oid"] == "order-1"
        assert trade["im"] is False


class TestGetOrderBook:
    async def test_calls_authenticated_order_book_endpoint(self, client):
        """Authenticated order book is /order-book/{symbol} (NOT /public/order-book/)."""
        mock = _mock_http(client, ORDER_BOOK_RESPONSE)
        await client.get_order_book("BTC-EUR")
        assert mock.call_args.kwargs["method"] == "GET"
        assert _base_url(mock.call_args) == f"{BASE_URL}/order-book/BTC-EUR"

    async def test_passes_depth_not_limit(self, client):
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

    async def test_returns_dict_with_bids_and_asks(self, client):
        _mock_http(client, ORDER_BOOK_RESPONSE)
        result = await client.get_order_book("BTC-EUR")
        assert "data" in result
        assert "asks" in result["data"]
        assert "bids" in result["data"]

    async def test_raises_on_non_dict_response(self, client):
        _mock_http(client, [{"unexpected": "list"}])
        with pytest.raises(ValueError, match="Invalid order book response"):
            await client.get_order_book("BTC-EUR")


class TestGetTicker:
    async def test_uses_authenticated_order_book_endpoint(self, client):
        """get_ticker derives from /order-book/{symbol} (authenticated)."""
        mock = _mock_http(client, ORDER_BOOK_RESPONSE)
        await client.get_ticker("BTC-EUR")
        assert f"/order-book/BTC-EUR" in mock.call_args.kwargs["url"]
        assert "/public/" not in mock.call_args.kwargs["url"]

    async def test_returns_best_bid(self, client):
        _mock_http(client, ORDER_BOOK_RESPONSE)
        result = await client.get_ticker("BTC-EUR")
        assert result["bid"] == 50000.0

    async def test_returns_best_ask(self, client):
        _mock_http(client, ORDER_BOOK_RESPONSE)
        result = await client.get_ticker("BTC-EUR")
        assert result["ask"] == 51000.0

    async def test_last_is_midprice(self, client):
        _mock_http(client, ORDER_BOOK_RESPONSE)
        result = await client.get_ticker("BTC-EUR")
        assert result["last"] == (50000.0 + 51000.0) / 2

    async def test_includes_symbol(self, client):
        _mock_http(client, ORDER_BOOK_RESPONSE)
        result = await client.get_ticker("BTC-EUR")
        assert result["symbol"] == "BTC-EUR"

    async def test_raises_on_empty_order_book(self, client):
        empty = {"data": {"asks": [], "bids": []}, "metadata": {"ts": 0}}
        _mock_http(client, empty)
        with pytest.raises(ValueError, match="Empty order book"):
            await client.get_ticker("BTC-EUR")


class TestGetCandles:
    async def test_calls_candles_endpoint(self, client):
        mock = _mock_http(client, CANDLE_RESPONSE)
        await client.get_candles("BTC-EUR")
        assert mock.call_args.kwargs["method"] == "GET"
        assert _base_url(mock.call_args) == f"{BASE_URL}/candles/BTC-EUR"

    async def test_passes_interval_param(self, client):
        mock = _mock_http(client, CANDLE_RESPONSE)
        await client.get_candles("BTC-EUR", interval=15)
        assert _url_params(mock.call_args)["interval"] == "15"

    async def test_passes_since_param(self, client):
        mock = _mock_http(client, CANDLE_RESPONSE)
        await client.get_candles("BTC-EUR", since=1700000000000)
        assert _url_params(mock.call_args)["since"] == "1700000000000"

    async def test_passes_until_param(self, client):
        mock = _mock_http(client, CANDLE_RESPONSE)
        await client.get_candles("BTC-EUR", until=1700086400000)
        assert _url_params(mock.call_args)["until"] == "1700086400000"

    async def test_since_omitted_when_not_provided(self, client):
        mock = _mock_http(client, CANDLE_RESPONSE)
        await client.get_candles("BTC-EUR")
        assert "since" not in _url_params(mock.call_args)

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
        assert result[0]["open"] == "49000.00"

    async def test_returns_empty_list_on_error(self, client):
        """get_candles swallows errors and returns [] to keep the bot alive."""
        _mock_http_error(client, 500)
        result = await client.get_candles("BTC-EUR")
        assert result == []


class TestGetTickers:
    async def test_calls_tickers_endpoint(self, client):
        mock = _mock_http(client, TICKERS_RESPONSE)
        await client.get_tickers()
        assert mock.call_args.kwargs["method"] == "GET"
        assert mock.call_args.kwargs["url"] == f"{BASE_URL}/tickers"

    async def test_returns_list_from_data_envelope(self, client):
        _mock_http(client, TICKERS_RESPONSE)
        result = await client.get_tickers()
        assert isinstance(result, list)
        assert len(result) == 2

    async def test_ticker_fields_match_docs(self, client):
        _mock_http(client, TICKERS_RESPONSE)
        result = await client.get_tickers()
        t = result[0]
        assert "symbol" in t
        assert "bid" in t
        assert "ask" in t
        assert "mid" in t
        assert "last_price" in t

    async def test_symbols_filter_param(self, client):
        mock = _mock_http(client, TICKERS_RESPONSE)
        await client.get_tickers(symbols=["BTC-EUR", "ETH-EUR"])
        assert _url_params(mock.call_args)["symbols"] == "BTC-EUR,ETH-EUR"

    async def test_raises_on_dict_without_data_key(self, client):
        _mock_http(client, {"unexpected": "no data key"})
        with pytest.raises(ValueError, match="Unexpected /tickers response shape"):
            await client.get_tickers()


class TestCheckPermissions:
    """check_permissions now catches RevolutAPIError (wraps httpx.HTTPStatusError)."""

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
            f"HTTP {status_code}",
            request=MagicMock(),
            response=resp,
        )
        return resp

    def _setup(self, client, balance_resp, order_status: int):
        order_resp = self._http_error_resp(order_status)
        client.client.request = AsyncMock(side_effect=[balance_resp, order_resp])

    async def test_view_true_when_balance_succeeds(self, client):
        self._setup(client, self._balance_ok_resp(), order_status=400)
        result = await client.check_permissions()
        assert result["view"] is True
        assert result["view_error"] is None

    async def test_view_false_and_error_deactivated_on_401(self, client):
        self._setup(client, self._http_error_resp(401), order_status=401)
        result = await client.check_permissions()
        assert result["view"] is False
        assert result["view_error"] == "deactivated"

    async def test_view_false_and_error_forbidden_on_403(self, client):
        self._setup(client, self._http_error_resp(403), order_status=403)
        result = await client.check_permissions()
        assert result["view"] is False
        assert result["view_error"] == "forbidden"

    async def test_view_false_and_error_http_code_on_other_status(self, client):
        self._setup(client, self._http_error_resp(500), order_status=401)
        result = await client.check_permissions()
        assert result["view"] is False
        assert result["view_error"] == "http_500"

    async def test_view_false_and_error_unreachable_on_connect_error(self, client):
        order_resp = self._http_error_resp(401)
        client.client.request = AsyncMock(
            side_effect=[httpx.ConnectError("connection refused"), order_resp]
        )
        result = await client.check_permissions()
        assert result["view"] is False
        assert result["view_error"] == "unreachable"

    async def test_trade_true_when_order_probe_returns_400(self, client):
        """400 = auth passed, payload invalid → key has trading permissions."""
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


class TestRevolutAPIError:
    async def test_raises_revolut_api_error_on_http_error(self, client):
        """_request wraps httpx.HTTPStatusError as RevolutAPIError."""
        _mock_http_error(client, 400, "No such pair: BTC-BTC")
        with pytest.raises(RevolutAPIError) as exc_info:
            await client.get_balance()
        assert exc_info.value.status_code == 400
        assert "No such pair" in exc_info.value.message

    async def test_revolut_api_error_includes_status_code(self, client):
        _mock_http_error(client, 404, "Order not found")
        with pytest.raises(RevolutAPIError) as exc_info:
            await client.get_order("nonexistent-id")
        assert exc_info.value.status_code == 404
