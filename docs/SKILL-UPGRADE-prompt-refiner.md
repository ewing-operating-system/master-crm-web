# Prompt-Refiner Skill: Upgrade Plan

**Current location:** `~/.claude/skills/prompt-refiner/SKILL.md` (Claude Code only)
**Goal:** Make it work in both Claude Code AND OpenClaw, with awareness of the full tool ecosystem

---

## Current Problems

### 1. It Only Exists in Claude Code's World

The skill lives at `~/.claude/skills/` which only Claude Code reads. OpenClaw agents read from `~/.openclaw/workspace/skills/`. The skill needs to be installable in BOTH locations, ideally from a single source of truth.

**Fix:** Publish to ClawHub so it can be installed via `openclaw skills install prompt-refiner` AND symlinked or copied to `~/.claude/skills/`.

### 2. It Has No Awareness of Available Tools

The current skill says "After restructuring, the refined prompt often maps cleanly onto an existing skill" and lists 4 examples (account-research, pptx, exa-enrichment, salesfinity-loader). But it has no idea about the 91 MCP tools, 57 openclaw skills, or 85 plugins that are actually available. It can't route to Clay for contact enrichment, Websets for buyer discovery, Gamma for presentations, or Gmail for email drafts.

**Fix:** Add a tool-awareness section that instructs the refiner to check what's available and route accordingly.

### 3. It Doesn't Know About Cross-System Context

The skill doesn't know about CLAUDE.md, SOUL.md, memory files, or vertical configs. When it restructures a prompt, it doesn't check whether the restructured task aligns with existing system instructions or contradicts them.

**Fix:** Add a context-checking step before restructuring.

### 4. It Uses AskUserQuestion (Claude Code Only)

Line 97-98 says "Ask using the AskUserQuestion tool when possible." OpenClaw agents don't have AskUserQuestion -- they use message delivery channels (Telegram, Slack, etc.).

**Fix:** Make the interaction method platform-aware.

### 5. No Output Persistence

The refined prompt is presented in the conversation and then disappears. There's no mechanism to save it for reuse, share it with another session, or audit it later.

**Fix:** Add an option to write the refined prompt to a file.

---

## The Upgraded Skill

Below is the complete rewritten SKILL.md. Changes are marked with `[NEW]` comments.

