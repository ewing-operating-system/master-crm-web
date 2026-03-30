"""
meeting_engine_v2.py — Next Chapter M&A Advisory
Renders the interactive meeting page v2 template from Supabase company data.

Usage:
    engine = MeetingEngineV2(supabase_client)
    html = engine.render(
        company_id="aquascience",
        meeting_date="2026-03-29",
        meeting_type="discovery"
    )

Meeting types:
    discovery        — First meeting: broad questions, owner motivation, story
    financial_review — Deep dive: margins, revenue mix, expenses, add-backs
    engagement       — Close meeting: timeline, fee, exclusivity, legal
"""

from datetime import date as date_type
from pathlib import Path
from typing import Literal

from jinja2 import Environment, FileSystemLoader, select_autoescape

MeetingType = Literal["discovery", "financial_review", "engagement"]

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

# ---------------------------------------------------------------------------
# Questions by meeting type
# ---------------------------------------------------------------------------

QUESTIONS: dict[str, list[str]] = {
    "discovery": [
        "Tell me about how the business got started — what was the original vision?",
        "How do the different parts of the business feed each other today?",
        "Of your team, who are the key people a buyer would need to retain to keep the business running?",
        "How much of your revenue is recurring — maintenance contracts, service agreements, repeat customers — versus one-time or project-based?",
        "What does your ideal outcome look like — full exit, partial sale with continued involvement, or something else?",
        "Is there anything about the business that would be difficult to transfer to new ownership?",
        "Have you been approached by buyers before? If so, what turned you off about those conversations?",
        "What's your timeline? Is there a personal milestone or business event driving the timing?",
        "If you could design the perfect buyer, what would matter most — price, culture, employee treatment, brand preservation?",
        "What are you most proud of when you look at what you've built?",
    ],
    "financial_review": [
        "Walk me through the P&L — what are the three biggest cost line items?",
        "How much of the revenue is truly recurring on contract versus repeat-but-not-contracted customers?",
        "What's the revenue mix by channel — and has that mix shifted in the last three years?",
        "What add-backs should we consider? Owner salary, personal expenses, one-time items?",
        "Are there any customer concentrations we should know about — one client over 10% of revenue?",
        "What does seasonality look like? Are there months where cash flow gets tight?",
        "What capital expenditures are required to maintain the business at current levels?",
        "Is there any deferred maintenance or equipment replacement that a buyer should know about?",
        "What does working capital look like — how much cash does the business typically need to operate?",
        "Are there any off-balance-sheet obligations — leases, earn-outs, contingent liabilities?",
    ],
    "engagement": [
        "Based on everything we've discussed, does a 3–6 month process timeline feel right to you?",
        "Our advisory fee is a success-only structure — does that approach make sense to you?",
        "Are you comfortable with an exclusivity period so we can run a focused, competitive process?",
        "Do you have legal counsel lined up for the transaction, or would you like a recommendation?",
        "Who else is involved in this decision — family, partners, advisors — and do they need to be part of the process?",
        "Are there any buyers you've already spoken with that we should know about?",
        "What information are you comfortable sharing in the initial teaser — we'll always get your approval first?",
        "Are there any buyers you'd specifically prefer we not approach?",
        "What's the best way to communicate during the process — email, phone, scheduled check-ins?",
        "Is there anything we haven't covered that's on your mind before we move forward?",
    ],
}

MEETING_TYPE_LABELS = {
    "discovery": "Discovery Meeting",
    "financial_review": "Financial Review",
    "engagement": "Engagement Discussion",
}

# ---------------------------------------------------------------------------
# Default content blocks
# ---------------------------------------------------------------------------

