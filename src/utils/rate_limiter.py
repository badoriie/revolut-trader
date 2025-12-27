"""Rate limiter for API calls using token bucket algorithm."""

import asyncio
import time
from collections import deque


class RateLimiter:
    """Token bucket rate limiter for controlling API request frequency.

    Prevents hitting API rate limits by enforcing maximum requests per time window.
    """

    def __init__(self, max_requests: int, time_window: float):
        """Initialize rate limiter.

        Args:
            max_requests: Maximum number of requests allowed in time window
            time_window: Time window in seconds
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire permission to make a request.

        Blocks if rate limit would be exceeded.
        """
        async with self._lock:
            now = time.time()

            # Remove requests outside the time window
            while self.requests and self.requests[0] < now - self.time_window:
                self.requests.popleft()

            # If at capacity, wait until oldest request expires
            if len(self.requests) >= self.max_requests:
                sleep_time = self.time_window - (now - self.requests[0])
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                    # Remove the expired request
                    self.requests.popleft()

            # Record this request
            self.requests.append(time.time())

    def reset(self) -> None:
        """Reset the rate limiter (clear all recorded requests)."""
        self.requests.clear()

    @property
    def current_usage(self) -> int:
        """Get current number of requests in the time window."""
        now = time.time()
        # Clean up old requests
        while self.requests and self.requests[0] < now - self.time_window:
            self.requests.popleft()
        return len(self.requests)

    @property
    def available_requests(self) -> int:
        """Get number of requests available without waiting."""
        return max(0, self.max_requests - self.current_usage)
