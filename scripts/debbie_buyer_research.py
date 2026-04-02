#!/usr/bin/env python3
"""
Debbie Buyer Research Pipeline
==============================
Enriches HR.com buyer data for the Debbie Review page:
1. Company profile (employees, domain, industry, HR products, HR revenue %)
2. Per-product review scraping (Reddit, G2, Trustpilot, Capterra)
3. LLM-scored review quality filter (informativeness, specificity, polarity)
4. LLM-generated narratives (media business, domain name)
5. Existing dossier extraction (golden nuggets, CEO vision, etc.)

Output: public/data/debbie-buyer-research.json

Usage:
    python3 scripts/debbie_buyer_research.py                  # all 10 buyers
    python3 scripts/debbie_buyer_research.py --buyer Paychex   # single buyer
    python3 scripts/debbie_buyer_research.py --skip-reviews    # skip expensive review scrape
    python3 scripts/debbie_buyer_research.py --dry-run         # show what would run
"""

import json
import os
import re
import sys
import time
import subprocess
import datetime
import argparse
from pathlib import Path

# Add backend/lib to path for ExaClient
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend', 'lib'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend', 'scripts'))

# Credentials: all keys come from env vars. See .env.example for names, ~/.zshrc for values.
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = "deepseek/deepseek-chat"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BUYER_LIST = PROJECT_ROOT / "backend" / "data" / "buyer-lists" / "hrcom_buyers.json"
OUTPUT_DIR = PROJECT_ROOT / "public" / "data"
OUTPUT_FILE = OUTPUT_DIR / "debbie-buyer-research.json"
PUBLIC_DIR = PROJECT_ROOT / "public"
LOG_FILE = PROJECT_ROOT / "logs" / "debbie_research.log"

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(LOG_FILE.parent, exist_ok=True)


# ── Logging ────────────────────────────────────────────
def log(msg):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def slugify(s):
    if not s:
        return "unknown"
    s = s.lower().strip()
    s = s.replace("&", "and").replace("/", "-")
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-')[:60]


