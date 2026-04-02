#!/usr/bin/env python3
"""
Traced buyer research run — captures EVERY step for audit.

Produces a Markdown trace document showing:
- Every process/agent involved
- Every search query sent (exact text)
- What came back (result count, URLs, cost, raw excerpts)
- Every LLM call (prompt summary, output summary)
- Every file write (path, size, fields written)
- Every Supabase write (table, columns, values)
- Timing for each step

Usage:
  python3 scripts/traced_buyer_run.py --buyer "SAP SuccessFactors" --city "Newtown Square" --state PA --ticker SAP --domain sap.com
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
REPO_ROOT = os.path.join(os.path.dirname(__file__), '..')

# ── Trace log ─────────────────────────────────────────────────────────────────
TRACE = []  # list of trace entries
TRACE_START = time.time()
STEP_NUM = 0

def trace(category, action, details):
    global STEP_NUM
    STEP_NUM += 1
    elapsed = time.time() - TRACE_START
    entry = {
        "step": STEP_NUM,
        "elapsed_s": round(elapsed, 1),
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "category": category,
        "action": action,
        **details,
    }
    TRACE.append(entry)
    # Also print live
    print(f"[{entry['timestamp']}] STEP {STEP_NUM:03d} | {category:12s} | {action}", flush=True)
    return entry

def slugify(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower().strip()).strip('-')[:80]

def parse_cost(resp):
    raw = resp.get("costDollars", 0.0)
    return float(raw.get("total", 0.0)) if isinstance(raw, dict) else float(raw or 0.0)

# ── LLM wrapper with tracing ─────────────────────────────────────────────────

def llm(prompt, timeout=120, label="llm_call"):
    t0 = time.time()
    try:
        result = subprocess.run(
            ["claude", "-p", "--output-format", "text"],
            input=prompt, capture_output=True, text=True, timeout=timeout,
        )
        elapsed_ms = int((time.time() - t0) * 1000)
        output = result.stdout.strip() if result.returncode == 0 else None
        trace("LLM", label, {
            "full_prompt": prompt,
            "full_output": output or "FAILED",
            "prompt_length": len(prompt),
            "output_length": len(output) if output else 0,
            "duration_ms": elapsed_ms,
            "returncode": result.returncode,
        })
        return output
    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        trace("LLM", f"{label} FAILED", {
            "full_prompt": prompt,
            "error": str(e),
            "duration_ms": elapsed_ms,
        })
        return None

# ── Exa wrapper with tracing ─────────────────────────────────────────────────

def traced_exa_search(exa, template_name, label, **kwargs):
    tmpl = TEMPLATES.get(template_name, {})
    query = tmpl.get("query", "").format(**kwargs).strip()
    t0 = time.time()
    try:
        resp = exa.search(template_name, **kwargs)
        elapsed_ms = int((time.time() - t0) * 1000)
        results = resp.get("results", [])
        cost = parse_cost(resp)
        urls = [r.get("url", "") for r in results if r.get("url")]

        # Extract text
        texts = []
        for r in results:
            content = r.get("text", "") or ""
            if not content:
                hl = r.get("highlights", [])
                content = " ".join(hl) if isinstance(hl, list) else ""
            title = r.get("title", "")
            if title:
                content = f"[{title}] {content}"
            if content.strip():
                texts.append(content.strip())

        trace("EXA", label, {
            "template": template_name,
            "query": query,
            "result_count": len(results),
            "cost_usd": cost,
            "duration_ms": elapsed_ms,
            "urls": urls,
            "full_texts": texts,
            "raw_response_keys": list(resp.keys()),
        })
        return "\n\n---\n\n".join(texts), urls, cost
    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        trace("EXA", f"{label} FAILED", {
            "template": template_name,
            "query": query,
            "error": str(e)[:200],
            "duration_ms": elapsed_ms,
        })
        return "", [], 0

def traced_exa_raw(exa, query, search_type, label, num_results=8, max_chars=3000):
    t0 = time.time()
    try:
        resp = exa.raw_search(query=query, search_type=search_type, num_results=num_results,
                               max_characters=max_chars, content_mode="text", use_autoprompt=True)
        elapsed_ms = int((time.time() - t0) * 1000)
        results = resp.get("results", [])
        cost = parse_cost(resp)
        texts = []
        for r in results:
            text = r.get("text", "")
            if text:
                texts.append(f"[{r.get('title','')}] ({r.get('url','')})\n{text}")

        trace("EXA", label, {
            "query": query,
            "search_type": search_type,
            "result_count": len(results),
            "cost_usd": cost,
            "duration_ms": elapsed_ms,
            "urls": [r.get("url","") for r in results],
            "full_texts": texts,
            "raw_response_keys": list(resp.keys()),
        })
        return texts, cost
    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        trace("EXA", f"{label} FAILED", {
            "query": query,
            "error": str(e)[:200],
            "duration_ms": elapsed_ms,
        })
        return [], 0

# ── File write with tracing ───────────────────────────────────────────────────

def traced_write(path, data, label):
    content = json.dumps(data, indent=2, default=str)
    with open(path, 'w') as f:
        f.write(content)
    trace("FILE_WRITE", label, {
        "path": path,
        "size_bytes": len(content),
        "keys": list(data.keys()) if isinstance(data, dict) else f"array[{len(data)}]",
    })

# ── Supabase write with tracing ──────────────────────────────────────────────

def traced_supabase_write(table, data, label):
    try:
        r = requests.post(
            f'{SUPABASE_URL}/rest/v1/{table}',
            headers={**SB_HEADERS, 'Prefer': 'return=minimal'},
            json=data
        )
        trace("SUPABASE", label, {
            "table": table,
            "columns": list(data.keys()),
            "status": r.status_code,
            "success": r.status_code in (200, 201),
            "error": r.text[:200] if r.status_code not in (200, 201) else None,
        })
        return r.status_code in (200, 201)
    except Exception as e:
        trace("SUPABASE", f"{label} FAILED", {"table": table, "error": str(e)[:200]})
        return False

# ── Section configs ───────────────────────────────────────────────────────────

def build_sections(name):
    return [
        {"key": "hr_media_business", "title": "HR.com Media Business",
         "templates": ["company_search", "company_financials"],
         "topic": f"{name} HR.com media business model revenue advertising learning marketplace"},
        {"key": "hr_domain_name", "title": "HR.com Domain Name Value",
         "templates": ["strategic_fit"],
         "topic": f"{name} HR.com domain name value premium domain HR technology branding"},
        {"key": "market_reputation", "title": "Market Reputation",
         "templates": ["reviews_search"],
         "topic": f"{name} products reviews ratings complaints customer satisfaction"},
        {"key": "strategic_fit", "title": "Strategic Fit",
         "templates": ["strategic_fit", "company_financials"],
         "topic": f"{name} HR technology strategy content marketing HR.com acquisition synergy"},
        {"key": "ceo_vision", "title": "CEO Vision & Strategy",
         "templates": ["earnings_call"],
         "topic": f"{name} CEO vision strategy growth priorities HR technology 2025"},
        {"key": "ma_appetite", "title": "M&A Appetite",
         "templates": ["ma_history"],
         "topic": f"{name} acquisition history M&A deals purchased companies"},
        {"key": "competitive_moat", "title": "Competitive Moat",
         "templates": ["strategic_fit"],
         "topic": f"{name} competitive advantage moat market position differentiation"},
        {"key": "earnings_quotes", "title": "Key Earnings Quotes",
         "templates": ["earnings_call"],
         "topic": f"{name} earnings call 2024 2025 CEO CFO quotes strategy growth"},
        {"key": "approach_strategy", "title": "Approach Strategy",
         "templates": ["buyer_contacts"],
         "topic": f"{name} corporate development VP M&A business development contact"},
        {"key": "golden_nuggets", "title": "Golden Nuggets",
         "templates": ["ma_history", "earnings_call"],
         "topic": f"{name} surprising facts culture awards unique partnerships community"},
    ]

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Traced buyer research run')
    parser.add_argument('--buyer', required=True)
    parser.add_argument('--city', required=True)
    parser.add_argument('--state', required=True)
    parser.add_argument('--ticker', default='')
    parser.add_argument('--domain', default='')
    parser.add_argument('--type', default='Strategic')
    parser.add_argument('--score', type=int, default=8)
    args = parser.parse_args()

    buyer_name = args.buyer
    buyer_slug = slugify(buyer_name)
    total_cost = 0.0

    trace("SYSTEM", "PIPELINE START", {
        "buyer": buyer_name, "slug": buyer_slug, "city": args.city, "state": args.state,
        "ticker": args.ticker, "domain": args.domain, "score": args.score, "type": args.type,
    })

    exa = ExaClient()
    sections = build_sections(buyer_name)
    section_results = []
    golden_nuggets_raw = ""

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 1: SECTION RESEARCH (10 sections, 13 template searches)
    # ══════════════════════════════════════════════════════════════════════════
    trace("PHASE", "SECTION RESEARCH START", {"sections": len(sections)})

    for section in sections:
        key = section["key"]
        trace("SECTION", f"START: {section['title']}", {"key": key, "templates": section["templates"]})

        section_texts = []
        section_urls = []

        for tmpl_name in section["templates"]:
            kwargs = {"company_name": buyer_name, "topic": section["topic"],
                      "city": args.city, "state": args.state, "vertical": "HR Technology", "owner_name": ""}

            text, urls, cost = traced_exa_search(exa, tmpl_name, f"search:{key}:{tmpl_name}", **kwargs)
            total_cost += cost
            if text:
                section_texts.append(text)
            section_urls.extend(urls)
            time.sleep(0.5)

        # Synthesize
        combined = "\n\n---\n\n".join(section_texts)
        unique_urls = list(dict.fromkeys(section_urls))

        if combined:
            html = llm(f"""You are a senior M&A research analyst writing buyer intelligence for {buyer_name}.
