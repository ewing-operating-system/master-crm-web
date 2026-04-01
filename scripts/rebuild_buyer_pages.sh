#!/bin/bash
# Credentials: all keys come from env vars (inherited from ~/.zshrc).
# See .env.example for variable names. NEVER hardcode keys in scripts.
# =============================================================================
# BUYER PAGE REBUILD ORCHESTRATOR
# Sends each problem page to a Claude Code agent via openclaw coding-agent
# to research the buyer, rebuild the page, and deploy to Vercel.
#
# Usage: bash ~/Projects/master-crm-web/scripts/rebuild_buyer_pages.sh
# =============================================================================

set -euo pipefail

PROJ_DIR="$HOME/Projects/master-crm-web"
PUBLIC_DIR="$PROJ_DIR/public"
LOG_DIR="$PROJ_DIR/logs/rebuild"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
MANIFEST="$LOG_DIR/manifest_${TIMESTAMP}.json"
SUMMARY_LOG="$LOG_DIR/summary_${TIMESTAMP}.log"
MAX_PARALLEL=3
ACTIVE_PIDS=()

mkdir -p "$LOG_DIR"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[REBUILD]${NC} $(date +%H:%M:%S) $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $(date +%H:%M:%S) $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $(date +%H:%M:%S) $1"; }
info() { echo -e "${CYAN}[INFO]${NC} $(date +%H:%M:%S) $1"; }

# ─────────────────────────────────────────────────────────────────────────────
# PROBLEM PAGE MANIFEST
# Each entry: entity|filename|issue_type|priority|context
# ─────────────────────────────────────────────────────────────────────────────

declare -a PAGES=()

# --- AIR CONTROL: Approach-only stubs (need full buyer profiles) ---
AC_STUBS=(
  "air-control_4front-solutions-court-square.html"
  "air-control_alpine-investors.html"
  "air-control_american-residential-services-gi-partners.html"
  "air-control_authority-brands-apax-partners.html"
  "air-control_bernhard-capital-partners.html"
  "air-control_comfort-systems-usa.html"
  "air-control_coolsys-ares-management.html"
  "air-control_emcor-group.html"
  "air-control_encompass-home-services.html"
  "air-control_flow-control-group-partners-group.html"
  "air-control_grey-mountain-partners.html"
  "air-control_gridiron-capital.html"
  "air-control_haller-enterprises.html"
  "air-control_home-alliance-conduit-capital.html"
  "air-control_homeserve-usa-brookfield.html"
  "air-control_huron-capital.html"
  "air-control_lee-equity-partners.html"
  "air-control_msouth-equity-partners.html"
  "air-control_neighborly-kkr.html"
  "air-control_norair-engineering.html"
  "air-control_peterman-brothers-roark-capital.html"
  "air-control_redwood-services.html"
  "air-control_service-logic-leonard-green.html"
  "air-control_sila-services.html"
  "air-control_therma-eqt-partners.html"
  "air-control_turnpoint-services-kohlberg.html"
)
for f in "${AC_STUBS[@]}"; do
  PAGES+=("air-control|$f|stub_rebuild|P2|HVAC buyer for Air Control (McLean VA)")
done

# Air Control: Raw dump pages needing cleanup + research
AC_DUMPS=(
  "air-control_ally-services.html"
  "air-control_apex-service-partners.html"
  "air-control_horizon-services.html"
  "air-control_service-experts.html"
  "air-control_wrench-group.html"
  "air-control_f-h-furr-plumbing-heating-ac-electrical.html"
)
for f in "${AC_DUMPS[@]}"; do
  PAGES+=("air-control|$f|raw_dump_fix|P2|HVAC buyer - strip markdown, add contacts/pipeline")
done

