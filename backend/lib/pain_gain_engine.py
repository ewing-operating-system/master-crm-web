#!/usr/bin/env python3
"""
Pain/Gain Analysis Engine
=========================
Cross-section, evidence-backed Pain/Gain analysis for buyer review pages.

Given a buyer slug + entity + target_company:
  1. Load the per-buyer JSON (public/data/debbie-research-{slug}.json)
  2. Extract pain signals from 6 sections (reviews + 5 narrative sections)
  3. Load entity_value_propositions from Supabase
  4. Call LLM with structured prompt (enforced JSON schema)
  5. Write to pain_gain_analyses table (upsert)
  6. Update per-buyer JSON with pain_gain_analysis key

Usage (standalone test):
    python3 backend/lib/pain_gain_engine.py \
        --buyer sap-successfactors \
        --entity next_chapter \
        --target "HR.com Ltd"
"""

import json
import os
import re
import sys
import subprocess
import datetime
import argparse
import urllib.request
import ssl
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
LIB_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = LIB_DIR.parent.parent
DATA_DIR = PROJECT_ROOT / "public" / "data"

sys.path.insert(0, str(LIB_DIR))
import supabase as db

# ── Credentials ───────────────────────────────────────────────────────────────
# All keys come from env vars (sourced from ~/.zshrc). Never hardcode.
def _ensure_env():
    """Load Supabase/API credentials if missing from env.

    Strategy:
    1. Parse ~/.zshrc directly for export lines (fast, no subprocess errors)
    2. Fall back to subprocess `source ~/.zshrc; env` if direct parse misses anything
    """
    needed = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
              "SUPABASE_ANON_KEY", "OPENROUTER_API_KEY")
    if all(os.environ.get(k) for k in needed):
        return

    # Strategy 1: parse ~/.zshrc directly
    zshrc = os.path.expanduser("~/.zshrc")
    if os.path.exists(zshrc):
        try:
            import re as _re
            with open(zshrc) as f:
                content = f.read()
            # Match: export KEY="value" or export KEY='value'
            for m in _re.finditer(r'export\s+(\w+)=["\'](.*?)["\']', content):
                k, v = m.group(1), m.group(2)
                if k in needed or k in ("DATABASE_URL", "OPENAI_API_KEY"):
                    os.environ.setdefault(k, v)
        except Exception:
            pass

    if all(os.environ.get(k) for k in needed):
        return

    # Strategy 2: subprocess (semicolon so env runs even if source has errors)
    try:
        result = subprocess.run(
            ["/bin/zsh", "-c", "source ~/.zshrc 2>/dev/null; env"],
            capture_output=True, text=True, timeout=15
        )
        for line in result.stdout.splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                if k in needed or k in ("DATABASE_URL", "OPENAI_API_KEY"):
                    os.environ.setdefault(k, v)
    except Exception:
        pass

_ensure_env()

# Patch supabase module in case env vars were missing at import time
db.URL = os.environ.get("SUPABASE_URL", db.URL)
db.KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", db.KEY)

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = "deepseek/deepseek-chat"

# ── Category constants (shared with debbie_buyer_research.py) ─────────────────
CANONICAL_CATEGORIES = {
    "outcomes", "capabilities", "efficiency", "data_integrity",
    "workflow", "ux", "support", "reliability", "compliance", "integration",
}

CATEGORY_ALIASES = {
    "usability": "ux", "navigation": "ux", "interface": "ux", "ui": "ux",
    "design": "ux", "accessibility": "ux",
    "features": "capabilities", "reporting": "capabilities",
    "analytics": "capabilities", "functionality": "capabilities",
    "customization": "capabilities", "flexibility": "capabilities",
    "pricing": "outcomes", "billing": "outcomes", "cost": "outcomes",
    "value": "outcomes", "roi": "outcomes",
    "onboarding": "workflow", "setup": "workflow",
    "implementation": "workflow", "configuration": "workflow",
    "deployment": "workflow", "adoption": "workflow",
    "bugs": "reliability", "crashes": "reliability",
    "performance": "reliability", "stability": "reliability",
    "downtime": "reliability", "errors": "reliability",
    "automation": "efficiency", "speed": "efficiency",
    "productivity": "efficiency",
    "api": "integration", "connectivity": "integration",
    "interoperability": "integration", "compatibility": "integration",
    "data quality": "data_integrity", "accuracy": "data_integrity",
    "sync": "data_integrity", "migration": "data_integrity",
    "security": "compliance", "gdpr": "compliance",
    "audit": "compliance", "regulations": "compliance",
}


