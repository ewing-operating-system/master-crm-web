# TIER 3 — SONNET TASKS
# Model: claude-sonnet-4-6
# Start with: export CLAUDE_CODE_DISABLE_1M_CONTEXT=1 && claude --model claude-sonnet-4-6
# Run AFTER Haiku tasks are complete (depends on H1, H2, H3 results)

These are config, wiring, and integration tasks. Need moderate reasoning for error recovery.

---

## Task S1: Configure ACP for main→researcher (from Decision 9)

```
Read ~/Projects/master-crm-web/SYSTEM-AUDIT-2026-03-29.md Section 3.5 for context.

Goal: Wire up ACP so the "main" agent can send structured messages to the "researcher" agent in real-time instead of writing files.

Steps:
1. Read ~/.openclaw/openclaw.json — find the agents section and gateway config
2. Read ~/.openclaw/workspace/AGENTS.md — understand current agent communication patterns
3. Enable ACP on the gateway if not already:
   openclaw acp server start
4. Configure main agent to use ACP for outbound:
   openclaw acp configure --agent main --mode client
5. Configure researcher agent to listen for ACP messages:
   openclaw acp configure --agent researcher --mode server
6. Test with a ping:
   openclaw acp client --session agent:main:main --message '{"action": "ping"}'
7. Verify researcher received it:
   openclaw acp logs --agent researcher --last 5

If any command doesn't exist or fails, read "openclaw acp --help" and adapt. Show me what you did differently.

Do NOT touch the validator, executor, or auditor agents yet.
```

---

## Task S2: Create Hybrid Bridge — File Layer (from Decisions 1-2)

```
Goal: Create the shared-state.json file that both Claude Code and OpenClaw read/write.

Steps:
1. Create the shared state file:
   Write ~/.openclaw/workspace/shared-state.json with this structure:
   {
     "version": 1,
     "last_updated": "<ISO timestamp>",
     "last_updated_by": "claude-code",
     "pipeline": {
       "status": "idle",
       "targets_researching": 0,
       "targets_validated": 0,
       "targets_queued_outreach": 0,
       "last_batch_pull": null,
       "last_error": null
     },
     "decisions": [],
     "alerts": []
   }

2. Add a Claude Code hook (PostToolUse) that writes pipeline-relevant decisions to this file.
   Edit ~/.claude/settings.json — add to the hooks section:
   {
     "PostToolUse": [
       {
         "matcher": "",
         "hooks": [
           {
             "type": "command",
             "command": "if [ -f ~/.openclaw/workspace/shared-state.json ]; then python3 -c \"import json,datetime; f=open('$HOME/.openclaw/workspace/shared-state.json','r+'); d=json.load(f); d['last_updated']=datetime.datetime.now().isoformat(); d['last_updated_by']='claude-code'; f.seek(0); json.dump(d,f,indent=2); f.truncate(); f.close()\"; fi"
           }
         ]
       }
     ]
   }

3. Verify the hook works by running any bash command, then check:
   cat ~/.openclaw/workspace/shared-state.json
   The last_updated timestamp should be fresh.

4. Add a note to ~/.openclaw/workspace/HEARTBEAT.md telling the heartbeat to read shared-state.json:
   Append: "5. Read ~/.openclaw/workspace/shared-state.json — report any alerts or errors to Telegram"
```

---

## Task S3: Create Hybrid Bridge — Supabase Layer (from Decisions 1-2)

```
Goal: Create a shared_state table in the existing master-crm Supabase instance for durable state that survives restarts.

Steps:
1. Read ~/.openclaw/.env to get the Supabase URL and service role key for dwrnfpjcvydhmhnvyzov (master-crm)

2. Create the table via Supabase API:
   curl -X POST '<SUPABASE_URL>/rest/v1/rpc/exec_sql' \
     -H 'apikey: <SERVICE_ROLE_KEY>' \
     -H 'Authorization: Bearer <SERVICE_ROLE_KEY>' \
     -H 'Content-Type: application/json' \
     -d '{"query": "CREATE TABLE IF NOT EXISTS shared_state (id serial primary key, key text unique not null, value jsonb not null, updated_at timestamptz default now(), updated_by text not null);"}'

   If the RPC method doesn't work, use the Supabase CLI or dashboard SQL editor instead.

3. Insert initial state rows:
   curl -X POST '<SUPABASE_URL>/rest/v1/shared_state' \
     -H 'apikey: <SERVICE_ROLE_KEY>' \
     -H 'Authorization: Bearer <SERVICE_ROLE_KEY>' \
     -H 'Content-Type: application/json' \
     -H 'Prefer: resolution=merge-duplicates' \
     -d '[
       {"key": "pipeline_status", "value": {"status": "idle", "last_batch": null}, "updated_by": "setup"},
       {"key": "last_bridge_sync", "value": {"timestamp": null, "direction": null}, "updated_by": "setup"},
       {"key": "active_alerts", "value": {"alerts": []}, "updated_by": "setup"}
     ]'

4. Verify:
   curl '<SUPABASE_URL>/rest/v1/shared_state?select=*' \
     -H 'apikey: <SERVICE_ROLE_KEY>'

5. Report what was created.

Ask me before running any destructive queries. This is a production database.
```

