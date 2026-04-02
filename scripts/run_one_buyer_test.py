#!/usr/bin/env python3
"""
Run comprehensive research for ONE buyer and log every step.
This is a test harness — validates the full pipeline end-to-end.

Usage: python3 scripts/run_one_buyer_test.py
"""

import json, os, sys, time, requests
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
from lib.exa_client import ExaClient, TEMPLATES

# ── Config ────────────────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')
SB_HEADERS = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}', 'Content-Type': 'application/json'}

BUYER_NAME = "Paychex"
BUYER_SLUG = "paychex"
BUYER_CITY = "Rochester"
BUYER_STATE = "NY"
ENTITY = "next_chapter"

PUBLIC_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'public', 'data')
RESEARCH_JSON_PATH = os.path.join(PUBLIC_DATA_DIR, 'debbie-buyer-research.json')

# The 10 sections the Debbie review page expects
SECTIONS = [
    {
        "key": "hr_media_business",
        "title": "HR.com Media Business",
        "templates": ["company_search", "company_financials"],
        "topic": "HR.com media business model revenue advertising learning marketplace",
    },
    {
        "key": "hr_domain_name",
        "title": "HR.com Domain Name Value",
        "templates": ["strategic_fit"],
        "topic": "HR.com domain name value premium domain HR technology branding",
    },
    {
        "key": "market_reputation",
        "title": "Market Reputation",
        "templates": ["reviews_search"],
        "topic": "Paychex products reviews ratings complaints customer satisfaction",
    },
    {
        "key": "strategic_fit",
        "title": "Strategic Fit",
        "templates": ["strategic_fit", "company_financials"],
        "topic": "Paychex HR technology strategy content marketing HR.com acquisition synergy",
    },
    {
        "key": "ceo_vision",
        "title": "CEO Vision & Strategy",
        "templates": ["earnings_call"],
        "topic": "Paychex CEO John Gibson vision strategy growth priorities HR technology 2025",
    },
    {
        "key": "ma_appetite",
        "title": "M&A Appetite",
        "templates": ["ma_history"],
        "topic": "Paychex acquisition history M&A deals purchased companies HR payroll",
    },
    {
        "key": "competitive_moat",
        "title": "Competitive Moat",
        "templates": ["strategic_fit"],
        "topic": "Paychex competitive advantage moat vs ADP Workday market position",
    },
    {
        "key": "earnings_quotes",
        "title": "Key Earnings Quotes",
        "templates": ["earnings_call"],
        "topic": "Paychex earnings call Q3 Q4 2024 2025 CEO CFO quotes strategy",
    },
    {
        "key": "approach_strategy",
        "title": "Approach Strategy",
        "templates": ["buyer_contacts"],
        "topic": "Paychex corporate development VP M&A business development contact",
    },
    {
        "key": "golden_nuggets",
        "title": "Golden Nuggets",
        "templates": ["ma_history", "earnings_call"],
        "topic": "Paychex surprising facts culture awards unique partnerships community",
    },
]

# ── Tracking ──────────────────────────────────────────────────────────────────
search_log = []  # every search we run
total_cost = 0.0

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def flatten_results(exa_response):
    results = exa_response.get("results", [])
    texts, urls = [], []
    for r in results:
        url = r.get("url", "")
        if url:
            urls.append(url)
        content = r.get("text", "") or ""
        if not content:
            highlights = r.get("highlights", [])
            if isinstance(highlights, list):
                content = " ".join(highlights)
        title = r.get("title", "")
        if title:
            content = f"[{title}] {content}"
        if content.strip():
            texts.append(content.strip())
    return "\n\n---\n\n".join(texts), urls

def log_to_supabase(company, method_code, query, tool, raw_resp, urls, count, cost, duration_ms, status, error=None):
    """Write to research_executions in Supabase."""
    try:
        r = requests.post(
            f'{SUPABASE_URL}/rest/v1/research_executions',
            headers={**SB_HEADERS, 'Prefer': 'return=minimal'},
            json={
                'company_name': company,
                'method_code': method_code,
                'actual_query': query,
                'tool': tool,
                'raw_response': json.dumps(raw_resp, default=str)[:10000] if raw_resp else None,
                'result_count': count,
                'source_urls': json.dumps(urls) if urls else None,
                'cost_usd': cost,
                'duration_ms': duration_ms,
                'status': status,
                'error_message': error,
                'entity': ENTITY,
                'executed_at': datetime.now(timezone.utc).isoformat(),
            }
        )
        return r.status_code in (200, 201)
    except Exception as e:
        log(f"  Supabase log failed: {e}")
        return False

