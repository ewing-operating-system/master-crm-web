#!/usr/bin/env python3
"""
Inject breadcrumb navigation into every HTML page in public/.
Links: Home (index.html) + Account Hub (if page belongs to an account).
Idempotent — removes old nav before injecting new one.
"""

import os
import re
import glob

PUBLIC = os.path.expanduser("~/Projects/master-crm-web/public")

# Account prefix → hub page mapping
ACCOUNT_MAP = {
    "air-control": {"hub": "air-control-hub.html", "name": "Air Control"},
    "aquascience": {"hub": "aquascience-hub.html", "name": "AquaScience"},
    "design-precast": {"hub": "design-precast-and-pipe-inc-hub.html", "name": "Design Precast"},
    "design-precast-and-pipe-inc": {"hub": "design-precast-and-pipe-inc-hub.html", "name": "Design Precast"},
    "design-precast-pipe-inc": {"hub": "design-precast-and-pipe-inc-hub.html", "name": "Design Precast"},
    "design-precast-pipe": {"hub": "design-precast-and-pipe-inc-hub.html", "name": "Design Precast"},
    "hrcom-ltd": {"hub": "hrcom-ltd-hub.html", "name": "HR.com"},
    "hr-com-ltd": {"hub": "hrcom-ltd-hub.html", "name": "HR.com"},
    "springer-floor": {"hub": "springer-floor-hub.html", "name": "Springer Floor"},
    "wieser-concrete-products-inc": {"hub": "wieser-concrete-products-inc-hub.html", "name": "Wieser Concrete"},
    "wieser-concrete": {"hub": "wieser-concrete-products-inc-hub.html", "name": "Wieser Concrete"},
    "weiser-concrete": {"hub": "wieser-concrete-products-inc-hub.html", "name": "Wieser Concrete"},
}

# Special pages that map to accounts via prefix match
SPECIAL_PREFIX_MAP = {
    "interactive-air-control": "air-control",
    "interactive-aquascience": "aquascience",
    "interactive-design-precast": "design-precast",
    "interactive-hrcom": "hrcom-ltd",
    "interactive-springer": "springer-floor",
    "interactive-wieser": "wieser-concrete",
    "dataroom-air-control": "air-control",
    "dataroom-aquascience": "aquascience",
    "dataroom-design-precast": "design-precast",
    "dataroom-hrcom": "hrcom-ltd",
    "dataroom-springer": "springer-floor",
    "dataroom-wieser": "wieser-concrete",
    "meeting-air-control": "air-control",
    "meeting-aquascience": "aquascience",
    "meeting-design-precast": "design-precast",
    "meeting-hrcom": "hrcom-ltd",
    "meeting-springer": "springer-floor",
    "meeting-wieser": "wieser-concrete",
    "sample-letter-aquascience": "aquascience",
}

# EBITDA levers vertical → no specific account, just home
EBITDA_PAGES = {"ebitda-levers", "ebitda-levers-master", "ebitda-levers-concrete-precast",
                "ebitda-levers-flooring", "ebitda-levers-hvac", "ebitda-levers-pest-control",
                "ebitda-levers-plumbing", "ebitda-levers-roofing", "ebitda-levers-water-treatment"}

# Pages that are "home" themselves or utility — only get System Overview link
HOME_PAGES = {"index", "dashboard", "dashboard_2026-03-29", "campaign-manager",
              "system-overview", "feature-roadmap", "version-history",
              "buyer-matching", "letter-template", "meeting-page-v2",
              "interactive-proposal-auto"}

# Skip non-HTML files
SKIP_EXTENSIONS = {".js", ".css", ".md", ".json"}

NAV_MARKER_START = "<!-- NAV:START -->"
NAV_MARKER_END = "<!-- NAV:END -->"


