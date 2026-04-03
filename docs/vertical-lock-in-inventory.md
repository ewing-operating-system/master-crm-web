# Vertical Lock-In Inventory

Audit date: 2026-04-02
Scope: All Python, JavaScript, JSX, and SQL files in master-crm-web (excluding docs/ comments)

Classification key:
- **(a)** Simple string replacement
- **(b)** Logic that needs to be parameterized
- **(c)** Structural change required

---

## 1. HARDCODED VALUES

### 1.1 VERTICAL_DATA Dictionaries (EBITDA multiples, buyer names, market context)

| File | Lines | What | Fix |
|------|-------|------|-----|
| `lib/letter_engine.py` | 32–229 | `VERTICAL_DATA` dict: 8 verticals (water_treatment, hvac, plumbing, roofing, pest_control, concrete_precast, flooring). Each maps to multiple_floor/ceiling, top_levers, market_context, buyer_appetite, premium_driver | **(b)** |
| `backend/lib/letter_integration.py` | 201–209 | `VERTICAL_MULTIPLES` dict: `"water_treatment": (4.0, 8.0), "hvac": (4.5, 8.5), "plumbing": (4.0, 7.5), "roofing": (3.5, 7.0), "pest_control": (5.0, 10.0), "concrete_precast": (4.0, 7.5), "flooring": (3.5, 6.5)` | **(b)** |
| `backend/lib/proposal_engine.py` | 294–306 | Duplicate EBITDA defaults dict (ebitda_low/med/high per vertical) | **(b)** |
| `backend/lib/research_transparency.py` | 425–429 | `"HVAC": {"ebitda_low": 3.5, "ebitda_med": 5.0, "ebitda_high": 7.0}` | **(b)** |
| `api/letters/generate.js` | 40–46 | JS mirror of VERTICAL_MULTIPLES: `hvac: {floor: 4.5, ceiling: 8.5, median: 6.0}` etc. | **(b)** |
| `public/letter-template.js` | 29–35 | Same EBITDA multiples duplicated in frontend JS | **(b)** |

> **Note:** EBITDA multiples are duplicated in at least 5 files. Any update requires 5 simultaneous edits.

### 1.2 Entity Keyword Dictionaries

| File | Lines | What | Fix |
|------|-------|------|-----|
| `backend/lib/classification.py` | 15–45 | `AND_CAPITAL_KEYWORDS`, `NEXT_CHAPTER_KEYWORDS` (includes "home services", "plumbing", "hvac", "roofing", "pest control", "water treatment", "flooring", "steel", "concrete", "precast", "trades", "contractor"), `REVSUP_KEYWORDS` | **(b)** |
| `backend/lib/classification.py` | 86–95 | `STANDALONE_KEYWORDS` mapping company names to entities (boomerang->the_forge, biolev, sea_sweet, precision_exploration) | **(a)** |
| `backend/agents/classify_all_targets.js` | 95–120 | `tradesKeywords` array: plumbing, hvac, roofing, pest, water treatment, flooring, steel, concrete, construction, home services, trades, contractor. Match -> `entity='next_chapter'` | **(b)** |

### 1.3 Person Routing

| File | Lines | What | Fix |
|------|-------|------|-----|
| `backend/lib/classification.py` | 72–84 | `PERSON_ENTITY_MAP` (chris rex->and_capital, etc.) and `PERSON_NEVER_MAP` (john kelly: never and_capital; ewing: never revsup) | **(a)** |

### 1.4 Entity-Specific If/Elif Chains

| File | Lines | What | Fix |
|------|-------|------|-----|
| `backend/agents/classify_remaining.js` | 46–50 | `if (vertical.includes('hvac') \|\| vertical.includes('plumbing') \|\| vertical.includes('pest') \|\| vertical.includes('construction')) { entity = 'next_chapter'; } else if (vertical.includes('electrical')) { entity = 'and_capital'; }` | **(c)** |
| `backend/lib/classification.py` | 189–230 | `_keyword_score()` computes per-entity scores from keyword dicts, then if/elif picks best | **(c)** |
| `backend/worker.py` | 166 | Classification prompt hardcodes entity options: "next_chapter (home services M&A), and_capital (PE fund/LP), revsup (SaaS recruiting)" | **(c)** |

### 1.5 Campaign Prefix Routing

