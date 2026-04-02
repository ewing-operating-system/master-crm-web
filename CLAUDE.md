# Master CRM Web — Claude Code Instructions

## WHAT THIS IS

Static HTML site + Vercel serverless API routes for Ewing Gillaspy's M&A advisory CRM. Serves company portal pages, buyer research, letter generation, and meeting prep to clients and internal reps.

**Entities:** Next Chapter (`next_chapter`), AND Capital (`and_capital`), RevsUp (`revsup`), The Forge (`the_forge`), BioLev (`biolev`), Sea Sweet (`sea_sweet`), Precision Exploration (`precision_exploration`)

**GitHub:** `ewing-operating-system/master-crm-web`

## ARCHITECTURE

```
Vercel (Production)
├── public/           # 380+ static HTML pages (hub pages, buyer pages, meeting prep)
├── api/              # Serverless functions (letters, auth, webhooks)
├── middleware.js      # Edge Middleware (portal gating — currently DISABLED)
└── lib/              # Shared JS (portal-config, supabase-letters, lob-integration)

Backend (Local Python — NOT deployed to Vercel)
├── backend/          # Agent orchestration, worker, watchdog
├── scripts/          # Automation (regenerate pages, overnight research, render output)
└── docs/             # Architecture docs, specs, audit reports
```

**Stack:** No framework, no build step. Raw HTML + vanilla JS. `vercel.json` sets `outputDirectory: "public"`.

## SINGLE SUPABASE INSTANCE

- **Project:** `dwrnfpjcvydhmhnvyzov`
- **URL:** `$SUPABASE_URL`
- **Service Role:** `$SUPABASE_SERVICE_ROLE_KEY` (secret — server-side only)
- **Anon Key:** `$SUPABASE_ANON_KEY` (public — browser-safe, in `public/supabase-config.js`)

Key tables: `proposals`, `engagement_buyers`, `letter_approvals`, `cost_ledger`, `agent_queue`, `targets`, `contacts`, `page_versions`, `do_not_call`, `guardrail_log`

Entity views: `nc_targets`, `nc_companies`, `nc_contacts`, `and_targets`, `and_companies`, `and_contacts`, `and_investors`, `ru_targets`, `ru_companies`, `ru_contacts`

## CREDENTIAL RULES

1. **NEVER hardcode API keys.** All credentials come from env vars (see `.env.example`).
2. **Python:** `os.environ.get("VAR_NAME", "")` — empty string fallback, never a raw key.
3. **Node/JS:** `process.env.VAR_NAME` — Vercel injects these at runtime.
4. **Frontend JS:** `window.__SUPABASE_URL` / `window.__SUPABASE_ANON_KEY` from `public/supabase-config.js`. This is the ONLY file with a raw anon key (public by Supabase design).
5. **Pre-commit hook** blocks commits containing key patterns. Allowlists `supabase-config.js`.
6. **Canonical env var names** match `~/.zshrc`. See `.env.example` for the full list.

## VERCEL ENV VARS (Production)

```
SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ANON_KEY, DATABASE_URL,
OPENROUTER_API_KEY, EXA_API_KEY, LOB_API_KEY, LOB_WEBHOOK_SECRET,
BATCH_SEND_SECRET, SALESFINITY_API_KEY,
PORTAL_PW_ADMIN, PORTAL_PW_HRCOM, PORTAL_PW_AQUASCIENCE, PORTAL_PW_SPRINGER,
PORTAL_PW_AIRCONTROL, PORTAL_PW_DESIGNPRECAST, PORTAL_PW_WIESER
```

## PORTAL AUTH SYSTEM

6 company portals with password-based access. Password identifies the company (no username).

| Company | Slug | Hub Page | Env Var |
|---------|------|----------|---------|
| HR.com Ltd | `hrcom` | `hrcom-ltd-hub.html` | `PORTAL_PW_HRCOM` |
| AquaScience | `aquascience` | `aquascience-hub.html` | `PORTAL_PW_AQUASCIENCE` |
| Springer Floor | `springer` | `springer-floor-hub.html` | `PORTAL_PW_SPRINGER` |
| Air Control | `air-control` | `air-control-hub.html` | `PORTAL_PW_AIRCONTROL` |
| Design Precast | `design-precast` | `design-precast-and-pipe-inc-hub.html` | `PORTAL_PW_DESIGNPRECAST` |
| Wieser Concrete | `wieser` | `wieser-concrete-products-inc-hub.html` | `PORTAL_PW_WIESER` |

**Auth flow:** `POST /api/auth/login` → sets `portal_session` cookie (HttpOnly, 7-day) → middleware gates pages by company slug. Admin password grants all-company access.

**Portal gating has been removed.** All pages are publicly accessible.

Public paths (always accessible): `/login.html`, `/api/*`, `/outputs/`, `/running-log.html`, `/system-overview.html`, `/version-history.html`, `/feature-roadmap.html`

