#!/usr/bin/env bash
# Dependency vulnerability audit for revolut-trader.
#
# Usage:
#   deps-audit.sh --check    Check for vulnerabilities; exit non-zero if any found.
#   deps-audit.sh --fix      Upgrade affected packages, then re-check; exit non-zero
#                            only if vulnerabilities STILL remain after fix attempt.
#
# Exit codes:
#   0  No open vulnerabilities (or all resolved in --fix mode)
#   1  Vulnerabilities remain
#   2  Precondition failure (missing tool, broken environment)

set -euo pipefail

REPO="badoriie/revolut-trader"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_PATH="${REPO_ROOT}/.venv"
MODE="${1:-}"

log()  { printf '\033[1;34m[deps-audit]\033[0m %s\n' "$*" >&2; }
ok()   { printf '\033[1;32m[deps-audit]\033[0m %s\n' "$*" >&2; }
warn() { printf '\033[1;33m[deps-audit]\033[0m WARNING: %s\n' "$*" >&2; }
fail() { printf '\033[1;31m[deps-audit]\033[0m ERROR: %s\n' "$*" >&2; exit 2; }

[[ "$MODE" == "--check" || "$MODE" == "--fix" ]] || \
    fail "Usage: $0 --check | --fix"

command -v uv  >/dev/null 2>&1 || fail "uv not found in PATH"
command -v gh  >/dev/null 2>&1 || fail "gh CLI not found in PATH"
command -v jq  >/dev/null 2>&1 || fail "jq not found in PATH"

[[ -d "$VENV_PATH" ]] || \
    fail ".venv not found. Run: uv sync --extra dev --extra analytics"

[[ -x "${VENV_PATH}/bin/pip-audit" ]] || \
    fail "pip-audit not in .venv. Run: uv sync --extra dev"

# ---------------------------------------------------------------------------
# Helpers: collect package names into a temp file, then read back
# (avoids mapfile / bash 4+ requirement)
# ---------------------------------------------------------------------------

_fetch_dependabot_pkgs() {
    local page=1
    while true; do
        local response
        response=$(gh api "repos/${REPO}/dependabot/alerts?state=open&per_page=100&page=${page}" \
            --jq '[.[] | .dependency.package.name | ascii_downcase]' 2>/dev/null) || break
        local count
        count=$(echo "$response" | jq 'length' 2>/dev/null || echo 0)
        [[ "$count" -eq 0 ]] && break
        echo "$response" | jq -r '.[]' 2>/dev/null || true
        (( page++ ))
    done
}

_fetch_pipaudit_pkgs() {
    local audit_json
    # pip-audit exits 1 when vulns found — capture regardless
    audit_json=$(uv run pip-audit \
        --path "${VENV_PATH}" \
        --format json \
        --progress-spinner off \
        2>/dev/null) || true
    if [[ -n "$audit_json" ]]; then
        echo "$audit_json" | jq -r '
            .dependencies[]
            | select(.vulns | length > 0)
            | .name | ascii_downcase
        ' 2>/dev/null || true
    fi
}

_merge_pkgs() {
    # Read two files of package names, deduplicate, return sorted unique list
    sort -u "$1" "$2"
}

# ---------------------------------------------------------------------------
# Step 1: Audit
# ---------------------------------------------------------------------------
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

log "Fetching Dependabot open alerts..."
_fetch_dependabot_pkgs > "${TMP}/dependabot.txt" 2>/dev/null || true
DEPENDABOT_COUNT=$(wc -l < "${TMP}/dependabot.txt" | tr -d ' ')
if [[ "$DEPENDABOT_COUNT" -gt 0 ]]; then
    log "  Dependabot alerts: $(tr '\n' ' ' < "${TMP}/dependabot.txt")"
else
    log "  No open Dependabot alerts."
fi

log "Running pip-audit against .venv..."
_fetch_pipaudit_pkgs > "${TMP}/pipaudit.txt" 2>/dev/null || true
PIPAUDIT_COUNT=$(wc -l < "${TMP}/pipaudit.txt" | tr -d ' ')
if [[ "$PIPAUDIT_COUNT" -gt 0 ]]; then
    log "  pip-audit: $(tr '\n' ' ' < "${TMP}/pipaudit.txt")"
else
    log "  pip-audit: clean."
fi

_merge_pkgs "${TMP}/dependabot.txt" "${TMP}/pipaudit.txt" > "${TMP}/all_affected.txt"
TOTAL=$(wc -l < "${TMP}/all_affected.txt" | tr -d ' ')

if [[ "$TOTAL" -eq 0 ]]; then
    ok "No vulnerabilities found."
    exit 0
fi

# ---------------------------------------------------------------------------
# Step 2 (--check): Report and block
# ---------------------------------------------------------------------------
if [[ "$MODE" == "--check" ]]; then
    echo >&2
    printf '\033[1;31m[deps-audit]\033[0m FAIL: %d vulnerable package(s):\n' "$TOTAL" >&2
    sed 's/^/  - /' "${TMP}/all_affected.txt" >&2
    echo >&2
    printf '\033[1;33m[deps-audit]\033[0m Run \033[1mjust deps-update\033[0m to attempt automatic fixes.\n' >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Step 3 (--fix): Upgrade each affected package within semver constraints
# ---------------------------------------------------------------------------
log "Attempting per-package upgrades..."
UPGRADE_FAILURES=""
while IFS= read -r pkg; do
    [[ -z "$pkg" ]] && continue
    log "  uv lock --upgrade-package ${pkg}"
    if uv lock --upgrade-package "${pkg}" 2>&1; then
        ok "  Locked: ${pkg}"
    else
        warn "  Could not upgrade ${pkg} (may be blocked by ~= constraint in pyproject.toml)"
        UPGRADE_FAILURES="${UPGRADE_FAILURES} ${pkg}"
    fi
done < "${TMP}/all_affected.txt"

log "Syncing environment..."
uv sync --extra dev --extra analytics --quiet 2>&1 || \
    fail "uv sync failed. Resolve manually."

# ---------------------------------------------------------------------------
# Step 4 (--fix): Verify fixes
# ---------------------------------------------------------------------------
log "Re-running pip-audit to verify..."
_fetch_pipaudit_pkgs > "${TMP}/pipaudit_after.txt" 2>/dev/null || true

log "Re-fetching Dependabot alerts..."
_fetch_dependabot_pkgs > "${TMP}/dependabot_after.txt" 2>/dev/null || true

_merge_pkgs "${TMP}/dependabot_after.txt" "${TMP}/pipaudit_after.txt" > "${TMP}/remaining.txt"
REMAINING=$(wc -l < "${TMP}/remaining.txt" | tr -d ' ')

if [[ "$REMAINING" -eq 0 ]]; then
    ok "All vulnerabilities resolved."
    echo >&2
    log "Stage uv.lock before committing:"
    log "  git add uv.lock && git commit -m 'chore(deps): upgrade vulnerable packages'"
    exit 0
fi

echo >&2
printf '\033[1;31m[deps-audit]\033[0m FAIL: %d package(s) still vulnerable after upgrade:\n' \
    "$REMAINING" >&2
sed 's/^/  - /' "${TMP}/remaining.txt" >&2
echo >&2
warn "Packages blocked by ~= constraints require a manual version bump in pyproject.toml."
[[ -n "${UPGRADE_FAILURES// /}" ]] && warn "Lock failures:${UPGRADE_FAILURES}"
exit 1