DEFAULT_AGENDA = {
    "discovery": [
        "Introductions and rapport — learn the owner's journey building the business",
        "Understand current priorities — what's working, what keeps them up at night",
        "Explore the business model — how the different parts work together",
        "Gauge openness to strategic alternatives — what does 'the next chapter' mean personally",
        "Outline Next Chapter's advisory approach and answer questions about the process",
    ],
    "financial_review": [
        "Review 3-year P&L summary — revenue trends, margin trajectory",
        "Walk through revenue mix — recurring vs. one-time, by channel",
        "Discuss add-backs and owner compensation structure",
        "Identify customer concentrations and one-time items",
        "Discuss working capital requirements and CapEx history",
        "Align on preliminary valuation methodology and range",
    ],
    "engagement": [
        "Recap what we've learned — confirm our understanding of the business",
        "Present preliminary valuation range and methodology",
        "Walk through our process — timeline, buyer outreach, confidentiality",
        "Discuss and finalize engagement terms",
        "Sign engagement letter and kick off the process",
    ],
}

DEFAULT_OBJECTIVES = {
    "discovery": [
        "Build genuine trust — this owner built something over decades and needs to know we respect that",
        "Understand personal motivation: retirement, partial exit, growth capital, or legacy preservation?",
        "Learn the real economics — margins, recurring vs. one-time, channel breakdown",
        "Identify deal-breakers early: employee retention, family involvement, non-competes",
        "Determine timeline expectations",
        "Assess whether the company is engagement-ready or needs pre-market preparation",
    ],
    "financial_review": [
        "Get comfortable with the real EBITDA — normalized for add-backs and one-time items",
        "Understand revenue quality: recurring vs. project-based, customer concentration",
        "Identify any issues: deferred CapEx, contingent liabilities, lease obligations",
        "Build the financial model inputs needed for the buyer package",
        "Confirm our preliminary valuation range is realistic",
    ],
    "engagement": [
        "Align on valuation range and process timeline",
        "Address any remaining objections or concerns",
        "Get to a signed engagement letter",
        "Establish communication cadence for the process",
    ],
}

DEFAULT_TALKING_POINTS = [
    "We specialize exclusively in home services and trades — we understand the language buyers speak in this space",
    "We run a controlled, confidential process — the owner's identity stays protected behind a blind teaser until they approve disclosure",
    "Our typical engagement targets 40–60 curated buyers: PE-backed platforms, national strategics, and family offices",
    "We handle everything — valuation, buyer outreach, negotiations, due diligence management — so the owner can keep running their business",
    "Businesses in this vertical are commanding strong multiples right now, and buyer appetite is high",
]

DEFAULT_DANGER_ZONES = {
    "discovery": [
        "Do NOT quote specific valuation numbers in a discovery meeting — anchor numbers can offend or set unrealistic expectations",
        "Avoid implying the business needs fixing — the owner built this successfully and is proud of it",
        "Do not press on succession planning or age-related exit pressure — let them volunteer their timeline",
        "Avoid rushing to next steps or contracts — this is discovery, not a close",
        "Do not mention specific buyer names — confidentiality works both directions at this stage",
    ],
    "financial_review": [
        "Do not challenge add-backs aggressively in this meeting — understand them first, verify later",
        "Avoid making valuation commitments before the full financial picture is clear",
        "Do not let the owner anchor to a specific price — discuss range and methodology, not a number",
        "Be careful with customer concentration questions — owners can be defensive about their biggest accounts",
    ],
    "engagement": [
        "Do not let the fee conversation dominate — tie it back to value and outcome",
        "Avoid exclusivity language that sounds like a trap — frame it as protecting the process quality",
        "Do not pressure to sign in the meeting — give them time to review the engagement letter",
        "Make sure all decision-makers have been briefed before the signing conversation",
    ],
}

DEFAULT_WHAT_WE_BRING = [
    "Boutique M&A advisory focused exclusively on home services businesses — plumbing, HVAC, water treatment, roofing, and related trades",
    "Controlled, confidential process — the owner's name and company identity stay protected until they approve disclosure to specific buyers",
    "40–60 curated buyers per engagement across PE-backed platforms, national strategics, and family offices",
    "We handle everything — valuation, buyer outreach, negotiations, due diligence management — so the owner can keep running their business",
    "Deep relationships with the buyers who are most active in this space right now",
]