# --- SPRINGER FLOOR: Full rebuilds (raw scraper dumps) ---
SF_REBUILDS=(
  "springer-floor_abm-industries.html"
  "springer-floor_aftermath-services-kinderhook.html"
  "springer-floor_anago-cleaning-systems.html"
  "springer-floor_ati-restoration.html"
  "springer-floor_belfor-holdings.html"
  "springer-floor_blusky-restoration.html"
  "springer-floor_building-services-of-america-bsa.html"
  "springer-floor_centre-partners.html"
  "springer-floor_chem-dry-international.html"
  "springer-floor_cintas-corporation.html"
  "springer-floor_city-wide-facility-solutions.html"
  "springer-floor_coit-cleaning-and-restoration.html"
  "springer-floor_compass-group-eurest-services.html"
  "springer-floor_corvus-janitorial.html"
  "springer-floor_coverall-north-america.html"
  "springer-floor_firstservice-brands.html"
  "springer-floor_gi-partners.html"
  "springer-floor_guardian-restoration-partners.html"
  "springer-floor_h-i-g-capital.html"
  "springer-floor_harvard-maintenance.html"
  "springer-floor_heartland-home-services.html"
  "springer-floor_heaven-s-best-carpet-cleaning.html"
  "springer-floor_incline-equity-partners.html"
  "springer-floor_jan-pro-cleaning-disinfecting.html"
  "springer-floor_kellermeyer-bergensons-services-kbs.html"
  "springer-floor_kinderhook-industries.html"
  "springer-floor_marsden-holding.html"
  "springer-floor_nexclean.html"
  "springer-floor_openworks.html"
  "springer-floor_oxi-fresh-carpet-cleaning.html"
  "springer-floor_paul-davis-restoration.html"
  "springer-floor_premium-service-brands.html"
  "springer-floor_pritchard-industries.html"
  "springer-floor_quickdry-pro.html"
  "springer-floor_rainbow-international-neighborly-kkr.html"
  "springer-floor_rainier-partners.html"
  "springer-floor_restoration-1.html"
  "springer-floor_roark-capital-servicemaster-brands.html"
  "springer-floor_seacoast-capital.html"
  "springer-floor_servpro-industries.html"
  "springer-floor_stanley-steemer.html"
  "springer-floor_summit-park.html"
  "springer-floor_the-riverside-company-millicare.html"
  "springer-floor_vanguard-cleaning-systems.html"
  "springer-floor_puroclean.html"
  "springer-floor_zerorez.html"
)
for f in "${SF_REBUILDS[@]}"; do
  PAGES+=("springer-floor|$f|full_rebuild|P1|Floor care/cleaning buyer for Springer Floor (Des Moines IA)")
done

# --- AQUASCIENCE: Empty shells + raw dumps + thin profiles ---
AQ_EMPTY=(
  "aquascience_culligan-international.html"
  "aquascience_bdt-msd-partners.html"
  "aquascience_pentair.html"
)
for f in "${AQ_EMPTY[@]}"; do
  PAGES+=("aquascience|$f|empty_shell|P1|Water treatment buyer - HIGHEST FIT, completely empty")
done

AQ_DUMPS=(
  "aquascience_grundfos.html"
  "aquascience_advent-international.html"
  "aquascience_essential-utilities-aqua-america.html"
)
for f in "${AQ_DUMPS[@]}"; do
  PAGES+=("aquascience|$f|raw_dump_fix|P1|Water treatment buyer - raw markdown + wrong company data")
done

AQ_THIN=(
  "aquascience_aligned-climate-capital.html"
  "aquascience_american-water-works-company.html"
  "aquascience_arcadis.html"
  "aquascience_bernhard-capital-partners.html"
  "aquascience_blue-water-industries.html"
  "aquascience_capstone-partners-advisory-lead.html"
  "aquascience_centre-partners.html"
  "aquascience_evoqua-water-technologies-xylem.html"
  "aquascience_h2o-innovation.html"
  "aquascience_harcros-chemicals.html"
  "aquascience_kelso-company.html"
  "aquascience_kinetico-incorporated.html"
  "aquascience_kkr-water-infrastructure.html"
  "aquascience_kurita-water-industries.html"
  "aquascience_leonard-green-partners.html"
  "aquascience_nautic-partners.html"
  "aquascience_platinum-equity.html"
  "aquascience_pureflow-inc.html"
  "aquascience_shv-holdings.html"
  "aquascience_solenis.html"
  "aquascience_southwest-water-company.html"
  "aquascience_suez-water-technologies.html"
  "aquascience_the-mclean-group.html"
  "aquascience_us-water-services-alaris-capital-partners.html"
  "aquascience_veolia-north-america.html"
  "aquascience_waterlogic-castik-capital.html"
  "aquascience_watts-water-technologies.html"
  "aquascience_whitewater-management.html"
  "aquascience_wind-point-partners.html"
)
for f in "${AQ_THIN[@]}"; do
  PAGES+=("aquascience|$f|add_sections|P2|Water treatment buyer - has profile, needs contacts/pipeline/opener")
