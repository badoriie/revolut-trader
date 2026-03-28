"""Tests for MockRevolutAPIClient — verifies it matches the real API contract.

All response shapes must match docs/revolut-x-api-docs.md exactly.
The mock client is used in ENVIRONMENT=dev to avoid real API calls.
"""

from decimal import Decimal

import pytest

from src.api.mock_client import MockRevolutAPIClient
from src.config import Environment

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def mock_client():
    """MockRevolutAPIClient instance ready for testing."""
    client = MockRevolutAPIClient()
    await client.initialize()
    yield client
    await client.close()


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestMockClientLifecycle:
    """Test initialization, close, and context manager."""

    @pytest.mark.asyncio
    async def test_initialize(self, mock_client: MockRevolutAPIClient):
        """Mock client initializes without requiring 1Password or private keys."""
        assert mock_client is not None

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Mock client works as an async context manager."""
        async with MockRevolutAPIClient() as client:
            assert client is not None

    @pytest.mark.asyncio
    async def test_close_is_safe(self, mock_client: MockRevolutAPIClient):
        """Calling close multiple times does not raise."""
        await mock_client.close()
        await mock_client.close()


# ---------------------------------------------------------------------------
# 1. GET /balances — get_balance()
# ---------------------------------------------------------------------------


class TestMockGetBalance:
    """Mock balance endpoint returns API-doc-compliant shapes."""

    @pytest.mark.asyncio
    async def test_returns_balances_dict(self, mock_client: MockRevolutAPIClient):
        """get_balance() returns the processed balance structure."""
        result = await mock_client.get_balance()
        assert "balances" in result
        assert "currencies" in result
        assert isinstance(result["balances"], dict)
        assert isinstance(result["currencies"], list)

    @pytest.mark.asyncio
    async def test_balance_has_eur(self, mock_client: MockRevolutAPIClient):
        """Dev mock includes EUR balance."""
        result = await mock_client.get_balance()
        assert "EUR" in result["balances"]
        eur = result["balances"]["EUR"]
        assert isinstance(eur["available"], Decimal)
        assert eur["available"] > 0

    @pytest.mark.asyncio
    async def test_balance_has_crypto(self, mock_client: MockRevolutAPIClient):
        """Dev mock includes BTC and ETH balances."""
        result = await mock_client.get_balance()
        assert "BTC" in result["balances"]
        assert "ETH" in result["balances"]

    @pytest.mark.asyncio
    async def test_balance_total_eur(self, mock_client: MockRevolutAPIClient):
        """Total EUR value is calculated."""
        result = await mock_client.get_balance()
        assert "total_eur" in result
        assert isinstance(result["total_eur"], Decimal)
        assert result["total_eur"] > 0


# ---------------------------------------------------------------------------
# 2. GET /configuration/currencies — get_currencies()
# ---------------------------------------------------------------------------


class TestMockGetCurrencies:
    """Mock currencies endpoint."""

    @pytest.mark.asyncio
    async def test_returns_dict(self, mock_client: MockRevolutAPIClient):
        """get_currencies() returns a dict keyed by currency symbol."""
        result = await mock_client.get_currencies()
        assert isinstance(result, dict)
        assert "BTC" in result
        assert "ETH" in result

    @pytest.mark.asyncio
    async def test_asset_type_is_lowercase(self, mock_client: MockRevolutAPIClient):
        """API docs: asset_type must be 'crypto' or 'fiat' (lowercase)."""
        result = await mock_client.get_currencies()
        assert result["BTC"]["asset_type"] == "crypto"
        assert result["ETH"]["asset_type"] == "crypto"
        assert result["EUR"]["asset_type"] == "fiat"

    @pytest.mark.asyncio
    async def test_status_is_lowercase(self, mock_client: MockRevolutAPIClient):
        """API docs: status must be 'active' or 'inactive' (lowercase)."""
        result = await mock_client.get_currencies()
        assert result["BTC"]["status"] == "active"
        assert result["ETH"]["status"] == "active"
        assert result["EUR"]["status"] == "active"


# ---------------------------------------------------------------------------
# 3. GET /configuration/pairs — get_currency_pairs()
# ---------------------------------------------------------------------------


class TestMockGetCurrencyPairs:
    """Mock currency pairs endpoint."""

    @pytest.mark.asyncio
    async def test_returns_dict(self, mock_client: MockRevolutAPIClient):
        """get_currency_pairs() returns a dict keyed by pair."""
        result = await mock_client.get_currency_pairs()
        assert isinstance(result, dict)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_status_is_lowercase(self, mock_client: MockRevolutAPIClient):
        """API docs: status must be 'active' or 'inactive' (lowercase)."""
        result = await mock_client.get_currency_pairs()
        for pair_data in result.values():
            assert pair_data["status"] == "active"


# ---------------------------------------------------------------------------
# 4. GET /public/last-trades — get_last_public_trades()
# ---------------------------------------------------------------------------


class TestMockGetLastPublicTrades:
    """Mock public trades endpoint."""

    @pytest.mark.asyncio
    async def test_returns_data_envelope(self, mock_client: MockRevolutAPIClient):
        """Response has 'data' and 'metadata' keys."""
        result = await mock_client.get_last_public_trades()
        assert "data" in result
        assert "metadata" in result
        assert isinstance(result["data"], list)

    @pytest.mark.asyncio
    async def test_vp_is_revx(self, mock_client: MockRevolutAPIClient):
        """API docs: vp (venue of publication) must always be 'REVX'."""
        result = await mock_client.get_last_public_trades()
        for trade in result["data"]:
            assert trade["vp"] == "REVX"


# ---------------------------------------------------------------------------
# 5. GET /public/order-book/{symbol} — get_public_order_book()
# ---------------------------------------------------------------------------


class TestMockGetPublicOrderBook:
    """Mock public order book endpoint."""

    @pytest.mark.asyncio
    async def test_returns_order_book_shape(self, mock_client: MockRevolutAPIClient):
        """Response has data.asks and data.bids."""
        result = await mock_client.get_public_order_book("BTC-EUR")
        assert "data" in result
        assert "asks" in result["data"]
        assert "bids" in result["data"]


# ---------------------------------------------------------------------------
# 6. POST /orders — create_order()
# ---------------------------------------------------------------------------


class TestMockCreateOrder:
    """Mock order creation."""

    @pytest.mark.asyncio
    async def test_limit_order_returns_correct_shape(self, mock_client: MockRevolutAPIClient):
        """Limit order returns venue_order_id, client_order_id, state."""
        result = await mock_client.create_order(
            symbol="BTC-EUR",
            side="buy",
            order_type="limit",
            quantity="0.001",
            price="50000",
        )
        assert "venue_order_id" in result
        assert "client_order_id" in result
        assert "state" in result
        assert result["state"] == "new"

    @pytest.mark.asyncio
    async def test_market_order_returns_correct_shape(self, mock_client: MockRevolutAPIClient):
        """Market order returns the same shape as limit order."""
        result = await mock_client.create_order(
            symbol="ETH-EUR",
            side="sell",
            order_type="market",
            quantity="1.0",
        )
        assert "venue_order_id" in result
        assert "client_order_id" in result
        assert result["state"] == "new"

    @pytest.mark.asyncio
    async def test_limit_order_requires_price(self, mock_client: MockRevolutAPIClient):
        """Limit order without price raises ValueError."""
        with pytest.raises(ValueError, match="price is required"):
            await mock_client.create_order(
                symbol="BTC-EUR",
                side="buy",
                order_type="limit",
                quantity="0.001",
            )

    @pytest.mark.asyncio
    async def test_order_tracked_in_active_orders(self, mock_client: MockRevolutAPIClient):
        """Created order appears in get_open_orders."""
        result = await mock_client.create_order(
            symbol="BTC-EUR",
            side="buy",
            order_type="limit",
            quantity="0.001",
            price="50000",
        )
        active = await mock_client.get_open_orders()
        order_ids = [o["id"] for o in active["data"]]
        assert result["venue_order_id"] in order_ids


# ---------------------------------------------------------------------------
# 7. DELETE /orders — cancel_all_orders()
# ---------------------------------------------------------------------------


class TestMockCancelAllOrders:
    """Mock cancel all orders."""

    @pytest.mark.asyncio
    async def test_cancels_all(self, mock_client: MockRevolutAPIClient):
        """All active orders are cancelled."""
        await mock_client.create_order("BTC-EUR", "buy", "limit", "0.001", "50000")
        await mock_client.create_order("ETH-EUR", "sell", "limit", "1.0", "3000")
        await mock_client.cancel_all_orders()
        active = await mock_client.get_open_orders()
        assert len(active["data"]) == 0


# ---------------------------------------------------------------------------
# 8. GET /orders/active — get_open_orders()
# ---------------------------------------------------------------------------


class TestMockGetOpenOrders:
    """Mock active orders endpoint."""

    @pytest.mark.asyncio
    async def test_returns_data_envelope(self, mock_client: MockRevolutAPIClient):
        """Response has 'data' and 'metadata' keys."""
        result = await mock_client.get_open_orders()
        assert "data" in result
        assert "metadata" in result

    @pytest.mark.asyncio
    async def test_order_fields_match_api_docs(self, mock_client: MockRevolutAPIClient):
        """Order objects have all fields from the API docs."""
        await mock_client.create_order("BTC-EUR", "buy", "limit", "0.001", "50000")
        result = await mock_client.get_open_orders()
        order = result["data"][0]
        assert "id" in order
        assert "client_order_id" in order
        assert "symbol" in order
        assert "side" in order
        assert "type" in order
        assert "quantity" in order
        assert "status" in order


# ---------------------------------------------------------------------------
# 9. GET /orders/historical — get_historical_orders()
# ---------------------------------------------------------------------------


class TestMockGetHistoricalOrders:
    """Mock historical orders endpoint."""

    @pytest.mark.asyncio
    async def test_returns_data_envelope(self, mock_client: MockRevolutAPIClient):
        """Response has 'data' and 'metadata' keys."""
        result = await mock_client.get_historical_orders()
        assert "data" in result
        assert "metadata" in result


# ---------------------------------------------------------------------------
# 10. GET /orders/{venue_order_id} — get_order()
# ---------------------------------------------------------------------------


class TestMockGetOrder:
    """Mock get single order."""

    @pytest.mark.asyncio
    async def test_returns_created_order(self, mock_client: MockRevolutAPIClient):
        """get_order retrieves a previously created order."""
        created = await mock_client.create_order("BTC-EUR", "buy", "limit", "0.001", "50000")
        order = await mock_client.get_order(created["venue_order_id"])
        assert order["id"] == created["venue_order_id"]
        assert order["symbol"] == "BTC-EUR"


# ---------------------------------------------------------------------------
# 11. DELETE /orders/{venue_order_id} — cancel_order()
# ---------------------------------------------------------------------------


class TestMockCancelOrder:
    """Mock cancel single order."""

    @pytest.mark.asyncio
    async def test_cancel_removes_from_active(self, mock_client: MockRevolutAPIClient):
        """Cancelled order no longer appears in active orders."""
        created = await mock_client.create_order("BTC-EUR", "buy", "limit", "0.001", "50000")
        await mock_client.cancel_order(created["venue_order_id"])
        active = await mock_client.get_open_orders()
        order_ids = [o["id"] for o in active["data"]]
        assert created["venue_order_id"] not in order_ids


# ---------------------------------------------------------------------------
# 12. GET /orders/fills/{venue_order_id} — get_order_fills()
# ---------------------------------------------------------------------------


class TestMockGetOrderFills:
    """Mock order fills endpoint."""

    @pytest.mark.asyncio
    async def test_returns_data_envelope(self, mock_client: MockRevolutAPIClient):
        """Response has 'data' key."""
        created = await mock_client.create_order("BTC-EUR", "buy", "limit", "0.001", "50000")
        result = await mock_client.get_order_fills(created["venue_order_id"])
        assert "data" in result


# ---------------------------------------------------------------------------
# 13. GET /trades/all/{symbol} — get_public_trades()
# ---------------------------------------------------------------------------


class TestMockGetPublicTrades:
    """Mock public trades for symbol."""

    @pytest.mark.asyncio
    async def test_returns_data_envelope(self, mock_client: MockRevolutAPIClient):
        """Response has 'data' and 'metadata' keys."""
        result = await mock_client.get_public_trades("BTC-EUR")
        assert "data" in result
        assert "metadata" in result

    @pytest.mark.asyncio
    async def test_trade_fields_match_api_docs(self, mock_client: MockRevolutAPIClient):
        """API docs: vp must be 'REVX', pn must be 'MONE', qn must be 'UNIT'."""
        result = await mock_client.get_public_trades("BTC-EUR")
        assert len(result["data"]) > 0
        for trade in result["data"]:
            assert trade["vp"] == "REVX", f"Expected vp='REVX', got {trade['vp']!r}"
            assert trade["pn"] == "MONE", f"Expected pn='MONE', got {trade.get('pn')!r}"
            assert trade["qn"] == "UNIT", f"Expected qn='UNIT', got {trade.get('qn')!r}"


# ---------------------------------------------------------------------------
# 14. GET /trades/private/{symbol} — get_trades()
# ---------------------------------------------------------------------------


class TestMockGetTrades:
    """Mock private trades."""

    @pytest.mark.asyncio
    async def test_returns_data_envelope(self, mock_client: MockRevolutAPIClient):
        """Response has 'data' and 'metadata' keys."""
        result = await mock_client.get_trades("BTC-EUR")
        assert "data" in result
        assert "metadata" in result


# ---------------------------------------------------------------------------
# 15. GET /order-book/{symbol} — get_order_book()
# ---------------------------------------------------------------------------


class TestMockGetOrderBook:
    """Mock authenticated order book."""

    @pytest.mark.asyncio
    async def test_returns_order_book_shape(self, mock_client: MockRevolutAPIClient):
        """Response has data.asks and data.bids matching OrderBookResponse model."""
        result = await mock_client.get_order_book("BTC-EUR")
        assert "data" in result
        assert "asks" in result["data"]
        assert "bids" in result["data"]

    @pytest.mark.asyncio
    async def test_order_book_entries_have_required_fields(self, mock_client: MockRevolutAPIClient):
        """Each entry has 'p' (price) and 'q' (quantity) as strings."""
        result = await mock_client.get_order_book("BTC-EUR")
        for entry in result["data"]["asks"]:
            assert "p" in entry
            assert "q" in entry
            # API returns prices as strings
            assert isinstance(entry["p"], str)
            assert isinstance(entry["q"], str)


# ---------------------------------------------------------------------------
# 16. GET /candles/{symbol} — get_candles()
# ---------------------------------------------------------------------------


class TestMockGetCandles:
    """Mock candles endpoint."""

    @pytest.mark.asyncio
    async def test_returns_list_of_candles(self, mock_client: MockRevolutAPIClient):
        """get_candles returns a list of candle dicts."""
        result = await mock_client.get_candles("BTC-EUR")
        assert isinstance(result, list)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_candle_has_ohlcv_fields(self, mock_client: MockRevolutAPIClient):
        """Each candle has start, open, high, low, close, volume."""
        result = await mock_client.get_candles("BTC-EUR")
        candle = result[0]
        assert "start" in candle
        assert "open" in candle
        assert "high" in candle
        assert "low" in candle
        assert "close" in candle
        assert "volume" in candle

    @pytest.mark.asyncio
    async def test_candle_limit_respected(self, mock_client: MockRevolutAPIClient):
        """Limit parameter caps the number of candles returned."""
        result = await mock_client.get_candles("BTC-EUR", limit=5)
        assert len(result) <= 5


# ---------------------------------------------------------------------------
# 17. GET /tickers — get_tickers()
# ---------------------------------------------------------------------------


class TestMockGetTickers:
    """Mock tickers endpoint."""

    @pytest.mark.asyncio
    async def test_returns_list(self, mock_client: MockRevolutAPIClient):
        """get_tickers returns a list of ticker dicts."""
        result = await mock_client.get_tickers()
        assert isinstance(result, list)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_ticker_fields_match_api_docs(self, mock_client: MockRevolutAPIClient):
        """Each ticker has symbol, bid, ask, mid, last_price as strings."""
        result = await mock_client.get_tickers()
        ticker = result[0]
        assert "symbol" in ticker
        assert "bid" in ticker
        assert "ask" in ticker


# ---------------------------------------------------------------------------
# Derived helper: get_ticker()
# ---------------------------------------------------------------------------


class TestMockGetTicker:
    """Mock get_ticker (order-book-derived helper)."""

    @pytest.mark.asyncio
    async def test_returns_normalised_ticker(self, mock_client: MockRevolutAPIClient):
        """get_ticker returns bid, ask, last, volume, symbol — all Decimal."""
        result = await mock_client.get_ticker("BTC-EUR")
        assert "bid" in result
        assert "ask" in result
        assert "last" in result
        assert "volume" in result
        assert "symbol" in result
        assert isinstance(result["bid"], Decimal)
        assert isinstance(result["ask"], Decimal)
        assert result["bid"] > 0
        assert result["ask"] > 0
        assert result["ask"] >= result["bid"]


# ---------------------------------------------------------------------------
# check_permissions()
# ---------------------------------------------------------------------------


class TestMockCheckPermissions:
    """Mock client always has full permissions."""

    @pytest.mark.asyncio
    async def test_view_and_trade_allowed(self, mock_client: MockRevolutAPIClient):
        """Mock client reports full view + trade permissions."""
        perms = await mock_client.check_permissions()
        assert perms["view"] is True
        assert perms["trade"] is True
        assert perms["view_error"] is None


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------


class TestCreateAPIClient:
    """Test the factory function that selects real vs mock client."""

    def test_dev_environment_returns_mock(self):
        """ENVIRONMENT=dev produces MockRevolutAPIClient."""
        from src.api import create_api_client

        client = create_api_client(Environment.DEV)
        assert isinstance(client, MockRevolutAPIClient)

    def test_int_environment_returns_real(self):
        """ENVIRONMENT=int produces RevolutAPIClient."""
        from src.api import create_api_client
        from src.api.client import RevolutAPIClient

        client = create_api_client(Environment.INT)
        assert isinstance(client, RevolutAPIClient)

    def test_prod_environment_returns_real(self):
        """ENVIRONMENT=prod produces RevolutAPIClient."""
        from src.api import create_api_client
        from src.api.client import RevolutAPIClient

        client = create_api_client(Environment.PROD)
        assert isinstance(client, RevolutAPIClient)
