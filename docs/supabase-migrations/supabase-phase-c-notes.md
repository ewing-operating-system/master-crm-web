# Phase C: Entity TEXT → entity_type Enum — Companion Notes

**Date:** 2026-04-03 | **Branch:** `refactor/cross-domain-inventory`
**SQL file:** `~/Desktop/supabase-phase-c-migration.sql`
**Prereqs:** Phase A (vertical_id columns, 2026-04-03 02:52 UTC) + Phase B (backfill, 2026-04-03 11:05 UTC)

---

## Scope

Convert 31 tables from `entity TEXT` to `entity entity_type` enum. Add NOT NULL constraints where safe. Preserve existing DEFAULT values. No new columns, no data model changes.

**Out of scope:** Canyon State reclassification, page_versions entity addition, enum 'unknown' removal, code fixes for root causes.

---

## Entity Type Enum — Live State

| # | Enum Value | In Architecture Doc? | Companies Count | Notes |
|---|-----------|---------------------|-----------------|-------|
| 1 | `next_chapter` | Yes | 260 | Primary operating entity |
| 2 | `and_capital` | Yes | 27 | Investment fund |
| 3 | `revsup` | Yes | 0 | Recruiting — 3 campaigns defined |
| 4 | `the_forge` | Yes | 0 | Athlete recruitment (forge_boomerang_targets: 227) |
| 5 | `biolev` | Yes | 0 | Static sale |
| 6 | `sea_sweet` | Yes | 0 | Roofing rollup |
| 7 | `precision_exploration` | Yes | 0 | Fraud case mgmt |
| 8 | `system` | Yes | 0 | Internal/infrastructure |
| 9 | `unknown` | **NO** | 1 | Canyon State only — data quality issue |

**No ALTER TYPE needed.** All 8 architecture entities exist in the live enum. The 9th value `unknown` is already present and used by Canyon State (companies) + 1 pending classifier task (agent_queue). Phase C can proceed without enum changes.

---

## Data Audit Results — All 31 TEXT Entity Tables

### Legend
- **Clean**: all values are valid entity_type variants, 0 NULLs
- **Fixable**: non-standard values with confirmed mapping
- Empty tables are inherently safe

### Tier 1: Safe (28 tables)

#### Populated — Clean Data (11 tables)

| Table | Rows | Entity Distribution | NULLs | Verdict |
|-------|------|-------------------|-------|---------|
| `agent_queue` | 7 | next_chapter=6, unknown=1 | 0 | Clean — 'unknown' is valid enum value |
| `agent_runs` | 12 | next_chapter=12 | 0 | Clean |
| `cost_budget` | 8 | next_chapter=2, and_capital=2, revsup=2, system=2 | 0 | Clean — multi-entity |
| `debbie_buyer_review_feedback` | 8 | next_chapter=8 | 0 | Clean |
| `entity_value_propositions` | 3 | next_chapter=3 | 0 | Clean |
| `pain_gain_analyses` | 1 | next_chapter=1 | 0 | Clean |
| `play_executions` | 6 | next_chapter=6 | 0 | Clean |
| `play_templates` | 8 | next_chapter=8 | 0 | Clean |
| `proposals` | 6 | next_chapter=6 | 0 | Clean |
| `research_executions` | 50 | next_chapter=50 | 0 | Clean |
| `situation_library` | 7 | next_chapter=7 | 0 | Clean |

#### Empty — Zero Data Risk (17 tables)

| Table | Schema Nullability | NOT NULL in Design? | Notes |
|-------|--------------------|--------------------|----|
| `campaign_batches` | NOT NULL | Yes | Governor table |
| `cost_ledger` | NOT NULL | Yes | Cost tracking |
| `debbie_review_exports` | NOT NULL | Yes | Export log |
| `estimate_accuracy` | nullable | No | Correction log |
| `feedback_log` | nullable | No | Meta table |
| `guardrail_log` | nullable | No | System monitoring |
| `human_review_queue` | nullable | No | System routing |
| `letter_approvals` | NOT NULL | Yes | Letter workflow |
| `letter_campaigns` | NOT NULL | Yes | Campaign tracking |
| `meeting_notes` | nullable* | Yes | *Phase A addition |
| `nurture_schedule` | nullable | No | Future use |
| `page_templates` | nullable | No | Cross-entity |
| `response_log` | nullable | No | Future use |
| `step_log` | nullable | No | Infrastructure |
| `verification_pairs` | nullable | No | Infrastructure |
| `why_sell_buyer_pitches` | nullable | Yes | Entity-scoped content |
| `why_sell_narratives` | nullable | Yes | Entity-scoped content |