---

## Task S4: Convert system-tuner to OpenClaw Sub-Agent (from Decisions 3-4)

```
Goal: Move the system-tuner from a Claude Code skill to an OpenClaw sub-agent that runs on schedule.

Steps:
1. Read ~/.claude/skills/system-tuner/SKILL.md — understand what it does
2. Read ~/.openclaw/openclaw.json — understand agent config format

3. Create the sub-agent:
   openclaw agents create system-tuner \
     --model deepseek/deepseek-chat \
     --workspace ~/.openclaw/workspace-system-tuner \
     --description "Weekly health check: OpenClaw status, cron jobs, channel health, credentials, Supabase, git repos"

4. Create the workspace and identity:
   mkdir -p ~/.openclaw/workspace-system-tuner
   Write ~/.openclaw/workspace-system-tuner/IDENTITY.md with the health check sequence from the SKILL.md

5. Create a cron job for it:
   openclaw cron create system-tuner-weekly \
     --agent system-tuner \
     --schedule "0 9 * * 1" \
     --message "Run weekly health check. Report results to Telegram. Only message Ewing if a decision is needed."

6. Verify:
   openclaw agents list
   openclaw cron list

Report what was created. Do not enable the cron job yet — I'll review first.
```

---

## Task S5: Upgrade Researcher Agent for Account + Buyer Research (Replaces cold-call-workflow)

```
Goal: Expand the existing OpenClaw researcher agent to focus on finding and researching new accounts, buyers, and targeting strategies. This is the #1 priority for Next Chapter's business.

Context: The researcher agent already exists (Gemini 2.5 Flash Lite, workspace at ~/.openclaw/workspace-researcher). We're upgrading its scope, not creating a new agent.

Steps:
1. Read ~/.openclaw/workspace-researcher/IDENTITY.md — understand current scope
2. Read ~/.openclaw/openclaw.json — find the researcher agent config

3. Update the researcher agent's IDENTITY.md to include this expanded scope:

   PRIMARY MISSION: Find and research new M&A target accounts and strategic buyers.

   RESEARCH WORKFLOW:
   a. Pull unresearched targets from Supabase (dwrnfpjcvydhmhnvyzov, targets table, status = 'NEW')
   b. For each target, run Exa search for:
      - Company overview (revenue, headcount, ownership structure, industry vertical)
      - Recent news (acquisitions, funding, leadership changes, expansions)
      - Competitive landscape (who else is in their market)
      - Key decision-makers (CEO, CFO, VP Corp Dev, board members)
   c. Run Clay enrichment for decision-maker contacts:
      - Direct phone numbers
      - Business email addresses
      - LinkedIn profiles
      - Title and tenure
   d. Build a buyer targeting profile:
      - Why would this buyer acquire in this vertical?
      - What's their acquisition history?
      - What's their estimated dry powder / capacity?
      - How to approach them (warm intro path, cold outreach angle, story hook)
   e. Score targeting fit (1-100) based on:
      - Strategic fit with seller's vertical
      - Financial capacity
      - Acquisition track record
      - Geographic proximity
      - Cultural alignment signals
   f. Write structured dossier back to Supabase (status → 'RESEARCHED')
   g. Send to validator agent for cross-check

   NOT IN SCOPE:
   - Open/active opportunities (they are current, don't need external research)
   - Deal monitoring on existing pipeline
   - Internal file gathering (that's CRM work, not research)

   QUALITY RULES:
   - Zero fabrication. If you can't find data, say "NOT FOUND" — never guess.
   - Every fact must have a source URL.
   - Buyer profiles must include acquisition history or explicitly state "No acquisitions found."

4. Update the cron schedule to run every 2 hours during business hours:
   openclaw cron update research-loop \
     --schedule "0 8,10,12,14,16,18 * * 1-5" \
     --message "Process next batch of unresearched targets. Research new accounts and buyers. Write results to Supabase."

5. Verify:
   openclaw agents list
   cat ~/.openclaw/workspace-researcher/IDENTITY.md
   openclaw cron list

Report what was changed. Do not enable the cron job yet.
```

---

## After all tasks: Report back with this format

```
S1 ACP main→researcher: [DONE/FAILED] — [summary]
S2 Bridge file layer: [DONE/FAILED] — [summary]
S3 Bridge Supabase layer: [DONE/FAILED] — [summary]
S4 system-tuner sub-agent: [DONE/FAILED] — [summary]
S5 researcher agent upgrade: [DONE/FAILED] — [summary]
```
