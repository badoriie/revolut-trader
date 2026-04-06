# GitHub Copilot Configuration

This folder is part of the GitHub Copilot config mirroring the `.claude/` setup.

## Structure

```
.github/
├── copilot-instructions.md        ← synced from CLAUDE.md (global instructions)
├── agents/                        ← synced from .claude/agents/ (specialized agents)
│   └── *.agent.md
├── instructions/                  ← synced from .claude/rules/ (context-specific rules)
│   ├── deployment-check.instructions.md
│   └── security-audit.instructions.md
└── prompts/                       ← maintained directly (reusable prompt files / skills)
    └── revolut-api.prompt.md
```

## Mapping to `.claude/`

| `.claude/` | `.github/` | Sync method |
|---|---|---|
| `CLAUDE.md` | `copilot-instructions.md` | `just sync-copilot` |
| `agents/*.md` | `agents/*.agent.md` | `just sync-agents` |
| `rules/*.md` | `instructions/*.instructions.md` | `just sync-rules` |
| `skills/*.md` | `prompts/*.prompt.md` | Maintained directly |
| `hooks/` | — | No Copilot equivalent |
| `memory/` | — | No Copilot equivalent |

## Sync Commands

```bash
just sync-all       # sync everything (copilot-instructions + agents + rules)
just sync-copilot   # sync CLAUDE.md → copilot-instructions.md
just sync-agents    # sync .claude/agents/ → .github/agents/
just sync-rules     # sync .claude/rules/ → .github/instructions/
```

Run `just sync-all` after any changes to `CLAUDE.md`, `.claude/agents/`, or `.claude/rules/`.

## Agent Files

- **audit-docs.agent.md** — Documentation audit agent
- **backtest-analyst.agent.md** — Backtest analysis and strategy evaluation
- **code-improvement.agent.md** — Code quality and modernization review
- **security-reviewer.agent.md** — Security audit for financial trading code
- **strategy-review.agent.md** — Trading strategy analysis and optimization
- **testing-debug.agent.md** — Testing and debugging specialist
