# Supabase Schema Unification Plan — Multi-Vertical Support
**Date:** 2026-04-03 | **Status:** ANALYSIS ONLY — no migrations executed
**Repo:** `~/Projects/master-crm-web` | **Branch:** `refactor/cross-domain-inventory`
**Schema source of truth:** `backend/data/10-SCHEMA-DESIGN.sql`

---

## The Two Axes

The system has two orthogonal classification dimensions that today are conflated:

| Axis | What it means | Current state | Examples |
|------|---------------|---------------|----------|
| **Entity** | Which business unit owns the record | `entity_type` enum with 8 values; most tables have it | `next_chapter`, `and_capital`, `revsup`, `the_forge`, `biolev`, `sea_sweet`, `precision_exploration`, `system` |
| **Vertical** | What industry the target company operates in | Free-text `vertical TEXT` on `companies` and `dialer_queue` only; not a first-class concept in the DB | `home_services`, `hr_media`, `precast_concrete`, `water_treatment`, `floor_care` |

**Key insight:** Entity is about **who works the deal**. Vertical is about **what industry the deal is in**. Next Chapter can work home_services deals AND hr_media deals. AND Capital can work deals in any vertical. These axes must be independent.

---

## Current Schema Inventory

### Tables with `entity` column (from `10-SCHEMA-DESIGN.sql`)

Already designed correctly — entity column present and indexed:

| Table | Entity Default | Notes |
|-------|---------------|-------|
| `companies` | NOT NULL | Also has `vertical TEXT` (free-text) |
| `contacts` | NOT NULL | |
| `targets` | NOT NULL | Core pipeline table |
| `campaigns` | NOT NULL | 17 seed campaigns, entity-tagged |
| `dossier_final` | NOT NULL | |
| `dossier_runs` | NOT NULL | |
| `dossier_provenance` | NOT NULL | |
| `cost_log` | NOT NULL | |
| `sent_log` | NOT NULL | |
| `call_log` | NOT NULL | |
| `call_analysis` | NOT NULL | |
| `outreach_queue` | NOT NULL | |
| `dialer_queue` | NOT NULL | Also has `vertical TEXT` |
| `pipeline_log` | NOT NULL | |
| `tam_businesses` | DEFAULT 'next_chapter' | TAM engine — currently NC-only |
| `tam_final` | DEFAULT 'next_chapter' | |
| `tam_verifications` | DEFAULT 'next_chapter' | |
| `tam_owner_profiles` | DEFAULT 'next_chapter' | |
| `tam_scrape_runs` | DEFAULT 'next_chapter' | |
| `deal_research` | NOT NULL | |
| `acquisition_targets` | NOT NULL | |

### Tables added via later migrations (may or may not match design)

| Table | Source | Has `entity`? | Notes |
|-------|--------|---------------|-------|
| `campaign_batches` | migration 003 | Yes (TEXT, DEFAULT 'next_chapter') | Governor: 250/150 rule |
| `call_outcomes` | migration 003 | Inherited via `batch_id` FK | |
| `meeting_notes` | migration 003 | Has `entity_id TEXT` (not `entity`) | Naming inconsistency |
| `stress_test_runs` | migration 004 | No | Infrastructure — correct |
| `benchmark_scores` | migration 004 | No | Infrastructure — correct |
| `agent_performance_log` | migration 004 | No | Infrastructure — correct |
| `re_enrichment_results` | migration 004 | No | Infrastructure — correct |
| `lovable_benchmark` | migration 004 | No | Infrastructure — correct |
| `guardrail_violations` | migration 20260330 | Yes (TEXT) | Should use enum |
| `user_sessions` | migration 20260330 | No | System table — correct |
| `why_sell_narratives` | migration 20260330 | Yes (TEXT, DEFAULT 'next_chapter') | Should use enum |
| `why_sell_buyer_pitches` | migration 20260330 | Yes (TEXT, DEFAULT 'next_chapter') | Should use enum |
| `debbie_buyer_review_feedback` | migration 20260401 | Yes (TEXT, DEFAULT 'next_chapter') | Should use enum |
| `debbie_review_exports` | migration 20260401 | Yes (TEXT, DEFAULT 'next_chapter') | Should use enum |

### Tables referenced in code but NOT in `10-SCHEMA-DESIGN.sql`

These were created before the schema design or outside of it:

