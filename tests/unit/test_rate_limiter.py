"""Unit tests for RateLimiter.

Tests use injected clock and sleep callables to stay deterministic —
no real time.sleep or asyncio.sleep calls are made.
"""

import asyncio

import pytest

from src.utils.rate_limiter import RateLimiter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_clock(start: float = 0.0):
    """Return a mutable clock whose current time can be advanced."""
    state = {"now": start}

    def clock() -> float:
        return state["now"]

    def advance(seconds: float) -> None:
        state["now"] += seconds

    return clock, advance


async def noop_sleep(_seconds: float) -> None:
    """Sleep stub that returns immediately without yielding control."""


class AdvancingClock:
    """Sleep stub that advances the shared clock by the requested duration.

    Advances by ``seconds + 1e-9`` to mirror real OS sleep behaviour: actual
    sleep always overshoots slightly.  The rate limiter's expiry check uses
    ``<=`` so an exact-boundary advance would work too, but the epsilon keeps
    the model realistic and provides a small safety margin.
    """

    _EPSILON = 1e-9

    def __init__(self, advance_fn):
        self.advance = advance_fn
        self.calls: list[float] = []

    async def sleep(self, seconds: float) -> None:
        self.calls.append(seconds)
        self.advance(seconds + self._EPSILON)


# ---------------------------------------------------------------------------
# Basic allow / deny behaviour
# ---------------------------------------------------------------------------


class TestAcquireAllowsRequests:
    async def test_single_request_is_allowed(self):
        clock, _ = make_clock()
        rl = RateLimiter(max_requests=3, time_window=1.0, clock=clock, sleep=noop_sleep)
        await rl.acquire()  # must not raise or hang
        assert rl.current_usage == 1

    async def test_requests_up_to_max_are_all_allowed(self):
        clock, _ = make_clock()
        rl = RateLimiter(max_requests=3, time_window=1.0, clock=clock, sleep=noop_sleep)
        for _ in range(3):
            await rl.acquire()
        assert rl.current_usage == 3

    async def test_acquire_records_each_request(self):
        clock, _ = make_clock()
        rl = RateLimiter(max_requests=5, time_window=10.0, clock=clock, sleep=noop_sleep)
        for expected in range(1, 6):
            await rl.acquire()
            assert rl.current_usage == expected


# ---------------------------------------------------------------------------
# Sliding-window expiry
# ---------------------------------------------------------------------------


class TestWindowExpiry:
    async def test_requests_expire_after_time_window(self):
        clock, advance = make_clock()
        rl = RateLimiter(max_requests=2, time_window=1.0, clock=clock, sleep=noop_sleep)

        await rl.acquire()
        await rl.acquire()
        assert rl.current_usage == 2

        advance(1.1)  # both requests now outside the window
        assert rl.current_usage == 0

    async def test_new_requests_allowed_after_window_expires(self):
        clock, advance = make_clock()
        advancing = AdvancingClock(advance)
        rl = RateLimiter(max_requests=2, time_window=1.0, clock=clock, sleep=advancing.sleep)

        await rl.acquire()
        await rl.acquire()

        # Advance past the window so the next acquire doesn't need to wait
        advance(1.1)
        await rl.acquire()  # must not sleep

        assert len(advancing.calls) == 0

    async def test_exact_boundary_expires_entry(self):
        """An entry at exactly now - time_window must be treated as expired.

        Previously the expiry check used strict ``<``, so advancing by exactly
        ``time_window`` left the entry alive; combined with sleep_time collapsing
        to 0 (skipped by the guard), this caused an infinite spin.
        """
        clock, advance = make_clock(start=0.0)
        rl = RateLimiter(max_requests=1, time_window=1.0, clock=clock, sleep=noop_sleep)
        await rl.acquire()  # t=0
        advance(1.0)  # exactly at the boundary — must expire the t=0 entry
        assert rl.current_usage == 0

    async def test_partial_expiry_counts_correctly(self):
        clock, advance = make_clock(start=0.0)
        rl = RateLimiter(max_requests=3, time_window=1.0, clock=clock, sleep=noop_sleep)

        await rl.acquire()  # t=0.0
        advance(0.5)
        await rl.acquire()  # t=0.5
        advance(0.6)  # now t=1.1 — first request (t=0) is expired
        assert rl.current_usage == 1  # only the t=0.5 request remains


# ---------------------------------------------------------------------------
# Blocking / sleeping behaviour
# ---------------------------------------------------------------------------


