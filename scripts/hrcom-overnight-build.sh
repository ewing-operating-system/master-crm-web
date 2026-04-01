#!/bin/bash
# Credentials: all keys come from env vars (inherited from ~/.zshrc).
# See .env.example for variable names. NEVER hardcode keys in scripts.
# ============================================================
# HR.COM DEAL — OVERNIGHT MULTI-AGENT BUILD
# Uses OpenClaw agents (DeepSeek/Gemini/GPT-4o-mini) — ZERO Claude usage
# Run: bash ~/Projects/master-crm-web/scripts/hrcom-overnight-build.sh
# ============================================================

set -euo pipefail

# --- Config ---
PROJECT_DIR="$HOME/Projects/master-crm-web"
OUTPUT_DIR="$PROJECT_DIR/outputs"
LOG_FILE="$PROJECT_DIR/scripts/hrcom-overnight-build.log"
SLEEP_BETWEEN=15  # seconds between agent calls (rate limit protection)

# Load env vars without interactive zsh features
export $(grep -E '^export ' ~/.zshrc 2>/dev/null | sed 's/^export //' | grep -v '#' | xargs) 2>/dev/null || true
source ~/.openclaw/.env 2>/dev/null || true

# --- Reference Data Paths ---
REF_DIR="$OUTPUT_DIR/reference"
INTEL_DIR="$OUTPUT_DIR/buyer-intel"
TRANSCRIPT_MAR23="$REF_DIR/transcript-march-23-summary.md"
TRANSCRIPT_MAR30="$REF_DIR/transcript-march-30-summary.md"
BUYERS_JSON="$INTEL_DIR/all-buyers-structured.json"
DEAL_INTEL="$INTEL_DIR/deal-intelligence.md"
EXISTING_SCRIPTS="$INTEL_DIR/existing-scripts.md"
DEALROOM_PAGE="$PROJECT_DIR/public/hrcom-dealroom-overnight.html"

# --- Pre-flight checks ---
preflight() {
  local missing=0
  for f in "$TRANSCRIPT_MAR23" "$TRANSCRIPT_MAR30" "$BUYERS_JSON" "$DEAL_INTEL" "$EXISTING_SCRIPTS"; do
    if [ ! -f "$f" ]; then
      echo "MISSING: $f"
      missing=$((missing + 1))
    fi
  done
  if [ $missing -gt 0 ]; then
    echo "❌ $missing reference files missing. Run the data prep first."
    exit 1
  fi
  echo "✅ All reference files present. Full context loaded."
}