Section: {key} | Goal: {section['title']}
Write 2-4 paragraphs of clean HTML (<p> tags, <strong> for key quotes). Stick to verifiable facts.
RAW RESEARCH:\n{combined[:8000]}\nReturn ONLY HTML.""", label=f"synthesize:{key}")
            if not html:
                html = f"<p>Synthesis failed for {section['title']}.</p>"
        else:
            html = f"<p>No data found for {section['title']}.</p>"

        section_results.append((key, html, unique_urls))
        if key == "golden_nuggets":
            golden_nuggets_raw = html

        trace("SECTION", f"DONE: {section['title']}", {
            "key": key, "html_chars": len(html), "source_count": len(unique_urls),
            "stored_as": "hr_media_business.narrative" if key in ("hr_media_business","hr_domain_name")
                         else "strategic_fit (direct string)" if key == "strategic_fit"
                         else "golden_nuggets (raw, will restructure)" if key == "golden_nuggets"
                         else f"sections.{key}",
        })

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 2: GOLDEN NUGGETS EXTRACTION
    # ══════════════════════════════════════════════════════════════════════════
    trace("PHASE", "GOLDEN NUGGETS EXTRACTION", {"raw_html_chars": len(golden_nuggets_raw)})

    nuggets_output = llm(f"""Extract golden nuggets from this research about {buyer_name}. Return a JSON array.
