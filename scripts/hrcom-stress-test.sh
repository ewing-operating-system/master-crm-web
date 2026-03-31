#!/bin/bash
# ============================================================
# HR.COM DEAL — OVERNIGHT STRESS TEST + AGENT TOURNAMENT
# Benchmarks, scores, re-enriches, and ranks every agent
# Launches overnight build (hrcom-overnight-build.sh) as Phase 5
# Budget: $100 | Claude usage: ZERO | All OpenClaw agents
# Run: bash ~/Projects/master-crm-web/scripts/hrcom-stress-test.sh
# ============================================================

set -uo pipefail
# NOTE: -e removed intentionally — we handle errors per-phase with || true

# --- Config ---
PROJECT_DIR="$HOME/Projects/master-crm-web"
OUTPUT_DIR="$PROJECT_DIR/outputs/stress-test"
LOG_FILE="$PROJECT_DIR/scripts/hrcom-stress-test.log"
SLEEP_BETWEEN=8
BUDGET_TOTAL=100.00
BUDGET_SPENT=0
BUDGET_REMAINING=100.00
EXA_COST_PER_SEARCH=0.75  # conservative estimate
RUN_ID=""
PHASE_START=0

# Load env vars without interactive zsh features
export $(grep -E '^export ' ~/.zshrc 2>/dev/null | sed 's/^export //' | grep -v '#' | xargs) 2>/dev/null || true
source ~/.openclaw/.env 2>/dev/null || true

SB_URL="${SUPABASE_URL}/rest/v1"
SB_KEY="$SUPABASE_SERVICE_ROLE_KEY"
SB_HEADERS=(-H "apikey: $SB_KEY" -H "Authorization: Bearer $SB_KEY" -H "Content-Type: application/json" -H "Prefer: return=representation")

# --- Helpers ---
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"; }
send_telegram() { openclaw message send --channel telegram --target "$EWING_TELEGRAM_CHAT_ID" --message "$1" 2>/dev/null || true; }

check_budget() {
  BUDGET_REMAINING=$(echo "$BUDGET_TOTAL - $BUDGET_SPENT" | bc)
  local cmp=$(echo "$BUDGET_REMAINING < 5" | bc)
  if [ "$cmp" = "1" ]; then
    log "⚠️ BUDGET GATE: \$${BUDGET_REMAINING} remaining (< \$5). Skipping to rankings."
    send_telegram "[Argus] ⚠️ Budget gate hit at \$${BUDGET_SPENT} spent. Skipping to Phase 6-8 for rankings."
    return 1
  fi
  return 0
}

track_cost() {
  local cost="$1"
  BUDGET_SPENT=$(echo "$BUDGET_SPENT + $cost" | bc)
  BUDGET_REMAINING=$(echo "$BUDGET_TOTAL - $BUDGET_SPENT" | bc)
}

sb_post() {
  local table="$1"
  local data="$2"
  curl -s "${SB_URL}/${table}" "${SB_HEADERS[@]}" -d "$data" 2>/dev/null
}

sb_patch() {
  local table="$1"
  local filter="$2"
  local data="$3"
  curl -s -X PATCH "${SB_URL}/${table}?${filter}" "${SB_HEADERS[@]}" -d "$data" 2>/dev/null
}

# --- Direct DeepSeek API call (bypasses broken OpenRouter) ---
deepseek_call() {
  local prompt="$1"
  local max_tokens="${2:-4000}"
  local temp="${3:-0.4}"

  curl -s https://api.deepseek.com/chat/completions \
    -H "Authorization: Bearer ${DEEPSEEK_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "{
      \"model\": \"deepseek-chat\",
      \"messages\": [{\"role\": \"user\", \"content\": $(python3 -c "import json; print(json.dumps('''$prompt'''[:12000]))")}],
      \"max_tokens\": $max_tokens,
      \"temperature\": $temp
    }" 2>/dev/null
}