def _normalize_category(raw: str) -> str:
    if not raw:
        return "capabilities"
    normalized = raw.strip().lower().replace(" ", "_")
    if normalized in CANONICAL_CATEGORIES:
        return normalized
    alias_key = normalized.replace("_", " ")
    if alias_key in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[alias_key]
    if normalized in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[normalized]
    for canon in CANONICAL_CATEGORIES:
        if canon in normalized:
            return canon
    return "capabilities"


# ── LLM helpers ───────────────────────────────────────────────────────────────
def _call_claude_cli(prompt: str, timeout: int = 240) -> str | None:
    try:
        env = os.environ.copy()
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + env.get("PATH", "")
        result = subprocess.run(
            ["claude", "-p", "--output-format", "text"],
            input=prompt, capture_output=True, text=True,
            timeout=timeout, env=env
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _call_openrouter(prompt: str) -> str | None:
    if not OPENROUTER_KEY:
        return None
    try:
        ctx = ssl.create_default_context()
        payload = json.dumps({
            "model": OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 4000,
        }).encode()
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, context=ctx, timeout=120) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  [pain_gain] OpenRouter error: {e}")
    return None


def _call_llm(prompt: str, timeout: int = 240) -> str:
    result = _call_claude_cli(prompt, timeout)
    if not result:
        print("  [pain_gain] Claude CLI unavailable, trying OpenRouter...")
        result = _call_openrouter(prompt)
    return result or ""


def _extract_json(text: str):
    if not text:
        return None
    for pattern in [r'\{[\s\S]*\}', r'\[[\s\S]*\]']:
        match = re.search(pattern, text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                continue
    return None


# ── Text cleanup ──────────────────────────────────────────────────────────────
def _clean_section_text(raw: str, max_chars: int = 700) -> str:
    """Strip ```html fences, HTML tags, and truncate to max_chars."""
    if not raw:
        return ""
    # Remove ```html ... ``` fences
    text = re.sub(r'```(?:html)?\s*', '', raw)
    text = re.sub(r'\s*```', '', text)
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    # Truncate with ellipsis
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(' ', 1)[0] + "…"
    return text


# ── Signal extraction ─────────────────────────────────────────────────────────
def _extract_review_pain_signals(buyer_data: dict) -> dict:
    """
    Aggregate negative reviews from market_reputation.product_reviews.
    Returns: {category: {"count": N, "product_sources": [...], "quotes": [...]}}
    Only includes categories with at least 1 quote.
    """
    signals: dict[str, dict] = {}
    market_rep = buyer_data.get("market_reputation", {})
    product_reviews = market_rep.get("product_reviews", {})

    for product_name, review_data in product_reviews.items():
        negatives = review_data.get("negative", [])
        for rev in negatives:
            text = rev.get("text", "").strip()
            if not text:
                continue
            raw_cat = rev.get("category", "capabilities")
            cat = _normalize_category(raw_cat)
            if cat not in signals:
                signals[cat] = {"count": 0, "product_sources": [], "quotes": []}
            signals[cat]["count"] += 1
            if product_name not in signals[cat]["product_sources"]:
                signals[cat]["product_sources"].append(product_name)
            # Keep up to 3 quotes per category
            if len(signals[cat]["quotes"]) < 3:
                signals[cat]["quotes"].append(text[:200])

    return signals


def _extract_section_signals(buyer_data: dict) -> dict[str, str]:
    """
    Extract cleaned text from 5 narrative sections.
    Returns: {section_key: cleaned_text}
    Only includes sections that have non-empty content.
    """
    section_keys = [
        "ceo_vision",
        "ma_appetite",
        "competitive_moat",
        "earnings_quotes",
        "recent_news",
        "strategic_fit",
    ]
    # sections can be nested under "sections" key or top-level
    sections_obj = buyer_data.get("sections", {})
    result = {}

    for key in section_keys:
        raw = sections_obj.get(key) or buyer_data.get(key, "")
        cleaned = _clean_section_text(raw, max_chars=700)
        if cleaned and len(cleaned) > 30:
            result[key] = cleaned

    return result


# ── Supabase helpers (direct REST — reads env vars at call time, not import time) ──
_ssl_ctx = ssl.create_default_context()


def _supabase_get(path: str, *, anon: bool = False) -> list:
    """GET from Supabase REST API. Returns list of rows or []."""
    base_url = os.environ.get("SUPABASE_URL", "")
    key = (
        os.environ.get("SUPABASE_ANON_KEY", "")
        if anon
        else os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    )
    if not base_url or not key:
        raise ValueError("SUPABASE_URL or key not set in environment")
    url = f"{base_url}/rest/v1/{path}"
    req = urllib.request.Request(
        url,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=20) as resp:
        return json.loads(resp.read())


def _supabase_upsert(table: str, row: dict) -> bool:
    """Upsert a row into Supabase. Returns True on success."""
    base_url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not base_url or not key:
        raise ValueError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set")
    url = f"{base_url}/rest/v1/{table}"
    payload = json.dumps(row, default=str).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, context=_ssl_ctx, timeout=20) as resp:
        resp.read()
    return True


