#!/bin/bash
# =============================================================================
# MANDATORY FIXES — Run from regular terminal (NOT inside Claude Code)
# Usage: bash ~/Projects/master-crm-web/fix-mandatory.sh
# =============================================================================

set -e
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[FIX]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; }

# ─────────────────────────────────────────────────────────────────────────────
# FIX 1: Supabase credential mismatch in ~/.openclaw/.env
# The primary .env has keys from project rdnnhxhohwjucvjwbwch (OLD)
# but URL points to dwrnfpjcvydhmhnvyzov (CURRENT).
# Workspace .env has the correct keys.
# ─────────────────────────────────────────────────────────────────────────────
log "FIX 1: Patching Supabase credentials in ~/.openclaw/.env"

CORRECT_ANON="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImR3cm5mcGpjdnlkaG1obnZ5em92Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ3NTcyOTAsImV4cCI6MjA5MDMzMzI5MH0.z0Gu1TWdGPcdptB5W7efnYMmxBbvD353ExG99ftQivY"
CORRECT_SERVICE="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImR3cm5mcGpjdnlkaG1obnZ5em92Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NDc1NzI5MCwiZXhwIjoyMDkwMzMzMjkwfQ.7Bd_6aZhpWazv-evA_f1WpocfEHcXX8JATLNSKAC00s"

# Backup first
cp ~/.openclaw/.env ~/.openclaw/.env.backup.$(date +%s)

# Replace the wrong keys with correct ones
sed -i '' "s|^SUPABASE_ANON_KEY=.*|SUPABASE_ANON_KEY=${CORRECT_ANON}|" ~/.openclaw/.env
sed -i '' "s|^SUPABASE_SERVICE_ROLE_KEY=.*|SUPABASE_SERVICE_ROLE_KEY=${CORRECT_SERVICE}|" ~/.openclaw/.env

# Also fix the MASTER_CRM key (it had a fabricated token)
sed -i '' "s|^MASTER_CRM_SUPABASE_SERVICE_ROLE_KEY=.*|MASTER_CRM_SUPABASE_SERVICE_ROLE_KEY=${CORRECT_SERVICE}|" ~/.openclaw/.env

# Verify
source ~/.openclaw/.env
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${SUPABASE_URL}/rest/v1/targets?select=id&limit=1" \
  -H "apikey: ${SUPABASE_SERVICE_ROLE_KEY}" \
  -H "Authorization: Bearer ${SUPABASE_SERVICE_ROLE_KEY}" 2>/dev/null)

if [ "$HTTP_CODE" = "200" ]; then
  log "Supabase credentials FIXED and VERIFIED (HTTP 200)"
else
  fail "Supabase still returning HTTP ${HTTP_CODE} — check keys manually"
fi

# ─────────────────────────────────────────────────────────────────────────────
# FIX 2: Write SQL migration for missing Supabase tables
# meeting_notes (for meeting page v2 auto-save)
# campaign_batches, call_outcomes, letter_campaigns (for 250/150 governor)
# RESEARCHED enum value
# ─────────────────────────────────────────────────────────────────────────────
log "FIX 2: Writing SQL migration file for missing tables"

mkdir -p ~/Projects/master-crm-web/migrations
cat > ~/Projects/master-crm-web/migrations/003_mandatory_tables.sql << 'SQLEOF'
-- =============================================================================
-- MANDATORY TABLES — Run in Supabase SQL Editor
-- =============================================================================

-- 1. Meeting notes (meeting page v2 auto-save)
CREATE TABLE IF NOT EXISTS meeting_notes (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  meeting_id text NOT NULL,
  field_name text NOT NULL,
  field_value text,
  captured_at timestamptz DEFAULT now(),
  UNIQUE(meeting_id, field_name)
);

-- 2. Campaign batches (250/150 governor)
CREATE TABLE IF NOT EXISTS campaign_batches (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  batch_number integer NOT NULL,
  entity text NOT NULL DEFAULT 'next_chapter',
  status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'MAILING', 'CALLING', 'COMPLETE', 'PAUSED')),
  letter_count integer NOT NULL DEFAULT 0 CHECK (letter_count <= 250),
  call_target integer NOT NULL DEFAULT 150,
  calls_completed integer NOT NULL DEFAULT 0,
  created_at timestamptz DEFAULT now(),
  locked_at timestamptz,
  completed_at timestamptz
);

-- Only one active batch at a time
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_batch
  ON campaign_batches (entity)
  WHERE status IN ('MAILING', 'CALLING');

-- 3. Call outcomes (Salesfinity tracking)
CREATE TABLE IF NOT EXISTS call_outcomes (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  batch_id uuid REFERENCES campaign_batches(id),
  target_id uuid REFERENCES targets(id),
  contact_name text,
  phone text,
  attempt_number integer NOT NULL DEFAULT 1 CHECK (attempt_number <= 5),
  outcome text CHECK (outcome IN ('CONNECTED', 'VOICEMAIL', 'NO_ANSWER', 'WRONG_NUMBER', 'CALLBACK', 'NOT_INTERESTED', 'INTERESTED')),
  notes text,
  called_at timestamptz DEFAULT now()
);

-- 4. Letter campaigns (Lob tracking)
CREATE TABLE IF NOT EXISTS letter_campaigns (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  batch_id uuid REFERENCES campaign_batches(id),
  target_id uuid REFERENCES targets(id),
  lob_letter_id text,
  variant text CHECK (variant IN ('touch_1', 'touch_2', 'touch_3')),
  status text DEFAULT 'QUEUED' CHECK (status IN ('QUEUED', 'SENT', 'DELIVERED', 'RETURNED')),
  sent_at timestamptz,
  delivered_at timestamptz,
  created_at timestamptz DEFAULT now()
);

