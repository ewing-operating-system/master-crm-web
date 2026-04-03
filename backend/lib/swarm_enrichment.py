"""
Agent Swarm Enrichment Worker
Processes agent_queue items where agent_name='swarm_enrichment'
Called by worker.py when it picks up a swarm job.

Payload from the HTML page:
{
    "buyer_slug": "paychex",
    "buyer_name": "Paychex",
    "section_key": "ceo_vision",
    "enhanced_prompt": "Paychex CEO vision strategy growth priorities HR technology",
    "goal": "Find CEO/executive quotes about vision, strategy, and growth priorities",
    "sources": "earnings calls, conference keynotes, interviews, annual letters",
    "exa_templates": ["earnings_call", "strategic_fit"],
    "avoid_queries": ["previous failed query 1", ...],
    "user_guidance": "Check their Q4 earnings call",
    "callback_field": "ceo_vision"
}
"""

import json
import os
import sys
import time
import subprocess
import psycopg2

# ── Path setup so imports resolve from backend/ ──────────────────────────────
_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_LIB_DIR)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from lib.exa_client import ExaClient

# ── Constants ─────────────────────────────────────────────────────────────────
PUBLIC_DATA_DIR = os.path.join(
    os.path.dirname(_BACKEND_DIR), "public", "data"
)
RESEARCH_JSON_PATH = os.path.join(PUBLIC_DATA_DIR, "debbie-buyer-research.json")
ENTITY = "next_chapter"


# ── LLM helpers ───────────────────────────────────────────────────────────────

def call_claude(prompt, timeout=300):
    try:
        result = subprocess.run(
            ["claude", "-p", "--output-format", "text"],
            input=prompt, capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def call_openrouter(prompt):
    import urllib.request, urllib.error, ssl
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        return None
    payload = json.dumps({
        "model": "deepseek/deepseek-chat-v3-0324",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4000,
        "temperature": 0.2,
    }).encode()
    ctx = ssl.create_default_context()
    try:
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        resp = urllib.request.urlopen(req, context=ctx, timeout=120)
        return json.loads(resp.read())["choices"][0]["message"]["content"]
    except Exception:
        return None


def llm(prompt, timeout=300):
    """Try Claude CLI first, fall back to OpenRouter."""
    return call_claude(prompt, timeout=timeout) or call_openrouter(prompt)


# ── Research execution logger ─────────────────────────────────────────────────

def log_execution(conn, buyer_name, section_key, query, raw_response,
                  source_urls, result_count, cost_usd, duration_ms,
                  status="success", error_message=None):
    """Write a row to research_executions for audit/dedup."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO research_executions
            (company_name, method_code, actual_query, tool, raw_response,
             result_count, source_urls, cost_usd, duration_ms, status,
             error_message, entity, executed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
    """, (
        buyer_name,
        f"swarm_{section_key}",
        query,
        "exa",
        json.dumps(raw_response, default=str)[:10000] if raw_response else None,
        result_count,
        json.dumps(source_urls) if source_urls else None,
        cost_usd,
        duration_ms,
        status,
        error_message,
        ENTITY,
    ))


# ── Previous search dedup check ───────────────────────────────────────────────

def get_previous_queries(conn, buyer_name, section_key):
    """Return set of queries already run for this buyer+section."""
    cur = conn.cursor()
    cur.execute("""
        SELECT actual_query FROM research_executions
        WHERE company_name = %s
          AND method_code = %s
          AND status = 'success'
    """, (buyer_name, f"swarm_{section_key}"))
    return {row[0] for row in cur.fetchall()}


# ── Exa result flattening ─────────────────────────────────────────────────────

def flatten_results(exa_response):
    """Return (combined_text, source_urls) from an Exa response dict."""
    results = exa_response.get("results", [])
    texts = []
    urls = []
    for r in results:
        url = r.get("url", "")
        if url:
            urls.append(url)
        # Prefer text, fall back to highlights
        content = r.get("text", "") or ""
        if not content:
            highlights = r.get("highlights", [])
            if isinstance(highlights, list):
                content = " ".join(highlights)
            elif isinstance(highlights, dict):
                content = " ".join(highlights.get("highlights", []))
        title = r.get("title", "")
        if title:
            content = f"[{title}] {content}"
        if content.strip():
            texts.append(content.strip())
    return "\n\n---\n\n".join(texts), urls


# ── Rephrase a query that should be avoided ───────────────────────────────────

def rephrase_query(original_query, buyer_name, section_key, avoid_queries):
    """Use Claude CLI to rephrase a query that overlaps with avoid_queries."""
    avoid_str = "\n".join(f"- {q}" for q in avoid_queries)
    prompt = (
        f"You are rephrasing a research query for the buyer research section '{section_key}' about {buyer_name}.\n"
        f"The original query is:\n  {original_query}\n\n"
        f"The following queries have already been tried and should NOT be repeated:\n{avoid_str}\n\n"
        f"Write ONE new search query that covers the same intent but uses different phrasing and keywords. "
        f"Return ONLY the new query string, nothing else."
    )
    result = llm(prompt, timeout=60)
    return result.strip() if result else original_query


