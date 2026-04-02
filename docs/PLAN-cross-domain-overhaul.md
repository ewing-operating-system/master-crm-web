# Cross-Domain CRM Engine — Overhaul Plan

**Date:** 2026-04-02
**Author:** Claude (Argus) + Ewing Gillaspy
**Status:** DRAFT — take to Claude Desktop for architecture review
**Recommended tool:** Claude Desktop (Projects) for analysis, Claude Code for implementation

---

## Executive Summary

Next Chapter's research pipeline, agent system, and data model are hard-coded to home services M&A. With the HR.com deal imminent and AND Capital / RevsUp still unbuilt, this must become a multi-vertical engine. This plan covers 5 workstreams in priority order, each designed to ship incrementally — not as a big-bang rewrite.

---

## Current State (What's Broken)

### Hard-Coded to Home Services
| Component | Home Services Lock-In | What Cross-Domain Needs |
|-----------|----------------------|------------------------|
| `SOUL.md` (openclaw) | "HVAC, plumbing, roofing, pest" in identity | Vertical passed as config per task |
| `buyer_research_plan.md` | "193 PE firms in home services" | Buyer list per engagement |
| Research sections | 7 sections (company overview → approach) | Variable sections per vertical |
| Exa templates | Generic company/financial searches | Domain-specific search templates |
| Buyer scoring | Fit score 4/6/8 with acquisition evidence | Scoring criteria vary by vertical |
| Agent identities | "Extract structured company intelligence from web search results" about home services | Vertical-agnostic workers that receive task-scoped instructions |
| Letter templates | Home services owner stories, "started with one truck" | Domain-specific hooks and language |
| Supabase schema | `targets` table designed for sell-side home services companies | Universal schema with entity/vertical tags |

### Two Disconnected Systems
| System | Context Source | Models | Output Destination |
|--------|--------------|--------|-------------------|
| Claude Code | `CLAUDE.md`, memory files, git repo | Claude Opus 4.6 | Static JSON → git → Vercel |
| OpenClaw | `SOUL.md`, `IDENTITY.md`, workspace memory | DeepSeek, Gemini Flash, GPT-4o-mini | Supabase `targets`, `pipeline_log` |

These never sync. Changes in one are invisible to the other.

### Dead Infrastructure
- OpenClaw DeepSeek key: 401 (dead)
- OpenClaw Groq key: 401 (dead)
- OpenClaw OpenRouter key: 200 (works — 7 of 10 agents can run)
- Dossier pipeline in SOUL.md: describes a different deal, different audience, different methodology
- `buyer_research_plan.md`: targets 193 PE firms for home services — not applicable to HR.com

---

## Workstream 1: Multi-Vertical Domain Onboarding

**Priority:** HIGHEST — blocks everything else
**Timeline:** Design this week, implement next week
**Tool:** Claude Code for implementation, Claude Desktop for schema design

### The Process (triggered when a new client signs)

```
NEW CLIENT SIGNS
     │
     ▼
┌─────────────────────────┐
│ 1. DOMAIN HOMEWORK      │  ← Research the INDUSTRY, not the company
│    - EBITDA multiples    │     "What do HR media companies sell for?"
│    - Comp transactions   │     "Who bought what, for how much, recently?"
│    - Industry levers     │     "What makes an HR media co more valuable?"
│    - Market size / TAM   │     "How big is this space?"
│    - Key terminology     │     "What do buyers in THIS space care about?"
└─────────┬───────────────┘
          │
          ▼
┌─────────────────────────┐
│ 2. CLIENT PROFILE        │  ← Research the SPECIFIC company
│    - Revenue/EBITDA      │     From client + public sources
│    - Unique assets       │     HR.com: domain name, 2M+ audience, certification
│    - Growth levers       │     What could a buyer unlock? (content → SaaS, etc.)
│    - Pain points         │     What's holding them back alone?
│    - Seller motivation   │     Why NOW?
└─────────┬───────────────┘
          │
          ▼
┌─────────────────────────┐
│ 3. BUYER IDENTIFICATION  │  ← Find 50-100 potential acquirers
│    - Strategic buyers    │     Companies that would merge/absorb
│    - Financial buyers    │     PE firms active in this vertical
│    - Adjacency buyers    │     Companies in adjacent verticals
│    - Score each: 4/6/8   │     Based on acquisition evidence
│    - City, state, ticker │     For page rendering
└─────────┬───────────────┘
          │
          ▼
┌─────────────────────────┐
│ 4. DEEP BUYER RESEARCH   │  ← Per-buyer pages (what we built for Debbie)
│    - 10 research sections│     Config-driven (see Workstream 2)
│    - Product discovery   │     What do they sell? Per-product reviews
│    - Golden nuggets      │     Quotes, culture, conversation openers
│    - Stock data          │     If public
│    - PAIN/GAIN MATCHING  │     ← THE CRITICAL PIECE (see below)
└─────────┬───────────────┘
          │
          ▼
┌─────────────────────────┐
│ 5. OUTREACH GENERATION   │  ← Letters, emails, call scripts
│    - Letter per buyer    │     Cites research, buyer-specific hooks
│    - Review + approve UX │     Source-cited, 3-min hallucination audit
│    - Lob integration     │     Print + mail
│    - Follow-up sequence  │     Email, LinkedIn, call
└─────────────────────────┘
```