def _load_entity_assets(entity: str, target_company: str) -> list[dict]:
    """Load value propositions from Supabase. Returns list of asset dicts."""
    import urllib.parse
    encoded_company = urllib.parse.quote(target_company)
    path = (
        f"entity_value_propositions"
        f"?entity=eq.{entity}"
        f"&target_company=eq.{encoded_company}"
        f"&order=sort_order"
    )
    try:
        rows = _supabase_get(path)
        return rows or []
    except Exception as e:
        print(f"  [pain_gain] WARNING: Could not load entity assets from Supabase: {e}")
        return []


def _write_to_supabase(
    entity: str,
    target_company: str,
    buyer_slug: str,
    buyer_name: str,
    analysis: dict,
) -> bool:
    """Upsert pain_gain_analyses row. Returns True on success."""
    row = {
        "entity": entity,
        "target_company": target_company,
        "buyer_slug": buyer_slug,
        "buyer_name": buyer_name,
        "pain_categories": analysis.get("pain_categories", []),
        "asset_mappings": analysis.get("asset_mappings", []),
        "synthesis": analysis.get("synthesis", ""),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }
    try:
        _supabase_upsert("pain_gain_analyses", row)
        print(f"  [pain_gain] Supabase upsert OK for {buyer_slug}")
        return True
    except Exception as e:
        print(f"  [pain_gain] Supabase upsert failed: {e}")
        return False


# ── JSON file helpers ─────────────────────────────────────────────────────────
def _load_buyer_json(buyer_slug: str) -> dict | None:
    path = DATA_DIR / f"debbie-research-{buyer_slug}.json"
    if not path.exists():
        print(f"  [pain_gain] Buyer JSON not found: {path}")
        return None
    with open(path, "r") as f:
        return json.load(f)


def _save_buyer_json(buyer_slug: str, data: dict) -> bool:
    path = DATA_DIR / f"debbie-research-{buyer_slug}.json"
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"  [pain_gain] Buyer JSON updated: {path.name}")
        return True
    except Exception as e:
        print(f"  [pain_gain] Failed to save buyer JSON: {e}")
        return False


