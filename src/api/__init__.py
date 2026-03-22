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
) -> RevolutAPIClient | MockRevolutAPIClient:
    """Create the appropriate API client for the given environment.

    Args:
        environment: The deployment environment (dev, int, prod).
        max_requests_per_minute: Rate limit (only applies to real client).

    Returns:
        MockRevolutAPIClient for dev, RevolutAPIClient for int/prod.
    """
    if environment == Environment.DEV:
        return MockRevolutAPIClient(max_requests_per_minute=max_requests_per_minute)
    return RevolutAPIClient(max_requests_per_minute=max_requests_per_minute)
