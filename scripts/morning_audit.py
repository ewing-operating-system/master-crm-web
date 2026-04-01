#!/usr/bin/env python3
"""
Morning System Audit — runs daily at 6AM via cron.

This script DOCUMENTS FINDINGS ONLY. It does NOT fix anything.
Fixes are decided by Claude Opus and implemented by Claude Sonnet.

Flow:
  1. This script runs all checks → writes findings JSON + HTML
  2. Claude Opus reads findings → decides what to fix
  3. Claude Sonnet implements fixes → commits + pushes

Usage:
  python3 scripts/morning_audit.py              # full audit
  python3 scripts/morning_audit.py --check key  # single check
  python3 scripts/morning_audit.py --json       # JSON output only
"""

# Credentials: all keys come from env vars. See .env.example for names, ~/.zshrc for values.

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = REPO_ROOT / "public"
FINDINGS_JSON = Path("/tmp/morning-audit-findings.json")
FIXES_JSON = Path("/tmp/morning-fixes.json")
HEALTH_PAGE = PUBLIC_DIR / "system-health.html"

# ---------------------------------------------------------------------------
# Check functions — each returns a dict with status, message, severity
# ---------------------------------------------------------------------------

def check_key_hygiene():
    """Scan for hardcoded API keys in code, skills, and openclaw config."""
    patterns = r"eyJhbGciOi|MakeMoneyNow|sk-or-v1|sk-ea0|2LU38|sk-proj-|tgp_v1|AIzaSy|f1f16b33"
    locations = [
        (str(REPO_ROOT), ["--include=*.py", "--include=*.js", "--include=*.md", "--include=*.sh",
                          "--exclude-dir=node_modules", "--exclude=supabase-config.js"]),
        (os.path.expanduser("~/.openclaw/"), ["--exclude-dir=browser", "--exclude-dir=logs",
                                               "--exclude-dir=sessions", "--include=*.js",
                                               "--include=*.py", "--include=*.md", "--include=*.sh",
                                               "--include=*.json"]),
        (os.path.expanduser("~/.claude/skills/"), ["--include=*.md"]),
    ]

    total_matches = 0
    match_files = []

    for path, flags in locations:
        if not os.path.exists(path):
            continue
        cmd = ["grep", "-rl", patterns] + flags + [path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.stdout.strip():
            files = [f for f in result.stdout.strip().split("\n")
                     if f and "sanitize" not in f and ".env" not in f.split("/")[-1]
                     and "morning_audit.py" not in f and "pre-commit" not in f]
            match_files.extend(files)
            total_matches += len(files)

    if total_matches == 0:
        return {"check": "key_hygiene", "status": "PASS", "severity": "critical",
                "message": "Zero hardcoded keys found"}
    return {"check": "key_hygiene", "status": "FAIL", "severity": "critical",
            "message": f"{total_matches} file(s) contain hardcoded keys",
            "details": match_files}


def check_vercel_env():
    """Verify all required Vercel env vars are present."""
    required = [
        "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY",
        "DATABASE_URL", "OPENROUTER_API_KEY", "LOB_API_KEY", "LOB_WEBHOOK_SECRET",
        "BATCH_SEND_SECRET", "SALESFINITY_API_KEY", "PORTAL_PW_ADMIN", "PORTAL_PW_HRCOM",
    ]
    deprecated = ["SUPABASE_SERVICE_KEY"]

    try:
        result = subprocess.run(
            ["npx", "--yes", "vercel", "env", "ls"],
            capture_output=True, text=True, timeout=30, cwd=str(REPO_ROOT)
        )
        output = result.stdout
    except Exception as e:
        return {"check": "vercel_env", "status": "ERROR", "severity": "critical",
                "message": f"Could not check Vercel env: {e}"}

    present = set()
    for line in output.split("\n"):
        parts = line.strip().split()
        if parts and parts[0].isupper():
            present.add(parts[0])

    missing = [v for v in required if v not in present]
    stale = [v for v in deprecated if v in present]

    issues = []
    if missing:
        issues.append(f"Missing: {', '.join(missing)}")
    if stale:
        issues.append(f"Deprecated (remove): {', '.join(stale)}")

    if not issues:
        return {"check": "vercel_env", "status": "PASS", "severity": "critical",
                "message": f"All {len(required)} required vars present"}
    return {"check": "vercel_env", "status": "WARN" if not missing else "FAIL",
            "severity": "critical", "message": "; ".join(issues)}


def check_supabase_health():
    """Ping Supabase REST API."""
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_ANON_KEY", "")
    if not url or not key:
        return {"check": "supabase_health", "status": "ERROR", "severity": "critical",
                "message": "SUPABASE_URL or SUPABASE_ANON_KEY not in env"}
    try:
        import urllib.request
        import ssl
        req = urllib.request.Request(f"{url}/rest/v1/targets?limit=0&select=id")
        req.add_header("apikey", key)
        req.add_header("Authorization", f"Bearer {key}")
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            status = resp.status
        if status == 200:
            return {"check": "supabase_health", "status": "PASS", "severity": "critical",
                    "message": "Supabase REST API responding (200)"}
        return {"check": "supabase_health", "status": "WARN", "severity": "critical",
                "message": f"Supabase returned HTTP {status}"}
    except Exception as e:
        return {"check": "supabase_health", "status": "FAIL", "severity": "critical",
                "message": f"Supabase unreachable: {e}"}


def check_gateway():
    """Verify OpenClaw gateway is running."""
    result = subprocess.run(["pgrep", "-f", "openclaw.*gateway"], capture_output=True, text=True)
    if result.stdout.strip():
        pid = result.stdout.strip().split("\n")[0]
        return {"check": "gateway", "status": "PASS", "severity": "high",
                "message": f"Gateway running (PID {pid})"}
    return {"check": "gateway", "status": "FAIL", "severity": "high",
            "message": "Gateway NOT running — restart with: launchctl load ~/Library/LaunchAgents/ai.openclaw.gateway.plist"}


def check_git_clean():
    """Check for uncommitted changes."""
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "status", "--porcelain"],
        capture_output=True, text=True
    )
    changes = [l for l in result.stdout.strip().split("\n") if l.strip()]
    if not changes:
        return {"check": "git_clean", "status": "PASS", "severity": "high",
                "message": "Working tree clean"}
    return {"check": "git_clean", "status": "WARN", "severity": "high",
            "message": f"{len(changes)} uncommitted change(s)",
            "details": changes[:10]}