### Tier 2: Needs Cleanup (3 tables)

#### 2A. `meeting_learnings` — 41 rows

| Entity Value | Count | Valid Enum? | Action |
|-------------|-------|-------------|--------|
| `next_chapter` | 11 | Yes | No change |
| `hrcom` | 30 | **NO** | → `next_chapter` |

**Root cause:** Meeting transcript pipeline (`scripts/meeting_pages.py`, `api/meetings/approve-learning.js`) wrote the client identifier "hrcom" instead of the entity. HR.com is a Next Chapter deal — correct entity is `next_chapter`.

**Mapping confidence:** HIGH — HR.com Ltd is confirmed in companies table as entity=next_chapter (inserted during Phase B Fix 1).

**Code files to fix after migration:**
- `scripts/meeting_pages.py`
- `api/meetings/approve-learning.js`

#### 2B. `engagement_buyers` — 224 rows

| Entity Value | Count | Valid Enum? | Action |
|-------------|-------|-------------|--------|
| `next_chapter` | 174 | Yes | No change |
| `Air Control LLC` | 10 | **NO** | → `next_chapter` |
| `Springer Floor Care` | 10 | **NO** | → `next_chapter` |
| `Design Precast & Pipe, Inc.` | 10 | **NO** | → `next_chapter` |
| `AquaScience` | 10 | **NO** | → `next_chapter` |
| `Wieser Concrete Products, Inc.` | 10 | **NO** | → `next_chapter` |

**Root cause:** Hub/buyer generation code wrote company_name into entity column instead of the entity value. All 50 affected rows traced to 5 proposals, all confirmed as entity=`next_chapter`.

**Mapping confidence:** HIGH — each company name traced to its proposal, all proposals confirmed next_chapter via live query.

**Proposal-level verification:**

| Proposal ID | Company | Proposal Entity |
|-------------|---------|----------------|
| `ce11b6b7-...` | Air Control | next_chapter |
| `deed565b-...` | Springer Floor | next_chapter |
| `d55f982f-...` | Design Precast & Pipe, Inc. | next_chapter |
| `656be30d-...` | AquaScience | next_chapter |
| `fca72ac6-...` | Wieser Concrete Products, Inc. | next_chapter |

**Code files to fix after migration:**
- `backend/lib/engagement_engine.py`
- `backend/lib/company_hub.py`
- `backend/data/buyer-lists/insert_buyers.js`
- `backend/scripts/refresh_hub_buyers.py`
- `backend/scripts/buyer_1pager_pipeline.py`

#### 2C. `intelligence_cache` — 35 rows

| Entity Value | Count | Valid Enum? | Action |
|-------------|-------|-------------|--------|
| `next_chapter` | 14 | Yes | No change |
| `AquaScience` | 6 | **NO** | → `next_chapter` |
| `Air Control LLC` | 7 | **NO** | → `next_chapter` |
| `Springer Floor Care LLC` | 8 | **NO** | → `next_chapter` |

**Root cause:** Intelligence cache writer used company_name as entity. All rows have company_id linking to next_chapter companies.

**Mapping confidence:** HIGH — company_id FK → companies table → all next_chapter.

**Code files to fix after migration:**
- `backend/lib/engagement_engine.py`
- `backend/lib/profile_engine.py`
- `backend/lib/meeting_engine.py`
- `backend/lib/sap_turbo.py`

### Tier 3: Deferred Items (0 tables needing migration deferral)

No tables require deferral. All 31 tables are either clean (Tier 1) or have confirmed, mappable fixes (Tier 2). The three Tier 2 tables have small, well-understood data issues with high-confidence corrections.

---

## NOT NULL Constraint Decisions

### Adding NOT NULL (5 tables)

| Table | Current | Rows | NULLs | Rationale |
|-------|---------|------|-------|-----------|
| `engagement_buyers` | nullable | 224 | 0 | Every buyer belongs to a proposal which has an entity |
| `research_executions` | nullable | 50 | 0 | Every research run is entity-scoped |
| `why_sell_buyer_pitches` | nullable | 0 | 0 | Entity-scoped sales content per design |
| `why_sell_narratives` | nullable | 0 | 0 | Entity-scoped narratives per design |
| `meeting_notes` | nullable | 0 | 0 | Entity required per schema design |

