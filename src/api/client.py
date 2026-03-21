"""Revolut X API Client with Ed25519 authentication.

All 17 endpoints from the official Revolut X REST API v1.0:
  https://developer.revolut.com/docs/x-api/revolut-x-crypto-exchange-rest-api

IMPORTANT: When modifying this file always verify against:
  - Official docs: https://developer.revolut.com/docs/x-api/revolut-x-crypto-exchange-rest-api
  - Internal reference: docs/revolut-x-api-docs.md

Never guess endpoint paths or response shapes.
"""

import base64
import time
import uuid
from typing import Any

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from loguru import logger
from pydantic import ValidationError

import src.utils.onepassword as op
from src.config import REVOLUT_API_BASE_URLS, settings
from src.models.domain import CandleResponse, OrderBookResponse
from src.utils.rate_limiter import RateLimiter


class RevolutAPIError(Exception):
    """Raised when the Revolut X API returns an application-level error.

    Wraps the structured error body ``{"message": ..., "error_id": ..., "timestamp": ...}``
    that every non-2xx response carries.  Callers can inspect ``status_code`` and
    ``message`` without having to parse raw HTTP exceptions.
    """

    def __init__(self, status_code: int, message: str, error_id: str | None = None):
        self.status_code = status_code
        self.message = message
        self.error_id = error_id
        super().__init__(f"[{status_code}] {message}")


