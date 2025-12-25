# Strategy Review Template

Use this template when asking the agent to review a trading strategy.

## Basic Review

```
Review the [STRATEGY_NAME] strategy in src/strategies/[STRATEGY_FILE].py

Focus on:
1. Signal generation logic and accuracy
2. Risk parameter adherence
3. Edge case handling
4. Code quality and best practices
5. Integration with existing system

Provide specific recommendations for improvement.
```

## Comprehensive Review

```
Perform a comprehensive review of the [STRATEGY_NAME] strategy:

**Signal Logic**
- Are entry/exit conditions clearly defined?
- Do signals account for market volatility?
- Are there any logical contradictions?

**Risk Management**
- Does it respect position size limits?
- Are stop losses properly implemented?
- Does it handle maximum position limits?

**Performance Considerations**
- Are there any performance bottlenecks?
- Is the strategy prone to overtrading?
- Does it handle different market conditions?

**Testing**
- What test cases should be added?
- Are there untested edge cases?
- Should we add backtesting?

**Code Quality**
- Is the code readable and maintainable?
- Are there proper docstrings?
- Does it follow the BaseStrategy pattern correctly?

Provide a prioritized list of recommendations.
```

## Parameter Optimization Review

```
Review the parameters for [STRATEGY_NAME] strategy:

Current parameters:
- [List current parameters and values]

Account details:
- Account size: $[AMOUNT]
- Risk level: [conservative/moderate/aggressive]
- Target volatility: [X]%

Questions:
1. Are these parameters appropriate for the account size?
2. Should any parameters be adjusted for current market conditions?
3. What's the expected risk/reward profile?
4. What's the recommended position sizing?

Suggest optimized parameters with reasoning.
```

## New Strategy Design

```
Help me design a new trading strategy:

**Concept**: [Describe the trading idea]

**Market Conditions**: [When should this strategy work best?]

**Entry Criteria**: [What triggers a buy signal?]

**Exit Criteria**: [What triggers a sell signal?]

**Risk Parameters**:
- Account size: $[AMOUNT]
- Risk level: [conservative/moderate/aggressive]
- Max position size: [X]%
- Stop loss: [X]%
- Take profit: [X]%

Please:
1. Validate the strategy concept
2. Suggest signal generation logic
3. Identify potential pitfalls
4. Recommend parameters
5. Provide implementation outline following BaseStrategy pattern
6. Suggest test cases
```

## Strategy Comparison

```
Compare these strategies for my use case:

**Strategies**: [List strategies to compare]

**Account Details**:
- Capital: $[AMOUNT]
- Risk tolerance: [conservative/moderate/aggressive]
- Trading pairs: [BTC-USD, ETH-USD, etc.]
- Time commitment: [How often can you monitor?]

**Market Outlook**: [Bullish/Bearish/Neutral, Volatile/Stable]

Provide:
1. Strengths and weaknesses of each
2. Expected performance in current market
3. Risk profiles comparison
4. Recommendation with reasoning
5. Suggested parameter adjustments for each
```

## Backtest Analysis

```
Help me analyze backtesting results for [STRATEGY_NAME]:

**Results Summary**:
- Total return: [X]%
- Sharpe ratio: [X]
- Max drawdown: [X]%
- Win rate: [X]%
- Average trade: [X]%

**Concerns**:
[List any concerns or unusual patterns]

Questions:
1. Do these results indicate overfitting?
2. Are there any red flags?
3. How would this perform in different market conditions?
4. What parameters should be adjusted?
5. Is this ready for paper trading?
```

## Multi-Strategy Configuration

```
Help me configure the MultiStrategy for optimal performance:

**Available Strategies**:
- Market Making: [enabled/disabled]
- Momentum: [enabled/disabled]
- Mean Reversion: [enabled/disabled]

**Requirements**:
- Consensus threshold: [How many strategies must agree?]
- Conflicting signal handling: [How to resolve?]
- Individual strategy weights: [Equal or weighted?]

**Market Conditions**: [Current market environment]

Suggest:
1. Which strategies to enable
2. Consensus requirements
3. Individual strategy parameters
4. Expected behavior
5. Test cases to validate
```
