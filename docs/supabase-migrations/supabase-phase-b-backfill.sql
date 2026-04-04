-- =============================================================================
-- PHASE B: Backfill vertical_id Columns
-- =============================================================================
-- Date:     2026-04-03
-- Branch:   refactor/cross-domain-inventory
-- Prereq:   Phase A columns must exist (executed 2026-04-03 02:52 UTC)
-- Rule:     Each UPDATE is wrapped in BEGIN/COMMIT with a row count check.
--           Run one block at a time. Verify before proceeding to the next.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- VALUE MAPPING: existing vertical text → vertical_id
-- ---------------------------------------------------------------------------
-- All trades/services map to 'home_services':
--   HVAC, Pest Control, pest control, Electrical, Plumbing, plumbing,
--   precast concrete, Precast Concrete Manufacturing,
--   Precast Concrete & Pipe Manufacturing, Floor Care / Carpet Cleaning,
--   Water Treatment, Water Treatment / eCommerce,
--   environmental services, foundation repair, home services, construction
--
-- HR/Tech maps to 'hr_media':
--   HR Technology / B2B Digital Media
--
-- NULL (90 companies incl all 27 and_capital) → left as NULL
-- ---------------------------------------------------------------------------

-- =========================================================================
-- 1. COMPANIES (287 rows, 197 with non-NULL vertical)
-- =========================================================================
-- Maps the existing free-text vertical to a controlled vertical_id.
-- All and_capital (27 rows) have NULL vertical → stay NULL.
-- 90 NULLs total: 27 and_capital + 63 next_chapter with no vertical data.

BEGIN;

UPDATE companies
SET vertical_id = CASE
    WHEN lower(vertical) IN (
        'hvac', 'pest control', 'electrical', 'plumbing',
        'precast concrete', 'precast concrete manufacturing',
        'precast concrete & pipe manufacturing',
        'floor care / carpet cleaning',
        'water treatment', 'water treatment / ecommerce',
        'environmental services', 'foundation repair',
        'home services', 'construction'
    ) THEN 'home_services'
    WHEN lower(vertical) IN (
        'hr technology / b2b digital media'
    ) THEN 'hr_media'
    ELSE NULL  -- unmappable or NULL source
END
WHERE vertical IS NOT NULL
  AND vertical_id IS NULL;

-- VERIFY: expect 197 rows updated (287 total - 90 NULL vertical)
-- SELECT count(*) FROM companies WHERE vertical_id IS NOT NULL;
-- Expected: 197
-- SELECT vertical_id, count(*) FROM companies WHERE vertical_id IS NOT NULL GROUP BY vertical_id;
-- Expected: home_services=197 (no hr_media companies — HR.com has NULL vertical)

COMMIT;

-- =========================================================================
-- 2. DIALER_QUEUE (646 rows, all have non-NULL vertical)
-- =========================================================================
-- All values are home_services trades: HVAC, Pest Control, Electrical,
-- Plumbing, Water Treatment / eCommerce, Floor Care / Carpet Cleaning.

BEGIN;

UPDATE dialer_queue
SET vertical_id = 'home_services'
WHERE vertical IS NOT NULL
  AND vertical_id IS NULL;

-- VERIFY: expect 646 rows updated
-- SELECT count(*) FROM dialer_queue WHERE vertical_id IS NOT NULL;
-- Expected: 646
-- SELECT vertical_id, count(*) FROM dialer_queue GROUP BY vertical_id;
-- Expected: home_services=646

COMMIT;

-- =========================================================================
-- 3. PROPOSALS (6 rows, all have non-NULL vertical)
-- =========================================================================
-- 5 are home_services trades, 1 is hr_media.

BEGIN;