done

# --- DESIGN PRECAST: Stubs needing full build ---
DP_STUBS=(
  "design-precast-pipe-inc_alfred-miller-precast.html"
  "design-precast-pipe-inc_coastal-precast-systems.html"
  "design-precast-pipe-inc_delta-industries-gulf-coast-division.html"
  "design-precast-pipe-inc_georgialina-precast.html"
  "design-precast-pipe-inc_permatile-concrete-products.html"
  "design-precast-pipe-inc_si-precast-concrete.html"
  "design-precast-pipe-inc_southern-precast-morvant-precast.html"
  "design-precast-pipe-inc_the-concrete-company.html"
  "design-precast-pipe-inc_the-shaddix-company.html"
)
for f in "${DP_STUBS[@]}"; do
  PAGES+=("design-precast|$f|stub_rebuild|P2|Precast concrete target for Design Precast (Biloxi MS)")
done

# --- WIESER: Stub buyer dossiers (wrong template) ---
WC_STUBS=(
  "wieser-concrete-products-inc_brown-precast.html"
  "wieser-concrete-products-inc_diamond-precast-llc.html"
  "wieser-concrete-products-inc_encore-precast.html"
  "wieser-concrete-products-inc_engineered-concrete-products-ecp.html"
  "wieser-concrete-products-inc_fairfield-precast-concrete.html"
  "wieser-concrete-products-inc_indianola-precast-concrete.html"
  "wieser-concrete-products-inc_kersten-precast-concrete-llc.html"
  "wieser-concrete-products-inc_mid-states-concrete-industries.html"
  "wieser-concrete-products-inc_panhandle-concrete-products.html"
  "wieser-concrete-products-inc_wilkinson-precast-inc.html"
)
for f in "${WC_STUBS[@]}"; do
  PAGES+=("wieser|$f|stub_rebuild|P3|Precast acquisition target for Wieser Concrete (Maiden Rock WI)")
done

TOTAL=${#PAGES[@]}
log "Manifest built: $TOTAL pages to rebuild"

# ─────────────────────────────────────────────────────────────────────────────
# ENTITY CONTEXT (passed to each agent for correct framing)
# ─────────────────────────────────────────────────────────────────────────────

get_entity_context() {
  local entity="$1"
  case "$entity" in
    air-control)
      echo "Air Control is a residential/commercial HVAC company based in McLean, Virginia. Owner is looking for potential buyers — these are SELL-SIDE buyer dossiers. Each page profiles a potential acquirer of Air Control. The page should explain who the buyer is, their M&A track record, why they'd want Air Control, key contacts, and a specific call opener."
      ;;
    springer-floor)
      echo "Springer Floor Care is a floor care and carpet cleaning company in Des Moines, Iowa. Owners: Terri (68) and Eddie Holman (70), ready to retire. ~\$900K revenue, Forever Kleen product line, 26-city Iowa footprint, Eddie is IICRC instructor. These are SELL-SIDE buyer dossiers profiling potential acquirers."
      ;;
    aquascience)
      echo "AquaScience is a water treatment company. Owner: Lawrence 'Larry' Casey. These are SELL-SIDE buyer dossiers profiling potential acquirers in the water treatment, water infrastructure, and environmental services space."
      ;;
    design-precast)
      echo "Design Precast & Pipe, Inc. is a precast concrete and pipe manufacturer in Biloxi, Mississippi. Owner: Pat Fore III (Founder/President). These are BUY-SIDE acquisition targets — companies Design Precast wants to acquire. Each page should profile the target company, its products, location, ownership, strategic fit for acquisition."
      ;;
    wieser)
      echo "Wieser Concrete Products, Inc. is a precast concrete manufacturer in Maiden Rock, Wisconsin. Owner: Andy Wieser (3rd generation, est. 1963). These are BUY-SIDE acquisition targets — companies Wieser wants to acquire to expand their Midwest precast footprint."
      ;;
  esac
}

# ─────────────────────────────────────────────────────────────────────────────
# GOLD STANDARD TEMPLATE (from Jarrett page — the best example)
# ─────────────────────────────────────────────────────────────────────────────

