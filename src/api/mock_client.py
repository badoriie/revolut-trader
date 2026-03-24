"""Mock Revolut X API Client for dev environment.

Returns realistic fake data matching the exact response shapes from
docs/revolut-x-api-docs.md.  No network calls, no 1Password, no Ed25519 keys.

Used when ENVIRONMENT=dev so developers can run the bot without real API credentials.
"""

import time
import uuid
from decimal import Decimal
from typing import Any

from loguru import logger

# ---------------------------------------------------------------------------
# Static mock prices (realistic EUR values)
# ---------------------------------------------------------------------------

_MOCK_PRICES: dict[str, dict[str, Decimal]] = {
    "BTC-EUR": {
        "bid": Decimal("49950.00"),
        "ask": Decimal("50050.00"),
    },
    "ETH-EUR": {
        "bid": Decimal("2995.00"),
        "ask": Decimal("3005.00"),
    },
    "SOL-EUR": {
        "bid": Decimal("145.50"),
        "ask": Decimal("146.50"),
    },
    "XRP-EUR": {
        "bid": Decimal("0.5490"),
        "ask": Decimal("0.5510"),
    },
}

_DEFAULT_PRICE = {"bid": Decimal("100.00"), "ask": Decimal("101.00")}


def _now_ms() -> int:
    """Current time as Unix epoch milliseconds."""
    return int(time.time() * 1000)


def _price_for(symbol: str) -> dict[str, Decimal]:
    """Return bid/ask for a symbol, falling back to a default."""
    return _MOCK_PRICES.get(symbol, _DEFAULT_PRICE)