# ── Prompt builder ────────────────────────────────────────────────────────────
def _build_prompt(
    buyer_name: str,
    assets: list[dict],
    review_signals: dict,
    section_signals: dict[str, str],
) -> str:
    # Format assets block
    if assets:
        assets_block = "\n".join(
            f"- {a['asset_key'].upper()}: {a.get('asset_label','')} ({a.get('asset_subtitle','')})\n"
            f"  {a.get('asset_description','')}"
            for a in assets
        )
    else:
        assets_block = "(No assets configured — generic analysis only)"

    # Format review pain signals
    if review_signals:
        rev_lines = []
        for cat, sig in sorted(review_signals.items(), key=lambda x: -x[1]["count"]):
            rev_lines.append(
                f"  [{cat.upper()}] {sig['count']} complaint(s) across: "
                f"{', '.join(sig['product_sources'][:3])}"
            )
            for q in sig["quotes"][:2]:
                rev_lines.append(f'    • "{q}"')
        review_block = "\n".join(rev_lines)
    else:
        review_block = "  No negative review data available."

    # Format section signals
    section_labels = {
        "ceo_vision":        "CEO/Executive Vision",
        "ma_appetite":       "M&A Track Record",
        "competitive_moat":  "Competitive Weaknesses",
        "earnings_quotes":   "Financial Pressures (Earnings)",
        "recent_news":       "Recent News & Announcements",
        "strategic_fit":     "Strategic Fit Analysis",
    }
    section_block_parts = []
    for key, label in section_labels.items():
        text = section_signals.get(key, "")
        if text:
            section_block_parts.append(f"{len(section_block_parts)+2}. {label}:\n{text}")
    section_block = "\n\n".join(section_block_parts) if section_block_parts else "(No section data available)"

    # Asset keys for mappings
    asset_keys = [a["asset_key"] for a in assets] if assets else ["asset_1", "asset_2"]
    asset_keys_str = " | ".join(asset_keys)

    prompt = f"""You are a senior M&A analyst producing a Pain/Gain Match analysis.

SELLER: {assets[0].get('target_company', 'Target Company') if assets else 'Target Company'}
SELLER'S ASSETS:
{assets_block}

BUYER: {buyer_name}

BUYER INTELLIGENCE (from research):

1. Product Review Pain Points (direct user complaints):
{review_block}

{section_block}

===

TASK:
For each meaningful pain category found across ALL sources above, determine how each seller asset addresses it.

Return ONLY a JSON object matching this exact schema — no markdown, no explanation:

{{
  "pain_categories": [
    {{
      "category": "one of: outcomes|capabilities|efficiency|data_integrity|workflow|ux|support|reliability|compliance|integration",
      "severity": "high|medium|low",
      "signal_count": <integer — count of distinct signals across all sources>,
      "sources": ["market_reputation", "ceo_vision", "ma_appetite", "competitive_moat", "earnings_quotes", "recent_news", "strategic_fit"],
      "evidence": "<1-2 sentences with SPECIFIC quotes or data points from the intelligence above>"
    }}
  ],
  "asset_mappings": [
    {{
      "pain_category": "<same category string as in pain_categories>",
      "asset_key": "<one of: {asset_keys_str}>",
      "strength": "strong|moderate|weak|none",
      "rationale": "<1-2 sentences citing SPECIFIC evidence from the buyer intelligence above>"
    }}
  ],
  "synthesis": "<2-3 paragraph narrative summarizing the overall pain/gain fit>"
}}

RULES:
- Only include pain_categories where you found real evidence in the intelligence above (minimum 1 signal)
- "sources" array must only list section names where you actually found relevant signals
- "strong" requires DIRECT evidence: named acquisition, verbatim quote, confirmed user pain with product name
- "moderate" requires PLAUSIBLE connection with indirect evidence
- "weak" means theoretical connection only — no actual evidence
- "none" means no meaningful connection — DO NOT force connections
- Every "rationale" MUST cite specific buyer intelligence (not generic assertions)
- Every pain_category needs one asset_mapping entry per asset
- "signal_count" is the total number of distinct pain signals you found across all sources for that category
- Do NOT invent data not present in the intelligence above

Return ONLY the JSON object. No markdown fences. No commentary."""

    return prompt


# ── Output validation ─────────────────────────────────────────────────────────
def _validate_and_clean(analysis: dict, asset_keys: list[str]) -> dict:
    """Normalize category values and enforce schema on LLM output."""
    valid_strengths = {"strong", "moderate", "weak", "none"}
    valid_severities = {"high", "medium", "low"}
    valid_sections = {
        "market_reputation", "ceo_vision", "ma_appetite",
        "competitive_moat", "earnings_quotes", "recent_news", "strategic_fit"
    }

    # Normalize pain_categories
    seen_cats = set()
    clean_cats = []
    for pc in analysis.get("pain_categories", []):
        cat = _normalize_category(str(pc.get("category", "")))
        if cat in seen_cats:
            continue
        seen_cats.add(cat)
        clean_cats.append({
            "category": cat,
            "severity": pc.get("severity", "medium") if pc.get("severity") in valid_severities else "medium",
            "signal_count": max(1, int(pc.get("signal_count", 1))),
            "sources": [s for s in pc.get("sources", []) if s in valid_sections],
            "evidence": str(pc.get("evidence", ""))[:500],
        })
    analysis["pain_categories"] = clean_cats

    # Normalize asset_mappings
    valid_cat_names = {pc["category"] for pc in clean_cats}
    clean_mappings = []
    seen_mappings = set()
    for am in analysis.get("asset_mappings", []):
        cat = _normalize_category(str(am.get("pain_category", "")))
        key = am.get("asset_key", "")
        # If LLM returned a non-existent asset key, skip
        if key not in asset_keys and asset_keys:
            continue
        pair = (cat, key)
        if pair in seen_mappings:
            continue
        seen_mappings.add(pair)
        clean_mappings.append({
            "pain_category": cat,
            "asset_key": key,
            "strength": am.get("strength", "weak") if am.get("strength") in valid_strengths else "weak",
            "rationale": str(am.get("rationale", ""))[:500],
        })
    analysis["asset_mappings"] = clean_mappings

    # Ensure synthesis is a non-empty string
    if not isinstance(analysis.get("synthesis"), str):
        analysis["synthesis"] = ""

    return analysis


