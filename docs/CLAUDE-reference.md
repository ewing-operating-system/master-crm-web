# Master CRM Web — Reference (Architecture, Schema, Pipeline, Scoring)

## ARCHITECTURE

```
Vercel (Production)
├── public/           # 380+ static HTML pages (hub pages, buyer pages, meeting prep)
├── api/              # Serverless functions (letters, auth, webhooks)
└── lib/              # Shared JS (portal-config, supabase-letters, lob-integration)

Backend (Local Python — NOT deployed to Vercel)
├── backend/          # Agent orchestration, worker, watchdog
├── scripts/          # Automation (regenerate pages, overnight research, render output)
└── docs/             # Architecture docs, specs, audit reports
```

**Stack:** No framework, no build step. Raw HTML + vanilla JS. `vercel.json` sets `outputDirectory: "public"`.

## SUPABASE

ONE instance. Never create new projects. Credentials from env vars only (see `.env.example`).

Key tables: `proposals`, `engagement_buyers`, `letter_approvals`, `cost_ledger`, `agent_queue`, `targets`, `contacts`, `page_versions`, `do_not_call`, `guardrail_log`

Entity views: `nc_targets`, `nc_companies`, `nc_contacts`, `and_targets`, `and_companies`, `and_contacts`, `and_investors`, `ru_targets`, `ru_companies`, `ru_contacts`

**`buyer_intelligence` is a VIEW** (reads from `engagement_buyers` joined with `proposals`). Do not INSERT/UPDATE it.

## DATA PIPELINE

### Buyer Research Pipeline
```bash
# Single buyer (production — always use traced version)
python3 scripts/traced_buyer_run.py --buyer "ADP" --city Roseland --state NJ --ticker ADP --domain adp.com

# Outputs: per-buyer JSON, manifest, trace docs, auto git push
# See docs/DEBBIE-REVIEW-SYSTEM.md for batch run syntax and full spec
```

Supabase writes do NOT appear on site automatically. Three steps required:
1. **Write to Supabase** — correct table/columns
2. **Regenerate pages** — `scripts/regenerate.py` rebuilds HTML
3. **Commit + deploy** — via `scripts/deploy.sh`

`backend/worker.py` handles steps 2+3 automatically after agent completions. `backend/orchestrator.py` syncs every 5 min as safety net.

New pages must be registered in `page_versions` and linked from the relevant hub page.

## BUYER SCORING

| Score | Label | Criteria |
|-------|-------|----------|
| 8 | HIGH | Confirmed prior acquisition in seller's vertical (must name the deal) |
| 6 | MEDIUM | Operates in adjacent space, no confirmed acquisition |
| 4 | LOW | Wrong vertical, pure VC, advisory, or too small |

When in doubt, score 6. Never use floats or scores above 8.

## RELATED DOCS

- `docs/CLAUDE-backend.md` — Backend agents, campaigns, entity classification
- `docs/page-system-v2-architecture.md` — Page generation system
- `docs/LETTER-TEMPLATE-ENGINE-EXECUTION.md` — Letter scoring and generation
- `docs/MEETING-PAGE-V2-SPEC.md` — Interactive meeting prep pages
- `docs/ENGAGEMENT-BUYERS-MIGRATION-BRIEF.md` — engagement_buyers audit
- `docs/DEBBIE-REVIEW-SYSTEM.md` — Debbie buyer review pages, traced pipeline, data contract, batch run process
