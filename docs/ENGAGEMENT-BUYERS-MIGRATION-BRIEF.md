# engagement_buyers Table Migration Brief

**Date:** 2026-04-01
**Status:** PLANNING — No changes made yet
**Author:** Mark (mark@chapter.guide) continuing Ewing's (ewing@engram.nexus) work
**Risk Level:** HIGH — 32 downstream files, live production system

---

## The Problem

`engagement_buyers` is a 58-column table doing triple duty:
1. **Company profile** (who is this buyer company)
2. **Engagement record** (how does this buyer relate to a specific deal)
3. **Contact info** (who is the person at the buyer company)

This means company data (HQ location, revenue, acquisition history, investment thesis) is duplicated across every proposal a buyer appears in. Currently 224 rows across 6 proposals. If a buyer appears in 3 deals, their company info is stored 3 times with no guarantee of consistency.

## Current Schema Reality

### engagement_buyers (58 columns, 224 rows)

**Company-scoped fields (should be on a company record):**
- buyer_company_name, buyer_type, buyer_city, buyer_state
- buyer_revenue, buyer_employee_count, buyer_description
- buyer_acquisition_history, buyer_investment_thesis
- competitive_advantage, pain_mapping, vision_mapping, convergence_points
- story_narrative, confidence
- research_source, research_date, research_methods_used
- refresh_schedule, last_refreshed_at, active_acquirer

**Proposal-scoped fields (correctly here):**
- id, proposal_id, target_id, entity, deal_side
- fit_score, fit_score_breakdown, fit_narrative
- approach_strategy, approach_script, call_opener
- one_pager_html, one_pager_json
- outreach_sequence, email_draft, letter_draft, linkedin_draft
- verified_contacts, source_attribution
- expert_verdict, expert_comment, expert_name, expert_verdict_at
- engagement_stage, status
- letter_sent_at, email_sent_at, called_at, linkedin_sent_at
- response, response_date, meeting_scheduled
- dnc_checked_at, dnc_clear

**Contact fields (should be on contacts table):**
- buyer_contact_name, buyer_title, buyer_email, buyer_phone, buyer_linkedin

### buyer_intelligence — IS A VIEW, NOT A TABLE

```sql
SELECT eb.*, p.company_name AS seller_company, p.owner_name AS seller_owner,
       p.vertical AS seller_vertical, p.deal_side AS seller_deal_side
FROM engagement_buyers eb
JOIN proposals p ON eb.proposal_id = p.id
ORDER BY p.company_name, eb.fit_score DESC NULLS LAST;
```

Only 1 code file references it (`hrcom-data-audit.html`).

### store_buyer_research — RPC FUNCTION (critical write path)

```sql
-- UPSERTs into engagement_buyers mixing company + proposal fields
-- Writes: story_narrative, call_opener, buyer_revenue, fit_score, confidence,
--         verified_contacts, convergence_points, vision_mapping, pain_mapping,
--         research_source, research_date, deal_side, entity, buyer_type
```

This function is the primary way research data enters the system. It treats company data and engagement data as one flat record.

### companies table (287 rows)

Exists but only ~3 of the 224 buyer companies appear in it. This table is used for SELLER companies, not buyers.

### contacts table (2,191 rows)

Exists but buyer contact info is stored inline on engagement_buyers, not linked here.

## Downstream Consumers (32 files)

### SELECT * / implicit all-fields (MUST update — 7 files)
- `backend/server.py:80` — Direct SQL
- `backend/lib/buyer_page_generator.py:839` — Direct SQL `eb.*`
- `backend/lib/engagement_engine.py:74` — Direct SQL
- `backend/lib/why_sell_engine.py:185,192` — REST API, no select param
- `public/interactive-proposal-template.js:72` — REST `select=*`
- `public/buyer-matching.html:269` — REST `select=*`
- `public/client-portal.html:253` — REST, no select param

### Explicit column queries (safer — 15 files)
- `backend/lib/company_hub.py:68` — 18 explicit columns
- `backend/lib/meeting_engine.py:91` — 6 explicit columns
- `backend/lib/dashboard.py:68` — COUNT only
- `backend/lib/slack_messages.py:27` — COUNT only
- `backend/scripts/buyer_1pager_pipeline.py:361` — 10 explicit columns
- `backend/scripts/buyer_1pager_fix.py:78` — same pattern
- `backend/scripts/refresh_hub_buyers.py:194,243` — explicit columns
- `backend/scripts/buyer-1pager-engine.mjs:330` — explicit select
- `backend/scripts/rebuild-proposals.js:1738` — explicit select
- `backend/data/insert_buyers.js:62` — INSERT 12 columns
- `public/buyer-feedback.js:251,312` — explicit select on expert_* fields
- `public/why-sell-narratives.html:631` — explicit select 6 columns
- `scripts/morning_audit.py:359` — select=proposal_id only

### Server-side objects
- `buyer_intelligence` VIEW — reads from engagement_buyers
- `store_buyer_research` RPC — writes to engagement_buyers
- 0 triggers, 0 RLS policies
- 3 indexes: pkey, idx_eb_proposal, idx_engagement_buyers_verdict

## Dead Fields (in schema, 0 code references)

buyer_description, competitive_advantage, pain_mapping, vision_mapping, convergence_points, research_source, research_date, research_methods_used, refresh_schedule, last_refreshed_at, active_acquirer

**BUT** `store_buyer_research` RPC writes to: convergence_points, vision_mapping, pain_mapping, research_source, research_date — so they're not truly dead, just never read by application code.

## Field Usage Frequency

| Field | Read by N files | Written by N files |
|-------|:-:|:-:|
| buyer_company_name | 14 | 2 |
| buyer_type | 13 | 2 |
| buyer_city | 9 | 2 |
| buyer_state | 9 | 2 |
| fit_score | 14 | 3 |
| fit_narrative | 7 | 1 |
| approach_strategy | 8 | 1 |
| approach_script | 7 | 2 |
| one_pager_html | 3 | 3 |
| expert_verdict/comment | 3 | 2 |
| story_narrative | 2 | 1 (RPC) |
| buyer_revenue | 1 | 1 (RPC) |
| All other company fields | 0-1 | 1 (RPC) |

## Data Quality Issues

1. 4 engagement_buyers had wrong entity tag (FIXED 2026-04-01)
2. 4 buyers missing one_pager_json (Wave 2 pipeline gap)
3. 1 buyer (MyPeople.ai) has full description paragraph in buyer_type field
4. dossier_final.deal_side = 'buy' for HR.com (should be 'sell')
5. 3 Exa research executions failed for HR.com seller research
6. 0 letters sent, 0 calls made, 0 feedback collected

## Constraints

- Live production system on Vercel (static HTML) + Supabase (PostgreSQL)
- No CI/CD tests — all validation is manual
- Single developer (Ewing) with AI agents doing most implementation
- 6 active clients across 3 entities sharing one Supabase instance
- No staging environment — changes go straight to production
- Budget-conscious: ~$0.89 total API spend to date

## What We're Trying to Decide

1. Should we split engagement_buyers into company + engagement tables?
2. If yes, what's the safest migration path?
3. If no, what's the alternative (views, computed columns, leave it)?
4. How do we handle the 7 SELECT * files?
5. How do we handle the store_buyer_research RPC?
6. What's the blast radius if we get it wrong?