### Keeping Nullable (15 tables)

| Table | Rows | Rationale |
|-------|------|-----------|
| `agent_queue` | 7 | Entity may not be known at enqueue time (classifier discovers it) |
| `agent_runs` | 12 | Inherits agent_queue constraint |
| `estimate_accuracy` | 0 | Correction log — entity is contextual |
| `feedback_log` | 0 | Meta/system table |
| `guardrail_log` | 0 | System monitoring |
| `human_review_queue` | 0 | System routing — entity may not be known |
| `intelligence_cache` | 35 | May cache cross-entity data in future |
| `nurture_schedule` | 0 | Entity routing TBD |
| `page_templates` | 0 | Templates can serve multiple entities |
| `play_executions` | 6 | May inherit entity from play_templates |
| `play_templates` | 8 | Some plays are cross-entity |
| `response_log` | 0 | Response routing TBD |
| `situation_library` | 7 | Situations may be cross-entity |
| `step_log` | 0 | Infrastructure audit trail |
| `verification_pairs` | 0 | Infrastructure |

### Already NOT NULL (11 tables, no change needed)

campaign_batches, cost_budget, cost_ledger, debbie_buyer_review_feedback, debbie_review_exports, entity_value_propositions, letter_approvals, letter_campaigns, meeting_learnings, pain_gain_analyses, proposals

---

## DEFAULT Value Preservation

These tables had `DEFAULT 'next_chapter'` as TEXT. After type conversion, the default is re-set as `'next_chapter'::entity_type`:

| Table | Had DEFAULT? | New DEFAULT |
|-------|-------------|-------------|
| `campaign_batches` | Yes | `'next_chapter'::entity_type` |
| `debbie_buyer_review_feedback` | Yes | `'next_chapter'::entity_type` |
| `debbie_review_exports` | Yes | `'next_chapter'::entity_type` |
| `research_executions` | Yes | `'next_chapter'::entity_type` |
| `why_sell_buyer_pitches` | Yes | `'next_chapter'::entity_type` |
| `why_sell_narratives` | Yes | `'next_chapter'::entity_type` |

---

## Recommended Execution Order

1. **Pause writes** — Stop orchestrator + worker to prevent concurrent INSERT/UPDATE on entity columns during migration. Watchdog will restart them, so stop watchdog first:
   ```
   crontab -e  # comment out watchdog line
   kill $(pgrep -f orchestrator.py)
   kill $(pgrep -f worker.py)
   ```

2. **Run Tier 1** — Execute the Tier 1 BEGIN/COMMIT block. This converts 28 tables with zero data risk. Takes <1 second (no row scans needed for empty tables, minimal scans for populated ones).

3. **Verify Tier 1** — Run the verification query. All 28 tables should show `udt_name = 'entity_type'`.

4. **Run Tier 2A** — meeting_learnings cleanup + conversion. Verify row counts match expectations.

5. **Run Tier 2B** — engagement_buyers cleanup + conversion. Verify.

6. **Run Tier 2C** — intelligence_cache cleanup + conversion. Verify.

7. **Run Tier 3** — NOT NULL constraints + DEFAULT values.

8. **Final verification** — Run the final verification query. All 31 tables should show entity_type.

9. **Resume writes** — Uncomment watchdog cron, restart orchestrator + worker.

10. **Fix code** — Update the 10+ code files that write invalid entity values (see Tier 2 sections for specific files). This is critical: after migration, any INSERT with a non-enum entity value will fail with a PostgreSQL type error.

**Estimated downtime:** <5 minutes total. Tiers execute in seconds. Verification is the slowest part.

---

## Rollback Plan

### Tier 1 Rollback (if needed before Tier 2)

```sql
-- Revert all Tier 1 tables back to TEXT
-- Run one ALTER per table:
ALTER TABLE agent_queue ALTER COLUMN entity TYPE text USING entity::text;
ALTER TABLE agent_runs ALTER COLUMN entity TYPE text USING entity::text;
-- ... (repeat for all 28 Tier 1 tables)
```

### Tier 2 Rollback

Each Tier 2 sub-block is its own transaction. If a block fails, it auto-rolls back.

