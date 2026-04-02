# Master Orchestration Checklist

> Single source of truth for system synchronization.
> This file is read by the 6AM daily audit and by every agent that needs to understand the system.
> Last verified: 2026-04-01

---

## 1. PRODUCTION SCORECARD

### Repositories

| Repo | Purpose | Status | URL |
|------|---------|--------|-----|
| `master-crm-web` | All code, pages, API routes, backend, scripts | **ACTIVE** | github.com/ewing-operating-system/master-crm-web |
| `master-crm` | OLD repo — replaced by master-crm-web | **ARCHIVED** | github.com/ewing-operating-system/master-crm |
| `aegis` | Security/infrastructure tooling | **ACTIVE** | github.com/ewing-operating-system/aegis |
| `sunshine-code-forge` | Code generation experiments | **ACTIVE** | github.com/ewing-operating-system/sunshine-code-forge |
| `recording-library` | Call recordings archive | **ACTIVE** | github.com/ewing-operating-system/recording-library |

**Rule:** All CRM work happens in `master-crm-web`. No other repo should contain CRM logic, keys, or Supabase references.

### Supabase

| Instance | Project ID | Status | Purpose |
|----------|-----------|--------|---------|
| Master CRM | `dwrnfpjcvydhmhnvyzov` | **LIVE** | All entities, all data |

**Rule:** ONE instance. Never create new Supabase projects. Every table gets an `entity` column (except `do_not_call` which is universal).

### Vercel

| Setting | Value |
|---------|-------|
| Project | `master-crm-web` |
| Production URL | `master-crm-web-eight.vercel.app` |
| Output directory | `public` |
| Build command | `echo 'Static site - no build needed'` |
| Functions | `api/**/*.js` (30s max duration) |

**Env vars required (17):**
```
SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ANON_KEY, DATABASE_URL,
OPENROUTER_API_KEY, EXA_API_KEY, LOB_API_KEY, LOB_WEBHOOK_SECRET,
LOB_FROM_NAME, LOB_FROM_ADDRESS, LOB_FROM_CITY, LOB_FROM_STATE, LOB_FROM_ZIP,
BATCH_SEND_SECRET, SALESFINITY_API_KEY, PORTAL_PW_ADMIN, PORTAL_PW_HRCOM
```

**Deprecated (remove after confirming deploy works):** `SUPABASE_SERVICE_KEY`

---

## 2. CREDENTIAL ARCHITECTURE

### Source of Truth: `~/.zshrc`

All 22 env vars are exported in `~/.zshrc`. Every process on this machine inherits them.

```
SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_DB_PASSWORD,
DATABASE_URL, OPENROUTER_API_KEY, DEEPSEEK_API_KEY, OPENAI_API_KEY,
MISTRAL_API_KEY, TOGETHER_API_KEY, EXA_API_KEY, GOOGLE_API_KEY, GOOGLE_CX,
GOOGLE_MAPS_API_KEY, CLAY_API_KEY, LOB_SECRET_KEY, LOB_PUBLISHABLE_KEY,
SALESFINITY_API_KEY, TELEGRAM_BOT_TOKEN, EWING_TELEGRAM_CHAT_ID,
EWING_CLAW_BOT_TOKEN, GATEWAY_AUTH_TOKEN
```

### How Each Layer Gets Keys

| Layer | Method | Notes |
|-------|--------|-------|
| Python scripts | `os.environ.get("VAR", "")` | Empty fallback, never raw keys |
| Node.js (Vercel) | `process.env.VAR` | Vercel injects at runtime |
| Frontend JS | `window.__SUPABASE_URL` | From `public/supabase-config.js` |
| OpenClaw gateway | `~/.openclaw/.env` | LaunchAgent reads this at boot |
| Cron jobs | `source ~/.zshrc` | Prefix in crontab |
| Claude Code | Inherits from shell | Automatic |

### Prevention

- **Pre-commit hook** blocks patterns: `eyJhbGciOi`, `MakeMoneyNow`, `sk-or-v1-`, `sk-proj-`, `sk-ant-api`, `sk-ea0`, `2LU38CRB`, `tgp_v1_`, `AIzaSy`, `f1f16b33`
- **Allowlist:** `public/supabase-config.js` (anon key is intentionally public)
- **Audit command:**
  ```bash
  grep -rn 'eyJhbGciOi\|MakeMoneyNow\|sk-or-v1\|sk-ea0\|2LU38\|sk-proj-\|tgp_v1\|AIzaSy\|f1f16b33' \
    --include='*.py' --include='*.js' --include='*.md' --include='*.sh' \
    --exclude-dir=node_modules --exclude='supabase-config.js' \
    ~/Projects/master-crm-web/ ~/.openclaw/ ~/.claude/skills/ 2>/dev/null
  ```

---

## 3. NORTH STAR DOCUMENTS

Where agents go to understand the business:

| Document | Location | What It Defines |
|----------|----------|----------------|
| NC Lifecycle Vision | `backend/data/north-star/NORTH-STAR-nc-lifecycle-vision.md` | 8-stage pipeline, 6 engines needed |
| Entity Classification | `backend/data/north-star/NORTH-STAR-entity-classification-guide.md` | Who is NC/AND/RU, decision trees |
| Infrastructure Map | `backend/data/north-star/NORTH-STAR-infrastructure-map.md` | Where everything lives, what's retired |
| Operating Philosophy | `backend/data/north-star/NORTH-STAR-operating-philosophy.md` | Feedback loops, 5 principles |
| Founder Guardrails | `backend/data/north-star/NORTH-STAR-founder-guardrails.md` | 13 non-negotiable rules |

