# GitHub Agents

This folder contains agent configurations synced from `.claude/agents/` for version control and team collaboration.

## Agent Files

All agent files follow the naming pattern: `<agent-name>.agent.md`

- **audit-docs.agent.md** — Documentation audit agent
- **backtest-analyst.agent.md** — Backtest analysis and strategy evaluation
- **code-improvement.agent.md** — Code quality and modernization review
- **security-reviewer.agent.md** — Security audit for financial trading code
- **strategy-review.agent.md** — Trading strategy analysis and optimization
- **testing-debug.agent.md** — Testing and debugging specialist

## Sync Process

These files are synced from `.claude/agents/` (Claude Desktop configuration):

```bash
# Sync all agents from .claude/agents/ to .github/agents/
just sync-agents
```

This ensures agent configurations are:
- ✅ Version controlled in git
- ✅ Accessible to all team members
- ✅ Documented in the repository
- ✅ Consistent across environments

## Source of Truth

- **`.claude/agents/`** — Local Claude Desktop configuration (not in git)
- **`.github/agents/`** — Version-controlled copy (synced via `just sync-agents`)

## Usage

These agent configurations can be used with:
- Claude Desktop (via `.claude/agents/`)
- GitHub Copilot Agents (future feature)
- Team documentation and onboarding
- CI/CD workflows (future integration)

## Related Files

- **`AGENTS.md`** — User guide for all available agents and how to use them
- **`.github/copilot-instructions.md`** — GitHub Copilot instructions (synced from `CLAUDE.md`)
