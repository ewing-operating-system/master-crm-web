# Next Chapter M&A Advisory — AI System Architecture Briefing

**Prepared:** March 30, 2026
**Author:** Ewing Gillaspy, Founder & Operator
**Purpose:** CTO Coach Audit — Method, Stack, Routines, Integration Map

---

## EXECUTIVE SUMMARY

This system is an **always-on prospecting-to-proposal engine** for M&A advisory in home services. It researches acquisition targets, generates physical letters, mails them via API, tracks phone outreach, and delivers a single "wow factor" URL to each prospect — all with minimal human touch.

The architecture spans **three layers**: a Claude Code development environment (where humans build), an OpenClaw orchestration platform (where agents run autonomously), and a Supabase + Vercel production stack (where data lives and pages deploy).

**Current state:** Core engines built, Supabase connected, 317 pages live on Vercel, Lob mail API verified. Autonomous agent pipeline designed but not yet operational (credential sync + agent instruction files needed).

---

## THE BUSINESS FLOW (What Actually Happens)

```
  RESEARCH          GENERATE           MAIL             CALL            CLOSE
 ┌─────────┐     ┌───────────┐     ┌─────────┐     ┌──────────┐     ┌────────┐
 │ Find new │     │ Build hub │     │ Print &  │     │ Parallel │     │ Share  │
 │ targets, │ ──► │ page, letter│ ──►│ mail via │ ──► │ dial via │ ──► │ URL on │
 │ qualify, │     │ proposal,  │     │ Lob API  │     │Salesfinity│    │ phone  │
 │ score    │     │ story page │     │ (250 max)│     │(150 x 5) │     │ call   │
 └─────────┘     └───────────┘     └─────────┘     └──────────┘     └────────┘
      │                │                 │                │               │
      ▼                ▼                 ▼                ▼               ▼
   Supabase         Vercel           Lob API        Salesfinity      Prospect
   targets          public/          letters        call_outcomes    sees page
   table            317 pages        endpoint       table            and says
                                                                     "wow"
```

**The 250/150 Governor:** Send a maximum of 250 letters per batch. HARD STOP. Monitor until 150 of those contacts have been called 5 times each in Salesfinity. Only then unlock the next batch. This prevents spray-and-pray and ensures every letter gets proper phone follow-up.

---

## SYSTEM ARCHITECTURE MAP

### Layer 1: Development Environment (Claude Code)

This is where Ewing and Claude build together. Three specialized sub-agents handle different task types automatically:

| Sub-Agent | Model | Cost | Role | Example Tasks |
|-----------|-------|------|------|---------------|
| **haiku-executor** | Claude Haiku 4.5 | ~$0.05/task | Fast execution, no reasoning | Git commits, file moves, health checks |
| **sonnet-builder** | Claude Sonnet 4.6 | ~$0.50/task | Build + moderate reasoning | Edit configs, write integrations, fix bugs |
| **opus-architect** | Claude Opus 4.6 | ~$2.00/task | Strategic design | Architecture decisions, trade-off analysis |

Claude Code **automatically routes** tasks to the right sub-agent based on complexity. No manual switching.

**Overnight batch runner:** A bash script runs 9 sequential headless Claude Sonnet sessions while Ewing sleeps. Each session builds a specific feature (letter engine, campaign manager, mobile CSS, etc.) using prompt files stored in `/prompts/`.

### Layer 2: Agent Orchestration (OpenClaw)

OpenClaw is a multi-agent platform running on the Mac Mini. It provides:
- **Gateway** on port 18789 (API for agent communication)
- **Cron scheduler** for recurring autonomous tasks
- **Agent fleet** with per-agent workspaces, models, and instruction files
- **Telegram bot** (@MacMiniEwingBot) for notifications and commands from phone

**10 OpenClaw Agents Defined:**