# ── Synthesis prompt builder ──────────────────────────────────────────────────

def build_synthesis_prompt(buyer_name, section_key, goal, sources,
                            combined_text, user_guidance):
    guidance_block = (
        f"\nUser guidance: {user_guidance.strip()}\n" if user_guidance else ""
    )
    return f"""You are a senior M&A research analyst writing buyer intelligence for a dossier on {buyer_name}.

Section: {section_key}
Goal: {goal}
Source types targeted: {sources}
{guidance_block}
Below are raw excerpts from web research. Synthesize them into a concise, factual HTML narrative for this section.

RULES:
- Write 2-4 paragraphs of clean HTML (use <p> tags, <strong> for key quotes/facts)
- Include direct quotes with attribution where available
- Stick to verifiable facts from the excerpts — do NOT invent figures
- If no relevant information is found, write: <p>No relevant data found for this section.</p>
- Do NOT include <html>, <head>, <body>, or <style> tags — only inline content

RAW RESEARCH:
{combined_text[:8000]}

Return ONLY the HTML content for this section."""


# ── Static JSON updater ───────────────────────────────────────────────────────

def update_static_json(buyer_slug, section_key, content_html, source_urls):
    """
    Merge new section data into public/data/debbie-buyer-research.json.
    Creates the file (and directory) if it doesn't exist.

    JSON format expected by debbie-buyer-review.html:
      {buyers: {slug: {buyer_name, fit_score, sections: {key: html},
       hr_media_business: {narrative: html}, market_reputation: {products_discovered: []},
       strategic_fit: "html string", source_urls: {key: [urls]}}}}
    """
    os.makedirs(PUBLIC_DATA_DIR, exist_ok=True)

    # Read existing data
    if os.path.exists(RESEARCH_JSON_PATH):
        try:
            with open(RESEARCH_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = {"buyers": {}}
    else:
        data = {"buyers": {}}

    if "buyers" not in data:
        data = {"buyers": data}  # migrate old flat format

    buyers = data["buyers"]
    if buyer_slug not in buyers:
        buyers[buyer_slug] = {"buyer_slug": buyer_slug, "sections": {}, "source_urls": {}}

    buyer = buyers[buyer_slug]
    if "sections" not in buyer:
        buyer["sections"] = {}
    if "source_urls" not in buyer:
        buyer["source_urls"] = {}

    # Route section data to the correct location based on what the page reads
    if section_key in ("hr_media_business", "hr_domain_name"):
        buyer[section_key] = {"narrative": content_html}
    elif section_key == "market_reputation":
        existing_rep = buyer.get("market_reputation", {})
        existing_rep["narrative"] = content_html
        if "products_discovered" not in existing_rep:
            existing_rep["products_discovered"] = []
        buyer["market_reputation"] = existing_rep
    elif section_key == "strategic_fit":
        buyer["strategic_fit"] = content_html
    elif section_key == "golden_nuggets":
        buyer["golden_nuggets"] = content_html
    else:
        buyer["sections"][section_key] = content_html

    buyer["source_urls"][section_key] = source_urls

    with open(RESEARCH_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


# ── Main entry point ──────────────────────────────────────────────────────────

def agent_swarm_enrichment(conn, item):
    """
    Process one swarm_enrichment queue item.
    Returns (status, error_message) matching the worker.py contract.
    """
    payload = item.get("payload", {})

    buyer_slug = payload.get("buyer_slug", "")
    buyer_name = payload.get("buyer_name", buyer_slug)
    section_key = payload.get("section_key", "")
    enhanced_prompt = payload.get("enhanced_prompt", buyer_name)
    goal = payload.get("goal", f"Research {section_key} for {buyer_name}")
    sources = payload.get("sources", "web")
    exa_templates = payload.get("exa_templates") or ["strategic_fit"]
    avoid_queries = payload.get("avoid_queries") or []
    user_guidance = payload.get("user_guidance", "")

    if not buyer_slug or not section_key:
        return "failed", "Missing buyer_slug or section_key in payload"

    # ── pain_gain_match: bypass Exa search — call engine directly ────────────
    if section_key == "pain_gain_match":
        try:
            from pain_gain_engine import generate_pain_gain_analysis
            entity = payload.get("entity", "next_chapter")
            target_company = payload.get("target_company", "HR.com Ltd")
            analysis = generate_pain_gain_analysis(
                buyer_slug=buyer_slug,
                entity=entity,
                target_company=target_company,
            )
            if not analysis:
                return "failed", "pain_gain_engine returned no analysis"
            return "done", None
        except Exception as e:
            return "failed", f"pain_gain_engine error: {e}"

    # ── 1. Check previous executions for dedup ────────────────────────────────
    previous_queries = get_previous_queries(conn, buyer_name, section_key)

    exa = ExaClient()
    all_text_parts = []
    all_source_urls = []

    # ── 2. Run Exa searches using specified templates ─────────────────────────
    for template_name in exa_templates:
        # Build the query string that the template will produce
        # We run with company_name + topic derived from enhanced_prompt
        kwargs = {
            "company_name": buyer_name,
            "topic": enhanced_prompt,
            # Provide safe defaults for templates that need these
            "city": "",
            "state": "",
            "vertical": "",
            "owner_name": "",
        }

        # Determine the effective query for dedup check
        try:
            from lib.exa_client import TEMPLATES
            raw_template_query = TEMPLATES.get(template_name, {}).get("query", "")
            effective_query = raw_template_query.format(**kwargs).strip()
        except (KeyError, AttributeError):
            effective_query = f"{buyer_name} {enhanced_prompt}"

        # If this query overlaps with avoid_queries, rephrase it
        if effective_query in avoid_queries:
            effective_query = rephrase_query(
                effective_query, buyer_name, section_key, avoid_queries
            )
            kwargs["topic"] = effective_query  # swap in rephrased topic

        # Skip if we've already successfully run this exact query
        if effective_query in previous_queries:
            continue

        t0 = time.time()
        try:
            exa_response = exa.search(template_name, **kwargs)
            duration_ms = int((time.time() - t0) * 1000)
            text_chunk, urls = flatten_results(exa_response)
            result_count = len(exa_response.get("results", []))
            raw_cost = exa_response.get("costDollars", 0.0)
            cost_usd = float(raw_cost.get("total", 0.0)) if isinstance(raw_cost, dict) else float(raw_cost or 0.0)

            log_execution(
                conn, buyer_name, section_key, effective_query,
                exa_response, urls, result_count, cost_usd, duration_ms,
            )

            if text_chunk:
                all_text_parts.append(text_chunk)
            all_source_urls.extend(urls)

        except Exception as exc:
            duration_ms = int((time.time() - t0) * 1000)
            log_execution(
                conn, buyer_name, section_key, effective_query,
                None, [], 0, 0.0, duration_ms,
                status="error", error_message=str(exc)[:500],
            )
            # Non-fatal — continue with other templates

        time.sleep(0.5)  # rate limit courtesy pause

    # ── 3. Run additional deep search if user gave guidance ───────────────────
    if user_guidance and user_guidance.strip():
        guidance_query = f"{buyer_name} {user_guidance.strip()}"

        if guidance_query not in previous_queries and guidance_query not in avoid_queries:
            t0 = time.time()
            try:
                exa_response = exa.raw_search(
                    query=guidance_query,
                    search_type="deep",
                    num_results=8,
                    max_characters=5000,
                    content_mode="text",
                    use_autoprompt=True,
                )
                duration_ms = int((time.time() - t0) * 1000)
                text_chunk, urls = flatten_results(exa_response)
                result_count = len(exa_response.get("results", []))
                raw_cost = exa_response.get("costDollars", 0.0)
                cost_usd = float(raw_cost.get("total", 0.0)) if isinstance(raw_cost, dict) else float(raw_cost or 0.0)

                log_execution(
                    conn, buyer_name, section_key, guidance_query,
                    exa_response, urls, result_count, cost_usd, duration_ms,
                )

                if text_chunk:
                    all_text_parts.append(text_chunk)
                all_source_urls.extend(urls)

            except Exception as exc:
                duration_ms = int((time.time() - t0) * 1000)
                log_execution(
                    conn, buyer_name, section_key, guidance_query,
                    None, [], 0, 0.0, duration_ms,
                    status="error", error_message=str(exc)[:500],
                )

    # ── 4. Synthesize via Claude CLI ──────────────────────────────────────────
    combined_text = "\n\n---\n\n".join(all_text_parts) if all_text_parts else ""
    unique_urls = list(dict.fromkeys(all_source_urls))  # deduplicate, preserve order

    synthesis_prompt = build_synthesis_prompt(
        buyer_name, section_key, goal, sources, combined_text, user_guidance
    )
    content_html = llm(synthesis_prompt, timeout=300)

    if not content_html:
        content_html = "<p>Research synthesis failed. Raw sources may be available.</p>"

    # ── 5. Update static JSON file ────────────────────────────────────────────
    try:
        update_static_json(buyer_slug, section_key, content_html, unique_urls)
    except Exception as exc:
        # Non-fatal — log but don't fail the job
        pass

    # ── 6. Write result back to agent_queue payload (for the HTML page poller) ─
    # The HTML page polls agent_queue for status='done' and reads result_payload
    # We store the synthesized content there so the page can display it.
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE agent_queue
            SET result_payload = %s
            WHERE id = %s
        """, (
            json.dumps({
                "section_key": section_key,
                "callback_field": payload.get("callback_field", section_key),
                "content": content_html,
                "source_urls": unique_urls,
            }, default=str),
            item["queue_id"],
        ))
    except Exception:
        # result_payload column may not exist yet — non-fatal
        pass

    return "done", None
