#!/bin/bash
# Morning Orchestration Pipeline — runs daily at 6AM
#
# Credentials: all keys come from env vars (inherited from ~/.zshrc).
# See .env.example for variable names. NEVER hardcode keys in scripts.
#
# Flow:
#   1. morning_audit.py runs all checks → findings JSON + HTML page
#   2. If findings need fixes → Claude Opus decides what to fix
#   3. Claude Sonnet implements the fixes
#   4. Commit + push + deploy
#
# Usage:
#   ./scripts/morning_orchestrator.sh           # full pipeline
#   ./scripts/morning_orchestrator.sh --audit   # audit only (no fixes)

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_FILE="$REPO_ROOT/logs/morning_orchestrator.log"
FINDINGS="/tmp/morning-audit-findings.json"
FIXES="/tmp/morning-fixes.json"
TIMESTAMP=$(date -u +"%Y-%m-%d %H:%M UTC")

mkdir -p "$REPO_ROOT/logs"

log() {
  echo "$TIMESTAMP | MORNING | $1" | tee -a "$LOG_FILE"
}

# ---------------------------------------------------------------------------
# Step 1: Run the audit
# ---------------------------------------------------------------------------
log "Starting morning audit..."
# Source env vars only (skip completions that fail in non-interactive shells)
eval "$(grep '^export ' ~/.zshrc 2>/dev/null)" || true

python3 "$REPO_ROOT/scripts/morning_audit.py" 2>&1 | tee -a "$LOG_FILE"
AUDIT_EXIT=$?

log "Audit complete (exit=$AUDIT_EXIT)"

# If --audit flag, stop here
if [[ "${1:-}" == "--audit" ]]; then
  log "Audit-only mode. Stopping."
  exit $AUDIT_EXIT
fi

# ---------------------------------------------------------------------------
# Step 2: Check if fixes are needed
# ---------------------------------------------------------------------------
FIX_COUNT=$(python3 -c "import json; d=json.load(open('$FIXES')); print(len(d))" 2>/dev/null || echo "0")

if [[ "$FIX_COUNT" == "0" ]]; then
  log "No fixes needed. System healthy."

  # Still commit and push the updated health page
  cd "$REPO_ROOT"
  if git diff --quiet public/system-health.html 2>/dev/null; then
    log "Health page unchanged. Done."
  else
    git add public/system-health.html
    git commit -m "[auto] daily health check — all clear ($TIMESTAMP)" \
      --author="Morning Audit <noreply@clawdbot.local>" 2>/dev/null || true
    git push 2>/dev/null || log "WARN: git push failed"
    log "Health page updated and deployed."
  fi
  exit 0
fi

log "$FIX_COUNT issue(s) found. Sending to Claude Opus for review..."

# ---------------------------------------------------------------------------
# Step 3: Claude Opus decides what to fix
# ---------------------------------------------------------------------------
OPUS_PROMPT="You are the morning system auditor for Master CRM. Read the findings below and decide what should be fixed automatically vs what needs human review.

Rules:
- CRITICAL severity: fix automatically if the fix is safe and reversible
- HIGH severity: fix automatically if straightforward, otherwise flag for human
- MEDIUM/LOW: log but do not fix
- Never rotate API keys automatically
- Never delete data automatically
- Never modify ~/.zshrc automatically

For each fix, output a JSON object with:
  {\"action\": \"fix|skip|human\", \"check\": \"name\", \"instruction\": \"exact steps for Sonnet\"}

Findings:
$(cat "$FIXES")

Output ONLY a JSON array of fix instructions. No explanation."

OPUS_RESPONSE=$(echo "$OPUS_PROMPT" | claude -p --model claude-opus-4-6 --output-format text 2>/dev/null || echo "[]")

log "Opus response received."

# Save Opus decisions
echo "$OPUS_RESPONSE" > /tmp/morning-opus-decisions.json

# ---------------------------------------------------------------------------
# Step 4: Claude Sonnet implements fixes
# ---------------------------------------------------------------------------
# Extract only "fix" actions
FIX_INSTRUCTIONS=$(echo "$OPUS_RESPONSE" | python3 -c "
import sys, json, re
raw = sys.stdin.read().strip()
# Strip markdown code fences if Opus wrapped its response
raw = re.sub(r'^\`\`\`json?\s*', '', raw)
raw = re.sub(r'\s*\`\`\`$', '', raw)
try:
    decisions = json.loads(raw)
    fixes = [d for d in decisions if d.get('action') == 'fix']
    if fixes:
        print(json.dumps(fixes, indent=2))
    else:
        print('NONE')
except Exception as e:
    print('NONE')
" 2>/dev/null || echo "NONE")

if [[ "$FIX_INSTRUCTIONS" == "NONE" ]]; then
  log "Opus decided: no automatic fixes needed."
else
  log "Sending fix instructions to Sonnet..."

  SONNET_PROMPT="You are implementing morning audit fixes for Master CRM Web at $REPO_ROOT.

Rules:
- Make the minimum change needed to fix each issue
- Do NOT modify ~/.zshrc or rotate keys
- Do NOT delete data
- Use Edit tool for file changes
- After all fixes, verify with: python3 scripts/morning_audit.py --check <name>

Fix instructions from Opus:
$FIX_INSTRUCTIONS"

  echo "$SONNET_PROMPT" | claude -p --model claude-sonnet-4-6 --output-format text 2>/dev/null | tee -a "$LOG_FILE"
  log "Sonnet fixes applied."
fi

# ---------------------------------------------------------------------------
# Step 5: Commit + push updated health page
# ---------------------------------------------------------------------------
cd "$REPO_ROOT"
git add public/system-health.html 2>/dev/null || true

if ! git diff --cached --quiet 2>/dev/null; then
  git commit -m "[auto] morning audit — $FIX_COUNT issue(s) found ($TIMESTAMP)" \
    --author="Morning Audit <noreply@clawdbot.local>" 2>/dev/null || true
  git push 2>/dev/null || log "WARN: git push failed"
  log "Changes committed and pushed."
fi

log "Morning orchestration complete."