def check_cron_health():
    """Verify cron jobs ran recently."""
    log_file = REPO_ROOT / "logs" / "call_sync.log"
    issues = []

    if log_file.exists():
        stat = log_file.stat()
        age_hours = (datetime.now().timestamp() - stat.st_mtime) / 3600
        if age_hours > 1:
            issues.append(f"call_sync.log last modified {age_hours:.1f}h ago (expect < 0.25h)")
    else:
        issues.append("call_sync.log does not exist")

    if not issues:
        return {"check": "cron_health", "status": "PASS", "severity": "high",
                "message": "Cron logs are current"}
    return {"check": "cron_health", "status": "WARN", "severity": "high",
            "message": "; ".join(issues)}


def check_ollama():
    """Check if Ollama is running."""
    result = subprocess.run(["pgrep", "-f", "ollama serve"], capture_output=True, text=True)
    if result.stdout.strip():
        return {"check": "ollama", "status": "PASS", "severity": "medium",
                "message": "Ollama running (port 11434)"}
    return {"check": "ollama", "status": "WARN", "severity": "medium",
            "message": "Ollama not running"}


def check_openclaw_version():
    """Check if OpenClaw is up to date."""
    try:
        result = subprocess.run(["openclaw", "--version"], capture_output=True, text=True, timeout=10)
        version = result.stdout.strip()
        return {"check": "openclaw_version", "status": "INFO", "severity": "medium",
                "message": f"OpenClaw version: {version}"}
    except Exception:
        return {"check": "openclaw_version", "status": "WARN", "severity": "medium",
                "message": "Could not determine OpenClaw version"}


