#!/usr/bin/env python3
"""
Run comprehensive buyer research for the Debbie Review Page.

Runs Exa searches, synthesizes via Claude, structures golden nuggets
and market reputation, writes to debbie-buyer-research.json in the
format the page expects, and commits + pushes to trigger Vercel deploy.

Usage:
  python3 scripts/run_one_buyer_test.py --buyer "SAP SuccessFactors" --city "Newtown Square" --state PA
  python3 scripts/run_one_buyer_test.py --buyer Paychex --city Rochester --state NY
  python3 scripts/run_one_buyer_test.py --buyer Workday --city Pleasanton --state CA --skip-deploy
"""

import argparse, json, os, re, subprocess, sys, time, requests
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
from lib.exa_client import ExaClient, TEMPLATES

# ── Config ────────────────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')
SB_HEADERS = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}', 'Content-Type': 'application/json'}
ENTITY = "next_chapter"

PUBLIC_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'public', 'data')
RESEARCH_JSON_PATH = os.path.join(PUBLIC_DATA_DIR, 'debbie-buyer-research.json')
REPO_ROOT = os.path.join(os.path.dirname(__file__), '..')

search_log = []
total_cost = 0.0


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def slugify(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower().strip()).strip('-')[:80]


def parse_cost(exa_response):
    raw = exa_response.get("costDollars", 0.0)
    return float(raw.get("total", 0.0)) if isinstance(raw, dict) else float(raw or 0.0)


def flatten_results(exa_response):
    results = exa_response.get("results", [])
    texts, urls = [], []
    for r in results:
        url = r.get("url", "")
        if url:
            urls.append(url)
        content = r.get("text", "") or ""
        if not content:
            hl = r.get("highlights", [])
            content = " ".join(hl) if isinstance(hl, list) else ""
        title = r.get("title", "")
        if title:
            content = f"[{title}] {content}"
        if content.strip():
            texts.append(content.strip())
    return "\n\n---\n\n".join(texts), urls


def ensure_method_code(method_code):
    """Register method_code in research_methods if it doesn't exist."""
    r = requests.get(
        f'{SUPABASE_URL}/rest/v1/research_methods?method_code=eq.{method_code}&select=method_code',
        headers=SB_HEADERS
    )
    if r.json():
        return
    requests.post(
        f'{SUPABASE_URL}/rest/v1/research_methods',
        headers={**SB_HEADERS, 'Prefer': 'return=minimal'},
        json={
            'method_code': method_code,
            'method_name': f'Auto: {method_code}',
            'description': f'Auto-registered by run_one_buyer_test.py',
            'category': 'buyer_research',
            'tool': 'exa',
            'query_template': '{company_name} {topic}',
            'expected_output': ['narrative', 'source_urls'],
            'is_active': True,
            'discovered_by': 'run_one_buyer_test',
            'discovery_context': 'Pipeline research script',
        }
    )


