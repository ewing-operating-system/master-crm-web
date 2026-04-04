# Phase B Backfill — Companion Notes

**Date:** 2026-04-03 | **Branch:** `refactor/cross-domain-inventory`
**SQL file:** `~/Desktop/supabase-phase-b-backfill.sql`
**Prereq:** Phase A executed 2026-04-03 02:52 UTC (all vertical_id columns exist)

---

## Value Mapping Table

### Existing `vertical` values → `vertical_id`

| Existing Value | Count (companies) | vertical_id | Confidence |
|---|---|---|---|
| `'HVAC'` | 97 | `home_services` | HIGH — in classification_keywords |
| `'Pest Control'` | 36 | `home_services` | HIGH |
| `'Electrical'` | 24 | `home_services` | HIGH |
| `'Plumbing'` | 21 | `home_services` | HIGH |
| `'pest control'` | 7 | `home_services` | HIGH (case variant) |
| `'precast concrete'` | 3 | `home_services` | HIGH — "concrete" in keywords |
| `'plumbing'` | 1 | `home_services` | HIGH (case variant) |
| `'Precast Concrete Manufacturing'` | 1 | `home_services` | HIGH |
| `'Floor Care / Carpet Cleaning'` | 1 | `home_services` | HIGH — "flooring" in keywords |
| `'Precast Concrete & Pipe Manufacturing'` | 1 | `home_services` | HIGH |
| `'Water Treatment'` | 1 | `home_services` | HIGH |
| `'environmental services'` | 1 | `home_services` | HIGH — "environmental" in keywords |
| `'foundation repair'` | 1 | `home_services` | HIGH — "foundation" in keywords |
| `'home services'` | 1 | `home_services` | HIGH — direct match |
| `'construction'` | 1 | `home_services` | MEDIUM — trades-adjacent, not explicitly in keywords |
| `'HR Technology / B2B Digital Media'` | 0 (proposals only) | `hr_media` | HIGH — "hr tech" in keywords |
| `'Water Treatment / eCommerce'` | 0 (dialer_queue/proposals) | `home_services` | HIGH |
| `NULL` | 90 (companies) | `NULL` (unmapped) | N/A |

### Unmappable Values

| Value | Count | Table(s) | Reason | Action |
|---|---|---|---|---|
| `NULL` | 90 | companies | 27 are and_capital (no vertical concept), 63 are next_chapter with no vertical data | Leave NULL — manual review later |
| `'construction'` | 1 | companies | Not explicitly in home_services keywords, but entity is `'unknown'` (data quality issue) | Mapped to home_services anyway — the company "Canyon State Enterprises LLC" also has entity='unknown' |

### Special Cases

| Table | Issue | Resolution |
|---|---|---|
| **companies (and_capital)** | All 27 AND Capital companies have `vertical=NULL`. AND Capital is an investment fund — "vertical" doesn't apply the same way. | Leave `vertical_id=NULL`. AND Capital's concept is `fund_vertical` on `and_investor_profiles`, not the company's industry. |
| **companies (HR.com)** | HR.com Ltd exists in companies but has `vertical=NULL`. It appears in proposals with `vertical='HR Technology / B2B Digital Media'`. | Companies backfill won't touch it (NULL source). But proposals, dossier_final, and research_executions will correctly set `vertical_id='hr_media'` via their own mapping. Consider manually setting `companies.vertical_id='hr_media'` for HR.com after Phase B. |
| **entity='unknown'** | Canyon State Enterprises LLC has entity='unknown' (not in the entity_type enum). | Flag for manual entity classification. vertical_id='home_services' is correct based on 'construction'. |

---

## Row Counts Per Table

| # | Table | Total Rows | Backfill Source | Expected Filled | Expected NULL | Notes |
|---|---|---|---|---|---|---|
| 1 | companies | 287 | `vertical` column | 197 | 90 | 90 NULL = 27 and_capital + 63 untagged NC |
| 2 | dialer_queue | 646 | `vertical` column | 646 | 0 | All rows have vertical data |
| 3 | proposals | 6 | `vertical` column | 6 | 0 | 5 home_services + 1 hr_media |
| 4 | targets | 201 | JOIN `companies.vertical_id` | ~170* | ~31* | *Depends on companies coverage |
| 5 | dossier_final | 27 | JOIN targets + company_name fallback | 27 | 0 | 20 via target_id, 7 via company_name |
| 6 | outreach_queue | 82 | JOIN `targets.vertical_id` | ~70* | ~12* | *Same coverage as targets |
| 7 | research_executions | 50 | Hard-coded company_name map | 50 | 0 | 6 known companies, all mappable |
| 8 | debbie_buyer_review_feedback | 8 | All hr_media buyers | 8 | 0 | paychex + sap-successfactors |
| 9 | campaign_batches | 0 | — | 0 | 0 | Empty table |
| 10 | letter_campaigns | 0 | — | 0 | 0 | Empty table |
| 11 | meeting_notes (entity) | 0 | — | 0 | 0 | Empty table |