| File | Lines | What | Fix |
|------|-------|------|-----|
| `backend/lib/classification.py` | 145–158 | Hardcoded prefix map: NC->next_chapter, AND->and_capital, RU/REV->revsup, FORGE->the_forge, BIOLEV->biolev, SEASWEET->sea_sweet, PEC->precision_exploration | **(a)** |

### 1.6 Entity Themes and Color Palettes

| File | Lines | What | Fix |
|------|-------|------|-----|
| `lib/portal-config.js` | 32–155 | `ENTITY_THEMES` mapping entity names to color palettes (nc->darkblue/gold, etc.) | **(a)** |
| `backend/lib/page_template.py` | 122–155 | `ENTITY_THEMES` dict with color codes per entity + shorthand name map (nc, and, ru) | **(a)** |
| `scripts/meeting_pages.py` | 295–338 | `INTERNAL_DOMAINS` dict (domain->entity), `ENTITY_MAP` (company->entity), color codes | **(a)** |

### 1.7 Home-Services-Specific Narrative Strings

| File | Lines | What | Fix |
|------|-------|------|-----|
| `backend/lib/linkedin_automation.py` | 39–133 | `CONNECTION_TEMPLATES` and `MESSAGE_SEQUENCES` per entity with vertical-specific messaging | **(a)** |
| `lib/meeting_engine_v2.py` | 132, 162 | "We specialize exclusively in home services and trades...", "Boutique M&A advisory focused exclusively on home services businesses -- plumbing, HVAC, water treatment, roofing..." | **(a)** |
| `public/proposal-auto-generator.js` | 10 | `INDUSTRY_MARGIN_BENCHMARK = 0.22` (22% home services margin) | **(a)** |
| `public/proposal-auto-generator.js` | 194 | `return d.industry \|\| 'Home Services'` fallback | **(a)** |

### 1.8 EBITDA Lever Page Registry

| File | Lines | What | Fix |
|------|-------|------|-----|
| `scripts/inject-nav.py` | 54–56 | `EBITDA_PAGES = {"ebitda-levers-concrete-precast", "ebitda-levers-flooring", "ebitda-levers-hvac", "ebitda-levers-pest-control", "ebitda-levers-plumbing", "ebitda-levers-roofing", "ebitda-levers-water-treatment"}` | **(a)** |
| `scripts/inject-nav.py` | 18–43 | Portal config mapping: `"design-precast": {"hub": "design-precast-...-hub.html"}` etc. | **(a)** |

### 1.9 Default Entity Fallbacks in Python

| File | Lines | What | Fix |
|------|-------|------|-----|
| `backend/lib/why_sell_engine.py` | 377, 452, 510, 634 | `entity="next_chapter"` as default param in `generate_why_sell()`, `generate_buyer_pitch()`, `batch_generate()`, CLI fallback | **(a)** |
| `backend/lib/letter_integration.py` | 429, 582, 650 | `.get("entity", "next_chapter")`, `batch_generate_letters(entity="next_chapter")`, argparse default | **(a)** |
| `backend/lib/research_templates.py` | 492 | `entity = target.get("entity", "next_chapter")` | **(a)** |
| `backend/lib/transcript_processor.py` | 69, 169, 194 | `entity="next_chapter"` default in `process_transcript()`, `.get()` fallback, argparse default | **(a)** |
| `backend/server.py` | 1091, 1109, 1184, 1197 | `.get("entity", "next_chapter")` in letter and company endpoints | **(a)** |
| `backend/agents/listener/agent.py` | 314, 701 | `.get("entity") or "next_chapter"` fallbacks | **(a)** |

---

## 2. TEMPLATE LOCK-IN

### 2.1 Exa Search Query Templates

