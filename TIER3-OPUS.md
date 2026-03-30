# TIER 3 — OPUS TASKS
# Model: claude-opus-4-6
# Start with: export CLAUDE_CODE_DISABLE_1M_CONTEXT=1 && claude --model claude-opus-4-6
# Run AFTER Sonnet tasks are complete (depends on S1-S5 results)

These are architecture tasks that require deep reasoning, design decisions, and cross-system understanding.

---

## Task O1: Design Vector Search Ingestion Pipeline (from Decisions 7-8)

```
Read ~/Projects/master-crm-web/SYSTEM-AUDIT-2026-03-29.md Section 3.4 for context.

Prerequisites: Chroma is running on localhost:8000, Ollama has nomic-embed-text.

Goal: Design AND implement the ingestion pipeline that pulls from Fireflies, Slack, and Gmail into Chroma.

Steps:
1. Read the MCP tools available for each source:
   - Fireflies: fireflies_get_transcripts, fireflies_get_transcript
   - Slack: slack_search_public_and_private
   - Gmail: gmail_search_messages, gmail_read_message

2. Design the chunking strategy:
   - Fireflies: One chunk per speaker turn. Include metadata: meeting_id, speaker, timestamp, meeting_title
   - Slack: One chunk per thread. Include metadata: channel, thread_ts, participants
   - Gmail: One chunk per message. Include metadata: from, to, date, subject, thread_id
   - Skip any Fireflies transcript with <80% confidence score (bad audio = bad embeddings)

3. Write a Python script: ~/.openclaw/scripts/vector-ingest.py
   The script should:
   a. Connect to Chroma (localhost:8000)
   b. Create 3 collections: fireflies_transcripts, slack_threads, gmail_messages
   c. For each source: fetch recent items (last 24 hours), chunk, embed via Ollama, store
   d. Track what's already been ingested (use a local SQLite DB at ~/.openclaw/vector-ingest-state.db)
   e. Log results to stdout

4. Write a Chroma MCP server config for Claude Code so it can search:
   Add to ~/.claude/settings.json under mcpServers:
   {
     "chroma-search": {
       "command": "python3",
       "args": ["-m", "chromadb.mcp_server", "--host", "localhost", "--port", "8000"]
     }
   }
   NOTE: Verify this MCP server package exists first. If not, write a simple custom MCP server that wraps Chroma search.

5. Create an OpenClaw cron job for nightly ingestion:
   openclaw cron create vector-ingest-nightly \
     --agent researcher \
     --schedule "0 2 * * *" \
     --message "Run python3 ~/.openclaw/scripts/vector-ingest.py and report any errors to Telegram"

6. Test the full pipeline:
   - Run the ingest script manually
   - Search Chroma for a test query
   - Verify results include source attribution

Design first, show me the plan, then implement. This is the most complex task — take your time.

Problems to watch for (from the audit):
- Stale embeddings: Plan for monthly re-embedding
- Bad audio transcripts: Filter by confidence score
- Storage growth: Plan for 6-month auto-archive
- False matches: Always return source links so user can verify
```

---

## Task O2: Design ACP Expansion Plan (from Decision 9)

```
Prerequisites: S1 has wired main→researcher via ACP.

Goal: Design the full ACP mesh for all 5 agents. Do NOT implement yet — design only.

Steps:
1. Read the ACP logs from S1 (openclaw acp logs) — understand what worked
2. Read each agent's workspace IDENTITY.md to understand their communication patterns
3. Design the message schemas for each pair:

   main→researcher: {action: "research", target_id, source, priority}
   researcher→main: {action: "research_complete", target_id, intel: {}, confidence}
   main→validator: {action: "validate", target_id, research_data}
   validator→main: {action: "verdict", target_id, result: "APPROVED|NEEDS_REVIEW|REJECTED", reason}
   main→executor: {action: "generate", target_id, template, data}
   executor→main: {action: "document_ready", target_id, path, format}
   main→auditor: {action: "audit", scope, target_files}
   auditor→main: {action: "audit_complete", findings: [], preservation_requirements: []}

4. Design the error handling:
   - What happens when an agent doesn't respond in 5 minutes?
   - What happens when validator returns REJECTED?
   - What happens when the gateway restarts mid-conversation?

5. Design the fallback:
   - If ACP fails, agents should fall back to file-based communication
   - How do you detect ACP is down?

6. Write the full plan to ~/Projects/master-crm-web/ACP-EXPANSION-PLAN.md

Do not implement. This plan will be handed to Sonnet for execution in a future session.
```

---

## Task O3: Review and Approve Sub-Agent Configs (from S4 + S5)

```
Prerequisites: S4 and S5 created system-tuner and cold-call sub-agents.

Goal: Review the sub-agent configurations for correctness, completeness, and stability before enabling.

Steps:
1. Read ~/.openclaw/workspace-system-tuner/IDENTITY.md
2. Read ~/.openclaw/workspace-cold-call/IDENTITY.md
3. Read the cron job configs: openclaw cron list --verbose

For each sub-agent, evaluate:
- Is the IDENTITY.md complete? Does it have clear instructions?
- Is the model choice appropriate? (DeepSeek for system-tuner, GPT-4o Mini for cold-call)
- Is the cron schedule right? (Weekly Monday 9am for tuner, daily M-F 6am for cold-call)
- What could go wrong? List failure modes.
- What should the Telegram notification look like? Draft a template.

4. Make any corrections needed to IDENTITY.md or cron configs
5. If everything looks good, enable both:
   openclaw cron enable system-tuner-weekly
   openclaw cron enable cold-call-morning
6. Send a test message to Telegram confirming both are active:
   openclaw acp client --session agent:main:main --message '{"action": "notify", "text": "system-tuner and cold-call agents are live. Weekly health check: Monday 9am. Daily cold-call pull: M-F 6am."}'

Report your review findings and any changes made.
```

---

## After all tasks: Report back with this format

```
O1 Vector pipeline: [DONE/FAILED] — [summary]
O2 ACP expansion plan: [DONE/FAILED] — [summary]
O3 Sub-agent review: [DONE/FAILED] — [summary]
```
