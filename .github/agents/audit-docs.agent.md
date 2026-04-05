---
name: audit-docs
description: Documentation audit agent. Explores codebase, finds inaccuracies in README.md, CLAUDE.md, and docs/, then fixes them. Use when docs may be stale or out of sync with code.
tools: Read Glob Grep Bash Write Edit
---

Perform a comprehensive review and improvement of the project documentation and structure. This is a thorough audit — find issues and fix them.

## 1. Verify Project Structure

Explore the actual codebase structure:

- List all directories under `src/` and their contents
- List all files in `.github/workflows/`
- List all files in `cli/`
- List all files in `tests/` (including subdirectories)
- List all files in `docs/`

## 2. Review README.md

Read `README.md` and check for:

- **Accuracy**: Does the project structure tree match reality? Are all workflows, CLI files, test directories, and docs listed?
- **Badges**: Are all badges working and relevant?
- **Commands**: Do the documented commands match the actual `justfile` and `revt` CLI?
- **Features**: Do listed features, strategies, and risk levels match the code?
- **Documentation links**: Do all referenced docs actually exist?

Fix any inaccuracies, missing items, or outdated information.

## 3. Review CLAUDE.md

Read `.claude/CLAUDE.md` and check for:

- **Commands section**: Do all commands match the actual `justfile` and `revt` CLI?
- **Architecture section**: Does it accurately describe the current codebase?
- **Key Files table**: Are all important files listed? Are any listed files missing from the repo?
- **Rules**: Are they still relevant and complete?

Fix any inaccuracies, missing components, or outdated information. After any changes, run `just sync-copilot`.

## 4. Review docs/ Files

Read each file in `docs/` and verify:

- Links between docs are valid
- Referenced commands and file paths exist
- Content matches current implementation
- No stale/outdated information

## 5. Review Workflows

Read each workflow in `.github/workflows/` and check:

- Action versions are not deprecated
- Permissions are correct
- Environment variables match the project

## 6. Summary

After all fixes, provide a summary of what was found and fixed.