| File | Lines | Template Text | Fix |
|------|-------|---------------|-----|
| `backend/lib/research_templates.py` | 34–55 | `NEXT_CHAPTER_BASE` — queries assume BBB rating, Google reviews, technician fleet, service agreements, NATE/EPA certs. e.g. `"{company_name} reviews BBB rating Google 4 5 stars"`, `"{vertical} company {city} {state} acquisition sale sold 2024 2025"` | **(b)** |
| `backend/lib/research_templates.py` | 57–194 | `NEXT_CHAPTER_VERTICAL_OVERRIDES` — per-vertical Exa queries: `"{company_name} NATE certified HVAC technicians"`, `"{company_name} termite warranty quarterly pest control"`, `"pest control company {city} {state} acquisition sold Rollins Rentokil 2024 2025"`, `"{company_name} NSF certification water softener reverse osmosis"` | **(c)** |
| `backend/lib/research_templates.py` | 200–247 | `AND_CAPITAL_BASE` + `AND_CAPITAL_VERTICAL_OVERRIDES` (healthcare, energy) — different verticals but same hardcoded pattern | **(b)** |
| `backend/lib/research_templates.py` | 249–298 | `REVSUP_BASE` + `REVSUP_VERTICAL_OVERRIDES` (saas, hr_tech) | **(b)** |
| `backend/lib/research_templates.py` | 393–395 | Entity->template lookup: `"next_chapter": (NEXT_CHAPTER_BASE, NEXT_CHAPTER_VERTICAL_OVERRIDES)` — hardcoded dispatch | **(b)** |

### 2.2 Story Hooks for Letters

| File | Lines | Template Text | Fix |
|------|-------|---------------|-----|
| `backend/lib/research_templates.py` | 306–373 | `STORY_HOOKS` dict keyed by entity+vertical. Examples: NC/hvac: "HVAC businesses with strong maintenance agreement books are trading at the highest multiples in the trades"; NC/pest_control: "A recurring quarterly pest control book is one of the most predictable revenue streams in all of home services"; NC/roofing: "Roofing businesses with strong insurance claim relationships..." | **(b)** |

### 2.3 Proposal Templates

| File | Lines | Template Text | Fix |
|------|-------|---------------|-----|
| `backend/campaigns/next_chapter/proposal-template.jsx` | Multiple | "HVAC consolidation estimated only 50% through its cycle", "PE dry powder at all-time highs with home services as top deployment target", example transactions: HVAC Platform $18M @8.2x, Plumbing Add-on $4.5M @5.5x | **(b)** |
| `backend/campaigns/next_chapter/templates/proposal-template-v1.jsx` | Multiple | Duplicate of proposal-template.jsx | **(b)** |
| `backend/campaigns/next_chapter/proposal-rules-and-template.md` | Entire file | "Home Services M&A Advisory Proposal — Top 10 Rules + Master Template". Rule 2: HVAC 4x-12x, plumbing 2.5x-8x, pest control 5x-10x. Rule 6: service agreements, technician retention, state licensing, fleet condition, seasonality. Section 3: "THE HOME SERVICES M&A LANDSCAPE" | **(c)** |

### 2.4 Buyside Criteria Documents

| File | Lines | Template Text | Fix |
|------|-------|---------------|-----|
| `backend/campaigns/next_chapter/buyside_criteria/buyside-criteria-design-precast.jsx` | 1–700+ | Entire criteria doc for concrete/precast: target criteria (40% underground precast minimum), ASTM C76/C478 certs, buyer name (Chris Fore), IIJA funding tailwinds | **(c)** |
| `backend/campaigns/next_chapter/buyside_criteria/buyside-criteria-wieser-concrete.jsx` | 1–700+ | Wieser Concrete: buyer profile (Andy), infrastructure/utility/ag precast wheelhouse, target criteria, market size | **(c)** |

### 2.5 Letter Text Builder (Synthesis Prompt)

| File | Lines | Template Text | Fix |
|------|-------|---------------|-----|
| `backend/lib/letter_integration.py` | 212–391 | `build_letter_text()` — entire letter narrative arc assumes home services value drivers: service agreements, recurring revenue, owner-operator exit, EBITDA multiples | **(c)** |
| `lib/letter_engine.py` | 428, 450, 498 | Uses `vertical_info['vertical_short']` in narrative: "We've spent significant time studying the {vertical_short}..." | **(a)** |

### 2.6 Fee Structure

| File | Lines | Template Text | Fix |
|------|-------|---------------|-----|
| `backend/campaigns/next_chapter/proposal-rules-and-template.md` | Rule 3 | $5K-$25K engagement fee, $2.5K-$7.5K monthly retainer, 5-10% success fee for sub-$5M deals — home services deal sizes. Does not work for PE fundraising (mgmt fee + carry) or SaaS recruiting (placement fees) | **(c)** |

### 2.7 Agent Briefings