class RevolutAPIClient:
    """Revolut X Crypto Exchange REST API Client with Ed25519 authentication.

    Implements all 17 documented endpoints.  Public endpoints (no auth headers
    required) are dispatched via ``_public_request``; all others via ``_request``.
    """

    def __init__(self, max_requests_per_minute: int = 60) -> None:
        self.api_key = op.get("REVOLUT_API_KEY")
        self._base_urls = [url.rstrip("/") for url in REVOLUT_API_BASE_URLS]
        self.base_url = self._base_urls[0]
        self.client = httpx.AsyncClient(timeout=30.0)
        self._private_key: Ed25519PrivateKey | None = None
        self.rate_limiter = RateLimiter(max_requests=max_requests_per_minute, time_window=60.0)
        logger.info(f"Rate limiter configured: {max_requests_per_minute} requests/minute")

    async def __aenter__(self) -> "RevolutAPIClient":
        await self.initialize()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def initialize(self) -> None:
        """Load the Ed25519 private key from 1Password.

        Raises:
            RuntimeError: If 1Password is unavailable or the key is missing.
            ValueError: If the stored key is not Ed25519 format.
        """
        pem_content = op.get("REVOLUT_PRIVATE_KEY")
        try:
            loaded_key = serialization.load_pem_private_key(
                pem_content.encode() if isinstance(pem_content, str) else pem_content,
                password=None,
            )
        except Exception as e:
            raise ValueError(f"Failed to load private key: {e}") from e

        if not isinstance(loaded_key, Ed25519PrivateKey):
            raise ValueError("Private key must be Ed25519 format")

        self._private_key = loaded_key
        logger.info("Revolut API client initialized successfully")

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self.client.aclose()

    # ------------------------------------------------------------------
    # Authentication helpers
    # ------------------------------------------------------------------

    def _generate_signature(
        self, timestamp: str, method: str, path: str, query: str = "", body: str = ""
    ) -> str:
        """Sign ``timestamp+method+path+query+body`` with Ed25519, return Base64."""
        if self._private_key is None:
            raise RuntimeError("Private key not loaded — call _load_private_key() first")
        message = f"{timestamp}{method}{path}{query}{body}"
        signature: bytes = self._private_key.sign(message.encode())
        return base64.b64encode(signature).decode()  # type: ignore[arg-type]

    def _build_headers(
        self, method: str, path: str, query: str = "", body: str = ""
    ) -> dict[str, str]:
        """Return the three mandatory Revolut X authentication headers."""
        timestamp = str(int(time.time() * 1000))
        return {
            "X-Revx-API-Key": self.api_key,
            "X-Revx-Timestamp": timestamp,
            "X-Revx-Signature": self._generate_signature(timestamp, method, path, query, body),
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # HTTP transport
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_api_message(e: httpx.HTTPStatusError) -> str:
        """Pull the human-readable ``message`` out of a Revolut API error body.

        Falls back to the raw exception string if parsing fails.
        """
        try:
            return e.response.json().get("message", str(e))
        except Exception:
            return str(e)

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Make an authenticated request to the Revolut X API.

        The query string is built and URL-encoded *before* signing so that the
        signature covers the exact bytes that will be sent on the wire.  Passing
        the query via ``params=`` to httpx would cause double-encoding and a
        signature mismatch on endpoints whose values contain special characters.
        """
        import json as _json
        from urllib.parse import urlencode

        await self.rate_limiter.acquire()

        path = f"/api/1.0{endpoint}"
        query = urlencode(sorted(params.items())) if params else ""

        body = ""
        if json_data is not None:
            body = _json.dumps(json_data, separators=(",", ":"))

        headers = self._build_headers(method, path, query, body)

        last_connect_error: Exception | None = None
        for base_url in self._base_urls:
            url = f"{base_url}{endpoint}"
            if query:
                url = f"{url}?{query}"
            try:
                response = await self.client.request(
                    method=method, url=url, headers=headers, json=json_data
                )
                response.raise_for_status()
                self.base_url = base_url
                return response.json() if response.content else {}
            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                logger.warning(f"Connection to {base_url} failed: {e}; trying next URL")
                last_connect_error = e
                continue
            except httpx.HTTPStatusError as e:
                msg = self._extract_api_message(e)
                if e.response.status_code >= 500:
                    logger.error(f"HTTP {e.response.status_code}: {msg}")
                else:
                    logger.debug(f"HTTP {e.response.status_code}: {msg}")
                raise RevolutAPIError(e.response.status_code, msg) from e
            except Exception as e:
                logger.error(f"Request failed: {e}")
                raise

        logger.error("All base URLs exhausted")
        raise last_connect_error  # type: ignore[misc]

    async def _public_request(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Make an unauthenticated GET request (public endpoints, no auth headers).

        Public endpoints live under ``/api/1.0/public/...`` and do not require
        ``X-Revx-*`` headers.
        """
        from urllib.parse import urlencode

        query = urlencode(sorted(params.items())) if params else ""

        last_connect_error: Exception | None = None
        for base_url in self._base_urls:
            url = f"{base_url}{endpoint}"
            if query:
                url = f"{url}?{query}"
            try:
                response = await self.client.request(method="GET", url=url)
                response.raise_for_status()
                self.base_url = base_url
                return response.json() if response.content else {}
            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                logger.warning(f"Connection to {base_url} failed: {e}; trying next URL")
                last_connect_error = e
                continue
            except httpx.HTTPStatusError as e:
                msg = self._extract_api_message(e)
                logger.debug(f"HTTP {e.response.status_code}: {msg}")
                raise RevolutAPIError(e.response.status_code, msg) from e
            except Exception as e:
                logger.error(f"Public request failed: {e}")
                raise

        logger.error("All base URLs exhausted")
        raise last_connect_error  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Permissions probe
    # ------------------------------------------------------------------

    async def check_permissions(self) -> dict[str, Any]:
        """Check what this API key can do.

        Returns:
            dict with keys:
              - ``view``       (bool)  key is valid and can read authenticated data
              - ``trade``      (bool)  key has trading-level permissions
              - ``view_error`` (str|None)  reason code when ``view`` is False:
                  ``"deactivated"`` — 401 (key invalid / deactivated)
                  ``"forbidden"``   — 403 (key lacks read permission)
                  ``"unreachable"`` — network / connection error
                  ``"http_<N>"``    — any other HTTP error status
                  ``"unknown"``     — non-HTTP exception

        Never raises; all errors are caught and surfaced via ``view_error``.
        """
        view_ok = False
        trade_ok = False
        view_error: str | None = None

        try:
            balance = await self.get_balance()
            view_ok = "currencies" in balance
        except RevolutAPIError as e:
            if e.status_code == 401:
                view_error = "deactivated"
            elif e.status_code == 403:
                view_error = "forbidden"
            else:
                view_error = f"http_{e.status_code}"
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError):
            view_error = "unreachable"
        except Exception:
            view_error = "unknown"

        # Trade probe — Revolut validates auth/permissions before payload:
        #   400/422 = passed auth, failed validation  → key can trade
        #   401/403 = rejected at auth/perm layer     → key cannot trade
        try:
            await self._request("POST", "/orders", json_data={})
            trade_ok = True
        except RevolutAPIError as e:
            trade_ok = e.status_code not in (401, 403)
        except Exception:  # nosec B110 — network errors leave trade_ok=False (safe default)
            pass

        return {"view": view_ok, "trade": trade_ok, "view_error": view_error}

    # ------------------------------------------------------------------
    # 1. GET /balances
    # ------------------------------------------------------------------

    async def get_balance(self) -> dict[str, Any]:
        """Get all account balances.

        Docs: GET /api/1.0/balances — Auth required.
        API returns a JSON array of balance objects with string amounts.

        Returns:
            ``{"balances": {currency: {...}}, "currencies": [...], "total_<base>": Decimal}``
            All monetary values are ``Decimal`` — never ``float``.
        """
        from decimal import Decimal

        raw = await self._request("GET", "/balances")
        if not isinstance(raw, list):
            raise ValueError(f"Invalid balance response: expected list, got {type(raw).__name__}")

        base_currency = settings.base_currency
        balances: dict[str, dict[str, Decimal]] = {}
        total_base = Decimal("0")

        # Collect non-base currencies that need FX conversion
        fx_needed: dict[str, Decimal] = {}  # currency -> total amount

        for item in raw:
            currency = item.get("currency", "UNKNOWN")
            available = Decimal(item.get("available", "0"))
            reserved = Decimal(item.get("reserved", "0"))
            staked = Decimal(item.get("staked", "0"))
            total = Decimal(item.get("total", "0"))
            balances[currency] = {
                "available": available,
                "reserved": reserved,
                "staked": staked,
                "total": total,
            }
            if currency == base_currency or currency == f"{base_currency}E":
                total_base += total
            elif total > 0:
                fx_needed[currency] = total

        # Resolve FX rates live from the order book
        for currency, amount in fx_needed.items():
            symbol = f"{currency}-{base_currency}"
            try:
                ticker = await self.get_ticker(symbol)
                rate = Decimal(str(ticker.get("last", "0")))
                if rate > 0:
                    total_base += amount * rate
            except Exception:  # nosec B110 — currency has no pair, FX contribution is zero
                pass

        return {
            "balances": balances,
            f"total_{base_currency.lower()}": total_base,
            "base_currency": base_currency,
            "currencies": list(balances.keys()),
        }

    # ------------------------------------------------------------------
    # 2. GET /configuration/currencies
    # ------------------------------------------------------------------

    async def get_currencies(self) -> dict[str, Any]:
        """Get configuration for all currencies on the exchange.

        Docs: GET /api/1.0/configuration/currencies — Auth required.

        Returns:
            Dict keyed by currency symbol, each containing ``symbol``, ``name``,
            ``scale``, ``asset_type``, ``status``.
        """
        raw = await self._request("GET", "/configuration/currencies")
        if not isinstance(raw, dict):
            raise ValueError(
                f"Invalid currencies response: expected dict, got {type(raw).__name__}"
            )
        return raw

    # ------------------------------------------------------------------
    # 3. GET /configuration/pairs
    # ------------------------------------------------------------------

    async def get_currency_pairs(self) -> dict[str, Any]:
        """Get configuration for all traded currency pairs.

        Docs: GET /api/1.0/configuration/pairs — Auth required.
        Rate limit: 1000 req/min.

        Returns:
            Dict keyed by pair (e.g. ``"BTC/USD"``), each containing ``base``,
            ``quote``, ``base_step``, ``quote_step``, ``min_order_size``,
            ``max_order_size``, ``min_order_size_quote``, ``status``.
        """
        raw = await self._request("GET", "/configuration/pairs")
        if not isinstance(raw, dict):
            raise ValueError(f"Invalid pairs response: expected dict, got {type(raw).__name__}")
        return raw

    # ------------------------------------------------------------------
    # 4. GET /public/last-trades  (unauthenticated)
    # ------------------------------------------------------------------

    async def get_last_public_trades(self) -> dict[str, Any]:
        """Get the last 100 trades across all pairs (public, no auth required).

        Docs: GET /api/1.0/public/last-trades — Auth NOT required.
        Rate limit: 20 requests per 10 seconds.

        Returns:
            ``{"data": [...], "metadata": {"timestamp": ...}}``
            Each trade has MiFID II / MiCA compliance fields:
            ``tdt``, ``aid``, ``anm``, ``p``, ``pc``, ``pn``,
            ``q``, ``qc``, ``qn``, ``ve``, ``pdt``, ``vp``, ``tid``.
        """
        raw = await self._public_request("/public/last-trades")
        if not isinstance(raw, dict):
            raise ValueError(
                f"Invalid last-trades response: expected dict, got {type(raw).__name__}"
            )
        return raw

    # ------------------------------------------------------------------
    # 5. GET /public/order-book/{symbol}  (unauthenticated, max 5 levels)
    # ------------------------------------------------------------------

    async def get_public_order_book(self, symbol: str) -> dict[str, Any]:
        """Get the public order book snapshot for a symbol (no auth, max 5 price levels).

        Docs: GET /api/1.0/public/order-book/{symbol} — Auth NOT required.

        Returns:
            ``{"data": {"asks": [...], "bids": [...]}, "metadata": {"timestamp": ...}}``
            Each entry has ``aid``, ``anm``, ``s``, ``p``, ``pc``, ``pn``,
            ``q``, ``qc``, ``qn``, ``ve``, ``no``, ``ts``, ``pdt``.
        """
        raw = await self._public_request(f"/public/order-book/{symbol}")
        if not isinstance(raw, dict):
            raise ValueError(
                f"Invalid public order book response: expected dict, got {type(raw).__name__}"
            )
        return raw

    # ------------------------------------------------------------------
    # 6. POST /orders  — place order
    # ------------------------------------------------------------------

    async def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: str | float,
        price: str | float | None = None,
    ) -> dict[str, Any]:
        """Place a new limit or market order.

        Docs: POST /api/1.0/orders — Auth required. Rate limit: 1000 req/min.

        Args:
            symbol:     Trading pair (e.g. ``"BTC-USD"``).
            side:       ``"buy"`` or ``"sell"`` (case-insensitive).
            order_type: ``"limit"`` or ``"market"`` (case-insensitive).
            quantity:   Base asset quantity. Pass ``str`` (from ``Decimal``) to
                        preserve full precision; ``float`` is also accepted.
            price:      Limit price — required for limit orders. Same precision
                        note as ``quantity``.

        Returns:
            ``{"venue_order_id": str, "client_order_id": str, "state": str}``

        Raises:
            ValueError: Missing price for limit order, unsupported type, or bad response.
        """
        order_type_lower = order_type.lower()

        if order_type_lower == "limit":
            if price is None:
                raise ValueError("price is required for limit orders")
            order_configuration: dict[str, Any] = {
                "limit": {
                    "base_size": str(quantity),
                    "price": str(price),
                    "execution_instructions": ["post_only"],
                }
            }
        elif order_type_lower == "market":
            order_configuration = {"market": {"base_size": str(quantity)}}
        else:
            raise ValueError(f"Unsupported order_type: {order_type!r}. Use 'limit' or 'market'.")

        order_data: dict[str, Any] = {
            "client_order_id": str(uuid.uuid4()),
            "symbol": symbol,
            "side": side.lower(),
            "order_configuration": order_configuration,
        }

        logger.info(f"Creating order: {symbol} {side.lower()} {order_type_lower} qty={quantity}")
        raw = await self._request("POST", "/orders", json_data=order_data)

        # Response: {"data": [{"venue_order_id": "...", "client_order_id": "...", "state": "..."}]}
        if not isinstance(raw, dict) or "data" not in raw:
            raise ValueError(f"Unexpected create_order response: {raw!r}")
        data = raw["data"]
        if not isinstance(data, list) or not data:
            raise ValueError(f"Empty data in create_order response: {raw!r}")

        item = data[0]
        return {
            "venue_order_id": item.get("venue_order_id", ""),
            "client_order_id": item.get("client_order_id", ""),
            "state": item.get("state", ""),
        }

    # ------------------------------------------------------------------
    # 7. DELETE /orders  — cancel all active orders
    # ------------------------------------------------------------------

    async def cancel_all_orders(self) -> None:
        """Cancel all active limit, conditional, and TPSL orders.

        Docs: DELETE /api/1.0/orders — Auth required. Response: 204 No Content.
        """
        logger.info("Cancelling all active orders")
        await self._request("DELETE", "/orders")

    # ------------------------------------------------------------------
    # 8. GET /orders/active
    # ------------------------------------------------------------------

    async def get_open_orders(
        self,
        symbols: list[str] | None = None,
        states: list[str] | None = None,
        types: list[str] | None = None,
        sides: list[str] | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Get all active (open) orders.

        Docs: GET /api/1.0/orders/active — Auth required.

        Args:
            symbols: Filter by trading pairs (e.g. ``["BTC-USD", "ETH-USD"]``).
            states:  Filter by state: ``"pending_new"``, ``"new"``, ``"partially_filled"``.
            types:   Filter by type: ``"limit"``, ``"conditional"``, ``"tpsl"``.
            sides:   Filter by direction: ``"buy"``, ``"sell"``.
            cursor:  Pagination cursor from ``metadata.next_cursor``.
            limit:   Max records 1–100 (default 100).

        Returns:
            ``{"data": [...orders...], "metadata": {"timestamp": ..., "next_cursor": ...}}``
        """
        params: dict[str, Any] = {"limit": limit}
        if symbols:
            params["symbols"] = ",".join(symbols)
        if states:
            params["states"] = ",".join(states)
        if types:
            params["types"] = ",".join(types)
        if sides:
            params["sides"] = ",".join(sides)
        if cursor:
            params["cursor"] = cursor

        raw = await self._request("GET", "/orders/active", params=params)
        if not isinstance(raw, dict):
            raise ValueError(
                f"Invalid active orders response: expected dict, got {type(raw).__name__}"
            )
        return raw

    # ------------------------------------------------------------------
    # 9. GET /orders/historical
    # ------------------------------------------------------------------

    async def get_historical_orders(
        self,
        symbols: list[str] | None = None,
        states: list[str] | None = None,
        types: list[str] | None = None,
        start_date: int | None = None,
        end_date: int | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Get completed (historical) orders.

        Docs: GET /api/1.0/orders/historical — Auth required.
        Date range must be ≤ 30 days.  Server defaults: start = end − 7 days.

        Args:
            symbols:    Filter by trading pairs.
            states:     Filter by state: ``"filled"``, ``"cancelled"``,
                        ``"rejected"``, ``"replaced"``.
            types:      Filter by type: ``"market"``, ``"limit"``.
            start_date: Start timestamp (Unix epoch ms).
            end_date:   End timestamp (Unix epoch ms).
            cursor:     Pagination cursor.
            limit:      Max records 1–100 (default 100).

        Returns:
            ``{"data": [...orders...], "metadata": {"timestamp": ..., "next_cursor": ...}}``
        """
        params: dict[str, Any] = {"limit": limit}
        if symbols:
            params["symbols"] = ",".join(symbols)
        if states:
            params["states"] = ",".join(states)
        if types:
            params["types"] = ",".join(types)
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if cursor:
            params["cursor"] = cursor

        raw = await self._request("GET", "/orders/historical", params=params)
        if not isinstance(raw, dict):
            raise ValueError(
                f"Invalid historical orders response: expected dict, got {type(raw).__name__}"
            )
        return raw

    # ------------------------------------------------------------------
    # 10. GET /orders/{venue_order_id}
    # ------------------------------------------------------------------

    async def get_order(self, venue_order_id: str) -> dict[str, Any]:
        """Get details for a specific order by venue order ID.

        Docs: GET /api/1.0/orders/{venue_order_id} — Auth required.

        Returns:
            The unwrapped order object (``data`` envelope is removed).

        Raises:
            RevolutAPIError: 404 if order not found.
        """
        raw = await self._request("GET", f"/orders/{venue_order_id}")
        if not isinstance(raw, dict):
            raise ValueError(f"Invalid order response: expected dict, got {type(raw).__name__}")
        # Response: {"data": {...order...}}
        return raw.get("data", raw)

    # ------------------------------------------------------------------
    # 11. DELETE /orders/{venue_order_id}
    # ------------------------------------------------------------------

    async def cancel_order(self, venue_order_id: str) -> None:
        """Cancel an active order by venue order ID.

        Docs: DELETE /api/1.0/orders/{venue_order_id} — Auth required.
        Response: 204 No Content.

        Raises:
            RevolutAPIError: 404 if order not found.
        """
        logger.info(f"Cancelling order: {venue_order_id}")
        await self._request("DELETE", f"/orders/{venue_order_id}")

    # ------------------------------------------------------------------
    # 12. GET /orders/fills/{venue_order_id}
    # ------------------------------------------------------------------

    async def get_order_fills(self, venue_order_id: str) -> dict[str, Any]:
        """Get the fills (executions) for a specific order.

        Docs: GET /api/1.0/orders/fills/{venue_order_id} — Auth required.

        Returns:
            ``{"data": [...fill objects...]}``
            Each fill has ``tdt``, ``aid``, ``anm``, ``p``, ``pc``, ``q``,
            ``qc``, ``ve``, ``tid``, ``oid``, ``s`` (side), ``im`` (maker flag).

        Raises:
            RevolutAPIError: 404 if order not found.
        """
        raw = await self._request("GET", f"/orders/fills/{venue_order_id}")
        if not isinstance(raw, dict):
            raise ValueError(f"Invalid fills response: expected dict, got {type(raw).__name__}")
        return raw

    # ------------------------------------------------------------------
    # 13. GET /trades/all/{symbol}
    # ------------------------------------------------------------------

    async def get_public_trades(
        self,
        symbol: str,
        start_date: int | None = None,
        end_date: int | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Get all trades for a symbol (not limited to the current client).

        Docs: GET /api/1.0/trades/all/{symbol} — Auth required.
        Max date range: 30 days.

        Returns:
            ``{"data": [...trades...], "metadata": {"timestamp": ..., "next_cursor": ...}}``
            Each trade has ``tdt``, ``aid``, ``anm``, ``p``, ``pc``, ``q``,
            ``qc``, ``ve``, ``pdt``, ``vp``, ``tid``.
        """
        params: dict[str, Any] = {"limit": limit}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if cursor:
            params["cursor"] = cursor

        raw = await self._request("GET", f"/trades/all/{symbol}", params=params)
        if not isinstance(raw, dict):
            raise ValueError(
                f"Invalid public trades response: expected dict, got {type(raw).__name__}"
            )
        return raw

    # ------------------------------------------------------------------
    # 14. GET /trades/private/{symbol}
    # ------------------------------------------------------------------

    async def get_trades(
        self,
        symbol: str,
        start_date: int | None = None,
        end_date: int | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Get private trade history (fills) for the authenticated client.

        Docs: GET /api/1.0/trades/private/{symbol} — Auth required.
        Max date range: 30 days.

        Returns:
            ``{"data": [...trades...], "metadata": {"timestamp": ..., "next_cursor": ...}}``
            Each trade adds ``oid`` (order ID), ``s`` (side), ``im`` (maker flag)
            on top of the public trade fields.
        """
        params: dict[str, Any] = {"limit": limit}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if cursor:
            params["cursor"] = cursor

        raw = await self._request("GET", f"/trades/private/{symbol}", params=params)
        if not isinstance(raw, dict):
            raise ValueError(
                f"Invalid private trades response: expected dict, got {type(raw).__name__}"
            )
        return raw

    # ------------------------------------------------------------------
    # 15. GET /order-book/{symbol}  (authenticated, up to 20 levels)
    # ------------------------------------------------------------------

    async def get_order_book(self, symbol: str, depth: int = 20) -> dict[str, Any]:
        """Get authenticated order book snapshot (up to 20 price levels).

        Docs: GET /api/1.0/order-book/{symbol} — Auth required.
        Rate limit: 1000 req/min.

        Args:
            symbol: Trading pair (e.g. ``"BTC-USD"``).
            depth:  Price levels 1–20 (default 20).

        Returns:
            ``{"data": {"asks": [...], "bids": [...]}, "metadata": {"ts": ...}}``
        """
        raw = await self._request("GET", f"/order-book/{symbol}", params={"depth": depth})
        if not isinstance(raw, dict):
            raise ValueError(
                f"Invalid order book response: expected dict, got {type(raw).__name__}"
            )
        return raw

    # ------------------------------------------------------------------
    # 16. GET /candles/{symbol}
    # ------------------------------------------------------------------

    async def get_candles(
        self,
        symbol: str,
        interval: int = 60,
        since: int | None = None,
        until: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get historical OHLCV candles for a symbol.

        Docs: GET /api/1.0/candles/{symbol} — Auth required.
        Max candles: (until − since) / interval ≤ 1000.

        Args:
            symbol:   Trading pair (e.g. ``"BTC-USD"``).
            interval: Minutes per candle. Valid: 1, 5, 15, 30, 60, 240, 1440,
                      2880, 5760, 10080, 20160, 40320.  Default: 60.
            since:    Start timestamp (Unix epoch ms).
            until:    End timestamp (Unix epoch ms).
            limit:    Client-side cap on returned candles (default 100).

        Returns:
            List of ``{"start", "open", "high", "low", "close", "volume"}`` dicts.
            Returns ``[]`` on error (non-raising to keep the bot alive).
        """
        params: dict[str, Any] = {"interval": interval}
        if since:
            params["since"] = since
        if until:
            params["until"] = until

        try:
            raw = await self._request("GET", f"/candles/{symbol}", params=params)
            if not isinstance(raw, dict):
                raise ValueError(
                    f"Invalid candles response: expected dict, got {type(raw).__name__}"
                )
            candle_response = CandleResponse(**raw)
            candles = [c.model_dump() for c in candle_response.data]
            return candles[:limit] if limit else candles
        except Exception as e:
            logger.error(f"Failed to fetch candles for {symbol}: {e}")
            return []

    # ------------------------------------------------------------------
    # 17. GET /tickers
    # ------------------------------------------------------------------

    async def get_tickers(self, symbols: list[str] | None = None) -> list[dict[str, Any]]:
        """Get latest market data snapshots for all (or filtered) currency pairs.

        Docs: GET /api/1.0/tickers — Auth required.

        Args:
            symbols: Optional filter (e.g. ``["BTC-USD", "ETH-USD"]``).

        Returns:
            List of ``{"symbol", "bid", "ask", "mid", "last_price"}`` dicts.
        """
        params: dict[str, Any] = {}
        if symbols:
            params["symbols"] = ",".join(symbols)

        raw = await self._request("GET", "/tickers", params=params if params else None)

        # Response is always {"data": [...], "metadata": {...}}
        if isinstance(raw, dict):
            data = raw.get("data")
            if isinstance(data, list):
                return data
            raise ValueError(f"Unexpected /tickers response shape: {list(raw.keys())}")
        # Fallback: bare list (defensive)
        if isinstance(raw, list):
            return raw
        raise ValueError(f"Unexpected /tickers response type: {type(raw).__name__}")

    # ------------------------------------------------------------------
    # Derived helpers (not direct API endpoints)
    # ------------------------------------------------------------------

    async def get_ticker(self, symbol: str) -> dict[str, Any]:
        """Return a normalised ticker for ``symbol`` using the authenticated order book.

        Uses ``GET /order-book/{symbol}`` (endpoint 15) to get best bid/ask.
        The mid-price is used as ``last``.

        Returns:
            ``{"bid": Decimal, "ask": Decimal, "last": Decimal, "volume": Decimal, "symbol": str}``

        Raises:
            ValueError: If the order book is empty or malformed.
        """
        from decimal import Decimal

        raw = await self.get_order_book(symbol)

        try:
            order_book = OrderBookResponse(**raw)
        except (ValidationError, Exception) as e:
            raise ValueError(f"Malformed order book for {symbol}: {e}") from e

        asks = order_book.data.asks
        bids = order_book.data.bids

        if not asks and not bids:
            raise ValueError(f"Empty order book for {symbol}")

        best_bid = bids[0].price if bids else Decimal("0")
        best_ask = asks[0].price if asks else Decimal("0")
        last = (best_bid + best_ask) / 2 if (best_bid and best_ask) else Decimal("0")
        volume = sum((b.quantity for b in bids), Decimal("0")) + sum(
            (a.quantity for a in asks), Decimal("0")
        )

        return {
            "bid": best_bid,
            "ask": best_ask,
            "last": last,
            "volume": volume,
            "symbol": symbol,
        }
