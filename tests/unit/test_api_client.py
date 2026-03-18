"""Unit tests for RevolutAPIClient.

Mocks the HTTP transport layer (httpx) to verify:
- Correct endpoint paths and HTTP methods for every client method
- Request parameters and body structure
- Response parsing and normalization
- Error handling (malformed responses, HTTP errors)
"""

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from unittest.mock import AsyncMock, MagicMock

from src.api.client import RevolutAPIClient

BASE_URL = "https://revx.revolut.com/api/1.0"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def client():
    """RevolutAPIClient with mocked 1Password and a real (test-only) Ed25519 key.

    Bypasses initialize() by directly injecting a generated private key,
    avoiding any real 1Password or filesystem access.
    """
    c = RevolutAPIClient()
    c._private_key = Ed25519PrivateKey.generate()
    yield c
    await c.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_http(client: RevolutAPIClient, json_data, status_code: int = 200) -> AsyncMock:
    """Replace the client's httpx transport with a mock returning json_data."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.content = b"content"
    mock_resp.json.return_value = json_data
    mock_resp.raise_for_status = MagicMock()
    client.client.request = AsyncMock(return_value=mock_resp)
    return client.client.request


def _mock_http_error(client: RevolutAPIClient, status_code: int) -> AsyncMock:
    """Mock an HTTP error response with the given status code."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.content = b"error"
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        f"HTTP {status_code}",
        request=MagicMock(),
        response=MagicMock(status_code=status_code),
    )
    client.client.request = AsyncMock(return_value=mock_resp)
    return client.client.request


# ---------------------------------------------------------------------------
# Sample API payloads (mirrors real Revolut X API response shapes)
# ---------------------------------------------------------------------------

BALANCE_RESPONSE = [
    {"currency": "BTC", "available": "0.5", "staked": "0", "reserved": "0.01", "total": "0.51"},
    {"currency": "EUR", "available": "5000.00", "staked": "0", "reserved": "0", "total": "5000.00"},
]

ORDER_BOOK_RESPONSE = {
    "data": {
        "asks": [
            {
                "p": "51000.00",
                "q": "0.1",
                "aid": "BTC",
                "anm": "Bitcoin",
                "s": "SELL",
                "pc": "EUR",
                "pn": "EUR",
                "qc": "BTC",
                "qn": "BTC",
                "ve": "REVX",
                "no": "1",
                "ts": "CLOB",
                "pdt": 1700000000000,
            }
        ],
        "bids": [
            {
                "p": "50000.00",
                "q": "0.2",
                "aid": "BTC",
                "anm": "Bitcoin",
                "s": "BUY",
                "pc": "EUR",
                "pn": "EUR",
                "qc": "BTC",
                "qn": "BTC",
                "ve": "REVX",
                "no": "1",
                "ts": "CLOB",
                "pdt": 1700000000000,
            }
        ],
    },
    "metadata": {"timestamp": 1700000000000},
}

ORDER_CREATION_RESPONSE = {
    "data": {
        "orderId": "abc-123",
        "status": "new",
        "symbol": "BTC-EUR",
        "side": "buy",
        "quantity": "0.01",
        "price": "50000.00",
    }
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
            "symbol": "BTC-EUR",
            "side": "buy",
            "type": "limit",
            "quantity": "0.01",
            "filled_quantity": "0",
            "price": "50000.00",
            "status": "new",
            "created_date": 1700000000000,
            "updated_date": 1700000000000,
        }
    ],
    "metadata": {"next_cursor": None},
}

