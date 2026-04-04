"""
letter_engine.py — Next Chapter M&A Advisory
Renders physical letter HTML from Supabase company profiles + valuation lever data.
Output is ready for direct submission to the Lob API (print-and-mail).

Config-driven: When a vertical config (vcfg) is provided, letter data is assembled
from the config file instead of the hardcoded VERTICAL_DATA dict. Falls back to legacy
dicts when vcfg is None (backward-compatible).

Usage:
    # Config-driven (preferred):
    from lib.config.vertical_config_schema import load_vertical
    vcfg = load_vertical("home_services")
    engine = LetterEngine(supabase_client, vcfg=vcfg)
    html = engine.render(company_id="aquascience", variant="initial")

    # Legacy (backward-compatible):
    engine = LetterEngine(supabase_client)
    html = engine.render(company_id="aquascience", variant="initial")

Variants:
    initial   — First outreach. Story hook, valuation benchmarks, CTA.
    followup  — Two-week follow-up. References first letter, reinforces timing.
    final     — Four-week final touch. Low-pressure, personal, door stays open.
"""

import importlib.util
import os
from datetime import date
from pathlib import Path
from typing import Literal

from jinja2 import Environment, FileSystemLoader, select_autoescape

LetterVariant = Literal["initial", "followup", "final"]

# Path resolution — works regardless of working directory
_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

# ── Load vertical config module via importlib (avoids sys.path 'lib' collision) ──
_REPO_ROOT = Path(__file__).resolve().parent.parent
_vcfg_path = _REPO_ROOT / "lib" / "config" / "vertical_config_schema.py"
try:
    _spec = importlib.util.spec_from_file_location("vertical_config_schema", str(_vcfg_path))
    _vcfg_mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_vcfg_mod)
    _load_vertical = _vcfg_mod.load_vertical
    _list_verticals = _vcfg_mod.list_verticals
except Exception:
    _load_vertical = None
    _list_verticals = lambda: []


# ── Metric display names ─────────────────────────────────────────────────
_METRIC_DISPLAY = {
    "ebitda": "EBITDA",
    "revenue": "revenue",
    "arr": "ARR",
    "sde": "SDE",
}


# ---------------------------------------------------------------------------
# Config-driven vertical data builder
# ---------------------------------------------------------------------------

def _lowercase_lever(lever: str) -> str:
    """Lowercase a lever name, preserving acronyms like DOT, NPCA, EPA."""
    if not lever:
        return ""
    first_word = lever.split()[0] if lever.split() else ""
    # If the first word is all-caps (acronym), keep it as-is
    if first_word.isupper() and len(first_word) > 1:
        return lever
    return lever[0].lower() + lever[1:]