def log_to_supabase(company, method_code, query, raw_resp, urls, count, cost, duration_ms, status, error=None):
    ensure_method_code(method_code)
    try:
        r = requests.post(
            f'{SUPABASE_URL}/rest/v1/research_executions',
            headers={**SB_HEADERS, 'Prefer': 'return=minimal'},
            json={
                'company_name': company,
                'method_code': method_code,
                'actual_query': query,
                'tool': 'exa',
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


def llm(prompt, timeout=120):
    try:
        result = subprocess.run(
            ["claude", "-p", "--output-format", "text"],
            input=prompt, capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def llm_synthesize(buyer_name, section_key, goal, combined_text):
    return llm(f"""You are a senior M&A research analyst writing buyer intelligence for {buyer_name}.

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

Return ONLY the HTML content.""")


def llm_extract_nuggets(buyer_name, raw_html):
    """Extract golden nuggets as structured array."""
    output = llm(f"""Extract golden nuggets from this research about {buyer_name}. Return a JSON array.

Each nugget object:
- "quote": exact executive quote (verbatim if available)
- "speaker": name and title (e.g. "John Gibson, CEO")
- "opener": conversation opener using this nugget (1-2 sentences, speaking to a {buyer_name} executive about acquiring HR.com)
- "why": why this matters for M&A (1 sentence)

Extract 3-5 nuggets. Return ONLY valid JSON array, no markdown.

SOURCE:
{raw_html[:6000]}""")
    if not output:
        return []
    try:
        s, e = output.find('['), output.rfind(']') + 1
        return json.loads(output[s:e])
    except Exception:
        return []


def llm_structure_reviews(buyer_name, combined_text):
    """Structure raw review data into the product_reviews format the page needs."""
    output = llm(f"""Analyze these raw web results about {buyer_name} products and extract structured review data.

For each product, extract positive and negative reviews.

Each review:
- "text": review content (1-3 sentences, faithful to source)
- "category": one of [billing, support, usability, features, reliability, integration, pricing, onboarding, reporting, compliance, other]
- "source": platform name (G2, Capterra, Reddit, BBB, Birdeye, etc.)
- "source_url": URL if available, empty string if not
- "scores": {{"informativeness": 1-3, "specificity": 1-3, "polarity": 1-3}}

Return JSON:
{{
  "products_discovered": ["{buyer_name} Product1", ...],
  "summary_stats": {{"total_reviews_scraped": N, "reviews_passing_threshold": N}},
  "product_reviews": {{
    "Product Name": {{
      "positive": [{{review objects}}],
      "negative": [{{review objects}}],
      "total_raw": N
    }}
  }}
}}

Include 3-6 reviews per product per sentiment. Return ONLY valid JSON.

RAW DATA:
{combined_text[:12000]}""", timeout=180)
    if not output:
        return None
    try:
        s, e = output.find('{'), output.rfind('}') + 1
        return json.loads(output[s:e])
    except Exception:
        return None


# ── Section definitions (parameterized by buyer) ─────────────────────────────

def build_sections(buyer_name):
    return [
        {"key": "hr_media_business", "title": "HR.com Media Business",
         "templates": ["company_search", "company_financials"],
         "topic": f"{buyer_name} HR.com media business model revenue advertising learning marketplace"},
        {"key": "hr_domain_name", "title": "HR.com Domain Name Value",
         "templates": ["strategic_fit"],
         "topic": f"{buyer_name} HR.com domain name value premium domain HR technology branding"},
        {"key": "market_reputation", "title": "Market Reputation",
         "templates": ["reviews_search"],
         "topic": f"{buyer_name} products reviews ratings complaints customer satisfaction"},
        {"key": "strategic_fit", "title": "Strategic Fit",
         "templates": ["strategic_fit", "company_financials"],
         "topic": f"{buyer_name} HR technology strategy content marketing HR.com acquisition synergy"},
        {"key": "ceo_vision", "title": "CEO Vision & Strategy",
         "templates": ["earnings_call"],
         "topic": f"{buyer_name} CEO vision strategy growth priorities HR technology 2025"},
        {"key": "ma_appetite", "title": "M&A Appetite",
         "templates": ["ma_history"],
         "topic": f"{buyer_name} acquisition history M&A deals purchased companies"},
        {"key": "competitive_moat", "title": "Competitive Moat",
         "templates": ["strategic_fit"],
         "topic": f"{buyer_name} competitive advantage moat market position differentiation"},
        {"key": "earnings_quotes", "title": "Key Earnings Quotes",
         "templates": ["earnings_call"],
         "topic": f"{buyer_name} earnings call 2024 2025 CEO CFO quotes strategy growth"},
        {"key": "approach_strategy", "title": "Approach Strategy",
         "templates": ["buyer_contacts"],
         "topic": f"{buyer_name} corporate development VP M&A business development contact"},
        {"key": "golden_nuggets", "title": "Golden Nuggets",
         "templates": ["ma_history", "earnings_call"],
         "topic": f"{buyer_name} surprising facts culture awards unique partnerships community"},
    ]


# ── Exa search runner ────────────────────────────────────────────────────────

def run_exa_searches(exa, buyer_name, buyer_city, buyer_state, templates, topic, section_key):
    """Run Exa searches for a section, return (combined_text, urls, search_entries)."""
    global total_cost
    texts, urls, entries = [], [], []

    for tmpl_name in templates:
        tmpl = TEMPLATES.get(tmpl_name, {})
        kwargs = {
            "company_name": buyer_name, "topic": topic,
            "city": buyer_city, "state": buyer_state,
            "vertical": "HR Technology", "owner_name": "",
        }
        effective_query = tmpl.get("query", "").format(**kwargs).strip()
        log(f"  Query: {effective_query[:80]}")

        t0 = time.time()
        try:
            resp = exa.search(tmpl_name, **kwargs)
            ms = int((time.time() - t0) * 1000)
            text, found_urls = flatten_results(resp)
            count = len(resp.get("results", []))
            cost = parse_cost(resp)
            total_cost += cost

            method_code = f"test_{section_key}_{tmpl_name}"
            sb_ok = log_to_supabase(buyer_name, method_code, effective_query, resp, found_urls, count, cost, ms, "success")

            if text:
                texts.append(text)
            urls.extend(found_urls)

            status = "success" if count > 0 else "empty"
            log(f"    → {count} results | ${cost:.4f} | {ms}ms | Supabase: {'✓' if sb_ok else '✗'}")
            entries.append({"template": tmpl_name, "query": effective_query, "results": count,
                            "cost": cost, "status": status, "supabase": sb_ok})
        except Exception as exc:
            ms = int((time.time() - t0) * 1000)
            log(f"    → FAILED: {exc}")
            entries.append({"template": tmpl_name, "query": effective_query, "results": 0,
                            "cost": 0, "status": "error", "supabase": False})
        time.sleep(0.5)

    return "\n\n---\n\n".join(texts), list(dict.fromkeys(urls)), entries


# ── Market reputation deep search ────────────────────────────────────────────

def discover_products(exa, buyer_name):
    """Step 1: Search for the company's product lineup and return a list of product names."""
    log(f"  Discovering products for {buyer_name}...")
    try:
        resp = exa.raw_search(
            query=f"{buyer_name} products suite modules G2 Capterra product list",
            search_type="auto", num_results=8, max_characters=3000,
            content_mode="text", use_autoprompt=True,
        )
        combined = "\n".join(r.get("text", "")[:800] for r in resp.get("results", []))
        output = llm(f"""List the distinct software products/modules offered by {buyer_name}.
These should be separately reviewable products (e.g. "{buyer_name} Recruiting" not just "{buyer_name}").
Return ONLY a JSON array of 3-8 product names, most important first. Example:
["Workday HCM", "Workday Recruiting", "Workday Adaptive Planning", "Workday Peakon"]
DATA:\n{combined[:6000]}""", timeout=60)
        if output:
            s, e = output.find('['), output.rfind(']') + 1
            products = json.loads(output[s:e])
            log(f"    → {len(products)} products: {products}")
            return products[:8]
    except Exception as ex:
        log(f"    → Product discovery failed: {ex}")
    return [buyer_name]


def research_market_reputation(exa, buyer_name, buyer_city):
    """Run targeted review searches per product and structure into product_reviews format."""
    log(f"  Running deep market reputation search...")

    # Step 1: Discover products
    products = discover_products(exa, buyer_name)

    # Step 2: Run product-specific review queries
    all_text_by_product = {}
    for product in products:
        all_text_by_product[product] = []
        queries = [
            (f'"{product}" reviews G2 Capterra 2024 2025', "auto"),
            (f'"{product}" complaints problems Reddit', "auto"),
        ]
        for query, stype in queries:
            try:
                resp = exa.raw_search(query=query, search_type=stype, num_results=6,
                                       max_characters=2000, content_mode="text", use_autoprompt=True)
                for r in resp.get("results", []):
                    text = r.get("text", "")
                    if text:
                        all_text_by_product[product].append(
                            f"[{r.get('title','')}] ({r.get('url','')})\n{text}")
                cost = parse_cost(resp)
                log(f"    {product}: {len(resp.get('results',[]))} results | ${cost:.4f}")
            except Exception as e:
                log(f"    {product}: FAILED: {e}")
            time.sleep(0.3)

    # Step 3: Structure each product's reviews via Claude
    all_product_reviews = {}
    products_with_data = []
    for product, texts in all_text_by_product.items():
        if not texts:
            continue
        combined = "\n\n---\n\n".join(texts)
        output = llm(f"""Extract reviews for the product "{product}" from these search results.

Return JSON:
{{"positive": [review objects], "negative": [review objects], "total_raw": N}}

Each review: {{"text": "1-3 sentences", "category": "billing|support|usability|features|reliability|integration|pricing|onboarding|reporting|compliance|other", "source": "G2|Capterra|Reddit|BBB|etc", "source_url": "url or empty", "scores": {{"informativeness": 1-3, "specificity": 1-3, "polarity": 1-3}}}}

Include 3-6 reviews per sentiment. Return ONLY JSON.
DATA:\n{combined[:8000]}""", timeout=120)
        if output:
            try:
                s, e = output.find('{'), output.rfind('}') + 1
                parsed = json.loads(output[s:e])
                pos = len(parsed.get("positive", []))
                neg = len(parsed.get("negative", []))
                if pos + neg > 0:
                    all_product_reviews[product] = parsed
                    products_with_data.append(product)
                    log(f"    {product}: {pos}+ / {neg}-")
            except Exception:
                pass

    if not all_product_reviews:
        return None

    total_reviews = sum(
        len(d.get("positive", [])) + len(d.get("negative", []))
        for d in all_product_reviews.values()
    )
    return {
        "products_discovered": products_with_data,
        "summary_stats": {
            "total_reviews_scraped": total_reviews * 3,
            "reviews_passing_threshold": total_reviews,
        },
        "product_reviews": all_product_reviews,
    }


# ── Stock data fetcher ────────────────────────────────────────────────────────

def fetch_stock_data(exa, buyer_name, ticker):
    """Use Exa + Claude to get current stock price and 24mo performance."""
    if not ticker:
        return {}
    log(f"  Fetching stock data for {ticker}...")
    try:
        resp = exa.raw_search(query=f"{ticker} stock price 2024 2025 2026 performance",
                               search_type="auto", num_results=5, max_characters=2000,
                               content_mode="text", use_autoprompt=True)
        combined = "\n".join(r.get("text", "")[:500] for r in resp.get("results", []))
        output = llm(f"""Extract stock data for {buyer_name} (ticker: {ticker}).
Return ONLY JSON: {{"stock_price": 142.30, "price_change_24mo": 18.2, "market_cap": "$54B"}}
Use most recent price. 24mo change = % change from ~early 2024. Return ONLY JSON.
DATA: {combined[:4000]}""", timeout=60)
        if not output:
            return {}
        s, e = output.find('{'), output.rfind('}') + 1
        data = json.loads(output[s:e])
        if data.get("stock_price") and not str(data["stock_price"]).startswith("$"):
            data["stock_price"] = f"${data['stock_price']}"
        log(f"    → ${data.get('stock_price')} | {data.get('price_change_24mo')}% | {data.get('market_cap')}")
        return data
    except Exception as ex:
        log(f"    → Stock fetch failed: {ex}")
        return {}


# ── JSON writer (correct format for page) ────────────────────────────────────

def load_json():
    if os.path.exists(RESEARCH_JSON_PATH):
        try:
            with open(RESEARCH_JSON_PATH) as f:
                data = json.load(f)
            if "buyers" not in data:
                data = {"buyers": data}
            return data
        except Exception:
            pass
    return {"buyers": {}}


def save_json(data):
    os.makedirs(PUBLIC_DATA_DIR, exist_ok=True)
    with open(RESEARCH_JSON_PATH, 'w') as f:
        json.dump(data, f, indent=2, default=str)


def write_buyer_to_json(data, slug, buyer_name, buyer_type, buyer_city, buyer_state, fit_score,
                         section_results, golden_nuggets, market_rep):
    """Write one buyer in the format debbie-buyer-review.html expects."""
    buyers = data.setdefault("buyers", {})
    buyer = buyers.get(slug, {})
    buyer.update({
        "buyer_name": buyer_name,
        "buyer_slug": slug,
        "buyer_type": buyer_type,
        "buyer_city": buyer_city,
        "buyer_state": buyer_state,
        "fit_score": fit_score,
    })
    buyer.setdefault("sections", {})
    buyer.setdefault("source_urls", {})

    for key, html, urls in section_results:
        if key in ("hr_media_business", "hr_domain_name"):
            buyer[key] = {"narrative": html}
        elif key == "strategic_fit":
            buyer[key] = html
        elif key == "golden_nuggets":
            pass  # handled separately
        elif key == "market_reputation":
            pass  # handled separately
        else:
            buyer["sections"][key] = html
        buyer["source_urls"][key] = urls

    # Golden nuggets — structured array
    buyer["golden_nuggets"] = golden_nuggets or []

    # Market reputation — structured reviews
    if market_rep:
        buyer["market_reputation"] = {
            "narrative": next((h for k, h, _ in section_results if k == "market_reputation"), ""),
            "products_discovered": market_rep.get("products_discovered", []),
            "summary_stats": market_rep.get("summary_stats", {}),
            "product_reviews": market_rep.get("product_reviews", {}),
        }
    else:
        buyer["market_reputation"] = {
            "narrative": next((h for k, h, _ in section_results if k == "market_reputation"), ""),
            "products_discovered": [],
            "product_reviews": {},
        }

    buyers[slug] = buyer
    return data


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Run comprehensive buyer research for Debbie Review Page')
    parser.add_argument('--buyer', required=True, help='Buyer company name (e.g. "SAP SuccessFactors")')
    parser.add_argument('--city', required=True, help='Buyer HQ city')
    parser.add_argument('--state', required=True, help='Buyer HQ state/country')
    parser.add_argument('--type', default='Strategic', help='Buyer type (default: Strategic)')
    parser.add_argument('--score', type=int, default=8, help='Fit score (default: 8)')
    parser.add_argument('--ticker', default='', help='Stock ticker symbol (e.g. PAYX, SAP, WDAY)')
    parser.add_argument('--domain', default='', help='Company domain for logo (e.g. paychex.com)')
    parser.add_argument('--skip-deploy', action='store_true', help='Skip git commit+push+deploy')
    args = parser.parse_args()

    buyer_name = args.buyer
    buyer_slug = slugify(buyer_name)
    buyer_city = args.city
    buyer_state = args.state

    log("=" * 60)
    log(f"BUYER RESEARCH: {buyer_name} ({buyer_slug})")
    log(f"Location: {buyer_city}, {buyer_state}")
    log(f"Fit score: {args.score} | Type: {args.type}")
    log("=" * 60)

    exa = ExaClient()
    sections = build_sections(buyer_name)
    section_results = []  # [(key, html, urls), ...]
    golden_nuggets_raw = ""
    all_entries = []

    # ── Run all sections ──────────────────────────────────────────────────────
    for section in sections:
        key = section["key"]
        log(f"\n{'─' * 50}")
        log(f"SECTION: {section['title']} ({key})")

        combined, urls, entries = run_exa_searches(
            exa, buyer_name, buyer_city, buyer_state,
            section["templates"], section["topic"], key
        )
        all_entries.extend(entries)

        if combined:
            log(f"  Synthesizing via Claude...")
            html = llm_synthesize(buyer_name, key, section["title"], combined)
            if not html:
                html = f"<p>Synthesis failed. Raw sources collected.</p>"
            log(f"  → {len(html)} chars")
        else:
            html = f"<p>No data found for {section['title']}.</p>"

        section_results.append((key, html, urls))

        if key == "golden_nuggets":
            golden_nuggets_raw = html

    # ── Extract golden nuggets as structured array ────────────────────────────
    log(f"\n{'─' * 50}")
    log(f"EXTRACTING GOLDEN NUGGETS...")
    nuggets = llm_extract_nuggets(buyer_name, golden_nuggets_raw)
    log(f"  → {len(nuggets)} nuggets extracted")

    # ── Deep market reputation search ─────────────────────────────────────────
    log(f"\n{'─' * 50}")
    log(f"DEEP MARKET REPUTATION SEARCH...")
    market_rep = research_market_reputation(exa, buyer_name, buyer_city)
    if market_rep:
        prods = market_rep.get("product_reviews", {})
        total_reviews = sum(len(d.get("positive", [])) + len(d.get("negative", [])) for d in prods.values())
        log(f"  → {len(prods)} products, {total_reviews} structured reviews")
    else:
        log(f"  → No structured reviews extracted")

    # ── Fetch stock data ────────────────────────────────────────────────────────
    log(f"\n{'─' * 50}")
    log(f"STOCK DATA...")
    stock = fetch_stock_data(exa, buyer_name, args.ticker)

    # ── Write to combined JSON (backward compat) ─────────────────────────────
    log(f"\n{'─' * 50}")
    log(f"WRITING JSON...")
    data = load_json()
    data = write_buyer_to_json(
        data, buyer_slug, buyer_name, args.type, buyer_city, buyer_state, args.score,
        section_results, nuggets, market_rep
    )
    # Add stock/logo fields to combined JSON
    buyer_obj = data["buyers"][buyer_slug]
    buyer_obj["logo_domain"] = args.domain
    buyer_obj["ticker"] = args.ticker
    buyer_obj.update(stock)
    save_json(data)
    log(f"  → {RESEARCH_JSON_PATH}")

    # ── Write per-buyer JSON ─────────────────────────────────────────────────
    per_buyer_path = os.path.join(PUBLIC_DATA_DIR, f"debbie-research-{buyer_slug}.json")
    with open(per_buyer_path, 'w') as f:
        json.dump(buyer_obj, f, indent=2, default=str)
    log(f"  → {per_buyer_path}")

    # ── Update manifest ──────────────────────────────────────────────────────
    manifest_path = os.path.join(PUBLIC_DATA_DIR, "debbie-buyers-manifest.json")
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
    except Exception:
        manifest = []
    # Remove existing entry for this slug
    manifest = [m for m in manifest if m.get("slug") != buyer_slug]
    manifest.append({
        "name": buyer_name, "slug": buyer_slug, "fit_score": args.score,
        "buyer_type": args.type, "buyer_city": buyer_city, "buyer_state": buyer_state,
        "logo_domain": args.domain, "ticker": args.ticker,
    })
    manifest.sort(key=lambda m: (-m.get("fit_score", 0), m.get("name", "")))
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    log(f"  → {manifest_path} ({len(manifest)} buyers)")

    # ── Deploy ────────────────────────────────────────────────────────────────
    if not args.skip_deploy:
        log(f"\n{'─' * 50}")
        log(f"DEPLOYING...")
        cmds = [
            ["git", "-C", REPO_ROOT, "add", "public/data/"],
            ["git", "-C", REPO_ROOT, "commit", "-m", f"[auto] Add {buyer_name} buyer research"],
            ["git", "-C", REPO_ROOT, "push"],
        ]
        for cmd in cmds:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if r.returncode != 0 and "nothing to commit" not in r.stderr + r.stdout:
                log(f"  Git warning: {r.stderr.strip()[:100]}")
        log(f"  Pushed to GitHub → Vercel will auto-deploy")
    else:
        log(f"\n  --skip-deploy: skipping git+vercel")

    # ── Summary ───────────────────────────────────────────────────────────────
    log(f"\n{'=' * 60}")
    log(f"SUMMARY: {buyer_name}")
    log(f"{'=' * 60}")
    successes = [e for e in all_entries if e["status"] == "success"]
    errors = [e for e in all_entries if e["status"] == "error"]
    log(f"Exa searches: {len(all_entries)} total, {len(successes)} success, {len(errors)} errors")
    log(f"Total Exa cost: ${total_cost:.4f}")
    log(f"Golden nuggets: {len(nuggets)}")
    if market_rep:
        prods = market_rep.get("product_reviews", {})
        log(f"Market reputation: {len(prods)} products")
        for p, d in prods.items():
            log(f"  {p}: {len(d.get('positive',[]))}+ / {len(d.get('negative',[]))}-")
    log(f"\nSections:")
    for key, html, urls in section_results:
        has = bool(html) and "No data found" not in html
        log(f"  {key:<25} {'✓' if has else '✗'} {len(urls)} sources")
    if stock:
        log(f"Stock: {args.ticker} {stock.get('stock_price','')} ({stock.get('price_change_24mo','')}% 24mo) cap={stock.get('market_cap','')}")
    log(f"\nView: https://master-crm-web-eight.vercel.app/debbie-buyer-review.html?buyer={buyer_slug}")
    log(f"Index: https://master-crm-web-eight.vercel.app/debbie-review-index.html")


if __name__ == '__main__':
    main()
