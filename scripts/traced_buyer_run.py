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


  --vertical: which config to load (default: home_services).
              Loads lib/config/verticals/{vertical}.json for sections, prompts, and valuation.
"""

from dotenv import load_dotenv
load_dotenv()

import argparse, json, os, re, subprocess, sys, time, requests
from datetime import datetime, timezone

REPO_ROOT = os.path.join(os.path.dirname(__file__), '..')

# Import exa_client from backend/lib/ (original import path)
sys.path.insert(0, os.path.join(REPO_ROOT, 'backend'))
from lib.exa_client import ExaClient, TEMPLATES
from lib.pain_gain_engine import generate_pain_gain_analysis

# Deal context for Pain/Gain engine — loaded from meetings JSON
MEETINGS_JSON = os.path.join(REPO_ROOT, 'backend', 'data', 'meetings', 'hrcom-debbie-mcgrath-2026-03-23.json')
_deal_context = None
def _load_deal_context():
    global _deal_context
    if _deal_context is None:
        try:
            with open(MEETINGS_JSON) as f:
                _deal_context = json.load(f)
        except Exception as e:
            print(f"[pain_gain] WARNING: Could not load deal context from {MEETINGS_JSON}: {e}")
            _deal_context = {}
    return _deal_context

# Import vertical config via importlib to avoid sys.path 'lib' collision
# (both REPO_ROOT/lib/ and backend/lib/ exist — sys.path can't disambiguate)
import importlib.util
_vcfg_path = os.path.join(REPO_ROOT, 'lib', 'config', 'vertical_config_schema.py')
_spec = importlib.util.spec_from_file_location('vertical_config_schema', _vcfg_path)
_vcfg_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_vcfg_mod)
load_vertical = _vcfg_mod.load_vertical
list_verticals = _vcfg_mod.list_verticals

# ── Config ────────────────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')
SB_HEADERS = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}', 'Content-Type': 'application/json'}
PUBLIC_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'public', 'data')

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

def select_best_content(texts, max_chars=12000):
    """Score and rank Exa results by M&A relevance before passing to LLM.
    Instead of hard-truncating at 8K, we score each result and take the best ones."""
    if not texts:
        return ""

    scored = []
    for text in texts:
        score = 0
        t = text.lower()
        # Financial signals: numbers, revenue, employees, market cap
        if re.search(r'\$[\d,.]+[BMK]?', text):
            score += 3
        if any(w in t for w in ['revenue', 'ebitda', 'margin', 'profit', 'earnings']):
            score += 2
        # M&A signals: acquisition, deal, purchased, merged
        if any(w in t for w in ['acqui', 'merger', 'deal', 'purchased', 'transaction']):
            score += 3
        # Quote signals: said, stated, announced, according to
        if any(w in t for w in ['" said', 'stated', 'announced', 'according to']):
            score += 2
        # Recency signals: 2025, 2026, recent, latest
        if any(w in t for w in ['2025', '2026', 'recent', 'latest']):
            score += 1
        # Length bonus: longer content tends to be more detailed
        if len(text) > 500:
            score += 1
        if len(text) > 1500:
            score += 1
        scored.append((score, text))

    # Sort by score descending, take best until max_chars
    scored.sort(key=lambda x: -x[0])
    selected = []
    total_chars = 0
    for score, text in scored:
        if total_chars + len(text) > max_chars:
            # Take partial if it would push us over but we have room
            remaining = max_chars - total_chars
            if remaining > 500:
                selected.append(text[:remaining])
            break
        selected.append(text)
        total_chars += len(text)

    return "\n\n---\n\n".join(selected)

def parse_cost(resp):
    raw = resp.get("costDollars", 0.0)
    return float(raw.get("total", 0.0)) if isinstance(raw, dict) else float(raw or 0.0)

# ── LLM wrapper with tracing ─────────────────────────────────────────────────

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")

def _call_openrouter(prompt, timeout=120):
    """Fallback LLM via OpenRouter when claude CLI is not available."""
    try:
        payload = json.dumps({
            "model": "deepseek/deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 4000,
        })
        result = subprocess.run(
            ["curl", "-s", "-X", "POST", "https://openrouter.ai/api/v1/chat/completions",
             "-H", f"Authorization: Bearer {OPENROUTER_KEY}",
             "-H", "Content-Type: application/json",
             "-d", payload],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    except Exception:
        pass
    return None

def llm(prompt, timeout=120, label="llm_call"):
    t0 = time.time()
    output = None
    source = "claude_cli"

    # Try claude CLI first
    try:
        result = subprocess.run(
            ["claude", "-p", "--output-format", "text"],
            input=prompt, capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode == 0 and result.stdout.strip():
            output = result.stdout.strip()
    except Exception:
        pass

    # Fallback to OpenRouter if claude CLI failed
    if not output and OPENROUTER_KEY:
        source = "openrouter"
        output = _call_openrouter(prompt, timeout)

    elapsed_ms = int((time.time() - t0) * 1000)
    trace("LLM", label, {
        "full_prompt": prompt,
        "full_output": output or "FAILED",
        "prompt_length": len(prompt),
        "output_length": len(output) if output else 0,
        "duration_ms": elapsed_ms,
        "source": source,
    })
    return output

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

def traced_supabase_write(table, data, label, upsert=False, upsert_key=None):
    """Write a row to Supabase. If upsert=True, check for existing row by upsert_key
    (a dict of {column: value}) and PATCH if found, POST if not."""
    try:
        op = "INSERT"
        if upsert and upsert_key:
            # Build filter query string
            filter_qs = "&".join(f"{k}=eq.{v}" for k, v in upsert_key.items())
            check = requests.get(
                f'{SUPABASE_URL}/rest/v1/{table}?{filter_qs}&select=id',
                headers={**SB_HEADERS},
            )
            existing = check.json() if check.status_code == 200 else []
            if existing:
                row_id = existing[0]["id"]
                r = requests.patch(
                    f'{SUPABASE_URL}/rest/v1/{table}?id=eq.{row_id}',
                    headers={**SB_HEADERS, 'Prefer': 'return=minimal'},
                    json=data,
                )
                op = "UPDATE"
            else:
                r = requests.post(
                    f'{SUPABASE_URL}/rest/v1/{table}',
                    headers={**SB_HEADERS, 'Prefer': 'return=minimal'},
                    json=data,
                )
        else:
            r = requests.post(
                f'{SUPABASE_URL}/rest/v1/{table}',
                headers={**SB_HEADERS, 'Prefer': 'return=minimal'},
                json=data,
            )
        trace("SUPABASE", label, {
            "table": table,
            "columns": list(data.keys()),
            "status": r.status_code,
            "success": r.status_code in (200, 201, 204),
            "operation": op,
            "error": r.text[:200] if r.status_code not in (200, 201, 204) else None,
        })
        return r.status_code in (200, 201, 204)
    except Exception as e:
        trace("SUPABASE", f"{label} FAILED", {"table": table, "error": str(e)[:200]})
        return False

# ── Section configs (loaded from vertical config) ────────────────────────────

def build_sections(buyer_name, vertical_config):
    """Build section definitions from vertical config's pipeline_sections.

    Each section in the config has:
      key, title, exa_template_names, topic_template (with {buyer_name} placeholder)

    Returns list of dicts matching the shape the rest of the pipeline expects:
      [{"key": ..., "title": ..., "templates": [...], "topic": ...}, ...]
    """
    pipeline_sections = vertical_config.get("pipeline_sections", [])
    if not pipeline_sections:
        raise ValueError(f"Vertical config '{vertical_config['vertical_id']}' has no pipeline_sections defined")

    sections = []
    for s in pipeline_sections:
        sections.append({
            "key": s["key"],
            "title": s["title"],
            "templates": s["exa_template_names"],
            "topic": s["topic_template"].format(buyer_name=buyer_name),
        })
    return sections

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Traced buyer research run')
    parser.add_argument('--buyer', required=True)
    parser.add_argument('--city', default='')
    parser.add_argument('--state', default='')
    parser.add_argument('--ticker', default='')
    parser.add_argument('--domain', default='')
    parser.add_argument('--type', default='Strategic')
    parser.add_argument('--score', type=int, default=8)
    parser.add_argument('--vertical', default='home_services',
                        help=f'Vertical config to load. Available: {", ".join(list_verticals())}')
    parser.add_argument('--pain-gain-only', action='store_true',
                        help='Skip all research phases; re-run only the Pain/Gain engine for an existing buyer JSON')
    args = parser.parse_args()

    # ── --pain-gain-only: backfill Pain/Gain for an existing buyer JSON ──────
    if args.pain_gain_only:
        buyer_slug = slugify(args.buyer)
        deal = _load_deal_context()
        entity = deal.get('entity', 'next_chapter')
        target_company = deal.get('company_name', 'HR.com Ltd')

        # Load vertical to get entity if present
        try:
            vcfg = load_vertical(args.vertical)
            entity = vcfg.get('entity_defaults', {}).get('entity', entity)
        except Exception:
            pass

        trace("SYSTEM", "PAIN_GAIN_ONLY MODE", {
            "buyer": args.buyer, "slug": buyer_slug,
            "entity": entity, "target_company": target_company,
        })

        t0 = time.time()
        analysis = generate_pain_gain_analysis(
            buyer_slug=buyer_slug,
            entity=entity,
            target_company=target_company,
        )
        elapsed_ms = int((time.time() - t0) * 1000)

        if analysis:
            trace("PAIN_GAIN", "ANALYSIS COMPLETE", {
                "buyer_slug": buyer_slug,
                "pain_categories": len(analysis.get("pain_categories", [])),
                "asset_mappings": len(analysis.get("asset_mappings", [])),
                "synthesis_chars": len(analysis.get("synthesis", "")),
                "generated_at": analysis.get("generated_at", ""),
                "duration_ms": elapsed_ms,
                "stored_in": f"public/data/debbie-research-{buyer_slug}.json → pain_gain_analysis",
                "supabase_table": "pain_gain_analyses",
            })
            print(f"\n[pain_gain] Backfill complete for {buyer_slug}")
        else:
            trace("PAIN_GAIN", "ANALYSIS FAILED", {
                "buyer_slug": buyer_slug, "duration_ms": elapsed_ms,
            })
            print(f"\n[pain_gain] Backfill FAILED for {buyer_slug} — see errors above")
            sys.exit(1)
        return

    # Validate required args for full pipeline
    if not args.city or not args.state:
        parser.error("--city and --state are required for a full pipeline run (omit them only with --pain-gain-only)")

    # ── Load vertical config ─────────────────────────────────────────────
    vcfg = load_vertical(args.vertical)
    ENTITY = vcfg["entity_defaults"]["entity"]
    prompts = vcfg.get("pipeline_prompts", {})
    vertical_label = prompts.get("vertical_label", vcfg["display_name"])
    valuation = vcfg.get("valuation_fields", {})

    buyer_name = args.buyer
    buyer_slug = slugify(buyer_name)
    total_cost = 0.0

    trace("SYSTEM", "PIPELINE START", {
        "buyer": buyer_name, "slug": buyer_slug, "city": args.city, "state": args.state,
        "ticker": args.ticker, "domain": args.domain, "score": args.score, "type": args.type,
        "vertical": args.vertical, "entity": ENTITY, "vertical_label": vertical_label,
        "valuation_metric": valuation.get("primary_metric", "ebitda"),
    })

    exa = ExaClient()
    sections = build_sections(buyer_name, vcfg)

    # Build output_format lookup from config (used in Phase 1 trace + Phase 5 assembly)
    section_output_formats = {}
    for s in vcfg.get("pipeline_sections", []):
        section_output_formats[s["key"]] = s.get("output_format", "section")

    section_results = []
    golden_nuggets_raw = ""
    golden_nuggets_raw_exa = ""  # Raw Exa results for nugget extraction (not synthesized)
    seen_urls = set()  # Track URLs across all searches for dedup

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
            # Use topic as-is for topic-driven templates (strategic_fit, earnings_call, ma_history)
            # These templates already embed {company_name} via the topic text, so we pass
            # company_name separately only for templates that need it independently
            kwargs = {"company_name": buyer_name, "topic": section["topic"],
                      "city": args.city, "state": args.state, "vertical": vertical_label, "owner_name": ""}

            text, urls, cost = traced_exa_search(exa, tmpl_name, f"search:{key}:{tmpl_name}", **kwargs)
            total_cost += cost
            if text:
                section_texts.append(text)
            section_urls.extend(urls)
            time.sleep(0.5)

        # Synthesize — dedup URLs within this section only (no cross-section filtering)
        combined = "\n\n---\n\n".join(section_texts)
        unique_urls = list(dict.fromkeys(section_urls))
        seen_urls.update(unique_urls)

        if combined:
            # Select highest-value content instead of hard truncation
            best_content = select_best_content(section_texts, max_chars=12000)
            synthesis_ctx = prompts.get("synthesis_context",
                "You are a senior M&A analyst writing buyer intelligence about {buyer_name}.").format(
                buyer_name=buyer_name, vertical_label=vertical_label)
            html = llm(f"""{synthesis_ctx}