UPDATE proposals
SET vertical_id = CASE
    WHEN lower(vertical) IN (
        'hvac', 'precast concrete manufacturing',
        'precast concrete & pipe manufacturing',
        'floor care / carpet cleaning',
        'water treatment / ecommerce'
    ) THEN 'home_services'
    WHEN lower(vertical) IN (
        'hr technology / b2b digital media'
    ) THEN 'hr_media'
    ELSE NULL
END
WHERE vertical IS NOT NULL
  AND vertical_id IS NULL;

-- VERIFY: expect 6 rows updated
-- SELECT company_name, vertical, vertical_id FROM proposals ORDER BY company_name;
-- Expected:
--   Air Control        | HVAC                              | home_services
--   AquaScience        | Water Treatment / eCommerce       | home_services
--   Design Precast...  | Precast Concrete & Pipe Mfg       | home_services
--   HR.com Ltd         | HR Technology / B2B Digital Media  | hr_media
--   Springer Floor     | Floor Care / Carpet Cleaning      | home_services
--   Wieser Concrete... | Precast Concrete Manufacturing    | home_services

COMMIT;

-- =========================================================================
-- 4. TARGETS (201 rows, all have company_id → companies)
-- =========================================================================
-- JOIN path: targets.company_id → companies.vertical_id
-- All 201 targets have non-NULL company_id.

BEGIN;

UPDATE targets t
SET vertical_id = c.vertical_id
FROM companies c
WHERE t.company_id = c.id
  AND t.vertical_id IS NULL
  AND c.vertical_id IS NOT NULL;

-- VERIFY: rows updated depends on how many companies had vertical_id set
-- SELECT count(*) FROM targets WHERE vertical_id IS NOT NULL;
-- SELECT vertical_id, count(*) FROM targets WHERE vertical_id IS NOT NULL GROUP BY vertical_id;
-- Some targets may remain NULL if their company has no vertical (and_capital, untagged NC)

COMMIT;

-- =========================================================================
-- 5. DOSSIER_FINAL (27 rows: 20 with target_id, 7 without)
-- =========================================================================
-- Two-step: first via target_id → targets.vertical_id, then company_name fallback.

-- Step 5a: via target_id (20 rows)
BEGIN;

UPDATE dossier_final df
SET vertical_id = t.vertical_id
FROM targets t
WHERE df.target_id = t.id
  AND df.vertical_id IS NULL
  AND t.vertical_id IS NOT NULL;

-- VERIFY: expect up to 20 rows updated
-- SELECT count(*) FROM dossier_final WHERE vertical_id IS NOT NULL AND target_id IS NOT NULL;

COMMIT;

-- Step 5b: 7 orphan rows — join on company_name (fuzzy)
-- Known mapping from live data inspection:
--   HR.com Ltd           → hr_media
--   Air Control LLC      → home_services (companies has 'Air Control LLC' with vertical='HVAC')
--   Design Precast...    → home_services
--   Wieser Concrete...   → home_services
--   AquaScience (x2)     → home_services
--   Springer Floor Care LLC → home_services
BEGIN;

UPDATE dossier_final
SET vertical_id = CASE
    WHEN company_name ILIKE '%hr.com%' THEN 'hr_media'
    ELSE 'home_services'
END
WHERE target_id IS NULL
  AND vertical_id IS NULL;

-- VERIFY: expect 7 rows updated
-- SELECT company_name, vertical_id FROM dossier_final WHERE target_id IS NULL;

COMMIT;

-- =========================================================================
-- 6. OUTREACH_QUEUE (82 rows, all have target_id → targets)
-- =========================================================================

BEGIN;

UPDATE outreach_queue oq
SET vertical_id = t.vertical_id
FROM targets t
WHERE oq.target_id = t.id
  AND oq.vertical_id IS NULL
  AND t.vertical_id IS NOT NULL;

-- VERIFY: rows updated depends on targets.vertical_id population
-- SELECT count(*) FROM outreach_queue WHERE vertical_id IS NOT NULL;

COMMIT;