# ── LLM Calls ─────────────────────────────────────────
def call_claude_cli(prompt, timeout=120):
    try:
        result = subprocess.run(
            ["claude", "-p", "--output-format", "text"],
            input=prompt, capture_output=True, text=True, timeout=timeout
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        log(f"  Claude CLI failed (rc={result.returncode})")
        return None
    except Exception as e:
        log(f"  Claude CLI error: {e}")
        return None


def call_openrouter(prompt):
    import requests
    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
            json={"model": OPENROUTER_MODEL, "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.3, "max_tokens": 3000},
            timeout=90
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log(f"  OpenRouter fallback failed: {e}")
        return None


def call_llm(prompt, timeout=120):
    result = call_claude_cli(prompt, timeout)
    if not result:
        log("  Falling back to OpenRouter...")
        result = call_openrouter(prompt)
    return result or ""


def extract_json(text):
    if not text:
        return None
    # Try to find JSON array or object
    for pattern in [r'\[[\s\S]*\]', r'\{[\s\S]*\}']:
        match = re.search(pattern, text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                continue
    return None


# ── Exa Client ─────────────────────────────────────────
def get_exa_client():
    from exa_client_v2 import ExaClient
    return ExaClient()


# ── PE Firm Portfolio Mapping ──────────────────────────
PE_PORTFOLIO = {
    "Thoma Bravo": {"portfolio": "Dayforce", "products_hint": "Dayforce HCM, Dayforce Payroll, Dayforce Workforce Management, Powerpay"},
    "HG Capital": {"portfolio": "P&I Personal & Informatik", "products_hint": "P&I LogaHR, P&I LOGA3, P&I Time Management"},
    "Drake Star Partners (Advisory Lead)": {"portfolio": None, "products_hint": None},  # M&A advisory, skip reviews
}

REVIEW_SOURCES = {
    "reddit": {
        "domains": ["reddit.com"],
        "query_template": '"{product_name}" review OR complaint OR love OR terrible OR amazing',
        "num_results": 10,
    },
    "g2": {
        "domains": ["g2.com"],
        "query_template": '"{product_name}" reviews pros cons',
        "num_results": 10,
    },
    "trustpilot": {
        "domains": ["trustpilot.com"],
        "query_template": '"{product_name}" OR "{buyer_name}" review',
        "num_results": 8,
    },
    "capterra": {
        "domains": ["capterra.com"],
        "query_template": '"{product_name}" reviews pros cons alternatives',
        "num_results": 10,
    },
}


# ══════════════════════════════════════════════════════
# PHASE 1: Company Profile
# ══════════════════════════════════════════════════════
def fetch_company_profile(buyer, exa):
    """Fetch employees, domain, industry, HR products, HR revenue % via Exa."""
    name = buyer["buyer_name"]
    log(f"  [Profile] {name}")

    # Query 1: Company overview
    try:
        overview = exa.raw_search(
            query=f"{name} company profile employees revenue domain industry HR products overview",
            search_type="deep", num_results=8, content_mode="text", max_characters=5000,
            include_domains=["crunchbase.com", "zoominfo.com", "linkedin.com",
                             "finance.yahoo.com", "sec.gov", "macrotrends.net"]
        )
        overview_text = "\n".join(r.get("text", "") for r in overview.get("results", []))
        overview_urls = [r.get("url", "") for r in overview.get("results", []) if r.get("url")]
    except Exception as e:
        log(f"    Overview query failed: {e}")
        overview_text = ""
        overview_urls = []
    time.sleep(0.5)

    # Query 2: HR revenue percentage
    try:
        hr_rev = exa.raw_search(
            query=f"{name} HR human resources revenue segment breakdown percentage annual report 10-K",
            search_type="deep", num_results=5, content_mode="text", max_characters=5000,
            include_domains=["sec.gov", "seekingalpha.com", "macrotrends.net",
                             "bloomberg.com", "investor.paychex.com", "investor.workday.com"]
        )
        hr_rev_text = "\n".join(r.get("text", "") for r in hr_rev.get("results", []))
    except Exception as e:
        log(f"    HR revenue query failed: {e}")
        hr_rev_text = ""
    time.sleep(0.5)

    # LLM extraction
    prompt = f"""From these search results about {name}, extract these fields as JSON:
{{
  "employees": "number or estimate with source qualifier",
  "domain": "primary website domain",
  "industry": "specific industry segment (not just 'technology')",
  "hr_products": "comma-separated list of their HR products/platforms/modules",
  "hr_revenue_pct": "percentage of revenue from HR (with qualifier like ~, est., per 10-K)"
}}

If a field is not available, use "N/A (private)" for private companies or "N/A" otherwise.

Search results:
{overview_text[:6000]}

HR Revenue data:
{hr_rev_text[:4000]}

Return ONLY the JSON object."""

    raw = call_llm(prompt)
    profile = extract_json(raw)
    if not profile:
        profile = {"employees": "N/A", "domain": "N/A", "industry": "N/A",
                   "hr_products": "N/A", "hr_revenue_pct": "N/A"}
    profile["sources"] = overview_urls[:5]
    log(f"    Got: {profile.get('employees', '?')} emp, {profile.get('hr_revenue_pct', '?')} HR rev")
    return profile


# ══════════════════════════════════════════════════════
# PHASE 2: Product Discovery
# ══════════════════════════════════════════════════════
def discover_products(buyer_name, profile, exa):
    """Discover all HR products offered by this buyer."""
    log(f"  [Products] Discovering products for {buyer_name}")

    # Check PE portfolio mapping first
    if buyer_name in PE_PORTFOLIO:
        pe = PE_PORTFOLIO[buyer_name]
        if pe["portfolio"] is None:
            log(f"    M&A advisory firm — no products to review")
            return []
        log(f"    PE firm — searching portfolio company: {pe['portfolio']}")
        buyer_name = pe["portfolio"]
        if pe["products_hint"]:
            return [p.strip() for p in pe["products_hint"].split(",")]

    # Try to get products from profile first
    known_products = profile.get("hr_products", "")
    if known_products and known_products != "N/A":
        products = [p.strip() for p in known_products.split(",") if p.strip()]
        if len(products) >= 2:
            log(f"    Found {len(products)} from profile: {products}")
            return products[:8]

    # Exa product catalog query
    domain = profile.get("domain", "")
    try:
        result = exa.raw_search(
            query=f"{buyer_name} HR products suite platform list features pricing",
            search_type="deep", num_results=10, content_mode="text", max_characters=8000,
            include_domains=["g2.com", "capterra.com", "getapp.com", "trustradius.com",
                             domain] if domain and domain != "N/A" else
                            ["g2.com", "capterra.com", "getapp.com", "trustradius.com"]
        )
        catalog_text = "\n".join(r.get("text", "") for r in result.get("results", []))
    except Exception as e:
        log(f"    Product discovery query failed: {e}")
        catalog_text = ""
    time.sleep(0.5)

    prompt = f"""From these search results about {buyer_name}, extract EVERY distinct HR product,
platform, module, or service they offer. Return as a JSON array of strings.

Example for Workday: ["Workday HCM", "Workday Payroll", "Workday Recruiting", "Workday Learning"]
Example for Paychex: ["Paychex Flex", "Paychex Oasis PEO", "SurePayroll", "Paychex 401(k)"]

Search results:
{catalog_text[:8000]}

Return ONLY the JSON array. No explanation. If you find nothing, return ["(unknown)"]."""

    raw = call_llm(prompt)
    products = extract_json(raw)
    if not products or not isinstance(products, list):
        products = [buyer_name + " HR"]
    products = [p for p in products if p and p != "(unknown)"][:8]
    log(f"    Found {len(products)} products: {products}")
    return products


# ══════════════════════════════════════════════════════
# PHASE 3: Per-Product Review Scraping
# ══════════════════════════════════════════════════════
def scrape_product_reviews(buyer_name, product, exa):
    """Scrape reviews for a single product across 4 sources."""
    raw_reviews = []
    for source_name, config in REVIEW_SOURCES.items():
        query = config["query_template"].format(product_name=product, buyer_name=buyer_name)
        try:
            results = exa.raw_search(
                query=query, search_type="auto",
                num_results=config["num_results"],
                content_mode="text", max_characters=4000,
                include_domains=config["domains"]
            )
            for r in results.get("results", []):
                text = r.get("text", "").strip()
                if len(text) < 30:
                    continue
                raw_reviews.append({
                    "text": text[:1500],
                    "url": r.get("url", ""),
                    "source": source_name,
                    "title": r.get("title", ""),
                })
        except Exception as e:
            log(f"      {source_name} failed for {product}: {e}")
        time.sleep(0.3)

    return raw_reviews


def score_reviews(raw_reviews, product_name, buyer_name):
    """LLM-score reviews for informativeness, specificity, and polarity."""
    if not raw_reviews:
        return []

    # Batch score up to 15 reviews at once to save LLM calls
    batch_size = 15
    scored = []

    for i in range(0, len(raw_reviews), batch_size):
        batch = raw_reviews[i:i + batch_size]
        reviews_text = "\n---\n".join(
            f"REVIEW {j+1} (source: {r['source']}):\n{r['text'][:500]}"
            for j, r in enumerate(batch)
        )

        prompt = f"""Score each review snippet about "{product_name}" ({buyer_name}).
Return a JSON array with one object per review, in order:

[
  {{
    "index": 1,
    "informativeness": 8,
    "specificity": 7,
    "polarity": 9,
    "verdict": "positive",
    "category": "efficiency"
  }}
]

SCORING:
- informativeness (1-10): teaches something concrete? Names specific workflow, data loss, measurable outcome = high
- specificity (1-10): references exact features, screens, scenarios? Not generic "it's good/bad"
- polarity (1-10): how strong is the opinion? Extreme outcomes = 10, mild = 4, neutral = 1
- verdict: "positive" or "negative" or "neutral"
- category: one of: outcomes, capabilities, efficiency, data_integrity, workflow, ux, support, reliability, compliance, integration

LOOK FOR reviews about:
- Outcomes: ROI, cost savings, revenue impact, measurable results
- Capabilities: what it can/can't do, feature gaps, integrations
- Efficiency: time savings, automation, workflow speed
- Data integrity: data loss, sync failures, migration problems, accuracy
- Workflow: process design, approval chains, ease of setup
- UX: interface design, navigation, mobile experience, learning curve
- Support: customer service, implementation help, responsiveness
- Reliability: uptime, bugs, crashes, performance under load
- Compliance: regulatory, audit trails, certifications
- Integration: API quality, third-party connections, data portability

Reviews:
{reviews_text}

Return ONLY the JSON array."""

        raw = call_llm(prompt, timeout=90)
        scores = extract_json(raw)
        if scores and isinstance(scores, list):
            for j, score in enumerate(scores):
                if j < len(batch):
                    review = batch[j].copy()
                    review["scores"] = {
                        "informativeness": score.get("informativeness", 0),
                        "specificity": score.get("specificity", 0),
                        "polarity": score.get("polarity", 0),
                    }
                    review["verdict"] = score.get("verdict", "neutral")
                    review["category"] = score.get("category", "capabilities")
                    review["product"] = product_name
                    scored.append(review)

    return scored


def scrape_buyer_reputation(buyer_name, profile, exa):
    """Full market reputation pipeline for one buyer."""
    log(f"  [Reputation] Starting reputation scrape for {buyer_name}")

    # Discover products
    products = discover_products(buyer_name, profile, exa)
    if not products:
        return {
            "products_discovered": [],
            "product_reviews": {},
            "summary_stats": {"total_reviews_scraped": 0, "reviews_passing_threshold": 0, "products_with_thin_data": []},
            "intelligence_summary": f"M&A advisory firm — no HR products to review."
        }

    # Determine actual search name (PE firms use portfolio company)
    search_name = buyer_name
    if buyer_name in PE_PORTFOLIO and PE_PORTFOLIO[buyer_name]["portfolio"]:
        search_name = PE_PORTFOLIO[buyer_name]["portfolio"]

    product_reviews = {}
    total_scraped = 0
    total_passing = 0

    for product in products:
        log(f"    Scraping: {product}")
        raw = scrape_product_reviews(search_name, product, exa)
        total_scraped += len(raw)
        log(f"      Got {len(raw)} raw reviews")

        if raw:
            scored = score_reviews(raw, product, search_name)
            passing = [r for r in scored
                       if r["scores"]["informativeness"] >= 6
                       and r["scores"]["specificity"] >= 6
                       and r["scores"]["polarity"] >= 7]
            passing.sort(key=lambda r: sum(r["scores"].values()), reverse=True)
        else:
            passing = []

        total_passing += len(passing)

        product_reviews[product] = {
            "positive": [r for r in passing if r["verdict"] == "positive"],
            "negative": [r for r in passing if r["verdict"] == "negative"],
            "total_raw": len(raw),
            "total_passing": len(passing),
        }
        log(f"      Passing threshold: {len(passing)} ({len([r for r in passing if r['verdict']=='positive'])}+, {len([r for r in passing if r['verdict']=='negative'])}−)")

    # Generate intelligence summary
    top_positives = []
    top_negatives = []
    for prod, data in product_reviews.items():
        top_positives.extend(data["positive"][:2])
        top_negatives.extend(data["negative"][:2])

    if top_positives or top_negatives:
        summary_prompt = f"""Based on these scored reviews for {buyer_name}'s products, write 2 paragraphs:

Paragraph 1 ("What the market loves"): Summarize the strongest positive themes. What do users praise most?
Paragraph 2 ("Where they're bleeding"): Summarize the most critical negative themes. What causes the most pain?

Be specific — name products, features, numbers. This is for an M&A advisor selling HR.com to this buyer.

Top positive reviews:
{json.dumps([{"product": r["product"], "text": r["text"][:300], "category": r["category"]} for r in top_positives[:6]], indent=2)}

Top negative reviews:
{json.dumps([{"product": r["product"], "text": r["text"][:300], "category": r["category"]} for r in top_negatives[:6]], indent=2)}

Write in plain text, 2 paragraphs only. No headers or bullets."""

        intelligence_summary = call_llm(summary_prompt, timeout=60) or "Review data collected — summary generation pending."
    else:
        intelligence_summary = f"Limited review data found for {buyer_name}'s HR products."

    return {
        "products_discovered": products,
        "product_reviews": product_reviews,
        "summary_stats": {
            "total_reviews_scraped": total_scraped,
            "reviews_passing_threshold": total_passing,
            "positive_count": sum(len(d["positive"]) for d in product_reviews.values()),
            "negative_count": sum(len(d["negative"]) for d in product_reviews.values()),
            "products_with_thin_data": [p for p, d in product_reviews.items() if d["total_passing"] < 3],
        },
        "intelligence_summary": intelligence_summary,
    }


# ══════════════════════════════════════════════════════
# PHASE 4: LLM Narratives (Media Business + Domain)
# ══════════════════════════════════════════════════════
def generate_narratives(buyer, profile, exa):
    """Generate media business and domain name narratives."""
    name = buyer["buyer_name"]
    log(f"  [Narratives] {name}")

    # Exa context query
    try:
        context = exa.raw_search(
            query=f"{name} content media platform acquisition HR technology strategy",
            search_type="deep", num_results=5, content_mode="text", max_characters=5000,
        )
        context_text = "\n".join(r.get("text", "") for r in context.get("results", []))
        context_urls = [r.get("url", "") for r in context.get("results", []) if r.get("url")]
    except Exception as e:
        log(f"    Context query failed: {e}")
        context_text = ""
        context_urls = []
    time.sleep(0.5)

    employees = profile.get("employees", "N/A")
    industry = profile.get("industry", "N/A")

    # Media business narrative
    media_prompt = f"""Write 2-3 paragraphs explaining how {name} ({buyer["buyer_type"]}, ~{employees} employees, {industry})
would benefit from owning HR.com's media business.

HR.com facts: 2M+ HR professional members, 5,000+ annual webcasts, 200+ annual virtual events,
30+ research institutes, HR certification programs, $42M revenue, 25-year track record,
the domain hr.com ranked #87 globally.

Research context:
{context_text[:4000]}

Write as a strategic M&A advisor. Be specific about synergies. No headers or bullets — just paragraphs.
Format as HTML <p> tags."""

    media_narrative = call_llm(media_prompt, timeout=90) or f"<p>Narrative pending for {name}.</p>"

    # Domain name narrative
    domain_prompt = f"""Write 2-3 paragraphs explaining how {name} would benefit from owning the domain name hr.com,
which is ranked #87 globally for traffic. This is one of only 676 two-letter .com domains in existence.

Key question: What could they do to increase value for their company by owning that traffic
if the media business was sold separately?

Consider: SEO authority, brand equity, direct-to-HR-buyer lead capture, content hub potential,
affiliate/advertising revenue, competitive positioning vs. other HR tech vendors.

Write as a strategic M&A advisor. No headers or bullets — just paragraphs.
Format as HTML <p> tags."""

    domain_narrative = call_llm(domain_prompt, timeout=90) or f"<p>Narrative pending for {name}.</p>"

    return {
        "hr_media_business": {"narrative": media_narrative, "sources": context_urls[:3]},
        "hr_domain_name": {"narrative": domain_narrative, "sources": context_urls[:3]},
    }


# ══════════════════════════════════════════════════════
# PHASE 5: Existing Dossier Extraction
# ══════════════════════════════════════════════════════
def extract_dossier_data(buyer_name):
    """Extract golden nuggets and sections from existing dossier HTML."""
    slug = f"hr-com-ltd_{slugify(buyer_name)}"
    html_path = PUBLIC_DIR / f"{slug}.html"

    result = {"golden_nuggets": [], "sections": {}}

    if not html_path.exists():
        log(f"  [Dossier] No dossier file: {slug}.html")
        return result

    log(f"  [Dossier] Extracting from {slug}.html")
    html = html_path.read_text(encoding="utf-8")

    # Extract golden nuggets
    nugget_pattern = re.compile(
        r'<div class="nugget-card">(.*?)</div>\s*(?=<div class="nugget-card">|</div>\s*</div>)',
        re.DOTALL
    )
    for match in nugget_pattern.finditer(html):
        block = match.group(1)
        header_m = re.search(r'class="nugget-header">(.*?)</div>', block)
        quote_m = re.search(r'class="ceo-quote"[^>]*>(.*?)</div>', block, re.DOTALL)
        opener_m = re.search(r'class="nugget-opener"[^>]*>.*?<p>(.*?)</p>', block, re.DOTALL)
        why_m = re.search(r'class="nugget-why"[^>]*>(.*?)</div>', block, re.DOTALL)

        nugget = {
            "speaker": re.sub(r'Nugget \d+ [-\u2014] ', '', header_m.group(1).strip()) if header_m else "",
            "quote": re.sub(r'<[^>]+>', '', quote_m.group(1).strip()) if quote_m else "",
            "opener": re.sub(r'<[^>]+>', '', opener_m.group(1).strip()) if opener_m else "",
            "why": re.sub(r'<[^>]+>', '', why_m.group(1).strip()) if why_m else "",
        }
        if nugget["quote"] or nugget["opener"]:
            result["golden_nuggets"].append(nugget)

    # Extract named sections by card id
    section_ids = ["strategic-fit", "ceo-vision", "ma-appetite", "competitive-moat",
                   "earnings-quotes", "approach", "challenges", "business-model"]
    for sid in section_ids:
        pattern = re.compile(rf'<div class="card" id="{sid}">(.*?)</div>\s*(?=<div class="card"|<!-- )', re.DOTALL)
        m = pattern.search(html)
        if m:
            content = m.group(1)
            # Strip to just the narrative content
            content = re.sub(r'<h2[^>]*>.*?</h2>', '', content).strip()
            content = content.strip()
            if len(content) > 50:
                key = sid.replace("-", "_")
                result["sections"][key] = content

    log(f"    Found {len(result['golden_nuggets'])} nuggets, {len(result['sections'])} sections")
    return result


# ══════════════════════════════════════════════════════
# MAIN PIPELINE
# ══════════════════════════════════════════════════════
def process_buyer(buyer, exa, skip_reviews=False):
    """Full pipeline for a single buyer."""
    name = buyer["buyer_name"]
    slug = slugify(name)
    log(f"\n{'='*60}")
    log(f"Processing: {name} (slug: {slug}, score: {buyer['fit_score']})")
    log(f"{'='*60}")

    # Phase 1: Company Profile
    profile = fetch_company_profile(buyer, exa)

    # Phase 2+3: Product Discovery + Review Scraping
    if skip_reviews:
        reputation = {"products_discovered": [], "product_reviews": {},
                      "summary_stats": {"total_reviews_scraped": 0, "reviews_passing_threshold": 0},
                      "intelligence_summary": "Review scraping skipped."}
    else:
        reputation = scrape_buyer_reputation(name, profile, exa)

    # Phase 4: Narratives
    narratives = generate_narratives(buyer, profile, exa)

    # Phase 5: Existing Dossier
    dossier = extract_dossier_data(name)

    return {
        "buyer_name": name,
        "buyer_slug": slug,
        "buyer_type": buyer["buyer_type"],
        "city": buyer["city"],
        "state": buyer["state"],
        "fit_score": buyer["fit_score"],
        "contact_name": buyer["contact_name"],
        "contact_title": buyer["contact_title"],
        "thesis": buyer["thesis"],
        "source": buyer.get("source", ""),
        "header": profile,
        "market_reputation": reputation,
        "hr_media_business": narratives["hr_media_business"],
        "hr_domain_name": narratives["hr_domain_name"],
        "strategic_fit": buyer["thesis"],
        "golden_nuggets": dossier["golden_nuggets"],
        "sections": dossier["sections"],
    }


def main():
    parser = argparse.ArgumentParser(description="Debbie Buyer Research Pipeline")
    parser.add_argument("--buyer", type=str, help="Process a single buyer by name")
    parser.add_argument("--skip-reviews", action="store_true", help="Skip review scraping")
    parser.add_argument("--dry-run", action="store_true", help="Show what would run")
    args = parser.parse_args()

    log(f"\n{'#'*60}")
    log(f"# Debbie Buyer Research Pipeline — {datetime.datetime.now().isoformat()}")
    log(f"{'#'*60}")

    # Load buyers
    with open(BUYER_LIST) as f:
        data = json.load(f)
    buyers = data["buyers"]

    if args.buyer:
        buyers = [b for b in buyers if args.buyer.lower() in b["buyer_name"].lower()]
        if not buyers:
            log(f"No buyer matching '{args.buyer}'")
            return

    log(f"Processing {len(buyers)} buyers")

    if args.dry_run:
        for b in buyers:
            log(f"  Would process: {b['buyer_name']} (score: {b['fit_score']})")
        return

    exa = get_exa_client()

    # Load existing output if it exists (for incremental updates)
    existing = {}
    if OUTPUT_FILE.exists():
        try:
            existing = json.loads(OUTPUT_FILE.read_text())
            log(f"Loaded existing output with {len(existing.get('buyers', {}))} buyers")
        except Exception:
            existing = {}

    all_buyers = existing.get("buyers", {})

    for buyer in buyers:
        try:
            result = process_buyer(buyer, exa, skip_reviews=args.skip_reviews)
            all_buyers[result["buyer_slug"]] = result
        except Exception as e:
            log(f"  FATAL ERROR processing {buyer['buyer_name']}: {e}")
            import traceback
            traceback.print_exc()

    # Write output
    output = {
        "generated_at": datetime.datetime.now().isoformat(),
        "company": "HR.com Ltd",
        "total_buyers": len(all_buyers),
        "buyers": all_buyers,
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    log(f"\nOutput written to {OUTPUT_FILE}")
    log(f"Total buyers: {len(all_buyers)}")

    # Summary
    for slug, b in all_buyers.items():
        rep = b.get("market_reputation", {})
        stats = rep.get("summary_stats", {})
        log(f"  {b['buyer_name']}: {len(b.get('golden_nuggets', []))} nuggets, "
            f"{stats.get('total_reviews_scraped', 0)} reviews scraped, "
            f"{stats.get('reviews_passing_threshold', 0)} passing")


if __name__ == "__main__":
    main()
