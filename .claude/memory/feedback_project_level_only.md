______________________________________________________________________

## name: Project-level configuration only description: All Claude Code settings, hooks, agents, skills, rules, and memories must be stored at the project level, never globally. type: feedback

Keep everything at the project level, not global.

**Why:** User explicitly requires all Claude Code configuration (settings, hooks, agents, skills, rules, memory) to live inside the project directory (`.claude/`), not in global Claude Code config.

**How to apply:** When configuring hooks, agents, skills, or any settings, always write to `.claude/settings.json` or `.claude/` subdirectories. Never modify `~/.claude/` or any global config path.