### The Pain/Gain Matching Engine (the "linkage that breaks the door open")

This is the highest-value component. For each buyer, produce:

```json
{
  "buyer": "SAP SuccessFactors",
  "client": "HR.com",
  "matches": [
    {
      "buyer_pain": "SAP struggles with mid-market adoption — enterprise-only perception",
      "buyer_source": "Q4 2024 earnings call, Christian Klein",
      "buyer_source_url": "https://seekingalpha.com/article/4752487",
      "client_solves": "HR.com has 2M+ mid-market HR professionals — instant mid-market channel",
      "talking_point": "Your mid-market gap is exactly what HR.com's audience fills",
      "letter_hook": "I noticed your Q4 commentary about expanding beyond enterprise..."
    },
    {
      "buyer_pain": "Content marketing costs growing faster than pipeline",
      "buyer_source": "G2 competitor analysis, 2025",
      "buyer_source_url": "https://www.g2.com/compare/...",
      "client_solves": "HR.com produces 500+ pieces of original HR content/year — built-in content engine",
      "talking_point": "Why build a content team when you can acquire one with 2M subscribers?",
      "letter_hook": "HR.com's content engine produces what your marketing team is trying to build..."
    }
  ]
}
```

**How it works:**
1. Buyer research produces `sections.ceo_vision`, `sections.competitive_moat`, `market_reputation.product_reviews` (negative = pains)
2. Client profile produces unique assets and growth levers
3. A synthesis step (LLM) matches buyer pains → client solutions
4. Output is stored per-buyer and fed into letter generation

This is where multi-agent competition matters: 3 agents independently match pains to gains, then we merge the best matches.

### Domain Config File

Each vertical gets a config file (not code):

```json
{
  "vertical": "hr_media",
  "display_name": "HR Media & Technology",
  "research_sections": [
    {"key": "hr_media_business", "title": "Media Business Model", "templates": ["company_search", "company_financials"]},
    {"key": "hr_domain_name", "title": "Domain Name Value", "templates": ["strategic_fit"]},
    {"key": "market_reputation", "title": "Market Reputation", "templates": ["reviews_search"]},
    {"key": "strategic_fit", "title": "Strategic Fit", "templates": ["strategic_fit", "company_financials"]},
    {"key": "ceo_vision", "title": "CEO Vision & Strategy", "templates": ["earnings_call"]},
    {"key": "ma_appetite", "title": "M&A Appetite", "templates": ["ma_history"]},
    {"key": "competitive_moat", "title": "Competitive Moat", "templates": ["strategic_fit"]},
    {"key": "earnings_quotes", "title": "Key Earnings Quotes", "templates": ["earnings_call"]},
    {"key": "approach_strategy", "title": "Approach Strategy", "templates": ["buyer_contacts"]},
    {"key": "golden_nuggets", "title": "Golden Nuggets", "templates": ["ma_history", "earnings_call"]}
  ],
  "scoring_criteria": {
    "8_HIGH": "Confirmed prior acquisition in seller's vertical (must name the deal)",
    "6_MEDIUM": "Operates in adjacent space, no confirmed acquisition",
    "4_LOW": "Wrong vertical, pure VC, advisory, or too small"
  },
  "client_assets": [
    "HR.com domain name (premium .com in $3T HR tech market)",
    "2M+ registered HR professionals",
    "500+ original content pieces per year",
    "Certification/accreditation programs",
    "Event/conference business"
  ],
  "valuation_multiples": {
    "revenue": "1-3x (digital media)",
    "ebitda": "5-12x (established media)",
    "subscriber_value": "$XX per registered user"
  },
  "exa_search_context": "HR technology, human capital management, workforce management, talent acquisition"
}
```