def _vertical_data_from_config(vcfg: dict, sub_vertical: "str | None" = None) -> dict:
    """
    Build a VERTICAL_DATA-shaped dict from a vertical config.

    Reads valuation_fields, growth_levers, and synthesis_prompts from the
    sub_vertical (if present) or the base config level. Produces the same
    shape that the legacy VERTICAL_DATA entries provide.
    """
    # Start with base-level config
    vf = dict(vcfg.get("valuation_fields", {}))
    gl = list(vcfg.get("growth_levers", []))
    sp = dict(vcfg.get("synthesis_prompts", {}))
    display_name = vcfg.get("display_name", "")

    # If a sub-vertical matches, merge its overrides
    sub_verticals = vcfg.get("sub_verticals", {})
    if sub_vertical and sub_vertical in sub_verticals:
        sv = sub_verticals[sub_vertical]
        display_name = sv.get("display_name", display_name)

        # Valuation: sub overrides base
        sv_vf = sv.get("valuation_fields", {})
        vf.update(sv_vf)

        # Growth levers: sub replaces base entirely if present
        sv_gl = sv.get("growth_levers")
        if sv_gl:
            gl = sv_gl

        # Synthesis prompts: sub overrides base per-key
        sv_sp = sv.get("synthesis_prompts", {})
        sp.update(sv_sp)

    # Derive vertical_short from display_name
    # "Concrete & Precast" → "concrete and precast", "HVAC" → "HVAC"
    vertical_short = display_name.replace("&", "and")
    # Only lowercase if it's not an acronym (all-caps and short)
    if not (len(vertical_short.replace(" ", "")) <= 5 and vertical_short.replace(" ", "").isupper()):
        vertical_short = vertical_short.lower()

    # Format multiples as "X.Yx" strings
    floor = vf.get("multiple_floor", 4.0)
    ceiling = vf.get("multiple_ceiling", 7.0)
    median = vf.get("multiple_median", 5.5)

    return {
        "vertical_short": vertical_short,
        "multiple_floor": f"{floor}x",
        "multiple_ceiling": f"{ceiling}x",
        "multiple_median": f"{median}x",
        "primary_metric": _METRIC_DISPLAY.get(
            vf.get("primary_metric", "ebitda"), "EBITDA"
        ),
        "top_levers": [_lowercase_lever(g.get("lever", "")) for g in gl][:3],
        "market_context": sp.get("market_context", ""),
        "buyer_appetite": sp.get("buyer_appetite", ""),
        "premium_driver": sp.get("premium_driver", ""),
    }