def get_account(filename):
    """Determine which account a file belongs to."""
    stem = filename.rsplit(".", 1)[0]  # remove .html

    # Check special prefix map first
    for prefix, account_key in SPECIAL_PREFIX_MAP.items():
        if stem.startswith(prefix):
            return ACCOUNT_MAP.get(account_key)

    # Check if it's a home/utility page
    if stem in HOME_PAGES:
        return None

    # Check if it's an EBITDA page
    if stem in EBITDA_PAGES:
        return None

    # Try matching against account prefixes (longest match first)
    sorted_keys = sorted(ACCOUNT_MAP.keys(), key=len, reverse=True)
    for prefix in sorted_keys:
        if stem.startswith(prefix):
            return ACCOUNT_MAP[prefix]

    return None


def build_nav_html(filename, account):
    """Build the breadcrumb nav bar HTML."""
    is_index = filename == "index.html"
    is_hub = filename.endswith("-hub.html")
    is_system = filename == "system-overview.html"

    links = []

    # Home link (always, unless we ARE the index)
    if not is_index:
        links.append('<a href="index.html">Home</a>')

    # System Overview link
    if not is_system:
        links.append('<a href="system-overview.html">System Overview</a>')

    # Account hub link (if page belongs to an account and isn't the hub itself)
    if account and not is_hub:
        links.append(f'<a href="{account["hub"]}">{account["name"]} Hub</a>')

    if not links:
        return None  # index.html that IS the system overview — shouldn't happen but safety

    links_html = "\n      ".join(links)

    return f"""{NAV_MARKER_START}
<div class="nc-nav" style="background:#f6f8fa;border-bottom:1px solid #d0d7de;padding:8px 20px;font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;font-size:13px;display:flex;align-items:center;gap:16px;position:sticky;top:0;z-index:999">
  <span style="font-weight:700;color:#0d1117;margin-right:8px">Next Chapter M&amp;A</span>
  <span style="color:#d0d7de">|</span>
  <style>.nc-nav a{{color:#0969da;text-decoration:none;font-weight:500}}.nc-nav a:hover{{text-decoration:underline}}</style>
  {links_html}
</div>
{NAV_MARKER_END}"""


def inject_nav(filepath, nav_html):
    """Inject nav into an HTML file. Idempotent."""
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    # Remove old nav if present
    pattern = re.compile(
        re.escape(NAV_MARKER_START) + r".*?" + re.escape(NAV_MARKER_END),
        re.DOTALL
    )
    content = pattern.sub("", content)

    # Find insertion point: right after <body...>
    body_match = re.search(r"<body[^>]*>", content, re.IGNORECASE)
    if not body_match:
        return False

    insert_pos = body_match.end()
    content = content[:insert_pos] + "\n" + nav_html + "\n" + content[insert_pos:]

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return True


def main():
    html_files = glob.glob(os.path.join(PUBLIC, "*.html"))
    total = 0
    updated = 0
    skipped = 0
    no_body = 0

    for filepath in sorted(html_files):
        filename = os.path.basename(filepath)
        ext = os.path.splitext(filename)[1]

        if ext in SKIP_EXTENSIONS:
            skipped += 1
            continue

        total += 1
        account = get_account(filename)
        nav_html = build_nav_html(filename, account)

        if nav_html is None:
            # Still inject a minimal nav for index
            if filename == "index.html":
                nav_html = f"""{NAV_MARKER_START}
<div class="nc-nav" style="background:#f6f8fa;border-bottom:1px solid #d0d7de;padding:8px 20px;font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;font-size:13px;display:flex;align-items:center;gap:16px;position:sticky;top:0;z-index:999">
  <span style="font-weight:700;color:#0d1117;margin-right:8px">Next Chapter M&amp;A</span>
  <span style="color:#d0d7de">|</span>
  <a href="system-overview.html">System Overview</a>
</div>
{NAV_MARKER_END}"""
            else:
                skipped += 1
                continue

        success = inject_nav(filepath, nav_html)
        if success:
            acct_label = account["name"] if account else "—"
            updated += 1
        else:
            no_body += 1

    print(f"Total HTML files: {total}")
    print(f"Updated: {updated}")
    print(f"Skipped (utility/non-HTML): {skipped}")
    print(f"No <body> tag found: {no_body}")


if __name__ == "__main__":
    main()
