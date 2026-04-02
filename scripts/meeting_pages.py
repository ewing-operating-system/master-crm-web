#!/usr/bin/env python3
"""
meeting_pages.py — Fireflies Meeting Transcript Page Generator

Credentials: all keys come from env vars (inherited from ~/.zshrc).
See .env.example for variable names. NEVER hardcode keys in scripts.

Modes:
  --poll        Check Fireflies for new transcripts, generate pages for any new ones
  --generate ID Generate page for a specific Fireflies transcript ID
  --rebuild     Regenerate all meeting pages from Supabase data

Flow:
  1. Fetch transcripts from Fireflies MCP via claude CLI
  2. Store in meeting_transcripts table
  3. Extract learnings via Claude (stored in meeting_learnings)
  4. Generate static HTML page at public/meetings/<fireflies-id>.html
  5. Commit + push to deploy

Usage:
  python3 scripts/meeting_pages.py --poll
  python3 scripts/meeting_pages.py --generate <fireflies_id>
  python3 scripts/meeting_pages.py --rebuild

Cron: 0 9-17 * * * (hourly 9am-5pm)
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path
from string import Template
from typing import Optional

# ── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = PROJECT_ROOT / "public"
MEETINGS_DIR = PUBLIC_DIR / "meetings"
LOGS_DIR = PROJECT_ROOT / "logs"

MEETINGS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOGS_DIR / "meeting_pages.log"),
    ],
)
log = logging.getLogger("meeting_pages")

# ── Credentials ──────────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


# ── Supabase helpers ─────────────────────────────────────────────────────────
def _supa_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def supa_get(table: str, params: str = "") -> list:
    url = f"{SUPABASE_URL}/rest/v1/{table}?{params}"
    req = urllib.request.Request(url, headers=_supa_headers())
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        log.error("Supabase GET %s error %s: %s", table, e.code, e.read().decode()[:300])
        return []


def supa_post(table: str, data: dict) -> Optional[dict]:
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = _supa_headers()
    headers["Prefer"] = "return=representation,resolution=merge-duplicates"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            rows = json.loads(resp.read())
            return rows[0] if rows else None
    except urllib.error.HTTPError as e:
        log.error("Supabase POST %s error %s: %s", table, e.code, e.read().decode()[:300])
        return None


def supa_patch(table: str, match: str, data: dict) -> Optional[dict]:
    url = f"{SUPABASE_URL}/rest/v1/{table}?{match}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers=_supa_headers(), method="PATCH")
    try:
        with urllib.request.urlopen(req) as resp:
            rows = json.loads(resp.read())
            return rows[0] if rows else None
    except urllib.error.HTTPError as e:
        log.error("Supabase PATCH %s error %s: %s", table, e.code, e.read().decode()[:300])
        return None


# ── Fireflies via Claude CLI ────────────────────────────────────────────────
def fetch_recent_transcripts(hours: int = 2) -> list[dict]:
    """Use claude CLI to invoke Fireflies MCP and get recent transcripts."""
    from_dt = datetime.now(timezone.utc) - timedelta(hours=hours)
    from_iso = from_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    prompt = f"""Use the Fireflies MCP tools to find transcripts from the last {hours} hours (since {from_iso}).

First call mcp__claude_ai_Fireflies__fireflies_get_transcripts to list recent transcripts.

For each transcript found, call mcp__claude_ai_Fireflies__fireflies_get_transcript to get the full details including the transcript text, speakers, and audio URL.

Return ONLY a JSON array. Each element must have:
{{
  "id": "fireflies transcript ID",
  "title": "meeting title",
  "date": "ISO-8601 datetime",
  "duration": duration_in_minutes,
  "audio_url": "URL to audio file or null",
  "participants": [{{"name": "Person Name", "email": "email@domain.com"}}],
  "summary": "meeting summary text",
  "action_items": ["action item 1", "action item 2"],
  "sentences": [{{"speaker_name": "Name", "text": "what they said", "start_time": 0.0, "end_time": 5.0}}]
}}

If no transcripts exist in this time range, return: []
Do NOT include any markdown formatting, explanations, or prose. ONLY the JSON array."""

    log.info("Invoking claude CLI for Fireflies (last %d hours since %s)...", hours, from_iso)
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text"],
            capture_output=True, text=True, timeout=180,
        )
    except FileNotFoundError:
        log.error("claude CLI not found")
        return []
    except subprocess.TimeoutExpired:
        log.error("claude CLI timed out")
        return []

    if result.returncode != 0:
        log.error("claude CLI error: %s", result.stderr[:500])
        return []

    raw = result.stdout.strip()
    # Strip markdown fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    m = re.search(r"(\[.*\])", raw, re.DOTALL)
    if not m:
        if raw in ("", "[]"):
            log.info("No new transcripts found.")
            return []
        log.warning("Could not parse JSON from claude output:\n%s", raw[:500])
        return []

    try:
        transcripts = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        log.warning("JSON parse error: %s\nRaw: %s", e, raw[:500])
        return []

    log.info("Fireflies returned %d transcript(s)", len(transcripts))
    return transcripts if isinstance(transcripts, list) else []


def fetch_single_transcript(fireflies_id: str) -> Optional[dict]:
    """Fetch a specific transcript by ID."""
    prompt = f"""Use the Fireflies MCP tool mcp__claude_ai_Fireflies__fireflies_get_transcript to fetch transcript with ID "{fireflies_id}".

