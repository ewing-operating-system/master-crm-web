# Phase A Migration — Companion Notes

**Date:** 2026-04-03 | **Branch:** `refactor/cross-domain-inventory`
**SQL file:** `~/Desktop/supabase-phase-a-migration.sql`

---

## What Changed From the Original Unification Plan

### 1. `companies.vertical` rename → split into add/backfill/drop

**Plan said:** `ALTER TABLE companies RENAME COLUMN vertical TO vertical_id;`
**Live reality:** 19 views (and_companies, nc_companies, ru_companies, buyer_intelligence) expose `companies.vertical`. The entity-scoped company views use `SELECT ... vertical ...` directly. Renaming would break all views and every query referencing `companies.vertical`.
**Phase A does:** ADD `vertical_id` alongside `vertical`. Both columns coexist.
**Phase B:** Backfill `vertical_id` FROM `vertical` (`UPDATE companies SET vertical_id = vertical WHERE vertical IS NOT NULL`).
**Phase C:** After all code + views are migrated to use `vertical_id`, DROP `vertical`.

### 2. `dialer_queue.vertical` rename → same split

**Plan said:** `ALTER TABLE dialer_queue RENAME COLUMN vertical TO vertical_id;`
**Same problem:** Live queries reference `dialer_queue.vertical` (646 rows).
**Phase A does:** ADD `vertical_id` alongside.

### 3. `proposals.vertical` — already exists, plan assumed it didn't

**Plan said:** ADD `vertical_id TEXT` to proposals (listed under "entity unknown").
**Live reality:** `proposals` already has `entity TEXT NOT NULL` and `vertical TEXT nullable` (6 rows).
**Phase A does:** ADD `vertical_id` alongside existing `vertical`. Same dual-column pattern as companies and dialer_queue.
**Correction:** Plan's Change 3 listed proposals as "entity Unknown — HIGH risk". It actually has `entity TEXT NOT NULL` in live.

### 4. `meeting_notes.entity_id` rename → pure ADD (no entity column exists)

**Plan said:** `ALTER TABLE meeting_notes RENAME COLUMN entity_id TO entity;` (Change 2, row for meeting_notes)
**Live reality:** meeting_notes has only 5 columns: `id, captured_at, field_name, field_value, meeting_id`. There is NO `entity_id` column and NO `entity` column. The `meeting_id` field is a session identifier (TEXT), not an entity reference.
**Phase A does:** ADD `entity TEXT` as a new column. Table has 0 rows, so no backfill needed.

### 5. Entity TEXT→enum conversions deferred entirely

**Plan said (Change 2):** Convert 12+ tables from `entity TEXT` to `entity entity_type`.
**Why deferred:** 30 tables use TEXT for entity (10 NOT NULL, 20 nullable). Any value not in the 8-value enum would cause an INSERT failure. Must run `SELECT DISTINCT entity FROM <table>` on every table first. Some tables may contain empty strings, NULL, or freeform text that doesn't match the enum.
**Deferred to Phase C** after comprehensive data audit.

### 6. TAM default removal deferred

**Plan said (Change 6):** Change TAM tables from `DEFAULT 'next_chapter'` to plain `NOT NULL`.
**Live reality:** All 5 TAM tables use `public.entity_type NOT NULL` (the enum). They may still have a DEFAULT in the column definition — but removing it is a separate ALTER that doesn't affect Phase A work.
**Deferred to Phase C** — minor cleanup, no urgency.

### 7. `engagement_buyers.entity` — already exists

**Plan said (Change 3):** May need entity added.
**Live reality:** Already has `entity TEXT nullable` (224 rows). No change needed for Phase A.

### 8. `letter_approvals.entity` — already exists

**Plan said (Change 3):** Unknown if entity exists.
**Live reality:** Already has `entity TEXT NOT NULL` plus 20+ columns (0 rows). No change needed.

### 9. `page_versions.entity` — does NOT exist, but not critical

**Plan said (Change 2):** Has `entity TEXT` (if exists).
**Live reality:** page_versions has 26 rows, columns include company_name, page_type, version, html_content, etc. — but NO entity column.
**Not added in Phase A** — page_versions is a versioning/audit table. Entity can be inferred from company_name → companies.entity. Add if needed later.

---

## What's Deferred to Phase B (Backfill)