| Agent | Model | Purpose |
|-------|-------|---------|
| **main** | DeepSeek Chat | Primary orchestration and routing |
| **researcher** | Gemini 2.5 Flash Lite | Web research, target qualification |
| **executor** | GPT-4o Mini | Task execution and command running |
| **validator** | DeepSeek V3 | Quality checks on research output |
| **auditor** | DeepSeek V3 | Pipeline health and compliance audits |
| **classifier** | DeepSeek V3 | Company and data classification |
| **controller** | DeepSeek Chat | Pipeline flow control and gating |
| **listener** | Gemini 2.5 Flash Lite | Channel monitoring (Telegram, email) |
| **certifier** | DeepSeek V3 | Data quality certification |
| **nurturer** | GPT-4o Mini | Outreach relationship management |

**Multi-model strategy:** Expensive models (Claude Opus/Sonnet) handle development. Cheap models (DeepSeek at $0.27/M input, Gemini Flash Lite, GPT-4o Mini) handle high-volume autonomous research. Ollama runs local embeddings at zero cost.

### Layer 3: Production Stack (Supabase + Vercel)

| Service | Role | Details |
|---------|------|---------|
| **Supabase** | Database + Auth | PostgreSQL with REST API. Stores targets, companies, contacts, pipeline state, call logs, campaign tracking |
| **Vercel** | Hosting + Serverless | Static HTML pages + API routes. Auto-deploys on git push |
| **Lob** | Physical mail | API sends print-ready letters. Webhooks track delivery status |
| **Salesfinity** | Parallel dialer | AI-powered phone dialing. Contacts pushed via API, outcomes synced back |
| **Telegram** | Control channel | Bot sends notifications, receives commands from phone |
| **Tailscale** | Network mesh | Secure access to Mac Mini dashboard from any device (IP: 100.112.160.48) |

---

## THE ENGINES (What Generates Output)

### 1. Letter Engine (`lib/letter_engine.py`)

Renders physical letters for Lob mail API from Supabase company data.

**Input:** Company ID + variant (touch_1, touch_2, touch_3)
**Output:** Print-ready HTML (8.5x11, Georgia serif, no color)

**How it works:**
- Pulls company data from Supabase (name, city, vertical, revenue, owner)
- Loads vertical-specific EBITDA benchmarks (7 verticals: water treatment, HVAC, plumbing, roofing, pest control, concrete, flooring)
- Generates paragraphs: opening hook, industry context, EBITDA narrative, highlight quote, personalized close
- Renders through Jinja2 template with 24 variables
- Each letter includes a **personalized URL** pointing to the prospect's hub page

**Operator narrative tone:** Letters read like they're from an operator who's been in the industry, not a PE fund sending form letters. "I know what it's like to build something with your hands and wonder what happens to the team when you're ready to step back."

### 2. Meeting Engine v2 (`lib/meeting_engine_v2.py`)

Renders interactive meeting prep pages with three meeting types.

**Meeting types:** Discovery, Financial Review, Engagement — each with distinct question sets (10 questions per type)

**Features:**
- Three tabs: Pre-Meeting / During-Meeting / Post-Meeting
- During-meeting: owner profile dropdowns, emotional temperature slider, revenue mix fields, margin grid, key employees table, deal breakers checklist, verbatim quotes capture
- Auto-saves every field to Supabase on change (600ms debounce)
- Per-field save indicators (saved/saving/queued for offline)
- Completeness score tracking (12 core fields)
- Unlock tracker: shows which downstream documents become available as fields are filled (letter unlocks at 3 fields, buyer targeting at 5, proposal at 6, full pipeline at 10)

### 3. Campaign Manager (`lib/campaign_manager.py`)

Governs the 250/150 letter-to-call pipeline.

**Rules enforced at three layers:**
1. **Python logic:** `send_batch()` checks count, `check_threshold()` gates next batch
2. **Database constraints:** `CHECK (letter_count <= 250)` on campaign_batches table
3. **Unique index:** Only one active batch per entity at a time

**Flow:**
```
create_campaign(company_ids) → slice into batches of 250
  → send_batch() → render letters → send via Lob → track in Supabase
  → check_threshold() → query Salesfinity call logs
  → if 150 contacts called 5x each → unlock next batch
  → else → HARD STOP, notify via Telegram
```

### 4. Regeneration Scripts (`scripts/regenerate.py`, `regenerate_all.py`)