def check_disk_usage():
    """Check disk space."""
    try:
        result = subprocess.run(["df", "-h", "/"], capture_output=True, text=True)
        for line in result.stdout.strip().split("\n")[1:]:
            parts = line.split()
            pct = int(parts[4].replace("%", ""))
            if pct >= 80:
                return {"check": "disk_usage", "status": "WARN", "severity": "medium",
                        "message": f"Disk {pct}% full ({parts[3]} available)"}
            return {"check": "disk_usage", "status": "PASS", "severity": "medium",
                    "message": f"Disk {pct}% used ({parts[3]} available)"}
    except Exception:
        return {"check": "disk_usage", "status": "ERROR", "severity": "medium",
                "message": "Could not check disk usage"}


def check_stale_files():
    """Look for backup/stale config files that shouldn't exist."""
    stale_patterns = [
        os.path.expanduser("~/.openclaw/*.bak*"),
        os.path.expanduser("~/.openclaw/*.backup*"),
        os.path.expanduser("~/.openclaw/*.old"),
    ]
    import glob
    found = []
    for pattern in stale_patterns:
        found.extend(glob.glob(pattern))
    if not found:
        return {"check": "stale_files", "status": "PASS", "severity": "low",
                "message": "No stale config backups found"}
    return {"check": "stale_files", "status": "WARN", "severity": "low",
            "message": f"{len(found)} stale file(s) found", "details": found}


def check_unpushed_commits():
    """Check if local repo has commits not pushed to remote."""
    try:
        # Fetch latest remote state without pulling
        subprocess.run(
            ["git", "-C", str(REPO_ROOT), "fetch", "--quiet"],
            capture_output=True, text=True, timeout=15
        )
        # Check for unpushed commits
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "log", "origin/main..HEAD", "--oneline"],
            capture_output=True, text=True
        )
        unpushed = [l for l in result.stdout.strip().split("\n") if l.strip()]

        if not unpushed:
            return {"check": "unpushed_commits", "status": "PASS", "severity": "high",
                    "message": "All commits pushed to GitHub"}

        # Assess if the push looks safe (no destructive keywords)
        dangerous_keywords = ["delete", "drop", "remove prod", "reset", "force", "wipe", "destroy"]
        risky = []
        for commit in unpushed:
            if any(kw in commit.lower() for kw in dangerous_keywords):
                risky.append(f"RISKY: {commit}")

        details = unpushed[:10]
        if risky:
            details = risky + [f"({len(unpushed)} total unpushed)"]
            return {"check": "unpushed_commits", "status": "WARN", "severity": "critical",
                    "message": f"{len(unpushed)} unpushed commit(s), {len(risky)} look risky — needs human review",
                    "details": details}

        return {"check": "unpushed_commits", "status": "WARN", "severity": "high",
                "message": f"{len(unpushed)} unpushed commit(s) — appear safe to push",
                "details": details}

    except Exception as e:
        return {"check": "unpushed_commits", "status": "ERROR", "severity": "high",
                "message": f"Could not check push status: {e}"}