| Task | Details |
|------|---------|
| Backfill `companies.vertical_id` | `UPDATE companies SET vertical_id = vertical WHERE vertical IS NOT NULL AND vertical_id IS NULL;` (287 rows, straightforward) |
| Backfill `dialer_queue.vertical_id` | `UPDATE dialer_queue SET vertical_id = vertical WHERE vertical IS NOT NULL AND vertical_id IS NULL;` (646 rows) |
| Backfill `proposals.vertical_id` | `UPDATE proposals SET vertical_id = vertical WHERE vertical IS NOT NULL AND vertical_id IS NULL;` (6 rows) |
| Backfill `targets.vertical_id` | Join to companies via company_id: `UPDATE targets t SET vertical_id = c.vertical_id FROM companies c WHERE t.company_id = c.id AND t.vertical_id IS NULL AND c.vertical_id IS NOT NULL;` (201 rows) |
| Backfill `dossier_final.vertical_id` | Join to targets via target_id → companies: `UPDATE dossier_final d SET vertical_id = c.vertical_id FROM targets t JOIN companies c ON t.company_id = c.id WHERE d.target_id = t.id AND d.vertical_id IS NULL;` (27 rows) |
| Backfill `outreach_queue.vertical_id` | Join to targets via target_id → companies (82 rows) |
| Backfill `debbie_buyer_review_feedback.vertical_id` | All current feedback is hr_media: `UPDATE debbie_buyer_review_feedback SET vertical_id = 'hr_media' WHERE vertical_id IS NULL;` (8 rows) |
| Backfill `research_executions.vertical_id` | Needs script-level classification based on company_name → companies lookup (50 rows) |
| Backfill `campaign_batches.vertical_id` | 0 rows, no backfill needed |
| Backfill `letter_campaigns.vertical_id` | 0 rows, no backfill needed |

---

## What's Deferred to Phase C (Constraints + Cleanup)

| Task | Risk | Prerequisite |
|------|------|-------------|
| DROP `companies.vertical` column | **HIGH** — breaks views + queries | All code, views, and JS migrated to use `vertical_id` |
| DROP `dialer_queue.vertical` column | **MEDIUM** | All code migrated |
| DROP `proposals.vertical` column | **MEDIUM** — buyer_intelligence view uses `seller_vertical` from proposals.vertical | View must be updated first |
| Convert entity TEXT → entity_type enum (30 tables) | **HIGH** — any non-enum value causes failure | Run `SELECT DISTINCT entity` on all 30 tables; fix any bad values |
| Add NOT NULL constraint to `vertical_id` columns | **MEDIUM** | All rows backfilled, all write paths include vertical_id |
| Remove DEFAULT from TAM tables | **LOW** | No code depends on the default |
| Update entity-scoped views to expose `vertical_id` | **LOW** | Phase A column must exist |
| Create vertical-scoped views (e.g., `hr_media_targets`) | **LOW** | Optional, only if hub pages need them |

---

## Code Changes Required Before/After Running Phase A SQL

### Before running (no code changes required)

Phase A SQL is purely additive — it adds nullable columns and indexes. No existing code will break. Run it immediately.

### After running — code changes to start writing `vertical_id`

| File/Module | Change | Priority |
|-------------|--------|----------|
| `backend/lib/letter_engine.py` | When writing to proposals or related tables, include `vertical_id` from `load_vertical()` config | HIGH |
| `backend/worker.py` / agent handlers | When creating targets or dossier entries, propagate `vertical_id` from company | HIGH |
| `backend/orchestrator.py` | Entity classifier already runs — add vertical_id propagation when company has a known vertical | MEDIUM |
| `public/debbie-buyer-review.html` | `saveFeedback()` should include `vertical_id` in the Supabase insert payload | MEDIUM |
| `backend/regenerate.py` | When generating proposals, copy `vertical_id` from company/target | MEDIUM |
| `public/js/proposal-auto-generator.js` | `setVertical()` should write `vertical_id` to proposals record | LOW |
| All Supabase SELECT queries | Optionally add `vertical_id` to select lists for display — not urgent | LOW |

### After Phase B backfill — view migration (before Phase C drops)

| View | Change |
|------|--------|
| `and_companies`, `nc_companies`, `ru_companies` | Add `vertical_id` to SELECT, keep `vertical` until Phase C |
| `buyer_intelligence` | Change `seller_vertical` derivation from `proposals.vertical` to `proposals.vertical_id` |
| All new hub page queries | Use `vertical_id` for filtering |

---

## Tables NOT Touched by Phase A (and why)

| Table | Reason |
|-------|--------|
| `do_not_call` | Universal DNC — intentionally entity/vertical agnostic |
| `cost_budget`, `cost_log`, `cost_ledger` | Budget is per-entity, not per-vertical |
| `agent_queue`, `agent_runs` | Infrastructure queue — routes by agent_name |
| `pipeline_log` | Action audit trail — entity granularity is sufficient |
| All TAM tables | NC-only today; vertical concept doesn't apply until TAM expands |
| Entity-specific tables (nc_owner_profiles, and_investor_profiles, etc.) | Vertical implied by entity context |
| Stress test / benchmark tables | Infrastructure |
| `page_versions`, `page_comments`, `notifications` | Audit/UI tables — entity inherited via company_name |
| `research_methods`, `skills_registry` | Cross-entity knowledge bases |

---

## Validation Checklist (Run After Executing SQL)