Rebuilds hub pages from Supabase data.

- **Incremental** (`regenerate.py`): Only rebuilds pages for companies with new/stale research
- **Full rebuild** (`regenerate_all.py`): All 171+ non-disqualified targets
- Supports `--dry-run`, `--company "Name"`, `--entity next_chapter` flags
- After generation: git commit + push triggers Vercel deploy automatically

### 5. Lob Client (`lib/lob_client.py`)

HTTP wrapper for Lob physical mail API.

- `send_letter(html, to_address, from_address)` → returns letter_id, tracking_url, expected_delivery_date
- `get_letter_status(letter_id)` → polls delivery status
- Webhook receiver at `/api/webhooks/lob.js` for delivery callbacks

### 6. Salesfinity Client (`lib/salesfinity_client.py`)

API integration for AI parallel dialer.

- `create_dialer_list(contacts)` → pushes contacts for calling
- `get_call_outcomes(list_id)` → fetches results (connected, voicemail, no answer, interested, etc.)
- `sync_outcomes_to_supabase()` → writes call_log records back to database

---

## DATA ARCHITECTURE

### Supabase Tables

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `targets` | Master list of acquisition targets | company_name, pipeline_status, vertical, notes, acquisition_status |
| `companies` | Enriched company profiles | name, city, state, revenue, founded_year, personalized_url |
| `contacts` | Owner/decision-maker contacts | first_name, last_name, phone, email, role |
| `pipeline_log` | Audit trail for all agent actions | agent, action, details, timestamp |
| `call_log` | Salesfinity call outcome tracking | contact_id, outcome, duration, called_at |
| `meeting_notes` | Per-field meeting data capture | meeting_id, field_name, field_value, captured_at |
| `campaign_batches` | 250/150 governor state | batch_number, letter_count, calls_completed, status |
| `letter_campaigns` | Individual letter tracking via Lob | lob_letter_id, variant, status, delivered_at |
| `call_outcomes` | Per-call attempt tracking | target_id, attempt_number (max 5), outcome |
| `deal_research` | Deep research notes per deal | (expanding) |

### Pipeline Status Flow

```
NEW → RESEARCHING → RESEARCHED → NEEDS_REVIEW → REPORT_LIVE → (outreach begins)
                                      ↑
                                 Quality gate:
                              "$5,000 consulting
                               report standard"
```

Every status transition is logged to `pipeline_log` with agent name, action, and reasoning.

---

## RESEARCH & QUALIFICATION METHOD

### Step 0: Acquisition Status Check (runs before all research)

10 targeted search queries per company to detect if already acquired:
- Company website footer (parent company disclosure)
- LinkedIn parent organization field
- BBB profile ownership changes
- Google Business Profile
- Trade press acquisition announcements

**Classification:** ACQUIRED / PLATFORM / INDEPENDENT / UNCLEAR

Only INDEPENDENT targets proceed to full research.

### Enrichment Sources

| Source | What It Provides | API/Method |
|--------|-----------------|------------|
| **Exa** (MCP) | Semantic web search, company discovery, contact enrichment | `web_search_exa`, `crawling_exa` |
| **Google Search API** | Broad web discovery, news, press releases | Gemini provider via OpenClaw |
| **Fireflies** (MCP) | Meeting transcripts, summaries, action items | `fireflies_get_transcript`, `fireflies_search` |
| **Gmail** (MCP) | Email threads, contact history | `gmail_search_messages`, `gmail_read_thread` |
| **Slack** (MCP) | Team discussions, deal context | `slack_search_public`, `slack_read_channel` |
| **Google Calendar** (MCP) | Meeting schedules, availability | `gcal_list_events`, `gcal_find_meeting_times` |
| **Google Drive** (MCP) | Shared documents, presentations | `google_drive_search`, `google_drive_fetch` |
| **Ollama** (local) | Vector embeddings via nomic-embed-text | localhost:11434 |
| **ChromaDB** (local) | Semantic search across all ingested data | Python API |

### Story Intelligence Layer