class MockRevolutAPIClient:
    """In-process mock of RevolutAPIClient for ENVIRONMENT=dev.

    Implements the same public async interface so it can be used as a
    drop-in replacement.  Maintains in-memory order state for realistic
    order lifecycle testing.
    """

    def __init__(self, max_requests_per_minute: int = 60) -> None:
        # In-memory state
        self._active_orders: dict[str, dict[str, Any]] = {}
        self._historical_orders: list[dict[str, Any]] = []
        self._fills: dict[str, list[dict[str, Any]]] = {}
        logger.info("MockRevolutAPIClient created (dev mode — no real API calls)")

    async def __aenter__(self) -> "MockRevolutAPIClient":
        await self.initialize()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def initialize(self) -> None:  # NOSONAR(python:S7503) - async for interface compat
        """No-op: mock client needs no private key."""
        logger.info("MockRevolutAPIClient initialized (no credentials required)")

    async def close(self) -> None:  # NOSONAR(python:S7503) - async for interface compat
        """No-op: nothing to close."""

    # ------------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------------

    async def check_permissions(self) -> dict[str, Any]:  # NOSONAR(python:S7503)
        """Mock always returns full permissions.

        Returns:
            dict with view=True, trade=True, view_error=None.
        """
        return {"view": True, "trade": True, "view_error": None}

    # ------------------------------------------------------------------
    # 1. GET /balances
    # ------------------------------------------------------------------

    async def get_balance(self) -> dict[str, Any]:  # NOSONAR(python:S7503)
        """Return mock balances matching the processed shape from RevolutAPIClient.

        Returns:
            ``{"balances": {currency: {available, reserved, staked, total}},
              "total_eur": Decimal, "base_currency": "EUR", "currencies": [...]}``
        """
        balances: dict[str, dict[str, Decimal]] = {
            "EUR": {
                "available": Decimal("10000.00"),
                "reserved": Decimal("0.00"),
                "staked": Decimal("0.00"),
                "total": Decimal("10000.00"),
            },
            "BTC": {
                "available": Decimal("0.50000000"),
                "reserved": Decimal("0.00000000"),
                "staked": Decimal("0.00000000"),
                "total": Decimal("0.50000000"),
            },
            "ETH": {
                "available": Decimal("5.00000000"),
                "reserved": Decimal("0.00000000"),
                "staked": Decimal("0.00000000"),
                "total": Decimal("5.00000000"),
            },
        }

        # Calculate total EUR value
        total_eur = balances["EUR"]["total"]
        btc_price = _MOCK_PRICES["BTC-EUR"]["ask"]
        eth_price = _MOCK_PRICES["ETH-EUR"]["ask"]
        total_eur += balances["BTC"]["total"] * btc_price
        total_eur += balances["ETH"]["total"] * eth_price

        return {
            "balances": balances,
            "total_eur": total_eur,
            "base_currency": "EUR",
            "currencies": list(balances.keys()),
        }

    # ------------------------------------------------------------------
    # 2. GET /configuration/currencies
    # ------------------------------------------------------------------

    async def get_currencies(self) -> dict[str, Any]:  # NOSONAR(python:S7503)
        """Return mock currency configuration.

        Returns:
            Dict keyed by currency symbol with name, scale, asset_type, status.
        """
        return {
            "BTC": {
                "symbol": "BTC",
                "name": "Bitcoin",
                "scale": 8,
                "asset_type": "CRYPTO",
                "status": "ACTIVE",
            },
            "ETH": {
                "symbol": "ETH",
                "name": "Ethereum",
                "scale": 8,
                "asset_type": "CRYPTO",
                "status": "ACTIVE",
            },
            "EUR": {
                "symbol": "EUR",
                "name": "Euro",
                "scale": 2,
                "asset_type": "FIAT",
                "status": "ACTIVE",
            },
        }

    # ------------------------------------------------------------------
    # 3. GET /configuration/pairs
    # ------------------------------------------------------------------

    async def get_currency_pairs(self) -> dict[str, Any]:  # NOSONAR(python:S7503)
        """Return mock currency pair configuration.

        Returns:
            Dict keyed by pair (e.g. "BTC/EUR") with trading parameters.
        """
        return {
            "BTC/EUR": {
                "base": "BTC",
                "quote": "EUR",
                "base_step": "0.00000001",
                "quote_step": "0.01",
                "min_order_size": "0.00001",
                "max_order_size": "100",
                "min_order_size_quote": "1",
                "status": "ACTIVE",
            },
            "ETH/EUR": {
                "base": "ETH",
                "quote": "EUR",
                "base_step": "0.00000001",
                "quote_step": "0.01",
                "min_order_size": "0.0001",
                "max_order_size": "1000",
                "min_order_size_quote": "1",
                "status": "ACTIVE",
            },
        }

    # ------------------------------------------------------------------
    # 4. GET /public/last-trades
    # ------------------------------------------------------------------

    async def get_last_public_trades(self) -> dict[str, Any]:  # NOSONAR(python:S7503)
        """Return mock last public trades.

        Returns:
            ``{"data": [...trades...], "metadata": {"timestamp": ...}}``
        """
        ts = _now_ms()
        return {
            "data": [
                {
                    "tdt": ts - 1000,
                    "aid": "BTC",
                    "anm": "Bitcoin",
                    "p": "50000",
                    "pc": "EUR",
                    "pn": "MONE",
                    "q": "0.01",
                    "qc": "BTC",
                    "qn": "UNIT",
                    "ve": "REVX",
                    "pdt": ts - 1000,
                    "vp": "50000",
                    "tid": str(uuid.uuid4()),
                },
            ],
            "metadata": {"timestamp": ts},
        }

    # ------------------------------------------------------------------
    # 5. GET /public/order-book/{symbol}
    # ------------------------------------------------------------------

    async def get_public_order_book(self, symbol: str) -> dict[str, Any]:  # NOSONAR(python:S7503)
        """Return mock public order book (max 5 levels).

        Args:
            symbol: Trading pair (e.g. "BTC-EUR").

        Returns:
            ``{"data": {"asks": [...], "bids": [...]}, "metadata": {"timestamp": ...}}``
        """
        prices = _price_for(symbol)
        ts = _now_ms()
        return {
            "data": {
                "asks": [
                    self._make_order_book_entry(symbol, "SELL", prices["ask"], "1.5", ts),
                ],
                "bids": [
                    self._make_order_book_entry(symbol, "BUY", prices["bid"], "2.0", ts),
                ],
            },
            "metadata": {"timestamp": ts},
        }

    # ------------------------------------------------------------------
    # 6. POST /orders
    # ------------------------------------------------------------------

    async def create_order(  # NOSONAR(python:S7503)
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: str | float,
        price: str | float | None = None,
    ) -> dict[str, Any]:
        """Place a mock order.

        Args:
            symbol:     Trading pair (e.g. "BTC-EUR").
            side:       "buy" or "sell".
            order_type: "limit" or "market".
            quantity:   Base asset quantity.
            price:      Limit price — required for limit orders.

        Returns:
            ``{"venue_order_id": str, "client_order_id": str, "state": "new"}``

        Raises:
            ValueError: Missing price for limit order or unsupported order type.
        """
        order_type_lower = order_type.lower()

        if order_type_lower == "limit" and price is None:
            raise ValueError("price is required for limit orders")
        if order_type_lower not in ("limit", "market"):
            raise ValueError(f"Unsupported order_type: {order_type!r}. Use 'limit' or 'market'.")

        venue_order_id = str(uuid.uuid4())
        client_order_id = str(uuid.uuid4())
        ts = _now_ms()

        # Store in active orders
        order_record: dict[str, Any] = {
            "id": venue_order_id,
            "client_order_id": client_order_id,
            "symbol": symbol,
            "side": side.lower(),
            "type": order_type_lower,
            "quantity": str(quantity),
            "filled_quantity": "0",
            "leaves_quantity": str(quantity),
            "price": str(price) if price is not None else None,
            "status": "new",
            "time_in_force": "gtc",
            "execution_instructions": ["post_only"] if order_type_lower == "limit" else [],
            "created_date": ts,
            "updated_date": ts,
        }
        self._active_orders[venue_order_id] = order_record
        self._fills[venue_order_id] = []

        logger.info(
            f"[MOCK] Order created: {symbol} {side.lower()} {order_type_lower} "
            f"qty={quantity} id={venue_order_id[:8]}..."
        )

        return {
            "venue_order_id": venue_order_id,
            "client_order_id": client_order_id,
            "state": "new",
        }

    # ------------------------------------------------------------------
    # 7. DELETE /orders
    # ------------------------------------------------------------------

    async def cancel_all_orders(self) -> None:  # NOSONAR(python:S7503)
        """Cancel all active mock orders."""
        cancelled = list(self._active_orders.keys())
        for oid in cancelled:
            order = self._active_orders.pop(oid)
            order["status"] = "cancelled"
            self._historical_orders.append(order)
        logger.info(f"[MOCK] Cancelled {len(cancelled)} orders")

    # ------------------------------------------------------------------
    # 8. GET /orders/active
    # ------------------------------------------------------------------

    async def get_open_orders(  # NOSONAR(python:S7503)
        self,
        symbols: list[str] | None = None,
        states: list[str] | None = None,
        types: list[str] | None = None,
        sides: list[str] | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Return mock active orders.

        Args:
            symbols: Filter by trading pairs.
            states:  Filter by state.
            types:   Filter by type.
            sides:   Filter by direction.
            cursor:  Pagination cursor (ignored in mock).
            limit:   Max records (default 100).

        Returns:
            ``{"data": [...orders...], "metadata": {"timestamp": ..., "next_cursor": ...}}``
        """
        orders = list(self._active_orders.values())

        if symbols:
            orders = [o for o in orders if o["symbol"] in symbols]
        if states:
            orders = [o for o in orders if o["status"] in states]
        if types:
            orders = [o for o in orders if o["type"] in types]
        if sides:
            orders = [o for o in orders if o["side"] in sides]

        return {
            "data": orders[:limit],
            "metadata": {"timestamp": _now_ms(), "next_cursor": None},
        }

    # ------------------------------------------------------------------
    # 9. GET /orders/historical
    # ------------------------------------------------------------------

    async def get_historical_orders(  # NOSONAR(python:S7503)
        self,
        symbols: list[str] | None = None,
        states: list[str] | None = None,
        types: list[str] | None = None,
        start_date: int | None = None,
        end_date: int | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Return mock historical orders.

        Returns:
            ``{"data": [...orders...], "metadata": {"timestamp": ..., "next_cursor": ...}}``
        """
        _ = (symbols, states, types, start_date, end_date, cursor)  # Mock ignores filters
        return {
            "data": self._historical_orders[:limit],
            "metadata": {"timestamp": _now_ms(), "next_cursor": None},
        }

    # ------------------------------------------------------------------
    # 10. GET /orders/{venue_order_id}
    # ------------------------------------------------------------------

    async def get_order(self, venue_order_id: str) -> dict[str, Any]:  # NOSONAR(python:S7503)
        """Get details for a specific mock order.

        Args:
            venue_order_id: The order ID.

        Returns:
            The order object (unwrapped from data envelope).

        Raises:
            ValueError: If order not found.
        """
        if venue_order_id in self._active_orders:
            return self._active_orders[venue_order_id]

        for order in self._historical_orders:
            if order["id"] == venue_order_id:
                return order

        raise ValueError(f"Order not found: {venue_order_id}")

    # ------------------------------------------------------------------
    # 11. DELETE /orders/{venue_order_id}
    # ------------------------------------------------------------------

    async def cancel_order(self, venue_order_id: str) -> None:  # NOSONAR(python:S7503)
        """Cancel a specific mock order.

        Args:
            venue_order_id: The order ID to cancel.

        Raises:
            ValueError: If order not found.
        """
        if venue_order_id not in self._active_orders:
            raise ValueError(f"Order not found: {venue_order_id}")

        order = self._active_orders.pop(venue_order_id)
        order["status"] = "cancelled"
        self._historical_orders.append(order)
        logger.info(f"[MOCK] Cancelled order {venue_order_id[:8]}...")

    # ------------------------------------------------------------------
    # 12. GET /orders/fills/{venue_order_id}
    # ------------------------------------------------------------------

    async def get_order_fills(self, venue_order_id: str) -> dict[str, Any]:  # NOSONAR(python:S7503)
        """Return mock fills for an order.

        Args:
            venue_order_id: The order ID.

        Returns:
            ``{"data": [...fill objects...]}``
        """
        fills = self._fills.get(venue_order_id, [])
        return {"data": fills}

    # ------------------------------------------------------------------
    # 13. GET /trades/all/{symbol}
    # ------------------------------------------------------------------

    async def get_public_trades(  # NOSONAR(python:S7503)
        self,
        symbol: str,
        start_date: int | None = None,
        end_date: int | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Return mock public trades for a symbol.

        Returns:
            ``{"data": [...trades...], "metadata": {"timestamp": ..., "next_cursor": ...}}``
        """
        _ = (start_date, end_date, cursor, limit)  # Mock ignores pagination/date filters
        prices = _price_for(symbol)
        mid = (prices["bid"] + prices["ask"]) / 2
        ts = _now_ms()
        return {
            "data": [
                {
                    "tdt": ts - 5000,
                    "aid": symbol.split("-")[0],
                    "anm": symbol.split("-")[0],
                    "p": str(mid),
                    "pc": symbol.split("-")[1],
                    "q": "0.1",
                    "qc": symbol.split("-")[0],
                    "ve": "REVX",
                    "pdt": ts - 5000,
                    "vp": str(mid),
                    "tid": str(uuid.uuid4()),
                },
            ],
            "metadata": {"timestamp": ts, "next_cursor": None},
        }

    # ------------------------------------------------------------------
    # 14. GET /trades/private/{symbol}
    # ------------------------------------------------------------------

    async def get_trades(  # NOSONAR(python:S7503)
        self,
        symbol: str,
        start_date: int | None = None,
        end_date: int | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Return mock private trades.

        Returns:
            ``{"data": [...trades...], "metadata": {"timestamp": ..., "next_cursor": ...}}``
        """
        _ = (symbol, start_date, end_date, cursor, limit)  # Mock returns empty list
        return {
            "data": [],
            "metadata": {"timestamp": _now_ms(), "next_cursor": None},
        }

    # ------------------------------------------------------------------
    # 15. GET /order-book/{symbol}
    # ------------------------------------------------------------------

    async def get_order_book(
        self, symbol: str, depth: int = 20
    ) -> dict[str, Any]:  # NOSONAR(python:S7503)
        """Return mock authenticated order book (up to 20 levels).

        Args:
            symbol: Trading pair (e.g. "BTC-EUR").
            depth:  Price levels 1–20 (default 20).

        Returns:
            ``{"data": {"asks": [...], "bids": [...]}, "metadata": {"ts": ...}}``
        """
        prices = _price_for(symbol)
        ts = _now_ms()
        bid = prices["bid"]
        ask = prices["ask"]

        # Generate depth levels with realistic spread
        asks = []
        bids = []
        for i in range(min(depth, 5)):
            spread_offset = Decimal(str(i)) * Decimal("10")
            asks.append(
                self._make_order_book_entry(
                    symbol,
                    "SELL",
                    ask + spread_offset,
                    str(Decimal("1.5") - Decimal("0.2") * i),
                    ts,
                )
            )
            bids.append(
                self._make_order_book_entry(
                    symbol, "BUY", bid - spread_offset, str(Decimal("2.0") - Decimal("0.3") * i), ts
                )
            )

        return {
            "data": {"asks": asks, "bids": bids},
            "metadata": {"ts": ts},
        }

    # ------------------------------------------------------------------
    # 16. GET /candles/{symbol}
    # ------------------------------------------------------------------

    async def get_candles(  # NOSONAR(python:S7503)
        self,
        symbol: str,
        interval: int = 60,
        since: int | None = None,
        until: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return mock OHLCV candles.

        Args:
            symbol:   Trading pair.
            interval: Minutes per candle (default 60).
            since:    Start timestamp (Unix epoch ms).
            until:    End timestamp (Unix epoch ms).
            limit:    Max candles returned (default 100).

        Returns:
            List of ``{"start", "open", "high", "low", "close", "volume"}`` dicts.
        """
        _ = (since, until)  # Mock ignores date range
        prices = _price_for(symbol)
        base_price = (prices["bid"] + prices["ask"]) / 2
        ts = _now_ms()
        interval_ms = interval * 60 * 1000

        candles = []
        for i in range(min(limit, 20)):
            offset = Decimal(str(i * 10))
            candle_start = ts - (20 - i) * interval_ms
            candles.append(
                {
                    "start": candle_start,
                    "open": str(base_price - offset),
                    "high": str(base_price + Decimal("50") - offset),
                    "low": str(base_price - Decimal("50") - offset),
                    "close": str(base_price + Decimal("10") - offset),
                    "volume": str(Decimal("0.5") + Decimal("0.01") * i),
                }
            )

        return candles

    # ------------------------------------------------------------------
    # 17. GET /tickers
    # ------------------------------------------------------------------

    async def get_tickers(
        self, symbols: list[str] | None = None
    ) -> list[dict[str, Any]]:  # NOSONAR(python:S7503)
        """Return mock tickers.

        Args:
            symbols: Optional filter by trading pairs.

        Returns:
            List of ``{"symbol", "bid", "ask", "mid", "last_price"}`` dicts.
        """
        tickers = []
        for sym, prices in _MOCK_PRICES.items():
            if symbols and sym not in symbols:
                continue
            mid = (prices["bid"] + prices["ask"]) / 2
            tickers.append(
                {
                    "symbol": sym.replace("-", "/"),
                    "bid": str(prices["bid"]),
                    "ask": str(prices["ask"]),
                    "mid": str(mid),
                    "last_price": str(mid),
                }
            )
        return tickers

    # ------------------------------------------------------------------
    # Derived helper: get_ticker()
    # ------------------------------------------------------------------

    async def get_ticker(self, symbol: str) -> dict[str, Any]:  # NOSONAR(python:S7503)
        """Return a normalised ticker for a symbol using mock order book data.

        Same contract as RevolutAPIClient.get_ticker().

        Args:
            symbol: Trading pair (e.g. "BTC-EUR").

        Returns:
            ``{"bid": Decimal, "ask": Decimal, "last": Decimal,
              "volume": Decimal, "symbol": str}``
        """
        prices = _price_for(symbol)
        bid = prices["bid"]
        ask = prices["ask"]
        last = (bid + ask) / 2
        return {
            "bid": bid,
            "ask": ask,
            "last": last,
            "volume": Decimal("100.0"),
            "symbol": symbol,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_order_book_entry(
        symbol: str, side: str, price: Decimal, quantity: str, ts: int
    ) -> dict[str, Any]:
        """Create a single order book entry matching the API docs shape.

        Args:
            symbol:   Trading pair (e.g. "BTC-EUR").
            side:     "SELL" or "BUY".
            price:    Price level.
            quantity: Quantity at this level.
            ts:       Timestamp (Unix epoch ms).

        Returns:
            Dict with fields: aid, anm, s, p, pc, pn, q, qc, qn, ve, no, ts, pdt.
        """
        parts = symbol.split("-")
        base = parts[0] if len(parts) > 0 else "BTC"
        quote = parts[1] if len(parts) > 1 else "EUR"
        return {
            "aid": base,
            "anm": base,
            "s": side,
            "p": str(price),
            "pc": quote,
            "pn": "MONE",
            "q": quantity,
            "qc": base,
            "qn": "UNIT",
            "ve": "REVX",
            "no": "1",
            "ts": "CLOB",
            "pdt": ts,
        }
