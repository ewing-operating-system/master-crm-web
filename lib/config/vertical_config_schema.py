"""
vertical_config_schema.py — Canonical schema for per-vertical configuration.

Every vertical config file (lib/config/verticals/*.json) MUST conform to this
schema.  The schema is the single source of truth for what a vertical needs to
be fully operational in the pipeline: research, classification, letters,
proposals, and scoring.

Usage:
    from lib.config.vertical_config_schema import SCHEMA, validate, load_vertical

    cfg = load_vertical("home_services")        # loads lib/config/verticals/home_services.json
    errors = validate(cfg)                       # [] if valid
"""

import json
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Schema definition
# ---------------------------------------------------------------------------

SCHEMA = {
    # ── Identity ──────────────────────────────────────────────────────────
    "vertical_id": {
        "type": "string",
        "required": True,
        "description": (
            "Unique slug used everywhere: Supabase columns, URL paths, config "
            "keys.  Must match the filename (e.g. home_services.json → "
            "'home_services')."
        ),
    },
    "display_name": {
        "type": "string",
        "required": True,
        "description": "Human-readable name shown in UI, letters, and reports.",
    },

    # ── Entity defaults ───────────────────────────────────────────────────
    # Replaces the 15+ `.get('entity', 'next_chapter')` fallbacks found in
    # the inventory (why_sell_engine, letter_integration, transcript_processor,
    # server.py, listener/agent.py, research_templates).
    "entity_defaults": {
        "type": "object",
        "required": True,
        "description": (
            "Default entity routing for this vertical. When a record has this "
            "vertical but no explicit entity, these values apply."
        ),
        "properties": {
            "entity": {
                "type": "string",
                "required": True,
                "description": "Default entity slug (e.g. 'next_chapter').",
            },
            "sub_type": {
                "type": "string",
                "required": False,
                "description": "Default sub-type (e.g. 'sell_side').",
            },
            "campaign_prefixes": {
                "type": "array",
                "items": "string",
                "required": False,
                "description": (
                    "Campaign-ID prefixes that resolve to this vertical's "
                    "default entity (e.g. ['NC'])."
                ),
            },
        },
    },

    # ── Classification keywords ───────────────────────────────────────────
    # Single source of truth — replaces NEXT_CHAPTER_KEYWORDS (classification.py)
    # and tradesKeywords (classify_all_targets.js).
    "classification_keywords": {
        "type": "object",
        "required": True,
        "description": (
            "Keyword sets used by the classification engine.  Replaces the "
            "duplicated Python sets and JS arrays."
        ),
        "properties": {
            "industry": {
                "type": "array",
                "items": "string",
                "required": True,
                "description": "Industry terms that signal this vertical.",
            },
            "transaction": {
                "type": "array",
                "items": "string",
                "required": False,
                "description": "Transaction-intent terms specific to this vertical.",
            },
            "company_names": {
                "type": "array",
                "items": "string",
                "required": False,
                "description": "Known company names in this vertical's orbit.",
            },
        },
    },

    # ── Research sections ─────────────────────────────────────────────────
    "research_sections": {
        "type": "array",
        "items": "string",
        "required": True,
        "description": (
            "Ordered list of research section IDs to run for this vertical. "
            "Each section ID maps to a goal string the researcher agent uses. "
            "Shared sections (owner_story, revenue_signal, exit_readiness) can "
            "be reused across verticals; vertical-specific ones are unique."
        ),
    },

    # ── Exa search templates ──────────────────────────────────────────────
    "exa_templates": {
        "type": "object",
        "required": True,
        "description": "Exa API search configuration for this vertical.",
        "properties": {
            "base_queries": {
                "type": "array",
                "items": "string",
                "required": True,
                "description": (
                    "Query templates with {placeholder} variables: "
                    "{company_name}, {city}, {state}, {owner_name}, "
                    "{vertical}, {contact_name}, {years_in_business}."
                ),
            },
            "vertical_queries": {
                "type": "array",
                "items": "string",
                "required": True,
                "description": (
                    "Additional vertical-specific query templates. "
                    "Appended to base_queries at runtime."
                ),
            },
            "content_mode": {
                "type": "string",
                "required": True,
                "description": "'highlights' or 'text'. Exa API response format.",
            },
            "num_results": {
                "type": "integer",
                "required": True,
                "description": "Number of Exa results per query.",
            },
        },
    },

    # ── Synthesis prompts ─────────────────────────────────────────────────
    "synthesis_prompts": {
        "type": "object",
        "required": True,
        "description": (
            "LLM prompt components used during research synthesis — turning "
            "raw Exa results into structured dossiers and narratives."
        ),
        "properties": {
            "research_goals": {
                "type": "array",
                "items": "string",
                "required": True,
                "description": (
                    "What the researcher should extract. Each string is a goal "
                    "statement (e.g. 'Owner story: years in business, how they "
                    "started, family involvement')."
                ),
            },
            "additional_goals": {
                "type": "array",
                "items": "string",
                "required": False,
                "description": "Vertical-specific research goals appended to base goals.",
            },
            "story_hooks": {
                "type": "array",
                "items": "string",
                "required": True,
                "description": (
                    "Narrative angles for letter generation. Templates with "
                    "{placeholders}. Used by get_story_hooks()."
                ),
            },
            "market_context": {
                "type": "string",
                "required": True,
                "description": (
                    "Paragraph describing the current M&A landscape for this "
                    "vertical. Used in letters and proposals."
                ),
            },
            "buyer_appetite": {
                "type": "string",
                "required": True,
                "description": (
                    "Paragraph naming active acquirers and what they are paying. "
                    "Used in letters and proposals."
                ),
            },
            "premium_driver": {
                "type": "string",
                "required": True,
                "description": (
                    "Paragraph explaining what separates a top-of-range outcome "
                    "from a floor outcome. Used in letters."
                ),
            },
        },
    },

    # ── Buyer scoring criteria ────────────────────────────────────────────
    "buyer_scoring_criteria": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "criterion": {
                    "type": "string",
                    "description": "What is being evaluated.",
                },
                "weight": {
                    "type": "number",
                    "description": "Relative weight (0.0–1.0). All weights should sum to 1.0.",
                },
                "score_8_description": {
                    "type": "string",
                    "description": "What qualifies as HIGH (score 8).",
                },
                "score_6_description": {
                    "type": "string",
                    "description": "What qualifies as MEDIUM (score 6).",
                },
                "score_4_description": {
                    "type": "string",
                    "description": "What qualifies as LOW (score 4).",
                },
            },
        },
        "required": True,
        "description": (
            "Criteria and weights for scoring buyers. Implements the 8/6/4 "
            "scoring system from CLAUDE.md."
        ),
    },

    # ── Valuation fields ──────────────────────────────────────────────────
    # Replaces VERTICAL_DATA (letter_engine.py), VERTICAL_MULTIPLES
    # (letter_integration.py), EBITDA defaults (proposal_engine.py),
    # and the JS mirrors (generate.js, letter-template.js).
    "valuation_fields": {
        "type": "object",
        "required": True,
        "description": (
            "Financial benchmarks for this vertical. Single source of truth "
            "replacing 5 duplicate definitions."
        ),
        "properties": {
            "primary_metric": {
                "type": "string",
                "required": True,
                "description": (
                    "Valuation metric used (e.g. 'ebitda', 'arr', 'revenue'). "
                    "Home services uses EBITDA; SaaS would use ARR."
                ),
            },
            "multiple_floor": {
                "type": "number",
                "required": True,
                "description": "Low end of the multiple range.",
            },
            "multiple_ceiling": {
                "type": "number",
                "required": True,
                "description": "High end of the multiple range.",
            },
            "multiple_median": {
                "type": "number",
                "required": True,
                "description": "Typical/median multiple.",
            },
            "industry_margin_benchmark": {
                "type": "number",
                "required": False,
                "description": (
                    "Industry-standard margin (e.g. 0.22 for home services). "
                    "Used in proposal-auto-generator."
                ),
            },
        },
    },

    # ── Growth levers ─────────────────────────────────────────────────────
    "growth_levers": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "lever": {
                    "type": "string",
                    "description": "Short name of the lever.",
                },
                "description": {
                    "type": "string",
                    "description": "Why this lever increases enterprise value in this vertical.",
                },
            },
        },
        "required": True,
        "description": (
            "Domain-specific levers of growth — what makes companies in THIS "
            "vertical more valuable. Replaces VERTICAL_DATA.top_levers."
        ),
    },

    # ── Letter config ─────────────────────────────────────────────────────
    "letter_config": {
        "type": "object",
        "required": True,
        "description": "Vertical-specific letter generation parameters.",
        "properties": {
            "variants": {
                "type": "array",
                "items": "string",
                "required": True,
                "description": "Supported letter variants (e.g. ['initial', 'followup', 'final']).",
            },
            "certifications_to_mention": {
                "type": "array",
                "items": "string",
                "required": False,
                "description": "Industry certifications to reference in letters.",
            },
            "fee_structure": {
                "type": "object",
                "required": False,
                "description": "Engagement fee, retainer, and success fee ranges.",
                "properties": {
                    "engagement_fee_range": {"type": "string"},
                    "monthly_retainer_range": {"type": "string"},
                    "success_fee_description": {"type": "string"},
                },
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate(config: dict) -> list[str]:
    """
    Validate a vertical config dict against the schema.

    Returns a list of error strings. Empty list = valid.
    """
    errors = []

    for field_name, field_def in SCHEMA.items():
        if field_def.get("required") and field_name not in config:
            errors.append(f"Missing required field: {field_name}")
            continue

        if field_name not in config:
            continue

        value = config[field_name]
        expected_type = field_def["type"]

        if expected_type == "string" and not isinstance(value, str):
            errors.append(f"{field_name}: expected string, got {type(value).__name__}")
        elif expected_type == "number" and not isinstance(value, (int, float)):
            errors.append(f"{field_name}: expected number, got {type(value).__name__}")
        elif expected_type == "integer" and not isinstance(value, int):
            errors.append(f"{field_name}: expected integer, got {type(value).__name__}")
        elif expected_type == "array" and not isinstance(value, list):
            errors.append(f"{field_name}: expected array, got {type(value).__name__}")
        elif expected_type == "object" and not isinstance(value, dict):
            errors.append(f"{field_name}: expected object, got {type(value).__name__}")

        # Recurse into object properties
        if expected_type == "object" and isinstance(value, dict) and "properties" in field_def:
            for prop_name, prop_def in field_def["properties"].items():
                if prop_def.get("required") and prop_name not in value:
                    errors.append(f"{field_name}.{prop_name}: missing required property")

    # Verify vertical_id matches no spaces / special chars
    vid = config.get("vertical_id", "")
    if vid and not vid.replace("_", "").isalnum():
        errors.append(f"vertical_id '{vid}' must be alphanumeric + underscores only")

    return errors


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

_CONFIG_DIR = Path(__file__).resolve().parent / "verticals"


def load_vertical(vertical_id: str) -> dict:
    """
    Load and validate a vertical config file.

    Args:
        vertical_id: slug matching the filename (e.g. 'home_services')

    Returns:
        Parsed config dict.

    Raises:
        FileNotFoundError: if config file doesn't exist.
        ValueError: if config fails validation.
    """
    path = _CONFIG_DIR / f"{vertical_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"No config for vertical '{vertical_id}' at {path}")

    with open(path) as f:
        config = json.load(f)

    errors = validate(config)
    if errors:
        raise ValueError(f"Vertical config '{vertical_id}' has {len(errors)} error(s):\n" +
                         "\n".join(f"  - {e}" for e in errors))

    return config


def list_verticals() -> list[str]:
    """Return sorted list of available vertical IDs."""
    if not _CONFIG_DIR.exists():
        return []
    return sorted(p.stem for p in _CONFIG_DIR.glob("*.json"))


def load_all_verticals() -> dict[str, dict]:
    """Load all vertical configs. Returns {vertical_id: config}."""
    return {vid: load_vertical(vid) for vid in list_verticals()}
