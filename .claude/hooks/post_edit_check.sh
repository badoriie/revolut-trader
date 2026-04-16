#!/usr/bin/env bash
# PostToolUse hook: enforces project conventions after Write/Edit
# Runs jq once, checks all rules in a single pass.

INPUT=$(cat)
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
[ -z "$FILE" ] && exit 0

MSGS=()

# Financial code: Decimal required, never float
echo "$FILE" | grep -qE '^src/(execution|risk_management|strategies|backtest|models|utils/fees)' && \
  MSGS+=("FINANCIAL [$FILE]: Use Decimal(\"...\") never float. ORM columns: Numeric(20,10) never Float.")

# All Python files: docs must stay in sync
echo "$FILE" | grep -qE '^(src|cli)/.+\.py$' && \
  MSGS+=("DOCS [$FILE]: Update README.md, docstrings, .claude/CLAUDE.md, and relevant docs/ guides.")

# API files: must match API docs
echo "$FILE" | grep -qE '^src/api/' && \
  MSGS+=("API [$FILE]: Cross-check docs/revolut-x-api-docs.md — fix code to match docs, not the reverse.")

# Security-sensitive files: credential hygiene
echo "$FILE" | grep -qE '^src/(config|utils/(one_password|encryption)|api/client)\.py$' && \
  MSGS+=("SECURITY [$FILE]: No credentials in code/logs. Secrets via 1Password only. Ed25519 key never logged.")

# Strategy/indicator files: update user-facing docs
echo "$FILE" | grep -qE '^src/strategies/[^/]+\.py$|^src/utils/indicators\.py$' && \
  MSGS+=("STRATEGY [$FILE]: Update docs/END_USER_GUIDE.md — strategies table if new strategy, indicators table if new indicator.")

[ ${#MSGS[@]} -eq 0 ] && exit 0

COMBINED=$(IFS=$'\n'; echo "${MSGS[*]}")
printf '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"%s"}}\n' \
  "$(echo "$COMBINED" | sed 's/\\/\\\\/g; s/"/\\"/g')"
