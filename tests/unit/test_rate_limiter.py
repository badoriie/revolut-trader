"""Unit tests for RateLimiter.

Covers token-bucket acquire logic, reset, current_usage, and
available_requests properties.
"""

import asyncio
import time

import pytest

from src.utils.rate_limiter import RateLimiter


class TestRateLimiterBasic:
    """Basic functionality tests."""

    @pytest.mark.asyncio
    async def test_acquire_records_request(self):
        """Single acquire should record one request."""
        limiter = RateLimiter(max_requests=5, time_window=60.0)
        await limiter.acquire()
        assert len(limiter.requests) == 1

    @pytest.mark.asyncio
    async def test_multiple_acquires_within_capacity(self):
        """Multiple acquires below max_requests should all succeed immediately."""
        limiter = RateLimiter(max_requests=5, time_window=60.0)
        for _ in range(3):
            await limiter.acquire()
        assert len(limiter.requests) == 3

    @pytest.mark.asyncio
    async def test_reset_clears_all_requests(self):
        """reset() should remove all recorded requests."""
        limiter = RateLimiter(max_requests=5, time_window=60.0)
        await limiter.acquire()
        await limiter.acquire()
        assert len(limiter.requests) == 2
        limiter.reset()
        assert len(limiter.requests) == 0


class TestRateLimiterUsageProperties:
    """Tests for current_usage and available_requests properties."""

    def test_available_requests_when_empty(self):
        """All slots available when no requests have been recorded."""
        limiter = RateLimiter(max_requests=5, time_window=60.0)
        assert limiter.available_requests == 5

    def test_available_requests_decreases_as_requests_fill(self):
        """available_requests drops as requests are added."""
        limiter = RateLimiter(max_requests=5, time_window=60.0)
        now = time.time()
        for _ in range(3):
            limiter.requests.append(now)
        assert limiter.available_requests == 2

    def test_available_requests_at_full_capacity_is_zero(self):
        """available_requests == 0 when at max capacity."""
        limiter = RateLimiter(max_requests=3, time_window=60.0)
        now = time.time()
        for _ in range(3):
            limiter.requests.append(now)
        assert limiter.available_requests == 0

    @pytest.mark.asyncio
    async def test_current_usage_drops_after_window_expires(self):
        """Expired requests should not count towards current_usage."""
        limiter = RateLimiter(max_requests=10, time_window=0.05)
        await limiter.acquire()
        assert limiter.current_usage == 1
        await asyncio.sleep(0.1)
        assert limiter.current_usage == 0

    def test_available_requests_after_reset(self):
        """After reset, all slots should be available."""
        limiter = RateLimiter(max_requests=5, time_window=60.0)
        now = time.time()
        for _ in range(5):
            limiter.requests.append(now)
        assert limiter.available_requests == 0
        limiter.reset()
        assert limiter.available_requests == 5


class TestRateLimiterWindowExpiry:
    """Tests for automatic cleanup of expired requests."""

    @pytest.mark.asyncio
    async def test_acquire_cleans_up_expired_requests(self):
        """acquire() removes expired entries before checking capacity."""
        limiter = RateLimiter(max_requests=2, time_window=0.05)
        await limiter.acquire()
        await limiter.acquire()
        # Wait for window to expire
        await asyncio.sleep(0.1)
        # Should not block — expired entries must be cleaned first
        await limiter.acquire()
        assert limiter.current_usage == 1

    @pytest.mark.asyncio
    async def test_rate_limit_enforced_when_at_capacity(self):
        """When at capacity, acquire() should wait until a slot opens."""
        limiter = RateLimiter(max_requests=1, time_window=0.05)
        await limiter.acquire()
        # Second acquire should sleep ~0.05 s and then succeed
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start
        # Should have waited at least a little bit (> 10 ms)
        assert elapsed > 0.01

    @pytest.mark.asyncio
    async def test_current_usage_property_cleans_expired(self):
        """current_usage property itself cleans up expired requests."""
        limiter = RateLimiter(max_requests=10, time_window=0.05)
        # Add stale entry directly
        limiter.requests.append(time.time() - 1.0)
        # current_usage should purge it and return 0
        assert limiter.current_usage == 0
        assert len(limiter.requests) == 0