DEFAULT_SUCCESS_CRITERIA = {
    "discovery": [
        "Owner opens up about personal motivations — we understand the 'why' behind the timing",
        "We learn the real revenue breakdown: recurring vs. one-time, channel mix, margin profile",
        "Owner asks us questions about the process — signals genuine interest",
        "We identify key employees and any retention risks",
        "Owner agrees to a follow-up meeting or asks what the next step would be",
        "No awkward moments — owner feels heard, respected, and confident we understand their business",
    ],
    "financial_review": [
        "We have a clean 3-year P&L with add-backs identified",
        "We understand the revenue quality and any concentrations",
        "We can defend a preliminary valuation range based on real numbers",
        "Owner is comfortable with the financial picture we've assembled",
    ],
    "engagement": [
        "Signed engagement letter",
        "Agreed process timeline and communication cadence",
        "Owner is excited about the process, not just resigned to it",
    ],
}

DEFAULT_NEXT_STEPS_POSITIVE = [
    "Schedule a deeper financial review meeting — request 3 years of P&Ls and tax returns",
    "Send a follow-up email summarizing what we heard and confirming mutual interest",
    "Prepare a preliminary valuation range based on actual financials",
    "Draft a blind teaser for owner review before any market outreach begins",
    "Begin building the curated buyer list of 40–60 targets",
    "Discuss and sign an engagement letter",
]

DEFAULT_NEXT_STEPS_NURTURE = [
    "Thank the owner sincerely and leave the door open",
    "Send a brief follow-up email with one useful insight about their vertical's M&A market",
    "Add to a 6-month nurture cadence — quarterly market update or relevant transaction comp",
    "Ask if they'd be open to a no-obligation valuation estimate for future planning",
    "Note any specific objections or concerns for future reference",
]


# ---------------------------------------------------------------------------
# MeetingEngineV2
# ---------------------------------------------------------------------------

