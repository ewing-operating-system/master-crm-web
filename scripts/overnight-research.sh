#!/bin/bash
# Credentials: all keys come from env vars (inherited from ~/.zshrc).
# See .env.example for variable names. NEVER hardcode keys in scripts.
# ============================================================
# OVERNIGHT RESEARCH SCRIPT — OpenClaw + Exa + Supabase
# Researches all 287 companies to SAP quality
# Run: bash ~/Projects/master-crm-web/scripts/overnight-research.sh
# ============================================================

set -euo pipefail

# --- Config ---
SUPABASE_URL="https://dwrnfpjcvydhmhnvyzov.supabase.co/rest/v1"
source ~/.openclaw/.env
SB_KEY="$SUPABASE_SERVICE_ROLE_KEY"
SB_HEADERS=(-H "apikey: $SB_KEY" -H "Authorization: Bearer $SB_KEY" -H "Content-Type: application/json" -H "Prefer: return=representation")
LOG_FILE="$HOME/Projects/master-crm-web/scripts/overnight-research.log"
BATCH_SIZE=5
SLEEP_BETWEEN=10  # seconds between batches (rate limit protection)

# --- Priority tiers ---
# Tier 1: The 6 companies on the live site (must be SAP quality first)
SITE_COMPANIES=(
  "HR.com Ltd"
  "AquaScience"
  "Springer Floor Care LLC"
  "Air Control"
  "Design Precast & Pipe, Inc."
  "Wieser Concrete Products, Inc."
)

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

send_telegram() {
  openclaw message send --channel telegram --target "$EWING_TELEGRAM_CHAT_ID" --message "$1" 2>/dev/null || true
}

# --- SAP Quality Check ---
# A company is SAP-quality if it has: revenue, ebitda, employee_count, year_founded, service_areas
check_sap_quality() {
  local company_id="$1"
  local result
  result=$(curl -s "${SUPABASE_URL}/companies?id=eq.${company_id}&select=estimated_revenue,estimated_ebitda,employee_count,year_founded,service_areas,pe_activity_level" \
    "${SB_HEADERS[@]}" 2>/dev/null)

  # Check if all SAP fields are populated
  echo "$result" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if not data:
    print('MISSING')
    sys.exit()
r = data[0]
fields = ['estimated_revenue', 'estimated_ebitda', 'employee_count', 'year_founded', 'service_areas']
missing = [f for f in fields if not r.get(f)]
if missing:
    print('MISSING:' + ','.join(missing))
else:
    print('SAP_OK')
" 2>/dev/null || echo "ERROR"
}

# --- Research a single company via OpenClaw ---
research_company() {
  local company_name="$1"
  local company_id="$2"

  log "🔍 Researching: $company_name (ID: $company_id)"

  local message="Research this company to SAP quality (M&A advisory standard — \$5,000 consulting report level).

Company: ${company_name}
Supabase ID: ${company_id}

Use Exa search (EXA_API_KEY in ~/.openclaw/.env) to find:
1. Estimated annual revenue (check BBB, Dun & Bradstreet, ZoomInfo, Google, industry databases)
2. Estimated EBITDA (use industry-standard margins for the vertical)
3. Employee count (LinkedIn, company website, Glassdoor)
4. Year founded (Secretary of State records, website about page)
5. Service areas (geographic coverage from their website/Google Business Profile)
6. PE activity level (any private equity interest in their vertical — check PitchBook references, recent deals)
7. Tech stack (if visible — what software they use)
8. Recurring revenue percentage estimate (for service businesses)
9. Owner/founder name and title

After research, update Supabase directly:
URL: https://dwrnfpjcvydhmhnvyzov.supabase.co/rest/v1
Service Role Key: read from MASTER_CRM_SERVICE_ROLE_KEY in ~/.openclaw/.env

PATCH the companies table where id='${company_id}' with all fields you found.
Also update lead_stage to 'researched' and field_confidence with a JSON object showing confidence per field (0.0-1.0).

Be thorough. This data feeds live M&A advisory pages that clients see."

  # Run the researcher agent with 5-minute timeout
  openclaw agent \
    --agent researcher \
    --message "$message" \
    --channel telegram \
    --deliver \
    --reply-to "$EWING_TELEGRAM_CHAT_ID" \
    --timeout 300 \
    --json 2>>"$LOG_FILE" || {
      log "❌ FAILED: $company_name"
      return 1
    }

  log "✅ Done: $company_name"
  return 0
}

