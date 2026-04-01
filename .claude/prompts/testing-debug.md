# Testing & Debugging Prompts

## Write Unit Tests

Target: `src/[PATH]` — cover happy path, edge cases, error conditions, boundary values, invalid inputs. Mock API calls, market data, time, and random values. Use pytest + pytest-asyncio.

## Debug Trading Issue

Describe: problem, frequency, conditions, relevant logs, steps to reproduce, expected vs actual behavior, severity, financial impact. Analyze for: root cause, immediate fix, long-term solution, prevention.

## Debug by Component

- **API issues** — endpoint, sanitized request/response, expected vs actual. Check auth, signing, rate limits.
- **Position management** — positions in bot vs Revolut, discrepancies, recent activity logs. Check sync logic.
- **Risk limits** — config (risk level, position size, daily loss, stop loss), observed vs expected behavior. Check `risk_manager.py`.
- **Signal generation** — strategy, pair, market conditions, expected vs actual signal, parameter values. Check strategy logic.

## Testing Checklists

**Integration Testing** — API client + API, strategy + market data, risk manager + executor, full trading loop. Define mock vs real boundaries and success criteria.

**Error Handling Review** — All exceptions caught appropriately, proper propagation, graceful degradation, error logging with context, recovery procedures. Critical paths: order submission, position updates, API auth, risk checks.

**Race Condition Testing** — Concurrent order execution, position updates, balance calculations, risk limit checks. Identify shared state, create concurrent scenarios, verify synchronization.

**Async Code Review** — Missing await keywords, blocking calls in async functions, asyncio.gather usage, task cancellation handling, event loop management, resource leaks.

## Performance & Reliability

**Profiling** — Strategy signal generation, API call latency, data processing, position calculations, risk checks. Use cProfile, memory_profiler, async task monitoring.

**Memory Leaks** — Market data accumulation, log growth, position tracking, API response caching. Use tracemalloc, objgraph.

**Coverage Analysis** — Run `pytest --cov`, identify uncovered critical areas, prioritize test additions.