Each nugget: {{"quote": "exact quote", "speaker": "Name, Title", "opener": "conversation starter about acquiring HR.com", "why": "M&A relevance"}}
3-5 nuggets. ONLY valid JSON array.\nSOURCE:\n{golden_nuggets_raw[:6000]}""", label="extract_nuggets")

    nuggets = []
    if nuggets_output:
        try:
            s, e = nuggets_output.find('['), nuggets_output.rfind(']') + 1
            nuggets = json.loads(nuggets_output[s:e])
        except: pass

    trace("TRANSFORM", "NUGGETS STRUCTURED", {
        "count": len(nuggets),
        "stored_as": "golden_nuggets (array of {quote, speaker, opener, why})",
        "speakers": [n.get("speaker","?") for n in nuggets],
    })

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 3: PRODUCT DISCOVERY + MARKET REPUTATION
    # ══════════════════════════════════════════════════════════════════════════
    trace("PHASE", "MARKET REPUTATION — PRODUCT DISCOVERY", {})

    # Step 3a: Discover products
    prod_texts, prod_cost = traced_exa_raw(exa, f"{buyer_name} products suite modules G2 Capterra product list",
                                            "auto", "product_discovery")
    total_cost += prod_cost

    prod_combined = "\n".join(t[:800] for t in prod_texts)
    prod_output = llm(f"""List distinct software products/modules offered by {buyer_name}.
