# Meeting Transcript System — Product & Engineering Spec

> **Owner:** Ewing Gillaspy / Next Chapter  
> **Built:** 2026-04-01  
> **Status:** Live (media playback pending Fireflies MCP auth)  
> **Production URL:** `https://master-crm-web-eight.vercel.app/meetings/`

---

## 1. WHAT THIS IS

An automated pipeline that captures Fireflies.ai meeting transcripts, extracts actionable business intelligence via Claude, and generates interactive static HTML pages with:

- Full speaker-annotated transcript with per-speaker color coding
- Embedded video/audio player with click-to-seek (click any utterance, playback jumps to that moment)
- AI-extracted learnings sidebar with one-click Agree/Reject approval
- Approved learnings write directly back to Supabase (dossier_final, targets, contacts)
- Multi-entity association (a meeting about HR.com tags both `hrcom` and `next_chapter`)

**Why it matters:** Every client meeting generates 10-20 actionable data points that previously died in notes. This system captures them structurally, routes them to the correct entity, and lets the team approve them into the CRM with one click.

---

## 2. ARCHITECTURE

```
Fireflies.ai (recordings)
    │
    ▼ (Claude CLI → Fireflies MCP tools)
meeting_pages.py (local Python, runs on cron)
    │
    ├──► Supabase: meeting_transcripts (raw data, media URLs, entities)
    ├──► Supabase: meeting_learnings (14 learnings per meeting, per-entity)
    ├──► public/meetings/<id>.html (static page with baked-in video URLs)
    │
    ▼ (git push)
Vercel (serves static HTML)
    │
    ├── /api/meetings/approve-learning  (POST — approve/reject, write to target table)
    └── /api/meetings/media-url         (GET — fallback media URL lookup from Supabase)
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Static HTML, not SPA** | Matches existing site architecture. No build step. Instant deploy via git push. |
| **Media URLs baked into HTML** | Fireflies CDN URLs are signed CloudFront URLs that expire in ~3 days. Fetched fresh at generation time via MCP, baked into the page. Hourly cron refreshes. |
| **Learnings extracted locally** | Claude CLI runs on the Mac Mini, not on Vercel Lambda. Extraction happens during page generation, not at serve time. |
| **Multi-entity association (Model C)** | A meeting about HR.com involves both `hrcom` (the client) and `next_chapter` (the advisor). Both entities get tagged. Each learning gets routed to its specific entity. |
| **Approve/reject, not auto-write** | AI extractions aren't always right. Human review via sidebar buttons ensures data quality before writing to CRM tables. |

---

## 3. DATABASE SCHEMA

### `meeting_transcripts`

```sql
CREATE TABLE meeting_transcripts (
    id                UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    fireflies_id      TEXT UNIQUE NOT NULL,
    title             TEXT,
    date              TIMESTAMPTZ,
    duration_minutes  INTEGER,
    audio_url         TEXT,           -- JSON: {"audio": "signed_url", "video": "signed_url"}
    transcript_json   JSONB,          -- Full utterance array from Fireflies
    participants      JSONB,          -- Speaker list with roles
    entities          TEXT[] DEFAULT '{}',  -- e.g. {next_chapter, hrcom}
    status            TEXT DEFAULT 'pending',  -- pending → extracted
    summary           TEXT,
    action_items      JSONB,
    page_path         TEXT,           -- e.g. meetings/01KN3D8S57CX196DC5C6MZ8YHB.html
    created_at        TIMESTAMPTZ DEFAULT now(),
    updated_at        TIMESTAMPTZ DEFAULT now()
);
```

### `meeting_learnings`

```sql
CREATE TABLE meeting_learnings (
    id                  UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    transcript_id       UUID REFERENCES meeting_transcripts(id) ON DELETE CASCADE,
    entity              TEXT NOT NULL,       -- Which entity this learning belongs to
    category            TEXT,                -- budget, competitive, timeline, requirement, etc.
    learning            TEXT NOT NULL,       -- The extracted insight
    confidence          FLOAT,              -- 0.0–1.0
    target_table        TEXT,                -- Where to write if approved (e.g. dossier_final)
    target_column       TEXT,                -- Which column (e.g. prior_offers_range)
    target_value        TEXT,                -- The value to write
    transcript_timestamp TEXT,               -- When in the meeting this was said
    approved            BOOLEAN DEFAULT NULL, -- null=pending, true=approved, false=rejected
    approved_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT now()
);
```

---

## 4. FILES

| File | Lines | Purpose |
|------|-------|---------|
| `scripts/meeting_pages.py` | 1,301 | **Core pipeline.** Polls Fireflies, extracts learnings, generates HTML, commits/deploys. |
| `api/meetings/approve-learning.js` | 158 | **Vercel serverless.** Approve/reject learnings, write to target Supabase tables. |
| `api/meetings/media-url.js` | 83 | **Vercel serverless.** Fallback media URL lookup from Supabase (when baked URLs expire). |
| `public/meetings/*.html` | ~1,300 each | **Generated pages.** One per meeting. Static HTML with embedded JS player. |

### `meeting_pages.py` — Key Functions

| Function | What It Does |
|----------|-------------|
| `fetch_recent_transcripts(hours)` | Calls Fireflies MCP via Claude CLI to get recent transcripts |
| `fetch_media_urls(fireflies_id)` | Gets fresh signed audio/video CDN URLs from Fireflies MCP |
| `extract_learnings(transcript_row)` | Sends transcript to Claude for business intelligence extraction |
| `process_transcript(fireflies_id)` | Full pipeline: fetch → store → extract → generate → commit |
| `generate_meeting_page(transcript_row, learnings)` | Builds complete HTML page with video player, transcript, sidebar |
| `detect_entities(transcript_row)` | Maps participants/title to known CRM entities |
| `run_poll(hours)` | Cron mode: check for new meetings in last N hours |
| `run_rebuild()` | Regenerate all pages, refresh media URLs |

---

## 5. API ENDPOINTS

### `POST /api/meetings/approve-learning`

Approves or rejects a learning. If approved and target fields are set, writes the value to the target Supabase table.

```json
// Request
{ "learning_id": "uuid", "approved": true }

// Response
{
    "success": true,
    "learning_id": "uuid",
    "approved": true,
    "target_write": { "written": true }
}
```

**Safety:** Only writes to allowlisted tables: `dossier_final`, `buyer_contacts`, `targets`, `contacts`.

### `GET /api/meetings/media-url?id=<fireflies_id>`

Returns cached media URLs from Supabase. Fallback for when baked-in HTML URLs expire.

```json
// Response
{
    "audio_url": "https://cdn.fireflies.ai/...",
    "video_url": "https://cdn.fireflies.ai/...",
    "transcript_url": "https://app.fireflies.ai/view/<id>"
}
```

---

## 6. HTML PAGE FEATURES

Each generated meeting page (`public/meetings/<fireflies_id>.html`) includes:

### Header
- Meeting title, date, duration
- Participant list with roles
- Entity tags (color-coded pills)

### Video/Audio Player
- HTML5 `<video>` element with signed CloudFront CDN URLs
- Play/pause, volume, progress bar
- Falls back to audio-only if no video URL
- Falls back to Fireflies app link if no media at all

### Transcript Panel (left side, ~65% width)
- Full speaker-annotated transcript
- Per-speaker color coding (consistent colors per speaker across the page)
- Timestamp on each utterance
- **Click-to-seek:** Click any utterance → video jumps to that timestamp and plays
- Auto-scroll: as video plays, transcript highlights and scrolls to current utterance
- Uses `getBoundingClientRect()` for reliable scroll positioning

### Learnings Sidebar (right side, ~35% width)
- AI-extracted business learnings as cards
- Each card shows: entity tag, category, learning text, confidence score
- **Agree** button (green) → marks approved, writes to target table if configured
- **Reject** button (red) → marks rejected, no write
- Entity filter buttons to show/hide learnings by entity
- Visual feedback on approve/reject (card styling changes)

### Technical Details
- No framework dependencies — vanilla HTML/CSS/JS
- `<script src="/supabase-config.js"></script>` for Supabase credentials
- Video `loadedmetadata` event gates playback (prevents race condition)
- `video.play().catch(() => {})` handles autoplay policy gracefully
- Responsive layout collapses to stacked on mobile

---

## 7. CRON SCHEDULE

```
0 9-17 * * *  source ~/.zshrc && python3 scripts/meeting_pages.py --poll --hours=2
```

- Runs hourly from 9am to 5pm (business hours)
- Checks Fireflies for meetings in the last 2 hours
- Generates pages for any new transcripts
- Auto-commits and pushes to git (triggers Vercel deploy)
- Logs to `logs/meeting_pages.log`

---

## 8. ENTITY DETECTION

Meetings are tagged with ALL entities involved (Model C — dual association):

```python
KNOWN_ENTITIES = {
    "revsup.com": "revsup",
    "hr.com": "hrcom",
    "aquascience": "aquascience",
    "springer": "springer",
    "air control": "aircontrol",
    "design precast": "designprecast",
    "wieser": "wieser",
    "next chapter": "next_chapter",
    "and capital": "and_capital",
    "ewing gillaspy": "next_chapter",
    "mark dechant": "next_chapter",
    "john kelly": "next_chapter",
}
```

Detection scans participant names, email domains, and meeting title. Each extracted learning gets its own `entity` field based on content relevance — a learning about HR.com's valuation gets `entity: hrcom`, a learning about NC's deal strategy gets `entity: next_chapter`.

---

## 9. LEARNING EXTRACTION

Claude analyzes the full transcript and extracts structured learnings. Each learning includes:

| Field | Example |
|-------|---------|
| `entity` | `hrcom` |
| `category` | `budget`, `competitive`, `timeline`, `requirement`, `objection`, `decision_maker`, `next_step`, `pain_point`, `relationship` |
| `learning` | "Previous offers ranged from $5M to $45M for the full business" |
| `confidence` | `0.95` |
| `target_table` | `dossier_final` |
| `target_column` | `prior_offers_range` |
| `target_value` | "$5M-$45M (domain + media + community, not domain-only)" |

The first meeting (HR.com Proposal Review) extracted **14 learnings** across 9 categories, split between `hrcom` (11) and `next_chapter` (3).

---

## 10. CURRENT STATE

### What's Live
- Pipeline: polls Fireflies, extracts learnings, generates pages, deploys to Vercel
- First meeting page: [HR.com Proposal Review with Debbie](https://master-crm-web-eight.vercel.app/meetings/01KN3D8S57CX196DC5C6MZ8YHB.html)
- Approve/reject API: working (first learning approved and written to `dossier_final.prior_offers_range`)
- Cron: running hourly 9am-5pm
- Hub page link: HR.com hub has "Meeting Transcripts" section with link to transcript page

### What Needs Attention
| Item | Status | Fix |
|------|--------|-----|
| Video/audio playback | URLs are null | Fireflies MCP needs OAuth re-auth. Run `/mcp` → select Fireflies → authenticate → `python3 scripts/meeting_pages.py --rebuild` |
| Hub page integration for other entities | Not started | As meetings are generated for other clients, add "Meeting Transcripts" sections to their hub pages |
| Media URL refresh | Designed, not tested | CDN URLs expire ~3 days. Hourly cron calls `fetch_media_urls()` during `--rebuild`. Fallback API reads from Supabase. |

### Data in Production

| Table | Records | Notes |
|-------|---------|-------|
| `meeting_transcripts` | 1 | HR.com Proposal Review (34 min, 4 speakers) |
| `meeting_learnings` | 14 | 11 hrcom + 3 next_chapter, 1 approved |

---

## 11. OPERATIONS PLAYBOOK

### Add a new meeting manually
```bash
python3 scripts/meeting_pages.py --generate <fireflies_id>
```

### Rebuild all pages (refresh media URLs)
```bash
python3 scripts/meeting_pages.py --rebuild
```

### Check cron is running
```bash
crontab -l | grep meeting
tail -20 logs/meeting_pages.log
```

### Debug a failed extraction
```bash
# Check Supabase for the transcript status
psql "$DATABASE_URL" -c "SELECT fireflies_id, status FROM meeting_transcripts WHERE status != 'extracted';"

# Check logs
grep ERROR logs/meeting_pages.log | tail -20
```

### Verify Fireflies MCP connection
```bash
claude mcp list 2>&1 | grep -i fireflies
```

If it shows only `authenticate` tool, run `/mcp` in Claude Code and re-authenticate.

---

## 12. DEPENDENCIES

| Service | Role | Cost | Notes |
|---------|------|------|-------|
| Fireflies.ai | Meeting recording + transcription | Existing subscription | MCP integration via Claude CLI |
| Claude CLI | Learning extraction + MCP bridge | Included in Max plan | Runs locally on Mac Mini |
| Supabase | Data storage | Existing instance | `dwrnfpjcvydhmhnvyzov` |
| Vercel | Static hosting + API | Existing project | `master-crm-web-eight.vercel.app` |

**No new services or signups were created for this system.**

---

## 13. COMMITS

| Hash | Message |
|------|---------|
| `9fcfc50` | Fix meeting video player: read media URLs from Supabase, not Claude CLI |
| Earlier today | Meeting transcript system: pipeline, pages, API endpoints, cron, hub integration, portal gating removal, RevsUp client addition |

---

## 14. FUTURE ENHANCEMENTS

1. **Auto-link to hub pages** — When a new meeting page is generated, automatically add it to the relevant entity hub page's Meeting Transcripts table
2. **Batch learning review** — "Approve All" button for high-confidence learnings (>0.9)
3. **Meeting search** — Index page at `/meetings/` listing all meetings with filters by entity, date, participant
4. **Follow-up tracking** — Extract action items and create follow-up tasks, track completion
5. **Competitive intelligence roll-up** — Aggregate `competitive` category learnings across meetings into a buyer intelligence view
