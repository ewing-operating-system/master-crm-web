# Master CRM Web — Claude Code Instructions

## WHAT THIS IS

Static HTML site + Vercel serverless API routes for Ewing Gillaspy's M&A advisory CRM. Serves company portal pages, buyer research, letter generation, and meeting prep.

**Entities:** Next Chapter (`next_chapter`), AND Capital (`and_capital`), RevsUp (`revsup`), The Forge (`the_forge`), BioLev (`biolev`), Sea Sweet (`sea_sweet`), Precision Exploration (`precision_exploration`)

**GitHub:** `ewing-operating-system/master-crm-web`

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

## CREDENTIAL RULES

**NEVER hardcode API keys.** Python: `os.environ.get()`. Node: `process.env`. Frontend: `window.__SUPABASE_URL` / `window.__SUPABASE_ANON_KEY` from `public/supabase-config.js`. Pre-commit hook blocks key patterns. Full list in `.env.example`.

## HARD RULES

1. **Every row gets an entity tag.** No untagged data.
2. **DNC is universal.** One block = blocked everywhere, all entities, all channels.
3. **Never sign up for new services** without explicit approval. If a key fails, STOP.
4. **Deploy via `scripts/deploy.sh` only.** Git push does NOT auto-deploy to Vercel.
5. **Letters before calls.** Mail sends first, enrichment is post-letter.
6. **250/150 Governor.** Max 250 letters per batch. Hard stop until 150 contacts called 5x each.
7. **Verify schema before coding.** Query `?limit=1&select=*` to confirm tables/columns exist.
8. **Never generate reports from memory.** Read actual data first.
9. **Multi-LLM consensus** required before customer-facing documents.

## DEPLOYMENT

**`git push` does NOT deploy.** Vercel's GitHub webhook is NOT connected.

```bash
bash scripts/deploy.sh --skip-commit          # after committing
bash scripts/deploy.sh --files "file" --message "msg"  # commit + deploy
```

Watchdog cron (`scripts/deploy_watchdog.sh`) runs every 5 min as safety net.

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

## PEOPLE ROUTING

- **Ewing Gillaspy:** AND Capital + Next Chapter only. NEVER RevsUp in Salesfinity.
- **Mark DeChant:** All three entities.
- **John Kelly:** Next Chapter + RevsUp ONLY. NEVER AND Capital.
- **Chris Rex:** AND Capital ONLY. Separate stack, invisible to this workspace.

## RELATED DOCS

- `docs/CLAUDE-backend.md` — Backend agents, campaigns, entity classification
- `docs/page-system-v2-architecture.md` — Page generation system
- `docs/LETTER-TEMPLATE-ENGINE-EXECUTION.md` — Letter scoring and generation
- `docs/MEETING-PAGE-V2-SPEC.md` — Interactive meeting prep pages
- `docs/ENGAGEMENT-BUYERS-MIGRATION-BRIEF.md` — engagement_buyers audit
- `docs/DEBBIE-REVIEW-SYSTEM.md` — Debbie buyer review pages, traced pipeline, data contract, batch run process