# ---------------------------------------------------------------------------
# Legacy: Vertical EBITDA data — sourced from the ebitda-levers pages
# Keyed by vertical slug matching Supabase companies.vertical field
# ---------------------------------------------------------------------------
VERTICAL_DATA: dict[str, dict] = {
    "water_treatment": {
        "vertical_short": "water treatment",
        "multiple_floor": "4.0x",
        "multiple_ceiling": "8.0x",
        "multiple_median": "5.5x",
        "top_levers": [
            "recurring filter and salt delivery revenue",
            "rental equipment portfolios with monthly income",
            "water testing and analysis capability",
        ],
        "market_context": (
            "Water treatment sits at the intersection of aging infrastructure, "
            "tightening EPA mandates around PFAS and lead, and essential-service "
            "recession resistance — a combination that has put this vertical at "
            "the top of every serious acquirer's target list."
        ),
        "buyer_appetite": (
            "Culligan, Pentair, Kinetico, and a growing list of family-office "
            "platforms are actively acquiring established water treatment operators. "
            "They are paying 5x to 8x EBITDA for businesses with strong recurring "
            "revenue — and competing hard for the ones that have it."
        ),
        "premium_driver": (
            "The businesses commanding premium multiples in water treatment today "
            "share one thing: recurring revenue from rentals, service agreements, "
            "and consumable delivery routes. That recurring base is what separates "
            "a 4x outcome from an 8x outcome on the same EBITDA dollar."
        ),
    },
    "hvac": {
        "vertical_short": "HVAC",
        "multiple_floor": "4.5x",
        "multiple_ceiling": "8.5x",
        "multiple_median": "6.0x",
        "top_levers": [
            "service agreement attach rate",
            "recurring maintenance contract revenue",
            "commercial vs. residential mix",
        ],
        "market_context": (
            "HVAC consolidation is running at full speed — PE-backed platforms "
            "and national strategics are competing for established operators in "
            "every major metro market."
        ),
        "buyer_appetite": (
            "Apex Service Partners, Redwood Services, and a dozen other "
            "PE-backed platforms are writing checks weekly for HVAC businesses "
            "with strong service agreement programs and tenured technician teams."
        ),
        "premium_driver": (
            "The spread between a 4.5x and an 8x outcome in HVAC almost always "
            "comes down to recurring revenue. Service agreements turn one-time "
            "replacement customers into annuities — and buyers underwrite "
            "those annuities at a significant premium."
        ),
    },
    "plumbing": {
        "vertical_short": "plumbing",
        "multiple_floor": "4.0x",
        "multiple_ceiling": "7.5x",
        "multiple_median": "5.5x",
        "top_levers": [
            "service agreement and maintenance plan revenue",
            "commercial account concentration",
            "drain jetting and hydro-excavation capability",
        ],
        "market_context": (
            "Plumbing is one of the most recession-resistant verticals in "
            "home services, and acquirers have taken notice. The combination "
            "of essential-service demand, aging housing stock, and growing "
            "commercial construction activity is driving sustained M&A interest."
        ),
        "buyer_appetite": (
            "National platforms and regional consolidators are actively "
            "acquiring plumbing businesses with strong commercial relationships "
            "and a documented recurring revenue base."
        ),
        "premium_driver": (
            "Plumbing businesses with commercial contract revenue and service "
            "agreements consistently trade at the top of the multiple range. "
            "Buyers value predictable call volume and repeat customer relationships "
            "above almost everything else in this vertical."
        ),
    },
    "roofing": {
        "vertical_short": "roofing",
        "multiple_floor": "3.5x",
        "multiple_ceiling": "7.0x",
        "multiple_median": "5.0x",
        "top_levers": [
            "storm-restoration revenue diversification",
            "commercial roofing contract concentration",
            "maintenance and inspection program revenue",
        ],
        "market_context": (
            "Roofing M&A has accelerated sharply as institutional buyers recognize "
            "the combination of essential-service demand, insurance-backed revenue, "
            "and the scalability of a well-run roofing operation."
        ),
        "buyer_appetite": (
            "Roofing platforms backed by institutional capital are actively "
            "seeking established operators with commercial relationships, "
            "storm-restoration track records, and tenured estimating teams."
        ),
        "premium_driver": (
            "Roofing businesses with commercial contract revenue and diversified "
            "revenue streams — new construction, re-roof, storm, maintenance — "
            "command the strongest multiples. Single-channel operators "
            "carry weather and seasonality risk that buyers discount."
        ),
    },
    "pest_control": {
        "vertical_short": "pest control",
        "multiple_floor": "5.0x",
        "multiple_ceiling": "10.0x",
        "multiple_median": "7.0x",
        "top_levers": [
            "recurring subscription revenue percentage",
            "route density and stops-per-hour efficiency",
            "commercial account contract value",
        ],
        "market_context": (
            "Pest control trades at some of the highest multiples in all of "
            "home services — driven almost entirely by the subscription model "
            "that creates predictable, recurring cash flow buyers can underwrite "
            "at premium multiples."
        ),
        "buyer_appetite": (
            "Rollins, Rentokil, and a growing number of PE-backed regional "
            "platforms are aggressively acquiring pest control operators, "
            "particularly those with high recurring revenue ratios and "
            "dense residential routes."
        ),
        "premium_driver": (
            "Recurring subscription revenue is the single most powerful "
            "value driver in pest control. Businesses with 80%+ recurring "
            "revenue routinely trade at 8x to 10x EBITDA — nearly double "
            "what a primarily one-time-service operator achieves."
        ),
    },
    "concrete_precast": {
        "vertical_short": "concrete and precast",
        "multiple_floor": "4.0x",
        "multiple_ceiling": "7.5x",
        "multiple_median": "5.5x",
        "top_levers": [
            "DOT and municipal contract portfolio",
            "precast product line diversification",
            "aggregate reserve assets",
        ],
        "market_context": (
            "The Infrastructure Investment and Jobs Act's $550 billion in "
            "new federal spending — concentrated in concrete-intensive highways, "
            "bridges, and water systems — has given serious demand visibility "
            "to well-positioned concrete operators and drawn increased M&A attention."
        ),
        "buyer_appetite": (
            "Summit Materials, Knife River, and regional platforms are building "
            "geographic networks of concrete and precast operations. Well-located "
            "plants with strong DOT relationships and tenured ACI-certified "
            "workforces are commanding premium attention."
        ),
        "premium_driver": (
            "The businesses trading at the top of the concrete multiple range "
            "share two things: irreplaceable permitted plant locations and "
            "long-term government contract relationships that create visible, "
            "multi-year revenue. Those combinations are genuinely scarce."
        ),
    },
    "flooring": {
        "vertical_short": "flooring",
        "multiple_floor": "3.5x",
        "multiple_ceiling": "6.5x",
        "multiple_median": "4.75x",
        "top_levers": [
            "commercial contract revenue concentration",
            "multi-family and property management relationships",
            "installation crew depth and tenure",
        ],
        "market_context": (
            "Flooring consolidation is in early innings, with platforms "
            "building regional operations by acquiring established local dealers "
            "and installation businesses with commercial track records."
        ),
        "buyer_appetite": (
            "Regional platforms and national floor covering chains are acquiring "
            "flooring businesses with strong commercial accounts, property "
            "management relationships, and experienced installation crews."
        ),
        "premium_driver": (
            "Commercial flooring relationships — multi-family, hospitality, "
            "healthcare, property management — drive premium multiples in "
            "this vertical. Repeat institutional customers represent the "
            "recurring revenue equivalent in an otherwise project-driven business."
        ),
    },
}