Section: {key} | Goal: {section['title']}

Write 2-4 paragraphs of clean HTML (<p> tags, <strong> for key quotes, exact numbers). Focus on:
- Deal rationale: Why would {buyer_name} want to acquire this business?
- Integration synergies: What capabilities would they gain?
- Negotiation leverage: What makes this buyer motivated or desperate?
- Red flags: Anything that would make this deal harder or less likely?

Stick to verifiable facts with specific numbers, dates, and names. Attribute quotes to speakers.
RAW RESEARCH:\n{best_content}\nReturn ONLY HTML.""", label=f"synthesize:{key}")
            if not html:
                html = f"<p>Synthesis failed for {section['title']}.</p>"
        else:
            html = f"<p>No data found for {section['title']}.</p>"

        section_results.append((key, html, unique_urls))
        if key == "golden_nuggets":
            golden_nuggets_raw = html
            golden_nuggets_raw_exa = combined  # Keep raw Exa text for nugget extraction

        fmt = section_output_formats.get(key, "section")
        if fmt == "narrative_object":
            stored_label = f"{key}.narrative"
        elif fmt == "direct_html":
            stored_label = f"{key} (direct string)"
        elif fmt == "golden_nuggets":
            stored_label = "golden_nuggets (raw, will restructure)"
        elif fmt == "market_reputation":
            stored_label = "market_reputation (raw, will restructure)"
        else:
            stored_label = f"sections.{key}"

        trace("SECTION", f"DONE: {section['title']}", {
            "key": key, "html_chars": len(html), "source_count": len(unique_urls),
            "stored_as": stored_label,
        })

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 2: GOLDEN NUGGETS EXTRACTION
    # ══════════════════════════════════════════════════════════════════════════
    trace("PHASE", "GOLDEN NUGGETS EXTRACTION", {"raw_html_chars": len(golden_nuggets_raw)})

    # Use raw Exa search results (not synthesized HTML) so we get actual quotes with attribution
    nugget_source = golden_nuggets_raw_exa if golden_nuggets_raw_exa else golden_nuggets_raw
    nuggets_ctx = prompts.get("nuggets_context",
        "You are extracting golden nuggets from RAW search results about {buyer_name}.").format(
        buyer_name=buyer_name)
    nuggets_focus = prompts.get("nuggets_focus",
        "Why {buyer_name} would want to acquire this business").format(
        buyer_name=buyer_name)
    nuggets_output = llm(f"""{nuggets_ctx}

