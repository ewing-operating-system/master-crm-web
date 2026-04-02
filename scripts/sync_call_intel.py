#!/usr/bin/env python3
"""
sync_call_intel.py — Call Intelligence Sync for Master CRM Hub Pages

Modes:
  --mode=poll   Poll Fireflies for new transcripts (last 30 min) via claude CLI
  --mode=sync   Read from Salesfinity call_log dump, match to hub pages

For each matched transcript/call:
  - Extracts call intelligence (outcome, contacts, transcript evidence, BANT notes)
  - Injects/updates a "Call Intelligence" section in the company hub HTML
  - Deploys to Vercel

Usage:
  python3 sync_call_intel.py --mode=sync
  python3 sync_call_intel.py --mode=poll
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# ── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT   = Path(__file__).resolve().parent.parent
PUBLIC_DIR     = PROJECT_ROOT / "public"
LOGS_DIR       = PROJECT_ROOT / "logs"
ENV_FILE       = Path.home() / ".openclaw" / ".env"
CALL_LOG_PATH  = Path.home() / "Projects" / "dossier-pipeline" / "data" / "supabase-full-dump" / "call_log.json"

# ── Logging ──────────────────────────────────────────────────────────────────
LOGS_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("sync_call_intel")


# ── Env loader ───────────────────────────────────────────────────────────────
def load_env(path: Path) -> dict:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


ENV = load_env(ENV_FILE)

SUPABASE_URL = os.environ.get("SUPABASE_URL", ENV.get("MASTER_CRM_SUPABASE_URL", "")).rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ENV.get("MASTER_CRM_SUPABASE_SERVICE_ROLE_KEY", ""))


# ── Slug helpers ─────────────────────────────────────────────────────────────
def slugify(text: str) -> str:
    """Convert a company name to a URL-safe slug."""
    text = text.lower().strip()
    # Normalize unicode
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    # Replace common separators with a hyphen
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def find_hub_page(company_name: str) -> Optional[Path]:
    """Return the hub HTML path for a company, or None if not found."""
    slug = slugify(company_name)
    # Direct match: {slug}-hub.html
    direct = PUBLIC_DIR / f"{slug}-hub.html"
    if direct.exists():
        return direct

    # Fuzzy: hub page whose name contains every word in the slug
    words = [w for w in slug.split("-") if len(w) > 2]
    if not words:
        return None
    candidates = list(PUBLIC_DIR.glob("*-hub.html"))
    for c in candidates:
        cname = c.stem.lower()  # e.g. "springer-floor-hub"
        if all(w in cname for w in words):
            return c
    return None


def hub_company_name(hub_path: Path) -> str:
    """Extract the company name from a hub page's <title> or meta tag."""
    html = hub_path.read_text(errors="replace")
    m = re.search(r'<meta\s+name="company-name"\s+content="([^"]+)"', html, re.I)
    if m:
        return m.group(1)
    m = re.search(r"<title>([^<]+?)\s*[—–-]", html)
    if m:
        return m.group(1).strip()
    return hub_path.stem.replace("-hub", "").replace("-", " ").title()


# ── Outcome badge helper ──────────────────────────────────────────────────────
OUTCOME_BADGE = {
    "meeting_set":      ("green",  "Meeting Set"),
    "answered":         ("blue",   "Answered"),
    "voicemail":        ("gray",   "Voicemail"),
    "not_answered":     ("gray",   "Not Answered"),
    "callback":         ("orange", "Callback"),
    "interested":       ("green",  "Interested"),
    "not_interested":   ("red",    "Not Interested"),
    "dnc":              ("red",    "DNC"),
    "follow_up":        ("blue",   "Follow-up"),
    "left_voicemail":   ("gray",   "Voicemail"),
}


def outcome_badge(category: str) -> str:
    key = (category or "").lower().replace(" ", "_")
    color, label = OUTCOME_BADGE.get(key, ("gray", (category or "Unknown").replace("_", " ").title()))
    return f'<span class="badge {color}" style="font-size:10px">{label}</span>'


