# Quick Start Guide - Trading Bot Claude Code Agent

Get started with the specialized trading bot agent in minutes.

## Installation

The agent is already configured in the `.claude/` directory. Claude Code will automatically detect and use it when working in this project.

## Basic Usage

Simply start Claude Code in your project directory and ask for help:

```bash
cd /path/to/revolut-trader
claude
```

## Common Commands

### For Beginners

**1. First Time Setup**

```
"Help me set up the trading bot for the first time. I want to start with paper trading."
```

**2. Configuration Help**

```
"Explain the configuration options in .env and help me choose appropriate settings for my account size of $[AMOUNT]."
```

**3. Run in Paper Mode**

```
"Help me start the bot in paper trading mode and explain what I should monitor."
```

### For Strategy Development

**4. Understand Existing Strategies**

```
"Explain how the momentum strategy works and when I should use it."
```

**5. Modify a Strategy**

```
"Help me adjust the mean reversion strategy to be more conservative."
```

**6. Create New Strategy**

```
"I want to create a Bollinger Bands strategy. Guide me through the implementation."
```

### For Testing & Validation

**7. Run Tests**

```
"Run all tests and fix any failures."
```

**8. Security Review**

```
"Perform a security audit before I deploy to live trading."
```

**9. Validate Configuration**

```
"Review my .env configuration and check if my risk parameters are appropriate for a $10,000 account."
```

### For Deployment

**10. Pre-Deployment Check**

```
"I want to deploy to live trading. Walk me through the pre-deployment checklist."
```

**11. Gradual Rollout**

```
"Create a gradual rollout plan for going live, starting with minimal risk."
```

### For Debugging

**12. Analyze Logs**

```
"Analyze the logs from today and tell me if there were any issues."
```

**13. Debug Issue**

```
"The bot is placing duplicate orders. Help me debug this issue."
```

**14. Performance Issues**

```
"The bot seems slow. Help me profile and optimize performance."
```

## Pro Tips

### Use Prompt Templates

For complex requests, use the templates in `.claude/prompts/`:

- `strategy-review.md` - Review and optimize strategies
- `security-audit.md` - Comprehensive security reviews
- `deployment-check.md` - Pre-deployment validation
- `testing-debug.md` - Testing and debugging help

### Safety First

Always follow this progression:

1. **Paper Trading** (test with simulated money)
1. **Small Live** (minimal position sizes)
1. **Full Live** (normal operation)

### Ask Specific Questions

The more context you provide, the better help you'll get:

**Good**: "Review the momentum strategy for a $25,000 account with moderate risk tolerance in the current high volatility market."

**Better**: Include your specific concerns: "Review the momentum strategy for a $25,000 account. I'm concerned the position sizes might be too large for the current volatility. Should I adjust the stop loss percentage?"

## Example Session

Here's a complete example of using the agent:

```
You: "Help me set up paper trading for the first time"

Agent: [Reviews your configuration, suggests appropriate settings]

You: "I want to use the momentum strategy with moderate risk. Is that good for current market conditions?"

Agent: [Analyzes strategy, provides recommendation, suggests parameters]

You: "Set it up for me"

Agent: [Configures .env, validates settings, prepares to run]

You: "Run all tests first"

Agent: [Runs pytest, mypy, validates everything passes]

You: "Start the bot"

Agent: [Provides command to start bot, explains what to monitor]

You: "After 24 hours - analyze the paper trading results"

Agent: [Reviews logs, analyzes performance, provides recommendations]
```

## Emergency Commands

### Stop the Bot Immediately

```
"How do I stop the bot immediately?"
```

### Cancel All Orders

```
"Help me cancel all open orders right now."
```

### Check Current Status

```
"Show me the current positions and recent activity."
```

## Best Practices

### Daily Checks

```
"Analyze today's trading and summarize performance."
```

### Weekly Reviews

```
"Review this week's trading performance and suggest any parameter adjustments."
```

### Before Any Changes

```
"I'm about to modify [COMPONENT]. What should I test to ensure it's safe?"
```

## Get More Help

### View Available Templates

```
"What prompt templates are available?"
```

### Understand a Component

```
"Explain how the risk manager works."
```

### Learn About Features

```
"What strategies are available and when should I use each one?"
```

## Project-Specific Knowledge

The agent understands:

- ✅ Revolut Crypto X API integration
- ✅ Ed25519 authentication
- ✅ All four trading strategies
- ✅ Risk management system
- ✅ Position sizing and limits
- ✅ Python asyncio patterns
- ✅ Pydantic models
- ✅ Testing with pytest

## What the Agent Can Do

### Code Tasks

- Write new trading strategies
- Add technical indicators
- Create tests
- Fix bugs
- Optimize performance
- Review security

### Analysis Tasks

- Review strategy logic
- Validate risk parameters
- Analyze trading logs
- Profile performance
- Identify issues

### Planning Tasks

- Design new features
- Plan deployments
- Create testing strategies
- Suggest improvements

### Educational Tasks

- Explain code
- Teach concepts
- Document systems
- Provide examples

## What Makes This Agent Special

1. **Financial Safety Focus**: Prioritizes preventing losses over features
1. **Risk-Aware**: Understands trading risks and recommends conservative approaches
1. **Testing Emphasis**: Insists on thorough testing before deployment
1. **Security Conscious**: Actively looks for vulnerabilities
1. **Project Context**: Knows your codebase structure and patterns
1. **Practical**: Provides actionable, specific advice

## Common Workflows

### Adding a New Indicator

```
1. "I want to add RSI indicator to the mean reversion strategy"
2. Agent helps implement the indicator
3. "Write tests for the new indicator logic"
4. Agent creates comprehensive tests
5. "Run tests and validate"
6. Agent runs tests and validates
7. "Test in paper mode"
8. Agent helps configure and monitor
```

### Debugging Production Issue

```
1. "The bot stopped generating signals. Help debug."
2. Agent asks for logs and symptoms
3. Provide requested information
4. Agent analyzes and identifies root cause
5. Agent suggests fix
6. "Implement the fix and test"
7. Agent implements, tests, and validates
```

### Preparing for Live Trading

```
1. "I've been paper trading for a week. Help me prepare for live."
2. Agent analyzes paper trading results
3. Agent runs pre-deployment checklist
4. Agent identifies any concerns
5. "Create a gradual rollout plan"
6. Agent creates safe deployment plan
7. "Help me execute phase 1"
8. Agent guides through first live trading
```

## Support

If you encounter issues:

1. Ask the agent for help (it's designed for troubleshooting)
1. Check the main README.md
1. Review the CHANGELOG.md
1. Check Revolut API documentation

## Version

Current agent version: **1.0.0**

Last updated: December 2024

______________________________________________________________________

**Remember**: This agent is designed to help you trade safely and profitably. Always follow its safety recommendations, especially regarding testing and risk management. When in doubt, ask!