def llm_synthesize(buyer_name, section_key, goal, combined_text):
    """Use Claude CLI to synthesize raw research into clean HTML."""
    import subprocess
    prompt = f"""You are a senior M&A research analyst writing buyer intelligence for {buyer_name}.

Section: {section_key}
Goal: {goal}

Below are raw excerpts from web research. Synthesize them into concise, factual HTML.

RULES:
- Write 2-4 paragraphs using <p> tags, <strong> for key quotes/facts
- Include direct quotes with attribution where available
- Stick to verifiable facts — do NOT invent
- If no relevant info, write: <p>No relevant data found.</p>
- Only inline HTML — no <html>/<head>/<body>/<style> tags

RAW RESEARCH:
{combined_text[:8000]}

Return ONLY the HTML content."""

    try:
        result = subprocess.run(
            ["claude", "-p", "--output-format", "text"],
            input=prompt, capture_output=True, text=True, timeout=120,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except:
        return None

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global total_cost

    log(f"=" * 60)
    log(f"COMPREHENSIVE BUYER TEST: {BUYER_NAME}")
    log(f"Sections to research: {len(SECTIONS)}")
    log(f"=" * 60)

    exa = ExaClient()
    os.makedirs(PUBLIC_DATA_DIR, exist_ok=True)

    # Load existing JSON if any
    if os.path.exists(RESEARCH_JSON_PATH):
        with open(RESEARCH_JSON_PATH) as f:
            all_data = json.load(f)
    else:
        all_data = {}

    if BUYER_SLUG not in all_data:
        all_data[BUYER_SLUG] = {}

    search_num = 0

    for section in SECTIONS:
        key = section["key"]
        title = section["title"]
        topic = section["topic"]
        templates = section["templates"]

        log(f"\n{'─' * 50}")
        log(f"SECTION: {title} ({key})")
        log(f"Templates: {templates}")

        section_texts = []
        section_urls = []

        for tmpl_name in templates:
            search_num += 1
            tmpl = TEMPLATES.get(tmpl_name, {})
            query_template = tmpl.get("query", "")

            kwargs = {
                "company_name": BUYER_NAME,
                "topic": topic,
                "city": BUYER_CITY,
                "state": BUYER_STATE,
                "vertical": "HR Technology / Payroll",
                "owner_name": "John Gibson",
            }
            effective_query = query_template.format(**kwargs).strip()

            log(f"  [{search_num}] Template: {tmpl_name}")
            log(f"       Query: {effective_query}")

            t0 = time.time()
            try:
                exa_response = exa.search(tmpl_name, **kwargs)
                duration_ms = int((time.time() - t0) * 1000)
                text_chunk, urls = flatten_results(exa_response)
                result_count = len(exa_response.get("results", []))
                raw_cost = exa_response.get("costDollars", 0.0)
                cost = float(raw_cost.get("total", 0.0)) if isinstance(raw_cost, dict) else float(raw_cost or 0.0)
                total_cost += cost

                entry = {
                    "search_num": search_num,
                    "section": key,
                    "template": tmpl_name,
                    "query": effective_query,
                    "result_count": result_count,
                    "cost_usd": cost,
                    "duration_ms": duration_ms,
                    "status": "success" if result_count > 0 else "empty",
                    "urls": urls[:5],
                    "stored_supabase": False,
                    "stored_json": False,
                }

                # Log to Supabase
                sb_ok = log_to_supabase(
                    BUYER_NAME, f"test_{key}_{tmpl_name}", effective_query,
                    "exa", exa_response, urls, result_count, cost, duration_ms,
                    "success"
                )
                entry["stored_supabase"] = sb_ok

                if text_chunk:
                    section_texts.append(text_chunk)
                section_urls.extend(urls)

                log(f"       Results: {result_count} | Cost: ${cost:.4f} | Time: {duration_ms}ms | Supabase: {'✓' if sb_ok else '✗'}")
                for u in urls[:3]:
                    log(f"       → {u}")

                search_log.append(entry)

            except Exception as exc:
                duration_ms = int((time.time() - t0) * 1000)
                log(f"       FAILED: {exc}")
                sb_ok = log_to_supabase(
                    BUYER_NAME, f"test_{key}_{tmpl_name}", effective_query,
                    "exa", None, [], 0, 0, duration_ms,
                    "error", str(exc)[:500]
                )
                search_log.append({
                    "search_num": search_num,
                    "section": key,
                    "template": tmpl_name,
                    "query": effective_query,
                    "result_count": 0,
                    "cost_usd": 0,
                    "duration_ms": duration_ms,
                    "status": "error",
                    "error": str(exc)[:200],
                    "stored_supabase": sb_ok,
                    "stored_json": False,
                })

            time.sleep(0.5)  # rate limit

        # ── Synthesize section ────────────────────────────────────────────────
        combined = "\n\n---\n\n".join(section_texts) if section_texts else ""
        unique_urls = list(dict.fromkeys(section_urls))

        if combined:
            log(f"  Synthesizing {len(section_texts)} text chunks via Claude...")
            html = llm_synthesize(BUYER_NAME, key, title, combined)
            if not html:
                html = f"<p>Synthesis failed. {len(section_texts)} raw sources collected.</p>"
            log(f"  Synthesis: {'OK' if '<p>' in html else 'FAILED'} ({len(html)} chars)")
        else:
            html = f"<p>No data found for {title}.</p>"
            log(f"  No raw data — skipping synthesis")

        # Store in JSON
        all_data[BUYER_SLUG][key] = {
            "content": html,
            "source_urls": unique_urls,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Mark stored
        for entry in search_log:
            if entry["section"] == key:
                entry["stored_json"] = True

    # ── Write final JSON ──────────────────────────────────────────────────────
    with open(RESEARCH_JSON_PATH, 'w') as f:
        json.dump(all_data, f, indent=2, default=str)
    log(f"\n{'=' * 60}")
    log(f"JSON written: {RESEARCH_JSON_PATH}")

    # ── Summary ───────────────────────────────────────────────────────────────
    log(f"\n{'=' * 60}")
    log(f"SEARCH LOG SUMMARY")
    log(f"{'=' * 60}")
    successes = [s for s in search_log if s["status"] == "success"]
    empties = [s for s in search_log if s["status"] == "empty"]
    errors = [s for s in search_log if s["status"] == "error"]
    log(f"Total searches: {len(search_log)}")
    log(f"  Returned results: {len(successes)}")
    log(f"  Empty (0 results): {len(empties)}")
    log(f"  Errors: {len(errors)}")
    log(f"Total Exa cost: ${total_cost:.4f}")
    log(f"")

    log(f"DETAILED LOG:")
    log(f"{'#':<4} {'Section':<22} {'Template':<20} {'Results':<8} {'Cost':<8} {'Supabase':<10} {'JSON':<6} {'Status'}")
    log(f"{'-'*4} {'-'*22} {'-'*20} {'-'*8} {'-'*8} {'-'*10} {'-'*6} {'-'*10}")
    for s in search_log:
        log(f"{s['search_num']:<4} {s['section']:<22} {s['template']:<20} {s['result_count']:<8} ${s['cost_usd']:<7.4f} {'✓' if s['stored_supabase'] else '✗':<10} {'✓' if s['stored_json'] else '✗':<6} {s['status']}")

    log(f"\nSECTION COVERAGE:")
    for section in SECTIONS:
        key = section["key"]
        data = all_data.get(BUYER_SLUG, {}).get(key, {})
        has_content = bool(data.get("content")) and "No data found" not in data.get("content", "")
        n_sources = len(data.get("source_urls", []))
        log(f"  {key:<25} {'✓ HAS DATA' if has_content else '✗ EMPTY':<15} {n_sources} sources")

    log(f"\nSTORAGE VERIFICATION:")
    log(f"  JSON file: {RESEARCH_JSON_PATH}")
    log(f"  JSON file exists: {os.path.exists(RESEARCH_JSON_PATH)}")
    log(f"  JSON file size: {os.path.getsize(RESEARCH_JSON_PATH)} bytes")
    log(f"  Supabase research_executions: {sum(1 for s in search_log if s['stored_supabase'])} rows written")

    return search_log

if __name__ == '__main__':
    main()
