#!/bin/bash
# resume-meeting-system.sh
# Run this in a fresh Claude Code terminal to pick up where we left off.
# Usage: paste this into Claude Code or run: claude -p "$(cat scripts/resume-meeting-system.sh)"

cat <<'PROMPT'
## CONTEXT

Read docs/MEETING-TRANSCRIPT-SYSTEM.md for full system context. This is the Meeting Transcript System — a pipeline that captures Fireflies meeting recordings, extracts business learnings via Claude, and generates interactive HTML pages.

## CURRENT STATE (as of 2026-04-01)

Everything is built, committed, and deployed EXCEPT one thing: the video/audio player has no media URLs because Fireflies MCP wasn't authenticated during the last rebuild.

## WHAT TO DO (in order)

### Step 1: Verify Fireflies MCP is authenticated
Run `claude mcp list` and check that "claude.ai Fireflies" shows tools beyond just `authenticate`. If it only shows the authenticate tool, tell the user to run `/mcp` and select Fireflies to complete OAuth.

### Step 2: Rebuild meeting pages with fresh media URLs
```bash
python3 scripts/meeting_pages.py --rebuild
```
This will:
- Fetch fresh signed audio/video CDN URLs from Fireflies MCP
- Store them in Supabase meeting_transcripts.audio_url as JSON
- Regenerate the HTML page at public/meetings/01KN3D8S57CX196DC5C6MZ8YHB.html with baked-in video src
- Commit and push to git (triggers Vercel deploy)

### Step 3: Verify the video player works
After deploy, check: https://master-crm-web-eight.vercel.app/meetings/01KN3D8S57CX196DC5C6MZ8YHB.html
- Video player should load and play
- Clicking a transcript utterance should seek the video to that timestamp
- Audio fallback should work if video URL is unavailable

### Step 4: Report result
Send via Telegram:
```bash
openclaw message send --channel telegram --target "$EWING_TELEGRAM_CHAT_ID" --message "[Argus] Meeting video player status: <result>. Page: https://master-crm-web-eight.vercel.app/meetings/01KN3D8S57CX196DC5C6MZ8YHB.html"
```

## KEY FILES
- docs/MEETING-TRANSCRIPT-SYSTEM.md — Full system spec
- scripts/meeting_pages.py — Core pipeline (1,301 lines)
- api/meetings/media-url.js — Fallback media URL API
- api/meetings/approve-learning.js — Learning approval API
- public/meetings/ — Generated meeting pages

## DO NOT
- Do not re-create tables or re-extract learnings — they already exist in Supabase
- Do not modify the pipeline code unless something is broken
- Do not ask the user questions in terminal — use Telegram
PROMPT
