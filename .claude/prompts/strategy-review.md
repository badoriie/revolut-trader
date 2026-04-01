# Strategy Review Prompts

## Basic Review

Review `src/strategies/[FILE].py`: signal generation logic, risk parameter adherence, edge case handling, code quality, BaseStrategy integration. Provide specific recommendations.

## Comprehensive Review

**Signal Logic** — Entry/exit clearly defined? Accounts for volatility? Any logical contradictions?

**Risk Management** — Respects position size limits? Stop losses correct? Handles max position limits?

**Performance** — Bottlenecks? Prone to overtrading? Handles different market conditions?

**Testing** — What tests to add? Untested edge cases? Backtest needed?

## New Strategy Design

Concept, market conditions, entry/exit criteria, risk parameters (position size, SL, TP). Validate concept, suggest signal logic, identify pitfalls, recommend parameters, provide BaseStrategy implementation outline, suggest test cases.

## Strategy Comparison

Compare strategies for: capital, risk tolerance, trading pairs, time commitment, market outlook. Evaluate strengths/weaknesses, expected performance, risk profiles. Recommend with reasoning.

## Backtest Analysis

Review results (return, Sharpe, max drawdown, win rate, avg trade). Check for overfitting, red flags, performance in different conditions, parameter adjustments. Assess readiness for paper trading.

## Multi-Strategy Configuration

Which strategies to enable, consensus threshold, conflicting signal handling, individual weights, expected behavior. Suggest configuration for current market conditions.
