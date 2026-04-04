-- ============================================================
-- PHASE C: Entity TEXT → entity_type Enum Normalization
-- Instance: dwrnfpjcvydhmhnvyzov (master-crm)
-- Generated: 2026-04-03 | Branch: refactor/cross-domain-inventory
-- Prereq: Phase A (vertical_id columns) + Phase B (backfill) complete
-- Status: ANALYSIS ONLY — DO NOT EXECUTE without review
-- ============================================================
--
-- SUMMARY:
--   31 tables have entity TEXT columns that should use entity_type enum.
--   21 tables with entity_type enum already exist (no changes needed).
--   Split into 3 risk tiers + NOT NULL + DEFAULT blocks.
--
-- ENUM STATE:
--   Live entity_type values: next_chapter, and_capital, revsup, the_forge,
--     biolev, sea_sweet, precision_exploration, system, unknown
--   Architecture doc lists 8 entities (excludes 'unknown').
--   'unknown' was added to enum at some point — used by Canyon State
--   and 1 pending classifier task. No ALTER TYPE needed for Phase C.
--

-- ═══════════════════════════════════════════════════════════════
-- TIER 1: SAFE CONVERSIONS (28 tables)
-- All existing values are valid entity_type enum variants. No NULLs.
-- Risk: MINIMAL — type cast will succeed on all rows.
-- ═══════════════════════════════════════════════════════════════

BEGIN; -- Tier 1 transaction

-- ─── Tier 1A: Populated tables with clean data (11 tables) ────

-- agent_queue: 7 rows (next_chapter=6, unknown=1)
-- 'unknown' is valid — it's a pending classifier task for Canyon State
ALTER TABLE agent_queue
  ALTER COLUMN entity TYPE entity_type USING entity::entity_type;

-- agent_runs: 12 rows (all next_chapter)
ALTER TABLE agent_runs
  ALTER COLUMN entity TYPE entity_type USING entity::entity_type;

-- cost_budget: 8 rows (next_chapter=2, and_capital=2, revsup=2, system=2)
ALTER TABLE cost_budget
  ALTER COLUMN entity TYPE entity_type USING entity::entity_type;

-- debbie_buyer_review_feedback: 8 rows (all next_chapter)
ALTER TABLE debbie_buyer_review_feedback
  ALTER COLUMN entity TYPE entity_type USING entity::entity_type;

-- entity_value_propositions: 3 rows (all next_chapter)
ALTER TABLE entity_value_propositions
  ALTER COLUMN entity TYPE entity_type USING entity::entity_type;

-- pain_gain_analyses: 1 row (next_chapter)
ALTER TABLE pain_gain_analyses
  ALTER COLUMN entity TYPE entity_type USING entity::entity_type;

-- play_executions: 6 rows (all next_chapter)
ALTER TABLE play_executions
  ALTER COLUMN entity TYPE entity_type USING entity::entity_type;

-- play_templates: 8 rows (all next_chapter)
ALTER TABLE play_templates
  ALTER COLUMN entity TYPE entity_type USING entity::entity_type;

-- proposals: 6 rows (all next_chapter)
ALTER TABLE proposals
  ALTER COLUMN entity TYPE entity_type USING entity::entity_type;

-- research_executions: 50 rows (all next_chapter)
ALTER TABLE research_executions
  ALTER COLUMN entity TYPE entity_type USING entity::entity_type;

-- situation_library: 7 rows (all next_chapter)
ALTER TABLE situation_library
  ALTER COLUMN entity TYPE entity_type USING entity::entity_type;


-- ─── Tier 1B: Empty tables — zero data risk (17 tables) ──────

-- campaign_batches: 0 rows
ALTER TABLE campaign_batches
  ALTER COLUMN entity TYPE entity_type USING entity::entity_type;

-- cost_ledger: 0 rows
ALTER TABLE cost_ledger
  ALTER COLUMN entity TYPE entity_type USING entity::entity_type;

-- debbie_review_exports: 0 rows
ALTER TABLE debbie_review_exports
  ALTER COLUMN entity TYPE entity_type USING entity::entity_type;

-- estimate_accuracy: 0 rows
ALTER TABLE estimate_accuracy
  ALTER COLUMN entity TYPE entity_type USING entity::entity_type;

-- feedback_log: 0 rows
ALTER TABLE feedback_log
  ALTER COLUMN entity TYPE entity_type USING entity::entity_type;

-- guardrail_log: 0 rows
ALTER TABLE guardrail_log
  ALTER COLUMN entity TYPE entity_type USING entity::entity_type;

-- human_review_queue: 0 rows
ALTER TABLE human_review_queue
  ALTER COLUMN entity TYPE entity_type USING entity::entity_type;