-- 5. Add RESEARCHED to pipeline_status enum (if it's an enum)
DO $$ BEGIN
  ALTER TYPE pipeline_status ADD VALUE IF NOT EXISTS 'RESEARCHED';
EXCEPTION WHEN others THEN
  RAISE NOTICE 'pipeline_status is not an enum or RESEARCHED already exists — skipping';
END $$;

-- 6. Index for regeneration scripts
CREATE INDEX IF NOT EXISTS idx_targets_pipeline_status ON targets(pipeline_status);
CREATE INDEX IF NOT EXISTS idx_targets_research_completed ON targets(research_completed_at) WHERE research_completed_at IS NOT NULL;
SQLEOF

log "Migration file written: ~/Projects/master-crm-web/migrations/003_mandatory_tables.sql"

# ─────────────────────────────────────────────────────────────────────────────
# FIX 3: Sync CRM project .env with correct Supabase creds
# Reference env var names, not raw keys — prevents key sprawl
# ─────────────────────────────────────────────────────────────────────────────
log "FIX 3: Ensuring CRM project .env has Supabase credentials"

CRM_ENV=~/Projects/master-crm-web/.env

# Verify .gitignore covers .env before writing keys
GITIGNORE=~/Projects/master-crm-web/.gitignore
SAFE_TO_WRITE=false

if [ -f "$GITIGNORE" ]; then
  if grep -qE '^\\.env$|^\\.env\\b' "$GITIGNORE" 2>/dev/null; then
    SAFE_TO_WRITE=true
  fi
fi

if [ "$SAFE_TO_WRITE" = false ]; then
  warn ".gitignore doesn't cover .env — adding it now"
  echo ".env" >> "$GITIGNORE"
  log "Added .env to .gitignore"
fi

if [ -f "$CRM_ENV" ]; then
  if ! grep -q "SUPABASE_URL" "$CRM_ENV"; then
    echo "" >> "$CRM_ENV"
    echo "# Supabase (added by fix-mandatory.sh)" >> "$CRM_ENV"
    echo "SUPABASE_URL=https://dwrnfpjcvydhmhnvyzov.supabase.co" >> "$CRM_ENV"
    echo "SUPABASE_SERVICE_ROLE_KEY=${CORRECT_SERVICE}" >> "$CRM_ENV"
    echo "SUPABASE_ANON_KEY=${CORRECT_ANON}" >> "$CRM_ENV"
    log "Added Supabase creds to CRM project .env"
  else
    log "CRM project .env already has Supabase creds"
  fi
else
  cat > "$CRM_ENV" << EOF
SUPABASE_URL=https://dwrnfpjcvydhmhnvyzov.supabase.co
SUPABASE_SERVICE_ROLE_KEY=${CORRECT_SERVICE}
SUPABASE_ANON_KEY=${CORRECT_ANON}
EOF
  log "Created CRM project .env"
fi

# ─────────────────────────────────────────────────────────────────────────────
# VERIFICATION
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "=========================================="
echo "  VERIFICATION"
echo "=========================================="

# Re-source
source ~/.openclaw/.env

# Test Supabase
HTTP=$(curl -s -o /dev/null -w "%{http_code}" "${SUPABASE_URL}/rest/v1/targets?select=id&limit=1" \
  -H "apikey: ${SUPABASE_SERVICE_ROLE_KEY}" \
  -H "Authorization: Bearer ${SUPABASE_SERVICE_ROLE_KEY}")
[ "$HTTP" = "200" ] && log "Supabase: CONNECTED" || fail "Supabase: HTTP $HTTP"

# Test Lob
LOB=$(curl -s -o /dev/null -w "%{http_code}" -u "${LOB_SECRET_KEY}:" "https://api.lob.com/v1/addresses?limit=1")
[ "$LOB" = "200" ] && log "Lob API: CONNECTED" || fail "Lob API: HTTP $LOB"

# Test OpenClaw gateway
GW=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:18789/health 2>/dev/null)
[ "$GW" = "200" ] && log "OpenClaw Gateway: RUNNING" || warn "OpenClaw Gateway: not responding"

# Test Ollama
OL=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:11434/api/tags 2>/dev/null)
[ "$OL" = "200" ] && log "Ollama: RUNNING" || warn "Ollama: not responding"

# Tailscale
TS=$(tailscale status 2>/dev/null | head -1)
[ -n "$TS" ] && log "Tailscale: $TS" || warn "Tailscale: not accessible"

echo ""
echo "=========================================="
echo "  MANUAL STEP REMAINING"
echo "=========================================="
echo ""
echo "1. Run the SQL migration in Supabase SQL Editor:"
echo "   https://supabase.com/dashboard/project/dwrnfpjcvydhmhnvyzov/sql"
echo "   File: ~/Projects/master-crm-web/migrations/003_mandatory_tables.sql"
echo ""
echo "2. Re-run the 4 blocked overnight builds in Claude Code:"
echo "   claude -p \"\$(cat ~/Projects/master-crm-web/prompts/build2.txt)\""
echo "   claude -p \"\$(cat ~/Projects/master-crm-web/prompts/build3.txt)\""
echo "   claude -p \"\$(cat ~/Projects/master-crm-web/prompts/build7.txt)\""
echo "   claude -p \"\$(cat ~/Projects/master-crm-web/prompts/build8.txt)\""
echo ""
echo "=========================================="
log "Script complete."
