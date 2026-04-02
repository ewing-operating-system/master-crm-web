#!/bin/bash
# deploy_watchdog.sh — Safety net that runs on cron.
#
# Every 5 minutes, checks if the live Vercel site matches the latest git commit.
# If they're out of sync, forces a deploy. This catches ANY gap — whether from
# a script that forgot to deploy, a manual push, or a failed webhook.
#
# Cron: */5 * * * * source ~/.zshrc && /Users/clawdbot/Projects/master-crm-web/scripts/deploy_watchdog.sh
#
# How it works:
#   1. Gets the latest commit hash on origin/main
#   2. Reads .last_deployed_commit (written by deploy.sh after each successful deploy)
#   3. If they differ → runs vercel deploy --prod
#   4. Logs everything to logs/deploy_watchdog.log

set -uo pipefail

REPO_ROOT="/Users/clawdbot/Projects/master-crm-web"
cd "$REPO_ROOT"

LOG="$REPO_ROOT/logs/deploy_watchdog.log"
LAST_DEPLOYED="$REPO_ROOT/.last_deployed_commit"
LOCKFILE="/tmp/deploy_watchdog.lock"
mkdir -p "$REPO_ROOT/logs"

log() {
  echo "[watchdog] $(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG"
}

# ── Prevent concurrent runs ────────────────────────────
if [ -f "$LOCKFILE" ]; then
  LOCK_AGE=$(( $(date +%s) - $(stat -f %m "$LOCKFILE" 2>/dev/null || echo 0) ))
  if [ "$LOCK_AGE" -lt 300 ]; then
    exit 0  # Another watchdog is running, skip silently
  fi
  rm -f "$LOCKFILE"  # Stale lock, remove
fi
trap "rm -f $LOCKFILE" EXIT
echo $$ > "$LOCKFILE"

# ── Fetch latest from remote ───────────────────────────
git fetch origin main --quiet 2>/dev/null || {
  log "WARN: git fetch failed"
  exit 0
}

REMOTE_HEAD=$(git rev-parse origin/main 2>/dev/null)
if [ -z "$REMOTE_HEAD" ]; then
  log "WARN: could not read origin/main HEAD"
  exit 0
fi

# ── Compare to last deployed ───────────────────────────
DEPLOYED_HEAD=""
if [ -f "$LAST_DEPLOYED" ]; then
  DEPLOYED_HEAD=$(cat "$LAST_DEPLOYED" 2>/dev/null)
fi

if [ "$REMOTE_HEAD" = "$DEPLOYED_HEAD" ]; then
  # In sync, nothing to do
  exit 0
fi

# ── Out of sync — deploy now ───────────────────────────
REMOTE_SHORT=$(echo "$REMOTE_HEAD" | cut -c1-7)
DEPLOYED_SHORT=$(echo "$DEPLOYED_HEAD" | cut -c1-7)
log "DRIFT DETECTED: deployed=${DEPLOYED_SHORT:-none} remote=${REMOTE_SHORT}"
log "Deploying to Vercel production..."

VERCEL_OUTPUT=$(npx vercel deploy --prod --yes 2>&1) || {
  log "FAIL: vercel deploy failed. Retrying in 10s..."
  sleep 10
  VERCEL_OUTPUT=$(npx vercel deploy --prod --yes 2>&1) || {
    log "FAIL: vercel deploy failed twice. Will retry next cycle."
    exit 1
  }
}

DEPLOY_URL=$(echo "$VERCEL_OUTPUT" | grep -o 'https://[^ ]*vercel.app' | tail -1)
log "Deploy OK: ${DEPLOY_URL:-unknown}"

# Record the deployed commit
echo "$REMOTE_HEAD" > "$LAST_DEPLOYED"
log "Synced: now at ${REMOTE_SHORT}"
