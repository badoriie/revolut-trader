#!/usr/bin/env bash
# Stop hook: fetch open CRITICAL/BLOCKER SonarCloud issues for the current branch/PR.
# Requires SONAR_TOKEN in the environment (or via op run).
# Silently skips if token is unavailable.

PROJECT_KEY="badoriie_revolut-trader"
API_URL="https://sonarcloud.io/api"

# Resolve token — try env first, then 1Password
if [ -z "$SONAR_TOKEN" ]; then
  SONAR_TOKEN=$(op read "op://Employee/sonarcloud-token/credential" 2>/dev/null || true)
fi
if [ -z "$SONAR_TOKEN" ]; then
  echo "WARNING: SONAR_TOKEN not found in env or 1Password — SonarCloud check skipped."
  exit 0
fi

# Determine branch context
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
[ -z "$BRANCH" ] && exit 0

# Use branch param (PRs are shown on the branch in SonarCloud)
BRANCH_PARAM="branch=${BRANCH}"
# Fall back to main when on a detached HEAD or main itself
[ "$BRANCH" = "HEAD" ] && BRANCH_PARAM="branch=main"

RESPONSE=$(curl -s --max-time 10 -u "${SONAR_TOKEN}:" \
  "${API_URL}/issues/search?componentKeys=${PROJECT_KEY}&${BRANCH_PARAM}&severities=BLOCKER,CRITICAL&statuses=OPEN,CONFIRMED,REOPENED&ps=20" \
  2>/dev/null)

if [ -z "$RESPONSE" ]; then
  echo "WARNING: SonarCloud API returned no response — check network or token validity."
  exit 0
fi

TOTAL=$(echo "$RESPONSE" | jq -r '.total // 0' 2>/dev/null)
[ "$TOTAL" = "0" ] && echo "SonarCloud: no CRITICAL/BLOCKER issues on branch '${BRANCH}'." && exit 0

echo "SonarCloud: ${TOTAL} open CRITICAL/BLOCKER issue(s) on '${BRANCH}':"
echo "$RESPONSE" | jq -r '
  .issues[] |
  "  [\(.severity)] \(.rule) — \(.component | split(":")[1] // .component):\(.line // "-") — \(.message)"
' 2>/dev/null
