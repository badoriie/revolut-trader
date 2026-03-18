"""Revolut X API Client with Ed25519 authentication.

This module handles all API communication with Revolut X exchange,
including signature generation and request signing.

IMPORTANT: When modifying this file, ALWAYS consult:
- Official API Docs: https://developer.revolut.com/docs/x-api/revolut-x-crypto-exchange-rest-api
- Internal Reference: .claude/API_REFERENCE.md

Never guess API endpoints or formats - verify against official documentation first.
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
from src.config import REVOLUT_API_BASE_URL, settings
from src.data.models import (
    CandleResponse,
    OrderBookResponse,
    OrderCreationResponse,
)
from src.utils.rate_limiter import RateLimiter


class RevolutAPIClient:
    """Revolut X Crypto Exchange REST API Client with Ed25519 authentication."""

    def __init__(
        self,
        max_requests_per_minute: int = 60,
    ):
        self.api_key = op.get("REVOLUT_API_KEY")
        self.base_url = REVOLUT_API_BASE_URL.rstrip("/")
        self.client = httpx.AsyncClient(timeout=30.0)
        self._private_key: Ed25519PrivateKey | None = None

        self.rate_limiter = RateLimiter(max_requests=max_requests_per_minute, time_window=60.0)
        logger.info(f"Rate limiter configured: {max_requests_per_minute} requests/minute")

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def initialize(self):
        """Initialize the API client by loading the private key from 1Password.

        Raises:
            RuntimeError: If 1Password is unavailable or REVOLUT_PRIVATE_KEY not found
            ValueError: If private key is not Ed25519 format
        """
        pem_content = op.get("REVOLUT_PRIVATE_KEY")
        logger.info("Using private key from 1Password")

        # Load the private key from PEM content
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

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    async def check_permissions(self) -> dict[str, bool]:
        """Check what this API key can do.

        Returns:
            {"view": bool, "trade": bool}
            view  — key is valid and can access authenticated account endpoints
            trade — key has trading-level permissions (can place orders)

        Uses /balances for the view check (truly authenticated endpoint —
        the public order-book endpoint accepts any request regardless of key status).

        Never raises; all errors are caught and reflected as False.
        """
        view_ok = False
        trade_ok = False

        # VIEW: /balances requires a valid, active API key.
        # (The public order-book endpoint ignores auth headers — not a reliable check.)
        try:
            balance = await self.get_balance()
            view_ok = "currencies" in balance
        except Exception:
            pass

        # TRADE: POST /orders with empty body.
        # Revolut validates auth/permissions before the payload:
        #   400/422 = reached validation → key can trade
        #   401/403 = rejected at auth/permission layer → key cannot trade
        try:
            await self._request("POST", "/orders", json_data={})
            trade_ok = True
        except httpx.HTTPStatusError as e:
            trade_ok = e.response.status_code not in (401, 403)
        except Exception:
            pass

        return {"view": view_ok, "trade": trade_ok}

    def _generate_signature(
        self, timestamp: str, method: str, path: str, query: str = "", body: str = ""
    ) -> str:
        """Generate Ed25519 signature for API request."""
        message = f"{timestamp}{method}{path}{query}{body}"
        signature_bytes = self._private_key.sign(message.encode())
        return base64.b64encode(signature_bytes).decode()

    def _build_headers(
        self, method: str, path: str, query: str = "", body: str = ""
    ) -> dict[str, str]:
        """Build request headers with authentication."""
        timestamp = str(int(time.time() * 1000))
        signature = self._generate_signature(timestamp, method, path, query, body)

        return {
            "X-Revx-API-Key": self.api_key,
            "X-Revx-Timestamp": timestamp,
            "X-Revx-Signature": signature,
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Make authenticated request to Revolut API with rate limiting."""
        # Apply rate limiting before making request
        await self.rate_limiter.acquire()

        path = f"/api/1.0{endpoint}"
        url = f"{self.base_url}{endpoint}"

        query = ""
        if params:
            query = "&".join([f"{k}={v}" for k, v in sorted(params.items())])

        body = ""
        if json_data is not None:
            import json

            body = json.dumps(json_data, separators=(",", ":"))

        headers = self._build_headers(method, path, query, body)

        try:
            response = await self.client.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json_data,
            )
            response.raise_for_status()
            return response.json() if response.content else {}

        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500:
                logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
            else:
                logger.debug(f"HTTP error {e.response.status_code}: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Request failed: {str(e)}")
            raise

    async def _public_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make public (unauthenticated) request to Revolut API.

        Public endpoints don't require authentication headers.
        """
        # Public endpoints use just the base domain without /api/1.0
        base_domain = self.base_url.replace("/api/1.0", "")
        url = f"{base_domain}{endpoint}"

        try:
            response = await self.client.request(
                method=method,
                url=url,
                params=params,
            )
            response.raise_for_status()
            return response.json() if response.content else {}

        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500:
                logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
            else:
                logger.debug(f"HTTP error {e.response.status_code}: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Request failed: {str(e)}")
            raise

    async def get_balance(self) -> dict[str, Any]:
        """Get account balances.

        Returns:
            Dictionary with balance information for all currencies

        Raises:
            ValidationError: If API response doesn't match expected format
        """
        raw_response = await self._request("GET", "/balances")

        # Response is an array of balance objects
        # Each balance has: currency, available, reserved, total
        if not isinstance(raw_response, list):
            logger.error(f"Expected array response, got: {type(raw_response)}")
            raise ValueError(
                f"Invalid balance response format: expected array, got {type(raw_response)}"
            )

        # Type narrowing: raw_response is now confirmed to be a list
        balance_list: list[Any] = raw_response

        # Convert array to dictionary with currency as key
        balances = {}
        total_base = 0.0

        # Get base currency from settings (default: EUR)
        base_currency = settings.base_currency

        for balance_obj in balance_list:
            currency = balance_obj.get("currency", "UNKNOWN")
            available = float(balance_obj.get("available", "0"))
            reserved = float(balance_obj.get("reserved", "0"))
            total = float(balance_obj.get("total", "0"))

            balances[currency] = {
                "available": available,
                "reserved": reserved,
                "total": total,
            }

            # Sum up base currency value (approximate for stablecoins)
            # EUR, EURE (Euro stablecoins), or base currency equivalents
            if currency == base_currency or currency == f"{base_currency}E":
                total_base += total
            # Also include USD/USDC/USDT for convenience (will need proper conversion in production)
            elif base_currency == "EUR" and currency in ["USD", "USDC", "USDT"]:
                total_base += total * 0.92  # Approximate EUR conversion (should use real rates)

        return {
            "balances": balances,
            f"total_{base_currency.lower()}": total_base,
            "base_currency": base_currency,
            "currencies": list(balances.keys()),
        }

    async def get_order_book(self, symbol: str, limit: int = 20) -> dict[str, Any]:
        """Get order book snapshot for a symbol.

        Args:
            symbol: Trading pair (e.g., "BTC-USD")
            limit: Depth of order book (1-20, default 20)

        Returns:
            Raw order book dict with "data.bids" and "data.asks" arrays.

        Reference: https://developer.revolut.com/docs/x-api/get-order-book
        """
        response = await self._request(
            "GET", f"/public/order-book/{symbol}", params={"limit": limit}
        )
        if not isinstance(response, dict):
            raise ValueError(f"Expected dict response, got {type(response)}")
        return response

    async def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
    ) -> dict[str, Any]:
        """Create a new order using the Revolut X order format.

        Args:
            symbol: Trading pair (e.g., "BTC-USD")
            side: "buy" or "sell" (case-insensitive)
            order_type: "limit" or "market" (case-insensitive)
            quantity: Base asset quantity
            price: Limit price (required for limit orders)

        Returns:
            Dictionary with order creation response

        Raises:
            ValueError: If price missing for limit order, or API returns unexpected format
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
            order_configuration = {
                "market": {
                    "base_size": str(quantity),
                }
            }
        else:
            raise ValueError(f"Unsupported order_type: {order_type!r}. Use 'limit' or 'market'.")

        order_data: dict[str, Any] = {
            "client_order_id": str(uuid.uuid4()),
            "symbol": symbol,
            "side": side.lower(),
            "order_configuration": order_configuration,
        }

        logger.info(f"Creating order: {symbol} {side.lower()} {order_type_lower} qty={quantity}")
        raw_response = await self._request("POST", "/orders", json_data=order_data)

        if not isinstance(raw_response, dict):
            raise ValueError(f"Expected dict response, got {type(raw_response)}")

        try:
            order_response = OrderCreationResponse(**raw_response)
        except ValidationError as e:
            logger.error(f"Invalid order creation response: {e}")
            raise ValueError(f"Malformed order response from API: {e}") from e

        return {
            "orderId": order_response.data.orderId,
            "status": order_response.data.status,
            "symbol": order_response.data.symbol,
            "side": order_response.data.side,
            "quantity": order_response.data.quantity,
            "price": order_response.data.price,
        }

    async def cancel_order(self, venue_order_id: str) -> dict[str, Any]:
        """Cancel an active order by its venue order ID.

        Args:
            venue_order_id: UUID of the order to cancel

        Returns:
            Empty dict on success (API returns 200 with no body).

        Reference: https://developer.revolut.com/docs/x-api/cancel-order
        """
        logger.info(f"Cancelling order: {venue_order_id}")
        response = await self._request("DELETE", f"/orders/{venue_order_id}")
        if not isinstance(response, dict):
            raise ValueError(f"Expected dict response, got {type(response)}")
        return response

    async def cancel_all_orders(self) -> dict[str, Any]:
        """Cancel all active limit, conditional, and TPSL orders.

        Returns:
            Empty dict on success (API returns 200 with no body).

        Reference: https://developer.revolut.com/docs/x-api/cancel-all-orders
        """
        logger.info("Cancelling all active orders")
        response = await self._request("DELETE", "/orders")
        if not isinstance(response, dict):
            return {}
        return response

    async def get_order(self, venue_order_id: str) -> dict[str, Any]:
        """Get details for a specific order by its venue order ID.

        Args:
            venue_order_id: UUID of the order

        Returns:
            Order dict with id, symbol, side, type, quantity, price, status, etc.

        Reference: https://developer.revolut.com/docs/x-api/get-order
        """
        response = await self._request("GET", f"/orders/{venue_order_id}")
        if not isinstance(response, dict):
            raise ValueError(f"Expected dict response, got {type(response)}")
        return response

    async def get_order_fills(self, venue_order_id: str) -> dict[str, Any]:
        """Get the fills (executions) for a specific order.

        Args:
            venue_order_id: UUID of the order

        Returns:
            Dict with "data" list of fill objects (price, quantity, timestamp, trade ID, etc.).

        Reference: https://developer.revolut.com/docs/x-api/get-order-fills
        """
        response = await self._request("GET", f"/orders/{venue_order_id}/fills")
        if not isinstance(response, dict):
            raise ValueError(f"Expected dict response, got {type(response)}")
        return response

    async def get_tickers(self) -> list[Any]:
        """Get latest market data snapshots for all supported currency pairs.

        Returns:
            List of ticker objects with current market snapshots for each pair.

        Reference: https://developer.revolut.com/docs/x-api/get-tickers
        """
        response = await self._request("GET", "/tickers")
        if not isinstance(response, list):
            raise ValueError(f"Expected list response, got {type(response)}")
        return response

    async def get_open_orders(
        self,
        symbols: list[str] | None = None,
        side: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Get all active (open) orders.

        Args:
            symbols: Filter by trading pairs (e.g., ["BTC-USD"])
            side: Filter by "buy" or "sell"
            cursor: Pagination token from previous response
            limit: Number of results (1-100, default 100)

        Returns:
            Dict with "data" list of active orders and "metadata.next_cursor".

        Reference: https://developer.revolut.com/docs/x-api/get-open-orders
        """
        params: dict[str, Any] = {
            "order_states": "pending_new,new,partially_filled",
            "limit": limit,
        }
        if symbols:
            params["symbols"] = ",".join(symbols)
        if side:
            params["side"] = side
        if cursor:
            params["cursor"] = cursor

        response = await self._request("GET", "/orders", params=params)
        if not isinstance(response, dict):
            raise ValueError(f"Expected dict response, got {type(response)}")
        return response

    async def get_historical_orders(
        self,
        symbols: list[str] | None = None,
        start_date: int | None = None,
        end_date: int | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Get historical (completed) orders.

        Args:
            symbols: Filter by trading pairs (e.g., ["BTC-USD"])
            start_date: Start timestamp in Unix milliseconds (defaults to 7 days before end_date)
            end_date: End timestamp in Unix milliseconds (defaults to now)
            cursor: Pagination token from previous response
            limit: Number of results (1-100, default 100)

        Returns:
            Dict with "data" list of orders and "metadata.next_cursor".

        Reference: https://developer.revolut.com/docs/x-api/get-open-orders
        """
        params: dict[str, Any] = {
            "order_states": "filled,cancelled,rejected,replaced",
            "limit": limit,
        }
        if symbols:
            params["symbols"] = ",".join(symbols)
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if cursor:
            params["cursor"] = cursor

        response = await self._request("GET", "/orders", params=params)
        if not isinstance(response, dict):
            raise ValueError(f"Expected dict response, got {type(response)}")
        return response

    async def get_trades(
        self,
        symbol: str,
        start_date: int | None = None,
        end_date: int | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Get private trade history (fills) for the authenticated client.

        Args:
            symbol: Trading pair (e.g., "BTC-USD") — required path parameter
            start_date: Start timestamp in Unix milliseconds (defaults to 7 days before end_date)
            end_date: End timestamp in Unix milliseconds (defaults to now; max range 30 days)
            cursor: Pagination token from previous response
            limit: Number of results (1-100, default 100)

        Returns:
            Dict with "data" list of trade objects and "metadata.next_cursor".

        Reference: https://developer.revolut.com/docs/x-api/get-trades
        """
        params: dict[str, Any] = {"limit": limit}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if cursor:
            params["cursor"] = cursor

        response = await self._request("GET", f"/private/trades/{symbol}", params=params)
        if not isinstance(response, dict):
            raise ValueError(f"Expected dict response, got {type(response)}")
        return response

    async def get_ticker(self, symbol: str) -> dict[str, Any]:
        """Get current market data from public order book.

        Returns a normalized ticker format with bid, ask, and last price.
        Uses the /public/order-book endpoint (requires authentication despite being "public").

        Raises:
            ValidationError: If API response doesn't match expected format
            ValueError: If order book is empty or malformed
        """
        # Get order book data - requires authentication even though it's a "public" endpoint
        raw_response = await self._request("GET", f"/public/order-book/{symbol}")

        # Ensure response is a dict
        if not isinstance(raw_response, dict):
            raise ValueError(f"Expected dict response, got {type(raw_response)}")

        # Validate response structure with Pydantic
        try:
            order_book = OrderBookResponse(**raw_response)
        except ValidationError as e:
            logger.error(f"Invalid order book response for {symbol}: {e}")
            raise ValueError(f"Malformed order book data from API: {e}") from e

        # Extract validated data
        asks = order_book.data.asks
        bids = order_book.data.bids

        if not asks and not bids:
            raise ValueError(f"Empty order book for {symbol}")

        # Get best bid and ask prices (with validation)
        best_bid = float(bids[0].price) if bids else 0.0
        best_ask = float(asks[0].price) if asks else 0.0

        # Calculate mid price as "last"
        last = (best_bid + best_ask) / 2 if (best_bid and best_ask) else 0.0

        # Calculate 24h volume (sum of quantities from order book - note: this is order book depth, not actual volume)
        volume = sum(float(bid.quantity) for bid in bids) + sum(float(ask.quantity) for ask in asks)

        # Return normalized ticker format compatible with existing code
        return {
            "bid": best_bid,
            "ask": best_ask,
            "last": last,
            "volume": volume,
            "high": last * 1.05,  # Estimated, not available in order book
            "low": last * 0.95,  # Estimated, not available in order book
            "symbol": symbol,
        }

    async def get_candles(
        self,
        symbol: str,
        interval: int = 60,
        since: int | None = None,
        until: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get historical OHLCV candles for a symbol.

        Args:
            symbol: Trading pair (e.g., "BTC-USD")
            interval: Time interval in minutes. Accepted: 1, 5, 15, 30, 60, 240, 1440, 2880, 5760, 10080, 20160, 40320
            since: Start timestamp in Unix milliseconds (defaults to end - interval*100)
            until: End timestamp in Unix milliseconds (defaults to now)
            limit: Maximum number of candles to return, applied client-side (default: 100)

        Returns:
            List of candle dictionaries with: start, open, high, low, close, volume

        Raises:
            ValidationError: If API response doesn't match expected format

        Reference: https://developer.revolut.com/docs/x-api/get-candles
        """
        params: dict[str, Any] = {"interval": interval}
        if since:
            params["since"] = since
        if until:
            params["until"] = until

        # Try the likely endpoint path
        try:
            raw_response = await self._request("GET", f"/candles/{symbol}", params=params)

            # Ensure response is a dict
            if not isinstance(raw_response, dict):
                raise ValueError(f"Expected dict response, got {type(raw_response)}")

            # Validate response with Pydantic
            try:
                candle_response = CandleResponse(**raw_response)
            except ValidationError as e:
                logger.error(f"Invalid candle response for {symbol}: {e}")
                raise ValueError(f"Malformed candle data from API: {e}") from e

            # Convert validated Pydantic models to dict format for backward compatibility
            candles = [candle.model_dump() for candle in candle_response.data]
            return candles[:limit] if limit else candles
        except Exception as e:
            logger.error(f"Failed to fetch candles for {symbol}: {e}")
            return []