| Table | Has `entity`? | Issue |
|-------|---------------|-------|
| `proposals` | Unknown — not in design file | Legacy table, heavily used (server.py, worker.py, regenerate.py) |
| `engagement_buyers` | No | Linked to proposals, used in hub generation |
| `letter_approvals` | Unknown | Used by server.py, letter-approval-component.js |
| `page_versions` | Has `entity TEXT` in code | Used by regenerate.py, version-widget.js |
| `cost_budget` | Has `entity TEXT` | Budget tracking per entity |
| `cost_ledger` | Has `entity TEXT` | Cost tracking per entity |
| `agent_queue` | Has `entity TEXT` in code | Core work queue |
| `agent_runs` | Unknown | Execution log |
| `research_methods` | No | Cross-entity knowledge base — correct |
| `research_executions` | Has `entity TEXT` | Exa search log |
| `page_comments` | Unknown | In-page commenting |
| `notifications` | Unknown | Notification system |
| `research_cache` | Unknown | Research caching |
| `conflict_resolutions` | Unknown | Conflict resolver |

### Intentionally entity-free tables

| Table | Reason |
|-------|--------|
| `do_not_call` | **Universal DNC** — one block = blocked everywhere (CLAUDE.md hard rule) |
| `research_methods` | Cross-entity methodology registry |
| `audits`, `harvests`, `stories`, `analysis` | System/ops tables |
| `skills_registry` | Has `entity_affinity TEXT` but not a filter |
| `user_sessions` | System tracking |
| Stress test tables (5) | Infrastructure/benchmarking |

### Entity-specific tables (one table per entity)

| Table | Entity | Domain |
|-------|--------|--------|
| `nc_owner_profiles` | next_chapter | Sell-side owner intelligence |
| `and_investor_profiles` | and_capital | LP/investor intelligence |
| `and_events` | and_capital | Event tracking |
| `and_event_targets` | and_capital | Event-contact links |
| `ru_placements` | revsup | Recruiting placements |
| `forge_boomerang_targets` | the_forge | Athlete recruitment |

---

## What Needs to Change for Multi-Vertical

### Change 1: Add `vertical_id TEXT` to key transactional tables

The `vertical` column already exists on `companies` and `dialer_queue` as free-text. Promote it to a consistent column across tables that hold deal-level data:

| Table | Action | Rationale |
|-------|--------|-----------|
| `companies` | Already has `vertical TEXT` — rename to `vertical_id` for consistency | Source of truth for company's industry |
| `targets` | **ADD** `vertical_id TEXT` | Pipeline queries need vertical filtering (e.g., "show me all hr_media targets") |
| `proposals` | **ADD** `vertical_id TEXT` | Proposals reference companies; need vertical for letter engine vcfg selection |
| `engagement_buyers` | No change | Inherits vertical via proposal_id FK → proposals |
| `dossier_final` | **ADD** `vertical_id TEXT` | Research content is vertical-specific |
| `dialer_queue` | Already has `vertical TEXT` — rename to `vertical_id` | |
| `outreach_queue` | **ADD** `vertical_id TEXT` | Letter variant selection depends on vertical |
| `debbie_buyer_review_feedback` | **ADD** `vertical_id TEXT` | Feedback is per-vertical research |
| `letter_campaigns` / `campaign_batches` | **ADD** `vertical_id TEXT` | Letters use vertical config for valuation narrative |
| `research_executions` | **ADD** `vertical_id TEXT` | Exa templates come from vertical config |

**Do NOT add `vertical_id` to:**
- `do_not_call` — universal
- `cost_budget`, `cost_log`, `cost_ledger` — budget is per entity, not per vertical
- `agent_queue`, `agent_runs` — infrastructure tables
- `pipeline_log` — action audit trail, entity-level granularity is sufficient
- TAM tables — currently NC-only; revisit when TAM supports other entities
- Entity-specific tables (nc_owner_profiles, etc.) — vertical is implied by entity context

### Change 2: Normalize `entity` column types across migrations

Migration-era tables use `entity TEXT DEFAULT 'next_chapter'`. The schema design uses `entity entity_type NOT NULL`. These should match.

