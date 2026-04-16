---
name: Always update documentation
description: User requires documentation updated with every code change — Claude Code must handle proactively without being asked.
type: feedback
originSessionId: 3f7d10a1-ef5d-4b1e-8ae7-facdac5723da
---
Always update relevant documentation when making any code change.

**Why:** The user considers documentation a first-class deliverable and does not want to have to remind Claude Code each time. This aligns with the CLAUDE.md rule under "Documentation Updates."

**How to apply:** After every code change, proactively update the relevant docs: `README.md` for features/config, inline docstrings for logic changes, `.claude/CLAUDE.md` for architectural changes, and any other relevant `docs/` files. Do not wait to be asked — treat doc updates as part of the task completion criteria.