FILLS_RESPONSE = {
    "data": [
        {
            "tdt": 1700000000000,
            "aid": "BTC",
            "anm": "Bitcoin",
            "p": "50000.00",
            "pc": "EUR",
            "pn": "EUR",
            "q": "0.01",
            "qc": "BTC",
            "qn": "BTC",
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

TICKERS_RESPONSE = [
    {"symbol": "BTC-EUR", "bid": "49900.00", "ask": "50100.00", "last": "50000.00"},
    {"symbol": "ETH-EUR", "bid": "2990.00", "ask": "3010.00", "last": "3000.00"},
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


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
        with pytest.raises(ValueError, match="Invalid balance response format"):
            await client.get_balance()


class TestGetOrderBook:
    async def test_calls_public_order_book_endpoint(self, client):
        mock = _mock_http(client, ORDER_BOOK_RESPONSE)
        await client.get_order_book("BTC-EUR")
        assert mock.call_args.kwargs["method"] == "GET"
        assert mock.call_args.kwargs["url"] == f"{BASE_URL}/public/order-book/BTC-EUR"

    async def test_passes_limit_as_query_param(self, client):
        mock = _mock_http(client, ORDER_BOOK_RESPONSE)
        await client.get_order_book("BTC-EUR", limit=5)
        assert mock.call_args.kwargs["params"]["limit"] == 5

    async def test_default_limit_is_20(self, client):
        mock = _mock_http(client, ORDER_BOOK_RESPONSE)
        await client.get_order_book("BTC-EUR")
        assert mock.call_args.kwargs["params"]["limit"] == 20

    async def test_returns_raw_dict_with_bids_and_asks(self, client):
        _mock_http(client, ORDER_BOOK_RESPONSE)
        result = await client.get_order_book("BTC-EUR")
        assert "data" in result
        assert "asks" in result["data"]
        assert "bids" in result["data"]

    async def test_raises_on_non_dict_response(self, client):
        _mock_http(client, [{"unexpected": "list"}])
        with pytest.raises(ValueError, match="Expected dict"):
            await client.get_order_book("BTC-EUR")


class TestGetTicker:
    async def test_calls_public_order_book_endpoint(self, client):
        mock = _mock_http(client, ORDER_BOOK_RESPONSE)
        await client.get_ticker("BTC-EUR")
        assert f"/public/order-book/BTC-EUR" in mock.call_args.kwargs["url"]

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
        empty_book = {"data": {"asks": [], "bids": []}, "metadata": {"timestamp": 0}}
        _mock_http(client, empty_book)
        with pytest.raises(ValueError, match="Empty order book"):
            await client.get_ticker("BTC-EUR")


class TestGetTickers:
    async def test_calls_tickers_endpoint(self, client):
        mock = _mock_http(client, TICKERS_RESPONSE)
        await client.get_tickers()
        assert mock.call_args.kwargs["method"] == "GET"
        assert mock.call_args.kwargs["url"] == f"{BASE_URL}/tickers"

    async def test_returns_list_when_response_is_bare_array(self, client):
        _mock_http(client, TICKERS_RESPONSE)
        result = await client.get_tickers()
        assert isinstance(result, list)
        assert len(result) == 2

    async def test_unwraps_data_envelope_when_response_is_dict(self, client):
        """API may return {"data": [...]} instead of a bare array."""
        _mock_http(client, {"data": TICKERS_RESPONSE, "metadata": {}})
        result = await client.get_tickers()
        assert isinstance(result, list)
        assert len(result) == 2

    async def test_raises_on_dict_without_data_key(self, client):
        _mock_http(client, {"unexpected": "no data key"})
        with pytest.raises(ValueError, match="Unexpected /tickers response shape"):
            await client.get_tickers()


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
        import uuid
        mock = _mock_http(client, ORDER_CREATION_RESPONSE)
        await client.create_order("BTC-EUR", "buy", "limit", 0.01, price=50000.0)
        body = mock.call_args.kwargs["json"]
        # Should not raise
        uuid.UUID(body["client_order_id"])

    async def test_limit_order_requires_price(self, client):
        with pytest.raises(ValueError, match="price is required"):
            await client.create_order("BTC-EUR", "buy", "limit", 0.01)

    async def test_invalid_order_type_raises(self, client):
        with pytest.raises(ValueError, match="Unsupported order_type"):
            await client.create_order("BTC-EUR", "buy", "stop_loss", 0.01)

    async def test_returns_normalized_order_dict(self, client):
        _mock_http(client, ORDER_CREATION_RESPONSE)
        result = await client.create_order("BTC-EUR", "buy", "limit", 0.01, price=50000.0)
        assert result["orderId"] == "abc-123"
        assert result["status"] == "new"
        assert result["symbol"] == "BTC-EUR"
        assert result["side"] == "buy"

    async def test_side_is_lowercased(self, client):
        mock = _mock_http(client, ORDER_CREATION_RESPONSE)
        await client.create_order("BTC-EUR", "BUY", "limit", 0.01, price=50000.0)
        body = mock.call_args.kwargs["json"]
        assert body["side"] == "buy"

    async def test_raises_on_malformed_response(self, client):
        _mock_http(client, {"data": {"missing_required_fields": True}})
        with pytest.raises(ValueError, match="Malformed order response"):
            await client.create_order("BTC-EUR", "buy", "limit", 0.01, price=50000.0)


class TestCancelOrder:
    async def test_calls_delete_on_order_path(self, client):
        mock = _mock_http(client, {})
        await client.cancel_order("venue-order-uuid-123")
        assert mock.call_args.kwargs["method"] == "DELETE"
        assert mock.call_args.kwargs["url"] == f"{BASE_URL}/orders/venue-order-uuid-123"

    async def test_returns_empty_dict_on_no_content(self, client):
        _mock_http(client, {})
        result = await client.cancel_order("venue-order-uuid-123")
        assert result == {}


class TestCancelAllOrders:
    async def test_calls_delete_on_orders_endpoint(self, client):
        mock = _mock_http(client, {})
        await client.cancel_all_orders()
        assert mock.call_args.kwargs["method"] == "DELETE"
        assert mock.call_args.kwargs["url"] == f"{BASE_URL}/orders"

    async def test_returns_empty_dict(self, client):
        _mock_http(client, {})
        result = await client.cancel_all_orders()
        assert result == {}


class TestGetOrder:
    async def test_calls_correct_endpoint(self, client):
        mock = _mock_http(client, {"id": "order-1", "status": "new"})
        await client.get_order("venue-order-uuid-123")
        assert mock.call_args.kwargs["method"] == "GET"
        assert mock.call_args.kwargs["url"] == f"{BASE_URL}/orders/venue-order-uuid-123"

    async def test_returns_order_dict(self, client):
        _mock_http(client, {"id": "order-1", "status": "filled", "symbol": "BTC-EUR"})
        result = await client.get_order("venue-order-uuid-123")
        assert result["id"] == "order-1"
        assert result["status"] == "filled"


class TestGetOrderFills:
    async def test_calls_fills_endpoint(self, client):
        mock = _mock_http(client, FILLS_RESPONSE)
        await client.get_order_fills("venue-order-uuid-123")
        assert mock.call_args.kwargs["method"] == "GET"
        assert mock.call_args.kwargs["url"] == f"{BASE_URL}/orders/venue-order-uuid-123/fills"

    async def test_returns_fills_data(self, client):
        _mock_http(client, FILLS_RESPONSE)
        result = await client.get_order_fills("venue-order-uuid-123")
        assert "data" in result
        assert len(result["data"]) == 1
        assert result["data"][0]["tid"] == "trade-1"
        assert result["data"][0]["p"] == "50000.00"


class TestGetOpenOrders:
    async def test_calls_get_orders_endpoint(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_open_orders()
        assert mock.call_args.kwargs["method"] == "GET"
        assert mock.call_args.kwargs["url"] == f"{BASE_URL}/orders"

    async def test_filters_by_active_order_states(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_open_orders()
        states = mock.call_args.kwargs["params"]["order_states"]
        assert "pending_new" in states
        assert "new" in states
        assert "partially_filled" in states

    async def test_does_not_include_terminal_states(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_open_orders()
        states = mock.call_args.kwargs["params"]["order_states"].split(",")
        assert "filled" not in states
        assert "cancelled" not in states

    async def test_optional_symbols_filter(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_open_orders(symbols=["BTC-EUR", "ETH-EUR"])
        assert mock.call_args.kwargs["params"]["symbols"] == "BTC-EUR,ETH-EUR"

    async def test_optional_side_filter(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_open_orders(side="buy")
        assert mock.call_args.kwargs["params"]["side"] == "buy"

    async def test_symbols_omitted_when_not_provided(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_open_orders()
        assert "symbols" not in mock.call_args.kwargs["params"]

    async def test_cursor_pagination(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_open_orders(cursor="next-page-token")
        assert mock.call_args.kwargs["params"]["cursor"] == "next-page-token"


class TestGetHistoricalOrders:
    async def test_calls_orders_endpoint(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_historical_orders()
        assert mock.call_args.kwargs["method"] == "GET"
        assert mock.call_args.kwargs["url"] == f"{BASE_URL}/orders"

    async def test_filters_by_terminal_order_states(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_historical_orders()
        states = mock.call_args.kwargs["params"]["order_states"]
        assert "filled" in states
        assert "cancelled" in states
        assert "rejected" in states
        assert "replaced" in states

    async def test_does_not_include_active_states(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_historical_orders()
        states = mock.call_args.kwargs["params"]["order_states"]
        assert "new" not in states
        assert "pending_new" not in states

    async def test_passes_date_range_params(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_historical_orders(start_date=1700000000000, end_date=1700086400000)
        params = mock.call_args.kwargs["params"]
        assert params["start_date"] == 1700000000000
        assert params["end_date"] == 1700086400000

    async def test_date_params_omitted_when_not_provided(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_historical_orders()
        params = mock.call_args.kwargs["params"]
        assert "start_date" not in params
        assert "end_date" not in params

    async def test_symbols_filter(self, client):
        mock = _mock_http(client, ORDERS_RESPONSE)
        await client.get_historical_orders(symbols=["ETH-EUR"])
        assert mock.call_args.kwargs["params"]["symbols"] == "ETH-EUR"


class TestGetTrades:
    async def test_symbol_is_path_param_not_query_param(self, client):
        mock = _mock_http(client, {"data": [], "metadata": {}})
        await client.get_trades("BTC-EUR")
        assert mock.call_args.kwargs["method"] == "GET"
        assert mock.call_args.kwargs["url"] == f"{BASE_URL}/private/trades/BTC-EUR"
        # symbol must NOT appear as a query param
        assert "symbol" not in (mock.call_args.kwargs.get("params") or {})

    async def test_date_range_passed_as_query_params(self, client):
        mock = _mock_http(client, {"data": [], "metadata": {}})
        await client.get_trades("BTC-EUR", start_date=1700000000000, end_date=1700086400000)
        params = mock.call_args.kwargs["params"]
        assert params["start_date"] == 1700000000000
        assert params["end_date"] == 1700086400000

    async def test_cursor_pagination(self, client):
        mock = _mock_http(client, {"data": [], "metadata": {}})
        await client.get_trades("BTC-EUR", cursor="next-page-token")
        assert mock.call_args.kwargs["params"]["cursor"] == "next-page-token"

    async def test_different_symbols_hit_different_paths(self, client):
        mock = _mock_http(client, {"data": [], "metadata": {}})
        await client.get_trades("ETH-EUR")
        assert mock.call_args.kwargs["url"] == f"{BASE_URL}/private/trades/ETH-EUR"


class TestGetCandles:
    async def test_calls_candles_endpoint(self, client):
        mock = _mock_http(client, CANDLE_RESPONSE)
        await client.get_candles("BTC-EUR")
        assert mock.call_args.kwargs["method"] == "GET"
        assert mock.call_args.kwargs["url"] == f"{BASE_URL}/candles/BTC-EUR"

    async def test_passes_interval_param(self, client):
        mock = _mock_http(client, CANDLE_RESPONSE)
        await client.get_candles("BTC-EUR", interval=15)
        assert mock.call_args.kwargs["params"]["interval"] == 15

    async def test_passes_since_param(self, client):
        mock = _mock_http(client, CANDLE_RESPONSE)
        await client.get_candles("BTC-EUR", since=1700000000000)
        assert mock.call_args.kwargs["params"]["since"] == 1700000000000

    async def test_passes_until_param(self, client):
        mock = _mock_http(client, CANDLE_RESPONSE)
        await client.get_candles("BTC-EUR", until=1700086400000)
        assert mock.call_args.kwargs["params"]["until"] == 1700086400000

    async def test_since_omitted_when_not_provided(self, client):
        mock = _mock_http(client, CANDLE_RESPONSE)
        await client.get_candles("BTC-EUR")
        assert "since" not in mock.call_args.kwargs["params"]

    async def test_until_omitted_when_not_provided(self, client):
        mock = _mock_http(client, CANDLE_RESPONSE)
        await client.get_candles("BTC-EUR")
        assert "until" not in mock.call_args.kwargs["params"]

    async def test_limit_applied_client_side_not_as_query_param(self, client):
        mock = _mock_http(client, CANDLE_RESPONSE)
        result = await client.get_candles("BTC-EUR", limit=1)
        assert len(result) == 1
        assert "limit" not in mock.call_args.kwargs["params"]

    async def test_returns_list_of_candle_dicts(self, client):
        _mock_http(client, CANDLE_RESPONSE)
        result = await client.get_candles("BTC-EUR")
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["open"] == "49000.00"
        assert result[1]["close"] == "51500.00"

    async def test_returns_empty_list_on_error(self, client):
        """get_candles catches all exceptions and returns [] rather than raising."""
        _mock_http_error(client, 500)
        result = await client.get_candles("BTC-EUR")
        assert result == []


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
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}",
            request=MagicMock(),
            response=MagicMock(status_code=status_code),
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
        """400 = auth passed, payload validation failed → key has trading permissions."""
        self._setup(client, self._balance_ok_resp(), order_status=400)
        result = await client.check_permissions()
        assert result["trade"] is True

    async def test_trade_true_when_order_probe_returns_422(self, client):
        """422 = unprocessable entity (past auth layer) → key has trading permissions."""
        self._setup(client, self._balance_ok_resp(), order_status=422)
        result = await client.check_permissions()
        assert result["trade"] is True

    async def test_trade_false_when_order_probe_returns_401(self, client):
        """401 = unauthorized → key does not have trading permissions."""
        self._setup(client, self._balance_ok_resp(), order_status=401)
        result = await client.check_permissions()
        assert result["trade"] is False

    async def test_trade_false_when_order_probe_returns_403(self, client):
        """403 = forbidden → key does not have trading permissions."""
        self._setup(client, self._balance_ok_resp(), order_status=403)
        result = await client.check_permissions()
        assert result["trade"] is False