def fmt_duration(secs: Optional[int]) -> str:
    if not secs:
        return "—"
    m, s = divmod(int(secs), 60)
    return f"{m}:{s:02d}"


def fmt_date(iso: Optional[str]) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%b %-d, %Y")
    except Exception:
        return iso[:10]


# ── HTML injection ────────────────────────────────────────────────────────────
CALL_INTEL_TEMPLATE = """\
    <div class="highlight-card" id="call-intelligence">
        <h2>Call Intelligence</h2>
        <table>
            <tr><th>Date</th><th>Type</th><th>Rep</th><th>Contact</th><th>Duration</th><th>Outcome</th></tr>
{rows}
        </table>
{intel_blocks}
    </div>"""


def build_call_type(record: dict) -> str:
    """Infer call type from BANT details or outcome."""
    bant = record.get("bant_details") or ""
    if isinstance(bant, str):
        try:
            bant = json.loads(bant)
        except Exception:
            bant = {}
    seq = str(bant.get("sequence", "")).lower()
    notes = str(bant.get("notes", "")).lower()
    called_at = record.get("called_at", "")
    if "follow" in seq or "follow" in notes:
        return "Follow-up"
    if record.get("outcome_category") in ("voicemail", "not_answered"):
        return "Cold Call"
    if record.get("is_valuable"):
        return "Discovery"
    return "Cold Call"


def build_intel_narrative(record: dict) -> str:
    """Build narrative text from transcript_evidence and bant_details."""
    lines = []

    # BANT / disposition notes
    bant = record.get("bant_details") or ""
    if isinstance(bant, str):
        try:
            bant = json.loads(bant)
        except Exception:
            bant = {}
    if isinstance(bant, dict):
        if bant.get("notes"):
            lines.append(f"<strong>Notes:</strong> {bant['notes']}")
        if bant.get("disposition"):
            lines.append(f"<strong>Disposition:</strong> {bant['disposition']}")

    # Transcript evidence (skip full_transcript entries, use meaningful facets)
    evidence = record.get("transcript_evidence") or []
    seen = set()
    for ev in evidence:
        if isinstance(ev, dict):
            facet = ev.get("facet", "")
            text  = ev.get("text", "").strip()
            if facet == "full_transcript" or not text or text in seen:
                continue
            if len(text) > 600:
                text = text[:600] + "…"
            seen.add(text)
            label = facet.replace("_", " ").title() if facet else "Evidence"
            lines.append(f"<strong>{label}:</strong> {text}")

    # Value signals
    signals = record.get("value_signals") or []
    if signals:
        lines.append(f"<strong>Value Signals:</strong> {'; '.join(str(s) for s in signals[:5])}")

    # Coaching wins
    wins = record.get("coaching_wins") or []
    if wins:
        lines.append(f"<strong>Coaching Wins:</strong> {'; '.join(str(w) for w in wins[:3])}")

    # Score
    score = record.get("total_score")
    if score:
        lines.append(f"<strong>Call Quality Score:</strong> {score}/100")

    if not lines:
        return ""
    return "\n\n".join(lines)


def build_call_intel_html(records: list[dict]) -> str:
    """Build the full call-intelligence highlight-card HTML from a list of call records."""
    rows = []
    intel_blocks = []

    for rec in records:
        date_str     = fmt_date(rec.get("called_at"))
        call_type    = build_call_type(rec)
        rep          = rec.get("rep_name") or "—"
        contact      = rec.get("contact_name") or "—"
        duration     = fmt_duration(rec.get("duration_sec"))
        badge        = outcome_badge(rec.get("outcome_category", ""))

        rows.append(
            f"            <tr>\n"
            f"                <td>{date_str}</td>\n"
            f"                <td>{call_type}</td>\n"
            f"                <td>{rep}</td>\n"
            f"                <td>{contact}</td>\n"
            f"                <td>{duration}</td>\n"
            f"                <td>{badge}</td>\n"
            f"            </tr>"
        )

        narrative = build_intel_narrative(rec)
        if narrative:
            intel_blocks.append(
                f'        <div style="margin-top:16px">\n'
                f'            <div class="script-label">Key Intel from {date_str} Call</div>\n'
                f'            <div class="narrative-box">{narrative}</div>\n'
                f'        </div>'
            )

    rows_html   = "\n".join(rows)
    blocks_html = "\n".join(intel_blocks)
    return CALL_INTEL_TEMPLATE.format(rows=rows_html, intel_blocks=blocks_html)


