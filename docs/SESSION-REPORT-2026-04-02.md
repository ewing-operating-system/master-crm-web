# Session Report: Cross-Domain CRM Overhaul Analysis

**Date:** 2026-04-02
**Session:** Claude Code (Argus) + Ewing Gillaspy
**Branch:** main

---

## Table of Contents

1. [Prompt Dissection — Good, Bad, and Horrendous](#1-prompt-dissection)
2. [Claude Code vs Claude Desktop Routing](#2-code-vs-desktop)
3. [Revised Prompt (Concise Version)](#3-revised-prompt)
4. [Tools, Skills, and Plugins Audit](#4-tools-audit)
5. [Prompt-Refiner Comparison](#5-prompt-refiner-comparison)
6. [Comprehensive Overhaul Plan](#6-overhaul-plan)
7. [Next Steps](#7-next-steps)

---

## 1. Prompt Dissection

Your original prompt was broken into 8 logical blocks and graded.

### Block 1: The Request Frame

> "Turn this into a plan. Make it comprehensive and detailed. I'm going to take it over to claude desktop to analyze further. Instruct me whether to use Claude code or claude cowork based on what I want to do."

**Grade: GOOD.** Clear deliverable (plan), clear destination (Claude Desktop), clear decision needed (Code vs Cowork). One fix: the tool choice question should come AFTER the problem statement, not before, because the reasoning depends on what follows.

### Block 2: The Strategic Problem

> "Here is the major gap that I see - we have many types of clients, and several companies to work through. We have ONLY worked on Home services to get started and build something and get our feet under us. Now we have a soon to be signed agreement with an HR media company that came inbound to us by way of referral."

**Grade: GOOD.** Essential context. You're telling me WHY this matters NOW -- there's a real deal forcing the issue. This is the "why" that most prompts lack entirely.

### Block 3: The Agent Architecture Vision

> "I need to work diligently with either code or cowork to refine the agent and method to be cross-domain. Some pieces (swarm of agents to certify accuracy) are good for broad application... and some clients require very specific research and more importantly, very bespoke matching of research to client, in this case matching pains, vision, and opportunity of the acquirer to the benefits provided by HR.com if acquired. This is the linkage that breaks the door open."

**Grade: MIXED.** The insight is brilliant -- the distinction between shared infrastructure (Exa, agent swarm, accuracy certification) and domain-specific logic (pain/gain matching, buyer-to-seller linkage) is the core architectural decision.

**Problem:** "This is the linkage that breaks the door open. This is the most important part of the exercise." -- you're selling me on why it matters, but I'm already working for you. Replace persuasion with specification. WHAT is the linkage? Define it: "For each buyer, match their stated pains/gaps to HR.com's specific capabilities that solve them. Output: a ranked list of talking points per buyer."

### Block 4: The Overhaul Declaration

> "We need a complete overhaul of a system that seems to be (poorly) designed and hard coded towards home services."

**Grade: GOOD but DANGEROUS.** You're right -- the system IS hard-coded to home services. But "complete overhaul" is a scope bomb. An AI will either (a) plan something so massive it never ships, or (b) ask 40 questions to narrow scope. Better: "Refactor the research pipeline to accept any vertical as config, not code."

### Block 5: The Domain Onboarding Example

> "Any vertical will have levers of growth, but ONLY the domain specific levers of growth matter to that client. If we were to represent a windows service company (new domain), we would need to kickoff a process to complete the overhead homework of that domain, get the multiples of ebitda to value the company, get the levers of growth..."

**Grade: EXCELLENT.** This is the best block in the prompt. You're defining a repeatable process by walking through a hypothetical. This gives the template:

1. Domain overhead homework (industry research)
2. EBITDA multiples for valuation
3. Levers of growth (domain-specific)
4. Transaction history
5. Buyer identification
6. Deep buyer research

This IS the onboarding spec. You should lead with this.

### Block 6: The Letter Pipeline Vision

> "Letter writing, for instance, is a tactic that is meant to take a formulaic input of the very research we have done, write a compelling letter that stands out... This should be a daily task that our users see every morning: Review and approve letters for xyz, click here to start... This allows the user to quickly validate in less than 3 minutes that everything they are looking at is justified and valid. This is the human hallucination audit."

**Grade: EXCELLENT but MISPLACED.** This is a complete product spec for the letter review UX. It's vivid, actionable, and buildable. But it's buried in paragraph 6 of a prompt about system architecture. This should be its own prompt, or a clearly delineated section.

### Block 7: The Anti-Pattern Statement

> "We can help you make this amazing. You just have to help us structure our engine in a way that doesn't lock us in and make every new client a brand new table structure, new python scripts, new supabase tables, new everything."

**Grade: HORRENDOUS FRAMING -- but 100% correct on the problem.** Here's why the framing hurts:

- "We can help you make this amazing" -- you're pitching me. I'm your tool, not your investor.
- "You just have to help us structure our engine" -- vague. WHICH engine? The Exa search pipeline? The Supabase schema? The page generation? The agent orchestration? All of them?
- "doesn't lock us in" -- this is a constraint, not a spec. Better: "One Supabase schema that handles any vertical. One Python script that takes a domain config and runs the full pipeline. One page template that renders any buyer research."

### Block 8: The Meta-Request

> "Your first task is to evaluate this prompt... Break it down... Audit all of my skills... Tell me everything wrong... Play it back revised... Run the /prompt-refiner skill..."

**Grade: GOOD concept, BAD execution.** You're asking for 6 deliverables in one paragraph. Stacking them creates a context bomb where later tasks get less attention because the model is exhausted from earlier ones. Better: number them explicitly and accept they'll come in sequence.

### Scorecard Summary

| Block | Topic | Grade | Issue |
|-------|-------|-------|-------|
| 1 | Request frame | Good | Tool choice asked before problem stated |
| 2 | Strategic problem | Good | Clean context |
| 3 | Agent architecture | Mixed | Insight strong, persuasion replaces specification |
| 4 | Overhaul declaration | Dangerous | "Complete overhaul" = scope bomb |
| 5 | Domain onboarding | Excellent | Best block -- defines the repeatable process |
| 6 | Letter pipeline | Excellent | Full product spec, but misplaced |
| 7 | Anti-pattern | Horrendous framing | Right problem, wrong format |
| 8 | Meta-request | Overloaded | 6 deliverables in 1 paragraph |

### The Three Biggest Problems

1. **Interleaving vision with specification with meta-requests.** A single prompt should do ONE of these: (a) describe a vision for alignment, (b) specify a deliverable for execution, or (c) request analysis/audit. Yours does all three simultaneously.

2. **Persuading instead of specifying.** Phrases like "this is the linkage that breaks the door open" and "we can help you make this amazing" are pitch language. Replace every persuasion sentence with a specification sentence.

3. **No priority stack.** You've described 6+ workstreams. Which one ships first? Without priority, the AI will either ask or guess wrong.

---

## 2. Claude Code vs Claude Desktop Routing

### Use Claude Code for:

- Running scripts, modifying Python/JS/HTML files, git operations
- Database queries, Exa searches, deploying to Vercel
- Building the traced research pipeline, fixing bugs, running batch jobs
- Anything that touches files on this machine

### Use Claude Desktop (Projects/Cowork) for:

- Analyzing plan documents
- Strategic architecture discussions (multi-vertical schema design)
- Reviewing trace documents and making methodology decisions
- Comparing research quality across agents
- Researching a new vertical's domain knowledge (levers of growth in HR media)
- Drafting narrative hooks and market context for a new vertical's letters
- Working with Gamma to create pitch decks from research

### The Handoff Pattern

Cowork produces the domain knowledge and strategic thinking. Code takes that output and puts it into the database/system.

**Example:** Cowork session produces "HR media levers of growth: employer brand reach, content library depth, audience demographics, event revenue, certification programs." Code session takes those and INSERTs them into the `vertical_knowledge` table with proper schema.

### For THIS specific task:

Start in Claude Code (here) to generate the plan, then take it to Claude Desktop to analyze, debate, and refine the architecture decisions. Come back to Code to implement.

---

## 3. Revised Prompt (Concise Version)

350 words. Same information as the original, zero waste, clear priority stack. Use this for Claude Code execution.

---

**Context:** Next Chapter is an M&A advisory CRM serving multiple verticals. We built the first version for home services (HVAC, plumbing). Now we have an inbound HR media deal (HR.com / Debbie McGrath) that exposed a critical problem: everything is hard-coded to home services -- research templates, Supabase tables, agent identities, buyer scoring, and output formats.

**Problem:** Every new client vertical currently requires new tables, new scripts, new agent configs, and new page templates. This doesn't scale. We need one engine that handles any vertical through configuration, not code.

**Deliverable:** A comprehensive implementation plan covering these 5 workstreams, in priority order:

**1. Multi-Vertical Domain Onboarding (highest priority)**
When a new client signs, the system should kick off a domain homework process:
- Industry EBITDA multiples and valuation benchmarks
- Domain-specific levers of growth (what makes companies in THIS vertical more valuable)
- Transaction history (recent M&A deals in this space)
- Buyer identification (50-100 potential acquirers, scored)
- Deep buyer research (per-buyer pages like we built for Debbie)

Define this as a config-driven pipeline, not a new codebase per client.

**2. Cross-Domain Research Engine**
Refactor `traced_buyer_run.py` and the Exa template system to accept a vertical config that defines: which research sections to run, which Exa search templates apply, which synthesis prompts to use, which buyer scoring criteria matter.

**3. OpenClaw Agent Sync**
Fix the disconnection between Claude Code and OpenClaw. Update SOUL.md and agent identities to be vertical-agnostic. Pass research methodology as task input, not workspace config. Use multiple agents to synthesize the same Exa results independently, then compare/merge.

**4. Letter Pipeline with Source Citation**
Letters generated from research. Review UX: letter text alongside source data for each claim, linked URLs, daily morning queue, 3-minute human hallucination audit.

**5. Schema Unification**
One Supabase schema for any entity and any vertical. No new tables per client -- use entity tags, vertical tags, and JSONB for domain-specific fields.

**Constraints:**
- Must work with existing Supabase instance (dwrnfpjcvydhmhnvyzov)
- Must produce traced audit docs (full, untruncated)
- Must support the 16-buyer HR.com batch run THIS WEEK
- OpenClaw API keys: OpenRouter works, DeepSeek/Groq are dead

---

## 4. Tools, Skills, and Plugins Audit

### MCP Tools Available (91 total)

#### Clay -- B2B Data Enrichment (10 tools)

| Tool | What It Does |
|------|-------------|
| find-and-enrich-company | Find and enrich a company by domain or LinkedIn URL |
| find-and-enrich-contacts-at-company | Search for contacts at a company by role, title, or department |
| find-and-enrich-list-of-contacts | Find and enrich specific named contacts |
| add-company-data-points | Add data points to companies in an existing search |
| add-contact-data-points | Add data points to contacts in an existing search |
| get-existing-search | Retrieve an existing search by task ID |
| get-my-accounts | Search Salesforce accounts synced to Clay |
| ask-question-about-accounts | Natural language questions about Salesforce accounts |
| get-credits-available | Check credit availability |
| track-event | Track analytics event with properties |

#### Gamma -- AI Presentations (4 tools)

| Tool | What It Does |
|------|-------------|
| generate | Create presentations, documents, webpages, or social posts |
| get_folders | Browse available Gamma folders |
| get_themes | Fetch available themes |
| get_generation_status | Check generation status |

#### Gmail -- Email Management (7 tools)

| Tool | What It Does |
|------|-------------|
| gmail_create_draft | Create a new email draft |
| gmail_get_profile | Retrieve Gmail profile information |
| gmail_list_drafts | List all saved email drafts |
| gmail_list_labels | List all labels |
| gmail_read_message | Read complete content of a specific message |
| gmail_read_thread | Read complete email conversation thread |
| gmail_search_messages | Search Gmail messages |

#### Google Calendar -- Meeting Management (9 tools)

| Tool | What It Does |
|------|-------------|
| gcal_create_event | Create a new calendar event |
| gcal_delete_event | Delete a calendar event |
| gcal_find_meeting_times | Find times when all attendees are available |
| gcal_find_my_free_time | Identify free time slots |
| gcal_get_event | Get details about a specific event |
| gcal_list_calendars | List calendars |
| gcal_list_events | List events within a time range |
| gcal_respond_to_event | RSVP to calendar invitations |
| gcal_update_event | Update an existing event |

#### Slack -- Chat and Messaging (13 tools)

| Tool | What It Does |
|------|-------------|
| slack_create_canvas | Create a Canvas document from markdown |
| slack_read_canvas | Retrieve Canvas content and section mapping |
| slack_read_channel | Read messages from a channel |
| slack_read_thread | Read messages from a specific thread |
| slack_read_user_profile | Retrieve user profile information |
| slack_schedule_message | Schedule a message for future delivery |
| slack_search_channels | Search channels by name or description |
| slack_search_public | Search public channels only |
| slack_search_public_and_private | Search all channels |
| slack_search_users | Search users by name, email, or profile |
| slack_send_message | Send a message to a channel or user |
| slack_send_message_draft | Create a draft message |
| slack_update_canvas | Update an existing Canvas |

#### Exa -- Advanced Web Search (3 tools)

| Tool | What It Does |
|------|-------------|
| web_search_exa | Search the web for any topic with clean content |
| crawling_exa | Read a webpage's full content as clean markdown |
| get_code_context_exa | Find code examples, documentation, and solutions |

#### Websets -- Web Entity Discovery (27 tools)

| Tool | What It Does |
|------|-------------|
| create_webset | Create a new collection |
| create_search | Find and add items to a webset |
| create_enrichment | Extract custom data from items |
| create_import | Upload CSV data |
| create_monitor | Auto-update a webset on schedule |
| create_webhook | Receive HTTP callbacks for webset events |
| get_webset / get_search / get_enrichment / get_import / get_item / get_monitor / get_webhook | Retrieve details |
| list_websets / list_webset_items / list_imports / list_monitors / list_webhooks / list_events | List collections |
| update_webset / update_monitor / update_webhook | Update settings |
| delete_webset / delete_monitor / delete_webhook | Delete items |
| cancel_search / cancel_enrichment | Cancel operations |
| preview_webset | Preview how a query will be interpreted |

### OpenClaw Skills (19 Ready / 57 Total)

#### Ready to Use

| Skill | What It Does |
|-------|-------------|
| 1password | Set up and use 1Password CLI |
| clawflow | Workflow orchestration with detached tasks |
| clawflow-inbox-triage | Example ClawFlow pattern for inbox triage |
| clawhub | Search, install, update skills from clawhub.com |
| coding-agent | Delegate coding tasks to Codex, Claude Code, or Pi |
| gh-issues | Fetch GitHub issues, spawn sub-agents |
| github | GitHub operations via gh CLI |
| healthcheck | Host security hardening |
| node-connect | Diagnose OpenClaw connection failures |
| openai-whisper-api | Transcribe audio via OpenAI |
| skill-creator | Create, edit, improve, or audit AgentSkills |
| tmux | Remote-control tmux sessions |
| video-frames | Extract frames from videos |
| weather | Weather forecasts |
| mission-control | Command center for all ClawdBots |
| rate-oracle | Track API rate limits and costs |
| capability-evolver | Self-evolution engine for agents |
| daily-brief | Daily weather and news brief |
| web-search | DuckDuckGo web search |

#### Needs Setup (38 skills including notable ones)

| Skill | What It Does |
|-------|-------------|
| summarize | Summarize URLs, podcasts, local files |
| notion | Notion API for pages, databases, blocks |
| goplaces | Google Places API for business search |
| nano-pdf | Edit PDFs with natural language |
| session-logs | Search and analyze session logs |
| slack | Control Slack from OpenClaw |
| peekaboo | Capture and automate macOS UI |
| sag | ElevenLabs text-to-speech |
| trello | Manage Trello boards and cards |

### OpenClaw Plugins (43 Loaded / 85 Total)

43 provider plugins are loaded (Anthropic, OpenAI, OpenRouter, DeepSeek, Google, Mistral, Together, etc.). 42 are disabled, including notable ones:

| Disabled Plugin | Why It Matters |
|----------------|---------------|
| exa | Native Exa integration -- wouldn't need the Python client |
| slack | Full Slack channel integration for agents |
| duckduckgo | Free web search fallback |
| firecrawl | Better web scraping than raw Exa crawl |
| memory-lancedb | Vector-based long-term memory for agents |
| perplexity | AI-powered search alternative |
| tavily | Another search provider option |

### What You're Missing Most

| Tool Suite | Why It Matters for Your Work |
|-----------|------------------------------|
| **Clay** (10 tools) | Purpose-built for contact enrichment. Find the VP of Corp Dev at SAP with verified email in one call. You're using Exa for this -- Clay is better. |
| **Websets** (27 tools) | An ENTIRE buyer discovery platform. "Find all companies that acquired HR tech companies in 2024" as a persistent, auto-updating collection. |
| **Gamma** (4 tools) | Turn buyer research JSON into polished pitch decks for Debbie with ONE call. |
| **clawflow** (skill) | Workflow orchestration for the 16-buyer batch -- farm out tasks, track progress, collect results. |
| **Exa MCP** (3 tools) | You use the Python Exa client but NOT the MCP Exa tools -- these are available directly in Claude without subprocess calls. |

---

## 5. Prompt-Refiner Comparison

### How the Test Worked

The /prompt-refiner skill does not exist as a callable OpenClaw skill. The agent searched `openclaw skills list` and the workspace skills directory -- nothing matching. The agent improvised by reading the actual codebase, analyzing the prompt, and producing a refined version grounded in real file paths.

**Finding:** You reference /prompt-refiner as something you "use a lot," but it may not be wired into OpenClaw. Worth investigating where you normally invoke it.

### Side-by-Side Comparison

| Dimension | My Revision | Prompt-Refiner Agent |
|-----------|------------|---------------------|
| Length | ~350 words | ~2,000 words |
| Format | Context, Problem, 5 Deliverables, Constraints | Full spec with Scope, Evaluation Criteria, Output Format, Constraints, Routing Guide |
| Specificity | Names workstreams and concepts | Names exact files: `research_templates.py`, `letter_engine.py`, `classification.py`, `VERTICAL_DATA` dicts |
| Actionability | "Refactor traced_buyer_run.py to accept a vertical config" | "Replace the VERTICAL_DATA dict in lib/letter_engine.py with a Supabase lookup to a new vertical_knowledge table" |
| Phasing | 5 workstreams with rough priorities | 4 explicit phases with time estimates |

### What the Prompt-Refiner Did Better

1. **Grounded in the codebase.** It grep'd for "home_service" and "vertical" across all Python files. Found 37 files with vertical lock-in. Named `VERTICAL_DATA`, `NEXT_CHAPTER_BASE`, and specific files to change.

2. **Made the acquirer-to-client matching engine the centerpiece.** Gave it its own numbered section with concrete examples for both verticals.

3. **Added evaluation criteria.** "Every recommendation must map to a specific file or table that exists today." Prevents hand-wavy architecture advice.

4. **Included a Code vs Cowork routing guide as a first-class section** with the handoff pattern explicitly described.

### What My Revision Did Better

1. **Concise.** 350 words that a model can execute without drowning. The refiner's 2,000 words risk context-exhaustion.

2. **Priority stack.** Numbered 1-5 with explicit "highest priority" markers.

3. **Included the constraint about dead API keys** and the immediate blocker (OpenClaw DeepSeek/Groq keys).

### Verdict

**Use the prompt-refiner's version for Claude Desktop.** It's the right length and specificity for a strategic planning session. Its codebase grounding will give Desktop the context it needs. Available at: `docs/PROMPT-refined-cross-domain.md`

**Use my revision for Claude Code execution.** The shorter version with clear priority stack drives action.

---

## 6. Comprehensive Overhaul Plan

The full plan is available as a separate document: `docs/PLAN-cross-domain-overhaul.md`

It covers:

- **Workstream 1:** Multi-Vertical Domain Onboarding (process diagram, pain/gain matching engine spec, domain config file format)
- **Workstream 2:** Cross-Domain Research Engine (traced_buyer_run.py refactor, batch runner, config-driven sections)
- **Workstream 3:** OpenClaw Agent Sync (agents as workers not decision-makers, multi-agent synthesis, SOUL.md replacement)
- **Workstream 4:** Letter Pipeline with Source Citation (daily morning task UX, split-pane review, claims schema)
- **Workstream 5:** Schema Unification (one schema for all verticals, JSONB for domain-specific fields)

### Implementation Sequence

| Week | Focus | Key Deliverables |
|------|-------|-----------------|
| Week 1 | Ship HR.com batch | Run 16 buyers, create vertical config, fix OpenClaw keys, design schema |
| Week 2 | Cross-domain refactor | Config-driven traced_buyer_run.py, pain/gain matching, update OpenClaw agents |
| Week 3 | Letter pipeline | Letter generation from matches, claims data model, review UX |
| Week 4 | Production hardening | Full HR.com batch with new pipeline, test second vertical, document everything |

### Decision Points for Claude Desktop

1. Should pain/gain matching be a separate LLM pass or integrated into section synthesis?
2. Is 3 agents per section worth the cost (~3x) or only for high-value sections?
3. Should pain/gain matches live as JSONB on engagement_buyers or as a separate table?
4. Should vertical configs live in Supabase or as JSON files in the repo?
5. Is multi-agent synthesis worth the complexity or should we keep Claude-only?

---

## 7. Next Steps

1. **Open Claude Desktop** and paste the refined prompt from `docs/PROMPT-refined-cross-domain.md`
2. **Analyze both plans** -- compare the plan from this session vs what Desktop produces
3. **Come back to Claude Code** to execute Phase 1 (unblock HR.com) and run the 16-buyer batch

### Documents on GitHub

| Document | Purpose | URL |
|----------|---------|-----|
| PLAN-cross-domain-overhaul.md | Full implementation plan | [GitHub](https://github.com/ewing-operating-system/master-crm-web/blob/main/docs/PLAN-cross-domain-overhaul.md) |
| PROMPT-refined-cross-domain.md | Refined prompt for Claude Desktop | [GitHub](https://github.com/ewing-operating-system/master-crm-web/blob/main/docs/PROMPT-refined-cross-domain.md) |
| TRACE-sap-successfactors-20260401-2149.md | Full untruncated SAP research trace | [GitHub](https://github.com/ewing-operating-system/master-crm-web/blob/main/docs/TRACE-sap-successfactors-20260401-2149.md) |
