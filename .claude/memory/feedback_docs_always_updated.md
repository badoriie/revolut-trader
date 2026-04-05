______________________________________________________________________

## name: Always update documentation description: User requires documentation to be updated with every code change — Claude Code must handle this proactively without being asked. type: feedback

Always update relevant documentation when making any code change.

**Why:** The user considers documentation a first-class deliverable and does not want to have to remind Claude Code each time. This aligns with the CLAUDE.md rule under "Documentation Updates."

**How to apply:** After every code change, proactively update the relevant docs: `README.md` for features/config, `CHANGELOG.md` for bug fixes, inline docstrings for logic changes, `CLAUDE.md` for architectural changes, and any other relevant docs (e.g., `docs/` files). Do not wait to be asked — treat doc updates as part of the task completion criteria.