class MeetingEngineV2:
    """
    Renders the interactive meeting page v2 for a given company and meeting type.

    Parameters
    ----------
    supabase_client : object, optional
        A Supabase Python client (supabase-py). Pass None to use stub data only
        (useful for testing or when Supabase is unavailable).
    """

    def __init__(self, supabase_client=None):
        self.client = supabase_client
        self.env = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=select_autoescape(["html"]),
        )

    def render(
        self,
        company_id: str,
        meeting_date: str,
        meeting_type: MeetingType = "discovery",
    ) -> str:
        """
        Render the v2 meeting page HTML.

        Parameters
        ----------
        company_id : str
            Slug matching Supabase companies.company_id (e.g. "aquascience")
        meeting_date : str
            ISO date string (e.g. "2026-03-29")
        meeting_type : MeetingType
            One of: discovery, financial_review, engagement
        """
        company  = self._fetch_company(company_id)
        buyers   = self._fetch_buyers(company_id)
        prior    = self._fetch_prior_notes(company_id)
        meeting_id = f"{company_id}_{meeting_date}_{meeting_type}"
        context  = self._build_context(
            company, buyers, prior, meeting_id, meeting_date, meeting_type
        )
        template = self.env.get_template("meeting-page-v2.html")
        return template.render(**context)

    # -----------------------------------------------------------------------
    # Supabase fetchers (gracefully fall back to stubs)
    # -----------------------------------------------------------------------

    def _fetch_company(self, company_id: str) -> dict:
        if not self.client:
            return _stub_company(company_id)
        try:
            result = (
                self.client.table("companies")
                .select("*")
                .eq("company_id", company_id)
                .single()
                .execute()
            )
            return result.data or _stub_company(company_id)
        except Exception:
            return _stub_company(company_id)

    def _fetch_buyers(self, company_id: str) -> list[dict]:
        if not self.client:
            return []
        try:
            result = (
                self.client.table("buyers")
                .select("buyer_name, buyer_type, fit_score, status")
                .eq("company_id", company_id)
                .order("fit_score", desc=True)
                .limit(15)
                .execute()
            )
            return [
                {
                    "name":   r.get("buyer_name", "Unknown"),
                    "type":   r.get("buyer_type", "Strategic"),
                    "fit":    r.get("fit_score", 5),
                    "status": r.get("status", "new"),
                }
                for r in (result.data or [])
            ]
        except Exception:
            return []

    def _fetch_prior_notes(self, company_id: str) -> dict:
        """Return {field_name: field_value} from the most recent prior meeting."""
        if not self.client:
            return {}
        try:
            result = (
                self.client.table("meeting_notes")
                .select("field_name, field_value, captured_at")
                .like("meeting_id", company_id + "%")
                .order("captured_at", desc=True)
                .execute()
            )
            seen: dict[str, str] = {}
            for r in (result.data or []):
                fn = r["field_name"]
                if fn not in seen:
                    seen[fn] = r["field_value"]
            return seen
        except Exception:
            return {}

    # -----------------------------------------------------------------------
    # Context builder
    # -----------------------------------------------------------------------

    def _build_context(
        self,
        company: dict,
        buyers: list[dict],
        prior: dict,
        meeting_id: str,
        meeting_date: str,
        meeting_type: MeetingType,
    ) -> dict:
        owner_name  = company.get("owner_name") or company.get("contact_name") or "the owner"
        owner_first = owner_name.split()[0] if owner_name else "there"

        return {
            "meeting_id":          meeting_id,
            "generated_at":        date_type.today().strftime("%B %d, %Y"),
            "company": {
                "name":            company.get("company_name", _slug_to_name(company.get("company_id", ""))),
                "owner_name":      owner_name,
                "location":        company.get("location", ""),
                "vertical":        company.get("vertical", ""),
                "vertical_label":  company.get("vertical_label") or company.get("vertical", ""),
                "revenue":         company.get("revenue", ""),
                "employees":       company.get("employee_count", ""),
                "years":           company.get("years_in_business", ""),
            },
            "meeting": {
                "date":            meeting_date,
                "type":            meeting_type,
                "type_label":      MEETING_TYPE_LABELS[meeting_type],
                "owner_name":      owner_name,
                "owner_first_name":owner_first,
            },
            "opening_hook":        self._build_hook(company, prior, meeting_type),
            "agenda_items":        DEFAULT_AGENDA[meeting_type],
            "objectives":          DEFAULT_OBJECTIVES[meeting_type],
            "questions":           QUESTIONS[meeting_type],
            "talking_points":      DEFAULT_TALKING_POINTS,
            "danger_zones":        DEFAULT_DANGER_ZONES[meeting_type],
            "what_we_bring":       DEFAULT_WHAT_WE_BRING,
            "success_criteria":    DEFAULT_SUCCESS_CRITERIA[meeting_type],
            "next_steps_positive": DEFAULT_NEXT_STEPS_POSITIVE,
            "next_steps_nurture":  DEFAULT_NEXT_STEPS_NURTURE,
            "buyers":              buyers,
        }

    def _build_hook(self, company: dict, prior: dict, meeting_type: MeetingType) -> str:
        name  = company.get("company_name", "your company")
        owner = (company.get("owner_name") or "").split()[0] or "the owner"
        story = prior.get("story_elements", "")

        if story and len(story) > 20:
            return (
                f'"{owner}, what you\'ve built here is genuinely rare — '
                f'and I want to make sure the buyers we bring understand that story as well as we do."'
            )

        years    = company.get("years_in_business", "")
        revenue  = company.get("revenue", "")
        vertical = company.get("vertical_label") or company.get("vertical", "your industry")

        parts = [f'"{owner}, you\'ve built something that very few operators in {vertical} have managed']
        if years:
            parts.append(f" — {years} years")
        if revenue:
            parts.append(f" of growth to {revenue}")
        parts.append(
            " — and right now, the buyers who would value that most are actively competing for businesses like yours.\""
        )
        return "".join(parts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slug_to_name(company_id: str) -> str:
    return company_id.replace("-", " ").replace("_", " ").title()


def _stub_company(company_id: str) -> dict:
    return {
        "company_id":         company_id,
        "company_name":       _slug_to_name(company_id),
        "owner_name":         "the owner",
        "location":           "",
        "vertical":           "",
        "vertical_label":     "",
        "revenue":            "",
        "employee_count":     "",
        "years_in_business":  "",
    }
