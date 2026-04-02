#!/usr/bin/env python3
"""
Build 6 Auto-Regeneration Pipeline — Full Rebuild
Regenerates ALL hub pages regardless of current report status.
Used when templates change and every page needs to be refreshed.

Query: all targets where research_completed_at IS NOT NULL
       AND pipeline_status != DISQUALIFIED

Usage:
  python regenerate_all.py                          # full rebuild
  python regenerate_all.py --dry-run                # preview only, no writes
  python regenerate_all.py --entity next_chapter    # filter by entity
"""

import argparse
import json
import os
import re
import ssl
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# Credentials: all keys come from env vars. See .env.example for names, ~/.zshrc for values.

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
DB_CONN_PATCHED = os.environ.get("DATABASE_URL", "")
BASE_URL = os.environ.get("CRM_BASE_URL", "https://master-crm-web.vercel.app").rstrip("/")

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = REPO_ROOT / "public"
CRM_LIB = Path.home() / "Projects" / "master-crm-web" / "backend" / "lib"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(msg: str):
    print(f"{datetime.utcnow().isoformat()} | REGEN-ALL | {msg}", flush=True)


def make_slug(company_name: str) -> str:
    """Lowercase, spaces to hyphens, remove dots/commas, & to and, max 40 chars."""
    slug = company_name.lower()
    slug = slug.replace("&", "and")
    slug = re.sub(r"[.,]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    return slug[:40].rstrip("-")


def supabase_request(method: str, path: str, body=None):
    """Raw urllib REST call to Supabase with SSL verification."""
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "return=representation")
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx) as resp:
        return json.loads(resp.read().decode())


def fetch_all_targets(entity_filter=None):
    """
    Fetch ALL targets except DISQUALIFIED ones.
    Used for full template rebuilds -- does not filter on research timestamps.
    Optionally filter by entity (e.g. 'next_chapter').
    """
    SELECT = (
        "select=id,company_name,pipeline_status,entity,deal_side,"
        "research_completed_at,report_generated_at,report_url"
    )
    query = (
        f"targets?pipeline_status=neq.DISQUALIFIED"
        f"&{SELECT}"
        f"&order=company_name.asc"
    )
    if entity_filter:
        query += f"&entity=eq.{entity_filter}"

    return supabase_request("GET", query)


def generate_html_for_target(company_name: str) -> str:
    """Import company_hub (with DB_CONN patch) and return HTML string."""
    crm_lib_str = str(CRM_LIB)
    if crm_lib_str not in sys.path:
        sys.path.insert(0, crm_lib_str)

    import company_hub  # deferred so sys.path patch takes effect first
    company_hub.DB_CONN = DB_CONN_PATCHED

    assets = company_hub.get_all_company_assets(company_name)
    html = company_hub.generate_hub_html(company_name, assets)
    return html


def check_git_remote() -> bool:
    """Return True if at least one git remote is configured."""
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "remote"],
        capture_output=True, text=True
    )
    return bool(result.stdout.strip())


def git_commit_and_push(files) -> bool:
    """Stage files, commit, push, AND deploy to Vercel. Returns True on success."""
    rel_files = [str(f.relative_to(REPO_ROOT)) for f in files]
    try:
        subprocess.run(
            ["git", "-C", str(REPO_ROOT), "add"] + rel_files,
            check=True
        )
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        subprocess.run(
            ["git", "-C", str(REPO_ROOT), "commit",
             "-m", f"[auto] full hub page rebuild -- {timestamp}"],
            check=True
        )
        subprocess.run(
            ["bash", str(REPO_ROOT / "scripts" / "deploy.sh"), "--skip-commit"],
            check=True, timeout=180
        )
        return True
    except subprocess.CalledProcessError as exc:
        log(f"ERROR: deploy failed -- {exc}")
        return False


def update_supabase_status(target_id: str, slug: str):
    """Set pipeline_status=REPORT_LIVE, report_generated_at=now, report_url."""
    now_iso = datetime.now(timezone.utc).isoformat()
    report_url = f"{BASE_URL}/{slug}-hub.html"
    supabase_request(
        "PATCH",
        f"targets?id=eq.{target_id}",
        body={
            "pipeline_status": "REPORT_LIVE",
            "report_generated_at": now_iso,
            "report_url": report_url,
        },
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Full hub page rebuild (all targets).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be generated -- no writes.")
    parser.add_argument("--entity", metavar="ENTITY",
                        help="Filter by entity (e.g. next_chapter, and_capital).")
    args = parser.parse_args()

    # Fetch targets
    entity_label = f" (entity={args.entity})" if args.entity else ""
    log(f"Fetching all eligible targets from Supabase{entity_label}...")
    try:
        targets = fetch_all_targets(entity_filter=args.entity)
    except Exception as exc:
        log(f"FATAL: Could not fetch targets -- {exc}")
        sys.exit(1)

    log(f"Found {len(targets)} target(s) to process.")

    if not targets:
        log("Nothing to do.")
        return

    if args.dry_run:
        log("DRY RUN -- no files will be written.")
        for t in targets:
            slug = make_slug(t["company_name"])
            log(f"  Would generate: public/{slug}-hub.html  ({t['company_name']})")
        return

    # Check remote before doing any work
    has_remote = check_git_remote()
    if not has_remote:
        log(
            "WARNING: No git remote configured. HTML files will be written locally "
            "but cannot be pushed. Configure a remote and re-run to trigger Vercel deploy."
        )

    # Generate pages
    files_written = []
    failed = []
    successful_targets = []

    for t in targets:
        company_name = t["company_name"]
        slug = make_slug(company_name)
        out_path = PUBLIC_DIR / f"{slug}-hub.html"

        log(f"Generating: {company_name} -> {out_path.name}")
        try:
            html = generate_html_for_target(company_name)
            out_path.write_text(html, encoding="utf-8")
            files_written.append(out_path)
            successful_targets.append(t)
            log(f"  OK: wrote {len(html):,} bytes")
        except Exception as exc:
            log(f"  FAILED: {company_name} -- {exc}")
            failed.append(company_name)

    # Git commit + push
    pushed = False
    if files_written:
        if has_remote:
            log(f"Committing and pushing {len(files_written)} file(s)...")
            pushed = git_commit_and_push(files_written)
        else:
            log("Skipping git push -- no remote configured.")

    # Update Supabase status for all successfully generated targets
    if pushed:
        log("Updating Supabase pipeline_status -> REPORT_LIVE...")
        for t in successful_targets:
            if t.get("id") is None:
                continue
            try:
                slug = make_slug(t["company_name"])
                update_supabase_status(str(t["id"]), slug)
                log(f"  Updated: {t['company_name']} (id={t['id']})")
            except Exception as exc:
                log(f"  WARNING: Supabase update failed for {t['company_name']} -- {exc}")

    # Summary
    log("--- SUMMARY ---")
    log(f"Generated: {len(files_written)}")
    log(f"Failed:    {len(failed)}")
    log(f"Pushed:    {pushed}")
    if failed:
        log(f"Failed companies: {', '.join(failed)}")


if __name__ == "__main__":
    main()