# Fallback for unrecognized verticals
_DEFAULT_VERTICAL = {
    "vertical_short": "home services",
    "multiple_floor": "4.0x",
    "multiple_ceiling": "7.0x",
    "multiple_median": "5.5x",
    "top_levers": ["recurring revenue", "management depth", "customer concentration"],
    "market_context": (
        "Home services M&A is running at record pace, with PE-backed platforms "
        "and strategic buyers competing hard for established operators with "
        "recurring revenue and tenured teams."
    ),
    "buyer_appetite": (
        "Institutional buyers across a broad spectrum of home services verticals "
        "are actively acquiring, paying premium multiples for businesses with "
        "strong recurring revenue and owner-independent operations."
    ),
    "premium_driver": (
        "The single most reliable driver of premium multiples in home services "
        "is recurring revenue. Service agreements, maintenance contracts, and "
        "subscription programs convert a transactional business into an annuity "
        "— and buyers pay significantly more for annuities."
    ),
}


# ---------------------------------------------------------------------------
# Variant copy blocks
# Slotted into {{ variant_paragraph }} in the template
# ---------------------------------------------------------------------------
VARIANT_PARAGRAPHS: dict[str, str] = {
    "initial": (
        "I'm reaching out because your business caught our attention during research "
        "we've been doing on established operators in your market. We're not a broker "
        "casting a wide net — we work with a small number of business owners at a time, "
        "and we only reach out when we believe there's a genuine fit between what a "
        "seller has built and what buyers are actively looking for. Based on what we "
        "know about your company, we think that fit exists here."
    ),
    "followup": (
        "I sent a letter a couple of weeks ago and wanted to follow up — not to push, "
        "but because the market has stayed active and I didn't want timing to work "
        "against you. The analysis we prepared is still current. If you've already "
        "reviewed it, I'd welcome a quick call. If the letter didn't reach you, I'm "
        "happy to walk through it over the phone in fifteen minutes."
    ),
    "final": (
        "This is my last outreach — I don't believe in wearing out a welcome. "
        "If the timing isn't right, I completely understand. Building a business "
        "like yours takes decades of commitment, and the decision to explore a "
        "transition deserves to be made on your terms and your timeline. "
        "If anything changes, I hope you'll keep Next Chapter in mind. "
        "The door is always open."
    ),
}

CLOSING_PARAGRAPHS: dict[str, str] = {
    "initial": (
        "There's no pressure and no obligation. If you're curious about what your "
        "business is worth in today's market, the analysis is there for you. "
        "If the timing isn't right, I understand completely. Either way, I hope "
        "this letter gives you something useful."
    ),
    "followup": (
        "Regardless of your timing, I hope the analysis we built for you is useful "
        "as a reference point. Understanding your market position and what drives "
        "value in your vertical costs you nothing — and that knowledge is yours "
        "whether you do anything with it or not."
    ),
    "final": (
        "Thank you for the time it took to read this. You've built something real "
        "over the years, and whatever path you choose, I genuinely wish you well."
    ),
}