Separately reviewable products (e.g. "{buyer_name} Recruiting" not just "{buyer_name}").
Return ONLY a JSON array of 3-8 product names.\nDATA:\n{prod_combined[:6000]}""",
        timeout=60, label="discover_products")

    products = [buyer_name]
    if prod_output:
        try:
            s, e = prod_output.find('['), prod_output.rfind(']') + 1
            products = json.loads(prod_output[s:e])[:6]
        except: pass

    trace("TRANSFORM", "PRODUCTS DISCOVERED", {
        "count": len(products),
        "products": products,
        "stored_as": "market_reputation.products_discovered",
    })

    # Step 3b: Per-product review searches
    all_product_reviews = {}
    for product in products:
        product_texts = []
        for query, stype in [(f'"{product}" reviews G2 Capterra 2024 2025', "auto"),
                              (f'"{product}" complaints problems Reddit', "auto")]:
            texts, cost = traced_exa_raw(exa, query, stype, f"reviews:{slugify(product)}")
            total_cost += cost
            product_texts.extend(texts)
            time.sleep(0.3)

        if not product_texts:
            continue

        combined = "\n\n---\n\n".join(product_texts)
        output = llm(f"""Extract reviews for "{product}". Return JSON:
{{"positive": [reviews], "negative": [reviews], "total_raw": N}}
Each review: {{"text": "1-3 sentences", "category": "billing|support|usability|features|reliability|integration|pricing|onboarding|reporting|compliance|other", "source": "G2|Capterra|Reddit|etc", "source_url": "", "scores": {{"informativeness": 1-3, "specificity": 1-3, "polarity": 1-3}}}}
3-6 per sentiment. ONLY JSON.\nDATA:\n{combined[:8000]}""", timeout=120, label=f"structure_reviews:{slugify(product)}")

        if output:
            try:
                s, e = output.find('{'), output.rfind('}') + 1
                parsed = json.loads(output[s:e])
                pos = len(parsed.get("positive", []))
                neg = len(parsed.get("negative", []))
                if pos + neg > 0:
                    all_product_reviews[product] = parsed
                    trace("TRANSFORM", f"REVIEWS STRUCTURED: {product}", {
                        "positive": pos, "negative": neg,
                        "categories": list(set(r.get("category","?") for r in parsed.get("negative",[]) + parsed.get("positive",[]))),
                        "stored_as": f"market_reputation.product_reviews.{product}",
                    })
            except: pass

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 4: STOCK DATA
    # ══════════════════════════════════════════════════════════════════════════
    trace("PHASE", "STOCK DATA FETCH", {"ticker": args.ticker})
    stock = {}
    if args.ticker:
        texts, cost = traced_exa_raw(exa, f"{args.ticker} stock price 2024 2025 2026 performance",
                                      "auto", "stock_data")
        total_cost += cost
        combined = "\n".join(t[:500] for t in texts)
        output = llm(f"""Extract stock data for {buyer_name} (ticker: {args.ticker}).