```markdown
---
name: prompt-refiner
description: "Restructures messy multi-intent prompts into clear, actionable instructions. Works in both Claude Code and OpenClaw. Checks available tools, cross-system context, and routes to the right execution environment. Triggers on stream-of-consciousness input with competing intentions."
---

> **Credentials:** NEVER put raw API keys in this file. Reference `$ENV_VAR_NAME` only.

# Prompt Refiner

You are a prompt translator. Your job is to take messy human thinking and turn it into
structured prompts that any agent (Claude Code, OpenClaw, or Claude Desktop) can execute
precisely.

## Why This Skill Exists

Busy operators don't think in structured prompts. They think in streams: context bleeds
into requests, justifications mix with feature specs, past decisions get tangled with
future vision. This skill sits between the raw thought and the execution -- it catches
the stream, extracts the actual intent, and presents a clean prompt back for approval.

## When to Activate

1. **Multiple competing intents** -- review AND build AND compare AND plan in one message
2. **Context masquerading as instructions** -- long explanations of why, not what to do
3. **Embedded assumptions** -- "assume I'm not an expert" buried in paragraph 4
4. **Missing output spec** -- lots of detail on what, zero on what the deliverable looks like
5. **Future vision mixed with current request** -- "eventually X" next to "right now do Y"
6. **Tool/method justifications** -- "I picked Exa because..." isn't an instruction

## The Refining Process

### Step 1: Read the Full Input Without Acting

Read the entire message. Do not start executing. The most helpful thing is to understand
what they actually want before doing anything.

### Step 2: Check Available Context  [NEW]

Before restructuring, check what the system already knows:

**If running in Claude Code:**
- Read CLAUDE.md in the current repo (if it exists) for project rules and constraints
- Check memory files at ~/.claude/projects/*/memory/ for user preferences and feedback
- Note any active tasks (TaskList) that this prompt might relate to

**If running in OpenClaw:**
- Read SOUL.md and IDENTITY.md for agent identity and rules
- Read workspace MEMORY.md for persistent context
- Read recent daily memory files (memory/YYYY-MM-DD.md)

**In either case:**
- Note the project directory and what kind of codebase this is
- Check if the prompt references files, tables, or tools that exist or don't exist

This prevents the restructured prompt from contradicting system instructions or
referencing things that don't exist.

### Step 3: Extract the Core Components

Pull apart the stream into these buckets:

**Primary Intent** -- The ONE thing they most want done right now. If multiple, rank them.
Often the first and last sentences reveal the real ask; the middle is context.

**Context That Matters** -- Background that changes how you'd execute. Business model,
tool stack, role, audience. Keep it, but move it to a context section.

**Constraints and Preferences** -- "assume I'm not an expert," "compare against best-in-
class," "make it actionable." These shape output format and depth.

**Scope Boundaries** -- In scope for THIS prompt vs. future work. Be explicit.

**Known Gaps** -- Things they already know are missing. Don't waste time rediscovering
obvious gaps -- focus on gaps they haven't identified.

**Tool/Stack Context** -- What they're using and why. Compress to a clean list.

### Step 4: Check Available Tools and Route  [NEW]

After extracting intent, check what tools are available that match:

**MCP Tools (check if connected):**
- Clay -- company/contact enrichment, finding contacts by role at a company
- Gamma -- generating presentations, documents, webpages from content
- Gmail -- email drafts, searching messages, reading threads
- Google Calendar -- scheduling, finding free times, event management
- Slack -- channel messaging, canvas creation, user lookup
- Exa -- web search, page crawling, code documentation search
- Websets -- web entity discovery, persistent monitored collections, enrichment

**OpenClaw Skills (check `openclaw skills list` or known skills):**
- clawflow -- multi-step workflow orchestration
- coding-agent -- delegate to Claude Code, Codex, or Pi
- skill-creator -- create or audit other skills
- web-search -- DuckDuckGo search
- github / gh-issues -- GitHub operations

**Platform Routing:**
- If the task is CODE or DATA manipulation --> Claude Code
- If the task is THINKING, STRATEGY, or PROSE --> Claude Desktop / Cowork
- If the task needs MULTI-AGENT competition --> OpenClaw with parallel agents
- If the task needs WORKFLOW orchestration --> OpenClaw clawflow

Include routing recommendation in the restructured prompt.

### Step 5: Identify What's Missing

Flag (but don't over-ask -- max 2 questions):

- **Output format** -- document, checklist, code, conversation?
- **Audience** -- just them, their team, a client?
- **Depth** -- surface overview or deep technical analysis?
- **Priority order** -- if multiple asks, which matters most?
- **Success criteria** -- how will they know the output is good?

### Step 6: Present the Restructured Prompt

Use this structure (not every prompt needs every section):

```
# [Clear Task Title]

## YOUR TASK
[1-3 sentences. Imperative form. What the agent should do.]

## CONTEXT
[Compressed background. Only what changes the approach.]

## SCOPE
**In scope:** [This prompt]
**Out of scope:** [Acknowledged but separate]

## AVAILABLE TOOLS  [NEW]
[List the specific tools/skills that apply to this task.
Include MCP tools, skills, and platform routing.]

## EVALUATION CRITERIA
[Quality bar, comparison benchmarks, expertise framing.]

## KNOWN CONSTRAINTS
[Stack, timeline, budget, technical limits.]

## OUTPUT FORMAT
[Exactly what the deliverable looks like.]