def inject_call_intel(hub_path: Path, records: list[dict]) -> bool:
    """
    Inject or replace the call-intelligence section in hub_path.
    Returns True if the file was modified.
    """
    html = hub_path.read_text(errors="replace")
    new_section = build_call_intel_html(records)

    # Pattern to match existing call-intelligence div (handles multiline)
    pattern = re.compile(
        r'<div\s[^>]*id=["\']call-intelligence["\'][^>]*>.*?(?=\n\s*<div\s|\Z)',
        re.DOTALL,
    )

    if pattern.search(html):
        updated = pattern.sub(new_section, html, count=1)
        log.info("  Replaced existing call-intelligence section in %s", hub_path.name)
    else:
        # No existing section — insert before </main> or before the first card after contacts
        insert_after = re.search(
            r'(</div>\s*\n)(\s*<div\s[^>]*id=["\']proposal["\'])',
            html, re.DOTALL
        )
        if insert_after:
            pos = insert_after.start(2)
            updated = html[:pos] + new_section + "\n\n    " + html[pos:]
            log.info("  Inserted new call-intelligence section into %s", hub_path.name)
        else:
            # Fallback: append before </main>
            updated = html.replace("</main>", new_section + "\n\n</main>", 1)
            log.info("  Appended call-intelligence section to %s", hub_path.name)

    if updated == html:
        log.info("  No change to %s", hub_path.name)
        return False

    hub_path.write_text(updated)
    return True


# ── Supabase helper ───────────────────────────────────────────────────────────
def supabase_get(table: str, params: str = "") -> list:
    """Simple Supabase REST GET."""
    import urllib.request
    import urllib.error

    url = f"{SUPABASE_URL}/rest/v1/{table}?{params}"
    req = urllib.request.Request(
        url,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        log.error("Supabase error %s: %s", e.code, e.read().decode())
        return []


# ── POLL MODE — Fireflies via claude CLI ──────────────────────────────────────
FIREFLIES_PROMPT_TEMPLATE = """\
Use the Fireflies MCP tool to fetch transcripts from the last 30 minutes.
Call: mcp__claude_ai_Fireflies__fireflies_get_recent_transcripts with fromDate set to {from_iso}
or use mcp__claude_ai_Fireflies__fireflies_search with a date range query.

Return ONLY a JSON array (no markdown, no prose). Each element must have:
{{
  "transcript_id": "...",
  "title": "...",
  "date": "ISO-8601 datetime",
  "duration_seconds": 123,
  "participants": [{{"email": "...", "name": "..."}}],
  "summary": "...",
  "action_items": ["..."],
  "transcript_text": "first 2000 chars of transcript"
}}

If there are no transcripts in the last 30 minutes, return an empty JSON array: []
"""


def poll_fireflies() -> list[dict]:
    """Use `claude -p` to invoke Fireflies MCP and return transcript dicts."""
    from_dt  = datetime.now(timezone.utc) - timedelta(minutes=30)
    from_iso = from_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    prompt   = FIREFLIES_PROMPT_TEMPLATE.format(from_iso=from_iso)

    log.info("Invoking claude CLI for Fireflies poll (last 30 min since %s)…", from_iso)
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text"],
            capture_output=True, text=True, timeout=120
        )
    except FileNotFoundError:
        log.error("claude CLI not found — cannot run poll mode")
        return []
    except subprocess.TimeoutExpired:
        log.error("claude CLI timed out waiting for Fireflies response")
        return []

    raw = result.stdout.strip()
    if result.returncode != 0:
        log.error("claude CLI error: %s", result.stderr[:500])
        return []

    # Extract JSON array from response (claude may wrap in prose)
    m = re.search(r"(\[.*\])", raw, re.DOTALL)
    if not m:
        if raw in ("", "[]"):
            log.info("No new Fireflies transcripts in last 30 minutes.")
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