Beyond financial data, the system hunts for **human stories** about each founder:
- YouTube interviews and podcast appearances
- Local news features and community involvement
- Google reviews mentioning the owner by name
- Trade publication profiles
- BBB complaint responses (reveals character)

These feed into the **Company Story Template** — a Lovable-inspired storyboard page with photos, pull quotes, generational narrative, and a "What Happens to the Team" section. The story page is what makes the prospect say "these people actually know us."

---

## BUSINESS RULES ENGINE

Business rules are stored at multiple levels:

| Rule Type | Where Stored | Example |
|-----------|-------------|---------|
| **Pipeline gates** | Python code (campaign_manager.py) | 250 letter max, 150/5x call threshold |
| **Database constraints** | Supabase CHECK + UNIQUE INDEX | Only one active batch per entity |
| **Quality standards** | SOUL.md (agent instructions) | "$5,000 consulting report" quality bar |
| **Scoring rubrics** | letter_engine.py vertical benchmarks | EBITDA floors/ceilings/medians per vertical |
| **Classification rules** | Acquisition status check (SOUL.md) | 10-query detection protocol |
| **Tone rules** | Letter template + prompt files | Operator narrative, not PE finance speak |
| **Cost caps** | Campaign manager + cron config | $1.50 per target research cost limit |
| **Retry logic** | Self-repair protocol | Exponential backoff: 30s/60s/120s/SKIP |

---

## COST STRUCTURE

| Component | Cost Per Unit | Usage Pattern |
|-----------|-------------|---------------|
| Claude Opus (architect) | ~$15/M input, $75/M output | Strategic design only |
| Claude Sonnet (builder) | ~$3/M input, $15/M output | Feature building, ~$0.50/session |
| Claude Haiku (executor) | ~$0.25/M input, $1.25/M output | Bulk execution |
| DeepSeek Chat | $0.27/M input, $1.10/M output | Autonomous agent work |
| Gemini Flash Lite | Free tier / minimal | Research agent |
| GPT-4o Mini | $0.15/M input, $0.60/M output | Executor + nurturer agents |
| Ollama (local) | $0.00 | Embeddings (nomic-embed-text) |
| Lob letters | ~$1.50/letter | Physical mail |
| Exa search | Per-query pricing | Target enrichment |
| Supabase | Free tier (current) | Database + auth |
| Vercel | Free tier (current) | Static hosting + serverless |

**Target cost per researched-and-mailed prospect:** Under $5.00 all-in (research + letter + tracking).

---

## SCHEDULED ROUTINES (Designed, Not Yet Active)

| Routine | Frequency | What It Does |
|---------|-----------|-------------|
| **batch-pull** | Every 2 hours | Pull NEW targets from Supabase, set to RESEARCHING |
| **research-loop** | Every 30 min | Run 5-step research on RESEARCHING targets |
| **quality-review** | Every 30 min | Review RESEARCHED targets against $5K report standard |
| **morning-brief** | Every 4 hours | Pipeline status summary with counts and costs |
| **publish-and-send** | Every hour | Generate reports for approved targets, queue outreach |
| **dialer-update** | Every 2 hours | Push REPORT_LIVE contacts to Salesfinity with call scripts |
| **heartbeat** | Every 15 min | Health check: stuck targets, errors, pipeline counts |
| **weekly-maintenance** | Weekly | Memory flush, error patterns, cost tracking vs. $1.50 cap |

---

## WHAT'S LIVE vs. WHAT'S NEXT

### LIVE NOW
- 317 HTML pages deployed on Vercel (hub pages, research, proposals, EBITDA levers, meeting notes)
- Letter engine generating print-ready HTML from Supabase data
- Meeting page v2 with live auto-save and completeness tracking
- Lob API verified and connected (live secret key)
- Telegram bot operational for notifications
- Regeneration scripts for incremental and full page rebuilds
- Claude Code sub-agents routing tasks by complexity
- Tailscale mesh for remote dashboard access
- Ollama + ChromaDB installed for local vector search