For home services, a different config:

```json
{
  "vertical": "home_services",
  "display_name": "Home Services (HVAC, Plumbing, Electrical)",
  "research_sections": [
    {"key": "service_territory", "title": "Service Territory & Market", "templates": ["company_search"]},
    {"key": "recurring_revenue", "title": "Recurring Revenue Mix", "templates": ["company_financials"]},
    {"key": "owner_story", "title": "Owner Story & Culture", "templates": ["owner_search"]},
    {"key": "reviews_reputation", "title": "Reviews & Reputation", "templates": ["reviews_search"]},
    ...
  ],
  "scoring_criteria": {
    "8_HIGH": "Active platform acquirer in this MSA, confirmed deal in last 24 months",
    ...
  },
  "valuation_multiples": {
    "ebitda": "4-7x (residential), 6-10x (commercial/recurring)",
    ...
  }
}
```

**The script reads the config. The config defines the vertical. No code changes per client.**

---

## Workstream 2: Cross-Domain Research Engine

**Priority:** HIGH — needed for the 16-buyer HR.com batch
**Timeline:** This week (refactor traced_buyer_run.py)
**Tool:** Claude Code

### Changes to `traced_buyer_run.py`

1. **Add `--config` flag** that loads a vertical config JSON
2. **Replace hard-coded `build_sections()`** with config-driven section loading
3. **Replace hard-coded prompts** with config-aware synthesis prompts that reference the client's assets and the vertical context
4. **Add pain/gain matching phase** (Phase 3.5) between product reviews and assembly
5. **Keep everything else** — the tracing, the Exa wrappers, the git push, the manifest

### New Phase: Pain/Gain Matching

After all buyer research is complete for a buyer, add:

```
Phase 3.5: PAIN/GAIN MATCHING
  Input: buyer sections + client_assets from config
  Process: LLM matches buyer pains/gaps → client capabilities
  Output: matches[] array in buyer JSON
  Multi-agent: Send same input to 3 openclaw agents, merge results
```

### Batch Runner

```bash
# Run all 16 HR.com buyers with the hr_media config
python3 scripts/traced_buyer_run.py --config configs/hr_media.json --batch buyers/hrcom-buyers.csv
```

Where `buyers/hrcom-buyers.csv`:
```csv
buyer,city,state,ticker,domain
Workday,Pleasanton,CA,WDAY,workday.com
Oracle HCM,Austin,TX,ORCL,oracle.com
ADP,Roseland,NJ,ADP,adp.com
...
```

---

## Workstream 3: OpenClaw Agent Sync

**Priority:** MEDIUM — not blocking the batch run, but needed for quality
**Timeline:** Next week
**Tool:** Claude Code for config changes

### Architecture: Agents as Workers, Not Decision-Makers

```
┌──────────────────────────────────────────────────┐
│ CLAUDE CODE (Controller)                          │
│                                                   │
│  1. Runs Exa searches (owns methodology)          │
│  2. Passes raw results + synthesis prompt          │
│     to N openclaw agents in parallel               │
│  3. Collects N independent outputs                 │
│  4. Picks best / merges                            │
│  5. Writes final JSON + trace                      │
│  6. Git push → Vercel deploy                       │
└───────┬──────────┬──────────┬────────────────────┘
        │          │          │
        ▼          ▼          ▼
   ┌─────────┐ ┌─────────┐ ┌─────────┐
   │ Agent A  │ │ Agent B  │ │ Agent C  │
   │ DeepSeek │ │ Gemini   │ │ GPT-4o   │
   │ v3-0324  │ │ Flash    │ │ mini     │
   │          │ │          │ │          │
   │ Receives:│ │ Receives:│ │ Receives:│
   │ raw Exa  │ │ raw Exa  │ │ raw Exa  │
   │ results  │ │ results  │ │ results  │
   │ + prompt │ │ + prompt │ │ + prompt │
   │          │ │          │ │          │
   │ Returns: │ │ Returns: │ │ Returns: │
   │ HTML     │ │ HTML     │ │ HTML     │
   │ synthesis│ │ synthesis│ │ synthesis│
   └─────────┘ └─────────┘ └─────────┘
```

### What Changes in OpenClaw