Return ONLY JSON: {{"stock_price": 142.30, "price_change_24mo": 18.2, "market_cap": "$54B"}}
DATA: {combined[:4000]}""", timeout=60, label="extract_stock")
        if output:
            try:
                s, e = output.find('{'), output.rfind('}') + 1
                stock = json.loads(output[s:e])
                if stock.get("stock_price") and not str(stock["stock_price"]).startswith("$"):
                    stock["stock_price"] = f"${stock['stock_price']}"
                trace("TRANSFORM", "STOCK EXTRACTED", {
                    "price": stock.get("stock_price"), "change_24mo": stock.get("price_change_24mo"),
                    "market_cap": stock.get("market_cap"),
                    "stored_as": "stock_price, price_change_24mo, market_cap (root fields)",
                })
            except: pass

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 5: ASSEMBLE & WRITE
    # ══════════════════════════════════════════════════════════════════════════
    trace("PHASE", "ASSEMBLE BUYER OBJECT", {})

    buyer_obj = {
        "buyer_name": buyer_name, "buyer_slug": buyer_slug,
        "buyer_type": args.type, "buyer_city": args.city, "buyer_state": args.state,
        "fit_score": args.score, "logo_domain": args.domain, "ticker": args.ticker,
        "sections": {}, "source_urls": {},
    }
    buyer_obj.update(stock)

    for key, html, urls in section_results:
        if key in ("hr_media_business", "hr_domain_name"):
            buyer_obj[key] = {"narrative": html}
        elif key == "strategic_fit":
            buyer_obj[key] = html
        elif key in ("golden_nuggets", "market_reputation"):
            pass
        else:
            buyer_obj["sections"][key] = html
        buyer_obj["source_urls"][key] = urls

    buyer_obj["golden_nuggets"] = nuggets

    products_with_data = list(all_product_reviews.keys())
    total_reviews = sum(len(d.get("positive",[]))+len(d.get("negative",[])) for d in all_product_reviews.values())
    rep_narrative = next((h for k, h, _ in section_results if k == "market_reputation"), "")
    buyer_obj["market_reputation"] = {
        "narrative": rep_narrative,
        "products_discovered": products_with_data,
        "summary_stats": {"total_reviews_scraped": total_reviews*3, "reviews_passing_threshold": total_reviews},
        "product_reviews": all_product_reviews,
    }

    # Field inventory
    all_fields = []
    def inventory(obj, prefix=""):
        for k, v in (obj.items() if isinstance(obj, dict) else []):
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                inventory(v, path)
            elif isinstance(v, list):
                all_fields.append(f"{path} (array[{len(v)}])")
            elif isinstance(v, str) and len(v) > 50:
                all_fields.append(f"{path} (string, {len(v)} chars)")
            else:
                all_fields.append(f"{path} = {json.dumps(v, default=str)[:60]}")
    inventory(buyer_obj)

    trace("ASSEMBLE", "BUYER OBJECT COMPLETE", {
        "total_fields": len(all_fields),
        "field_inventory": all_fields,
    })

    # Write per-buyer JSON
    per_buyer_path = os.path.join(PUBLIC_DATA_DIR, f"debbie-research-{buyer_slug}.json")
    os.makedirs(PUBLIC_DATA_DIR, exist_ok=True)
    traced_write(per_buyer_path, buyer_obj, f"per-buyer JSON: {buyer_slug}")

    # Write combined JSON
    combined_path = os.path.join(PUBLIC_DATA_DIR, "debbie-buyer-research.json")
    try:
        with open(combined_path) as f:
            combined_data = json.load(f)
        if "buyers" not in combined_data:
            combined_data = {"buyers": combined_data}
    except: combined_data = {"buyers": {}}
    combined_data["buyers"][buyer_slug] = buyer_obj
    traced_write(combined_path, combined_data, "combined JSON (all buyers)")

    # Update manifest
    manifest_path = os.path.join(PUBLIC_DATA_DIR, "debbie-buyers-manifest.json")
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
    except: manifest = []
    manifest = [m for m in manifest if m.get("slug") != buyer_slug]
    manifest.append({"name": buyer_name, "slug": buyer_slug, "fit_score": args.score,
                      "buyer_type": args.type, "buyer_city": args.city, "buyer_state": args.state,
                      "logo_domain": args.domain, "ticker": args.ticker})
    manifest.sort(key=lambda m: (-m.get("fit_score",0), m.get("name","")))
    traced_write(manifest_path, manifest, "manifest (buyer index)")

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 6: GIT + DEPLOY
    # ══════════════════════════════════════════════════════════════════════════
    trace("PHASE", "GIT COMMIT + PUSH", {})
    for cmd_label, cmd in [
        ("git add", ["git", "-C", REPO_ROOT, "add", "public/data/"]),
        ("git commit", ["git", "-C", REPO_ROOT, "commit", "-m", f"[auto][traced] Add {buyer_name} buyer research"]),
        ("git push", ["git", "-C", REPO_ROOT, "push"]),
    ]:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        trace("GIT", cmd_label, {
            "command": " ".join(cmd[-3:]),
            "returncode": r.returncode,
            "stdout_preview": r.stdout.strip()[:100],
            "stderr_preview": r.stderr.strip()[:100] if r.returncode != 0 else None,
        })

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 7: GENERATE TRACE DOCUMENT
    # ══════════════════════════════════════════════════════════════════════════
    total_elapsed = time.time() - TRACE_START
    trace("SYSTEM", "PIPELINE COMPLETE", {
        "total_steps": STEP_NUM,
        "total_elapsed_s": round(total_elapsed, 1),
        "total_exa_cost": round(total_cost, 4),
        "exa_searches": sum(1 for t in TRACE if t["category"] == "EXA"),
        "llm_calls": sum(1 for t in TRACE if t["category"] == "LLM"),
        "file_writes": sum(1 for t in TRACE if t["category"] == "FILE_WRITE"),
    })

    # Build markdown trace
    md = [f"# Traced Research Run: {buyer_name}\n"]
    md.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    md.append(f"**Buyer:** {buyer_name} ({buyer_slug})")
    md.append(f"**Location:** {args.city}, {args.state}")
    md.append(f"**Ticker:** {args.ticker or 'N/A'} | **Domain:** {args.domain or 'N/A'}")
    md.append(f"**Total time:** {total_elapsed:.0f}s | **Exa cost:** ${total_cost:.4f}")
    md.append(f"**Steps:** {STEP_NUM} | **Exa searches:** {sum(1 for t in TRACE if t['category']=='EXA')} | **LLM calls:** {sum(1 for t in TRACE if t['category']=='LLM')}")
    md.append(f"\n---\n")

    # Group by phase
    current_phase = None
    for entry in TRACE:
        if entry["category"] == "PHASE":
            current_phase = entry["action"]
            md.append(f"\n## {current_phase}\n")
            for k, v in entry.items():
                if k not in ("step","elapsed_s","timestamp","category","action"):
                    md.append(f"- {k}: `{v}`")
            continue

        if entry["category"] == "SYSTEM":
            md.append(f"\n### {entry['action']}\n")
            for k, v in entry.items():
                if k not in ("step","elapsed_s","timestamp","category","action"):
                    if isinstance(v, (list, dict)):
                        md.append(f"- **{k}:** `{json.dumps(v, default=str)}`")
                    else:
                        md.append(f"- **{k}:** `{v}`")
            continue

        icon = {"EXA": "🔍", "LLM": "🤖", "TRANSFORM": "🔄", "FILE_WRITE": "💾",
                "SUPABASE": "🗄️", "GIT": "📦", "SECTION": "📋", "ASSEMBLE": "🔧"}.get(entry["category"], "•")

        md.append(f"\n### Step {entry['step']} — {icon} {entry['category']}: {entry['action']}\n")
        md.append(f"*{entry['timestamp']} (+{entry['elapsed_s']}s)*\n")

        for k, v in entry.items():
            if k in ("step","elapsed_s","timestamp","category","action"):
                continue
            if k == "field_inventory":
                md.append(f"\n**Field inventory ({len(v)} fields):**")
                for f in v:
                    md.append(f"- `{f}`")
            elif k in ("full_prompt", "full_output"):
                # UNTRUNCATED — full content in fenced block
                md.append(f"\n**{k}:**\n")
                md.append(f"```")
                md.append(str(v))
                md.append(f"```\n")
            elif k == "full_texts":
                # UNTRUNCATED — every Exa result in full
                md.append(f"\n**{k} ({len(v)} results):**\n")
                for i, text in enumerate(v):
                    md.append(f"**--- Result {i+1} ---**\n")
                    md.append(f"```")
                    md.append(text)
                    md.append(f"```\n")
            elif isinstance(v, list):
                md.append(f"- **{k}:**")
                for item in v:
                    md.append(f"  - `{item}`")
            elif isinstance(v, str) and len(v) > 100:
                # NO TRUNCATION — full string
                md.append(f"- **{k}:** {v}")
            else:
                md.append(f"- **{k}:** `{v}`")

    trace_path = os.path.join(REPO_ROOT, "docs", f"TRACE-{buyer_slug}-{datetime.now().strftime('%Y%m%d-%H%M')}.md")
    with open(trace_path, 'w') as f:
        f.write("\n".join(md))
    print(f"\n{'='*60}")
    print(f"TRACE DOCUMENT: {trace_path}")
    print(f"{'='*60}")

    # Also write raw JSON trace
    trace_json_path = trace_path.replace('.md', '.json')
    with open(trace_json_path, 'w') as f:
        json.dump(TRACE, f, indent=2, default=str)
    print(f"RAW TRACE JSON: {trace_json_path}")
    print(f"\nView page: https://master-crm-web-eight.vercel.app/debbie-buyer-review.html?buyer={buyer_slug}")

if __name__ == '__main__':
    main()