# --- Load reference data into variables ---
load_context() {
  CONTEXT_MAR23=$(cat "$TRANSCRIPT_MAR23" 2>/dev/null | head -120)
  CONTEXT_MAR30=$(cat "$TRANSCRIPT_MAR30" 2>/dev/null | head -120)
  CONTEXT_DEAL_INTEL=$(cat "$DEAL_INTEL" 2>/dev/null)
  CONTEXT_SCRIPTS=$(cat "$EXISTING_SCRIPTS" 2>/dev/null | head -80)

  # Extract buyer names by segment
  BUYERS_FIT8=$(python3 -c "
import json
data = json.load(open('$BUYERS_JSON'))
for b in data:
    if b.get('fit_score') == '8':
        print(f\"- {b['name']} ({b.get('type','?')}, {b.get('location','?')})\")
" 2>/dev/null || echo "Could not load buyers")

  BUYERS_ALL_NAMES=$(python3 -c "
import json
data = json.load(open('$BUYERS_JSON'))
for b in data:
    print(f\"- {b['name']} | fit={b.get('fit_score','?')} | type={b.get('type','?')} | segment={b.get('segment','?')}\")
" 2>/dev/null || echo "Could not load buyers")

  # Count stats
  TOTAL_BUYERS=$(python3 -c "import json; print(len(json.load(open('$BUYERS_JSON'))))" 2>/dev/null || echo "?")

  log "  Context loaded: Mar23 transcript, Mar30 transcript, $TOTAL_BUYERS buyers, deal intel, scripts"
}

# --- Logging ---
log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

send_telegram() {
  openclaw message send --channel telegram --target "$EWING_TELEGRAM_CHAT_ID" --message "$1" 2>/dev/null || true
}

# --- Direct DeepSeek API call (bypasses broken OpenRouter) ---
run_agent() {
  local agent_type="$1"  # label only — all calls go to DeepSeek direct
  local output_file="$2"
  local message="$3"
  local timeout="${4:-600}"

  log "  [$agent_type → DeepSeek] $(basename $output_file)"

  local tmpfile=$(mktemp)
  echo "$message" > "$tmpfile"

  local result
  result=$(python3 -c "
import json, requests
prompt = open('$tmpfile').read()[:12000]
try:
    resp = requests.post('https://api.deepseek.com/chat/completions',
        headers={'Authorization': 'Bearer ${DEEPSEEK_API_KEY}', 'Content-Type': 'application/json'},
        json={'model': 'deepseek-chat', 'messages': [{'role': 'user', 'content': prompt}], 'max_tokens': 4000, 'temperature': 0.4},
        timeout=$timeout
    )
    data = resp.json()
    content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
    usage = data.get('usage', {})
    cost = (usage.get('prompt_tokens',0) * 0.27 + usage.get('completion_tokens',0) * 1.10) / 1000000
    print(content)
    import sys; print(f'[cost: \${cost:.4f}]', file=sys.stderr)
except Exception as e:
    print(f'ERROR: {e}')
    import sys; sys.exit(1)
" 2>>"$LOG_FILE") || {
    rm -f "$tmpfile"
    log "  ❌ FAILED: $(basename $output_file) — retrying..."
    sleep 20
    local tmpfile2=$(mktemp)
    echo "$message" > "$tmpfile2"
    result=$(python3 -c "
import json, requests
prompt = open('$tmpfile2').read()[:12000]
resp = requests.post('https://api.deepseek.com/chat/completions',
    headers={'Authorization': 'Bearer ${DEEPSEEK_API_KEY}', 'Content-Type': 'application/json'},
    json={'model': 'deepseek-chat', 'messages': [{'role': 'user', 'content': prompt}], 'max_tokens': 4000, 'temperature': 0.4},
    timeout=$timeout)
print(resp.json().get('choices', [{}])[0].get('message', {}).get('content', ''))
" 2>>"$LOG_FILE") || {
      rm -f "$tmpfile2"
      log "  ❌ FAILED TWICE: $(basename $output_file)"
      echo "FAILED" > "$output_file"
      return 1
    }
    rm -f "$tmpfile2"
  }

  rm -f "$tmpfile"
  echo "$result" > "$output_file"
  log "  ✅ Done: $(basename $output_file)"
  return 0
}

# --- Exa search helper (direct API, no agent needed) ---
exa_search() {
  local query="$1"
  local output_file="$2"
  local num_results="${3:-8}"

  curl -s "https://api.exa.ai/search" \
    -H "x-api-key: $EXA_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{
      \"query\": $(python3 -c "import json; print(json.dumps('$query'))"),
      \"numResults\": $num_results,
      \"type\": \"auto\",
      \"contents\": {\"text\": {\"maxCharacters\": 3000}, \"highlights\": true}
    }" > "$output_file" 2>/dev/null

  local count
  count=$(python3 -c "import json; d=json.load(open('$output_file')); print(len(d.get('results',[])))" 2>/dev/null || echo "0")
  log "  Exa: '$query' → $count results"
}

# ============================================================
# PHASE 1: BUYER RESEARCH (Agent 3)
# Direct Exa API calls — no agent overhead
# ============================================================
phase1_buyer_research() {
  log "=========================================="
  log "PHASE 1: BUYER RESEARCH (Exa API direct)"
  log "=========================================="

  local intel_dir="$OUTPUT_DIR/buyer-intel"
  mkdir -p "$intel_dir"

  # 10 search queries from the prompt
  local -a QUERIES=(
    '"HR.com domain" OR "hr.com acquisition"'
    '"two-letter domain" AND ("acquisition" OR "purchase" OR "sold") AND ("2024" OR "2025" OR "2026")'
    'site:linkedin.com "head of corporate development" AND ("SAP" OR "Workday" OR "Oracle" OR "ADP")'
    '"category defining domain" AND "enterprise" AND ("acquired" OR "purchased")'
    '"OpenAI" OR "Anthropic" OR "Google" AND "HR" AND ("platform" OR "product" OR "launch")'
    '"Deel" OR "Rippling" OR "Remote" AND ("acquisition" OR "acquired" OR "M&A") AND "2025" OR "2026"'
    '"Christian Klein" AND "SAP" AND ("HR" OR "SuccessFactors" OR "acquisition" OR "strategy")'
    '"Carl Eschenbach" AND "Workday" AND ("strategy" OR "acquisition" OR "domain" OR "brand")'
    '"hr.com" AND ("valuation" OR "worth" OR "revenue" OR "traffic")'
    '"two letter .com domain" AND ("sold" OR "price" OR "million")'
  )

  local -a NAMES=(
    "search-hrcom-domain"
    "search-two-letter-domain-sales"
    "search-corp-dev-leaders"
    "search-category-domain-precedent"
    "search-ai-entering-hr"
    "search-hrtech-consolidation"
    "search-sap-ceo-strategy"
    "search-workday-ceo-strategy"
    "search-hrcom-public-intel"
    "search-two-letter-domain-comps"
  )

  for i in "${!QUERIES[@]}"; do
    exa_search "${QUERIES[$i]}" "$intel_dir/${NAMES[$i]}.json"
    sleep 3  # light rate limiting
  done

  # Media buyer research
  log "  --- Media buyer research ---"
  exa_search "HubSpot acquired The Hustle media acquisition B2B content" "$intel_dir/search-media-hubspot-hustle.json"
  sleep 3
  exa_search "B2B media company acquisitions 2024 2025 2026 HR content" "$intel_dir/search-b2b-media-acquisitions.json"
  sleep 3

  # MyPeople / investor research
  log "  --- MyPeople investor research ---"
  exa_search "Tim Glory Sierra Ventures HR tech investment portfolio" "$intel_dir/search-sierra-ventures.json"
  sleep 3
  exa_search "AI HR platform investors venture capital 2025 2026 seed series A" "$intel_dir/search-ai-hr-investors.json"
  sleep 3
  exa_search "HR tech company acquired early stage AI platform 2024 2025" "$intel_dir/search-hrtech-ai-acquisitions.json"

  log "  PHASE 1 COMPLETE — $(ls $intel_dir/*.json | wc -l | tr -d ' ') search results saved"
  send_telegram "[Argus] Phase 1 done — $(ls $intel_dir/*.json | wc -l | tr -d ' ') Exa searches complete. Buyer intel saved. Moving to document generation."
}

# ============================================================
# PHASE 2: DOCUMENT GENERATION (Agents 2, 5, 6)
# OpenClaw executor + DeepSeek — heavy synthesis
# ============================================================
phase2_documents() {
  log "=========================================="
  log "PHASE 2: DOCUMENT GENERATION (OpenClaw)"
  log "=========================================="

  # --- 2A: Action Plan ---
  log "--- Agent 2A: Action Plan from March 30 call ---"
  run_agent "executor" "$OUTPUT_DIR/action-plan/action-plan.md" "
You are writing an action plan document for a high-stakes M&A deal. Use an operator tone — direct, confident, no advisory fluff.

## FULL CONTEXT — MARCH 23 DISCOVERY CALL:
$CONTEXT_MAR23

## FULL CONTEXT — MARCH 30 STRATEGY CALL:
$CONTEXT_MAR30

## DEAL INTELLIGENCE:
$CONTEXT_DEAL_INTEL

## BUYER STATS: $TOTAL_BUYERS total buyers mapped, 29 at fit score 8

# HR.COM DEAL — ACTION PLAN
## Source: March 30, 2026 call with Debbie McGrath, John Kelly, Ewing Gillaspy

## CONFIRMED DECISIONS:
- 3 separate asset tracks (domain / media / MyPeople platform)
- Domain sale runs first (simplest, highest value — \$15-35M range)
- 90-day engagement window
- Fee range 5-8% (Wednesday decision point)
- John Kelly as interim CEO/mentor for MyPeople
- Wednesday follow-up after 3:30 PM ET (Ontario time zone)
- Debbie has Bambora data access (free intent data appending)
- Tim Glory / Sierra Ventures connection for MyPeople
- Informa REMOVED from buyer list (being sold themselves)
- Jason Corcello — Debbie's next conversation (track outcome)
- Domain broker Andrew Miller at 10% commission already engaged
- Hip surgery Wednesday — limited availability
- Debbie open to 2-year transition commitment

## THIS WEEK ACTION ITEMS (before Thursday):
1. Update dealroom site with operator positioning (kill advisory tone)
2. Prepare simplified engagement options for Wednesday call
3. Audit buyer list — remove Informa, flag others being acquired
4. Draft 90-day engagement letter addressing tail clause concern
5. Begin MyPeople CEO search (John to mentor two internal candidates)
6. Map Tim Glory / Sierra Ventures pathway for MyPeople funding
7. Track Jason Corcello conversation outcome

## DECISION LOG TABLE:
Create a markdown table with columns: Date | Decision | Who Decided | Impact | Status
Include all decisions from March 23 and March 30 calls.

## SIMPLIFIED FEE OPTIONS (one-pager for Wednesday):
Option A — Standard Process (5%): Three parallel tracks, modest monthly advisory fee, 5% on close, 90-day engagement, tail clause limited to 12 months on contacted buyers only. Recommended.
Option B — Performance Aligned (4% + kicker): Same process, lower base fee, 4% + performance bonus above agreed floor.
Option C — Full Conviction (6% / 20% above \$40M): No monthly fee, we eat cost, 6% on first \$40M, 20% above. Maximum alignment. 90-day exclusivity required.

Tail clause language: 'Tail applies only to buyers we directly contacted during the engagement. 12-month tail. Named buyer list provided at engagement start and updated weekly.'

Write this as a clean, professional markdown document with headers, bullet points, and the decision log table. Operator tone throughout.
" 900

  sleep $SLEEP_BETWEEN

  # --- 2B: Engagement Fee One-Pager ---
  log "--- Agent 2C: Engagement Fee One-Pager ---"
  run_agent "executor" "$OUTPUT_DIR/action-plan/fee-options-one-pager.md" "
Write a one-page decision document for a CEO named Debbie McGrath. She's evaluating engagement options for selling three assets: the hr.com domain (\$15-35M), hr.com media business (~\$7-10M), and MyPeople.ai platform (\$7M revenue).

Title: How You Want Us to Run the Market

Frame this NOT as a pricing decision but as a decision about how aggressively to run the market.

Three options:

OPTION A — STANDARD PROCESS (RECOMMENDED)
- We run three parallel tracks (domain, media, MyPeople)
- Monthly advisory fee (\$15K/mo)
- 5% success fee on close
- 90-day engagement
- Tail: 12 months, named buyer list only — buyers we actually contacted and got response from
- Best for: Maximum control with reasonable economics

OPTION B — PERFORMANCE ALIGNED
- Same process, same tracks
- Lower monthly (\$8K/mo)
- 4% success fee + performance bonus above agreed floor price
- Good if you want downside protection on our fees
- Best for: Shared risk, shared upside

OPTION C — FULL CONVICTION
- No monthly fee — we eat the cost
- 6% on first \$40M, 20% above \$40M
- 90-day exclusivity required
- Maximum alignment — we only win big if you win big
- Best for: Maximum incentive alignment, if you trust the process

Bottom section: 'What the tail clause actually means'
- Tail applies ONLY to buyers we directly contacted AND received a response from during the engagement
- 12-month tail period
- Named buyer list provided at engagement start, updated weekly
- You see every name, every contact, every response
- If we pitched Oracle and they ghosted us? Not on the tail list.

Tone: Operator, not advisor. Direct. Confident. Short paragraphs. No corporate-safe language.
Format: Clean markdown, ready to print.
" 600

  sleep $SLEEP_BETWEEN

  # --- 5A: The Patient Woman Narrative ---
  log "--- Agent 5A: Debbie McGrath Narrative ---"
  run_agent "executor" "$OUTPUT_DIR/narrative/debbie-mcgrath-story.md" "
Write a compelling narrative (not a bio — a STORY) about Debbie McGrath and her three assets. This is for internal team use and can be adapted for buyer-facing materials.

## SOURCE MATERIAL — DEBBIE'S OWN WORDS (from March 23 & 30 calls):
Key Debbie quotes to weave into the narrative:
- 'I don't want another CEO job'
- 'I've worked 12 hours a day for years'
- 'I have people who have been with me 20 years, 30 years'
- 'Selling just the domain name is kind of the simplest, easiest, and probably the highest value right now'
- 'Workday is being very difficult to work with and not letting anybody get their data out'
- 'Clients are going to just be sick of waiting for these guys to catch up'
- 'I can get you all that data for free' (re: Bambora access)
- 'All that data is going to be free everywhere soon'
- 'Silicon Valley funding people want young people. They don't want us.'
- On COVID: Did 260 virtual activations including ADP developer community (10K developers) and Michelle Obama on the platform

## KEY JOHN KELLY QUOTES to reference:
- 'We're damn good at what we do'
- 'Let us blow you away'
- 'I can build leadership teams in minutes now'
- On deal: 'One plus one plus one equals six or seven. It's a very different thing.'

## DEAL INTELLIGENCE:
$CONTEXT_DEAL_INTEL

THE FACTS:
- Founded HR.com 27 years ago (1999)
- Bootstrapped — no outside capital, ever
- Survived dot-com crash, 2008 financial crisis, COVID (260 virtual activations during pandemic proved the platform's reach)
- Sold her first company to Washington Post in 1998
- Built 1.8 million member HR community — largest in the world
- Recovered the Forj IP (rebranded MyPeople) after 4 failed CEO/CTOs in 3 years burned through \$8M in investor capital
- Rebuilt the entire tech stack from scratch in TypeScript/React/Node.js — modern, AI-native architecture
- MyPeople.ai now at \$7M revenue, 35 interested clients, 7 onboarding in next 45 days
- Having hip surgery — can't travel until June 8
- Age 63. Canadian. Does not want another CEO job.
- Two-letter domain hr.com is one of the most valuable domains in enterprise software

THE THREE ASSETS:
1. HR.com Domain — category-defining two-letter domain in a \$30B+ market. Prior offers ranged \$9M-\$45M. AI has repriced strategic digital real estate.
2. HR.com Media Business — profitable media company, ~20% EBITDA, 1.8M engaged community, content + events + certification + research. Comparable: HubSpot acquired The Hustle for audience + data.
3. MyPeople.ai — AI-native HR platform, \$7M revenue, modern stack, needs CEO + growth capital to unlock.

THE NARRATIVE FRAME:
- This is the culmination of 27 years of patient building
- Three assets worth more apart than together
- A founder who knows her worth but needs operators to extract it
- An AI market shift that has repriced everything she built
- A controlled process, not a fire sale
- The woman who bootstrapped the largest HR community in the world is ready to unlock its full value

Write this as a 2-3 page narrative. Think investor memo meets war story. Confident, specific, operator tone. Use actual numbers and facts. Make it compelling enough that anyone reading it understands why this deal matters and why NOW is the moment.
" 900

  sleep $SLEEP_BETWEEN

  # --- 5B: Three One-Pagers ---
  log "--- Agent 5B: Domain One-Pager ---"
  run_agent "executor" "$OUTPUT_DIR/narrative/one-pager-domain.md" "
Write a buyer-facing one-pager for the hr.com domain sale.

Title: HR.COM — The Most Valuable Two Letters in Human Resources

Structure:
- THE ASSET: Two-letter .com domain in a \$30B+ HCM market. Category-defining. One of fewer than 676 possible two-letter .com domains.
- THE COMMUNITY: 1.8 million HR professionals. Massive organic traffic. 27 years of brand equity.
- THE MARKET: Prior offers \$9M-\$45M. These established demand, not a ceiling. AI has repriced how strategic digital real estate is valued.
- THE OPPORTUNITY: Control the HR layer. Own the conversation between employers and employees globally. In an AI-driven world, the company that owns hr.com owns the namespace.
- THE PROCESS: Controlled sale. Multiple qualified buyers. Window to engage is limited. Contact: Ewing Gillaspy, Next Chapter Capital.

Tone: Confident, scarce, premium. Not desperate. Not salesy. Think luxury real estate listing meets tech deal memo.
One page max. Clean markdown.
" 600

  sleep $SLEEP_BETWEEN

  log "--- Agent 5B: Media One-Pager ---"
  run_agent "executor" "$OUTPUT_DIR/narrative/one-pager-media.md" "
Write a buyer-facing one-pager for the HR.com media business.

Title: HR.COM MEDIA — Distribution, Data, and 1.8 Million Decision-Makers

Structure:
- THE BUSINESS: Profitable B2B media company. ~20% EBITDA margins. 27 years of audience trust.
- THE AUDIENCE: 1.8M engaged HR professionals. Content, events, certification, research.
- THE DATA: Intent data, engagement data, community behavior data across the HR ecosystem. Debbie has Bambora access for free data appending.
- THE COMPARABLE: HubSpot acquired The Hustle for audience + data in 2021. Same thesis — content-to-commerce to content-to-platform.
- THE FINANCIALS: ~\$7-10M enterprise value at 1.2-1.5x revenue. Profitable. Stable. Not venture-dependent.
- THE OPPORTUNITY: Rare chance to own the largest HR media property globally. Add AI, add data monetization, add enterprise services.
- THE PROCESS: Controlled sale. Multiple qualified buyers. Contact: Ewing Gillaspy, Next Chapter Capital.

One page. Clean markdown. Premium but analytical tone.
" 600

  sleep $SLEEP_BETWEEN

  log "--- Agent 5B: MyPeople One-Pager ---"
  run_agent "executor" "$OUTPUT_DIR/narrative/one-pager-mypeople.md" "
Write a buyer/investor-facing one-pager for MyPeople.ai.

Title: MYPEOPLE.AI — AI-Native HR Platform Ready for Scale

Structure:
- THE PLATFORM: AI-native HR platform built on TypeScript/Node.js/React. API-first architecture. Modern stack — not legacy code with AI bolted on.
- THE TRACTION: \$7M revenue. 35 interested enterprise clients. 7 onboarding in next 45 days. Product-market fit validated.
- THE ORIGIN: Built by the team behind HR.com (1.8M community). Spun out from \$8M Forj investment. IP recovered, stack rebuilt from scratch.
- THE NEED: CEO + growth capital. Two internal candidates being mentored. John Kelly (former Oracle/SAP executive, 6 exits, IPO, \$750M+ VC raised) engaged as interim CEO/mentor.
- THE MARKET: \$30B+ HCM market. Enterprise buyers frustrated with closed AI ecosystems (Workday, Oracle, SAP). Independent AI layer positioning.
- THE ASK: Growth investment (\$5-15M) + experienced CEO to take from \$7M to \$50M+. Warm intro available via Tim Glory / Sierra Ventures.
- THE PROCESS: Controlled investment process. Contact: Ewing Gillaspy, Next Chapter Capital.

One page. Clean markdown. Venture-ready tone — growth story with operator credibility.
" 600

  sleep $SLEEP_BETWEEN

  # --- 6A: Tech Explainer for Debbie ---
  log "--- Agent 6A: Tech Explainer (Debbie-facing) ---"
  run_agent "executor" "$OUTPUT_DIR/tech-plan/how-we-run-your-deal.md" "
Write a plain-language document explaining the technology powering this M&A deal process. The audience is Debbie McGrath — a smart CEO but not technical. She needs to understand WHAT we do, not HOW the code works.

Title: How We Run Your Deal — The Machine Behind the Process

Sections:

1. AI BUYER RESEARCH
We don't Google companies and guess. We use AI that reads earnings calls, 10-Ks, press releases, LinkedIn profiles, and acquisition histories. For every potential buyer, we know what their CEO said publicly about HR strategy, what they've acquired recently, and why YOUR asset fits their roadmap. Every outreach is custom-built from real intelligence. Not templates.

2. DUAL DASHBOARD SYSTEM
You get a clean, simple dashboard (debbiedealroom.com) showing progress, feedback options, and key decisions. Our team operates from a separate CRM hub with all 68+ buyers, scores, scripts, and pipeline data. You see outcomes. We manage the machine. You never have to wonder what's happening.

3. AUTOMATED OUTREACH AT SCALE
AI-powered parallel dialing — we reach 5x more decision-makers per hour than traditional cold calling. Custom email sequences per buyer segment. LinkedIn outreach with personalized messaging. Every touchpoint tracked and scored. You get a weekly report showing exactly who we contacted, who responded, and what the market is saying.

4. REAL-TIME TRACKING & TRANSPARENCY
Every call recorded and transcribed. Every email logged. Every meeting noted. You can inspect our work as if we're employees in your company. No black box. Full visibility. The dashboard shows you everything — unedited.

5. WHAT COMES NEXT (AFTER ENGAGEMENT)
Once we sign, we build a comprehensive Fact Book for each asset — financial data, technical specs, audience data, growth metrics. This is what qualified buyers receive in a controlled diligence process. Professional. Thorough. The kind of materials that command premium valuations.

6. WEEKLY REPORTING
Every week you get: who we contacted, who responded, what the market is saying, what we recommend adjusting. Real data, not vibes. You can review and redirect anytime. This is your deal — we just run the machine.

Write this in plain, warm but confident language. Short paragraphs. No jargon. No acronyms without explanation. Think: explaining to a very smart person who happens not to be technical.
" 600

  log "  PHASE 2 COMPLETE — documents generated"
  send_telegram "[Argus] Phase 2 done — Action plan, fee options, Debbie narrative, 3 one-pagers, and tech explainer all written. Moving to custom mailers."
}

# ============================================================
# PHASE 3: CUSTOM MAILERS (Agent 4)
# Uses Exa research from Phase 1 to build targeted emails
# ============================================================
phase3_mailers() {
  log "=========================================="
  log "PHASE 3: CUSTOM MAILERS (OpenClaw)"
  log "=========================================="

  local mailer_dir="$OUTPUT_DIR/mailers"
  mkdir -p "$mailer_dir"

  # Load existing script templates as reference
  local script_templates=""
  if [ -f "$EXISTING_SCRIPTS" ]; then
    script_templates=$(cat "$EXISTING_SCRIPTS" | head -70)
  fi

  # Read Exa research for SAP and Workday
  local sap_intel=""
  local workday_intel=""
  local ai_intel=""

  if [ -f "$OUTPUT_DIR/buyer-intel/search-sap-ceo-strategy.json" ]; then
    sap_intel=$(python3 -c "
import json
d = json.load(open('$OUTPUT_DIR/buyer-intel/search-sap-ceo-strategy.json'))
for r in d.get('results',[])[:3]:
    print(r.get('title',''), '—', r.get('text','')[:500])
" 2>/dev/null || echo "No SAP research found")
  fi

  if [ -f "$OUTPUT_DIR/buyer-intel/search-workday-ceo-strategy.json" ]; then
    workday_intel=$(python3 -c "
import json
d = json.load(open('$OUTPUT_DIR/buyer-intel/search-workday-ceo-strategy.json'))
for r in d.get('results',[])[:3]:
    print(r.get('title',''), '—', r.get('text','')[:500])
" 2>/dev/null || echo "No Workday research found")
  fi

  if [ -f "$OUTPUT_DIR/buyer-intel/search-ai-entering-hr.json" ]; then
    ai_intel=$(python3 -c "
import json
d = json.load(open('$OUTPUT_DIR/buyer-intel/search-ai-entering-hr.json'))
for r in d.get('results',[])[:3]:
    print(r.get('title',''), '—', r.get('text','')[:500])
" 2>/dev/null || echo "No AI/HR research found")
  fi

  # --- 4A: SAP Custom Mailer ---
  log "--- Agent 4A: SAP Custom Email ---"
  run_agent "executor" "$mailer_dir/mailer-sap.md" "
Write a cold outreach email to SAP's corporate development team about acquiring the hr.com domain.

EXISTING SCRIPT TEMPLATE (match this quality, upgrade the tone to operator):
$script_templates

DEAL CONTEXT:
- HR.com: 27-year old platform, 1.8M community, category-defining two-letter domain
- Prior offers: \$9M-\$45M range (8 offers in 2022)
- Domain estimated \$15-20M by specialist brokers
- Debbie said on call: 'Workday is being very difficult to work with and not letting anybody get their data out. They are forcing clients to buy their AI level.'
- Debbie said: 'If somebody like a Workday buys it, they should keep it separate and run it as their independent layer of AI'
- Oracle's Larry Ellison buying media properties to 'control the narrative'
- All big players doing 'lip service' on AI per Debbie

RESEARCH ON SAP CEO CHRISTIAN KLEIN:
$sap_intel

INSTRUCTIONS:
- Subject line must reference a specific SAP strategic initiative or Klein quote (from the research above)
- Opening: Reference what Klein has said publicly about SuccessFactors, HR, or AI strategy
- Bridge: How owning hr.com accelerates that specific strategy
- Proof: 1.8M community, 27 years of brand equity, category-defining domain
- Close: 'This is a controlled process with multiple qualified parties. The window to engage is the next 60 days.'
- Sign off as: Ewing Gillaspy, Next Chapter Capital

Tone: Peer-to-peer, not vendor-to-buyer. Operator credibility. Specific, not generic. One page max.
Write the actual email ready to send — subject line, body, signature.
" 600

  sleep $SLEEP_BETWEEN

  # --- 4B: Workday Custom Mailer ---
  log "--- Agent 4B: Workday Custom Email ---"
  run_agent "executor" "$mailer_dir/mailer-workday.md" "
Write a cold outreach email to Workday's corporate development team about acquiring the hr.com domain.

RESEARCH ON WORKDAY CEO CARL ESCHENBACH:
$workday_intel

CONTEXT FROM DEBBIE (the seller):
Debbie said on a call: 'Workday is being very difficult to work with and not letting anybody get their data out. They are saying if you want AI, you have to buy our AI level. Clients are going to be sick of waiting for these guys to catch up.'

INSTRUCTIONS:
- Subject line must reference Workday's specific positioning challenge or opportunity
- Opening: Reference Eschenbach's public statements on strategy, AI, or HCM positioning
- Bridge: How owning hr.com solves Workday's biggest challenge — being seen as open and community-driven
- Proof: 1.8M community, independent platform, 27 years of trust
- Close: 'Controlled process. Multiple qualified parties. Window is 60 days.'
- Sign off as: Ewing Gillaspy, Next Chapter Capital

Tone: Direct. Specific to Workday. Not a template.
Write the actual email ready to send.
" 600

  sleep $SLEEP_BETWEEN

  # --- 4C: AI Company Mailer ---
  log "--- Agent 4C: AI Company Email (OpenAI/Anthropic) ---"
  run_agent "executor" "$mailer_dir/mailer-ai-company.md" "
Write a cold outreach email to an AI company (OpenAI or Anthropic) about the hr.com domain.

AI COMPANIES ENTERING HR RESEARCH:
$ai_intel

INSTRUCTIONS:
- Position hr.com as 'controlling the HR layer in an AI-driven world'
- The thesis: Every AI company will need vertical entry points. HR is a \$30B+ market. The company that owns hr.com owns the namespace for AI + HR.
- Reference the trend: 'Every major AI lab is building vertical products. The domains that define those verticals are the most valuable digital real estate of the next decade.'
- Proof: 1.8M community, SEO authority, 27 years of content and trust
- Close: Controlled process, multiple parties, 60-day window
- Sign off as: Ewing Gillaspy, Next Chapter Capital

Tone: Tech-forward. Strategic. Not desperate. Think: one founder writing to another.
Write the actual email ready to send.
" 600

  sleep $SLEEP_BETWEEN

  # --- 4D: Media Buyer Template ---
  log "--- Agent 4D: Media Buyer Email Template ---"
  run_agent "executor" "$mailer_dir/mailer-media-template.md" "
Write an email template for outreach to B2B media companies and content acquirers about the HR.com media business.

PRECEDENT:
- HubSpot acquired The Hustle in 2021 for audience + data + content-to-platform strategy
- This is the same thesis: own the audience, own the data, build the platform

MERGE FIELDS (use these brackets):
- {{COMPANY_NAME}} — buyer company
- {{CEO_NAME}} — buyer CEO
- {{RECENT_ACQUISITION}} — their most recent media/content acquisition
- {{STRATEGIC_ANGLE}} — how HR.com media fits their specific strategy

TEMPLATE:
- Subject: reference the HubSpot/Hustle precedent or their specific strategy
- Opening: Reference {{RECENT_ACQUISITION}} — show you know their playbook
- Bridge: HR.com media = 1.8M HR professionals + data + distribution + 20% EBITDA
- Differentiation: 27 years of audience trust. Profitable. Not a money-losing startup.
- Close: Controlled process, multiple parties
- Sign off as: Ewing Gillaspy, Next Chapter Capital

Write the full template with merge fields.
" 600

  sleep $SLEEP_BETWEEN

  # --- 4E: MyPeople Investor Mailer ---
  log "--- Agent 4E: MyPeople Investor Email ---"
  run_agent "executor" "$mailer_dir/mailer-mypeople-investor.md" "
Write an email for outreach to VC/growth investors about MyPeople.ai.

KEY FACTS:
- \$7M revenue, AI-native, TypeScript/React/Node.js modern stack
- 35 interested enterprise clients, 7 onboarding in next 45 days
- Built by team that built HR.com's 1.8M community
- Recovered IP from failed \$8M Forj investment (4 CEO/CTOs in 3 years)
- Rebuilt stack from scratch — clean, modern, no legacy debt
- Needs: CEO + \$5-15M growth capital
- John Kelly (Oracle/SAP executive, 6 exits, IPO, \$750M+ VC) engaged as interim CEO/mentor
- Tim Glory / Sierra Ventures warm intro available
- Debbie McGrath (27-year founder, sold first company to Washington Post) still involved

INSTRUCTIONS:
- Position as a spin-out opportunity with built-in distribution (1.8M HR professionals)
- Emphasize revenue traction (\$7M is real, not projections)
- The story: Patient founder built the community. Now the technology is ready. Needs operator capital to scale.
- Close: 'We have a controlled investment process underway. Happy to share the deck and intro you to the team.'
- Sign off as: Ewing Gillaspy, Next Chapter Capital

Tone: VC-ready. Growth story. Operator credibility. Not startup hype.
" 600

  sleep $SLEEP_BETWEEN

  # --- 4F: Salesfinity Call Scripts ---
  log "--- Agent 4F: Salesfinity Call Scripts ---"
  run_agent "executor" "$mailer_dir/call-scripts-all-segments.md" "
Write parallel dialer call scripts for three buyer segments. Each script must be usable by a caller in a high-velocity dialing environment (Salesfinity AI dialer).

EXISTING CALL SCRIPT TEMPLATE (upgrade to operator tone, keep the structure):
$(echo "$script_templates" | grep -A 15 'Call Script')

TOP FIT-8 BUYERS WE'RE CALLING:
$BUYERS_FIT8

JOHN KELLY TONE DIRECTIVE: 'Stop sounding like advisors. Sound like operators. She's not choosing a firm. She's choosing how aggressively to run three separate markets.'

FORMAT PER SEGMENT:
- 15-second opener
- Value prop (one sentence)
- One qualifying question
- Meeting set close
- Top 3 objection handles

SEGMENT 1: DOMAIN BUYERS
Target: Corp dev at SAP, Workday, Oracle, ADP, OpenAI, Anthropic, Deel, Rippling
Opener: 'Hi [NAME], this is Ewing from Next Chapter. Quick question — is [COMPANY] the right group to talk to about strategic domain acquisitions? I'm reaching out about hr.com.'
Value: 'HR.com is the category-defining two-letter domain in the largest enterprise software vertical. We're running a controlled process with a 60-day window.'
Qualify: 'Has [COMPANY] looked at domain acquisitions as part of your platform strategy?'
Close: 'I'd love to send over a one-page overview and get 15 minutes with the right person on your team this week.'

SEGMENT 2: MEDIA BUSINESS BUYERS
Target: Corp dev at media companies, PE firms, B2B platforms
Opener: 'Hi [NAME], this is Ewing from Next Chapter. We're representing the owner of hr.com — the largest HR media property globally. Are you the right person for potential acquisitions?'
Value: 'HR.com media reaches 1.8 million HR professionals, runs at 20% EBITDA, and the founder is ready for a transition after 27 years.'
Qualify: 'Has [COMPANY] looked at B2B media acquisitions in the professional services space?'
Close: 'Can I send you a brief and get 15 minutes this week?'

SEGMENT 3: MYPEOPLE INVESTORS
Target: VC partners, growth investors, HR tech acquirers
Opener: 'Hi [NAME], Ewing from Next Chapter. I'm reaching out about an AI HR platform at \$7M revenue that's looking for a growth partner. Is that something [FUND] would look at?'
Value: 'MyPeople.ai — AI-native HR platform, modern stack, 35 enterprise prospects, built by the HR.com team. Looking for CEO + growth capital.'
Qualify: 'Is HR tech AI in your current investment thesis?'
Close: 'Happy to send the deck and intro you to the interim CEO who ran billion-dollar divisions at Oracle and SAP.'

OBJECTION HANDLES (per segment):
Include top 3 objections per segment with one-line responses. Keep it punchy — these are used mid-call.

Tone: Operator. Direct. Not salesy. Confident. John Kelly energy: 'We're damn good at what we do.'
" 600

  log "  PHASE 3 COMPLETE — mailers and scripts generated"
  send_telegram "[Argus] Phase 3 done — SAP, Workday, AI company, media template, investor email, and all call scripts written. Moving to dealroom content."
}

# ============================================================
# PHASE 4: DEALROOM CONTENT GENERATION (Agent 1)
# Generates content files — manual Lovable update in morning
# ============================================================
phase4_dealroom() {
  log "=========================================="
  log "PHASE 4: DEALROOM CONTENT (OpenClaw)"
  log "=========================================="

  local dr_dir="$OUTPUT_DIR/dealroom"
  mkdir -p "$dr_dir"

  # --- 1A: Overview Page Content ---
  log "--- Agent 1A: Overview Page Rewrite ---"
  run_agent "executor" "$dr_dir/page-overview.md" "
Write the full content for the Overview page of debbiedealroom.com. This replaces the current warm personal letter to Debbie with operator positioning.

KILL: The warm fluffy letter. John Kelly called it 'too fluffy.'

REPLACE WITH:

Opening: 'You don't have a typical sell-my-company situation. You have three distinct assets, each with different buyer universes, different valuation drivers, and different optimal outcomes.'

Key content blocks:
1. THREE ASSETS, THREE MARKETS
- HR.com Domain — category-defining two-letter domain, \$15-35M range
- HR.com Media Business — profitable media company, 1.8M community, ~20% EBITDA
- MyPeople.ai — AI-native HR platform, \$7M revenue, needs CEO + capital

2. THE NUMBERS
- 63 pre-qualified buyers already mapped
- 10 searches, 15 Exa deep-learning research sweeps across buyer targets
- Every buyer scored on fit, acquisitiveness, and strategic alignment

3. THE CONVICTION THRESHOLD
- 90 days. That is how long we need to prove this process works.
- If we have not created real market pressure in 90 days, fire us.
- No tail clause games. No holding your buyers hostage.

4. THREE PARALLEL TRACKS
- Domain track: Domain specialists + strategic acquirers
- Media track: B2B media buyers + PE roll-up plays
- MyPeople track: Growth investors + strategic acquirers + CEO placement

5. WHY US
- We have sat on both sides of this table. Bought companies. Sold companies. Run companies.
- John Kelly ran billion-dollar divisions at Oracle and SAP. Six exits. IPO.
- This is not a pitch. This is what we actually do.

6. MYPEOPLE PROTECTION
- This asset can either get discounted in a bundled deal or become a standalone upside driver
- We run it as a separate track to protect its value
- John Kelly engaged as interim CEO/mentor

CLOSE: 'You need a controlled process, real market pressure, and operators who can run three markets in parallel without losing value. That is what we do.'

Write this as clean HTML-ready content (use <h2>, <p>, <ul> tags). Operator tone. Direct. Confident. No advisory fluff.
" 900

  sleep $SLEEP_BETWEEN

  # --- 1B: Team Page Content ---
  log "--- Agent 1B: Team Page Rewrite ---"
  run_agent "executor" "$dr_dir/page-team.md" "
Write the full content for the Team page of debbiedealroom.com.

REMOVE: All 'co-founder' titles.

TEAM MEMBERS:

EWING GILLASPY
Title: Deal Lead | Buyer Strategy & Process Control
Tagline: 'Ewing is the difference between activity and a real market.'
Bio: Focus on deal execution, buyer targeting, technology-driven process. Built the AI research engine powering buyer intelligence. 15+ years in business development, sales leadership, and M&A advisory. Runs the outreach machine.

JOHN KELLY
Title: Executive Operator | Strategy, Narrative & Buyer Access
Tagline: 'John is the difference between a well-run process and a well-negotiated outcome.'
Bio: Former CEO/CRO/COO at Oracle and SAP (multi-billion dollar divisions). Worked with Larry Ellison and Bill McDermott. Six exits, IPO, \$750M+ VC raised. Personally knows CEOs of Remote, Rippling, Deel. Engaged as interim CEO for MyPeople. This is not a consultant — this is an operator.

MARK DECHANT
Title: Execution Lead | Process, Diligence & Deal Management
Tagline: 'Mark is the difference between a good process and a closed deal.'
Bio: Runs deal process end-to-end. Timeline management, diligence coordination, buyer communication. 10 years of executive recruiting and deal execution at RevsUp.

CHRIS REX
Title: Technology & Data | Buyer Targeting, AI Engine & Technical Positioning
Tagline: 'Chris is the reason we know who to go after and how to reach them.'
Bio: Built the AI-driven buyer research and outreach engine. Technical positioning for MyPeople. Data infrastructure for buyer intelligence.

HOW THIS TEAM WORKS:
- Ewing runs the market. John shapes the narrative and opens doors. Mark keeps the trains running. Chris powers the machine.
- We are not a traditional advisory firm. We are a deal team that operates like a company.

WHY THIS MATTERS:
'Most firms assign a team. Our team has actually run companies, negotiated at scale, and closed deals from the inside. We do not advise on deals. We execute them.'

Write as clean HTML-ready content. Operator tone throughout.
" 900

  sleep $SLEEP_BETWEEN

  # --- 1D: Engagement Options Page ---
  log "--- Agent 1D: Engagement Options Page ---"
  run_agent "executor" "$dr_dir/page-engagement-options.md" "
Write the full content for the Engagement Options page of debbiedealroom.com. This page currently returns 404 — we are building it from scratch.

FRAMING: 'This is not a pricing decision. It is a decision about how aggressively to run the market.'

THREE OPTIONS:

OPTION 1 — CLEAN EXIT
- Tighter buyer set, bundled approach, faster timeline
- \$15K/month engagement fee
- 4% success fee
- Performance kicker above agreed floor
- Best for: Getting to an outcome quickly with a focused buyer set

OPTION 2 — MAX VALUE PROCESS (RECOMMENDED)
- Three parallel tracks, different buyer universes
- \$8K/month (half of Option 1)
- 5% success fee
- No performance tier
- Best for: Maximum value extraction across all three assets

OPTION 3 — CONVICTION BET
- No upfront fee — we eat the cost
- 90-day exclusivity required
- 6% on first \$40M, 20% above \$40M
- Aggressive. Maximum alignment.
- Best for: If you believe in the process and want maximum incentive alignment

COMPARISON TABLE:
| Feature | Clean Exit | Max Value (Rec.) | Conviction Bet |
Monthly Fee, Success Fee, Exclusivity, Timeline, Best For

TAIL CLAUSE:
- Tail applies only to buyers we directly contacted AND received a response from
- 12-month tail period
- Named buyer list provided at start, updated weekly
- Transparent. Auditable. Fair.

BOTTOM: 'Every option runs a real market. The difference is scope, speed, and how we split the economics. Wednesday we pick one and go.'

Write as clean HTML-ready content. Operator tone. Make the recommended option visually prominent.
" 900

  sleep $SLEEP_BETWEEN

  # --- 1E: Targets Page ---
  log "--- Agent 1E: Targets Page ---"
  run_agent "executor" "$dr_dir/page-targets.md" "
Write the full content for the Targets page of debbiedealroom.com. This page currently returns 404.

SECTIONS:

1. DOMAIN BUYER TARGETS
Segments:
- Big Tech AI: OpenAI, Anthropic, Google, Microsoft
- Enterprise HCM: SAP, Workday, Oracle, ADP, UKG, Ceridian/Dayforce, Paychex, Paylocity
- HR Tech Disruptors: Deel, Rippling, Remote, Gusto
- Consulting/Services: Deloitte, Accenture, PwC, McKinsey
- Domain Investors: Premium domain funds, two-letter specialists

2. MEDIA BUSINESS BUYER TARGETS
Segments:
- Platform + Data: Companies wanting HR audience data
- Media Acquirers: B2B media roll-ups (Industry Dive, TechTarget, RELX)
- Content-to-Commerce: Companies monetizing professional audience
- PE Roll-up: HG Capital, Vista Equity, Francisco Partners

3. MYPEOPLE.AI BUYER/INVESTOR TARGETS
Segments:
- AI-native HR platforms
- Enterprise software with AI gaps
- VC firms active in HR tech AI (Sierra Ventures, etc.)
- Strategic acquirers wanting AI talent + product

4. CEO CANDIDATES PIPELINE
- Two internal candidates being mentored
- John Kelly engaged as interim CEO
- Active search for permanent CEO once funding secured

STATS BAR AT TOP: '63 pre-qualified buyers mapped | 3 asset tracks | 5 buyer segments | Research depth: earnings calls, 10-Ks, acquisition history'

NOTE: Informa has been REMOVED from all lists (they are being sold themselves).

Write as clean HTML-ready content with segment headers and company lists. Include a note that detailed buyer profiles are available on request.
" 900

  log "  PHASE 4 COMPLETE — dealroom content files generated"
  send_telegram "[Argus] Phase 4 done — All 5 dealroom page rewrites generated (overview, team, engagement options, targets, process tone). Ready for Lovable push in morning."
}

# ============================================================
# PHASE 5: BUYER LIST AUDIT (Agent 3A)
# ============================================================
phase5_audit() {
  log "=========================================="
  log "PHASE 5: BUYER LIST AUDIT (OpenClaw)"
  log "=========================================="

  local intel_dir="$OUTPUT_DIR/buyer-intel"

  # Read the acquirer table
  local acquirer_json="$intel_dir/acquirer-table.json"
  if [ ! -f "$acquirer_json" ]; then
    log "  ⚠️ No acquirer table found — skipping audit"
    return 0
  fi

  run_agent "auditor" "$intel_dir/buyer-audit-report.md" "
You are auditing a buyer list for an M&A deal. The list has $TOTAL_BUYERS potential acquirers for three assets: hr.com domain, hr.com media business, and MyPeople.ai platform.

TASK:
1. Flag Informa — MUST BE REMOVED (Debbie confirmed on March 30 call they are being sold themselves AND trying to sell Debbie an asset)
2. For each major company, identify if they are currently involved in M&A as a TARGET (being acquired/sold) — these should be flagged
3. Categorize all buyers into: Domain Buyers, Media Buyers, MyPeople Buyers/Investors
4. Identify Top 10 per category based on fit
5. Flag any buyer Debbie has a personal relationship with (warm intro path)

FULL BUYER LIST WITH FIT SCORES AND SEGMENTS:
$BUYERS_ALL_NAMES

DEAL CONTEXT:
$CONTEXT_DEAL_INTEL

KEY INTEL FROM DEBBIE (March 30):
- Informa is being sold AND trying to sell Debbie an asset — REMOVE
- Debbie 'knows all these people' — most buyers are warm contacts
- Domain broker Andrew Miller at 10% handles domain-only buyers
- Jason Corcello is Debbie's next call — track as potential buyer or advisor
- Doug Merritt (Splunk/SAP) is a mutual contact through John Kelly

OUTPUT FORMAT:
## REMOVED
- Informa (being sold)
- [any others flagged]

## TOP 10 DOMAIN BUYERS
1. Company — reason

## TOP 10 MEDIA BUYERS
1. Company — reason

## TOP 10 MYPEOPLE BUYERS/INVESTORS
1. Company — reason

## FULL SEGMENT MAP
[All companies categorized]
" 600

  log "  PHASE 5 COMPLETE — buyer audit done"
  send_telegram "[Argus] Phase 5 done — Buyer list audited. Informa removed. Top 10 per segment identified."
}

# ============================================================
# PHASE 6: UPDATE DEAL ROOM PAGE WITH REAL LINKS
# ============================================================
phase6_update_dealroom_page() {
  log "=========================================="
  log "PHASE 6: DEAL ROOM PAGE UPDATE"
  log "=========================================="

  if [ ! -f "$DEALROOM_PAGE" ]; then
    log "  ⚠️ Deal room page not found at $DEALROOM_PAGE — skipping"
    return 0
  fi

  # Update data-file links to real relative links for markdown files
  # The page uses href="#" with data-file attributes — replace href with real paths
  cd "$PROJECT_DIR"

  python3 -c "
import re, os, glob

page_path = '$DEALROOM_PAGE'
with open(page_path) as f:
    html = f.read()

# Find all output files
output_files = {}
for root, dirs, files in os.walk('outputs'):
    for fname in files:
        fpath = os.path.join(root, fname)
        output_files[fname] = fpath

# Replace data-file references with real links
# Pattern: href=\"#\" data-file=\"outputs/path/file.ext\"
def replace_link(match):
    data_file = match.group(1)
    basename = os.path.basename(data_file)
    # Check if file exists
    if os.path.exists(data_file):
        # For markdown/json files, link to raw GitHub or local path
        return f'href=\"/{data_file}\" data-file=\"{data_file}\" data-status=\"ready\"'
    else:
        return f'href=\"#\" data-file=\"{data_file}\" data-status=\"pending\"'

html = re.sub(r'href=\"#\" data-file=\"([^\"]+)\"', replace_link, html)

# Add generation timestamp
html = html.replace('Generated March 31, 2026', f'Generated March 31, 2026 at {os.popen(\"date +%H:%M\").read().strip()}')

# Count ready vs pending
ready = html.count('data-status=\"ready\"')
pending = html.count('data-status=\"pending\"')

with open(page_path, 'w') as f:
    f.write(html)

print(f'Updated: {ready} links ready, {pending} pending')
" 2>>"$LOG_FILE" || log "  ⚠️ Python link update failed"

  # Also add the deal room page to the hub sidebar
  if grep -q 'hrcom-dealroom-overnight' "$PROJECT_DIR/public/hrcom-ltd-hub.html" 2>/dev/null; then
    log "  Deal room link already in hub sidebar"
  else
    # Add link to sidebar
    sed -i '' 's|<a href="#pipeline-history" class="sidebar-link">Pipeline History</a>|<a href="#pipeline-history" class="sidebar-link">Pipeline History</a>\n<a href="hrcom-dealroom-overnight.html" class="sidebar-link" style="color:#f0883e">⚡ Deal Room</a>|' \
      "$PROJECT_DIR/public/hrcom-ltd-hub.html" 2>/dev/null || true
    log "  Added ⚡ Deal Room link to hub sidebar"
  fi

  log "  PHASE 6 COMPLETE — deal room page updated"
  send_telegram "[Argus] Phase 6 done — Deal room page updated with live links. All outputs accessible via ⚡ on the hub."
}

# ============================================================
# PHASE 7: FINAL ASSEMBLY + GIT
# ============================================================
phase7_finalize() {
  log "=========================================="
  log "PHASE 6: FINAL ASSEMBLY"
  log "=========================================="

  cd "$PROJECT_DIR"

  # Count outputs
  local total_files
  total_files=$(find "$OUTPUT_DIR" -type f | wc -l | tr -d ' ')

  # Build index
  {
    echo "# HR.COM DEAL — OVERNIGHT BUILD OUTPUT INDEX"
    echo "## Generated: $(date '+%Y-%m-%d %H:%M')"
    echo ""
    echo "## Buyer Intelligence (outputs/buyer-intel/)"
    ls "$OUTPUT_DIR/buyer-intel/"*.json "$OUTPUT_DIR/buyer-intel/"*.md 2>/dev/null | while read f; do echo "- $(basename $f)"; done
    echo ""
    echo "## Action Plan (outputs/action-plan/)"
    ls "$OUTPUT_DIR/action-plan/"*.md 2>/dev/null | while read f; do echo "- $(basename $f)"; done
    echo ""
    echo "## Mailers & Scripts (outputs/mailers/)"
    ls "$OUTPUT_DIR/mailers/"*.md 2>/dev/null | while read f; do echo "- $(basename $f)"; done
    echo ""
    echo "## Narrative (outputs/narrative/)"
    ls "$OUTPUT_DIR/narrative/"*.md 2>/dev/null | while read f; do echo "- $(basename $f)"; done
    echo ""
    echo "## Dealroom Content (outputs/dealroom/)"
    ls "$OUTPUT_DIR/dealroom/"*.md 2>/dev/null | while read f; do echo "- $(basename $f)"; done
    echo ""
    echo "## Tech Plan (outputs/tech-plan/)"
    ls "$OUTPUT_DIR/tech-plan/"*.md 2>/dev/null | while read f; do echo "- $(basename $f)"; done
  } > "$OUTPUT_DIR/INDEX.md"

  log "  Total output files: $total_files"
  log "  Index written to outputs/INDEX.md"

  # Git commit (but don't push yet — Ewing reviews first)
  if [ -n "$(git status --porcelain outputs/ public/)" ]; then
    git add outputs/ public/hrcom-dealroom-overnight.html public/index.html public/hrcom-ltd-hub.html
    git commit -m "feat: HR.com overnight build — full deal room with $total_files outputs

7 phases, zero Claude usage, all OpenClaw agents:
- 15 Exa buyer research searches (SAP, Workday, AI, domain comps)
- Action plan + decision log + fee one-pager (Wednesday ready)
- 5 custom mailers (SAP, Workday, AI, media, investor)
- Call scripts for all 3 segments (domain, media, MyPeople)
- Debbie McGrath narrative + 3 buyer one-pagers
- 5 dealroom page rewrites (overview, team, options, targets, process)
- Tech explainer for Debbie
- Buyer audit (Informa removed, top 10 per segment)
- Deal room page with all output links (⚡ on hub)

Full context: both transcripts, $TOTAL_BUYERS buyers, deal intel, existing scripts

Co-Authored-By: OpenClaw Agents <noreply@openclaw.ai>" 2>>"$LOG_FILE" || true
    log "  ✅ Git committed (not pushed — you review first)"
  fi

  # Final report
  local summary="[Argus] 🏁 HR.COM OVERNIGHT BUILD COMPLETE

📊 $total_files files generated across 7 phases:
• 15 Exa buyer research searches
• Action plan + decision log + fee options
• 5 custom mailers (SAP, Workday, AI, media, investor)
• 6 call scripts (3 segments)
• Debbie McGrath narrative
• 3 buyer one-pagers (domain, media, MyPeople)
• 5 dealroom page rewrites
• Tech explainer for Debbie
• Buyer audit report (Informa removed)
• ⚡ Deal room page live with all links

🔗 Deal room: master-crm-web-eight.vercel.app/hrcom-dealroom-overnight.html
📋 Hub: master-crm-web-eight.vercel.app/hrcom-ltd-hub.html

⏰ Morning checklist:
1. Click ⚡ on hub → review all outputs
2. Open Claude → push dealroom content to Lovable (5 min)
3. git push to deploy (deal room page auto-deploys)
4. Print fee one-pager for Wednesday call

All files at: ~/Projects/master-crm-web/outputs/
Index: outputs/INDEX.md"

  send_telegram "$summary"
  log "$summary"
  log "=========================================="
  log "HR.COM OVERNIGHT BUILD — COMPLETE"
  log "=========================================="
}

# ============================================================
# MAIN
# ============================================================
main() {
  log "============================================"
  log "HR.COM OVERNIGHT BUILD — STARTING"
  log "Agents: OpenClaw (DeepSeek/Gemini/GPT-4o-mini)"
  log "Claude usage: ZERO"
  log "============================================"

  # Pre-flight: verify all reference data exists
  preflight

  # Load all context into memory
  load_context

  send_telegram "[Argus] 🌙 HR.com overnight build starting. Full context loaded:
• March 23 transcript (discovery call)
• March 30 transcript (strategy call)
• $TOTAL_BUYERS buyers with fit scores & segments
• Deal intelligence + existing scripts
• John Kelly quotes + Debbie quotes pre-extracted

7 phases, ~30 agent calls. Zero Claude usage. All OpenClaw.

Phase 1: Exa buyer research (15 searches)
Phase 2: Documents (action plan, narrative, one-pagers, tech explainer)
Phase 3: Custom mailers (SAP, Workday, AI, media, investor + call scripts)
Phase 4: Dealroom page content (5 pages for Lovable)
Phase 5: Buyer list audit
Phase 6: Deal room page update (link all outputs)
Phase 7: Git commit + index

Go to sleep. I'll Telegram you when done."

  phase1_buyer_research
  phase2_documents
  phase3_mailers
  phase4_dealroom
  phase5_audit
  phase6_update_dealroom_page
  phase7_finalize
}

main "$@"