-- letter_approvals: 0 rows
ALTER TABLE letter_approvals
  ALTER COLUMN entity TYPE entity_type USING entity::entity_type;

-- letter_campaigns: 0 rows
ALTER TABLE letter_campaigns
  ALTER COLUMN entity TYPE entity_type USING entity::entity_type;

-- meeting_notes: 0 rows (entity column added by Phase A)
ALTER TABLE meeting_notes
  ALTER COLUMN entity TYPE entity_type USING entity::entity_type;

-- nurture_schedule: 0 rows
ALTER TABLE nurture_schedule
  ALTER COLUMN entity TYPE entity_type USING entity::entity_type;

-- page_templates: 0 rows
ALTER TABLE page_templates
  ALTER COLUMN entity TYPE entity_type USING entity::entity_type;

-- response_log: 0 rows
ALTER TABLE response_log
  ALTER COLUMN entity TYPE entity_type USING entity::entity_type;

-- step_log: 0 rows
ALTER TABLE step_log
  ALTER COLUMN entity TYPE entity_type USING entity::entity_type;

-- verification_pairs: 0 rows
ALTER TABLE verification_pairs
  ALTER COLUMN entity TYPE entity_type USING entity::entity_type;

-- why_sell_buyer_pitches: 0 rows
ALTER TABLE why_sell_buyer_pitches
  ALTER COLUMN entity TYPE entity_type USING entity::entity_type;

-- why_sell_narratives: 0 rows
ALTER TABLE why_sell_narratives
  ALTER COLUMN entity TYPE entity_type USING entity::entity_type;

COMMIT; -- End Tier 1


-- ═══════════════════════════════════════════════════════════════
-- TIER 1 VERIFICATION (run between Tier 1 and Tier 2)
-- ═══════════════════════════════════════════════════════════════

-- Verify all Tier 1 tables now use entity_type:
-- SELECT table_name, column_name, udt_name
-- FROM information_schema.columns
-- WHERE column_name = 'entity'
--   AND table_schema = 'public'
--   AND table_name IN (
--     'agent_queue','agent_runs','cost_budget','debbie_buyer_review_feedback',
--     'entity_value_propositions','pain_gain_analyses','play_executions',
--     'play_templates','proposals','research_executions','situation_library',
--     'campaign_batches','cost_ledger','debbie_review_exports','estimate_accuracy',
--     'feedback_log','guardrail_log','human_review_queue','letter_approvals',
--     'letter_campaigns','meeting_notes','nurture_schedule','page_templates',
--     'response_log','step_log','verification_pairs','why_sell_buyer_pitches',
--     'why_sell_narratives'
--   )
-- ORDER BY table_name;
-- Expected: all rows show udt_name = 'entity_type'


-- ═══════════════════════════════════════════════════════════════
-- TIER 2: CLEANUP + CONVERSION (3 tables)
-- Non-standard values that map to valid enum variants.
-- UPDATE first, verify, then ALTER TYPE.
-- Risk: MODERATE — data cleanup required but mappings are confirmed.
-- ═══════════════════════════════════════════════════════════════

-- ─── 2A: meeting_learnings (41 rows) ─────────────────────────
-- Problem: 30 rows have entity='hrcom' — not a valid enum variant.
--          HR.com is a Next Chapter deal; correct entity is 'next_chapter'.
-- Root cause: meeting transcript pipeline wrote client identifier, not entity.
-- Code to fix: scripts/meeting_pages.py, api/meetings/approve-learning.js

BEGIN;

-- Pre-check
-- SELECT entity, count(*) FROM meeting_learnings GROUP BY entity ORDER BY entity;
-- Expected: hrcom=30, next_chapter=11

UPDATE meeting_learnings
  SET entity = 'next_chapter'
  WHERE entity = 'hrcom';
-- Expected: 30 rows updated

-- Post-check
-- SELECT entity, count(*) FROM meeting_learnings GROUP BY entity ORDER BY entity;
-- Expected: next_chapter=41

ALTER TABLE meeting_learnings
  ALTER COLUMN entity TYPE entity_type USING entity::entity_type;

COMMIT;


-- ─── 2B: engagement_buyers (224 rows) ────────────────────────
-- Problem: 50 rows have company names as entity values:
--   'Air Control LLC' (10), 'Springer Floor Care' (10),
--   'Design Precast & Pipe, Inc.' (10), 'AquaScience' (10),
--   'Wieser Concrete Products, Inc.' (10)
-- All 5 parent proposals confirmed as entity='next_chapter'.
-- Root cause: hub/buyer generation code wrote company_name into entity column.
-- Code to fix: backend/lib/engagement_engine.py, backend/lib/company_hub.py,
--              backend/data/buyer-lists/insert_buyers.js