If cleanup UPDATEs succeeded but you need to revert:
- **meeting_learnings:** The original value 'hrcom' is not recoverable from a simple revert (there's no 'hrcom' entity_type value). You'd need to ALTER back to TEXT first, then restore the original values. However, since 'hrcom' was incorrect data, reverting to 'hrcom' is not recommended.
- **engagement_buyers / intelligence_cache:** Same — company names are not recoverable without a backup. Take a backup before executing.

### Recommended: Backup Before Execution

```sql
-- Create backup tables (run before any migration)
CREATE TABLE _backup_meeting_learnings AS SELECT id, entity FROM meeting_learnings;
CREATE TABLE _backup_engagement_buyers AS SELECT id, entity FROM engagement_buyers;
CREATE TABLE _backup_intelligence_cache AS SELECT id, entity FROM intelligence_cache;
```

### Full Rollback (nuclear option)

If everything needs to revert, convert all columns back to TEXT:

```sql
-- Generate rollback DDL for all 31 tables:
-- SELECT 'ALTER TABLE ' || table_name || ' ALTER COLUMN entity TYPE text USING entity::text;'
-- FROM information_schema.columns
-- WHERE column_name = 'entity'
--   AND table_schema = 'public'
--   AND udt_name = 'entity_type'
--   AND table_name NOT IN (
--     -- Exclude the 21 tables that were ALREADY entity_type before Phase C
--     'acquisition_targets','call_analysis','call_log','campaigns','companies',
--     'contacts','cost_log','deal_research','dialer_queue','dossier_final',
--     'dossier_provenance','dossier_runs','outreach_queue','pipeline_log',
--     'sent_log','tam_businesses','tam_final','tam_owner_profiles',
--     'tam_scrape_runs','tam_verifications','targets'
--   )
-- ORDER BY table_name;
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Type cast fails on unexpected value | LOW | HIGH (transaction rolls back) | Audit completed — all values mapped |
| Code writes non-enum value post-migration | **HIGH** | MEDIUM (INSERT fails) | Fix code files listed in Tier 2 before resuming writes |
| Concurrent write during migration | LOW | MEDIUM | Stop orchestrator/worker during migration |
| NOT NULL constraint breaks future INSERT | LOW | MEDIUM | Only applied to tables where entity is always required |
| DEFAULT 'next_chapter' masks multi-entity bugs | LOW | LOW | Acceptable for NC-dominant tables; remove defaults when multi-entity is active |

**Highest risk:** Code that writes invalid entity values (company names, 'hrcom') will break on INSERT after migration. The code fix is the most important follow-up task.

---

## Pre-existing Issues (Not Phase C)

### 1. Canyon State entity='unknown'
- **Table:** companies (already entity_type enum)
- **Issue:** 'unknown' is not in the 8-entity architecture. It's a 9th enum value added to accommodate unclassified data.
- **Fix:** `UPDATE companies SET entity = 'next_chapter' WHERE company_name = 'Canyon State Enterprises LLC.';` + delete the pending agent_queue classifier task.
- **Blocked by:** Manual decision — is Canyon State a Next Chapter deal? Phase B says vertical_id='home_services' which is NC-dominant.

### 2. Enum contains 'unknown' value
- **Issue:** Allows any code to write 'unknown' as entity, bypassing classification.
- **Fix:** Remove from enum after Canyon State is reclassified. PostgreSQL doesn't support DROP VALUE — requires enum recreation.
- **Recommendation:** Defer to Phase D.

### 3. page_versions has no entity column
- **Issue:** Unification plan listed it as potentially having entity. Live query confirms it does not.
- **Fix:** If entity tracking needed, add via ALTER TABLE (separate effort).

---

## Tables Already Using entity_type (21 — no changes needed)

For completeness, these tables already have `entity entity_type NOT NULL`:

| Table | Rows | Notes |
|-------|------|-------|
| acquisition_targets | 18 | |
| call_analysis | 2,273 | |
| call_log | 0 | |
| campaigns | 21 | |
| companies | 288 | Includes 1 'unknown' (Canyon State) |
| contacts | 2,191 | |
| cost_log | 549 | |
| deal_research | 134 | |
| dialer_queue | 646 | |
| dossier_final | 27 | |
| dossier_provenance | 2,322 | |
| dossier_runs | 1,638 | |
| outreach_queue | 82 | |
| pipeline_log | 1,345 | |
| sent_log | 27 | |
| tam_businesses | 8,350 | |
| tam_final | 3,000 | |
| tam_owner_profiles | 306 | |
| tam_scrape_runs | 287 | |
| tam_verifications | 6,113 | |
| targets | 201 | |

---

*Phase C generated 2026-04-03. Do not execute without review. See supabase-phase-c-migration.sql for the SQL.*

---

## Execution Log — 2026-04-03

**Branch:** `refactor/cross-domain-inventory`
**Executed by:** Claude Code (Sonnet 4.6)
**Code fixes commit:** `c8cdb81`
**Schema commit:** `3f75d98`

### Pre-execution fixes (code)
- `scripts/meeting_pages.py` — fixed KNOWN_ENTITIES/KNOWN_PEOPLE/title_entity_map mappings; added _VALID_ENTITIES guard on all entity inserts
- `backend/lib/engagement_engine.py` — intelligence_cache INSERT: hardcoded 'next_chapter' → `c.entity` via subselect
- `backend/lib/meeting_processor.py` — same fix as engagement_engine
- `backend/lib/sap_turbo.py` — added _VALID_ENTITIES guard on cost_log entity field
- `api/meetings/approve-learning.js` — added VALID_ENTITIES set; guard in writeToTarget()
- `backend/data/buyer-lists/insert_buyers.js` — engagement_buyers INSERT entity: companyName → 'next_chapter'

### Pre-execution data fixes
- `pain_gain_analyses` id=8: DELETE (entity='hr_media', duplicate of id=7 with wrong entity + empty asset_mappings; unique constraint prevented UPDATE)
- `meeting_learnings`: 30 rows with entity='hrcom' → UPDATE to 'next_chapter'
- `engagement_buyers`: 50 rows with company names (Air Control LLC, AquaScience, Design Precast & Pipe, Springer Floor Care, Wieser Concrete Products) → UPDATE to 'next_chapter'
- `intelligence_cache`: 21 rows with company names (Air Control LLC, AquaScience, Springer Floor Care LLC) → UPDATE to 'next_chapter'

### Tier 1 — 28 base tables (PASS)
Attempts: 4 (3 rolled back for discovery of unexpected issues)
- Attempt 1: FAIL — DEFAULT 'next_chapter'::text cannot be cast automatically (fix: DROP DEFAULT before ALTER, restore after)
- Attempt 2: FAIL — pain_gain_analyses entity='hr_media' invalid value (fix: DELETE id=8 pre-fix)
- Attempt 3: FAIL — disagreement_summary and pending_reviews are VIEWS, not tables; PostgreSQL blocked ALTER on columns used by view rules (fix: exclude views from table list, DROP/recreate views in transaction)
- Attempt 4: PASS — all 28 tables converted, both views dropped and recreated

Views excluded (not tables): `disagreement_summary`, `pending_reviews`
Defaults dropped (not restored — 'all' is invalid enum): `play_templates`, `situation_library`
Defaults dropped and restored as entity_type: `campaign_batches`, `debbie_buyer_review_feedback`, `debbie_review_exports`, `page_templates`, `research_executions`, `why_sell_buyer_pitches`, `why_sell_narratives`

### Tier 2A — meeting_learnings (PASS)
30 rows remapped ('hrcom' → 'next_chapter'), column converted.

### Tier 2B — engagement_buyers (PASS)
50 rows remapped (company names → 'next_chapter'), column converted, DEFAULT restored.

### Tier 2C — intelligence_cache (PASS)
21 rows remapped (company names → 'next_chapter'), column converted.

### Tier 3 — NOT NULL + defaults (PASS)
NOT NULL added (0 NULLs in all): engagement_buyers, research_executions, why_sell_buyer_pitches, why_sell_narratives, meeting_notes
DEFAULT 'next_chapter'::entity_type confirmed on: campaign_batches, debbie_buyer_review_feedback, debbie_review_exports, research_executions, why_sell_buyer_pitches, why_sell_narratives

### Final verification
- entity_type columns total: 63 (32 pre-existing + 31 converted)
- TEXT entity columns remaining: 3 (_backup_engagement_buyers, _backup_intelligence_cache, _backup_meeting_learnings — expected, pre-migration snapshots)
- All views present and functional: pending_reviews, disagreement_summary