# --- Main ---
main() {
  log "============================================"
  log "OVERNIGHT RESEARCH — STARTING"
  log "============================================"

  send_telegram "[Argus] 🌙 Overnight research starting. 287 companies to audit. Tier 1 (6 site companies) first. Go to sleep — I'll message you when done."

  # --- TIER 1: Site companies (priority) ---
  log "--- TIER 1: Live site companies ---"

  for company_name in "${SITE_COMPANIES[@]}"; do
    # Get company ID from Supabase
    local encoded_name
    encoded_name=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$company_name'))")
    local company_data
    company_data=$(curl -s "${SUPABASE_URL}/companies?company_name=eq.${encoded_name}&select=id" \
      "${SB_HEADERS[@]}" 2>/dev/null)

    local company_id
    company_id=$(echo "$company_data" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['id'] if d else 'NOT_FOUND')" 2>/dev/null)

    if [ "$company_id" = "NOT_FOUND" ]; then
      log "⚠️  Not in Supabase: $company_name — skipping"
      continue
    fi

    # Check if already SAP quality
    local quality
    quality=$(check_sap_quality "$company_id")

    if [ "$quality" = "SAP_OK" ]; then
      log "✅ Already SAP quality: $company_name — skipping"
      continue
    fi

    log "📋 Needs research ($quality): $company_name"
    research_company "$company_name" "$company_id"
    sleep $SLEEP_BETWEEN
  done

  send_telegram "[Argus] ✅ Tier 1 complete (6 site companies). Starting Tier 2 — remaining 281 companies."

  # --- TIER 2: All remaining companies in batches ---
  log "--- TIER 2: All remaining companies ---"

  local offset=0
  local total_researched=0
  local total_skipped=0
  local total_failed=0

  while true; do
    # Fetch next batch
    local batch
    batch=$(curl -s "${SUPABASE_URL}/companies?select=id,company_name&lead_stage=neq.researched&order=estimated_revenue.desc.nullslast&limit=${BATCH_SIZE}&offset=${offset}" \
      "${SB_HEADERS[@]}" 2>/dev/null)

    # Check if batch is empty
    local count
    count=$(echo "$batch" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))" 2>/dev/null)

    if [ "$count" = "0" ] || [ -z "$count" ]; then
      log "No more companies to research. Done!"
      break
    fi

    log "--- Batch starting at offset $offset ($count companies) ---"

    # Process each company in the batch
    echo "$batch" | python3 -c "
import json, sys
for c in json.load(sys.stdin):
    print(c['id'] + '|' + c['company_name'])
" 2>/dev/null | while IFS='|' read -r cid cname; do

      # Check SAP quality
      local quality
      quality=$(check_sap_quality "$cid")

      if [ "$quality" = "SAP_OK" ]; then
        log "✅ Already SAP: $cname"
        total_skipped=$((total_skipped + 1))
        continue
      fi

      research_company "$cname" "$cid" && {
        total_researched=$((total_researched + 1))
      } || {
        total_failed=$((total_failed + 1))
      }

      sleep $SLEEP_BETWEEN
    done

    offset=$((offset + BATCH_SIZE))

    # Progress update every 25 companies
    if [ $((offset % 25)) -eq 0 ]; then
      send_telegram "[Argus] 📊 Progress: ${offset}/287 processed. ${total_researched} researched, ${total_skipped} skipped (already SAP), ${total_failed} failed."
    fi
  done

  # --- TIER 3: Git commit + push (triggers Vercel auto-deploy) ---
  log "--- Committing any local changes ---"
  cd ~/Projects/master-crm-web
  if [ -n "$(git status --porcelain)" ]; then
    git add -A
    git commit -m "Overnight research: ${total_researched} companies enriched to SAP quality

Co-Authored-By: OpenClaw Researcher <noreply@openclaw.ai>" 2>>"$LOG_FILE" || true
    git push origin main 2>>"$LOG_FILE" || true
    log "✅ Pushed to GitHub — Vercel will auto-deploy"
  else
    log "No local file changes to commit"
  fi

  # --- Final report ---
  local summary="[Argus] 🌅 Overnight research COMPLETE.
• Researched: ${total_researched}
• Already SAP: ${total_skipped}
• Failed: ${total_failed}
• Supabase: updated directly
• Vercel: auto-deploying from git push
Check the site: https://master-crm-web-eight.vercel.app"

  send_telegram "$summary"
  log "$summary"
  log "============================================"
  log "OVERNIGHT RESEARCH — COMPLETE"
  log "============================================"
}

main "$@"