TEMPLATE_INSTRUCTIONS='
Use the EXACT same HTML structure, CSS styles, and section pattern as the existing page.
Keep the existing CSS in <style> tags, the nav bar (nc-nav), and footer scripts intact.

Required sections (in order):
1. HEADER: Company name, subtitle (location, industry), score badge (1-10, green=#27ae60 for 7+, orange=#f39c12 for 4-6, red=#e74c3c for 1-3)
2. CONTEXT BAR: Entity name, owner name, status badge
3. BUYER/COMPANY PROFILE card: Real facts — HQ, founded, ownership, revenue range, employees, M&A history, products/services. Use <table> or <ul>, NOT raw paragraphs.
4. CONTACTS card: <table> with columns: Name, Title, Email, Notes. Research real names. If email unknown, leave "—" (do NOT fabricate).
5. STRATEGIC FIT card: narrative-box div. Write 3-4 paragraphs explaining WHY this buyer/target fits. Be specific — reference geography, deal history, capabilities overlap.
6. APPROACH STRATEGY card: 3 numbered talking points for a cold call. Each must reference a SPECIFIC fact (deal name, date, person, number). Never use generic "We noticed your activity in X" boilerplate.
7. PIPELINE HISTORY card: <table> with columns: Step, Status (badge), Date. At minimum: Target Identified (Complete), Research Complete (Complete, Mar 2026), Outreach Pending (Next Step).

CRITICAL RULES:
- NO raw markdown (##, ###, ---, |---|) in HTML
- NO scraped website navigation, cookie banners, ad tags, or login walls
- NO wrong-company data (verify company names match)
- NO generic boilerplate call openers
- NO fabricated emails or phone numbers
- Revenue displayed as "$3M" not "3000000.0"
- All content must be about the CORRECT company
- Use the dark theme (bg: #0d1117, cards: #161b22, accent: #58a6ff) unless the existing page uses a different theme — then match it
'

# ─────────────────────────────────────────────────────────────────────────────
# REBUILD FUNCTION (sends one page to Claude Code)
# ─────────────────────────────────────────────────────────────────────────────

rebuild_page() {
  local entry="$1"
  local entity=$(echo "$entry" | cut -d'|' -f1)
  local filename=$(echo "$entry" | cut -d'|' -f2)
  local issue_type=$(echo "$entry" | cut -d'|' -f3)
  local priority=$(echo "$entry" | cut -d'|' -f4)
  local context=$(echo "$entry" | cut -d'|' -f5)
  local filepath="$PUBLIC_DIR/$filename"
  local logfile="$LOG_DIR/${filename%.html}_${TIMESTAMP}.log"
  local entity_context
  entity_context=$(get_entity_context "$entity")

  # Build the prompt
  local prompt="You are rebuilding a buyer/target dossier page for a CRM system.

ENTITY CONTEXT: ${entity_context}

COMPANY CONTEXT: ${context}

FILE TO REBUILD: ${filepath}

ISSUE: ${issue_type} — "

  case "$issue_type" in
    stub_rebuild)
      prompt+="This page is a stub with only 1-2 cards. It needs a complete rebuild with all required sections."
      ;;
    full_rebuild)
      prompt+="This page has raw scraper output dumped into HTML. It may contain wrong-company data, scraped nav elements, cookie banners, and markdown artifacts. Strip ALL of that and rebuild with real, verified content."
      ;;
    raw_dump_fix)
      prompt+="This page has raw markdown rendering as visible text, scraped artifacts, and possibly wrong-company data. Clean it up, add missing sections."
      ;;
    empty_shell)
      prompt+="This page has a header but ZERO content in the body. Build the complete page from scratch."
      ;;
    add_sections)
      prompt+="This page has a buyer profile but is missing: contacts table, strategic fit card, pipeline history, and approach strategy. Add all missing sections. Keep the existing profile content if it's accurate."
      ;;
  esac

  prompt+="

INSTRUCTIONS:
${TEMPLATE_INSTRUCTIONS}

RESEARCH: Use web search (DuckDuckGo) to find current information about this company. Look for:
- Company website, about page
- Recent acquisitions or M&A activity
- Key executives (CEO, VP of M&A, CFO)
- Revenue estimates, employee count
- Geographic coverage
- News articles about the company