Return ONLY a JSON object with:
{{
  "id": "{fireflies_id}",
  "title": "meeting title",
  "date": "ISO-8601 datetime",
  "duration": duration_in_minutes,
  "audio_url": "URL to audio file or null",
  "participants": [{{"name": "Person Name", "email": "email@domain.com"}}],
  "summary": "meeting summary text",
  "action_items": ["action item 1"],
  "sentences": [{{"speaker_name": "Name", "text": "what they said", "start_time": 0.0, "end_time": 5.0}}]
}}

No markdown, no prose. ONLY the JSON object."""

    log.info("Fetching transcript %s via claude CLI...", fireflies_id)
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text"],
            capture_output=True, text=True, timeout=180,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        log.error("claude CLI error: %s", e)
        return None

    if result.returncode != 0:
        log.error("claude CLI error: %s", result.stderr[:500])
        return None

    raw = result.stdout.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    m = re.search(r"(\{.*\})", raw, re.DOTALL)
    if not m:
        log.warning("Could not parse JSON: %s", raw[:500])
        return None

    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError as e:
        log.warning("JSON parse error: %s", e)
        return None


# ── Entity detection ─────────────────────────────────────────────────────────
KNOWN_ENTITIES = {
    "revsup.com": "revsup",
    "nextchapteradvisory.com": "next_chapter",
    "andcapital.com": "and_capital",
    "theforge.com": "the_forge",
    "biolev.com": "biolev",
    "seasweet.com": "sea_sweet",
}

INTERNAL_DOMAINS = {"revsup.com", "nextchapteradvisory.com", "andcapital.com"}


def detect_entities(transcript: dict) -> list[str]:
    """Detect which entities are involved in a meeting from participants."""
    entities = set()
    participants = transcript.get("participants") or []
    for p in participants:
        email = (p.get("email") or "").lower()
        if "@" in email:
            domain = email.split("@")[1]
            if domain in KNOWN_ENTITIES:
                entities.add(KNOWN_ENTITIES[domain])
            elif domain not in INTERNAL_DOMAINS:
                # External participant — try to match to a known company via Supabase
                rows = supa_get("targets", f"select=entity&extra_fields->>email=ilike.*{domain}*&limit=1")
                for row in rows:
                    if row.get("entity"):
                        entities.add(row["entity"])

    # Also check title for entity keywords
    title = (transcript.get("title") or "").lower()
    for entity_name in ["revsup", "and capital", "next chapter", "the forge", "biolev", "sea sweet"]:
        slug = entity_name.replace(" ", "_")
        if entity_name in title:
            entities.add(slug)

    return sorted(entities) if entities else ["unknown"]


# ── Learning extraction ──────────────────────────────────────────────────────
def extract_learnings(transcript: dict, entities: list[str]) -> list[dict]:
    """Use Claude to extract business learnings from a transcript."""
    sentences = transcript.get("sentences") or []
    # Build a readable transcript for Claude
    transcript_text = ""
    for s in sentences[:500]:  # Cap at 500 sentences to stay in context
        speaker = s.get("speaker_name", "Unknown")
        text = s.get("text", "")
        transcript_text += f"{speaker}: {text}\n"

    if not transcript_text:
        transcript_text = transcript.get("summary") or "No transcript text available."

    entity_list = ", ".join(entities)
    prompt = f"""You are extracting business intelligence from a meeting transcript for a CRM system.

The entities involved in this meeting are: {entity_list}

Transcript:
{transcript_text[:8000]}

For each business-relevant learning in this conversation, create an extraction. Categories:
- pain_point: Problems or challenges mentioned
- budget: Budget, revenue, deal size, financial information
- timeline: Dates, deadlines, expected close dates
- decision_maker: Who makes decisions, org structure
- objection: Concerns, pushback, hesitation
- next_step: Action items, follow-ups, commitments
- relationship: Rapport, trust signals, personal connections
- competitive: Competitor mentions, market positioning
- requirement: Specific needs, criteria, specifications

For each learning, specify which entity it pertains to. A learning about the buyer's acquisition plans goes to the buyer entity. A learning about how the seller positioned themselves goes to the seller entity.

Return ONLY a JSON array. Each element:
{{
  "entity": "entity_slug",
  "category": "one of the categories above",
  "learning": "clear, specific statement of what was learned",
  "confidence": 0.0 to 1.0,
  "target_table": "dossier_final or buyer_contacts or targets",
  "target_column": "relevant column name or null",
  "target_value": "the specific value to store or null",
  "transcript_timestamp": "approximate timestamp or speaker quote reference"
}}

