"""Rate limiter for API calls using token bucket algorithm."""

import asyncio
import time
from collections import deque
from collections.abc import Callable, Coroutine


class RateLimiter:
    """Token bucket rate limiter for controlling API request frequency.

    Prevents hitting API rate limits by enforcing maximum requests per time window.
    Accepts optional ``clock`` and ``sleep`` callables for deterministic testing.
    """

    def __init__(
        self,
        max_requests: int,
        time_window: float,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], Coroutine] | None = None,
    ) -> None:
        """Initialize rate limiter.

        Args:
            max_requests: Maximum number of requests allowed in time window.
            time_window: Time window in seconds.
            clock: Wall-clock function (default ``time.time``).
            sleep: Async sleep function (default ``asyncio.sleep``).
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self._clock = clock or time.time
        self._sleep = sleep or asyncio.sleep
        self.requests: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire permission to make a request.

        Blocks if rate limit would be exceeded.  Uses a recheck loop so that
        if the sleep overshoots (OS scheduling jitter) any additional entries
        that became stale during the sleep are cleaned before recording.
        """
        async with self._lock:
            while True:
                now = self._clock()

                # Remove requests outside the time window
                while self.requests and self.requests[0] < now - self.time_window:
                    self.requests.popleft()

                if len(self.requests) < self.max_requests:
                    break

                # At capacity — sleep until the oldest request falls outside
                # the window, then recheck (the sleep may overshoot).
                sleep_time = self.requests[0] + self.time_window - now
                if sleep_time > 0:
                    await self._sleep(sleep_time)

            self.requests.append(self._clock())

    def reset(self) -> None:
        """Reset the rate limiter (clear all recorded requests)."""
        self.requests.clear()

    @property
    def current_usage(self) -> int:
        """Get current number of requests in the time window."""
        now = self._clock()
        # Clean up old requests
        while self.requests and self.requests[0] < now - self.time_window:
            self.requests.popleft()
        return len(self.requests)

    @property
    def available_requests(self) -> int:
        """Get number of requests available without waiting."""
        return max(0, self.max_requests - self.current_usage)