BEGIN;

-- Pre-check
-- SELECT entity, count(*) FROM engagement_buyers GROUP BY entity ORDER BY entity;
-- Expected: 5 company names (10 each) + next_chapter=174

UPDATE engagement_buyers
  SET entity = 'next_chapter'
  WHERE entity NOT IN (
    'next_chapter', 'and_capital', 'revsup', 'the_forge',
    'biolev', 'sea_sweet', 'precision_exploration', 'system', 'unknown'
  );
-- Expected: 50 rows updated

-- Post-check
-- SELECT entity, count(*) FROM engagement_buyers GROUP BY entity ORDER BY entity;
-- Expected: next_chapter=224

ALTER TABLE engagement_buyers
  ALTER COLUMN entity TYPE entity_type USING entity::entity_type;

COMMIT;


-- ─── 2C: intelligence_cache (35 rows) ────────────────────────
-- Problem: 21 rows have company names as entity values:
--   'AquaScience' (6), 'Air Control LLC' (7), 'Springer Floor Care LLC' (8)
-- All have company_id linking to next_chapter companies.
-- Root cause: intelligence cache writer used company_name instead of entity.
-- Code to fix: backend/lib/engagement_engine.py, backend/lib/profile_engine.py,
--              backend/lib/meeting_engine.py

BEGIN;

-- Pre-check
-- SELECT entity, count(*) FROM intelligence_cache GROUP BY entity ORDER BY entity;
-- Expected: 3 company names + next_chapter=14

UPDATE intelligence_cache
  SET entity = 'next_chapter'
  WHERE entity NOT IN (
    'next_chapter', 'and_capital', 'revsup', 'the_forge',
    'biolev', 'sea_sweet', 'precision_exploration', 'system', 'unknown'
  );
-- Expected: 21 rows updated

-- Post-check
-- SELECT entity, count(*) FROM intelligence_cache GROUP BY entity ORDER BY entity;
-- Expected: next_chapter=35

ALTER TABLE intelligence_cache
  ALTER COLUMN entity TYPE entity_type USING entity::entity_type;

COMMIT;


-- ═══════════════════════════════════════════════════════════════
-- TIER 2 VERIFICATION
-- ═══════════════════════════════════════════════════════════════

-- Verify all Tier 2 tables now use entity_type:
-- SELECT table_name, column_name, udt_name
-- FROM information_schema.columns
-- WHERE column_name = 'entity'
--   AND table_schema = 'public'
--   AND table_name IN ('meeting_learnings','engagement_buyers','intelligence_cache')
-- ORDER BY table_name;
-- Expected: all rows show udt_name = 'entity_type'

-- Verify no non-enum values remain anywhere:
-- SELECT table_name, count(*)
-- FROM (
--   SELECT 'meeting_learnings' AS table_name, entity FROM meeting_learnings
--   UNION ALL SELECT 'engagement_buyers', entity::text FROM engagement_buyers
--   UNION ALL SELECT 'intelligence_cache', entity::text FROM intelligence_cache
-- ) sub
-- WHERE entity::text NOT IN (
--   'next_chapter','and_capital','revsup','the_forge',
--   'biolev','sea_sweet','precision_exploration','system','unknown'
-- )
-- GROUP BY table_name;
-- Expected: 0 rows


-- ═══════════════════════════════════════════════════════════════
-- TIER 3: NOT NULL CONSTRAINTS + DEFAULTS
-- Only after Tier 1 + Tier 2 are verified.
-- Risk: LOW for tables with 0 NULLs. NOT NULL on nullable columns
-- will fail if any row has NULL — but audit shows 0 NULLs in all tables.
-- ═══════════════════════════════════════════════════════════════

BEGIN;

-- ─── 3A: Add NOT NULL where entity is always required ────────
-- These tables are entity-scoped by design; NULL entity is a data bug.
-- Current state: 0 NULLs in all, verified by live audit.

-- engagement_buyers: entity identifies the business unit (all rows have values)
ALTER TABLE engagement_buyers
  ALTER COLUMN entity SET NOT NULL;

-- research_executions: every research run is entity-scoped
ALTER TABLE research_executions
  ALTER COLUMN entity SET NOT NULL;

-- why_sell_buyer_pitches: entity-scoped sales content
ALTER TABLE why_sell_buyer_pitches
  ALTER COLUMN entity SET NOT NULL;

-- why_sell_narratives: entity-scoped narratives
ALTER TABLE why_sell_narratives
  ALTER COLUMN entity SET NOT NULL;

