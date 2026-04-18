"""Revolut X API client package.

Provides ``create_api_client()`` factory that returns a ``MockRevolutAPIClient``
for the dev environment and a real ``RevolutAPIClient`` for int/prod.
"""

from src.config import Environment

from .client import RevolutAPIClient
from .mock_client import MockRevolutAPIClient


def create_api_client(
    environment: Environment,
    max_requests_per_minute: int = 60,
    force_real: bool = False,
) -> RevolutAPIClient | MockRevolutAPIClient:
    """Create the appropriate API client for the given environment.

    Args:
        environment: The deployment environment (dev, int, prod).
        max_requests_per_minute: Rate limit (only applies to real client).
        force_real: If True, always return the real client even in dev. Use for
            backtests that need real market data regardless of current branch.

    Returns:
        MockRevolutAPIClient for dev (unless force_real), RevolutAPIClient for int/prod.
    """
    if not force_real and environment == Environment.DEV:
        return MockRevolutAPIClient(max_requests_per_minute=max_requests_per_minute)
    return RevolutAPIClient(max_requests_per_minute=max_requests_per_minute)