# --- Agent call with full performance tracking (DeepSeek direct) ---
run_agent_tracked() {
  local agent_type="$1"
  local task_type="$2"
  local task_id="$3"
  local output_file="$4"
  local message="$5"
  local timeout="${6:-600}"
  local prompt_variant="${7:-default}"
  local tournament_group="${8:-}"

  local start_time=$(date +%s)
  local input_size=${#message}
  local model_name="deepseek-chat"

  log "  [$agent_type] $task_type: $task_id"

  # Write message to temp file to avoid shell escaping issues
  local tmpfile=$(mktemp)
  echo "$message" > "$tmpfile"

  local raw_response
  raw_response=$(python3 -c "
import json, requests, sys

prompt = open('$tmpfile').read()[:12000]

try:
    resp = requests.post('https://api.deepseek.com/chat/completions',
        headers={'Authorization': 'Bearer ${DEEPSEEK_API_KEY}', 'Content-Type': 'application/json'},
        json={'model': 'deepseek-chat', 'messages': [{'role': 'user', 'content': prompt}], 'max_tokens': 4000, 'temperature': 0.4},
        timeout=120
    )
    data = resp.json()
    content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
    usage = data.get('usage', {})
    in_tok = usage.get('prompt_tokens', 0)
    out_tok = usage.get('completion_tokens', 0)
    # DeepSeek pricing: \$0.27/M input, \$1.10/M output
    cost = (in_tok * 0.27 + out_tok * 1.10) / 1000000
    print(json.dumps({'content': content, 'in_tok': in_tok, 'out_tok': out_tok, 'cost': round(cost, 6), 'ok': True}))
except Exception as e:
    print(json.dumps({'content': '', 'in_tok': 0, 'out_tok': 0, 'cost': 0, 'ok': False, 'error': str(e)}))
" 2>/dev/null)

  rm -f "$tmpfile"

  local ok=$(echo "$raw_response" | python3 -c "import json,sys; print(json.load(sys.stdin).get('ok', False))" 2>/dev/null || echo "False")

  if [ "$ok" = "True" ]; then
    local content=$(echo "$raw_response" | python3 -c "import json,sys; print(json.load(sys.stdin).get('content',''))" 2>/dev/null)
    local cost=$(echo "$raw_response" | python3 -c "import json,sys; print(json.load(sys.stdin).get('cost',0))" 2>/dev/null)
    local in_tok=$(echo "$raw_response" | python3 -c "import json,sys; print(json.load(sys.stdin).get('in_tok',0))" 2>/dev/null)
    local out_tok=$(echo "$raw_response" | python3 -c "import json,sys; print(json.load(sys.stdin).get('out_tok',0))" 2>/dev/null)

    echo "$content" > "$output_file"
    local elapsed=$(( $(date +%s) - start_time ))
    local output_size=${#content}

    track_cost "$cost"

    # Log to Supabase
    sb_post "agent_performance_log" "{
      \"run_id\":\"$RUN_ID\",\"agent_id\":\"$agent_type\",\"agent_model\":\"$model_name\",
      \"task_type\":\"$task_type\",\"task_id\":\"$task_id\",
      \"input_size_chars\":$input_size,\"output_size_chars\":$output_size,
      \"output_usable\":true,\"cost_usd\":$cost,\"duration_seconds\":$elapsed,
      \"prompt_variant\":\"$prompt_variant\",
      \"tournament_group\":$([ -n "$tournament_group" ] && echo "\"$tournament_group\"" || echo "null")
    }" > /dev/null 2>&1

    log "  ✅ $task_id (${elapsed}s, ${in_tok}→${out_tok} tok, \$${cost})"
    return 0
  else
    log "  ❌ FAILED: $task_id — retrying..."
    sleep 15

    # Retry once
    local tmpfile2=$(mktemp)
    echo "$message" > "$tmpfile2"
    raw_response=$(python3 -c "
import json, requests
prompt = open('$tmpfile2').read()[:12000]
try:
    resp = requests.post('https://api.deepseek.com/chat/completions',
        headers={'Authorization': 'Bearer ${DEEPSEEK_API_KEY}', 'Content-Type': 'application/json'},
        json={'model': 'deepseek-chat', 'messages': [{'role': 'user', 'content': prompt}], 'max_tokens': 4000, 'temperature': 0.4},
        timeout=120
    )
    data = resp.json()
    content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
    usage = data.get('usage', {})
    cost = (usage.get('prompt_tokens',0) * 0.27 + usage.get('completion_tokens',0) * 1.10) / 1000000
    print(json.dumps({'content': content, 'cost': round(cost,6), 'ok': True}))
except Exception as e:
    print(json.dumps({'content': '', 'cost': 0, 'ok': False, 'error': str(e)}))
" 2>/dev/null)
    rm -f "$tmpfile2"

    ok=$(echo "$raw_response" | python3 -c "import json,sys; print(json.load(sys.stdin).get('ok', False))" 2>/dev/null || echo "False")
    if [ "$ok" = "True" ]; then
      echo "$raw_response" | python3 -c "import json,sys; print(json.load(sys.stdin).get('content',''))" > "$output_file" 2>/dev/null
      local cost=$(echo "$raw_response" | python3 -c "import json,sys; print(json.load(sys.stdin).get('cost',0))" 2>/dev/null)
      track_cost "$cost"
      local elapsed=$(( $(date +%s) - start_time ))
      log "  ✅ $task_id (retry OK, ${elapsed}s, \$${cost})"
      return 0
    fi

    log "  ❌ FAILED TWICE: $task_id"
    echo "FAILED" > "$output_file"
    return 1
  fi
}

# --- Exa search with cost tracking ---
exa_search_tracked() {
  local query="$1"
  local output_file="$2"
  local task_id="${3:-exa-search}"
  local num_results="${4:-5}"

  check_budget || return 1

  local start_time=$(date +%s)

  curl -s "https://api.exa.ai/search" \
    -H "x-api-key: $EXA_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{
      \"query\": $(python3 -c "import json; print(json.dumps(\"$query\"))"),
      \"numResults\": $num_results,
      \"type\": \"auto\",
      \"contents\": {\"text\": {\"maxCharacters\": 3000}, \"highlights\": true}
    }" > "$output_file" 2>/dev/null

  local elapsed=$(( $(date +%s) - start_time ))
  local count=$(python3 -c "import json; d=json.load(open('$output_file')); print(len(d.get('results',[])))" 2>/dev/null || echo "0")

  track_cost "$EXA_COST_PER_SEARCH"

  sb_post "agent_performance_log" "{
    \"run_id\":\"$RUN_ID\",\"agent_id\":\"exa-api\",\"agent_model\":\"exa-search\",
    \"task_type\":\"exa_search\",\"task_id\":\"$task_id\",
    \"input_size_chars\":${#query},\"output_size_chars\":$(wc -c < "$output_file" 2>/dev/null || echo 0),
    \"output_usable\":$([ "$count" -gt 0 ] && echo "true" || echo "false"),
    \"cost_usd\":$EXA_COST_PER_SEARCH,\"duration_seconds\":$elapsed,
    \"exa_searches_used\":1
  }" > /dev/null

  log "  Exa: '$query' → $count results (${elapsed}s, \$$EXA_COST_PER_SEARCH)"
}

# ============================================================
# PHASE 0: PREFLIGHT
# ============================================================
phase0_preflight() {
  log "=========================================="
  log "PHASE 0: PREFLIGHT"
  log "=========================================="

  mkdir -p "$OUTPUT_DIR"/{lovable,tournament,reports}

  # Run migration via psycopg2 (direct DB connection)
  log "  Running Supabase migration via psycopg2..."
  python3 -c "
import psycopg2, os
conn = psycopg2.connect(os.environ.get('DATABASE_URL', '$DATABASE_URL'))
conn.autocommit = True
cur = conn.cursor()
# Check if tables exist already
cur.execute(\"SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename='stress_test_runs'\")
if cur.fetchone():
    print('Tables already exist — skipping migration')
else:
    print('Creating tables...')
    # Read and execute migration (tables created individually to avoid semicolon splitting issues)
    tables_sql = open('$PROJECT_DIR/migrations/004_stress_test_tables.sql').read()
    cur.execute(tables_sql)
    print('Migration complete')
cur.close()
conn.close()
" 2>>"$LOG_FILE" || log "  ⚠️ Migration failed — tables may already exist, continuing..."

  # Create run record
  local run_result
  run_result=$(sb_post "stress_test_runs" "{
    \"run_name\":\"stress-test-$(date +%Y%m%d-%H%M)\",
    \"status\":\"running\",
    \"budget_total\":$BUDGET_TOTAL,
    \"config\":{\"exa_cost_est\":$EXA_COST_PER_SEARCH,\"tournament_size\":12}
  }")

  RUN_ID=$(echo "$run_result" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['id'] if isinstance(d,list) else d.get('id',''))" 2>/dev/null || echo "")

  if [ -z "$RUN_ID" ]; then
    log "  ⚠️ Could not create run record — using local tracking only"
    RUN_ID="local-$(date +%s)"
  fi

  log "  Run ID: $RUN_ID"
  log "  Budget: \$${BUDGET_TOTAL}"

  # Count buyer pages
  local buyer_count=$(ls "$PROJECT_DIR/public/hr-com-ltd_"*.html 2>/dev/null | wc -l | tr -d ' ')
  log "  Buyer pages found: $buyer_count"

  log "  PHASE 0 COMPLETE"
}

# ============================================================
# PHASE 1: SCRAPE LOVABLE BENCHMARK
# ============================================================
phase1_benchmark() {
  log "=========================================="
  log "PHASE 1: LOVABLE BENCHMARK"
  log "=========================================="

  # Scrape dealroom pages via Exa
  local pages=("debbiedealroom.com" "debbiedealroom.com overview" "debbiedealroom.com team" "debbiedealroom.com process" "debbiedealroom.com engagement options")

  for page in "${pages[@]}"; do
    local slug=$(echo "$page" | sed 's/ /-/g; s/debbiedealroom.com/dealroom/')
    exa_search_tracked "site:$page" "$OUTPUT_DIR/lovable/exa-$slug.json" "lovable-$slug" 3
    sleep 3
  done

  # Build quality rubric from scraped data
  local lovable_context=""
  for f in "$OUTPUT_DIR/lovable/"*.json; do
    local page_data=$(python3 -c "
import json
try:
    d = json.load(open('$f'))
    for r in d.get('results',[])[:2]:
        print(r.get('title',''), '---', r.get('text','')[:800])
except: pass
" 2>/dev/null)
    lovable_context+="$page_data
"
  done

  # Also load the gold standard buyer page for comparison
  local gold_page=$(python3 -c "
import re
html = open('$PROJECT_DIR/public/hr-com-ltd_accenture.html').read()
text = re.sub(r'<[^>]+>', ' ', html)
text = re.sub(r'\s+', ' ', text).strip()
print(text[:6000])
" 2>/dev/null)

  run_agent_tracked "auditor" "build_rubric" "lovable-rubric" "$OUTPUT_DIR/lovable/scoring-rubric.json" "
You are building a quality scoring rubric for M&A buyer research pages. You have two reference points:

REFERENCE A — LOVABLE DEALROOM (debbiedealroom.com):
This is a well-designed deal room with strong narrative quality, operator tone, strategic structure.
Content scraped:
$lovable_context

REFERENCE B — GOLD STANDARD BUYER PAGE (Accenture):
This is our best buyer research page with deep CEO quotes, 5 golden nugget call openers, earnings data, verified contacts.
Content:
$gold_page

BUILD A JSON SCORING RUBRIC with these 6 dimensions, each scored 0-10:

1. narrative_quality: Writing quality, specificity, operator tone. 10 = Lovable's strategic narrative + Accenture's research depth combined. 0 = generic, vague, template-sounding.

2. strategic_depth: Number of distinct acquisition angles with evidence. 10 = 4+ angles each backed by CEO quotes or financial data. 0 = one generic angle.

3. evidence_density: Hard data count. 10 = 8+ CEO quotes with dates, dollar amounts, specific deal references. 0 = no quotes, no numbers.

4. actionability: Ready-to-use call scripts, email openers, verified contacts. 10 = 5 golden nuggets + 5 verified contacts with LinkedIn + approach strategy. 0 = no scripts, empty contacts.

5. completeness: All sections present (strategic fit, golden nuggets, CEO vision, M&A appetite, challenges, earnings quotes, contacts, approach). 10 = all 8 sections with substantive content. 0 = missing multiple sections.

6. structure: Proper card layout, content density, section balance. 10 = balanced sections, good information hierarchy. 0 = wall of text or mostly empty.

For each dimension, provide:
- description: what this measures
- score_10_example: what a 10 looks like (reference specific content)
- score_5_example: what a 5 looks like
- score_1_example: what a 1 looks like
- weight: the dimension weight (narrative=0.25, strategic=0.20, evidence=0.20, actionability=0.15, completeness=0.10, structure=0.10)

Return as valid JSON with a 'rubric' object containing 6 dimension objects.
" 600

  log "  PHASE 1 COMPLETE — rubric built"
  send_telegram "[Argus] Phase 1: Lovable benchmark scraped, scoring rubric built. Budget: \$${BUDGET_SPENT}/\$${BUDGET_TOTAL}. Starting page scoring."
}

# ============================================================
# PHASE 2: SCORE ALL 68 BUYER PAGES
# ============================================================
phase2_score_pages() {
  log "=========================================="
  log "PHASE 2: SCORE ALL BUYER PAGES"
  log "=========================================="

  local rubric=""
  if [ -f "$OUTPUT_DIR/lovable/scoring-rubric.json" ]; then
    rubric=$(cat "$OUTPUT_DIR/lovable/scoring-rubric.json" | head -200)
  fi

  # Get all buyer pages
  local pages=($(ls "$PROJECT_DIR/public/hr-com-ltd_"*.html 2>/dev/null))
  local total=${#pages[@]}
  local scored=0
  local batch_size=3

  log "  Scoring $total buyer pages in batches of $batch_size..."

  for ((i=0; i<total; i+=batch_size)); do
    local batch_pids=()

    for ((j=0; j<batch_size && i+j<total; j++)); do
      local page_file="${pages[$((i+j))]}"
      local slug=$(basename "$page_file" .html | sed 's/hr-com-ltd_//')
      local buyer_name=$(python3 -c "
import re
html = open('$page_file').read()
m = re.search(r'<title[^>]*>(.*?)</title>', html)
print(m.group(1).split('—')[0].strip() if m else '$slug')
" 2>/dev/null || echo "$slug")

      (
        # Extract page text
        local page_text=$(python3 -c "
import re
html = open('$page_file').read()
text = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
text = re.sub(r'<[^>]+>', ' ', text)
text = re.sub(r'\s+', ' ', text).strip()
print(text[:6000])
" 2>/dev/null)

        local line_count=$(wc -l < "$page_file" 2>/dev/null || echo 0)

        run_agent_tracked "classifier" "score_page" "$slug" "$OUTPUT_DIR/tournament/score-$slug.json" "
Score this M&A buyer research page on 6 dimensions (0-10 each). Return ONLY valid JSON.

SCORING RUBRIC:
$rubric

PAGE CONTENT ($buyer_name, $line_count lines):
$page_text

Return JSON: {
  \"buyer_slug\": \"$slug\",
  \"buyer_name\": \"$buyer_name\",
  \"line_count\": $line_count,
  \"scores\": {
    \"narrative_quality\": X.X,
    \"strategic_depth\": X.X,
    \"evidence_density\": X.X,
    \"actionability\": X.X,
    \"completeness\": X.X,
    \"structure\": X.X
  },
  \"overall\": X.XX,
  \"tier\": \"gold|good|incomplete|empty\",
  \"gaps\": {\"narrative\": \"...\", \"structure\": \"...\", \"tone\": \"...\"},
  \"top_strength\": \"...\",
  \"biggest_gap\": \"...\"
}

Scoring guide: gold>=7.0, good=4.0-6.9, incomplete=2.0-3.9, empty<2.0
Overall = narrative*0.25 + strategic*0.20 + evidence*0.20 + actionability*0.15 + completeness*0.10 + structure*0.10
" 300 "default"

        # Store in Supabase
        if [ -f "$OUTPUT_DIR/tournament/score-$slug.json" ] && [ "$(cat "$OUTPUT_DIR/tournament/score-$slug.json")" != "FAILED" ]; then
          python3 -c "
import json, subprocess
try:
    raw = open('$OUTPUT_DIR/tournament/score-$slug.json').read()
    # Try to extract JSON from agent response
    start = raw.find('{')
    end = raw.rfind('}') + 1
    if start >= 0 and end > start:
        d = json.loads(raw[start:end])
        s = d.get('scores', {})
        payload = json.dumps({
            'run_id': '$RUN_ID',
            'buyer_slug': '$slug',
            'buyer_name': d.get('buyer_name', '$slug'),
            'html_file': '$(basename $page_file)',
            'page_line_count': d.get('line_count', $line_count),
            'score_narrative_quality': s.get('narrative_quality', 0),
            'score_strategic_depth': s.get('strategic_depth', 0),
            'score_evidence_density': s.get('evidence_density', 0),
            'score_actionability': s.get('actionability', 0),
            'score_completeness': s.get('completeness', 0),
            'score_structure': s.get('structure', 0),
            'score_overall': d.get('overall', 0),
            'quality_tier': d.get('tier', 'incomplete'),
            'gap_narrative': d.get('gaps', {}).get('narrative', ''),
            'gap_structure': d.get('gaps', {}).get('structure', ''),
            'gap_tone': d.get('gaps', {}).get('tone', ''),
            'scoring_agent': 'classifier',
            'scoring_model': 'deepseek-v3',
            'raw_agent_response': d
        })
        subprocess.run(['curl', '-s', '${SB_URL}/benchmark_scores',
          '-H', 'apikey: ${SB_KEY}', '-H', 'Authorization: Bearer ${SB_KEY}',
          '-H', 'Content-Type: application/json', '-H', 'Prefer: return=representation',
          '-d', payload], capture_output=True)
except Exception as e:
    print(f'Score parse error for $slug: {e}')
" 2>/dev/null
        fi
      ) &
      batch_pids+=($!)
    done

    # Wait for batch
    for pid in "${batch_pids[@]}"; do
      wait "$pid" 2>/dev/null || true
    done

    scored=$((scored + batch_size))
    if [ $((scored % 15)) -eq 0 ]; then
      log "  Progress: $scored/$total scored"
    fi
    sleep 2
  done

  # Build rankings file
  python3 -c "
import json, os, glob
scores = []
for f in glob.glob('$OUTPUT_DIR/tournament/score-*.json'):
    try:
        raw = open(f).read()
        start = raw.find('{')
        end = raw.rfind('}') + 1
        if start >= 0:
            d = json.loads(raw[start:end])
            scores.append(d)
    except: pass

scores.sort(key=lambda x: x.get('overall', 0))

with open('$OUTPUT_DIR/reports/buyer-rankings.json', 'w') as f:
    json.dump(scores, f, indent=2)

# Markdown report
with open('$OUTPUT_DIR/reports/buyer-rankings.md', 'w') as f:
    f.write('# Buyer Page Quality Rankings\n\n')
    f.write(f'Scored {len(scores)} pages against Lovable benchmark rubric\n\n')
    f.write('| Rank | Buyer | Overall | Tier | Biggest Gap |\n')
    f.write('|------|-------|---------|------|-------------|\n')
    for i, s in enumerate(reversed(scores)):
        f.write(f'| {i+1} | {s.get(\"buyer_name\",\"?\")} | {s.get(\"overall\",0):.1f} | {s.get(\"tier\",\"?\")} | {s.get(\"biggest_gap\",\"\")} |\n')

# Bottom 12 for tournament
bottom = scores[:12]
with open('$OUTPUT_DIR/reports/tournament-candidates.json', 'w') as f:
    json.dump([s.get('buyer_slug') for s in bottom], f)
print(f'Rankings: {len(scores)} scored. Bottom 12: {[s.get(\"buyer_slug\") for s in bottom]}')
" 2>&1 | tee -a "$LOG_FILE"

  log "  PHASE 2 COMPLETE — $total pages scored"
  send_telegram "[Argus] Phase 2: All $total buyer pages scored. Budget: \$${BUDGET_SPENT}/\$${BUDGET_TOTAL}. Rankings saved. Starting comparison analysis."
}

# ============================================================
# PHASE 3: LOVABLE vs CRM COMPARISON
# ============================================================
phase3_comparison() {
  log "=========================================="
  log "PHASE 3: LOVABLE vs CRM COMPARISON"
  log "=========================================="

  local rankings=""
  if [ -f "$OUTPUT_DIR/reports/buyer-rankings.md" ]; then
    rankings=$(cat "$OUTPUT_DIR/reports/buyer-rankings.md" | head -80)
  fi

  local lovable_data=""
  for f in "$OUTPUT_DIR/lovable/"*.json; do
    lovable_data+=$(python3 -c "
import json
try:
    d = json.load(open('$f'))
    for r in d.get('results',[])[:1]:
        print(r.get('title',''), ':', r.get('text','')[:400])
except: pass
" 2>/dev/null)
    lovable_data+=$'\n'
  done

  run_agent_tracked "auditor" "comparison" "lovable-vs-crm" "$OUTPUT_DIR/reports/lovable-comparison.md" "
You are writing a detailed comparison report between two systems. This report will be shared with downstream agents so they know exactly what gaps to fix and what quality bar to hit.

SYSTEM A — LOVABLE DEALROOM (debbiedealroom.com):
$lovable_data

SYSTEM B — CRM BUYER PAGES (scored rankings):
$rankings

Write a structured comparison with these sections:

## 1. EXECUTIVE SUMMARY
One paragraph: what's the core quality gap?

## 2. WHAT LOVABLE DOES BETTER
- Narrative tone (operator vs. advisory)
- Strategic framing (how it positions each section)
- Information hierarchy (how it organizes for scanning)
- Personalization (how it addresses the reader)
- Specificity (numbers, names, dates vs. generic statements)

## 3. WHAT CRM PAGES DO BETTER
- Research depth (CEO quotes, earnings data, M&A history)
- Actionability (golden nuggets, call scripts, verified contacts)
- Data density (more fields, more evidence per page)
- Scale (68 pages vs. placeholder sections)

## 4. THE GAP ANALYSIS
For each of the 6 scoring dimensions, identify:
- Where CRM pages fall short of Lovable quality bar
- Specific examples from top-scored and bottom-scored pages
- What a prompt needs to produce to close the gap

## 5. RECOMMENDATIONS FOR DOWNSTREAM AGENTS
Write this as INSTRUCTIONS that agents will follow:
- When generating narrative content, do THIS not THAT
- When structuring sections, follow THIS pattern
- When using CEO quotes, format them THIS way
- When writing call openers, use THIS tone
- Include 3 prompt variations that should produce Lovable-quality output

## 6. PROCESS IMPROVEMENT RECOMMENDATIONS
What should change in the dossier pipeline (Exa research → dual-LLM analysis → validation → synthesis) to consistently produce gold-tier pages?

Write for an audience of AI agents who will execute these recommendations autonomously. Be specific. Include exact prompt fragments they should use.
" 900

  # Cross-check with validator
  if [ -f "$OUTPUT_DIR/reports/lovable-comparison.md" ]; then
    run_agent_tracked "validator" "validate_comparison" "comparison-check" "$OUTPUT_DIR/reports/comparison-validation.json" "
Review this comparison report for accuracy and completeness. Flag any claims that aren't supported by the data provided. Return JSON with: {\"is_valid\": true/false, \"issues\": [...], \"missing_topics\": [...], \"quality_score\": X.X}

REPORT:
$(cat "$OUTPUT_DIR/reports/lovable-comparison.md" | head -200)
" 300
  fi

  log "  PHASE 3 COMPLETE"
  send_telegram "[Argus] Phase 3: Lovable vs CRM comparison complete. Gap analysis + prompt recommendations written. Budget: \$${BUDGET_SPENT}/\$${BUDGET_TOTAL}. Starting agent tournament."
}

# ============================================================
# PHASE 4: AGENT TOURNAMENT
# ============================================================
phase4_tournament() {
  log "=========================================="
  log "PHASE 4: AGENT TOURNAMENT"
  log "=========================================="

  # Load tournament candidates (bottom 12 from Phase 2)
  local candidates_file=$(mktemp)
  if [ -f "$OUTPUT_DIR/reports/tournament-candidates.json" ]; then
    python3 -c "
import json
for slug in json.load(open('$OUTPUT_DIR/reports/tournament-candidates.json')):
    print(slug)
" > "$candidates_file" 2>/dev/null
  fi

  local total=$(wc -l < "$candidates_file" | tr -d ' ')
  if [ "$total" -eq 0 ] 2>/dev/null; then
    log "  No tournament candidates found — skipping"
    rm -f "$candidates_file"
    return 0
  fi
  local completed=0

  # Load comparison recommendations for prompt context
  local recommendations=""
  if [ -f "$OUTPUT_DIR/reports/lovable-comparison.md" ]; then
    recommendations=$(grep -A 50 "RECOMMENDATIONS FOR DOWNSTREAM" "$OUTPUT_DIR/reports/lovable-comparison.md" 2>/dev/null | head -60)
  fi

  log "  Tournament: $total buyers competing"

  while IFS= read -r slug; do
    [ -z "$slug" ] && continue
    check_budget || break

    local page_file="$PROJECT_DIR/public/hr-com-ltd_${slug}.html"
    if [ ! -f "$page_file" ]; then
      log "  ⚠️ Page not found: $slug — skipping"
      continue
    fi

    local buyer_name=$(python3 -c "
import re
html = open('$page_file').read()
m = re.search(r'<title[^>]*>(.*?)</title>', html)
print(m.group(1).split('—')[0].strip() if m else '$slug')
" 2>/dev/null || echo "$slug")

    local original_score=$(python3 -c "
import json, glob
for f in glob.glob('$OUTPUT_DIR/tournament/score-${slug}.json'):
    raw = open(f).read()
    start = raw.find('{')
    end = raw.rfind('}') + 1
    if start >= 0:
        d = json.loads(raw[start:end])
        print(d.get('overall', 0))
        break
" 2>/dev/null || echo "0")

    log "  --- Tournament: $buyer_name (original score: $original_score) ---"

    local tgroup="tournament-${slug}"

    # Step 1: Exa research (ONE set, shared by all agents)
    local exa_context=""
    local exa_count=0
    local queries=(
      "$buyer_name CEO strategy HR acquisition 2025 2026"
      "$buyer_name M&A acquisition history recent deals"
      "$buyer_name HR technology community platform strategy"
      "$buyer_name earnings call CEO quotes AI strategy"
    )

    for q in "${queries[@]}"; do
      check_budget || break
      exa_search_tracked "$q" "$OUTPUT_DIR/tournament/exa-${slug}-${exa_count}.json" "exa-${slug}-${exa_count}"
      exa_count=$((exa_count + 1))
      sleep 2
    done

    # Compile Exa results
    exa_context=$(python3 -c "
import json, glob
text = ''
for f in sorted(glob.glob('$OUTPUT_DIR/tournament/exa-${slug}-*.json')):
    try:
        d = json.load(open(f))
        for r in d.get('results',[])[:3]:
            text += r.get('title','') + ': ' + r.get('text','')[:600] + '\n\n'
    except: pass
print(text[:8000])
" 2>/dev/null)

    # Step 2: Two agents synthesize competing narratives
    local existing_page=$(python3 -c "
import re
html = open('$page_file').read()
text = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
text = re.sub(r'<[^>]+>', ' ', text)
text = re.sub(r'\s+', ' ', text).strip()
print(text[:4000])
" 2>/dev/null)

    local base_prompt="
TASK: Re-write the buyer research narrative for $buyer_name to gold-tier quality.

CURRENT PAGE CONTENT (scored $original_score/10):
$existing_page

NEW EXA RESEARCH:
$exa_context

QUALITY IMPROVEMENT INSTRUCTIONS:
$recommendations

OUTPUT FORMAT — Return a JSON object:
{
  \"strategic_fit\": \"300-400 word narrative on why $buyer_name should acquire HR.com assets\",
  \"golden_nuggets\": [\"5 cold call openers, each with a CEO quote + opener script + why it works\"],
  \"ceo_vision\": \"200 word CEO strategy synthesis\",
  \"ma_appetite\": \"200 word M&A pattern analysis with specific deals\",
  \"challenges\": \"200 word headwinds HR.com solves\",
  \"earnings_quotes\": [\"8 CEO quotes with dates and sources\"],
  \"fit_score\": 7,
  \"fit_rationale\": \"Why this score\"
}

Be SPECIFIC. Use real CEO names, real quotes, real deal references. No generic language."

    # Agent A: executor (GPT-4o-mini) — operator tone
    run_agent_tracked "executor" "re_enrich" "$slug" "$OUTPUT_DIR/tournament/enrich-${slug}-A.json" "
$base_prompt
TONE: Operator. Direct. Specific. Like John Kelly: 'We're damn good at what we do.'
" 900 "operator_tone" "$tgroup"

    sleep $SLEEP_BETWEEN

    # Agent B: nurturer (GPT-4o-mini) — strategic analyst tone
    run_agent_tracked "nurturer" "re_enrich" "$slug" "$OUTPUT_DIR/tournament/enrich-${slug}-B.json" "
$base_prompt
TONE: Strategic analyst. Data-heavy. McKinsey style. Lead with numbers and market positioning.
" 900 "analyst_tone" "$tgroup"

    sleep $SLEEP_BETWEEN

    # Step 3: Auditor scores both
    local output_a=$(cat "$OUTPUT_DIR/tournament/enrich-${slug}-A.json" 2>/dev/null | head -200)
    local output_b=$(cat "$OUTPUT_DIR/tournament/enrich-${slug}-B.json" 2>/dev/null | head -200)

    run_agent_tracked "auditor" "judge_tournament" "$slug" "$OUTPUT_DIR/tournament/judge-${slug}.json" "
Score both outputs for $buyer_name on narrative quality, strategic depth, evidence density, actionability (0-10 each).

OUTPUT A (executor, operator tone):
$output_a

OUTPUT B (nurturer, analyst tone):
$output_b

Return JSON: {
  \"agent_a\": {\"score\": X.X, \"strengths\": \"...\", \"weaknesses\": \"...\"},
  \"agent_b\": {\"score\": X.X, \"strengths\": \"...\", \"weaknesses\": \"...\"},
  \"winner\": \"a|b\",
  \"winner_score\": X.X,
  \"reason\": \"Why the winner is better\",
  \"needs_agent_c\": true/false
}

Set needs_agent_c=true if BOTH score below 5.0.
" 300 "default" "$tgroup"

    # Step 4: Check if swap needed
    local needs_c=$(python3 -c "
import json
try:
    raw = open('$OUTPUT_DIR/tournament/judge-${slug}.json').read()
    start = raw.find('{')
    end = raw.rfind('}') + 1
    d = json.loads(raw[start:end])
    print('true' if d.get('needs_agent_c', False) else 'false')
except: print('false')
" 2>/dev/null || echo "false")

    if [ "$needs_c" = "true" ]; then
      log "  ⚡ INNOVATION: Both agents scored low for $slug — swapping in auditor (DeepSeek V3)"

      run_agent_tracked "auditor" "re_enrich" "$slug" "$OUTPUT_DIR/tournament/enrich-${slug}-C.json" "
$base_prompt
TONE: Narrative storytelling. Connect CEO quotes directly to acquisition thesis. Make the reader feel the strategic urgency.
" 900 "narrative_tone" "$tgroup"

      # Re-judge with C included
      local output_c=$(cat "$OUTPUT_DIR/tournament/enrich-${slug}-C.json" 2>/dev/null | head -200)
      run_agent_tracked "auditor" "judge_tournament_3way" "$slug" "$OUTPUT_DIR/tournament/judge-${slug}-final.json" "
Score all three outputs for $buyer_name. Return JSON with winner.
A (executor): $output_a
B (nurturer): $output_b
C (auditor, narrative): $output_c
Return: {\"winner\": \"a|b|c\", \"winner_score\": X.X, \"scores\": {\"a\": X.X, \"b\": X.X, \"c\": X.X}}
" 300 "default" "$tgroup"

      sleep $SLEEP_BETWEEN
    fi

    # Store tournament result
    python3 -c "
import json, subprocess
try:
    judge_file = '$OUTPUT_DIR/tournament/judge-${slug}-final.json' if '$needs_c' == 'true' else '$OUTPUT_DIR/tournament/judge-${slug}.json'
    raw = open(judge_file).read()
    start = raw.find('{')
    end = raw.rfind('}') + 1
    j = json.loads(raw[start:end])

    payload = json.dumps({
        'run_id': '$RUN_ID',
        'buyer_slug': '$slug',
        'buyer_name': '$buyer_name',
        'original_score': float('$original_score') if '$original_score' != '0' else 0,
        'winning_agent': j.get('winner', 'unknown'),
        'winning_score': j.get('winner_score', 0),
        'score_improvement': j.get('winner_score', 0) - float('$original_score') if '$original_score' != '0' else 0,
        'exa_searches_used': $exa_count,
        'total_cost': $exa_count * $EXA_COST_PER_SEARCH + 0.01
    })
    subprocess.run(['curl', '-s', '${SB_URL}/re_enrichment_results',
      '-H', 'apikey: ${SB_KEY}', '-H', 'Authorization: Bearer ${SB_KEY}',
      '-H', 'Content-Type: application/json', '-H', 'Prefer: return=representation',
      '-d', payload], capture_output=True)
except Exception as e:
    print(f'Tournament store error: {e}')
" 2>/dev/null

    completed=$((completed + 1))
    log "  Tournament: $completed/$total complete. Budget: \$${BUDGET_SPENT}/\$${BUDGET_TOTAL}"

    if [ $((completed % 4)) -eq 0 ]; then
      send_telegram "[Argus] Tournament: $completed/$total buyers re-enriched. Budget: \$${BUDGET_SPENT}/\$${BUDGET_TOTAL}."
    fi
  done < "$candidates_file"

  rm -f "$candidates_file"
  log "  PHASE 4 COMPLETE — $completed buyers through tournament"
  send_telegram "[Argus] Phase 4: Agent tournament complete. $completed buyers re-enriched. Budget: \$${BUDGET_SPENT}/\$${BUDGET_TOTAL}. Launching overnight build + generating rankings."
}

# ============================================================
# PHASE 5: LAUNCH OVERNIGHT BUILD (background)
# ============================================================
phase5_overnight_build() {
  log "=========================================="
  log "PHASE 5: LAUNCHING OVERNIGHT BUILD"
  log "=========================================="

  if [ -f "$PROJECT_DIR/scripts/hrcom-overnight-build.sh" ]; then
    bash "$PROJECT_DIR/scripts/hrcom-overnight-build.sh" &
    local overnight_pid=$!
    log "  Overnight build launched as PID $overnight_pid"
    send_telegram "[Argus] Phase 5: Overnight build launched in background (PID $overnight_pid). Stress test continuing to rankings."
  else
    log "  ⚠️ Overnight build script not found — skipping"
  fi
}

# ============================================================
# PHASE 6: AGENT PERFORMANCE RANKING
# ============================================================
phase6_rankings() {
  log "=========================================="
  log "PHASE 6: AGENT PERFORMANCE RANKINGS"
  log "=========================================="

  # Pull all performance data from Supabase
  local perf_data=$(curl -s "${SB_URL}/agent_performance_log?run_id=eq.${RUN_ID}&select=agent_id,agent_model,task_type,output_quality_score,cost_usd,duration_seconds,output_usable,was_swapped,tournament_rank,prompt_variant&order=created_at.asc" \
    "${SB_HEADERS[@]}" 2>/dev/null)

  # Also pull tournament results
  local tournament_data=$(curl -s "${SB_URL}/re_enrichment_results?run_id=eq.${RUN_ID}&select=buyer_slug,winning_agent,winning_score,original_score,score_improvement,total_cost" \
    "${SB_HEADERS[@]}" 2>/dev/null)

  run_agent_tracked "controller" "rank_agents" "final-rankings" "$OUTPUT_DIR/reports/agent-rankings.md" "
You are writing the definitive agent performance report for an overnight stress test. This report tells us which agents excel at which tasks, what they cost, and how to optimize the fleet.

RAW PERFORMANCE DATA (from Supabase):
$perf_data

TOURNAMENT RESULTS:
$tournament_data

TOTAL BUDGET SPENT: \$${BUDGET_SPENT} of \$${BUDGET_TOTAL}

Write a report with these sections:

## 1. AGENT LEADERBOARD
Rank all agents by average quality score per task type. Table format:
| Agent | Model | Task | Avg Quality | Avg Cost | Avg Duration | Win Rate |

## 2. TASK-BY-TASK ANALYSIS
For each task type (score_page, re_enrich, judge_tournament, build_rubric, comparison, exa_search):
- Best agent for this task
- Worst agent for this task
- Cost efficiency (quality per dollar)

## 3. PROMPT VARIATION RESULTS
Compare operator_tone vs analyst_tone vs narrative_tone:
- Which produced higher scores?
- Which was more cost-efficient?
- Recommendation for default prompt style

## 4. INNOVATION EVENTS
List every agent swap that occurred:
- Which buyer triggered the swap
- Why (what scored low)
- Did the swap improve results?
- Recommendation: should we swap more aggressively or less?

## 5. COST REPORT
- Total Exa searches and cost
- Total agent calls and cost
- Cost per re-enriched buyer
- Budget utilization efficiency
- Recommendation for next run's budget allocation

## 6. FLEET RECOMMENDATIONS
Based on all data:
- Which agents should be promoted to more tasks?
- Which agents should be retired or reassigned?
- What model upgrades would have the highest ROI?
- What's the ideal agent assignment matrix for the next run?

## 7. PROCESS IMPROVEMENTS
What should change in the pipeline based on tonight's learnings:
- Prompt improvements that worked
- Research depth changes needed
- Validation steps to add/remove
- Scoring calibration adjustments

Be data-driven. Use actual numbers from the performance data. This report shapes how we build the next version of the system.
" 900

  # Also generate JSON version
  run_agent_tracked "classifier" "rank_agents_json" "rankings-json" "$OUTPUT_DIR/reports/agent-rankings.json" "
Summarize agent performance as JSON. Input data:
$perf_data

Return: {
  \"rankings_by_task\": {\"score_page\": [{\"agent\": \"...\", \"model\": \"...\", \"avg_quality\": X.X, \"avg_cost\": X.XX, \"calls\": N}]},
  \"prompt_variation_results\": {\"operator_tone\": {\"avg_score\": X.X}, \"analyst_tone\": {\"avg_score\": X.X}},
  \"innovation_events\": [{\"buyer\": \"...\", \"swapped\": \"...\", \"reason\": \"...\", \"improved\": true}],
  \"top_agent_overall\": \"...\",
  \"best_value_agent\": \"...\",
  \"total_cost\": $BUDGET_SPENT,
  \"total_calls\": N
}
" 300

  log "  PHASE 6 COMPLETE"
  send_telegram "[Argus] Phase 6: Agent rankings complete. Budget: \$${BUDGET_SPENT}/\$${BUDGET_TOTAL}."
}

# ============================================================
# PHASE 7: INSPECTION REPORT
# ============================================================
phase7_inspection() {
  log "=========================================="
  log "PHASE 7: INSPECTION REPORT"
  log "=========================================="

  # Gather all outputs for context
  local rankings_md=""
  [ -f "$OUTPUT_DIR/reports/agent-rankings.md" ] && rankings_md=$(cat "$OUTPUT_DIR/reports/agent-rankings.md" | head -150)
  local comparison_md=""
  [ -f "$OUTPUT_DIR/reports/lovable-comparison.md" ] && comparison_md=$(cat "$OUTPUT_DIR/reports/lovable-comparison.md" | head -150)
  local buyer_rankings=""
  [ -f "$OUTPUT_DIR/reports/buyer-rankings.md" ] && buyer_rankings=$(cat "$OUTPUT_DIR/reports/buyer-rankings.md" | head -80)

  run_agent_tracked "executor" "inspection_report" "final-report" "$OUTPUT_DIR/reports/inspection-report.md" "
You are writing the master inspection report for an overnight stress test of an M&A deal automation system. This report is the SINGLE document that downstream agents will read to understand everything that happened tonight, what was learned, and what to do differently.

FORMAT: Every finding must include:
- WHAT WAS DONE (method, agent, prompt)
- WHAT IT FOUND (data, scores, comparisons)
- WHAT IT MEANS (interpretation)
- WHAT TO DO NEXT (specific action for the next agent)

AGENT RANKINGS:
$rankings_md

LOVABLE vs CRM COMPARISON:
$comparison_md

BUYER PAGE RANKINGS:
$buyer_rankings

BUDGET: \$${BUDGET_SPENT} of \$${BUDGET_TOTAL} spent

Write the report with these 8 sections:

## 1. EXECUTIVE SUMMARY
3 sentences. What happened tonight, what we learned, what changes.

## 2. LOVABLE BENCHMARK FINDINGS
What the quality bar looks like. What dimensions matter most.

## 3. BUYER PAGE QUALITY DISTRIBUTION
How many gold/good/incomplete/empty. What separates tiers.

## 4. GAP ANALYSIS
The specific gaps between our pages and the benchmark. Include exact prompt fragments that close each gap.

## 5. TOURNAMENT RESULTS
Which agents won, which lost, which prompts worked.

## 6. INNOVATION LOG
Every swap, every re-run, every hunch that paid off or didn't.

## 7. COST ANALYSIS
Where money went. What was worth it. What wasn't.

## 8. NEXT RUN PLAYBOOK
Exact instructions for the next overnight run. Agent assignments, prompt templates, budget allocation, quality gates.

This document is the institutional memory of tonight. Write it like a field manual.
" 900

  log "  PHASE 7 COMPLETE"
}

# ============================================================
# PHASE 8: DEAL ROOM UPDATE + GIT
# ============================================================
phase8_finalize() {
  log "=========================================="
  log "PHASE 8: DEAL ROOM + GIT"
  log "=========================================="

  cd "$PROJECT_DIR"

  # Count all outputs
  local total_files=$(find "$OUTPUT_DIR" -type f | wc -l | tr -d ' ')
  local total_scored=$(ls "$OUTPUT_DIR/tournament/score-"*.json 2>/dev/null | wc -l | tr -d ' ')
  local total_enriched=$(ls "$OUTPUT_DIR/tournament/enrich-"*.json 2>/dev/null | wc -l | tr -d ' ')

  # Generate Agent Lab HTML section
  cat > "$OUTPUT_DIR/reports/agent-lab-section.html" << 'LABEOF'
<div class="section-card" style="grid-column: 1 / -1">
  <div class="section-header">
    <h2>Agent Lab — Stress Test Results</h2>
    <span class="badge" style="background:#8b5cf6">EXPERIMENTAL</span>
  </div>
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:16px 0">
LABEOF

  echo "    <div style='background:#21262d;border:1px solid #30363d;border-radius:8px;padding:16px;text-align:center'>
      <div style='font-size:28px;font-weight:700;color:#58a6ff'>$total_scored</div>
      <div style='font-size:12px;color:#8b949e'>Pages Scored</div>
    </div>
    <div style='background:#21262d;border:1px solid #30363d;border-radius:8px;padding:16px;text-align:center'>
      <div style='font-size:28px;font-weight:700;color:#f0883e'>\$${BUDGET_SPENT}</div>
      <div style='font-size:12px;color:#8b949e'>Budget Used</div>
    </div>
    <div style='background:#21262d;border:1px solid #30363d;border-radius:8px;padding:16px;text-align:center'>
      <div style='font-size:28px;font-weight:700;color:#3fb950'>$total_enriched</div>
      <div style='font-size:12px;color:#8b949e'>Tournament Rounds</div>
    </div>
  </div>
  <div style='display:flex;flex-wrap:wrap;gap:8px'>
    <a href='/outputs/stress-test/reports/inspection-report.md' class='quick-link'>Inspection Report</a>
    <a href='/outputs/stress-test/reports/buyer-rankings.md' class='quick-link'>Buyer Rankings</a>
    <a href='/outputs/stress-test/reports/agent-rankings.md' class='quick-link accent'>Agent Leaderboard</a>
    <a href='/outputs/stress-test/reports/lovable-comparison.md' class='quick-link'>Lovable Comparison</a>
    <a href='/outputs/stress-test/reports/agent-rankings.json' class='quick-link'>Performance Data (JSON)</a>
  </div>
</div>" >> "$OUTPUT_DIR/reports/agent-lab-section.html"

  # Inject Agent Lab into deal room page
  if [ -f "public/hrcom-dealroom-overnight.html" ]; then
    local lab_html=$(cat "$OUTPUT_DIR/reports/agent-lab-section.html")
    python3 -c "
import re
html = open('public/hrcom-dealroom-overnight.html').read()
# Insert before the morning checklist or before </main> or before last </div>
if '<!-- AGENT-LAB -->' not in html:
    # Find the checklist section or end of grid
    insert_point = html.rfind('<!-- Morning Checklist')
    if insert_point < 0:
        insert_point = html.rfind('</main>')
    if insert_point < 0:
        insert_point = html.rfind('</body>')
    if insert_point > 0:
        lab = open('$OUTPUT_DIR/reports/agent-lab-section.html').read()
        html = html[:insert_point] + '<!-- AGENT-LAB -->\n' + lab + '\n' + html[insert_point:]
        open('public/hrcom-dealroom-overnight.html', 'w').write(html)
        print('Agent Lab injected into deal room page')
    else:
        print('Could not find injection point')
" 2>/dev/null || log "  ⚠️ Could not inject Agent Lab into deal room page"
  fi

  # Build master index
  {
    echo "# STRESS TEST — OUTPUT INDEX"
    echo "## Run: $(date '+%Y-%m-%d %H:%M')"
    echo "## Budget: \$${BUDGET_SPENT} / \$${BUDGET_TOTAL}"
    echo ""
    echo "## Reports"
    ls "$OUTPUT_DIR/reports/"* 2>/dev/null | while read f; do echo "- $(basename $f)"; done
    echo ""
    echo "## Tournament"
    echo "- Score files: $(ls "$OUTPUT_DIR/tournament/score-"*.json 2>/dev/null | wc -l | tr -d ' ')"
    echo "- Enrichment files: $(ls "$OUTPUT_DIR/tournament/enrich-"*.json 2>/dev/null | wc -l | tr -d ' ')"
    echo "- Judge files: $(ls "$OUTPUT_DIR/tournament/judge-"*.json 2>/dev/null | wc -l | tr -d ' ')"
    echo ""
    echo "## Lovable Benchmark"
    ls "$OUTPUT_DIR/lovable/"* 2>/dev/null | while read f; do echo "- $(basename $f)"; done
  } > "$OUTPUT_DIR/INDEX.md"

  # Update run status in Supabase
  sb_patch "stress_test_runs" "id=eq.${RUN_ID}" "{
    \"status\":\"completed\",
    \"budget_spent\":$BUDGET_SPENT,
    \"budget_remaining\":$BUDGET_REMAINING,
    \"total_buyers_scored\":$total_scored,
    \"total_buyers_re_enriched\":$((total_enriched / 2)),
    \"completed_at\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
  }" > /dev/null

  # Git commit
  if [ -n "$(git status --porcelain outputs/ public/ migrations/)" ]; then
    git add outputs/stress-test/ public/hrcom-dealroom-overnight.html migrations/004_stress_test_tables.sql
    git commit -m "feat: stress test complete — $total_scored pages scored, agent tournament, \$${BUDGET_SPENT} spent

Overnight stress test results:
- $total_scored buyer pages scored against Lovable benchmark
- $((total_enriched / 2)) buyers re-enriched via agent tournament
- Agent performance rankings generated
- Lovable vs CRM gap analysis complete
- Budget: \$${BUDGET_SPENT} / \$${BUDGET_TOTAL}
- Deal room Agent Lab section live

Co-Authored-By: OpenClaw Agents <noreply@openclaw.ai>" 2>>"$LOG_FILE" || true
    log "  ✅ Git committed (not pushed)"
  fi

  # Final Telegram
  local summary="[Argus] 🏁 STRESS TEST COMPLETE

📊 Results:
• $total_scored buyer pages scored (6 dimensions each)
• $((total_enriched / 2)) buyers through agent tournament
• $total_files total output files
• Agent leaderboard generated

💰 Budget: \$${BUDGET_SPENT} / \$${BUDGET_TOTAL} (\$${BUDGET_REMAINING} remaining)

🔗 Deal room: master-crm-web-eight.vercel.app/hrcom-dealroom-overnight.html
📋 Agent Lab section added with rankings + tournament data

📄 Key files:
• outputs/stress-test/reports/inspection-report.md
• outputs/stress-test/reports/agent-rankings.md
• outputs/stress-test/reports/buyer-rankings.md
• outputs/stress-test/reports/lovable-comparison.md

⏰ The overnight build is running in background.
Check the deal room ⚡ for everything."

  send_telegram "$summary"
  log "$summary"
  log "=========================================="
  log "STRESS TEST — COMPLETE"
  log "=========================================="
}

# ============================================================
# MAIN
# ============================================================
main() {
  log "============================================"
  log "HR.COM STRESS TEST + AGENT TOURNAMENT"
  log "Budget: \$${BUDGET_TOTAL} | Claude: ZERO"
  log "============================================"

  send_telegram "[Argus] 🧪 STRESS TEST STARTING

\$100 budget. 8 phases. Full agent tournament.

Phase 0: Preflight + Supabase migration
Phase 1: Scrape Lovable benchmark (5 Exa searches)
Phase 2: Score all 68 buyer pages (6 dimensions)
Phase 3: Lovable vs CRM comparison + gap analysis
Phase 4: Agent tournament — bottom 12 buyers re-enriched
Phase 5: Launch overnight build (background)
Phase 6: Agent performance rankings
Phase 7: Inspection report (downstream context)
Phase 8: Deal room Agent Lab + git

Zero Claude. All OpenClaw. Every call tracked.
Go to sleep. I'll Telegram you everything."

  phase0_preflight

  # Resume mode: skip phases whose outputs already exist
  local resume="${1:-}"

  if [ "$resume" = "--resume" ] && [ -f "$OUTPUT_DIR/lovable/scoring-rubric.json" ]; then
    log "  ⏭️ RESUME: Skipping Phase 1 (rubric exists)"
  else
    phase1_benchmark
  fi

  if [ "$resume" = "--resume" ] && [ -f "$OUTPUT_DIR/reports/buyer-rankings.json" ]; then
    log "  ⏭️ RESUME: Skipping Phase 2 (rankings exist)"
  else
    phase2_score_pages
  fi

  if [ "$resume" = "--resume" ] && [ -f "$OUTPUT_DIR/reports/lovable-comparison.md" ]; then
    log "  ⏭️ RESUME: Skipping Phase 3 (comparison exists)"
  else
    phase3_comparison
  fi

  phase4_tournament
  phase5_overnight_build
  phase6_rankings
  phase7_inspection
  phase8_finalize
}

main "$@"