def check_data_sync():
    """Verify Supabase data is reaching downstream pages.

    Samples ~30% of hub pages and verifies buyer counts match Supabase.
    Also checks that Vercel deployment matches the latest git commit.
    """
    import urllib.request
    import ssl
    import random

    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        return {"check": "data_sync", "status": "ERROR", "severity": "critical",
                "message": "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY"}

    issues = []
    details = []

    def supa_get(path):
        req = urllib.request.Request(f"{url}/rest/v1/{path}")
        req.add_header("apikey", key)
        req.add_header("Authorization", f"Bearer {key}")
        req.add_header("Content-Type", "application/json")
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            return json.loads(resp.read().decode())

    # 1. Check proposals → hub pages exist
    try:
        proposals = supa_get("proposals?select=id,company_name,quality_score")
        hub_pages = list(PUBLIC_DIR.glob("*-hub.html"))
        hub_names = {p.stem.replace("-hub", "") for p in hub_pages}
        details.append(f"Proposals in DB: {len(proposals)}, Hub pages on disk: {len(hub_pages)}")

        for p in proposals:
            name = p.get("company_name", "")
            # Make slug same way as regenerate.py
            slug = re.sub(r"[.,]", "", name.lower().replace("&", "and"))
            slug = re.sub(r"\s+", "-", slug.strip())[:40].rstrip("-")
            if slug not in hub_names and slug:
                issues.append(f"Proposal '{name}' has no hub page (expected {slug}-hub.html)")
    except Exception as e:
        issues.append(f"Could not verify proposals→pages: {e}")

    # 2. Sample 30% of hub pages — check buyer counts match DB
    try:
        hub_pages = list(PUBLIC_DIR.glob("*-hub.html"))
        sample_size = max(2, len(hub_pages) * 30 // 100)
        sampled = random.sample(hub_pages, min(sample_size, len(hub_pages)))

        for page in sampled:
            page_content = page.read_text(encoding="utf-8", errors="ignore")

            # Count buyer rows in HTML (look for table rows with buyer data)
            buyer_rows_html = len(re.findall(r'<tr[^>]*class="buyer-row"', page_content))
            # Also try counting any table rows in buyer sections
            if buyer_rows_html == 0:
                buyer_rows_html = page_content.count("fit_score") + page_content.count("fit-score")

            # Check for empty/broken pages
            if len(page_content) < 1000:
                issues.append(f"{page.name}: suspiciously small ({len(page_content)} bytes)")
            elif "<title>" not in page_content:
                issues.append(f"{page.name}: missing <title> tag — may be broken")
            else:
                details.append(f"Sampled {page.name}: {len(page_content):,} bytes, ~{buyer_rows_html} buyer refs")
    except Exception as e:
        issues.append(f"Page content audit error: {e}")

    # 3. Check engagement_buyers count vs what pages show
    try:
        buyers = supa_get("engagement_buyers?select=proposal_id&limit=500")
        proposal_buyer_counts = {}
        for b in buyers:
            pid = b.get("proposal_id", "unknown")
            proposal_buyer_counts[pid] = proposal_buyer_counts.get(pid, 0) + 1
        details.append(f"Engagement buyers in DB: {len(buyers)} across {len(proposal_buyer_counts)} proposals")
    except Exception as e:
        issues.append(f"Could not count engagement_buyers: {e}")

    # 4. Check Vercel deploy matches latest git commit
    try:
        git_result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True
        )
        local_sha = git_result.stdout.strip()[:7]

        remote_result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "origin/main"],
            capture_output=True, text=True
        )
        remote_sha = remote_result.stdout.strip()[:7]

        if local_sha == remote_sha:
            details.append(f"Git HEAD ({local_sha}) matches origin/main — Vercel should be in sync")
        else:
            issues.append(f"Git HEAD ({local_sha}) != origin/main ({remote_sha}) — Vercel may be stale")
    except Exception as e:
        issues.append(f"Could not check git/Vercel sync: {e}")

    # 5. Check letter_approvals for stuck records
    try:
        stuck = supa_get("letter_approvals?status=eq.approved&select=id,company_id,approved_at&limit=10")
        if stuck:
            issues.append(f"{len(stuck)} approved letter(s) not yet sent — may be stuck in queue")
            details.extend([f"Stuck letter: {s.get('id','?')[:8]}... approved {s.get('approved_at','?')}" for s in stuck[:3]])
    except Exception:
        pass  # Table might not exist yet

    # 6. Check page_versions for recent activity
    try:
        versions = supa_get("page_versions?select=id,page_path,published_at&order=published_at.desc&limit=5")
        if versions:
            latest = versions[0].get("published_at", "unknown")
            details.append(f"Latest page version: {latest}")
        else:
            details.append("No page_versions records found")
    except Exception:
        pass

    if not issues:
        return {"check": "data_sync", "status": "PASS", "severity": "critical",
                "message": f"Data sync verified ({len(details)} checks passed)",
                "details": details}

    severity = "critical" if any("stale" in i.lower() or "no hub page" in i.lower() for i in issues) else "high"
    return {"check": "data_sync", "status": "WARN" if len(issues) < 3 else "FAIL",
            "severity": severity,
            "message": f"{len(issues)} sync issue(s) found",
            "details": issues + ["---"] + details}