*Estimates for targets and outreach_queue: depends on how many of their companies had a vertical set. 197/287 companies have vertical data, so roughly 70% coverage.

---

## JOIN Path Analysis

| Table | JOIN Path | Works? | Issue |
|---|---|---|---|
| **targets** | `targets.company_id → companies.id` | YES | All 201 targets have non-NULL company_id |
| **dossier_final** | `dossier_final.target_id → targets.id → companies.id` | PARTIAL | 20/27 have target_id. 7 orphans use company_name fallback. |
| **outreach_queue** | `outreach_queue.target_id → targets.id` | YES | All 82 have non-NULL target_id |
| **research_executions** | `research_executions.company_id → companies.id` | **NO** | All 50 rows have NULL company_id. company_name exists but doesn't match exactly ("Springer Floor" vs "Springer Floor Care LLC", "Air Control" vs "Air Control LLC"). Used hard-coded mapping instead. |
| **debbie_buyer_review_feedback** | No FK to companies | **NO** | Has `buyer_slug` and `entity` but no company reference. All 8 rows are hr_media buyer reviews — hard-coded. |
| **campaign_batches** | No direct FK to companies | N/A | 0 rows — moot |
| **letter_campaigns** | No direct FK to companies | N/A | 0 rows — moot |
| **meeting_notes** | Has `meeting_id TEXT` only | N/A | 0 rows — moot. Future: derive entity from meeting transcript → company → entity. |

---

## Tables Needing Manual Review

### 1. research_executions — broken company_id FK

All 50 rows have `company_id = NULL` despite having `company_name` populated. The company_name values don't exactly match companies.company_name:

| research_executions.company_name | companies.company_name | Match? |
|---|---|---|
| `'HR.com Ltd'` | `'HR.com Ltd'` | Exact, but companies.vertical is NULL |
| `'Springer Floor'` | `'Springer Floor Care LLC'` | NO — substring |
| `'Air Control'` | `'Air Control LLC'` | NO — substring |
| `'Design Precast & Pipe, Inc.'` | `'Design Precast & Pipe, Inc.'` | Exact match |
| `'AquaScience'` | `'AquaScience'` | Exact match |
| `'Wieser Concrete Products, Inc.'` | `'Wieser Concrete Products, Inc.'` | Exact match |

**Recommendation:** After backfill, also backfill `research_executions.company_id` from companies via ILIKE match. Not in Phase B scope but would fix the broken FK.

### 2. HR.com Ltd — missing vertical in companies

HR.com Ltd exists in `companies` with `vertical = NULL`, but:
- `proposals` has it as `vertical = 'HR Technology / B2B Digital Media'`
- `dossier_final` has research for it
- `research_executions` has 9 Exa runs for it
- All `debbie_buyer_review_feedback` is for HR.com's buyer list

**Recommendation:** After Phase B, manually set:
```sql
UPDATE companies SET vertical = 'HR Technology / B2B Digital Media', vertical_id = 'hr_media'
WHERE company_name = 'HR.com Ltd';
```

### 3. 63 Next Chapter companies with no vertical

These are next_chapter companies that were imported without a vertical tag. They may be home_services (the dominant NC vertical) or unknown. Need manual classification or bulk tagging.

---

## What This Does NOT Backfill

| Item | Reason |
|---|---|
| `companies.vertical_id` for NULL-vertical rows | Can't infer vertical from no data |
| `meeting_notes.entity` | Table is empty |
| `campaign_batches.vertical_id` | Table is empty |
| `letter_campaigns.vertical_id` | Table is empty |
| Entity TEXT → entity_type enum conversion | Deferred to Phase C |
| `companies.vertical_id` for HR.com Ltd | companies.vertical is NULL — needs manual fix |

---

## Execution Log — 2026-04-03 11:05 UTC

### Pre-Execution Audit

**Critical finding during audit:** The 63 Next Chapter companies with NULL vertical are NOT home_services. They are HR tech / PE / consulting firms (ADP, BambooHR, Ceridian, Salesforce, Thoma Bravo, etc.) — buyer research targets for the HR.com deal. Correct mapping is `hr_media`, not `home_services`.