# ── Main entry point ──────────────────────────────────────────────────────────
def generate_pain_gain_analysis(
    buyer_slug: str,
    entity: str,
    target_company: str,
) -> dict | None:
    """
    Generate a cross-section Pain/Gain analysis for one buyer.

    Args:
        buyer_slug: e.g. "sap-successfactors"
        entity: e.g. "next_chapter"
        target_company: e.g. "HR.com Ltd"

    Returns:
        The analysis dict, or None on failure.
    """
    print(f"\n[pain_gain] Starting analysis for {buyer_slug} | {entity} → {target_company}")

    # 1. Load buyer JSON
    buyer_data = _load_buyer_json(buyer_slug)
    if not buyer_data:
        return None
    buyer_name = buyer_data.get("buyer_name", buyer_slug)

    # 2. Extract signals
    print("  [pain_gain] Extracting review pain signals...")
    review_signals = _extract_review_pain_signals(buyer_data)
    print(f"             {len(review_signals)} categories from reviews: {list(review_signals.keys())}")

    print("  [pain_gain] Extracting section signals...")
    section_signals = _extract_section_signals(buyer_data)
    print(f"             Sections found: {list(section_signals.keys())}")

    if not review_signals and not section_signals:
        print("  [pain_gain] ERROR: No signals found in buyer data. Aborting.")
        return None

    # 3. Load entity assets
    print("  [pain_gain] Loading entity assets from Supabase...")
    assets = _load_entity_assets(entity, target_company)
    if not assets:
        print(f"  [pain_gain] WARNING: No assets found for {entity} / {target_company}. "
              "Analysis will proceed but asset_mappings may be empty.")
    else:
        print(f"             {len(assets)} assets: {[a['asset_key'] for a in assets]}")

    asset_keys = [a["asset_key"] for a in assets]

    # 4. Build prompt and call LLM
    print("  [pain_gain] Building prompt...")
    prompt = _build_prompt(buyer_name, assets, review_signals, section_signals)
    print(f"             Prompt length: {len(prompt)} chars")

    print("  [pain_gain] Calling LLM (may take 60-180s)...")
    raw_response = _call_llm(prompt, timeout=240)
    if not raw_response:
        print("  [pain_gain] ERROR: LLM returned empty response.")
        return None

    # 5. Parse and validate
    print("  [pain_gain] Parsing LLM response...")
    analysis = _extract_json(raw_response)
    if not analysis or not isinstance(analysis, dict):
        print(f"  [pain_gain] ERROR: Could not parse JSON from LLM response.")
        print(f"             Raw (first 500 chars): {raw_response[:500]}")
        return None

    analysis = _validate_and_clean(analysis, asset_keys)
    analysis["generated_at"] = datetime.datetime.utcnow().isoformat() + "Z"
    analysis["buyer_slug"] = buyer_slug
    analysis["entity"] = entity
    analysis["target_company"] = target_company

    n_cats = len(analysis.get("pain_categories", []))
    n_maps = len(analysis.get("asset_mappings", []))
    print(f"  [pain_gain] Analysis OK: {n_cats} pain categories, {n_maps} asset mappings")

    # 6. Write to Supabase
    _write_to_supabase(entity, target_company, buyer_slug, buyer_name, analysis)

    # 7. Update per-buyer JSON
    buyer_data["pain_gain_analysis"] = analysis
    _save_buyer_json(buyer_slug, buyer_data)

    print(f"[pain_gain] Done for {buyer_slug}\n")
    return analysis


# ── CLI entry point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Pain/Gain analysis for a buyer.")
    parser.add_argument("--buyer", required=True, help="Buyer slug, e.g. sap-successfactors")
    parser.add_argument("--entity", default="next_chapter", help="Entity key, e.g. next_chapter")
    parser.add_argument("--target", default="HR.com Ltd", help="Target company name")
    args = parser.parse_args()

    result = generate_pain_gain_analysis(
        buyer_slug=args.buyer,
        entity=args.entity,
        target_company=args.target,
    )

    if result:
        print("\n=== RESULT SUMMARY ===")
        for pc in result.get("pain_categories", []):
            print(f"  [{pc['severity'].upper()}] {pc['category']} "
                  f"(signals: {pc['signal_count']}, sources: {pc['sources']})")
        print(f"\nAsset mappings: {len(result.get('asset_mappings', []))}")
        print(f"Synthesis length: {len(result.get('synthesis', ''))} chars")
    else:
        print("\nAnalysis FAILED — see errors above.")
        sys.exit(1)