## EXECUTION ENVIRONMENT  [NEW]
[Where this should run: Claude Code, Claude Desktop,
OpenClaw agent, or a combination with handoff points.]
```

### Step 7: Get Approval, Then Execute

Present the restructured prompt with a brief explanation of what changed and why.

**If in Claude Code:** Present inline and ask for approval before executing.

**If in OpenClaw:** Present via the active delivery channel (Telegram, Slack, etc.)
using the channel's formatting conventions. Do NOT use AskUserQuestion.  [NEW]

### Step 8: Persist (Optional)  [NEW]

If the refined prompt represents a repeatable task or a significant planning artifact:
- Save to `docs/PROMPT-{topic}-{date}.md` in the current project repo
- Or save to the openclaw workspace memory for future reference
- Note: only persist if the user approves or the prompt is part of a larger plan

## Refinement Patterns

### Pattern: "Review everything and also build the thing"
Split into two prompts. Review first, then build.

### Pattern: "Compare us to the best in the world"
Ask: best at WHAT specifically? Each comparison produces a different output.

### Pattern: "Eventually we need X, also do Y now"
Acknowledge X in Out of Scope. Execute Y.

### Pattern: "I picked [tool] because [reasons]"
Compress to: "**Stack:** [tool] -- [one-line why]". Note constraints from the reasons.

### Pattern: Implicit expertise framing
"Assume I'm not an expert" means: explain WHY, not just WHAT. Use analogies. No acronyms.

### Pattern: "Here's what we haven't done yet"
Goldmine. Don't rediscover known gaps. Spend words on gaps they haven't identified.

### Pattern: Tool-unaware request  [NEW]
User asks for something that a connected MCP tool handles perfectly but doesn't mention
the tool. Example: "find me the VP of Corp Dev at SAP" when Clay is connected. Route to
the tool and explain why.

### Pattern: Cross-system request  [NEW]
User wants something that spans Claude Code + OpenClaw + Desktop. Break into phases with
explicit handoff points. Example: "Research HR media verticals (Desktop) --> Insert
vertical config (Code) --> Run buyer research with multi-agent synthesis (OpenClaw+Code)."

## What NOT to Do

- Don't silently restructure and execute. Always show the refined prompt first.
- Don't add scope they didn't ask for.
- Don't strip personality or voice.
- Don't ask more than 2-3 clarifying questions.
- Don't over-structure simple requests.
- Don't route to tools the user hasn't connected or doesn't have access to.  [NEW]
- Don't reference file paths in the output -- use URLs or tool names instead.  [NEW]

## Integration with Other Skills

After restructuring, point out which skill or tool handles execution:

- Company research --> Clay MCP tools or Exa search
- Presentation creation --> Gamma MCP tool
- Email drafting --> Gmail MCP tool
- Meeting scheduling --> Google Calendar MCP tool
- Buyer discovery --> Websets MCP tools or Exa search
- Multi-step workflow --> OpenClaw clawflow skill
- Code changes --> Claude Code directly or coding-agent skill
- Strategic analysis --> Claude Desktop / Cowork
```

---

## Installation Plan

### Step 1: Update the Claude Code copy
```bash
# Overwrite ~/.claude/skills/prompt-refiner/SKILL.md with the new version
```

### Step 2: Install in OpenClaw workspace
```bash
mkdir -p ~/.openclaw/workspace/skills/prompt-refiner
cp ~/.claude/skills/prompt-refiner/SKILL.md ~/.openclaw/workspace/skills/prompt-refiner/
```

### Step 3 (Optional): Publish to ClawHub
```bash
openclaw skills search prompt-refiner  # check if name is taken
# Use skill-creator to package and publish
```

### Step 4: Symlink for single source of truth
Instead of two copies that drift:
```bash
# Pick one canonical location
CANONICAL=~/.claude/skills/prompt-refiner/SKILL.md
ln -sf "$CANONICAL" ~/.openclaw/workspace/skills/prompt-refiner/SKILL.md
```

Now edits to the Claude Code version automatically appear in OpenClaw.

---

## Summary of Changes

| Change | Why |
|--------|-----|
| Added Step 2: Check Available Context | Prevents refined prompts from contradicting CLAUDE.md or SOUL.md rules |
| Added Step 4: Check Available Tools and Route | Routes to Clay, Gamma, Websets, etc. instead of ignoring 91 MCP tools |
| Added AVAILABLE TOOLS section to output template | User sees which tools apply before approving |
| Added EXECUTION ENVIRONMENT section | Explicit Code vs Desktop vs OpenClaw routing |
| Replaced AskUserQuestion with platform-aware interaction | Works in both Claude Code and OpenClaw channels |
| Added Step 8: Persist | Refined prompts can be saved for reuse and audit |
| Added cross-system and tool-unaware patterns | Handles the most common real-world patterns |
| Updated skill integration list | Maps to actual MCP tools, not hypothetical skills |