def match_fireflies_to_hub(transcript: dict) -> Optional[Path]:
    """
    Match a Fireflies transcript to a hub page.
    Tries: participant emails vs Supabase targets, then company name keywords.
    """
    # Try to match participant domains to known companies
    participants = transcript.get("participants") or []
    emails = [p.get("email", "") for p in participants if p.get("email")]
    domains = set()
    for email in emails:
        if "@" in email:
            domain = email.split("@")[1].lower()
            # Skip common personal/work domains
            if domain not in ("gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
                              "revsup.com", "nextchapteradvisory.com"):
                domains.add(domain)

    # Query Supabase targets for matching emails/domains
    if domains:
        for domain in domains:
            # Search by email domain in extra_fields
            rows = supabase_get(
                "targets",
                f"select=company_name&extra_fields->>email=ilike.*{domain}*&limit=3"
            )
            for row in rows:
                hub = find_hub_page(row.get("company_name", ""))
                if hub:
                    log.info("  Matched transcript '%s' to %s via email domain %s",
                             transcript.get("title", ""), hub.name, domain)
                    return hub

    # Keyword match via transcript title
    title = transcript.get("title", "")
    if title:
        hub = find_hub_page(title)
        if hub:
            return hub

    # Try hub page names vs transcript text
    text = transcript.get("transcript_text", "") + " " + transcript.get("summary", "")
    for hub_file in PUBLIC_DIR.glob("*-hub.html"):
        company = hub_company_name(hub_file)
        slug_words = [w for w in slugify(company).split("-") if len(w) > 3]
        if slug_words and all(w in text.lower() for w in slug_words[:2]):
            log.info("  Matched transcript '%s' to %s via keyword scan", title, hub_file.name)
            return hub_file

    return None


def fireflies_transcript_to_call_record(t: dict) -> dict:
    """Convert a Fireflies transcript dict to a synthetic call_log-style record."""
    participants = t.get("participants") or []
    contact_name  = next((p.get("name", "") for p in participants
                          if p.get("email", "").split("@")[-1] not in
                          ("revsup.com", "nextchapteradvisory.com")), "")
    contact_email = next((p.get("email", "") for p in participants
                          if p.get("email", "").split("@")[-1] not in
                          ("revsup.com", "nextchapteradvisory.com")), "")
    rep_name      = next((p.get("name", "") for p in participants
                          if p.get("email", "").split("@")[-1] in
                          ("revsup.com", "nextchapteradvisory.com")), "")

    evidence = []
    if t.get("transcript_text"):
        evidence.append({"text": t["transcript_text"][:2000], "facet": "full_transcript", "source": "fireflies"})
    if t.get("summary"):
        evidence.append({"text": t["summary"], "facet": "call_summary", "source": "fireflies"})
    for item in (t.get("action_items") or []):
        evidence.append({"text": item, "facet": "action_item", "source": "fireflies"})

    return {
        "call_id": t.get("transcript_id", ""),
        "rep_name": rep_name,
        "contact_name": contact_name,
        "contact_email": contact_email,
        "contact_company": "",
        "duration_sec": t.get("duration_seconds"),
        "outcome_category": "answered",
        "called_at": t.get("date", ""),
        "is_valuable": True,
        "value_signals": [],
        "transcript_evidence": evidence,
        "bant_details": {},
        "coaching_wins": [],
        "total_score": None,
    }


# ── SYNC MODE — Salesfinity call_log dump ────────────────────────────────────
def load_call_log() -> list[dict]:
    if not CALL_LOG_PATH.exists():
        log.error("call_log.json not found at %s", CALL_LOG_PATH)
        return []
    with open(CALL_LOG_PATH) as f:
        data = json.load(f)
    log.info("Loaded %d call_log records", len(data))
    return data if isinstance(data, list) else []