| Table | Current | Target |
|-------|---------|--------|
| `campaign_batches` | `TEXT DEFAULT 'next_chapter'` | `entity_type NOT NULL DEFAULT 'next_chapter'` |
| `meeting_notes` | `entity_id TEXT` (wrong name!) | `entity entity_type NOT NULL` |
| `guardrail_violations` | `TEXT` | `entity_type` |
| `why_sell_narratives` | `TEXT DEFAULT 'next_chapter'` | `entity_type NOT NULL DEFAULT 'next_chapter'` |
| `why_sell_buyer_pitches` | `TEXT DEFAULT 'next_chapter'` | `entity_type NOT NULL DEFAULT 'next_chapter'` |
| `debbie_buyer_review_feedback` | `TEXT DEFAULT 'next_chapter'` | `entity_type NOT NULL DEFAULT 'next_chapter'` |
| `debbie_review_exports` | `TEXT DEFAULT 'next_chapter'` | `entity_type NOT NULL DEFAULT 'next_chapter'` |
| `page_versions` | `TEXT` (if exists) | `entity_type` |
| `cost_budget` | `TEXT` (if exists) | `entity_type` |
| `cost_ledger` | `TEXT` (if exists) | `entity_type` |
| `agent_queue` | `TEXT` (if exists) | `entity_type` |
| `research_executions` | `TEXT DEFAULT 'next_chapter'` | `entity_type NOT NULL DEFAULT 'next_chapter'` |

