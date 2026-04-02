#!/bin/bash
# deploy.sh — Single source of truth for deploying to Vercel.
#
# EVERY script that pushes code MUST call this instead of raw `git push`.
# This script does git push AND vercel deploy. No exceptions.
#
# Usage:
#   scripts/deploy.sh                          # push current staged/committed changes
#   scripts/deploy.sh --files "file1 file2"    # git add specific files, commit, push, deploy
#   scripts/deploy.sh --message "commit msg"   # custom commit message
#   scripts/deploy.sh --skip-commit            # just push + deploy (already committed)
#
# From Python:
#   subprocess.run(["bash", "scripts/deploy.sh", "--skip-commit"], cwd=PROJECT_ROOT)
#
# Returns: 0 on success, 1 on failure

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

DEPLOY_LOG="$REPO_ROOT/logs/deploy.log"
LAST_DEPLOYED="$REPO_ROOT/.last_deployed_commit"
mkdir -p "$REPO_ROOT/logs"

log() {
  local msg="[deploy] $(date '+%Y-%m-%d %H:%M:%S') $1"
  echo "$msg"
  echo "$msg" >> "$DEPLOY_LOG"
}

# ── Parse args ──────────────────────────────────────────
FILES=""
MESSAGE=""
SKIP_COMMIT=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --files)    FILES="$2"; shift 2 ;;
    --message)  MESSAGE="$2"; shift 2 ;;
    --skip-commit) SKIP_COMMIT=true; shift ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

# ── Stage + Commit (unless --skip-commit) ───────────────
if [ "$SKIP_COMMIT" = false ]; then
  if [ -n "$FILES" ]; then
    for f in $FILES; do
      git add "$f" 2>/dev/null || true
    done
  fi

  if ! git diff --cached --quiet 2>/dev/null; then
    COMMIT_MSG="${MESSAGE:-[auto] deploy $(date '+%Y-%m-%d %H:%M')}"
    git commit -m "$COMMIT_MSG" \
      --author="Deploy Bot <noreply@clawdbot.local>" 2>/dev/null || true
  fi
fi

# ── Push to GitHub ──────────────────────────────────────
log "Pushing to GitHub..."
PUSH_OUTPUT=$(git push 2>&1) || {
  log "FAIL: git push failed: $PUSH_OUTPUT"
  exit 1
}
log "Push OK."

# ── Deploy to Vercel ────────────────────────────────────
log "Deploying to Vercel production..."
VERCEL_OUTPUT=$(npx vercel deploy --prod --yes 2>&1) || {
  log "FAIL: vercel deploy failed. Retrying in 5s..."
  sleep 5
  VERCEL_OUTPUT=$(npx vercel deploy --prod --yes 2>&1) || {
    log "FAIL: vercel deploy failed twice: $VERCEL_OUTPUT"
    exit 1
  }
}

# Extract the deploy URL for logging
DEPLOY_URL=$(echo "$VERCEL_OUTPUT" | grep -o 'https://[^ ]*vercel.app' | tail -1)
log "Deploy OK: ${DEPLOY_URL:-unknown}"

# ── Record deployed commit ─────────────────────────────
git rev-parse HEAD > "$LAST_DEPLOYED"
log "Recorded deployed commit: $(cat "$LAST_DEPLOYED")"
