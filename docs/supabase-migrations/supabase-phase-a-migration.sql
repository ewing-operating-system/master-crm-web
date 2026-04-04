-- =============================================================================
-- PHASE A: Non-Breaking Migration — Multi-Vertical Column Additions
-- =============================================================================
-- Date:     2026-04-03
-- Branch:   refactor/cross-domain-inventory
-- Status:   READY FOR REVIEW — do NOT execute without reading companion notes
-- Rule:     Every statement is ADD COLUMN or CREATE INDEX. No DROP, no RENAME,
--           no ALTER TYPE. Running code continues unaffected.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Add vertical_id to tables that ALREADY have a free-text `vertical` column
--    (companies, dialer_queue, proposals)
--    These get a NEW column alongside the old one. Phase B backfills,
--    Phase C drops the old column after all code is migrated.
-- ---------------------------------------------------------------------------

-- companies: currently has `vertical TEXT nullable` (287 rows)
ALTER TABLE companies ADD COLUMN IF NOT EXISTS vertical_id TEXT;
COMMENT ON COLUMN companies.vertical_id IS 'Controlled vertical identifier (e.g. home_services, hr_media). Phase A: coexists with legacy vertical column. Phase C: drop vertical after code migration.';

-- dialer_queue: currently has `vertical TEXT nullable` (646 rows)
ALTER TABLE dialer_queue ADD COLUMN IF NOT EXISTS vertical_id TEXT;
COMMENT ON COLUMN dialer_queue.vertical_id IS 'Controlled vertical identifier. Phase A: coexists with legacy vertical column.';

-- proposals: currently has `vertical TEXT nullable` (6 rows)
ALTER TABLE proposals ADD COLUMN IF NOT EXISTS vertical_id TEXT;
COMMENT ON COLUMN proposals.vertical_id IS 'Controlled vertical identifier. Phase A: coexists with legacy vertical column.';

-- ---------------------------------------------------------------------------
-- 2. Add vertical_id to tables that need it but DON'T have any vertical column
-- ---------------------------------------------------------------------------

-- targets: core pipeline table (201 rows). Vertical filtering needed for
-- "show me all hr_media targets" queries.
ALTER TABLE targets ADD COLUMN IF NOT EXISTS vertical_id TEXT;

-- dossier_final: research content is vertical-specific (27 rows)
ALTER TABLE dossier_final ADD COLUMN IF NOT EXISTS vertical_id TEXT;

-- outreach_queue: letter variant selection depends on vertical (82 rows)
ALTER TABLE outreach_queue ADD COLUMN IF NOT EXISTS vertical_id TEXT;

-- debbie_buyer_review_feedback: feedback is per-vertical research (8 rows)
ALTER TABLE debbie_buyer_review_feedback ADD COLUMN IF NOT EXISTS vertical_id TEXT;

-- research_executions: Exa templates come from vertical config (50 rows)
ALTER TABLE research_executions ADD COLUMN IF NOT EXISTS vertical_id TEXT;

-- campaign_batches: letters use vertical config for valuation narrative (0 rows)
ALTER TABLE campaign_batches ADD COLUMN IF NOT EXISTS vertical_id TEXT;

-- letter_campaigns: same rationale as campaign_batches (0 rows)
ALTER TABLE letter_campaigns ADD COLUMN IF NOT EXISTS vertical_id TEXT;

-- ---------------------------------------------------------------------------
-- 3. Add entity column to meeting_notes
--    Live schema shows: id, captured_at, field_name, field_value, meeting_id
--    NO entity column exists (not even entity_id — the unification plan was
--    wrong about this). This is a pure ADD, not a rename. Table has 0 rows.
-- ---------------------------------------------------------------------------

ALTER TABLE meeting_notes ADD COLUMN IF NOT EXISTS entity TEXT;
COMMENT ON COLUMN meeting_notes.entity IS 'Entity tag. Added Phase A. Currently TEXT; Phase C will convert to entity_type enum after data audit.';

-- ---------------------------------------------------------------------------
-- 4. Indexes for vertical_id columns (new vertical-filtering queries)
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_companies_vertical_id ON companies(vertical_id);
CREATE INDEX IF NOT EXISTS idx_targets_vertical_id ON targets(vertical_id);
CREATE INDEX IF NOT EXISTS idx_proposals_vertical_id ON proposals(vertical_id);
CREATE INDEX IF NOT EXISTS idx_dossier_final_vertical_id ON dossier_final(vertical_id);
CREATE INDEX IF NOT EXISTS idx_dialer_queue_vertical_id ON dialer_queue(vertical_id);
CREATE INDEX IF NOT EXISTS idx_outreach_queue_vertical_id ON outreach_queue(vertical_id);
CREATE INDEX IF NOT EXISTS idx_research_executions_vertical_id ON research_executions(vertical_id);
CREATE INDEX IF NOT EXISTS idx_debbie_feedback_vertical_id ON debbie_buyer_review_feedback(vertical_id);

-- ---------------------------------------------------------------------------
-- 5. Composite indexes for common query patterns
--    entity + vertical_id together cover "show me NC's home_services targets"
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_targets_entity_vertical ON targets(entity, vertical_id);
CREATE INDEX IF NOT EXISTS idx_proposals_entity_vertical ON proposals(entity, vertical_id);
CREATE INDEX IF NOT EXISTS idx_companies_entity_vertical ON companies(entity, vertical_id);
CREATE INDEX IF NOT EXISTS idx_dossier_final_entity_vertical ON dossier_final(entity, vertical_id);

-- ---------------------------------------------------------------------------
-- 6. Debbie review feedback — section-level lookup index
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_debbie_feedback_buyer_section
  ON debbie_buyer_review_feedback(buyer_slug, section_key);

-- =============================================================================
-- END PHASE A
-- =============================================================================
-- Next steps:
--   Phase B: Backfill vertical_id from legacy vertical column + company lookups
--   Phase C: Tighten constraints (NOT NULL), drop old vertical columns,
--            convert TEXT entity → entity_type enum on migration-era tables
-- =============================================================================
