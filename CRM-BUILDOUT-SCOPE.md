# CRM BUILDOUT SCOPE — Next Chapter Master CRM
# Rewritten: 2026-03-30 00:55
# Vision: Always-on prospecting → proposal engine → humanless letter mailing → wow URL on the phone

---

## THE 10 BUILDS — In Order

### BUILD 1: Letter Template Engine (TONIGHT)
Create a master letter template system. Letters are written in operator narrative, NOT private equity finance speak. They tell the owner's story back to them. They embed favorable EBITDA multipliers naturally. They feel personal and human — not mass-produced.

Template must include:
- Company-specific opening (their story, their market, their growth)
- Industry EBITDA benchmarks woven into the narrative (from ebitda-levers data)
- Why NOW is the right time (market consolidation, multiples, buyer appetite)
- Specific buyer interest framing (without naming buyers)
- Clear CTA: "Visit [URL] to see the full analysis we've prepared for your company"
- Professional letterhead formatting for physical mail via Lob

Template lives at: templates/master-letter.html
Engine lives at: lib/letter_engine.py
Uses: Supabase buyer data + EBITDA levers + company profiles

### BUILD 1.5: Meeting Page v2 — The Data Collection Engine (TONIGHT)
The first meeting page is already good (agenda, questions, talking points, danger zones). But it's read-only. It needs to become the interactive data capture form that feeds EVERYTHING downstream.

New sections:
- **During-Meeting Form**: Live note-taking with dropdowns for owner motivation, timeline, revenue breakdown, margin profile, key employees, deal breakers, emotional temperature, story elements, verbatim quotes
- **Post-Meeting Auto-Gen**: After the call, auto-generates meeting summary, data completeness score ("you captured 8/12 fields"), what this data unlocks, action items, link to generate follow-up email and proposal
- **Downstream Data Flow**: Meeting notes → letter engine (owner's story, emotional hooks), proposal engine (revenue, margins, timeline), buyer targeting (perfect buyer profile), valuation (revenue + margins → range), EBITDA levers (relevant based on their operations)

Nailing this meeting = getting a YES to the proposal. Every downstream document is 10x better with captured first-meeting data.

### BUILD 2: Lob API Integration (Physical Letter Mailing)
Wire Lob API (key already exists, LIVE) to send physical letters.
- Input: rendered letter HTML + recipient address
- Output: physical letter in the mail
- Tracking: letter_id, status, delivery date stored in Supabase `letter_campaigns` table
- API docs: https://docs.lob.com

### BUILD 3: Letter Campaign Manager (the 250/150 Rule)
The governor that controls spend:
- Agent generates and mails up to 250 letters per campaign batch
- After 250 sent → STOP sending
- Monitor Salesfinity for call outcomes on those 250 recipients
- Won't send more letters until: 150 of the 250 have been called 5x each, logged in Supabase
- When threshold met → unlock next batch of 250
- Telegram notification: "Batch 1: 250 letters sent. 87/150 contacts called 5x. Need 63 more before next batch."

### BUILD 4: SAP-Quality Research for All 193 Buyers
Upgrade researcher agent to fill all 7 research sections for every buyer:
1. Company overview (revenue, headcount, ownership)
2. Acquisition history
3. Strategic rationale (why they'd buy in this vertical)
4. Financial capacity / dry powder
5. Key decision-makers with contact info
6. Recent news and market moves
7. Approach strategy (warm intro path, cold angle, story hook)

Currently: 20 of 193 have this depth. Target: all 193.

### BUILD 5: Shareable URL Experience Polish
The URL you share on the phone must work perfectly on mobile.
- Test every interactive proposal page on iPhone viewport
- Fix any layout breaks, font sizing, touch targets
- The data room gate must work on mobile
- Load time under 2 seconds
- One URL → full story: company profile, EBITDA benchmarks, buyer rationale, interactive proposal

### BUILD 6: Auto-Regeneration Pipeline
Research agent → Supabase → auto-generate HTML → git push → Vercel deploy → URL live.
No human in the loop between research completing and the page being shareable.

### BUILD 7: Salesfinity Integration
- Load enriched contacts into Salesfinity dialer via API
- Track call outcomes: connected, voicemail, no answer, callback requested
- Feed outcomes back to Supabase
- Powers the 250/150 governor (Build 3)

### BUILD 8: Source Attribution on Every Fact
Every claim on every page gets a footnote: [1] → source URL.
When they ask "where'd you get that?" you say "click the footnote."

### BUILD 9: Graduated Auto-Trust
- First 10 letters: require manual approval before Lob sends
- After 10 approved: auto-send with 24-hour inspection window (Telegram notification with preview link, auto-sends unless you reply STOP)
- After 50 approved: auto-send immediately, log only
- This is how you scale from 250 to 2,500

### BUILD 10: Listener Agent
Watches 5 channels (Gmail, Salesfinity, Calendar, Fireflies, Slack).
When a prospect engages: update CRM, regenerate pages, notify Telegram.
Closes the loop from letter → call → response → deal stage update.

---

## EXECUTION MODEL

| Build | Model | Can Run Overnight? | Human Needed? |
|-------|-------|--------------------|---------------|
| 1 | Sonnet | YES | No — template is pre-decided |
| 2 | Sonnet | YES | No — Lob API key exists |
| 3 | Sonnet | YES | No — rules are defined above |
| 4 | Researcher agent | YES (cron) | No — agent runs autonomously |
| 5 | Sonnet | YES | No — just CSS/layout fixes |
| 6 | Sonnet | YES | No — wiring existing engines |
| 7 | Sonnet | YES | No — Salesfinity API key exists |
| 8 | Sonnet | YES | No — mechanical find-and-add |
| 9 | Sonnet | YES | No — rules defined above |
| 10 | Opus design → Sonnet build | Design overnight, build tomorrow | Design: no. Build: maybe |

ALL 10 can run overnight on Sonnet without human input.