def group_calls_by_company(records: list[dict]) -> dict[str, list[dict]]:
    """Group call records by contact_company name."""
    groups: dict[str, list[dict]] = {}
    for rec in records:
        company = (rec.get("contact_company") or "").strip()
        if not company:
            continue
        groups.setdefault(company, []).append(rec)
    return groups


def sort_records(records: list[dict]) -> list[dict]:
    """Sort records newest-first."""
    def key(r):
        try:
            return datetime.fromisoformat((r.get("called_at") or "2000-01-01").replace("Z", "+00:00"))
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)
    return sorted(records, key=key, reverse=True)


# ── Vercel deploy ─────────────────────────────────────────────────────────────
def deploy_vercel():
    log.info("Deploying to Vercel…")
    result = subprocess.run(
        ["npx", "vercel", "--prod", "--yes"],
        capture_output=True, text=True, timeout=300,
        cwd=str(PROJECT_ROOT),
    )
    if result.returncode == 0:
        # Extract deployment URL from output
        url_match = re.search(r"https://[^\s]+\.vercel\.app", result.stdout)
        url = url_match.group(0) if url_match else "(see output)"
        log.info("Vercel deploy succeeded: %s", url)
    else:
        log.error("Vercel deploy failed:\n%s\n%s", result.stdout[-500:], result.stderr[-500:])


# ── Main ──────────────────────────────────────────────────────────────────────
def run_poll_mode():
    transcripts = poll_fireflies()
    if not transcripts:
        log.info("No new transcripts — nothing to do.")
        return

    modified = []
    for t in transcripts:
        hub = match_fireflies_to_hub(t)
        if not hub:
            log.warning("No hub page matched for transcript: %s", t.get("title", "(no title)"))
            continue

        record = fireflies_transcript_to_call_record(t)
        changed = inject_call_intel(hub, [record])
        if changed:
            modified.append(hub.name)

    if modified:
        log.info("Updated %d hub page(s): %s", len(modified), ", ".join(modified))
        deploy_vercel()
    else:
        log.info("No hub pages modified — skipping deploy.")


def run_sync_mode():
    records = load_call_log()
    if not records:
        log.info("No call records found — nothing to do.")
        return

    groups = group_calls_by_company(records)
    log.info("Found %d distinct companies in call_log", len(groups))

    modified = []
    skipped  = []

    for company, company_records in groups.items():
        hub = find_hub_page(company)
        if not hub:
            skipped.append(company)
            continue

        sorted_recs = sort_records(company_records)
        # Limit to 10 most recent calls per company to keep the page manageable
        top_recs = sorted_recs[:10]

        log.info("Processing %s (%d calls) → %s", company, len(top_recs), hub.name)
        changed = inject_call_intel(hub, top_recs)
        if changed:
            modified.append(hub.name)

    if skipped:
        log.warning(
            "Skipped %d companies with no hub page: %s",
            len(skipped),
            ", ".join(skipped[:20]) + ("…" if len(skipped) > 20 else ""),
        )

    if modified:
        log.info("Updated %d hub page(s): %s", len(modified), ", ".join(modified))
        deploy_vercel()
    else:
        log.info("No hub pages modified — skipping deploy.")


def main():
    parser = argparse.ArgumentParser(description="Sync call intelligence to hub pages")
    parser.add_argument(
        "--mode",
        choices=["poll", "sync"],
        default="sync",
        help="poll = Fireflies API via claude CLI; sync = Salesfinity call_log dump",
    )
    parser.add_argument(
        "--no-deploy",
        action="store_true",
        help="Skip Vercel deploy (useful for testing)",
    )
    args = parser.parse_args()

    log.info("=== sync_call_intel.py  mode=%s  %s ===",
             args.mode, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # Monkey-patch deploy if --no-deploy
    if args.no_deploy:
        global deploy_vercel
        deploy_vercel = lambda: log.info("--no-deploy: skipping Vercel deploy")  # noqa: E731

    if args.mode == "poll":
        run_poll_mode()
    else:
        run_sync_mode()

    log.info("Done.")


if __name__ == "__main__":
    main()