1. **Fix dead keys:** Switch main/controller from `deepseek/deepseek-chat` to `openrouter/deepseek/deepseek-chat-v3-0324`
2. **Replace SOUL.md:** Kill the home services dossier pipeline. Replace with: "You are a research synthesis worker. You receive raw search results and a synthesis prompt. Return structured output. You do not decide what to search or where to store."
3. **Replace all IDENTITY.md files:** Make agents vertical-agnostic. Their identity is their MODEL + their synthesis style, not their domain knowledge.
4. **Do NOT let agents read workspace files for task context:** Pass everything in the message. The message IS the context.

### How traced_buyer_run.py Calls OpenClaw Agents

```python
def multi_agent_synthesize(raw_text, prompt, section_key):
    """Send same data to 3 agents, pick best output."""
    agents = ["researcher", "validator", "auditor"]  # different models
    results = []
    for agent_id in agents:
        output = subprocess.run(
            ["openclaw", "agent", "--agent", agent_id, "--local",
             "--message", f"{prompt}\n\nRAW DATA:\n{raw_text}",
             "--json", "--timeout", "120"],
            capture_output=True, text=True, timeout=130
        )
        if output.returncode == 0:
            results.append(json.loads(output.stdout))
    
    # Pick longest non-empty output, or merge
    return pick_best(results)
```

---

## Workstream 4: Letter Pipeline with Source Citation

**Priority:** HIGH — this is the daily user-facing workflow
**Timeline:** 2 weeks
**Tool:** Claude Code for backend, Claude Desktop for UX design

### The Daily Morning Task

```
┌─────────────────────────────────────────────────┐
│  Good morning, Mark.                             │
│                                                  │
│  📬 12 letters ready for HR.com                  │
│     3 letters ready for Canyon State Plumbing    │
│                                                  │
│  [Review HR.com Letters →]                       │
│  [Review Canyon State Letters →]                 │
└─────────────────────────────────────────────────┘
```

### The Review UX (per letter)

```
┌─────────────────────────────┬──────────────────────────────┐
│ LETTER (editable)           │ SOURCES (read-only)          │
│                             │                              │
│ Dear Mr. Alam,              │ ■ Claim: "SAP acquired       │
│                             │   SmartRecruiters in Sept    │
│ I noticed SAP's recent      │   2025"                      │
│ acquisition of              │   Source: GlobeNewsWire ↗     │
│ SmartRecruiters signals a   │   Confidence: HIGH           │
│ renewed commitment to       │                              │
│ talent acquisition...       │ ■ Claim: "2M+ HR             │
│                             │   professionals"             │
│ HR.com's 2M+ registered     │   Source: HR.com about page ↗│
│ HR professionals represent  │   Confidence: HIGH           │
│ the exact mid-market        │                              │
│ audience your Q4 earnings   │ ■ Claim: "mid-market gap     │
│ call identified as a        │   mentioned in Q4 earnings"  │
│ growth priority.            │   Source: Seeking Alpha ↗     │
│                             │   Confidence: MEDIUM          │
│ [Edit text here...]         │   (paraphrased, not exact)   │
│                             │                              │
├─────────────────────────────┤                              │
│ [← Previous] [Approve ✓]   │                              │
│ [Skip] [Reject ✗]          │                              │
│ [Next →]                    │                              │
└─────────────────────────────┴──────────────────────────────┘
```

### Data Flow

1. Research produces per-buyer JSON with `source_urls` per section
2. Pain/gain matching produces `matches[]` with `buyer_source_url` per match
3. Letter generation cites specific matches and includes source metadata
4. Letter JSON stored with `claims[]` array linking each statement to its source
5. Review page renders letter + claims side-by-side
6. User approves → letter goes to Lob print queue

### Letter Claims Schema

```json
{
  "letter_id": "uuid",
  "buyer_slug": "sap-successfactors",
  "proposal_id": "uuid",
  "body_html": "<p>Dear Mr. Alam...</p>",
  "claims": [
    {
      "text": "SAP's recent acquisition of SmartRecruiters",
      "source_section": "ma_appetite",
      "source_url": "https://www.globenewswire.com/...",
      "confidence": "HIGH",
      "position": {"start": 45, "end": 89}
    }
  ],
  "status": "pending_review",
  "reviewed_by": null,
  "reviewed_at": null
}
```

---

## Workstream 5: Schema Unification

**Priority:** MEDIUM-HIGH — design now, migrate incrementally
**Timeline:** Design this week, migrate over 2-3 weeks
**Tool:** Claude Desktop for schema design, Claude Code for migration scripts

### Principle: One Schema, Many Verticals