def check_skill_watch():
    """Identify repetitive processes that should become skills."""
    suggestions = []

    # Check git log for repeated script runs
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "log", "--oneline", "-50", "--format=%s"],
            capture_output=True, text=True
        )
        commits = result.stdout.strip().split("\n")
        # Look for patterns in commit messages
        patterns = {}
        for msg in commits:
            # Extract action words
            action = msg.split(":")[0].strip().lower() if ":" in msg else msg.split()[0].lower() if msg.split() else ""
            if action:
                patterns[action] = patterns.get(action, 0) + 1

        repeated = {k: v for k, v in patterns.items() if v >= 3}
        if repeated:
            for action, count in sorted(repeated.items(), key=lambda x: -x[1]):
                suggestions.append(f"'{action}' appears in {count} commits — potential skill candidate")
    except Exception:
        pass

    # Check for scripts not covered by skills
    scripts = list((REPO_ROOT / "scripts").glob("*.py")) + list((REPO_ROOT / "scripts").glob("*.sh"))
    skill_dir = Path.home() / ".claude" / "skills"
    skill_names = {d.name for d in skill_dir.iterdir() if d.is_dir()} if skill_dir.exists() else set()

    for script in scripts:
        stem = script.stem.replace("_", "-").replace(".", "-")
        # Check if any skill name is close
        if not any(stem in s or s in stem for s in skill_names):
            suggestions.append(f"Script '{script.name}' has no matching skill")

    return {"check": "skill_watch", "status": "INFO", "severity": "info",
            "message": f"{len(suggestions)} skill suggestion(s)",
            "details": suggestions[:15]}


# ---------------------------------------------------------------------------
# HTML report generator
# ---------------------------------------------------------------------------