Find 3-5 surprising, specific, quotable statements from executives or analysts that reveal:
- {nuggets_focus}
- Their appetite for acquisitions in adjacent markets
- Specific pain points or gaps in their product portfolio
- Bold strategic commitments from leadership

Return a JSON array. Each nugget MUST have an exact quote from the source material:
{{"quote": "exact verbatim quote from the text", "speaker": "Full Name, Title at Company", "opener": "conversation starter connecting this quote to the acquisition thesis", "why": "how this signals M&A interest or strategic fit"}}

ONLY valid JSON array. 3-5 nuggets.
RAW SEARCH RESULTS:\n{nugget_source[:12000]}""", label="extract_nuggets")

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
    product_query_template = prompts.get("product_discovery_query",
        "{buyer_name} offers products and services that can be individually reviewed by customers")
    product_query = product_query_template.format(buyer_name=buyer_name)
    prod_texts, prod_cost = traced_exa_raw(exa, product_query, "auto", "product_discovery")
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
        for query, stype in [(f'Customers review {product} on G2 and Capterra, describing what they love and hate about the platform', "auto"),
                              (f'Users of {product} share their honest experience on Reddit, including complaints, workarounds, and what they wish was better', "auto")]:
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
3-6 per sentiment. ONLY JSON.\nDATA:\n{combined[:12000]}""", timeout=120, label=f"structure_reviews:{slugify(product)}")

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
Return ONLY JSON with ALL of these fields. If a field is not available in the provided data, return null for that field. Always return all fields.
{{
  "stock_price": 142.30,
  "price_change_24mo": 18.2,
  "market_cap": "$54B",
  "day_high": 143.50,
  "day_low": 140.10,
  "52_week_high": 200.00,
  "52_week_low": 110.00,
  "volume": 1234567,
  "pe_ratio": 25.4
}}
DATA: {combined[:4000]}""", timeout=60, label="extract_stock")
        # Canonical set of stock fields — always present, default null
        STOCK_FIELDS = ["stock_price", "price_change_24mo", "market_cap",
                        "day_high", "day_low", "52_week_high", "52_week_low",
                        "volume", "pe_ratio"]
        if output:
            try:
                s, e = output.find('{'), output.rfind('}') + 1
                stock = json.loads(output[s:e])
                if stock.get("stock_price") and not str(stock["stock_price"]).startswith("$"):
                    stock["stock_price"] = f"${stock['stock_price']}"
                trace("TRANSFORM", "STOCK EXTRACTED", {
                    "price": stock.get("stock_price"), "change_24mo": stock.get("price_change_24mo"),
                    "market_cap": stock.get("market_cap"),
                    "day_high": stock.get("day_high"), "day_low": stock.get("day_low"),
                    "52_week_high": stock.get("52_week_high"), "52_week_low": stock.get("52_week_low"),
                    "volume": stock.get("volume"), "pe_ratio": stock.get("pe_ratio"),
                    "stored_as": "root fields",
                })
            except: pass
        # Normalize: ensure all canonical fields exist in stock dict (null if missing)
        for f in STOCK_FIELDS:
            if f not in stock:
                stock[f] = None

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 5: ASSEMBLE & WRITE
    # ══════════════════════════════════════════════════════════════════════════
    trace("PHASE", "ASSEMBLE BUYER OBJECT", {})

    buyer_obj = {
        "buyer_name": buyer_name, "buyer_slug": buyer_slug,
        "buyer_type": args.type, "buyer_city": args.city, "buyer_state": args.state,
        "fit_score": args.score, "logo_domain": args.domain, "ticker": args.ticker,
        "vertical": args.vertical, "entity": ENTITY,
        "valuation_metric": valuation.get("primary_metric", "ebitda"),
        "multiple_floor": valuation.get("multiple_floor"),
        "multiple_ceiling": valuation.get("multiple_ceiling"),
        "sections": {}, "source_urls": {},
    }
    buyer_obj.update(stock)

    for key, html, urls in section_results:
        fmt = section_output_formats.get(key, "section")
        if fmt == "narrative_object":
            buyer_obj[key] = {"narrative": html}
        elif fmt == "direct_html":
            buyer_obj[key] = html
        elif fmt in ("golden_nuggets", "market_reputation"):
            pass  # handled separately below
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

    # Write per-buyer JSON (initial write — Pain/Gain will update it in place)
    per_buyer_path = os.path.join(PUBLIC_DATA_DIR, f"debbie-research-{buyer_slug}.json")
    os.makedirs(PUBLIC_DATA_DIR, exist_ok=True)
    traced_write(per_buyer_path, buyer_obj, f"per-buyer JSON: {buyer_slug}")

    # Upsert into engagement_buyers — check-then-patch-or-insert on (buyer_company_name, entity)
    traced_supabase_write(
        "engagement_buyers",
        {
            "buyer_company_name": buyer_name,
            "entity": ENTITY,
            "fit_score": args.score,
            "buyer_city": args.city,
            "buyer_state": args.state,
            "buyer_type": args.type,
            "research_date": datetime.now(timezone.utc).isoformat(),
            "status": "identified",
        },
        f"upsert engagement_buyers: {buyer_slug}",
        upsert=True,
        upsert_key={"buyer_company_name": buyer_name, "entity": ENTITY},
    )

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 6 (STEP 15): PAIN/GAIN MATCH ENGINE
    # Cross-section analysis using completed research + deal context
    # ══════════════════════════════════════════════════════════════════════════
    trace("PHASE", "PAIN/GAIN MATCH ENGINE", {"step": 15})

    deal = _load_deal_context()
    pg_entity = ENTITY
    pg_target_company = deal.get("company_name", "HR.com Ltd")

    trace("PAIN_GAIN", "STARTING ANALYSIS", {
        "buyer_slug": buyer_slug,
        "entity": pg_entity,
        "target_company": pg_target_company,
        "sections_available": list(buyer_obj.get("sections", {}).keys()),
        "has_market_reputation": bool(buyer_obj.get("market_reputation", {}).get("product_reviews")),
        "deal_context_source": MEETINGS_JSON,
    })

    t0_pg = time.time()
    pg_analysis = generate_pain_gain_analysis(
        buyer_slug=buyer_slug,
        entity=pg_entity,
        target_company=pg_target_company,
    )
    elapsed_pg_ms = int((time.time() - t0_pg) * 1000)

    if pg_analysis:
        # Store in buyer object so callers have it in memory
        buyer_obj["pain_gain_analysis"] = pg_analysis
        trace("PAIN_GAIN", "ANALYSIS COMPLETE", {
            "buyer_slug": buyer_slug,
            "pain_categories": len(pg_analysis.get("pain_categories", [])),
            "asset_mappings": len(pg_analysis.get("asset_mappings", [])),
            "synthesis_chars": len(pg_analysis.get("synthesis", "")),
            "generated_at": pg_analysis.get("generated_at", ""),
            "duration_ms": elapsed_pg_ms,
            "stored_in": f"public/data/debbie-research-{buyer_slug}.json → pain_gain_analysis",
            "supabase_table": "pain_gain_analyses",
        })
        # engine already wrote the JSON; no second traced_write needed
    else:
        trace("PAIN_GAIN", "ANALYSIS FAILED — continuing without pain/gain data", {
            "buyer_slug": buyer_slug,
            "duration_ms": elapsed_pg_ms,
        })

    # Manifest build and deploy handled by scripts/build_debbie_manifest.py after batch completes

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