```
engagements (replaces per-client engagement tracking)
├── id
├── entity (next_chapter | and_capital | revsup)
├── vertical (home_services | hr_media | windows | concrete | ...)
├── client_company_name
├── client_config JSONB  ← vertical-specific config
├── status
├── created_at
└── ...

engagement_buyers (already exists — extend, don't replace)
├── id
├── proposal_id → engagements
├── buyer_company_name
├── buyer_slug
├── fit_score
├── vertical_fit JSONB  ← domain-specific scoring rationale
├── pain_gain_matches JSONB  ← the linkage
├── research_json_path  ← "public/data/debbie-research-{slug}.json"
├── letter_claims JSONB
├── ...existing 58 columns...
└── ...

domain_configs (NEW — one row per vertical)
├── id
├── vertical_slug
├── display_name
├── research_sections JSONB
├── scoring_criteria JSONB
├── valuation_multiples JSONB
├── client_assets_template JSONB
├── exa_search_context
└── created_at
```

### What Does NOT Need New Tables
- Buyer research → stays as static JSON files (proven pattern)
- Letters → use existing `letter_approvals` + add `claims` JSONB column
- Page rendering → stays as `debbie-buyer-review.html?buyer={slug}` (template works for any vertical)
- Traces → stay as `docs/TRACE-{slug}-{timestamp}.md` files

### What DOES Need New Tables
- `domain_configs` — vertical configuration (replaces hard-coded sections in Python)
- `engagement_pain_gain_matches` — or just a JSONB column on `engagement_buyers`

---

## Implementation Sequence

### Week 1 (This Week): Ship the HR.com Batch
1. Run 16 buyers with current `traced_buyer_run.py` (works today)
2. Create `configs/hr_media.json` vertical config (doesn't change script yet, just documents the config)
3. Fix openclaw dead keys (DeepSeek → OpenRouter)
4. Design `domain_configs` table schema

### Week 2: Cross-Domain Refactor
1. Refactor `traced_buyer_run.py` to read vertical config
2. Add pain/gain matching phase
3. Update openclaw SOUL.md and agent identities to be vertical-agnostic
4. Test one buyer with multi-agent synthesis

### Week 3: Letter Pipeline
1. Build letter generation from pain/gain matches
2. Add `claims` to letter data model
3. Build review UX (split-pane: letter + sources)
4. Wire to daily morning task page

### Week 4: Production Hardening
1. Run full batch for HR.com with new pipeline
2. Test domain onboarding with a hypothetical second vertical
3. Migrate openclaw to task-scoped instructions (no workspace context)
4. Document everything in CLAUDE.md and openclaw workspace

---

## Decision Points for Claude Desktop Review

Take these to Claude Desktop (Projects) for deeper analysis:

1. **Pain/gain matching**: Should this be a separate LLM pass, or integrated into section synthesis? Trade-off: separate = more cost, more auditable; integrated = faster, cheaper.

2. **Multi-agent competition**: Is 3 agents per section worth the cost (~3x)? Or only for high-value sections (approach strategy, golden nuggets)?

3. **Schema**: Should pain/gain matches live as JSONB on `engagement_buyers`, or as a separate table with FK? Trade-off: JSONB = simpler queries, separate table = better audit trail.

4. **Vertical config**: Should configs live in Supabase (`domain_configs` table) or as JSON files in the repo? Trade-off: DB = editable without deploy, file = version-controlled.

5. **OpenClaw role**: Is multi-agent synthesis worth the complexity, or should we keep Claude-only synthesis and use openclaw purely for monitoring/orchestration?

---

## Appendix: Files That Must Change

| File | Change | Workstream |
|------|--------|-----------|
| `scripts/traced_buyer_run.py` | Add --config flag, config-driven sections, pain/gain phase | 2 |
| `configs/hr_media.json` | NEW — vertical config for HR.com | 1 |
| `configs/home_services.json` | NEW — extract existing home services config | 1 |
| `~/.openclaw/agents/main/IDENTITY.md` | Replace home services pipeline with vertical-agnostic worker | 3 |
| `~/.openclaw/workspace/SOUL.md` | Kill dossier pipeline, replace with worker protocol | 3 |
| `~/.openclaw/.env` | Fix DeepSeek key or reroute to OpenRouter | 3 |
| `public/debbie-buyer-review.html` | Add pain/gain matching section to page template | 2 |
| `public/letter-review.html` | NEW — split-pane letter + sources review UX | 4 |
| `CLAUDE.md` | Add domain onboarding process, vertical config pattern | 1 |
| `docs/DEBBIE-REVIEW-SYSTEM.md` | Update with config-driven pipeline, pain/gain matching | 2 |
