import base64
import time
from pathlib import Path
from typing import Any

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from loguru import logger

from src.config import settings


class RevolutAPIClient:
    """Revolut X Crypto Exchange REST API Client with Ed25519 authentication."""

    def __init__(
        self,
        api_key: str | None = None,
        private_key_path: Path | None = None,
        private_key_content: str | None = None,
        base_url: str | None = None,
    ):
        self.api_key = api_key or settings.revolut_api_key
        self.private_key_path = private_key_path
        self.private_key_content = private_key_content
        self.base_url = (base_url or settings.revolut_api_base_url).rstrip("/")
        self.client = httpx.AsyncClient(timeout=30.0)
        self._private_key: Ed25519PrivateKey | None = None

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def initialize(self):
        """Initialize the API client by loading the private key.

        Priority:
        1. Use private_key_content if provided directly
        2. Use private_key_path if provided and exists
        3. Try to get from 1Password via settings
        4. Fall back to file path from settings

        Raises:
            FileNotFoundError: If private key cannot be found
            ValueError: If private key is not Ed25519 format
        """
        pem_content = None

        # Priority 1: Use content if provided directly
        if self.private_key_content:
            pem_content = self.private_key_content
            logger.debug("Using private key content provided directly")

        # Priority 2: Use file path if provided and exists
        elif self.private_key_path and self.private_key_path.exists():
            pem_content = self.private_key_path.read_text()
            logger.debug(f"Using private key from path: {self.private_key_path}")

        # Priority 3 & 4: Try 1Password first, then fall back to file from settings
        else:
            pem_content = settings.get_private_key_content()
            if pem_content:
                logger.info("Using private key from 1Password (secure storage)")
            else:
                raise FileNotFoundError(
                    "Private key not found. Please either:\n"
                    "1. Store it in 1Password using field 'REVOLUT_PRIVATE_KEY', or\n"
                    f"2. Place it at {settings.revolut_private_key_path}"
                )

        # Load the private key from PEM content
        try:
            self._private_key = serialization.load_pem_private_key(
                pem_content.encode() if isinstance(pem_content, str) else pem_content,
                password=None,
            )
        except Exception as e:
            raise ValueError(f"Failed to load private key: {e}")

        if not isinstance(self._private_key, Ed25519PrivateKey):
            raise ValueError("Private key must be Ed25519 format")

        logger.info("Revolut API client initialized successfully")

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

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
    ) -> dict[str, Any]:
        """Make authenticated request to Revolut API."""
        path = f"/api/1.0{endpoint}"
        url = f"{self.base_url}{path}"

        query = ""
        if params:
            query = "&".join([f"{k}={v}" for k, v in sorted(params.items())])

        body = ""
        if json_data:
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
            logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Request failed: {str(e)}")
            raise

    async def get_balance(self) -> dict[str, Any]:
        """Get account balance."""
        return await self._request("GET", "/balance")

    async def get_market_data(self, symbol: str) -> dict[str, Any]:
        """Get market data for a symbol."""
        return await self._request("GET", f"/market-data/{symbol}")

    async def get_order_book(self, symbol: str, depth: int = 10) -> dict[str, Any]:
        """Get order book for a symbol."""
        return await self._request("GET", f"/orderbook/{symbol}", params={"depth": depth})

    async def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
        time_in_force: str = "GTC",
    ) -> dict[str, Any]:
        """Create a new order."""
        order_data = {
            "symbol": symbol,
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": str(quantity),
            "timeInForce": time_in_force,
        }

        if price is not None:
            order_data["price"] = str(price)

        logger.info(f"Creating order: {order_data}")
        return await self._request("POST", "/orders", json_data=order_data)

    async def cancel_order(self, order_id: str) -> dict[str, Any]:
        """Cancel an existing order."""
        logger.info(f"Cancelling order: {order_id}")
        return await self._request("DELETE", f"/orders/{order_id}")

    async def get_order(self, order_id: str) -> dict[str, Any]:
        """Get order details."""
        return await self._request("GET", f"/orders/{order_id}")

    async def get_open_orders(self, symbol: str | None = None) -> dict[str, Any]:
        """Get all open orders."""
        params = {"symbol": symbol} if symbol else {}
        return await self._request("GET", "/orders", params=params)

    async def get_trades(self, symbol: str | None = None, limit: int = 100) -> dict[str, Any]:
        """Get recent trades."""
        params = {"limit": limit}
        if symbol:
            params["symbol"] = symbol
        return await self._request("GET", "/trades", params=params)

    async def get_ticker(self, symbol: str) -> dict[str, Any]:
        """Get 24hr ticker price change statistics."""
        return await self._request("GET", f"/ticker/{symbol}")
