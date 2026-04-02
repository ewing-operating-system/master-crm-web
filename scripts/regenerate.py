#!/usr/bin/env python3
"""
Build 6 Auto-Regeneration Pipeline — Incremental
Generates hub pages only for new/stale targets.

Query logic:
  Condition A: pipeline_status = RESEARCHED
  Condition B: research_completed_at IS NOT NULL
               AND report_generated_at IS NULL
               AND pipeline_status != DISQUALIFIED

Results are merged and deduplicated by id.

Usage:
  python regenerate.py                     # normal run
  python regenerate.py --dry-run           # preview only, no writes
  python regenerate.py --company "Name"    # single company (skips status update)
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
    print(f"{datetime.utcnow().isoformat()} | REGEN | {msg}", flush=True)


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


def fetch_targets_incremental():
    """Fetch and deduplicate targets from Condition A and Condition B."""
    seen_ids = set()
    targets = []

    SELECT = (
        "select=id,company_name,pipeline_status,entity,deal_side,"
        "research_completed_at,report_generated_at,report_url"
    )

    # Condition A: pipeline_status = RESEARCHED
    try:
        rows_a = supabase_request(
            "GET",
            f"targets?pipeline_status=eq.RESEARCHED&{SELECT}",
        )
        for row in rows_a:
            if row.get("id") not in seen_ids:
                seen_ids.add(row["id"])
                targets.append(row)
    except Exception as exc:
        log(f"WARNING: Condition A query failed -- {exc}")

    # Condition B: research_completed_at IS NOT NULL, report_generated_at IS NULL,
    #              pipeline_status != DISQUALIFIED
    try:
        rows_b = supabase_request(
            "GET",
            f"targets?research_completed_at=not.is.null"
            f"&report_generated_at=is.null"
            f"&pipeline_status=neq.DISQUALIFIED"
            f"&{SELECT}",
        )
        for row in rows_b:
            if row.get("id") not in seen_ids:
                seen_ids.add(row["id"])
                targets.append(row)
    except Exception as exc:
        log(f"WARNING: Condition B query failed -- {exc}")

    return targets


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
    """Stage files, commit, push. Returns True on success."""
    rel_files = [str(f.relative_to(REPO_ROOT)) for f in files]
    try:
        subprocess.run(
            ["git", "-C", str(REPO_ROOT), "add"] + rel_files + ["public/data/*.json"],
            check=True
        )
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        subprocess.run(
            ["git", "-C", str(REPO_ROOT), "commit",
             "-m", f"[auto] regenerate hub pages -- {timestamp}"],
            check=True
        )
        subprocess.run(
            ["git", "-C", str(REPO_ROOT), "push"],
            check=True
        )
        return True
    except subprocess.CalledProcessError as exc:
        log(f"ERROR: git operation failed -- {exc}")
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


def register_page(page_path: str, page_type: str, company_name: str, entity: str):
    """Upsert a row into page_versions after generating an HTML file.

    Uses company_name + page_type as the natural merge key (via Prefer header).
    Stores page_path in template_used and entity in generated_by.
    """
    url = f"{SUPABASE_URL}/rest/v1/page_versions"
    body = {
        "company_name": company_name,
        "page_type": page_type,
        "template_used": page_path,
        "generated_by": entity,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "resolution=merge-duplicates,return=representation")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx) as resp:
            resp.read()
    except Exception as exc:
        log(f"  WARNING: page_versions upsert failed for {page_path} -- {exc}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Incremental hub page regeneration.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be generated -- no writes.")
    parser.add_argument("--company", metavar="NAME",
                        help="Regenerate a single company by name.")
    args = parser.parse_args()

    # Build target list
    if args.company:
        targets = [{"id": None, "company_name": args.company}]
        log(f"Single-company mode: {args.company}")
    else:
        log("Fetching incremental targets from Supabase...")
        targets = fetch_targets_incremental()
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
            register_page(
                page_path=out_path.name,
                page_type="hub",
                company_name=company_name,
                entity=t.get("entity", ""),
            )
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

    # Update Supabase status (only after successful push, skip single-company mode)
    if pushed and not args.company:
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