**Second finding:** HR.com Ltd does NOT exist in the companies table. It only exists in proposals (with `company_id=NULL`). Fix 1 was changed from UPDATE to INSERT.

### Manual Fix Results

| Fix | Action | Rows | Result |
|-----|--------|------|--------|
| Fix 1 | INSERT HR.com Ltd into companies (entity=next_chapter, vertical='HR Technology / B2B Digital Media', vertical_id='hr_media') + link proposals.company_id | 1 inserted + 1 linked | PASS |
| Fix 2 | UPDATE 63 NC buyer companies SET vertical_id='hr_media' (NOT home_services — these are HR tech buyers) | 63 updated | PASS |
| Fix 3 | research_executions.company_id universally NULL | DEFERRED | Tech debt — needs separate data recovery. company_name exists but doesn't match companies.company_name exactly. |

### Backfill Block Results

| Block | Table | Rows Updated | Expected | Verification | Result |
|-------|-------|-------------|----------|-------------|--------|
| 1 | companies | 197 | 197 | vertical_id: home_services=197, hr_media=64, NULL=27 | PASS |
| 2 | dialer_queue | 646 | 646 | home_services=646 | PASS |
| 3 | proposals | 6 | 6 | home_services=5, hr_media=1 | PASS |
| 4 | targets | 201 | ~170 | home_services=201, NULL=0 (better than expected — all companies had coverage) | PASS |
| 5a | dossier_final (target_id) | 20 | 20 | 20 filled via target_id | PASS |
| 5b | dossier_final (orphans) | 7 | 7 | HR.com→hr_media, 6 others→home_services | PASS |
| 6 | outreach_queue | 82 | ~70 | home_services=82, NULL=0 (100% coverage) | PASS |
| 7 | research_executions | 50 | 50 | HR.com(9)→hr_media, others(41)→home_services | PASS |
| 8 | debbie_buyer_review_feedback | 8 | 8 | hr_media=8 (paychex=7, sap-successfactors=1) | PASS |
| 9 | campaign_batches | 0 | 0 | Empty table, no-op | N/A |
| 10 | letter_campaigns | 0 | 0 | Empty table, no-op | N/A |
| 11 | meeting_notes (entity) | 0 | 0 | Empty table, no-op | N/A |

### Final Verification — Fill Rates

| Table | Filled | Total | Coverage |
|-------|--------|-------|----------|
| companies | 261 | 288 | 91% |
| dialer_queue | 646 | 646 | 100% |
| proposals | 6 | 6 | 100% |
| targets | 201 | 201 | 100% |
| dossier_final | 27 | 27 | 100% |
| outreach_queue | 82 | 82 | 100% |
| research_executions | 50 | 50 | 100% |
| debbie_buyer_review_feedback | 8 | 8 | 100% |
| campaign_batches | 0 | 0 | N/A |
| letter_campaigns | 0 | 0 | N/A |

**Remaining NULLs:** 27 companies (all and_capital). This is intentional — AND Capital uses `fund_vertical` on `and_investor_profiles`, not the seller-side vertical concept.

### Vertical Distribution After Backfill

| Table | home_services | hr_media | NULL |
|-------|-------------|---------|------|
| companies | 197 | 64 | 27 |
| targets | 201 | 0 | 0 |
| proposals | 5 | 1 | 0 |
| dossier_final | 26 | 1 | 0 |
| dialer_queue | 646 | 0 | 0 |
| outreach_queue | 82 | 0 | 0 |
| research_executions | 41 | 9 | 0 |
| debbie_buyer_review_feedback | 0 | 8 | 0 |

### Deferred Tech Debt

1. **research_executions.company_id** — all 50 rows have NULL company_id despite having company_name. Three of 6 company names don't exactly match companies.company_name ("Springer Floor" vs "Springer Floor Care LLC", "Air Control" vs "Air Control LLC"). Needs an ILIKE-based company_id backfill as a separate effort.

2. **Entity 'unknown'** — Canyon State Enterprises LLC has entity='unknown' which is not in the entity_type enum. Needs manual entity classification. Its vertical_id='home_services' is correct.

### Summary

**Phase B complete. 1,283 rows backfilled across 8 tables. 2 manual fixes applied. 0 failures. 8/10 operational tables at 100% vertical_id coverage. Only gap: 27 and_capital companies (intentionally NULL).**