Read the existing file first, then rewrite it completely with real researched content. Write the final HTML directly to the file using the Write tool. Do NOT ask for confirmation — just do it."

  info "Starting: $filename ($issue_type)"

  # Use claude with --print mode — runs on Claude Code subscription (no extra API cost)
  claude -p "$prompt" \
    --permission-mode bypassPermissions \
    --model sonnet \
    > "$logfile" 2>&1

  local exit_code=$?

  if [ $exit_code -eq 0 ]; then
    # Check if the file was actually modified
    if [ -f "$filepath" ]; then
      local size=$(wc -c < "$filepath")
      if [ "$size" -gt 2000 ]; then
        log "✓ $filename — rebuilt ($size bytes)"
        echo "OK|$filename|$size" >> "$SUMMARY_LOG"
        return 0
      else
        warn "⚠ $filename — file too small ($size bytes), may not have been rebuilt"
        echo "WARN|$filename|$size|too_small" >> "$SUMMARY_LOG"
        return 1
      fi
    fi
  fi

  fail "✗ $filename — agent exited $exit_code"
  echo "FAIL|$filename|exit_$exit_code" >> "$SUMMARY_LOG"
  return 1
}

# ─────────────────────────────────────────────────────────────────────────────
# PARALLEL EXECUTION WITH THROTTLE
# ─────────────────────────────────────────────────────────────────────────────

wait_for_slot() {
  while [ ${#ACTIVE_PIDS[@]} -ge $MAX_PARALLEL ]; do
    local new_pids=()
    for pid in "${ACTIVE_PIDS[@]}"; do
      if kill -0 "$pid" 2>/dev/null; then
        new_pids+=("$pid")
      fi
    done
    ACTIVE_PIDS=("${new_pids[@]}")
    if [ ${#ACTIVE_PIDS[@]} -ge $MAX_PARALLEL ]; then
      sleep 2
    fi
  done
}

# ─────────────────────────────────────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────────────────────────────────────

log "=========================================="
log "  BUYER PAGE REBUILD — $TOTAL pages"
log "  Parallel: $MAX_PARALLEL at a time"
log "  Log dir: $LOG_DIR"
log "=========================================="
echo ""

COMPLETED=0
FAILED=0

# Sort by priority (P1 first)
IFS=$'\n' SORTED=($(printf '%s\n' "${PAGES[@]}" | sort -t'|' -k4))

for entry in "${SORTED[@]}"; do
  wait_for_slot

  rebuild_page "$entry" &
  ACTIVE_PIDS+=($!)

  # Small delay to avoid API rate limiting
  sleep 3
done

# Wait for all remaining
for pid in "${ACTIVE_PIDS[@]}"; do
  wait "$pid" 2>/dev/null || true
done

# ─────────────────────────────────────────────────────────────────────────────
# DEPLOY AND REPORT
# ─────────────────────────────────────────────────────────────────────────────

echo ""
log "=========================================="
log "  ALL AGENTS COMPLETE — DEPLOYING"
log "=========================================="

cd "$PROJ_DIR"
npx vercel --prod --yes 2>&1 | grep -i "ready\|production" || warn "Vercel deploy may have issues"

echo ""
log "=========================================="
log "  FINAL REPORT"
log "=========================================="

if [ -f "$SUMMARY_LOG" ]; then
  OK_COUNT=$(grep -c "^OK|" "$SUMMARY_LOG" 2>/dev/null || echo 0)
  WARN_COUNT=$(grep -c "^WARN|" "$SUMMARY_LOG" 2>/dev/null || echo 0)
  FAIL_COUNT=$(grep -c "^FAIL|" "$SUMMARY_LOG" 2>/dev/null || echo 0)

  log "Rebuilt successfully: $OK_COUNT"
  warn "Warnings: $WARN_COUNT"
  fail "Failed: $FAIL_COUNT"

  if [ "$FAIL_COUNT" -gt 0 ]; then
    echo ""
    fail "Failed pages:"
    grep "^FAIL|" "$SUMMARY_LOG" | while IFS='|' read -r status file reason; do
      echo "  - $file ($reason)"
    done
  fi
else
  warn "No summary log found — check individual logs in $LOG_DIR"
fi

echo ""
log "Logs: $LOG_DIR"
log "Summary: $SUMMARY_LOG"
log "Done."
