#!/usr/bin/env python3
"""
render-output.py — Convert raw JSON/Markdown output files into clean, readable HTML pages.

Usage:
  python3 scripts/render-output.py <input_file>           # renders one file
  python3 scripts/render-output.py --all                  # renders every file in public/outputs/
  python3 scripts/render-output.py --dir <subdir>         # renders all files in a subdirectory

The rendered HTML is written next to the source file with the same name + .html extension.
e.g. search-ai-entering-hr.json → search-ai-entering-hr.json.html

For files already ending in .html, it skips them.
"""

import json, sys, os, re, html, textwrap, glob
from pathlib import Path
from datetime import datetime

OUTPUTS_ROOT = Path(__file__).resolve().parent.parent / "public" / "outputs"

# === HTML TEMPLATE ===

TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — Next Chapter</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0d1117;color:#c9d1d9;line-height:1.7;padding:0}}
.page-header{{background:linear-gradient(135deg,#161b22,#1a3a5c);padding:28px 32px;border-bottom:1px solid #30363d}}
.page-header h1{{color:#58a6ff;font-size:22px;margin-bottom:4px}}
.page-header .meta{{color:#8b949e;font-size:13px}}
.page-header .breadcrumb{{color:#8b949e;font-size:12px;margin-bottom:8px}}
.page-header .breadcrumb a{{color:#58a6ff;text-decoration:none}}
.page-header .breadcrumb a:hover{{text-decoration:underline}}
.badge{{display:inline-block;padding:2px 10px;border-radius:12px;font-size:11px;font-weight:600;margin-right:6px;margin-top:6px}}
.badge-json{{background:#1c2d1a;color:#3fb950;border:1px solid #3fb950}}
.badge-md{{background:#2d1c36;color:#d2a8ff;border:1px solid #d2a8ff}}
.badge-section{{background:#1a2a3a;color:#79c0ff;border:1px solid #388bfd}}
.container{{max-width:1000px;margin:0 auto;padding:24px 20px}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:20px;margin-bottom:16px}}
.card h2{{font-size:17px;color:#f0f6fc;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid #21262d}}
.card h3{{font-size:15px;color:#79c0ff;margin:16px 0 8px}}
.card p,.card li{{font-size:14px;color:#c9d1d9;margin-bottom:8px}}
.card ul,.card ol{{padding-left:20px}}
.card a{{color:#58a6ff;text-decoration:none}}
.card a:hover{{text-decoration:underline}}
.card blockquote{{border-left:3px solid #388bfd;padding:8px 16px;margin:10px 0;background:#0d1117;border-radius:0 6px 6px 0;font-style:italic;color:#8b949e}}
.card strong{{color:#f0f6fc}}
.card em{{color:#d2a8ff}}
.card code{{background:#0d1117;padding:2px 6px;border-radius:4px;font-size:13px;color:#7ee787;font-family:'SF Mono',Consolas,monospace}}
.card pre{{background:#0d1117;border:1px solid #21262d;border-radius:6px;padding:12px;overflow-x:auto;font-size:13px;color:#c9d1d9;margin:10px 0}}
.card table{{width:100%;border-collapse:collapse;font-size:13px;margin:10px 0}}
.card th{{text-align:left;padding:8px 10px;background:#21262d;color:#f0f6fc;font-weight:600;border:1px solid #30363d}}
.card td{{padding:8px 10px;border:1px solid #21262d}}
.source-card{{background:#0d1117;border:1px solid #21262d;border-radius:8px;padding:14px;margin-bottom:10px;transition:border-color 0.2s}}
.source-card:hover{{border-color:#388bfd}}
.source-title{{font-size:14px;font-weight:600;color:#58a6ff;margin-bottom:4px}}
.source-title a{{color:#58a6ff;text-decoration:none}}
.source-title a:hover{{text-decoration:underline}}
.source-date{{font-size:11px;color:#8b949e;margin-bottom:6px}}
.source-excerpt{{font-size:13px;color:#8b949e;line-height:1.5}}
.source-url{{font-size:11px;color:#484f58;word-break:break-all;margin-top:4px}}
.score-bar{{height:4px;border-radius:2px;background:#21262d;margin-top:4px;overflow:hidden}}
.score-fill{{height:100%;border-radius:2px}}
.buyer-row{{display:grid;grid-template-columns:2fr 1fr 60px 100px;gap:8px;padding:8px 0;border-bottom:1px solid #21262d;align-items:center;font-size:13px}}
.buyer-row:first-child{{font-weight:600;color:#f0f6fc}}
.fit-8{{color:#3fb950;font-weight:700}}
.fit-6{{color:#f0883e;font-weight:600}}
.fit-4{{color:#8b949e}}
.section-divider{{font-size:12px;color:#8b949e;text-transform:uppercase;letter-spacing:1px;margin:20px 0 10px;padding:8px 0;border-bottom:1px solid #21262d}}
.back-link{{display:inline-block;margin:16px 0;color:#58a6ff;text-decoration:none;font-size:13px;padding:6px 14px;border-radius:6px;background:#21262d;border:1px solid #30363d}}
.back-link:hover{{border-color:#58a6ff}}
.footer{{text-align:center;padding:24px;color:#484f58;font-size:11px;border-top:1px solid #21262d;margin-top:20px}}
hr{{border:none;border-top:1px solid #21262d;margin:16px 0}}
@media(max-width:700px){{.container{{padding:12px}}.buyer-row{{grid-template-columns:1fr;gap:2px}}}}
</style>
</head>
<body>
<div class="page-header">
  <div class="breadcrumb"><a href="/index.html">Home</a> / <a href="/hrcom-ltd-hub.html">HR.com Hub</a> / {breadcrumb}</div>
  <h1>{title}</h1>
  <div class="meta">{subtitle}</div>
  {badges_html}
</div>
<div class="container">
{content}
</div>
<div class="footer">
  Rendered {render_date} — Next Chapter M&A Advisory | <a href="/hrcom-dealroom-overnight.html" style="color:#58a6ff;text-decoration:none">Deal Room</a>
</div>
</body>
</html>
"""


def clean_text(text):
    """Strip web scraping noise from Exa text content."""
    if not text:
        return ""
    # Remove common web noise patterns
    noise = [
        r'This web-site uses cookies.*?Policy',
        r'Subscribe\s*\n',
        r'Share\s*\n\s*(Facebook|Twitter|Linkedin|LinkedIn)',
        r'Email\s*Processing Sign up.*?Privacy Policy\.',
        r'Printed by for personal.*?licensing@.*?\.com\.',
        r'hx-target=.*?"',
        r'= \d+\], intersect once.*?$',
        r'\n\s*\n\s*\n+',
    ]
    for pattern in noise:
        text = re.sub(pattern, '\n', text, flags=re.DOTALL | re.MULTILINE)
    # Collapse excessive whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def extract_meaningful_text(raw_text, max_chars=800):
    """Extract the most meaningful portion of an article's text."""
    cleaned = clean_text(raw_text)
    if not cleaned:
        return ""
    # Find the first heading or substantial paragraph
    lines = cleaned.split('\n')
    meaningful = []
    char_count = 0
    started = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Skip navigation items, short fragments
        if len(stripped) < 20 and not stripped.startswith('#'):
            continue
        if stripped.startswith('#') or len(stripped) > 50:
            started = True
        if started:
            meaningful.append(stripped)
            char_count += len(stripped)
            if char_count > max_chars:
                break
    return '\n'.join(meaningful)


def render_exa_search_json(data, filename):
    """Render Exa search results JSON into article cards."""
    results = data.get("results", [])
    search_type = data.get("resolvedSearchType", "neural")
    cost = data.get("costDollars", {}).get("total", 0)
    search_time = data.get("searchTime", 0)

    # Derive the theme from the filename
    theme = filename.replace("search-", "").replace(".json", "").replace("-", " ").title()

    title = f"Research: {theme}"
    subtitle = f"{len(results)} sources found | {search_type} search | ${cost:.3f} cost | {search_time/1000:.1f}s"

    cards = []

    # Summary card
    cards.append(f'<div class="card"><h2>What This Search Found</h2>')
    cards.append(f'<p>Exa searched for intelligence on <strong>{theme}</strong> and returned {len(results)} relevant sources. ')
    cards.append(f'Below are the key findings, organized by source with the most relevant excerpts highlighted.</p></div>')

    for i, r in enumerate(results, 1):
        url = r.get("url", "")
        r_title = html.escape(r.get("title", "Untitled"))
        date = r.get("publishedDate", "")
        text = r.get("text", "")
        highlights = r.get("highlights", [])
        scores = r.get("highlightScores", [])
        author = r.get("author", "")

        # Format date
        date_str = ""
        if date:
            try:
                dt = datetime.fromisoformat(date.replace("Z", "+00:00"))
                date_str = dt.strftime("%B %d, %Y")
            except:
                date_str = date[:10]

        # Get meaningful excerpt
        excerpt = extract_meaningful_text(text, 600)
        if not excerpt and highlights:
            excerpt = clean_text(highlights[0])[:600]

        # Extract domain for display
        domain = ""
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc.replace("www.", "")
        except:
            domain = url[:50]

        card = f'<div class="source-card">'
        card += f'<div class="source-title"><a href="{html.escape(url)}" target="_blank">{r_title}</a></div>'
        meta_parts = []
        if date_str:
            meta_parts.append(date_str)
        if author:
            meta_parts.append(html.escape(author))
        meta_parts.append(domain)
        card += f'<div class="source-date">{" · ".join(meta_parts)}</div>'

        if excerpt:
            # Truncate cleanly
            if len(excerpt) > 600:
                excerpt = excerpt[:597] + "..."
            card += f'<div class="source-excerpt">{html.escape(excerpt)}</div>'

        if scores:
            best_score = max(scores) if scores else 0
            pct = min(max(int(best_score * 100), 5), 100)
            color = "#3fb950" if pct > 50 else "#f0883e" if pct > 20 else "#8b949e"
            card += f'<div class="score-bar"><div class="score-fill" style="width:{pct}%;background:{color}"></div></div>'

        card += '</div>'
        cards.append(card)

    badges_html = '<span class="badge badge-json">JSON</span><span class="badge badge-section">Exa Search</span>'
    breadcrumb = f'<a href="/outputs/buyer-intel/">Buyer Intel</a> / {filename}'

    return TEMPLATE.format(
        title=title,
        subtitle=subtitle,
        breadcrumb=breadcrumb,
        badges_html=badges_html,
        content='\n'.join(cards),
        render_date=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )


def render_buyer_list_json(data, filename):
    """Render the structured buyer list JSON."""
    title = "Identified Buyers — Structured List"
    subtitle = f"{len(data)} buyers scored and categorized"

    content = '<div class="card"><h2>All Buyers by Fit Score</h2>'
    content += '<div class="buyer-row"><span>Company</span><span>Type</span><span>Fit</span><span>Status</span></div>'

    for b in sorted(data, key=lambda x: -x.get("fit_score", 0)):
        name = html.escape(b.get("name", "Unknown"))
        btype = html.escape(b.get("type", ""))
        score = b.get("fit_score", 0)
        status = html.escape(b.get("script_status", b.get("status", "")))
        css = f"fit-{score}" if score in (4, 6, 8) else ""
        page = b.get("page", "")
        name_html = f'<a href="/{html.escape(page)}">{name}</a>' if page else name
        content += f'<div class="buyer-row"><span>{name_html}</span><span>{btype}</span><span class="{css}">{score}</span><span>{status}</span></div>'

    content += '</div>'

    badges_html = '<span class="badge badge-json">JSON</span><span class="badge badge-section">Buyer List</span>'
    breadcrumb = f'<a href="/outputs/buyer-intel/">Buyer Intel</a> / {filename}'

    return TEMPLATE.format(
        title=title,
        subtitle=subtitle,
        breadcrumb=breadcrumb,
        badges_html=badges_html,
        content=content,
        render_date=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )


def render_agent_rankings_json(data, filename):
    """Render agent performance JSON."""
    title = "Agent Performance Rankings"
    summary = data.get("summary", data)
    overall = data.get("overall", {})

    subtitle_parts = []
    if overall:
        subtitle_parts.append(f'{overall.get("total_runs", "?")} total runs')
        subtitle_parts.append(f'${overall.get("total_cost_usd", 0):.2f} total cost')
        subtitle_parts.append(f'{overall.get("output_usable_rate", 0)*100:.0f}% success rate')
    subtitle = " | ".join(subtitle_parts)

    content = '<div class="card"><h2>Agent Performance Summary</h2><table>'
    content += '<tr><th>Agent</th><th>Model</th><th>Runs</th><th>Avg Cost</th><th>Avg Time</th><th>Success</th></tr>'

    agents = summary if isinstance(summary, dict) else {}
    for name, info in agents.items():
        if not isinstance(info, dict):
            continue
        content += '<tr>'
        content += f'<td><strong>{html.escape(name)}</strong></td>'
        content += f'<td>{html.escape(info.get("agent_model", ""))}</td>'
        content += f'<td>{info.get("total_runs", 0)}</td>'
        content += f'<td>${info.get("average_cost_per_run_usd", 0):.4f}</td>'
        content += f'<td>{info.get("average_duration_seconds", 0):.1f}s</td>'
        content += f'<td>{info.get("output_usable_rate", 0)*100:.0f}%</td>'
        content += '</tr>'

    content += '</table></div>'

    badges_html = '<span class="badge badge-json">JSON</span><span class="badge badge-section">Performance</span>'
    breadcrumb = f'<a href="/outputs/stress-test/reports/">Stress Test</a> / {filename}'

    return TEMPLATE.format(
        title=title,
        subtitle=subtitle,
        breadcrumb=breadcrumb,
        badges_html=badges_html,
        content=content,
        render_date=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )


def markdown_to_html_simple(md_text):
    """Convert markdown to HTML with basic formatting. No external deps."""
    lines = md_text.split('\n')
    html_parts = []
    in_list = False
    in_ol = False
    in_code = False
    in_blockquote = False
    in_table = False

    for line in lines:
        stripped = line.strip()

        # Code blocks
        if stripped.startswith('```'):
            if in_code:
                html_parts.append('</pre>')
                in_code = False
            else:
                html_parts.append('<pre>')
                in_code = True
            continue
        if in_code:
            html_parts.append(html.escape(line))
            continue

        # Close lists if not continuing
        if in_list and not stripped.startswith(('- ', '* ', '  -', '  *')):
            html_parts.append('</ul>')
            in_list = False
        if in_ol and not re.match(r'^\d+\.', stripped):
            html_parts.append('</ol>')
            in_ol = False
        if in_blockquote and not stripped.startswith('>'):
            html_parts.append('</blockquote>')
            in_blockquote = False

        # Tables
        if '|' in stripped and stripped.startswith('|'):
            if not in_table:
                html_parts.append('<table>')
                in_table = True
            if stripped.replace('|', '').replace('-', '').replace(' ', '') == '':
                continue  # separator row
            cells = [c.strip() for c in stripped.strip('|').split('|')]
            tag = 'th' if not in_table or html_parts[-1] == '<table>' else 'td'
            row = '<tr>' + ''.join(f'<{tag}>{format_inline(c)}</{tag}>' for c in cells) + '</tr>'
            html_parts.append(row)
            continue
        elif in_table:
            html_parts.append('</table>')
            in_table = False

        # Empty line
        if not stripped:
            html_parts.append('<br>')
            continue

        # Headers
        if stripped.startswith('######'):
            html_parts.append(f'<h6>{format_inline(stripped[6:].strip())}</h6>')
        elif stripped.startswith('#####'):
            html_parts.append(f'<h5>{format_inline(stripped[5:].strip())}</h5>')
        elif stripped.startswith('####'):
            html_parts.append(f'<h4>{format_inline(stripped[4:].strip())}</h4>')
        elif stripped.startswith('###'):
            html_parts.append(f'<h3>{format_inline(stripped[3:].strip())}</h3>')
        elif stripped.startswith('##'):
            html_parts.append(f'<h2>{format_inline(stripped[2:].strip())}</h2>')
        elif stripped.startswith('#'):
            html_parts.append(f'<h2>{format_inline(stripped[1:].strip())}</h2>')

        # Horizontal rule
        elif stripped in ('---', '***', '___'):
            html_parts.append('<hr>')

        # Blockquote
        elif stripped.startswith('>'):
            if not in_blockquote:
                html_parts.append('<blockquote>')
                in_blockquote = True
            html_parts.append(format_inline(stripped[1:].strip()))

        # Unordered list
        elif stripped.startswith(('- ', '* ')):
            if not in_list:
                html_parts.append('<ul>')
                in_list = True
            html_parts.append(f'<li>{format_inline(stripped[2:])}</li>')

        # Ordered list
        elif re.match(r'^\d+\.\s', stripped):
            if not in_ol:
                html_parts.append('<ol>')
                in_ol = True
            text = re.sub(r'^\d+\.\s*', '', stripped)
            html_parts.append(f'<li>{format_inline(text)}</li>')

        # Sub-list items (indented)
        elif stripped.startswith(('  - ', '  * ', '    -', '    *')):
            text = stripped.lstrip(' -*').strip()
            html_parts.append(f'<li style="margin-left:20px">{format_inline(text)}</li>')

        # Regular paragraph
        else:
            html_parts.append(f'<p>{format_inline(stripped)}</p>')

    # Close any open tags
    if in_list: html_parts.append('</ul>')
    if in_ol: html_parts.append('</ol>')
    if in_code: html_parts.append('</pre>')
    if in_blockquote: html_parts.append('</blockquote>')
    if in_table: html_parts.append('</table>')

    return '\n'.join(html_parts)


def format_inline(text):
    """Apply inline markdown formatting."""
    t = html.escape(text)
    # Bold + italic
    t = re.sub(r'\*\*\*(.*?)\*\*\*', r'<strong><em>\1</em></strong>', t)
    # Bold
    t = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', t)
    # Italic
    t = re.sub(r'\*(.*?)\*', r'<em>\1</em>', t)
    # Inline code
    t = re.sub(r'`(.*?)`', r'<code>\1</code>', t)
    # Links
    t = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" target="_blank">\1</a>', t)
    return t


def render_markdown(md_text, filename, subdir):
    """Render a markdown file into styled HTML."""
    # Extract title from first heading or filename
    title_match = re.search(r'^#+\s*(.+)', md_text, re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip().strip('*')
    else:
        title = filename.replace('.md', '').replace('-', ' ').title()

    # Check if the markdown contains embedded HTML (dealroom pages)
    if '<div' in md_text or '<style>' in md_text:
        # Extract just the HTML portion
        html_match = re.search(r'```html\s*(.*?)\s*```', md_text, re.DOTALL)
        if html_match:
            content = f'<div class="card">{html_match.group(1)}</div>'
        else:
            content = f'<div class="card">{md_text}</div>'
    else:
        content = f'<div class="card">{markdown_to_html_simple(md_text)}</div>'

    # Determine badge and breadcrumb based on subdir
    section_map = {
        'buyer-intel': ('Buyer Intel', 'Research'),
        'dealroom': ('Deal Room', 'Client Facing'),
        'mailers': ('Outreach', 'Scripts & Templates'),
        'narrative': ('Narrative', 'Strategic'),
        'process': ('Process', 'Internal'),
        'tech': ('Technical', 'Operations'),
    }
    # Handle nested paths like stress-test/reports
    section_key = subdir.split('/')[0] if '/' in subdir else subdir
    section_name, section_type = section_map.get(section_key, (subdir.title(), 'Document'))

    subtitle = f"{section_name} — {section_type}"
    badges_html = f'<span class="badge badge-md">Markdown</span><span class="badge badge-section">{section_name}</span>'
    breadcrumb = f'<a href="/outputs/{subdir}/">{section_name}</a> / {filename}'

    return TEMPLATE.format(
        title=title,
        subtitle=subtitle,
        breadcrumb=breadcrumb,
        badges_html=badges_html,
        content=content,
        render_date=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )


def render_file(filepath):
    """Detect file type and render accordingly."""
    filepath = Path(filepath)
    filename = filepath.name

    # Skip already-rendered HTML
    if filename.endswith('.html'):
        return None

    # Determine subdirectory relative to outputs root
    try:
        rel = filepath.relative_to(OUTPUTS_ROOT)
        subdir = str(rel.parent)
    except ValueError:
        subdir = ""

    if filename.endswith('.json'):
        with open(filepath, 'r') as f:
            raw = f.read().strip()
        if not raw:
            return None
        # Strip markdown code fences if present
        if raw.startswith('```'):
            raw = re.sub(r'^```\w*\n?', '', raw)
            raw = re.sub(r'\n?```\s*$', '', raw)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None

        # Detect JSON type
        if isinstance(data, list) and len(data) > 0 and "fit_score" in data[0]:
            rendered = render_buyer_list_json(data, filename)
        elif isinstance(data, dict) and "results" in data:
            rendered = render_exa_search_json(data, filename)
        elif isinstance(data, dict) and ("summary" in data or "overall" in data):
            rendered = render_agent_rankings_json(data, filename)
        else:
            # Generic JSON — wrap in a readable display
            rendered = render_generic_json(data, filename, subdir)

    elif filename.endswith('.md'):
        with open(filepath, 'r') as f:
            md_text = f.read()
        rendered = render_markdown(md_text, filename, subdir)
    else:
        return None

    # Write output
    out_path = filepath.parent / (filename + '.html')
    with open(out_path, 'w') as f:
        f.write(rendered)

    return out_path


def render_generic_json(data, filename, subdir):
    """Fallback renderer for unrecognized JSON structures."""
    title = filename.replace('.json', '').replace('-', ' ').title()
    content = f'<div class="card"><h2>Data</h2><pre>{html.escape(json.dumps(data, indent=2)[:5000])}</pre></div>'
    badges_html = '<span class="badge badge-json">JSON</span>'
    breadcrumb = f'{subdir} / {filename}'
    return TEMPLATE.format(
        title=title,
        subtitle="Raw data view",
        breadcrumb=breadcrumb,
        badges_html=badges_html,
        content=content,
        render_date=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )


def render_all():
    """Render every file in outputs/."""
    count = 0
    for root, dirs, files in os.walk(OUTPUTS_ROOT):
        for f in files:
            if f.endswith('.html'):
                continue
            filepath = Path(root) / f
            out = render_file(filepath)
            if out:
                print(f"  OK  {out.relative_to(OUTPUTS_ROOT)}")
                count += 1
    return count


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 render-output.py <file> | --all | --dir <subdir>")
        sys.exit(1)

    if sys.argv[1] == '--all':
        count = render_all()
        print(f"\nRendered {count} files.")

    elif sys.argv[1] == '--dir':
        subdir = sys.argv[2] if len(sys.argv) > 2 else ""
        target = OUTPUTS_ROOT / subdir
        count = 0
        for f in target.iterdir():
            if f.is_file() and not f.name.endswith('.html'):
                out = render_file(f)
                if out:
                    print(f"  OK  {out.name}")
                    count += 1
        print(f"\nRendered {count} files in {subdir}.")

    else:
        filepath = Path(sys.argv[1])
        if not filepath.is_absolute():
            filepath = OUTPUTS_ROOT / filepath
        out = render_file(filepath)
        if out:
            print(f"OK  {out}")
        else:
            print(f"Skipped {filepath}")


if __name__ == "__main__":
    main()