class TestBlocking:
    async def test_acquire_sleeps_when_at_capacity(self):
        clock, advance = make_clock()
        advancing = AdvancingClock(advance)
        rl = RateLimiter(max_requests=2, time_window=1.0, clock=clock, sleep=advancing.sleep)

        await rl.acquire()  # t=0
        await rl.acquire()  # t=0  — now full

        # Next acquire must sleep until the oldest entry (t=0) expires
        await rl.acquire()
        assert len(advancing.calls) == 1
        assert advancing.calls[0] == pytest.approx(1.0)

    async def test_sleep_duration_is_time_until_oldest_expires(self):
        clock, advance = make_clock(start=0.0)
        advancing = AdvancingClock(advance)
        rl = RateLimiter(max_requests=1, time_window=2.0, clock=clock, sleep=advancing.sleep)

        await rl.acquire()  # t=0 — fills the single slot
        advance(0.5)  # t=0.5 — 1.5 s remaining in the window

        await rl.acquire()  # must sleep 1.5 s
        assert advancing.calls[0] == pytest.approx(1.5)

    async def test_exact_boundary_does_not_hang(self):
        """Calling acquire() when the clock sits exactly at the boundary must
        not hang.  With a strict ``<`` expiry, sleep_time was 0 and the guard
        blocked the await, causing an infinite synchronous spin.
        """
        clock, advance = make_clock(start=0.0)
        rl = RateLimiter(max_requests=1, time_window=1.0, clock=clock, sleep=noop_sleep)
        await rl.acquire()  # t=0 — fills the single slot
        advance(1.0)  # now = exactly time_window; entry must be expired by <=
        await rl.acquire()  # must not hang
        assert rl.current_usage == 1

    async def test_no_sleep_when_capacity_becomes_available(self):
        # max_requests=1 forces expiry to matter: without the advance the
        # second acquire would be blocked; with it the slot is free.
        clock, advance = make_clock()
        advancing = AdvancingClock(advance)
        rl = RateLimiter(max_requests=1, time_window=1.0, clock=clock, sleep=advancing.sleep)

        await rl.acquire()
        advance(1.1)  # the single slot has now expired
        await rl.acquire()  # must not sleep

        assert len(advancing.calls) == 0


# ---------------------------------------------------------------------------
# available_requests property
# ---------------------------------------------------------------------------


class TestAvailableRequests:
    async def test_all_slots_free_at_start(self):
        clock, _ = make_clock()
        rl = RateLimiter(max_requests=5, time_window=1.0, clock=clock, sleep=noop_sleep)
        assert rl.available_requests == 5

    async def test_decrements_as_requests_are_made(self):
        clock, _ = make_clock()
        rl = RateLimiter(max_requests=3, time_window=1.0, clock=clock, sleep=noop_sleep)
        await rl.acquire()
        assert rl.available_requests == 2
        await rl.acquire()
        assert rl.available_requests == 1

    async def test_zero_when_at_capacity(self):
        clock, _ = make_clock()
        rl = RateLimiter(max_requests=2, time_window=1.0, clock=clock, sleep=noop_sleep)
        await rl.acquire()
        await rl.acquire()
        assert rl.available_requests == 0

    async def test_recovers_after_window_expires(self):
        clock, advance = make_clock()
        rl = RateLimiter(max_requests=2, time_window=1.0, clock=clock, sleep=noop_sleep)
        await rl.acquire()
        await rl.acquire()
        advance(1.1)
        assert rl.available_requests == 2


# ---------------------------------------------------------------------------
# reset()
# ---------------------------------------------------------------------------


class TestReset:
    async def test_reset_clears_all_recorded_requests(self):
        clock, _ = make_clock()
        rl = RateLimiter(max_requests=3, time_window=1.0, clock=clock, sleep=noop_sleep)
        await rl.acquire()
        await rl.acquire()
        rl.reset()
        assert rl.current_usage == 0
        assert rl.available_requests == 3

    async def test_acquire_works_normally_after_reset(self):
        clock, _ = make_clock()
        rl = RateLimiter(max_requests=2, time_window=1.0, clock=clock, sleep=noop_sleep)
        await rl.acquire()
        await rl.acquire()
        rl.reset()
        await rl.acquire()  # must not sleep — capacity was restored
        assert rl.current_usage == 1


# ---------------------------------------------------------------------------
# Concurrent access
# ---------------------------------------------------------------------------


class TestConcurrency:
    async def test_concurrent_acquires_do_not_exceed_limit(self):
        """Fire N coroutines simultaneously; none should bypass the limit.

        The asyncio.Lock serialises all callers, so execution is deterministic:
        coroutines 1-3 go through immediately; coroutine 4 sleeps once (all
        three t=0 entries expire); coroutine 5 finds one entry and proceeds
        without sleeping.  Exactly one sleep call is expected.
        """
        clock, advance = make_clock()
        advancing = AdvancingClock(advance)
        rl = RateLimiter(max_requests=3, time_window=1.0, clock=clock, sleep=advancing.sleep)

        await asyncio.gather(*(rl.acquire() for _ in range(5)))

        assert len(advancing.calls) == 1
        assert advancing.calls[0] == pytest.approx(1.0)

    async def test_lock_serialises_concurrent_callers(self):
        """Concurrent acquires must never record more than max_requests entries
        in the same instant — the lock must prevent interleaving in the
        check-then-record window.

        With max_requests=1, each waiter blocks on the previous waiter's newly
        recorded entry, so both must sleep.  Trace:
          setup:  requests=[t=0]  (at capacity)
          coro A: sleeps 1.0 s → clock=1.0+ε, entry expires, records t=1.0+ε
          coro B: entry t=1.0+ε is now the sole occupant → sleeps 1.0 s →
                  clock=2.0+2ε, entry expires, records t=2.0+2ε
        Result: exactly two sleep calls, each of 1.0 s.
        """
        clock, advance = make_clock()
        advancing = AdvancingClock(advance)
        rl = RateLimiter(max_requests=1, time_window=1.0, clock=clock, sleep=advancing.sleep)

        await rl.acquire()  # fill the single slot at t=0

        # Both waiters must each sleep; neither can bypass the other.
        await asyncio.gather(rl.acquire(), rl.acquire())

        assert len(advancing.calls) == 2
        assert advancing.calls[0] == pytest.approx(1.0)
        assert advancing.calls[1] == pytest.approx(1.0)