**Rule:** The canonical copies live in `master-crm-web/backend/data/north-star/`. No other copies should exist.

---

## 4. CONTEXT SOURCES

How an agent or developer gets up to speed:

| Need | Read This |
|------|-----------|
| System architecture | `CLAUDE.md` (repo root) |
| Backend details | `docs/CLAUDE-backend.md` |
| Env var names | `.env.example` |
| Portal auth | `lib/portal-config.js` |
| Letter pipeline | `docs/LETTER-TEMPLATE-ENGINE-EXECUTION.md` |
| Page system | `docs/page-system-v2-architecture.md` |
| Meeting pages | `docs/MEETING-PAGE-V2-SPEC.md` |
| Recent work | `docs/CURRENT-BUILD-STATE.md` |
| Buyer scoring | `CLAUDE.md` section "BUYER SCORING" |

---

## 5. RUNNING SERVICES

### Always On (LaunchAgents)

| Service | Plist | Port | Purpose |
|---------|-------|------|---------|
| OpenClaw Gateway | `ai.openclaw.gateway.plist` | 18789 | Telegram bot, agent orchestration |
| Ollama | `homebrew.mxcl.ollama.plist` | 11434 | Local LLM inference (Mistral Small) |
| Tailscale | `homebrew.mxcl.tailscale.plist` | — | VPN mesh network |

### Cron Jobs

| Schedule | Script | Purpose |
|----------|--------|---------|
| `*/30 * * * *` | `classify_all_targets.js` | Entity classification |
| `*/15 * * * *` | `sync_call_intel.py --mode=poll` | Call intel polling |
| `0 6 * * *` | `sync_call_intel.py --mode=sync` | Full daily call sync |
| `0 6 * * *` | `morning_audit.py` | **Daily system audit (THIS CHECKLIST)** |

### OpenClaw Agents (10)

| Agent | Model | Role |
|-------|-------|------|
| main | DeepSeek Chat | Pipeline controller |
| researcher | Gemini 2.5 Flash Lite | Web research |
| validator | DeepSeek V3 | Fact verification |
| executor | GPT-4o Mini | Letter/script generation |
| auditor | DeepSeek V3 | System audit |
| controller | DeepSeek Chat | Pipeline flow |
| classifier | DeepSeek V3 | Entity classification |
| listener | Gemini Flash Lite | Channel monitoring |
| certifier | DeepSeek V3 | Data certification |
| nurturer | GPT-4o Mini | Relationship mgmt |

---

## 6. DAILY SYNC AUDIT (6AM)

### What Gets Checked

| Check | Pass Criteria | Severity |
|-------|--------------|----------|
| **Key hygiene** | Zero hardcoded keys in repo, skills, openclaw | CRITICAL |
| **Vercel env sync** | All 17 vars present, no deprecated vars | CRITICAL |
| **Supabase health** | REST API returns 200 | CRITICAL |
| **Data sync** | DB data matches pages, Vercel matches git, no stuck records | CRITICAL |
| **Gateway running** | PID exists, Telegram polling OK | HIGH |
| **Git clean** | No uncommitted changes in master-crm-web | HIGH |
| **Unpushed commits** | All local commits pushed; risky commits flagged | HIGH |
| **Cron health** | All 3 crons ran in last interval | HIGH |
| **Ollama running** | Port 11434 responding | MEDIUM |
| **OpenClaw version** | Running latest version | MEDIUM |
| **Disk usage** | < 80% on all volumes | MEDIUM |
| **Stale files** | No .bak, .backup, .old config files | LOW |
| **Skill suggestions** | Log repetitive processes for skill creation | INFO |

### What Gets Fixed

The audit script **documents findings only**. Fixes follow this chain:

```
morning_audit.py (OpenClaw/DeepSeek)
  → documents findings to public/system-health.html
  → writes fix plan to /tmp/morning-fixes.json

claude -p "Read /tmp/morning-fixes.json. Decide what to fix." --model opus  (Opus 4.6)
  → produces fix instructions

claude -p "Implement these fixes: ..." --model sonnet  (Sonnet 4.6)
  → executes changes, commits, pushes
```

### Skill-Watch

The audit also watches for:
- Commands run > 3 times in the last week that aren't already skills
- Scripts called from multiple places that could be consolidated
- Patterns in conversation history suggesting repeatable workflows

These get logged to the system health page under "Suggested Skills".

---

## 7. FILE LOCATIONS QUICK REFERENCE

```
~/Projects/master-crm-web/          # THE repo (code, pages, API, backend)
  CLAUDE.md                         # Master agent instructions
  .env.example                      # Canonical env var list
  .git/hooks/pre-commit             # Key leak prevention
  public/supabase-config.js         # Frontend Supabase config (anon key)
  public/system-health.html         # Daily audit findings page
  backend/data/north-star/          # Business vision documents
  scripts/morning_audit.py          # Daily 6AM audit script

~/.zshrc                            # All API keys (source of truth)
~/.openclaw/.env                    # Gateway runtime credentials
~/.openclaw/openclaw.json           # Agent fleet configuration
~/.openclaw/cron/jobs.json          # OpenClaw scheduled tasks
~/.openclaw/workspace/              # Agent workspace scripts
~/.claude/skills/                   # 23 installed skills
~/.claude/CLAUDE.md                 # Global Claude Code instructions
~/Library/LaunchAgents/             # macOS background services
```