### NEXT TO ACTIVATE
- Fix Supabase credential sync (5-minute fix, script written)
- Create missing database tables (SQL migration written)
- Write SOUL.md instruction files for all 10 OpenClaw agents
- Enable cron scheduler with correct agent IDs and delivery channels
- Wire Salesfinity API for call outcome sync
- Connect ChromaDB ingestion pipeline (Fireflies transcripts + Slack + Gmail)
- Campaign manager end-to-end test (letter → Lob → track → Salesfinity → threshold)

---

## INFRASTRUCTURE MAP

```
┌─────────────────────────────────────────────────────────────────────┐
│                        MAC MINI (Always On)                        │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────────┐ │
│  │ Claude Code   │  │  OpenClaw    │  │  Local Services           │ │
│  │              │  │  Gateway     │  │                           │ │
│  │ ┌──────────┐ │  │  :18789     │  │  Ollama    :11434         │ │
│  │ │  Opus    │ │  │              │  │  (nomic-embed-text)       │ │
│  │ │Architect │ │  │  10 Agents:  │  │                           │ │
│  │ ├──────────┤ │  │  main        │  │  ChromaDB  (Python)       │ │
│  │ │ Sonnet   │ │  │  researcher  │  │  (vector store)           │ │
│  │ │ Builder  │ │  │  executor    │  │                           │ │
│  │ ├──────────┤ │  │  validator   │  │  Tailscale                │ │
│  │ │  Haiku   │ │  │  auditor     │  │  100.112.160.48           │ │
│  │ │ Executor │ │  │  classifier  │  │                           │ │
│  │ └──────────┘ │  │  controller  │  └───────────────────────────┘ │
│  │              │  │  listener    │                                 │
│  │  MCP Tools:  │  │  certifier   │                                │
│  │  Exa         │  │  nurturer    │                                │
│  │  Fireflies   │  │              │                                │
│  │  Gmail       │  │  8 Cron Jobs │                                │
│  │  Slack       │  │  (disabled)  │                                │
│  │  Calendar    │  │              │                                │
│  │  Drive       │  │  Telegram    │                                │
│  │  Chrome      │  │  Bot         │                                │
│  └──────────────┘  └──────────────┘                                │
│                                                                     │
└────────────────────────────┬────────────────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
     ┌──────────────┐ ┌───────────┐ ┌────────────┐
     │   Supabase   │ │  Vercel   │ │ External   │
     │              │ │           │ │ APIs       │
     │  targets     │ │ 317 HTML  │ │            │
     │  companies   │ │ pages     │ │ Lob        │
     │  contacts    │ │           │ │ (mail)     │
     │  pipeline_log│ │ /api/     │ │            │
     │  call_log    │ │ letters/  │ │ Salesfinity│
     │  meeting_    │ │ webhooks/ │ │ (dialer)   │
     │    notes     │ │           │ │            │
     │  campaign_   │ │ Auto-     │ │ Telegram   │
     │    batches   │ │ deploy on │ │ (notify)   │
     │  letter_     │ │ git push  │ │            │
     │    campaigns │ │           │ │ Exa        │
     │  call_       │ │           │ │ (search)   │
     │    outcomes  │ │           │ │            │
     └──────────────┘ └───────────┘ └────────────┘
```

---

## KEY DESIGN DECISIONS

1. **Operator narrative over PE finance speak** — Letters and pages sound like someone who built a business, not someone who buys them
2. **OpenClaw agents over custom Agent SDK** — Single orchestration platform, not a DIY framework
3. **Cheap models for volume, expensive for strategy** — DeepSeek/Gemini at <$0.30/M for autonomous research; Claude Opus only for architecture
4. **Local embeddings (Ollama) over cloud** — Zero marginal cost for vector search across transcripts and emails
5. **Hard governor (250/150) over soft limits** — Database constraints enforce discipline; no config toggle can override
6. **Single URL as the closer** — Every prospect gets one page that tells their company's story better than they could. That URL is the product.
7. **Hybrid file + database bridge** — Speed of local file reads with durability of Supabase persistence
8. **Telegram as primary control channel** — Ewing controls everything from his phone; decisions only, no noise

---

*System built by Ewing Gillaspy with Claude Code (Anthropic). Running on Mac Mini via OpenClaw v2026.3.28.*