Extract 5-15 learnings. Focus on actionable intelligence. Skip pleasantries.
No markdown, no prose. ONLY the JSON array."""

    log.info("Extracting learnings via Claude...")
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text"],
            capture_output=True, text=True, timeout=120,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        log.error("Learning extraction failed: %s", e)
        return []

    if result.returncode != 0:
        log.error("claude CLI error: %s", result.stderr[:500])
        return []

    raw = result.stdout.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    m = re.search(r"(\[.*\])", raw, re.DOTALL)
    if not m:
        log.warning("Could not parse learnings JSON")
        return []

    try:
        learnings = json.loads(m.group(1))
        return learnings if isinstance(learnings, list) else []
    except json.JSONDecodeError as e:
        log.warning("Learnings JSON parse error: %s", e)
        return []


# ── HTML page generation ─────────────────────────────────────────────────────
def generate_meeting_page(transcript_row: dict, learnings: list[dict]) -> str:
    """Generate a static HTML page for a meeting transcript."""
    title = transcript_row.get("title") or "Meeting"
    date = transcript_row.get("date") or ""
    duration = transcript_row.get("duration_minutes") or 0
    audio_url = transcript_row.get("audio_url") or ""
    fireflies_id = transcript_row.get("fireflies_id") or ""
    participants = transcript_row.get("participants") or []
    entities = transcript_row.get("entities") or []
    summary = transcript_row.get("summary") or ""
    sentences = (transcript_row.get("transcript_json") or {}).get("sentences") or []
    transcript_id = transcript_row.get("id") or ""

    # Format date
    try:
        dt = datetime.fromisoformat(str(date).replace("Z", "+00:00"))
        date_display = dt.strftime("%B %-d, %Y")
        date_short = dt.strftime("%b %-d, %Y")
    except Exception:
        date_display = str(date)[:10]
        date_short = date_display

    # Format participants
    participant_names = [p.get("name", p.get("email", "Unknown")) for p in participants]
    participants_display = ", ".join(participant_names)

    # Format entity badges
    entity_badges = ""
    entity_colors = {
        "and_capital": "#1a1a2e", "revsup": "#c0392b", "next_chapter": "#2c3e50",
        "the_forge": "#e67e22", "biolev": "#27ae60", "sea_sweet": "#2980b9",
    }
    for e in entities:
        color = entity_colors.get(e, "#6c757d")
        label = e.replace("_", " ").title()
        entity_badges += f'<span class="entity-badge" style="background:{color}">{label}</span> '

    # Speaker color assignment for visual distinction
    speaker_colors = ["#58a6ff", "#f78166", "#a5d6ff", "#7ee787", "#d2a8ff", "#ffa657", "#ff7b72", "#79c0ff"]
    speaker_map = {}
    color_idx = 0
    for s in sentences:
        name = s.get("speaker_name", "Unknown")
        if name not in speaker_map:
            speaker_map[name] = speaker_colors[color_idx % len(speaker_colors)]
            color_idx += 1

    # Build transcript HTML with per-speaker colors
    transcript_html = ""
    current_speaker = ""
    for s in sentences:
        speaker = s.get("speaker_name", "Unknown")
        text = s.get("text", "")
        start = s.get("start_time", 0)
        color = speaker_map.get(speaker, "#58a6ff")

        # Format timestamp
        mins = int(start // 60)
        secs = int(start % 60)
        timestamp = f"{mins:02d}:{secs:02d}"

        if speaker != current_speaker:
            if current_speaker:
                transcript_html += '</div>\n'
            transcript_html += f'''<div class="utterance" data-time="{start}">
  <div class="speaker-row">
    <span class="timestamp">[{timestamp}]</span>
    <span class="speaker-name" style="color:{color}">{speaker}</span>
  </div>
  <p class="speaker-text">{text}</p>
'''
            current_speaker = speaker
        else:
            transcript_html += f'  <p class="speaker-text">{text}</p>\n'

    if current_speaker:
        transcript_html += '</div>\n'

    # Build learnings HTML
    learnings_html = ""
    for i, l in enumerate(learnings):
        learning_id = l.get("id", f"learning-{i}")
        entity = l.get("entity", "unknown")
        category = l.get("category", "general")
        learning_text = l.get("learning", "")
        confidence = l.get("confidence", 0.5)
        approved = l.get("approved")

        category_icons = {
            "pain_point": "&#x26A0;", "budget": "&#x1F4B0;", "timeline": "&#x1F4C5;",
            "decision_maker": "&#x1F464;", "objection": "&#x1F6D1;", "next_step": "&#x27A1;",
            "relationship": "&#x1F91D;", "competitive": "&#x2694;", "requirement": "&#x1F4CB;",
        }
        icon = category_icons.get(category, "&#x1F4A1;")
        cat_label = category.replace("_", " ").title()
        entity_label = entity.replace("_", " ").title()
        conf_pct = int(confidence * 100)

        status_class = ""
        status_buttons = ""
        if approved is True:
            status_class = "approved"
            status_buttons = '<span class="status-tag approved-tag">Approved</span>'
        elif approved is False:
            status_class = "rejected"
            status_buttons = '<span class="status-tag rejected-tag">Rejected</span>'
        else:
            status_buttons = f'''<button class="btn-approve" onclick="approveLearning('{learning_id}', true)">Agree</button>
<button class="btn-reject" onclick="approveLearning('{learning_id}', false)">Reject</button>'''

        learnings_html += f'''
<div class="learning-card {status_class}" id="learning-{learning_id}" data-entity="{entity}">
  <div class="learning-header">
    <span class="learning-icon">{icon}</span>
    <span class="learning-category">{cat_label}</span>
    <span class="learning-entity">{entity_label}</span>
    <span class="learning-confidence">{conf_pct}%</span>
  </div>
  <p class="learning-text">{learning_text}</p>
  <div class="learning-actions">
    {status_buttons}
  </div>
</div>'''

    # Hub page links
    hub_links = ""
    for e in entities:
        if e == "unknown":
            continue
        # Find matching hub page
        slug = e.replace("_", "-")
        hub_links += f'<a href="/{slug}-hub.html" class="hub-link">{e.replace("_", " ").title()} Account Page</a> '

    # Build entity filter buttons (outside f-string to avoid backslash issues)
    entity_filter_buttons = ""
    for e in entities:
        if e != "unknown":
            label = e.replace("_", " ").title()
            entity_filter_buttons += f'<button class="filter-btn" onclick="filterLearnings(\'{e}\')">{label}</button>\n        '

    # Determine if audio_url is a direct file or a Fireflies view link
    has_audio = bool(audio_url)

    # Build speaker legend
    speaker_legend = ""
    for name, color in speaker_map.items():
        speaker_legend += f'<span class="speaker-chip" style="--speaker-color:{color}">{name}</span>'

    # Count learnings by status
    pending_count = sum(1 for l in learnings if l.get("approved") is None)
    approved_count = sum(1 for l in learnings if l.get("approved") is True)
    rejected_count = sum(1 for l in learnings if l.get("approved") is False)

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — Meeting Transcript</title>
  <meta name="page-type" content="meeting-transcript">
  <meta name="transcript-id" content="{transcript_id}">
  <meta name="entities" content="{','.join(entities)}">
  <script src="/supabase-config.js"></script>
  <style>
    *, *::before, *::after {{ margin: 0; padding: 0; box-sizing: border-box; }}
    html {{ height: 100%; }}
    body {{
      background: #0d1117; color: #c9d1d9;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      height: 100%; display: flex; flex-direction: column;
    }}

    /* ── Header ─────────────────────────────────────── */
    .meeting-header {{
      background: #161b22;
      border-bottom: 1px solid #30363d;
      padding: 20px 28px 16px;
      flex-shrink: 0;
    }}
    .header-top {{
      display: flex; align-items: flex-start; justify-content: space-between;
      gap: 16px; flex-wrap: wrap;
    }}
    .meeting-header h1 {{
      font-size: 20px; font-weight: 600; color: #f0f6fc;
      letter-spacing: -0.3px;
    }}
    .header-badges {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}
    .entity-badge {{
      display: inline-flex; align-items: center; padding: 4px 12px;
      border-radius: 16px; color: #fff; font-size: 11px;
      font-weight: 600; letter-spacing: 0.3px; text-transform: uppercase;
    }}
    .meta-row {{
      display: flex; gap: 20px; flex-wrap: wrap; align-items: center;
      font-size: 13px; color: #8b949e; margin-top: 10px;
    }}
    .meta-item {{ display: flex; align-items: center; gap: 5px; }}
    .meta-icon {{ opacity: 0.6; }}
    .hub-links {{ margin-top: 8px; display: flex; gap: 16px; }}
    .hub-link {{
      color: #58a6ff; text-decoration: none; font-size: 12px;
      display: flex; align-items: center; gap: 4px;
    }}
    .hub-link:hover {{ text-decoration: underline; }}

    /* ── Video player ───────────────────────────────── */
    .player-section {{
      background: #000; border-bottom: 1px solid #21262d;
      flex-shrink: 0; position: relative;
    }}
    .player-section video {{
      width: 100%; max-height: 280px; display: block;
      background: #000;
    }}
    .player-loading {{
      display: flex; align-items: center; justify-content: center;
      padding: 40px; color: #484f58; font-size: 13px; gap: 10px;
    }}
    .player-loading .spinner {{
      width: 18px; height: 18px; border: 2px solid #30363d;
      border-top-color: #58a6ff; border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
    .player-fallback {{
      display: none; padding: 16px 28px;
      background: #161b22; text-align: center;
    }}
    .player-fallback a {{
      color: #58a6ff; text-decoration: none; font-size: 13px;
    }}
    .player-fallback a:hover {{ text-decoration: underline; }}

    /* ── Summary strip ─────────────────────────────── */
    .summary-strip {{
      background: #161b22; border-bottom: 1px solid #21262d;
      padding: 14px 28px; flex-shrink: 0;
    }}
    .summary-strip h3 {{
      color: #8b949e; font-size: 10px; text-transform: uppercase;
      letter-spacing: 1px; margin-bottom: 6px; font-weight: 600;
    }}
    .summary-text {{
      color: #c9d1d9; font-size: 13px; line-height: 1.55;
      max-width: 900px;
    }}

    /* ── Speaker legend ────────────────────────────── */
    .speaker-legend {{
      background: #0d1117; border-bottom: 1px solid #21262d;
      padding: 10px 28px; flex-shrink: 0;
      display: flex; gap: 10px; flex-wrap: wrap; align-items: center;
    }}
    .speaker-legend-label {{
      color: #484f58; font-size: 10px; text-transform: uppercase;
      letter-spacing: 1px; margin-right: 4px;
    }}
    .speaker-chip {{
      display: inline-flex; align-items: center; gap: 4px;
      font-size: 12px; color: var(--speaker-color); font-weight: 500;
      padding: 3px 10px; border-radius: 12px;
      background: color-mix(in srgb, var(--speaker-color) 12%, transparent);
      border: 1px solid color-mix(in srgb, var(--speaker-color) 25%, transparent);
    }}

    /* ── Main two-column layout ────────────────────── */
    .main-content {{
      display: grid;
      grid-template-columns: 1fr 400px;
      flex: 1; min-height: 0;
    }}
    @media (max-width: 960px) {{
      .main-content {{ grid-template-columns: 1fr; grid-template-rows: 1fr auto; }}
    }}

    /* ── Transcript panel ──────────────────────────── */
    .transcript-panel {{
      overflow-y: auto; padding: 20px 28px 40px;
      border-right: 1px solid #21262d;
    }}
    .transcript-panel h2 {{
      color: #f0f6fc; font-size: 13px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.8px;
      margin-bottom: 16px; padding-bottom: 10px;
      border-bottom: 1px solid #21262d;
    }}
    .utterance {{
      margin-bottom: 2px; padding: 6px 10px;
      border-radius: 4px; transition: background 0.15s;
      border-left: 2px solid transparent;
    }}
    .utterance:hover {{
      background: #161b22;
      border-left-color: #30363d;
      cursor: pointer;
    }}
    .utterance.active {{
      background: rgba(31,111,235,0.08);
      border-left-color: #1f6feb;
    }}
    .speaker-row {{
      display: flex; align-items: baseline; gap: 8px; margin-bottom: 2px;
    }}
    .timestamp {{
      color: #484f58; font-size: 10px; font-family: "SF Mono", "Fira Code", monospace;
      cursor: pointer; min-width: 38px; user-select: none;
    }}
    .timestamp:hover {{ color: #58a6ff; }}
    .speaker-name {{
      font-weight: 600; font-size: 12px;
    }}
    .speaker-text {{
      color: #c9d1d9; font-size: 13px; line-height: 1.55;
      margin-left: 46px; margin-bottom: 2px;
    }}

    /* ── Learnings panel ───────────────────────────── */
    .learnings-panel {{
      overflow-y: auto; padding: 20px 18px 40px;
      background: #0d1117;
    }}
    .learnings-header {{
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 4px;
    }}
    .learnings-panel h2 {{
      color: #f0f6fc; font-size: 13px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.8px;
    }}
    .learnings-count {{
      font-size: 11px; color: #8b949e;
    }}
    .learnings-count .num {{ color: #58a6ff; font-weight: 600; }}
    .learnings-subtitle {{
      color: #484f58; font-size: 11px; margin-bottom: 14px;
    }}

    /* Filter pills */
    .filter-bar {{
      display: flex; gap: 4px; margin-bottom: 14px; flex-wrap: wrap;
      padding-bottom: 12px; border-bottom: 1px solid #21262d;
    }}
    .filter-btn {{
      padding: 4px 12px; border-radius: 16px; border: 1px solid #30363d;
      background: transparent; color: #8b949e; font-size: 11px;
      cursor: pointer; transition: all 0.15s; white-space: nowrap;
    }}
    .filter-btn:hover {{ border-color: #58a6ff; color: #c9d1d9; }}
    .filter-btn.active {{
      background: #1f6feb; color: #fff; border-color: #1f6feb;
      font-weight: 500;
    }}

    /* Learning cards */
    .learning-card {{
      background: #161b22; border: 1px solid #21262d;
      border-radius: 8px; padding: 12px 14px;
      margin-bottom: 8px; transition: all 0.15s;
      position: relative;
    }}
    .learning-card:hover {{
      border-color: #30363d;
      box-shadow: 0 1px 3px rgba(0,0,0,0.3);
    }}
    .learning-card.approved {{
      border-left: 3px solid #238636;
      background: linear-gradient(90deg, rgba(35,134,54,0.06) 0%, #161b22 40%);
    }}
    .learning-card.rejected {{
      border-left: 3px solid #da3633;
      opacity: 0.5;
    }}
    .learning-header {{
      display: flex; align-items: center; gap: 6px;
      margin-bottom: 6px; flex-wrap: wrap;
    }}
    .learning-icon {{ font-size: 13px; line-height: 1; }}
    .learning-category {{
      background: #21262d; color: #8b949e; font-size: 9px;
      padding: 2px 8px; border-radius: 10px; text-transform: uppercase;
      letter-spacing: 0.6px; font-weight: 600;
    }}
    .learning-entity {{
      color: #58a6ff; font-size: 9px; padding: 2px 8px;
      border-radius: 10px; font-weight: 500;
      border: 1px solid rgba(88,166,255,0.2);
    }}
    .learning-confidence {{
      color: #484f58; font-size: 10px; margin-left: auto;
      font-family: "SF Mono", monospace;
    }}
    .learning-text {{
      color: #c9d1d9; font-size: 12px; line-height: 1.5;
      margin-bottom: 10px;
    }}
    .learning-actions {{
      display: flex; gap: 6px; align-items: center;
    }}
    .btn-approve, .btn-reject {{
      padding: 5px 16px; border-radius: 6px; border: 1px solid transparent;
      font-size: 12px; font-weight: 500; cursor: pointer;
      transition: all 0.15s;
    }}
    .btn-approve {{
      background: #238636; color: #fff; border-color: #238636;
    }}
    .btn-approve:hover {{ background: #2ea043; }}
    .btn-reject {{
      background: transparent; color: #8b949e; border-color: #30363d;
    }}
    .btn-reject:hover {{ background: #21262d; color: #da3633; border-color: #da3633; }}
    .status-tag {{
      font-size: 11px; padding: 4px 12px; border-radius: 6px; font-weight: 500;
    }}
    .approved-tag {{ background: rgba(35,134,54,0.15); color: #3fb950; }}
    .rejected-tag {{ background: rgba(218,54,51,0.15); color: #f85149; }}

    /* ── Scrollbar ──────────────────────────────────── */
    ::-webkit-scrollbar {{ width: 6px; }}
    ::-webkit-scrollbar-track {{ background: transparent; }}
    ::-webkit-scrollbar-thumb {{ background: #30363d; border-radius: 3px; }}
    ::-webkit-scrollbar-thumb:hover {{ background: #484f58; }}
  </style>
</head>
<body>
  <header class="meeting-header">
    <div class="header-top">
      <h1>{title}</h1>
      <div class="header-badges">{entity_badges}</div>
    </div>
    <div class="meta-row">
      <span class="meta-item"><span class="meta-icon">&#x1F4C5;</span> {date_display}</span>
      <span class="meta-item"><span class="meta-icon">&#x23F1;</span> {duration} min</span>
      <span class="meta-item"><span class="meta-icon">&#x1F465;</span> {participants_display}</span>
    </div>
    <div class="hub-links">{hub_links}</div>
  </header>

  <div class="player-section" id="player-section">
    <div class="player-loading" id="player-loading">
      <div class="spinner"></div>
      Loading recording...
    </div>
    <video id="meeting-video" controls preload="none" style="display:none"></video>
    <div class="player-fallback" id="player-fallback">
      <a href="{audio_url}" target="_blank" rel="noopener">Open recording in Fireflies &rarr;</a>
    </div>
  </div>

  <div class="summary-strip">
    <h3>Summary</h3>
    <p class="summary-text">{summary}</p>
  </div>

  <div class="speaker-legend">
    <span class="speaker-legend-label">Speakers</span>
    {speaker_legend}
  </div>

  <div class="main-content">
    <div class="transcript-panel">
      <h2>Transcript</h2>
      {transcript_html if transcript_html else '<p style="color:#484f58;font-size:13px">No transcript text available.</p>'}
    </div>

    <div class="learnings-panel">
      <div class="learnings-header">
        <h2>Learnings</h2>
        <span class="learnings-count"><span class="num">{pending_count}</span> pending &middot; <span class="num">{approved_count}</span> approved</span>
      </div>
      <p class="learnings-subtitle">Review what was extracted from this conversation</p>

      <div class="filter-bar">
        <button class="filter-btn active" onclick="filterLearnings('all')">All ({len(learnings)})</button>
        {entity_filter_buttons}
        <button class="filter-btn" onclick="filterLearnings('pending')">Pending ({pending_count})</button>
        <button class="filter-btn" onclick="filterLearnings('approved')">Approved ({approved_count})</button>
      </div>

      <div id="learnings-list">
        {learnings_html if learnings_html else '<p style="color:#484f58;font-size:13px">No learnings extracted yet.</p>'}
      </div>
    </div>
  </div>

  <script>
    const SUPABASE_URL = window.__SUPABASE_URL;
    const SUPABASE_KEY = window.__SUPABASE_ANON_KEY;
    const TRANSCRIPT_ID = '{transcript_id}';
    const FIREFLIES_ID = '{fireflies_id}';

    // ── Video player setup ──────────────────────────
    const video = document.getElementById('meeting-video');
    const loading = document.getElementById('player-loading');
    const fallback = document.getElementById('player-fallback');
    const utterances = document.querySelectorAll('.utterance');
    let videoReady = false;

    (async function loadMedia() {{
      try {{
        const resp = await fetch('/api/meetings/media-url?id=' + FIREFLIES_ID);
        const data = await resp.json();

        const src = data.video_url || data.audio_url;
        if (src) {{
          video.src = src;
          video.style.display = 'block';
          loading.style.display = 'none';
          videoReady = true;

          video.addEventListener('error', () => {{
            video.style.display = 'none';
            fallback.style.display = 'block';
          }});
        }} else {{
          loading.style.display = 'none';
          fallback.style.display = 'block';
        }}
      }} catch (e) {{
        loading.style.display = 'none';
        fallback.style.display = 'block';
      }}
    }})();

    // ── Transcript ↔ Video sync ─────────────────────
    // Click utterance → seek video
    utterances.forEach(u => {{
      u.addEventListener('click', (e) => {{
        if (e.target.closest('.btn-approve, .btn-reject')) return;
        const time = parseFloat(u.dataset.time);
        if (videoReady && !isNaN(time)) {{
          video.currentTime = time;
          video.play();
          highlightUtterance(u);
          video.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
        }}
      }});
    }});

    // Video timeupdate → highlight + scroll transcript
    let lastHighlighted = null;
    if (video) {{
      video.addEventListener('timeupdate', () => {{
        const t = video.currentTime;
        let closest = null;
        let closestDist = Infinity;

        utterances.forEach(u => {{
          const uTime = parseFloat(u.dataset.time);
          if (!isNaN(uTime) && uTime <= t) {{
            const dist = t - uTime;
            if (dist < closestDist) {{
              closestDist = dist;
              closest = u;
            }}
          }}
        }});

        if (closest && closest !== lastHighlighted) {{
          highlightUtterance(closest);
          // Auto-scroll transcript panel to keep active line visible
          const panel = closest.closest('.transcript-panel');
          if (panel) {{
            const uTop = closest.offsetTop - panel.offsetTop;
            const panelScroll = panel.scrollTop;
            const panelHeight = panel.clientHeight;
            if (uTop < panelScroll + 60 || uTop > panelScroll + panelHeight - 80) {{
              panel.scrollTo({{ top: uTop - 100, behavior: 'smooth' }});
            }}
          }}
        }}
      }});
    }}

    function highlightUtterance(el) {{
      if (lastHighlighted) lastHighlighted.classList.remove('active');
      el.classList.add('active');
      lastHighlighted = el;
    }}

    // ── Learning approval ───────────────────────────
    async function approveLearning(learningId, approved) {{
      const btn = event.target;
      btn.disabled = true;
      btn.textContent = approved ? 'Saving...' : 'Rejecting...';

      try {{
        const resp = await fetch('/api/meetings/approve-learning', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ learning_id: learningId, approved: approved }})
        }});

        const data = await resp.json();
        if (data.success) {{
          const card = document.getElementById('learning-' + learningId);
          const actions = card.querySelector('.learning-actions');
          if (approved) {{
            card.classList.add('approved');
            card.classList.remove('rejected');
            actions.innerHTML = '<span class="status-tag approved-tag">Approved</span>';
          }} else {{
            card.classList.add('rejected');
            card.classList.remove('approved');
            actions.innerHTML = '<span class="status-tag rejected-tag">Rejected</span>';
          }}
          updateCounts();
        }} else {{
          btn.disabled = false;
          btn.textContent = approved ? 'Agree' : 'Reject';
        }}
      }} catch (err) {{
        btn.disabled = false;
        btn.textContent = approved ? 'Agree' : 'Reject';
      }}
    }}

    function updateCounts() {{
      const cards = document.querySelectorAll('.learning-card');
      let p = 0, a = 0;
      cards.forEach(c => {{
        if (c.classList.contains('approved')) a++;
        else if (!c.classList.contains('rejected')) p++;
      }});
      const counter = document.querySelector('.learnings-count');
      if (counter) counter.innerHTML = '<span class="num">' + p + '</span> pending &middot; <span class="num">' + a + '</span> approved';
    }}

    function filterLearnings(filter) {{
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      event.target.classList.add('active');

      document.querySelectorAll('.learning-card').forEach(card => {{
        if (filter === 'all') {{
          card.style.display = '';
        }} else if (filter === 'pending') {{
          card.style.display = (!card.classList.contains('approved') && !card.classList.contains('rejected')) ? '' : 'none';
        }} else if (filter === 'approved') {{
          card.style.display = card.classList.contains('approved') ? '' : 'none';
        }} else {{
          card.style.display = card.dataset.entity === filter ? '' : 'none';
        }}
      }});
    }}
  </script>
</body>
</html>'''

    return html


# ── Pipeline ─────────────────────────────────────────────────────────────────
def process_transcript(transcript: dict, skip_existing: bool = True) -> Optional[str]:
    """
    Full pipeline for one transcript:
      1. Check if already processed
      2. Detect entities
      3. Store in meeting_transcripts
      4. Extract learnings
      5. Store learnings
      6. Generate HTML page
    Returns the page path or None.
    """
    fireflies_id = transcript.get("id", "")
    if not fireflies_id:
        log.warning("Transcript has no ID, skipping")
        return None

    # Check if already exists
    if skip_existing:
        existing = supa_get("meeting_transcripts", f"fireflies_id=eq.{fireflies_id}&select=id,status")
        if existing:
            log.info("Transcript %s already exists (status=%s), skipping", fireflies_id, existing[0].get("status"))
            return None

    title = transcript.get("title", "Untitled Meeting")
    log.info("Processing transcript: %s (%s)", title, fireflies_id)

    # Detect entities
    entities = detect_entities(transcript)
    log.info("  Entities: %s", entities)

    # Store transcript
    sentences = transcript.get("sentences") or []
    row = supa_post("meeting_transcripts", {
        "fireflies_id": fireflies_id,
        "title": title,
        "date": transcript.get("date"),
        "duration_minutes": transcript.get("duration"),
        "audio_url": transcript.get("audio_url"),
        "transcript_json": {"sentences": sentences},
        "participants": transcript.get("participants") or [],
        "entities": entities,
        "summary": transcript.get("summary", ""),
        "action_items": transcript.get("action_items") or [],
        "status": "processing",
    })

    if not row:
        log.error("  Failed to store transcript in Supabase")
        return None

    transcript_uuid = row["id"]
    log.info("  Stored as %s", transcript_uuid)

    # Extract learnings
    learnings = extract_learnings(transcript, entities)
    log.info("  Extracted %d learnings", len(learnings))

    # Store learnings
    stored_learnings = []
    for l in learnings:
        lr = supa_post("meeting_learnings", {
            "transcript_id": transcript_uuid,
            "entity": l.get("entity", entities[0] if entities else "unknown"),
            "category": l.get("category", "general"),
            "learning": l.get("learning", ""),
            "confidence": l.get("confidence", 0.5),
            "target_table": l.get("target_table"),
            "target_column": l.get("target_column"),
            "target_value": l.get("target_value"),
            "transcript_timestamp": l.get("transcript_timestamp"),
        })
        if lr:
            l["id"] = lr["id"]
            stored_learnings.append(l)

    # Build page data
    page_data = {
        "id": transcript_uuid,
        "title": title,
        "date": transcript.get("date"),
        "duration_minutes": transcript.get("duration"),
        "audio_url": transcript.get("audio_url"),
        "transcript_json": {"sentences": sentences},
        "participants": transcript.get("participants") or [],
        "entities": entities,
        "summary": transcript.get("summary", ""),
    }

    # Generate HTML
    html = generate_meeting_page(page_data, stored_learnings)
    page_path = MEETINGS_DIR / f"{fireflies_id}.html"
    page_path.write_text(html)
    log.info("  Generated page: %s", page_path.relative_to(PROJECT_ROOT))

    # Update transcript status
    supa_patch(
        "meeting_transcripts",
        f"id=eq.{transcript_uuid}",
        {"status": "extracted", "page_path": f"meetings/{fireflies_id}.html", "updated_at": datetime.now(timezone.utc).isoformat()},
    )

    return str(page_path.relative_to(PROJECT_ROOT))


def deploy_changes(pages: list[str]):
    """Commit and push new meeting pages."""
    if not pages:
        return

    log.info("Committing %d new meeting page(s)...", len(pages))
    try:
        for p in pages:
            subprocess.run(["git", "add", p], cwd=str(PROJECT_ROOT), capture_output=True)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        subprocess.run(
            ["git", "commit", "-m", f"[auto] meeting pages generated ({timestamp})",
             "--author=Meeting Sync <noreply@clawdbot.local>"],
            cwd=str(PROJECT_ROOT), capture_output=True,
        )
        result = subprocess.run(
            ["git", "push"],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            log.info("Pushed to git. Vercel will deploy automatically.")
        else:
            log.warning("Git push failed: %s", result.stderr[:300])
    except Exception as e:
        log.error("Deploy error: %s", e)


# ── CLI modes ────────────────────────────────────────────────────────────────
def run_poll(hours: int = 2):
    """Poll Fireflies for new transcripts and generate pages."""
    log.info("=== Meeting Pages Poll (last %d hours) ===", hours)
    transcripts = fetch_recent_transcripts(hours=hours)

    if not transcripts:
        log.info("No new transcripts. Done.")
        return

    pages = []
    for t in transcripts:
        page = process_transcript(t)
        if page:
            pages.append(page)

    deploy_changes(pages)
    log.info("=== Poll complete. %d page(s) generated. ===", len(pages))


def run_generate(fireflies_id: str):
    """Generate page for a specific transcript."""
    log.info("=== Generating page for %s ===", fireflies_id)
    transcript = fetch_single_transcript(fireflies_id)
    if not transcript:
        log.error("Could not fetch transcript %s", fireflies_id)
        return

    page = process_transcript(transcript, skip_existing=False)
    if page:
        deploy_changes([page])
    log.info("=== Generate complete. ===")


def run_rebuild():
    """Regenerate HTML pages for all transcripts in Supabase."""
    log.info("=== Rebuilding all meeting pages ===")
    rows = supa_get("meeting_transcripts", "select=*&order=date.desc")
    if not rows:
        log.info("No transcripts in database.")
        return

    pages = []
    for row in rows:
        learnings = supa_get("meeting_learnings", f"transcript_id=eq.{row['id']}&select=*")
        html = generate_meeting_page(row, learnings)
        fid = row.get("fireflies_id", row["id"])
        page_path = MEETINGS_DIR / f"{fid}.html"
        page_path.write_text(html)
        pages.append(str(page_path.relative_to(PROJECT_ROOT)))
        log.info("  Rebuilt: %s", page_path.name)

    deploy_changes(pages)
    log.info("=== Rebuild complete. %d page(s). ===", len(pages))


def main():
    parser = argparse.ArgumentParser(description="Fireflies Meeting Transcript Page Generator")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--poll", action="store_true", help="Poll Fireflies for new transcripts")
    group.add_argument("--generate", metavar="ID", help="Generate page for a specific transcript ID")
    group.add_argument("--rebuild", action="store_true", help="Rebuild all meeting pages from Supabase")
    parser.add_argument("--hours", type=int, default=2, help="Hours to look back for --poll (default: 2)")
    parser.add_argument("--no-deploy", action="store_true", help="Skip git commit/push")

    args = parser.parse_args()

    if args.no_deploy:
        global deploy_changes
        deploy_changes = lambda pages: log.info("--no-deploy: skipping deploy for %d pages", len(pages))  # noqa: E731

    if args.poll:
        run_poll(hours=args.hours)
    elif args.generate:
        run_generate(args.generate)
    elif args.rebuild:
        run_rebuild()


if __name__ == "__main__":
    main()