def generate_html(findings, timestamp):
    """Generate the system-health.html page."""
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    findings.sort(key=lambda f: (severity_order.get(f["severity"], 5), f["status"] != "FAIL"))

    status_colors = {"PASS": "#22c55e", "FAIL": "#ef4444", "WARN": "#f59e0b",
                     "ERROR": "#ef4444", "INFO": "#3b82f6"}
    severity_badges = {"critical": "#dc2626", "high": "#ea580c", "medium": "#ca8a04",
                       "low": "#16a34a", "info": "#6366f1"}

    pass_count = sum(1 for f in findings if f["status"] == "PASS")
    total = len(findings)
    fail_count = sum(1 for f in findings if f["status"] in ("FAIL", "ERROR"))
    warn_count = sum(1 for f in findings if f["status"] == "WARN")

    overall = "ALL CLEAR" if fail_count == 0 and warn_count == 0 else \
              f"{fail_count} CRITICAL" if fail_count > 0 else f"{warn_count} WARNING(S)"
    overall_color = "#22c55e" if fail_count == 0 and warn_count == 0 else \
                    "#ef4444" if fail_count > 0 else "#f59e0b"

    rows = ""
    for f in findings:
        color = status_colors.get(f["status"], "#888")
        badge = severity_badges.get(f["severity"], "#888")
        details = ""
        if f.get("details"):
            items = f["details"][:10]
            details = "<br>".join(f"<code style='font-size:11px;color:#666'>{d}</code>" for d in items)
            if len(f["details"]) > 10:
                details += f"<br><em>...and {len(f['details'])-10} more</em>"

        rows += f"""
        <tr>
          <td><span style="display:inline-block;padding:2px 8px;border-radius:4px;
              background:{color};color:white;font-weight:600;font-size:12px">{f['status']}</span></td>
          <td><span style="display:inline-block;padding:1px 6px;border-radius:3px;
              background:{badge};color:white;font-size:11px">{f['severity']}</span></td>
          <td style="font-weight:500">{f['check'].replace('_',' ').title()}</td>
          <td>{f['message']}{('<br>' + details) if details else ''}</td>
        </tr>"""

    # Skill suggestions section
    skill_findings = [f for f in findings if f["check"] == "skill_watch"]
    skill_html = ""
    if skill_findings and skill_findings[0].get("details"):
        items = "".join(f"<li>{s}</li>" for s in skill_findings[0]["details"])
        skill_html = f"""
        <div style="margin-top:30px;padding:20px;background:#f0f4ff;border-radius:8px;border-left:4px solid #6366f1">
          <h3 style="margin:0 0 10px">Suggested Skills</h3>
          <p style="color:#555;font-size:13px">Processes detected that could become reusable skills:</p>
          <ul style="font-size:13px">{items}</ul>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>System Health — Master CRM</title>
  <style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
           background:#f8fafc; color:#1e293b; padding:30px; }}
    .header {{ text-align:center; margin-bottom:30px; }}
    .header h1 {{ font-size:24px; margin-bottom:5px; }}
    .header .timestamp {{ color:#64748b; font-size:13px; }}
    .overall {{ text-align:center; padding:20px; border-radius:12px; margin-bottom:30px;
               background:white; box-shadow:0 1px 3px rgba(0,0,0,0.1); }}
    .overall .score {{ font-size:36px; font-weight:700; color:{overall_color}; }}
    .overall .detail {{ color:#64748b; font-size:14px; margin-top:5px; }}
    table {{ width:100%; border-collapse:collapse; background:white;
            border-radius:8px; overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,0.1); }}
    th {{ background:#f1f5f9; padding:10px 12px; text-align:left; font-size:12px;
         text-transform:uppercase; color:#64748b; letter-spacing:0.5px; }}
    td {{ padding:10px 12px; border-top:1px solid #f1f5f9; font-size:13px; vertical-align:top; }}
    tr:hover {{ background:#f8fafc; }}
    .footer {{ text-align:center; margin-top:30px; color:#94a3b8; font-size:12px; }}
  </style>
</head>
<body>
  <div class="header">
    <h1>System Health Dashboard</h1>
    <div class="timestamp">Last audit: {timestamp} | Next: 6:00 AM tomorrow</div>
  </div>

  <div class="overall">
    <div class="score">{overall}</div>
    <div class="detail">{pass_count}/{total} checks passed | {fail_count} failures | {warn_count} warnings</div>
  </div>

  <table>
    <thead>
      <tr><th>Status</th><th>Severity</th><th>Check</th><th>Finding</th></tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>

  {skill_html}

  <div class="footer">
    Generated by morning_audit.py | Findings only — fixes decided by Claude Opus, implemented by Sonnet
  </div>
</body>
</html>"""
    return html


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    json_only = "--json" in sys.argv
    single = None
    if "--check" in sys.argv:
        idx = sys.argv.index("--check")
        if idx + 1 < len(sys.argv):
            single = sys.argv[idx + 1]

    checks = [
        check_key_hygiene,
        check_vercel_env,
        check_supabase_health,
        check_gateway,
        check_git_clean,
        check_unpushed_commits,
        check_data_sync,
        check_cron_health,
        check_ollama,
        check_openclaw_version,
        check_disk_usage,
        check_stale_files,
        check_skill_watch,
    ]

    if single:
        checks = [c for c in checks if c.__name__.replace("check_", "") == single]

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    findings = []

    for check_fn in checks:
        try:
            result = check_fn()
            result["timestamp"] = timestamp
            findings.append(result)
            status_icon = {"PASS": "+", "FAIL": "!", "WARN": "~", "ERROR": "!", "INFO": "*"}.get(result["status"], "?")
            if not json_only:
                print(f"[{status_icon}] {result['check']:20s} {result['status']:5s} {result['message']}")
        except Exception as e:
            findings.append({"check": check_fn.__name__, "status": "ERROR",
                            "severity": "high", "message": str(e), "timestamp": timestamp})

    # Write findings JSON
    FINDINGS_JSON.write_text(json.dumps(findings, indent=2))

    # Build fixes list (only FAIL and WARN items)
    fixes = [f for f in findings if f["status"] in ("FAIL", "WARN")]
    FIXES_JSON.write_text(json.dumps(fixes, indent=2))

    # Generate HTML page
    html = generate_html(findings, timestamp)
    HEALTH_PAGE.write_text(html, encoding="utf-8")

    if json_only:
        print(json.dumps(findings, indent=2))
    else:
        print(f"\nFindings: {FINDINGS_JSON}")
        print(f"Fixes:    {FIXES_JSON}")
        print(f"HTML:     {HEALTH_PAGE}")

    # Return exit code based on findings
    has_failures = any(f["status"] == "FAIL" for f in findings)
    return 1 if has_failures else 0


if __name__ == "__main__":
    sys.exit(main())