-- =========================================================================
-- 7. RESEARCH_EXECUTIONS (50 rows, ALL have NULL company_id)
-- =========================================================================
-- No FK to companies. company_name exists but doesn't match exactly:
--   'Springer Floor' vs 'Springer Floor Care LLC'
--   'Air Control' vs 'Air Control LLC'
--   'HR.com Ltd' has NULL vertical in companies
--
-- Hard-coded mapping based on the 6 known companies:

BEGIN;

UPDATE research_executions
SET vertical_id = CASE
    WHEN company_name ILIKE '%hr.com%' THEN 'hr_media'
    ELSE 'home_services'
END
WHERE vertical_id IS NULL;

-- VERIFY: expect 50 rows updated
-- SELECT company_name, vertical_id, count(*) FROM research_executions
-- GROUP BY company_name, vertical_id ORDER BY company_name;
-- Expected: HR.com Ltd=hr_media (9), all others=home_services (41)

COMMIT;

-- =========================================================================
-- 8. DEBBIE_BUYER_REVIEW_FEEDBACK (8 rows)
-- =========================================================================
-- All current feedback is for hr_media buyers (paychex, sap-successfactors).
-- These are HR/payroll companies being reviewed as potential acquirers of HR.com.

BEGIN;

UPDATE debbie_buyer_review_feedback
SET vertical_id = 'hr_media'
WHERE vertical_id IS NULL;

-- VERIFY: expect 8 rows updated
-- SELECT buyer_slug, vertical_id FROM debbie_buyer_review_feedback;
-- Expected: all 8 rows = hr_media

COMMIT;

-- =========================================================================
-- 9. CAMPAIGN_BATCHES (0 rows) — no-op
-- =========================================================================
-- Table is empty. No backfill needed.
-- Future inserts should include vertical_id from the campaign's context.

-- =========================================================================
-- 10. LETTER_CAMPAIGNS (0 rows) — no-op
-- =========================================================================
-- Table is empty. No backfill needed.

-- =========================================================================
-- 11. MEETING_NOTES.ENTITY (0 rows) — no-op
-- =========================================================================
-- Table is empty. No backfill needed.
-- Future inserts should derive entity from the meeting/company context.

-- =============================================================================
-- FINAL VERIFICATION
-- =============================================================================
-- Run after all backfills complete:

-- SELECT 'companies' AS tbl, count(*) FILTER (WHERE vertical_id IS NOT NULL) AS filled, count(*) AS total FROM companies
-- UNION ALL SELECT 'dialer_queue', count(*) FILTER (WHERE vertical_id IS NOT NULL), count(*) FROM dialer_queue
-- UNION ALL SELECT 'proposals', count(*) FILTER (WHERE vertical_id IS NOT NULL), count(*) FROM proposals
-- UNION ALL SELECT 'targets', count(*) FILTER (WHERE vertical_id IS NOT NULL), count(*) FROM targets
-- UNION ALL SELECT 'dossier_final', count(*) FILTER (WHERE vertical_id IS NOT NULL), count(*) FROM dossier_final
-- UNION ALL SELECT 'outreach_queue', count(*) FILTER (WHERE vertical_id IS NOT NULL), count(*) FROM outreach_queue
-- UNION ALL SELECT 'research_executions', count(*) FILTER (WHERE vertical_id IS NOT NULL), count(*) FROM research_executions
-- UNION ALL SELECT 'debbie_feedback', count(*) FILTER (WHERE vertical_id IS NOT NULL), count(*) FROM debbie_buyer_review_feedback
-- UNION ALL SELECT 'campaign_batches', count(*) FILTER (WHERE vertical_id IS NOT NULL), count(*) FROM campaign_batches
-- UNION ALL SELECT 'letter_campaigns', count(*) FILTER (WHERE vertical_id IS NOT NULL), count(*) FROM letter_campaigns
-- ORDER BY tbl;

-- =============================================================================
-- END PHASE B
-- =============================================================================