**Migration concern:** The `entity_type` enum must already exist (it's in 10-SCHEMA-DESIGN.sql). If the live DB was bootstrapped from that file, it exists. If not, create it first.

### Change 3: Add `entity` to tables that the design says should have it but might not in production

These are the tables in `10-SCHEMA-DESIGN.sql` that have `entity NOT NULL` but whose live state is uncertain:

| Table | Risk |
|-------|------|
| `proposals` | **HIGH** — not in design file at all. Needs entity + vertical_id added. Heavily queried. |
| `engagement_buyers` | **MEDIUM** — not in design file. May need entity for direct queries (not just via FK). |
| `letter_approvals` | **LOW** — small table, infrequent queries |

### Change 4: Create vertical_id validation

Option A (recommended): **Soft validation only** — `vertical_id TEXT` as free-text, validated by application code against `lib/config/verticals/*.json` file names. No enum, no foreign key.

Option B: Create a `verticals` reference table and FK. More rigorous but adds migration complexity when new verticals are added (must INSERT before referencing).

**Recommendation: Option A.** The vertical config JSON files are the source of truth. Adding a SQL enum or reference table means two places to update when a vertical is added. The application code already validates via `load_vertical()`.

### Change 5: Entity-specific tables — keep or unify?

| Table | Recommendation | Rationale |
|-------|---------------|-----------|
| `nc_owner_profiles` | **Keep as-is** | NC-specific fields (az_roc_license, bbb_rating, retirement_timeline) have no equivalent in other entities |
| `and_investor_profiles` | **Keep as-is** | AND-specific fields (aum, finra_risk, propensity_score) are investor-domain |
| `and_events` / `and_event_targets` | **Keep as-is** | Only AND Capital does event-based outreach |
| `ru_placements` | **Keep as-is** | Recruiting placements are RevsUp-only |
| `forge_boomerang_targets` | **Keep as-is** | Completely different domain |

**Do NOT try to unify these into a polymorphic table.** The column sets are radically different. A JSONB `metadata` column would lose type safety and make queries harder. These tables are small, well-scoped, and rarely cross entity boundaries.

### Change 6: TAM tables — unlock for multi-entity

Currently hardcoded `DEFAULT 'next_chapter'`. When AND Capital or RevsUp need TAM functionality:

| Table | Change |
|-------|--------|
| `tam_businesses` | Change `DEFAULT 'next_chapter'` to `NOT NULL` (force explicit entity) |
| `tam_final` | Same |
| `tam_verifications` | Same |
| `tam_owner_profiles` | Same |
| `tam_scrape_runs` | Same |

**Not urgent** — TAM is only used for NC home_services market sizing today. But removing the default now prevents future NC-only assumptions from leaking in.

---

## Index Strategy

### New indexes needed for multi-vertical queries

```sql
-- Vertical filtering (new)
CREATE INDEX idx_targets_vertical ON targets(vertical_id);
CREATE INDEX idx_proposals_vertical ON proposals(vertical_id);
CREATE INDEX idx_dossier_final_vertical ON dossier_final(vertical_id);
CREATE INDEX idx_research_executions_vertical ON research_executions(vertical_id);

-- Composite indexes for common query patterns
CREATE INDEX idx_targets_entity_vertical ON targets(entity, vertical_id);
CREATE INDEX idx_targets_entity_status ON targets(entity, pipeline_status);
CREATE INDEX idx_proposals_entity_vertical ON proposals(entity, vertical_id);

-- Debbie review feedback (vertical-aware lookups)
CREATE INDEX idx_debbie_feedback_vertical ON debbie_buyer_review_feedback(vertical_id);
CREATE INDEX idx_debbie_feedback_buyer_section ON debbie_buyer_review_feedback(buyer_slug, section_key);
```

### Existing indexes (already in design, verify they exist in live DB)

```sql
-- These should already exist per 10-SCHEMA-DESIGN.sql
idx_companies_entity, idx_contacts_entity, idx_targets_entity,
idx_targets_campaign, idx_targets_status, idx_dossier_final_entity,
idx_call_analysis_entity, idx_dialer_queue_entity, idx_sent_log_entity,
idx_cost_log_entity, idx_pipeline_log_entity, idx_tam_businesses_entity,
idx_do_not_call_phone, idx_do_not_call_company
```

---

## Query Changes Required

### Python backend — orchestrator.py
```
Current:  SELECT FROM targets WHERE entity IS NULL (classifier scan)
Change:   No change needed — entity classification is entity-level, not vertical-level
```

### Python backend — regenerate.py
```
Current:  SELECT FROM targets WHERE pipeline_status='RESEARCHED' AND report_generated_at IS NULL
Change:   May want to ADD: WHERE vertical_id = ? for vertical-scoped regeneration
          But current behavior (regenerate all) is fine for now
```

### Python backend — worker.py
```
Current:  agent_queue claims don't filter by vertical
Change:   No change needed — queue routing is by agent_name, not vertical
```

### Python lib — letter_engine.py
```
Current:  Caller passes vcfg= manually; no DB lookup of vertical
Change:   When letter_engine receives a company_id, it should:
          1. Look up company.vertical_id from proposals or targets
          2. Call load_vertical(vertical_id) to get vcfg
          3. Pass vcfg to render()
          This replaces the current "caller must know to pass vcfg" gap
```

### Python lib — salesfinity_client.py
```
Current:  DNC check queries do_not_call by phone
Change:   No change — DNC is universal, intentionally entity/vertical agnostic
```

### Frontend JS — debbie-buyer-review.html
```
Current:  Reads entity from per-buyer JSON (buyer.entity)
Change:   Also read vertical_id from buyer JSON for Supabase writes:
          saveFeedback() should include vertical_id in the payload
          Currently writes entity only
```

### Frontend JS — supabase queries (all pages)
```
Current:  Most queries don't filter by entity or vertical
Change:   Hub pages should pass entity filter to prevent cross-entity data leaks
          Buyer review should pass vertical_id to feedback saves
```

### Server.py API routes
```
POST /api/buyer-feedback:
  Current: saves to buyer_feedback (unknown schema)
  Change:  include entity + vertical_id in insert

POST /api/letter-send:
  Current: calls lob_client directly
  Change:  look up vertical_id from proposal → pass vcfg to letter_engine

POST /api/campaign-create:
  Current: unknown
  Change:  require entity + optional vertical_id
```

---

## Data Migration Sequence

### Phase A: Non-breaking column additions (safe, reversible)

```sql
-- 1. Add vertical_id to tables that need it (nullable, no default)
ALTER TABLE targets ADD COLUMN IF NOT EXISTS vertical_id TEXT;
ALTER TABLE proposals ADD COLUMN IF NOT EXISTS vertical_id TEXT;
ALTER TABLE dossier_final ADD COLUMN IF NOT EXISTS vertical_id TEXT;
ALTER TABLE outreach_queue ADD COLUMN IF NOT EXISTS vertical_id TEXT;
ALTER TABLE debbie_buyer_review_feedback ADD COLUMN IF NOT EXISTS vertical_id TEXT;
ALTER TABLE research_executions ADD COLUMN IF NOT EXISTS vertical_id TEXT;
ALTER TABLE campaign_batches ADD COLUMN IF NOT EXISTS vertical_id TEXT;

-- 2. Rename existing 'vertical' to 'vertical_id' where it exists
ALTER TABLE companies RENAME COLUMN vertical TO vertical_id;
ALTER TABLE dialer_queue RENAME COLUMN vertical TO vertical_id;

-- 3. Fix meeting_notes entity column name
ALTER TABLE meeting_notes RENAME COLUMN entity_id TO entity;

-- 4. Create new indexes
CREATE INDEX IF NOT EXISTS idx_targets_vertical ON targets(vertical_id);
CREATE INDEX IF NOT EXISTS idx_targets_entity_vertical ON targets(entity, vertical_id);
CREATE INDEX IF NOT EXISTS idx_proposals_vertical ON proposals(vertical_id);
```

### Phase B: Backfill vertical_id from existing data

```sql
-- Backfill targets.vertical_id from companies.vertical_id (via company_id FK)
UPDATE targets t
SET vertical_id = c.vertical_id
FROM companies c
WHERE t.company_id = c.id AND t.vertical_id IS NULL AND c.vertical_id IS NOT NULL;

-- Backfill proposals.vertical_id — need to map company_name → vertical
-- This requires a lookup script, not a single SQL statement
-- Script: for each proposal, find matching company, copy vertical_id

-- Backfill debbie_buyer_review_feedback.vertical_id
-- All current feedback is for hr_media vertical
UPDATE debbie_buyer_review_feedback SET vertical_id = 'hr_media' WHERE vertical_id IS NULL;

-- Backfill research_executions.vertical_id
-- Current executions are hr_media or home_services based on company
-- Needs script-level classification
```

### Phase C: Tighten constraints (only after backfill is verified)

```sql
-- Add NOT NULL constraints after all data is backfilled
-- ALTER TABLE targets ALTER COLUMN vertical_id SET NOT NULL;
-- ^ Only after every row has a value

-- Normalize entity columns to use enum
-- ALTER TABLE campaign_batches ALTER COLUMN entity TYPE entity_type USING entity::entity_type;
-- ^ Test carefully — any value not in enum will fail
```

---

## Breaking Changes

| Change | Impact | Mitigation |
|--------|--------|------------|
| `companies.vertical` → `companies.vertical_id` rename | Any code referencing `companies.vertical` breaks | Grep + update all references before migration |
| `dialer_queue.vertical` → `dialer_queue.vertical_id` rename | Same | Grep + update |
| `meeting_notes.entity_id` → `meeting_notes.entity` rename | Code referencing `entity_id` breaks | Grep + update |
| Entity TEXT → entity_type enum conversion | Any value not in the enum causes INSERT failure | Verify all existing values match enum before ALTER |
| `proposals` gets entity + vertical_id columns | No breaks (nullable add) but queries that should filter by entity/vertical won't until code is updated | Update code incrementally |

---

## Risks and Concerns

1. **Live database vs. design file divergence**: The `10-SCHEMA-DESIGN.sql` was never fully applied to the live Supabase instance. Many tables were created ad-hoc or via migration files. Before any migration, run `\d tablename` in psql (or Supabase SQL editor) to confirm actual column types vs. design assumptions.

2. **Entity enum values**: The design defines 8 entity types. If the live DB uses TEXT columns, there may be values like `""`, `null`, or typos that don't match the enum. Run `SELECT DISTINCT entity FROM <table>` on every table before converting to enum type.

3. **No `proposals` table in design**: The `proposals` table is one of the most heavily used tables but doesn't appear in `10-SCHEMA-DESIGN.sql`. Its actual schema needs to be introspected from the live DB before planning migrations.

4. **Supabase RLS**: Migrations 20260330 adds RLS policies. Adding columns doesn't break RLS, but if RLS policies filter on `entity`, they may need updating for `vertical_id` filtering.

5. **View dependencies**: Entity-scoped views (`nc_targets`, `and_targets`, etc.) filter on `entity`. Adding `vertical_id` doesn't break them, but if you want vertical-scoped views (e.g., `hr_media_targets`), those would need to be created.

6. **Column rename on `companies.vertical`**: This is the highest-risk single change. Every query that references `companies.vertical` will break. Grep shows references in: classification agents (JS), dialer_queue, schema design SQL. Must update all code references in the same deployment.

---

## Recommended Execution Order

1. **Introspect live schema** — Run `\d` on every table listed above to confirm actual vs. design state. Document differences.
2. **Phase A migrations** — Non-breaking column additions + renames. Deploy code changes for renames simultaneously.
3. **Phase B backfill** — Run backfill scripts for vertical_id population.
4. **Update code** — Add vertical_id to all write paths (letter_engine callers, debbie review feedback, research executions).
5. **Phase C constraints** — Only after all data is clean and all code writes include vertical_id.
6. **Update entity-scoped views** — Add vertical-scoped views if needed.
7. **Entity enum normalization** — Convert TEXT → entity_type on migration-era tables. Last step, highest risk.

---

## What This Unlocks

Once vertical_id is a first-class column:
- `debbie_buyer_research.py --vertical home_services` writes `vertical_id='home_services'` to research_executions
- `letter_engine.py` auto-resolves vcfg from `proposals.vertical_id` — callers stop needing to pass it
- `proposal-auto-generator.js` can call `setVertical()` from DB-stored config
- Hub pages can filter by vertical: "show me all hr_media proposals"
- Cost tracking can break down by entity AND vertical
- TAM engine can expand beyond next_chapter without architectural changes
- New verticals work end-to-end by adding one JSON file + one vertical_id value — no schema changes