| File | Lines | Template Text | Fix |
|------|-------|---------------|-----|
| `backend/agents/researcher.md` | Multiple | Agent briefing written for home services context | **(b)** |
| `backend/agents/executor.md` | Multiple | Agent briefing written for home services context | **(b)** |
| `backend/scripts/rebuild-proposals.js` | 79–189 | Hardcoded example proposals: HVAC (Air Control, McLean VA), Water Treatment (AquaScience), Flooring (Springer Floor Care) with vertical-specific strategicBuyers lists and licenses | **(c)** |

---

## 3. SCHEMA LOCK-IN

### 3.1 Entity-Specific SQL Views

| File | Lines | What | Fix |
|------|-------|------|-----|
| `backend/data/10-SCHEMA-DESIGN.sql` | ~700–730 | 9 hardcoded views: `nc_targets`, `nc_companies`, `nc_contacts` (WHERE entity = 'next_chapter'); `and_targets`, `and_companies`, `and_contacts`, `and_investors` (WHERE entity = 'and_capital'); `ru_targets`, `ru_companies`, `ru_contacts` (WHERE entity = 'revsup'); `and_daily_briefing` | **(c)** |

> **Impact:** Every new entity requires creating 3+ new views.

### 3.2 Entity-Specific Tables

| File | Lines | What | Fix |
|------|-------|------|-----|
| `backend/data/10-SCHEMA-DESIGN.sql` | Multiple | Dedicated tables per entity: `nc_owner_profiles`, `and_investor_profiles`, `ru_placements`, `and_events`, `and_event_targets`, `forge_boomerang_targets` | **(c)** |

> **Impact:** No polymorphic pattern. New entities require new tables + relationships.

### 3.3 Default Entity in Migration Files

| File | Lines | What | Fix |
|------|-------|------|-----|
| `migrations/003_mandatory_tables.sql` | 19 | `entity text NOT NULL DEFAULT 'next_chapter'` | **(a)** |
| `backend/supabase/migrations/20260330_final_features_tables.sql` | 62, 92 | `entity TEXT DEFAULT 'next_chapter'` (why_sell_narratives, why_sell_buyer_pitches) | **(a)** |
| `backend/supabase/migrations/20260401_debbie_review_feedback.sql` | 33, 53 | `entity text NOT NULL DEFAULT 'next_chapter'` (debbie_review_feedback, debbie_review_sessions) | **(a)** |

### 3.4 Hardcoded Entity in Orchestrator Queries

| File | Lines | What | Fix |
|------|-------|------|-----|
| `backend/orchestrator.py` | 97–99 | Certifier queue INSERT hardcodes `'next_chapter'`: `VALUES ('certifier', 'proposal', %s, 'next_chapter', 'normal', %s)` | **(b)** |

### 3.5 Entity-Filtered Supabase REST Queries

| File | Lines | What | Fix |
|------|-------|------|-----|
| `backend/lib/revsup_engine.py` | 36, 41 | `_sb_get("ru_targets", "entity=eq.revsup&status=eq.active")`, `_sb_get("ru_contacts", "entity=eq.revsup")` | **(a)** |
| `backend/lib/and_capital_engine.py` | 36, 50 | `_sb_get("and_targets", "entity=eq.and_capital")`, `_sb_get("and_contacts", "entity=eq.and_capital")` | **(a)** |

### 3.6 Dashboard Queries (Implicit Entity Assumptions)

| File | Lines | What | Fix |
|------|-------|------|-----|
| `backend/lib/dashboard.py` | 40, 74, 98 | Campaigns grouped by entity, pipeline stages unfiltered, `cost_budget` assumes entity column exists per entity | **(a)** |

---

## Summary Statistics

| Metric | Count |
|--------|-------|
| Files with hardcoded vertical logic | 28+ |
| Duplicate EBITDA multiple definitions | 5 files |
| Duplicate keyword dictionaries | 2 files (Python + JS) |
| Entity-specific SQL views | 9 |
| Entity-specific tables | 6 |
| `DEFAULT 'next_chapter'` in migrations | 4 columns across 3 files |
| `.get("entity", "next_chapter")` fallbacks | 15+ call sites across 6 files |
| Lines of hardcoded home-services logic | ~2,500+ |
| Items classified (a) string replacement | 22 |
| Items classified (b) needs parameterization | 18 |
| Items classified (c) structural change | 12 |
