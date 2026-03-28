"""Test that MockRevolutAPIClient returns deterministic results for a fixed time."""

import asyncio
from decimal import Decimal
from unittest.mock import patch

from src.api.mock_client import MockRevolutAPIClient


def test_mock_api_returns_constant_prices_for_fixed_time():
    client = MockRevolutAPIClient()
    symbol = "BTC-EUR"
    fixed_time = 1234567890.0
    with patch("time.time", return_value=fixed_time):
        # Call get_ticker multiple times
        results = [asyncio.run(client.get_ticker(symbol)) for _ in range(5)]
    # All results should be identical
    first = results[0]
    for r in results[1:]:
        assert r == first, f"Mock API returned different results for the same time: {r} vs {first}"
    # Check that bid < ask and values are Decimal
    assert isinstance(first["bid"], Decimal)
    assert isinstance(first["ask"], Decimal)
    assert first["bid"] < first["ask"]