# ---------------------------------------------------------------------------
# LetterEngine
# ---------------------------------------------------------------------------
class LetterEngine:
    """
    Renders a personalized Next Chapter letter for a given company.

    Args:
        supabase: An initialized supabase-py client instance.
        template_dir: Override the default templates/ directory path.
        vcfg: Vertical config dict (from load_vertical). When provided,
              letter data is assembled from config instead of VERTICAL_DATA.
    """

    def __init__(self, supabase, template_dir: "Path | None" = None, vcfg: "dict | None" = None):
        self.supabase = supabase
        self.vcfg = vcfg
        tdir = template_dir or _TEMPLATE_DIR
        self.jinja = Environment(
            loader=FileSystemLoader(str(tdir)),
            autoescape=select_autoescape(["html"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render(self, company_id: str, variant: str = "initial", vcfg: "dict | None" = None) -> str:
        """
        Render a letter for the given company_id and variant.

        Args:
            company_id: Supabase company ID.
            variant: Letter variant (initial, followup, final).
            vcfg: Optional per-call config override. Falls back to self.vcfg.

        Returns:
            Rendered HTML string, ready for Lob API submission.

        Raises:
            ValueError: If the company or owner record is not found.
        """
        if variant not in VARIANT_PARAGRAPHS:
            raise ValueError(f"Invalid variant '{variant}'. Must be: initial, followup, final.")

        cfg = vcfg or self.vcfg
        company = self._fetch_company(company_id)
        owner = self._fetch_owner(company_id)

        # Config-driven path: build vertical_info from config
        if cfg:
            sub_vertical = company.get("vertical", "")
            vertical_info = _vertical_data_from_config(cfg, sub_vertical)
        else:
            # Legacy path: use hardcoded VERTICAL_DATA
            vertical_info = VERTICAL_DATA.get(company.get("vertical", ""), _DEFAULT_VERTICAL)

        context = self._build_context(company, owner, vertical_info, variant)
        template = self.jinja.get_template("master-letter.html")
        return template.render(**context)

    def render_all_variants(self, company_id: str) -> dict:
        """
        Render initial, followup, and final variants for a single company.

        Returns:
            Dict mapping variant name to rendered HTML string.
        """
        return {
            "initial": self.render(company_id, "initial"),
            "followup": self.render(company_id, "followup"),
            "final": self.render(company_id, "final"),
        }

    # ------------------------------------------------------------------
    # Supabase fetchers
    # ------------------------------------------------------------------

    def _fetch_company(self, company_id: str) -> dict:
        resp = (
            self.supabase.table("companies")
            .select("*")
            .eq("id", company_id)
            .single()
            .execute()
        )
        if not resp.data:
            raise ValueError(f"Company not found: {company_id}")
        return resp.data

    def _fetch_owner(self, company_id: str) -> dict:
        resp = (
            self.supabase.table("contacts")
            .select("*")
            .eq("company_id", company_id)
            .eq("role", "owner")
            .limit(1)
            .execute()
        )
        if not resp.data:
            raise ValueError(f"No owner contact found for company: {company_id}")
        return resp.data[0]

    # ------------------------------------------------------------------
    # Context builder
    # ------------------------------------------------------------------

    def _build_context(
        self,
        company: dict,
        owner: dict,
        vertical_info: dict,
        variant: str,
    ) -> dict:
        owner_first = owner.get("first_name", "")
        owner_last = owner.get("last_name", "")
        company_name = company.get("name", "")
        city = company.get("city", "")
        state = company.get("state", "")
        founded_year = company.get("founded_year")
        years_in_business = (date.today().year - int(founded_year)) if founded_year else None

        opening_paragraph = self._build_opening(
            owner_first, company_name, city, state, years_in_business, company
        )

        industry_context_paragraph = (
            vertical_info["market_context"] + " " + vertical_info["buyer_appetite"]
        )

        ebitda_narrative_paragraph = self._build_ebitda_narrative(company, vertical_info)

        highlight_quote = self._build_highlight_quote(company, vertical_info)

        hook_paragraph = (
            f"We've spent significant time studying the {vertical_info['vertical_short']} "
            f"market and the buyers who are most active in it right now. Based on what we "
            f"know about {company_name} and where the market sits today, we put together a "
            f"full analysis of your company's position — valuation range, the specific levers "
            f"that would move your multiple, and a map of the buyers most likely to compete "
            f"for a business like yours."
        )

        personalized_url = company.get(
            "personalized_url",
            f"https://nextchapterma.com/{company.get('id', company_name.lower().replace(' ', '-'))}",
        )

        return {
            "owner_first_name": owner_first,
            "owner_last_name": owner_last,
            "company_name": company_name,
            "company_address": company.get("address", ""),
            "company_city": city,
            "company_state": state,
            "company_zip": company.get("zip", ""),
            "letter_date": date.today().strftime("%B %-d, %Y"),
            "vertical_short": vertical_info["vertical_short"],
            "opening_paragraph": opening_paragraph,
            "industry_context_paragraph": industry_context_paragraph,
            "ebitda_narrative_paragraph": ebitda_narrative_paragraph,
            "highlight_quote": highlight_quote,
            "hook_paragraph": hook_paragraph,
            "variant_paragraph": VARIANT_PARAGRAPHS[variant],
            "closing_paragraph": CLOSING_PARAGRAPHS[variant],
            "personalized_url": personalized_url,
        }

    # ------------------------------------------------------------------
    # Paragraph generators
    # ------------------------------------------------------------------

    def _build_opening(
        self,
        owner_first: str,
        company_name: str,
        city: str,
        state: str,
        years_in_business: "int | None",
        company: dict,
    ) -> str:
        age_phrase = (
            f"over {years_in_business} years" if years_in_business else "many years"
        )
        revenue_phrase = ""
        if company.get("estimated_revenue") and company["estimated_revenue"] >= 1_000_000:
            revenue_phrase = ", growing it to a multi-million-dollar operation,"
        location_phrase = f" in {city}, {state}" if city and state else ""

        return (
            f"You've spent {age_phrase} building {company_name}{location_phrase}"
            f"{revenue_phrase} and that kind of track record doesn't happen by accident. "
            f"It takes the right combination of operational discipline, customer trust, "
            f"and the willingness to keep grinding through the years when it wasn't easy. "
            f"That's exactly the kind of business that serious buyers are looking for "
            f"right now — and why I wanted to reach out directly."
        )

    def _build_ebitda_narrative(self, company: dict, vertical_info: dict) -> str:
        floor = vertical_info["multiple_floor"]
        ceiling = vertical_info["multiple_ceiling"]
        median = vertical_info["multiple_median"]
        premium_driver = vertical_info["premium_driver"]
        metric = vertical_info.get("primary_metric", "EBITDA")

        return (
            f"Businesses in {vertical_info['vertical_short']} are currently trading at "
            f"{floor} to {ceiling} {metric}, with well-positioned operators achieving {median} "
            f"or better when the right factors are in place. {premium_driver}"
        )

    def _build_highlight_quote(self, company: dict, vertical_info: dict) -> str:
        company_name = company.get("name", "this business")
        return (
            f"The right buyer, with the right process, will compete hard for a business "
            f"like {company_name}. The question is whether you have someone in your corner "
            f"who knows exactly which buyers those are, what they're paying, and how to "
            f"structure the conversation so you walk away with the best possible outcome."
        )