## API ROUTES

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/auth/login` | POST | Password auth, sets session cookie |
| `/api/auth/logout` | POST | Clears session cookie |
| `/api/letters/generate` | POST | Generate personalized letter from meeting data |
| `/api/letters/approve` | POST | Move letter to approved status |
| `/api/letters/send` | POST | Save letter to Supabase |
| `/api/letters/send-to-lob` | POST | Print & mail via Lob API ($1.75/letter) |
| `/api/letters/batch-send` | POST | Batch send up to 250 letters (requires `BATCH_SEND_SECRET`) |
| `/api/webhooks/lob` | POST | Lob delivery event callbacks |

## KEY SCRIPTS

| Script | Usage |
|--------|-------|
| `scripts/regenerate.py` | Regenerate hub pages from Supabase (incremental) |
| `scripts/regenerate_all.py` | Full rebuild of all hub pages (template changes) |
| `scripts/render-output.py` | Convert JSON/MD output files to styled HTML |
| `scripts/refresh_hub_buyers.py` | Backfill buyer data + regenerate hub buyer table |
| `scripts/overnight-research.sh` | Autonomous overnight research pipeline |
| `scripts/sync_call_intel.py` | Sync Salesfinity call outcomes to Supabase |

## HARD RULES

1. **Every row gets an entity tag.** No untagged data.
2. **DNC is universal.** One block = blocked everywhere, all entities, all channels.
3. **ONE Supabase instance.** Never create new projects or instances.
4. **Never sign up for new services** without explicit approval.
5. **Always commit + push** after changes.
6. **Letters before calls.** Mail sends first, enrichment (cell/email) is post-letter.
7. **250/150 Governor.** Max 250 letters per batch. Hard stop until 150 contacts called 5x each.
8. **Verify schema before coding.** Query `?limit=1&select=*` to confirm table/column names exist.
9. **Never generate reports from memory.** Read actual data first.
10. **Multi-LLM consensus** required before customer-facing documents.
11. **If a key fails, STOP.** Do not sign up for replacements.

## DATA PIPELINE RULES (Critical — prevents research from going invisible)

Vercel serves **static HTML**. Supabase writes do NOT automatically appear on the site. Every agent, script, and process that writes research data MUST complete all three steps:

1. **Write to Supabase** — store structured data in the correct table/columns.
2. **Regenerate static pages** — run `scripts/regenerate.py` (or the relevant regeneration script) to rebuild the HTML. If the agent writes to `public/data/*.json`, that file must be committed.
3. **Commit + push to git** — Vercel deploys from git. No push = no deploy = invisible data.

### Automatic pipeline (already wired)
- `backend/worker.py` calls `trigger_regeneration()` after any `swarm_enrichment`, `researcher`, or `buyer_1pager` agent completes. This handles step 2+3.
- `backend/orchestrator.py` runs `sync_stale_pages()` and `sync_public_data_git()` every 5 minutes as a safety net.

### Rules for new agents/scripts
- **Every new page must be registered** in the `page_versions` table via `scripts/regenerate.py:register_page()`.
- **Every new page must be linked** from the relevant hub page (e.g., `hrcom-ltd-hub.html`). Orphan pages are invisible.
- **Static JSON files** under `public/data/` must be git-committed after writes. The orchestrator does this automatically, but manual scripts should also commit.
- **Never write company-profile data to `engagement_buyers`** unless it's proposal-scoped. Company-level data (HQ, revenue, description) goes on the company record; proposal-level data (fit_score, approach_strategy, one_pager) stays on `engagement_buyers`.
- **The `store_buyer_research` RPC** writes both company and proposal fields to `engagement_buyers`. This is a known legacy pattern — do not extend it. New research fields should go to `public/data/*.json` or a dedicated table.
- **`buyer_intelligence` is a VIEW**, not a table. It reads from `engagement_buyers` joined with `proposals`. Do not INSERT/UPDATE it.

### Field ownership (engagement_buyers)
| Owner | Fields |
|-------|--------|
| Proposal-scoped (correct home) | fit_score, fit_narrative, approach_strategy, approach_script, call_opener, one_pager_html/json, outreach_sequence, email/letter/linkedin_draft, expert_verdict/comment, engagement_stage, status, sent_at timestamps, response fields, dnc_* |
| Company-scoped (legacy, do not extend) | buyer_company_name, buyer_type, buyer_city, buyer_state, buyer_revenue, buyer_employee_count, buyer_description, story_narrative, confidence, acquisition_history, investment_thesis |
| Contact-scoped (legacy, do not extend) | buyer_contact_name, buyer_title, buyer_email, buyer_phone, buyer_linkedin |

## BUYER SCORING

| Score | Label | Criteria |
|-------|-------|----------|
| 8 | HIGH | Confirmed prior acquisition in seller's vertical (must name the deal) |
| 6 | MEDIUM | Operates in adjacent space, no confirmed acquisition |
| 4 | LOW | Wrong vertical, pure VC, advisory, or too small |

When in doubt, score 6. Upgrade to 8 only with acquisition evidence. Never use floats or scores above 8.

## FRONTEND PATTERN

All frontend JS widgets use centralized config. Every HTML page that uses Supabase must include:
```html
<script src="/supabase-config.js"></script>
```
before any widget scripts. Widgets read `window.__SUPABASE_URL` and `window.__SUPABASE_ANON_KEY`.

## PEOPLE ROUTING

- **Ewing Gillaspy:** AND Capital + Next Chapter only. NEVER RevsUp in Salesfinity.
- **Mark DeChant:** All three entities.
- **John Kelly:** Next Chapter + RevsUp ONLY. NEVER AND Capital.
- **Chris Rex:** AND Capital ONLY. Separate stack, invisible to this workspace.

## RELATED DOCS

- `docs/CLAUDE-backend.md` — Full backend infra, agents, campaigns, entity classification
- `docs/page-system-v2-architecture.md` — Page generation system
- `docs/LETTER-TEMPLATE-ENGINE-EXECUTION.md` — Letter scoring and generation algorithm
- `docs/MEETING-PAGE-V2-SPEC.md` — Interactive meeting prep pages
- `docs/CURRENT-BUILD-STATE.md` — Recent feature completions