-- meeting_notes: entity required per schema design (Phase A addition)
ALTER TABLE meeting_notes
  ALTER COLUMN entity SET NOT NULL;


-- ─── 3B: Keep nullable (entity is contextual/optional) ───────
-- These tables are infrastructure, system, or cross-entity by design.
-- Adding NOT NULL would break future inserts where entity isn't known.
--
-- KEPT NULLABLE:
--   agent_queue       — entity may not be known at enqueue time (classifier)
--   agent_runs        — inherits from agent_queue; same constraint
--   estimate_accuracy — correction log; entity is contextual
--   feedback_log      — meta/system table
--   guardrail_log     — system monitoring
--   human_review_queue — system routing
--   intelligence_cache — may cache cross-entity data
--   nurture_schedule  — 0 rows; entity routing TBD
--   page_templates    — templates can be cross-entity
--   play_executions   — may inherit entity from play_templates
--   play_templates    — some plays serve multiple entities
--   response_log      — response routing TBD
--   situation_library — situations may be cross-entity
--   step_log          — infrastructure audit trail
--   verification_pairs — infrastructure


-- ─── 3C: Set/preserve DEFAULT values ─────────────────────────
-- Tables that had DEFAULT 'next_chapter' as TEXT need the default
-- re-cast to entity_type after the type conversion.

ALTER TABLE campaign_batches
  ALTER COLUMN entity SET DEFAULT 'next_chapter'::entity_type;

ALTER TABLE debbie_buyer_review_feedback
  ALTER COLUMN entity SET DEFAULT 'next_chapter'::entity_type;

ALTER TABLE debbie_review_exports
  ALTER COLUMN entity SET DEFAULT 'next_chapter'::entity_type;

ALTER TABLE research_executions
  ALTER COLUMN entity SET DEFAULT 'next_chapter'::entity_type;

ALTER TABLE why_sell_buyer_pitches
  ALTER COLUMN entity SET DEFAULT 'next_chapter'::entity_type;

ALTER TABLE why_sell_narratives
  ALTER COLUMN entity SET DEFAULT 'next_chapter'::entity_type;

COMMIT;


-- ═══════════════════════════════════════════════════════════════
-- FINAL VERIFICATION
-- ═══════════════════════════════════════════════════════════════

-- All 31 tables should now have entity_type (not text):
-- SELECT table_name, udt_name, is_nullable, column_default
-- FROM information_schema.columns
-- WHERE column_name = 'entity'
--   AND table_schema = 'public'
-- ORDER BY udt_name, table_name;
--
-- Expected:
--   52 rows total (21 pre-existing entity_type + 31 converted)
--   udt_name = 'entity_type' for ALL
--   NOT NULL on: campaign_batches, cost_budget, cost_ledger,
--     debbie_buyer_review_feedback, debbie_review_exports,
--     engagement_buyers, entity_value_propositions, letter_approvals,
--     letter_campaigns, meeting_learnings, meeting_notes,
--     pain_gain_analyses, proposals, research_executions,
--     why_sell_buyer_pitches, why_sell_narratives
--     (+ all 21 pre-existing entity_type NOT NULL tables)


-- ═══════════════════════════════════════════════════════════════
-- PRE-EXISTING DATA QUALITY ISSUES (outside Phase C scope)
-- ═══════════════════════════════════════════════════════════════

-- 1. Canyon State Enterprises LLC has entity='unknown' in companies table.
--    The companies table already uses entity_type enum, so 'unknown' IS in the
--    live enum despite not being in the architecture doc's 8-entity list.
--    Canyon State is a home_services company (vertical_id='home_services').
--    Recommended manual fix:
--
--    UPDATE companies
--      SET entity = 'next_chapter'
--      WHERE company_name = 'Canyon State Enterprises LLC.';
--
--    DELETE FROM agent_queue
--      WHERE id = '46ce0c37-e346-4c84-8d02-37460ac553a3';
--    -- (pending classifier task for Canyon State, no longer needed)

-- 2. Consider removing 'unknown' from entity_type enum after Canyon State
--    is reclassified. This prevents future unclassified data from being
--    silently accepted. However, this requires verifying no code path
--    writes 'unknown' as a default.
--
--    -- PostgreSQL does not support DROP VALUE from enum.
--    -- Would require: create new enum → migrate all columns → drop old enum.
--    -- Defer to Phase D if desired.

-- 3. page_versions table has NO entity column (confirmed via live query).
--    The unification plan listed it as potentially having one, but it doesn't.
--    If entity tracking is needed for page versions, a separate ALTER TABLE ADD
--    COLUMN would be required (not Phase C scope).