```sql
-- 1. Verify vertical_id columns exist
SELECT table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE column_name = 'vertical_id'
ORDER BY table_name;
-- Expected: 11 rows (companies, dialer_queue, proposals, targets,
--   dossier_final, outreach_queue, debbie_buyer_review_feedback,
--   research_executions, campaign_batches, letter_campaigns + any extras)

-- 2. Verify meeting_notes.entity column exists
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'meeting_notes' AND column_name = 'entity';
-- Expected: 1 row, TEXT, nullable

-- 3. Verify indexes were created
SELECT indexname FROM pg_indexes
WHERE indexname LIKE 'idx_%vertical%'
ORDER BY indexname;
-- Expected: 12 indexes (8 single-column + 4 composite)

-- 4. Verify no data was modified (row counts unchanged)
-- Spot-check a few high-value tables:
SELECT count(*) FROM companies;    -- Expected: 287
SELECT count(*) FROM targets;      -- Expected: 201
SELECT count(*) FROM proposals;    -- Expected: 6

-- 5. Verify old `vertical` column still works (dual-column coexistence)
SELECT id, vertical, vertical_id FROM companies LIMIT 3;
-- Expected: vertical has data, vertical_id is NULL (until Phase B backfill)
```

---

## Execution Log — 2026-04-03 02:52 UTC

### Safety Checks (all passed)

| Check | Result |
|-------|--------|
| Every statement is ADD COLUMN or CREATE INDEX (no DROP/RENAME/ALTER TYPE) | PASS |
| Tables with existing `vertical` column get `vertical_id` (no name collision) | PASS |
| No NOT NULL constraints without defaults on existing tables | PASS |
| Index names don't collide with existing indexes | PASS |

### ADD COLUMN Results (11/11 passed)

| # | Statement | Result | Verified |
|---|-----------|--------|----------|
| 1 | `companies ADD vertical_id TEXT` | PASS | `('vertical_id', 'text', 'YES')` |
| 2 | `dialer_queue ADD vertical_id TEXT` | PASS | `('vertical_id', 'text', 'YES')` |
| 3 | `proposals ADD vertical_id TEXT` | PASS | `('vertical_id', 'text', 'YES')` |
| 4 | `targets ADD vertical_id TEXT` | PASS | `('vertical_id', 'text', 'YES')` |
| 5 | `dossier_final ADD vertical_id TEXT` | PASS | `('vertical_id', 'text', 'YES')` |
| 6 | `outreach_queue ADD vertical_id TEXT` | PASS | `('vertical_id', 'text', 'YES')` |
| 7 | `debbie_buyer_review_feedback ADD vertical_id TEXT` | PASS | `('vertical_id', 'text', 'YES')` |
| 8 | `research_executions ADD vertical_id TEXT` | PASS | `('vertical_id', 'text', 'YES')` |
| 9 | `campaign_batches ADD vertical_id TEXT` | PASS | `('vertical_id', 'text', 'YES')` |
| 10 | `letter_campaigns ADD vertical_id TEXT` | PASS | `('vertical_id', 'text', 'YES')` |
| 11 | `meeting_notes ADD entity TEXT` | PASS | `('entity', 'text', 'YES')` |

### CREATE INDEX Results (13/13 passed)

| # | Index Name | Table | Result |
|---|-----------|-------|--------|
| 1 | `idx_companies_vertical_id` | companies | PASS |
| 2 | `idx_targets_vertical_id` | targets | PASS |
| 3 | `idx_proposals_vertical_id` | proposals | PASS |
| 4 | `idx_dossier_final_vertical_id` | dossier_final | PASS |
| 5 | `idx_dialer_queue_vertical_id` | dialer_queue | PASS |
| 6 | `idx_outreach_queue_vertical_id` | outreach_queue | PASS |
| 7 | `idx_research_executions_vertical_id` | research_executions | PASS |
| 8 | `idx_debbie_feedback_vertical_id` | debbie_buyer_review_feedback | PASS |
| 9 | `idx_targets_entity_vertical` | targets | PASS |
| 10 | `idx_proposals_entity_vertical` | proposals | PASS |
| 11 | `idx_companies_entity_vertical` | companies | PASS |
| 12 | `idx_dossier_final_entity_vertical` | dossier_final | PASS |
| 13 | `idx_debbie_feedback_buyer_section` | debbie_buyer_review_feedback | PASS |

### Final Verification

**vertical_id columns confirmed on 10 tables:** campaign_batches, companies, debbie_buyer_review_feedback, dialer_queue, dossier_final, letter_campaigns, outreach_queue, proposals, research_executions, targets

**meeting_notes.entity confirmed:** `('entity', 'text', 'YES')`

**Row counts unchanged:**
- companies: 287 (expected 287)
- targets: 201 (expected 201)
- proposals: 6 (expected 6)
- dialer_queue: 646 (expected 646)
- dossier_final: 27 (expected 27)
- meeting_notes: 0 (expected 0)

**Dual-column coexistence verified:**
```
companies sample: vertical='Electrical', vertical_id=None
companies sample: vertical='HVAC',       vertical_id=None
```
Old `vertical` column untouched. New `vertical_id` is NULL — ready for Phase B backfill.

### Summary

**24/24 statements executed successfully. Zero failures. No data modified. Live database is now Phase A complete.**
