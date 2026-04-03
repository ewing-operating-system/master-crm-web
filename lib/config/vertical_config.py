"""
vertical_config.py — Runtime config loader for verticals, shared keywords,
entity branding, and market multiples.

Provides cached access to all config-driven data that was previously hardcoded
in backend/lib/classification.py and other modules.

Usage:
    from lib.config.vertical_config import (
        load_all_verticals, load_shared_keywords, get_entity_keywords,
        get_all_entity_keyword_sets, get_market_multiples, get_entity_branding,
    )
"""

import json
import os
from functools import lru_cache

# ---------------------------------------------------------------------------
# Path resolution — same pattern as vertical_config_schema.py
# ---------------------------------------------------------------------------

_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
_VERTICALS_DIR = os.path.join(_CONFIG_DIR, "verticals")


# ---------------------------------------------------------------------------
# Core loaders (cached)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def load_all_verticals():
    """Load all vertical configs from lib/config/verticals/*.json.
    Returns {vertical_id: config_dict}."""
    result = {}
    if not os.path.isdir(_VERTICALS_DIR):
        return result
    for fname in sorted(os.listdir(_VERTICALS_DIR)):
        if fname.endswith(".json"):
            path = os.path.join(_VERTICALS_DIR, fname)
            with open(path) as f:
                cfg = json.load(f)
            vid = cfg.get("vertical_id", fname.replace(".json", ""))
            result[vid] = cfg
    return result


@lru_cache(maxsize=1)
def load_shared_keywords():
    """Load shared_keywords.json. Returns the full dict."""
    path = os.path.join(_CONFIG_DIR, "shared_keywords.json")
    with open(path) as f:
        return json.load(f)


@lru_cache(maxsize=1)
def get_entity_branding(entity=None):
    """Load entity_branding.json. If entity is given, return that entity's
    branding dict (falling back to _default). If None, return the full dict."""
    path = os.path.join(_CONFIG_DIR, "entity_branding.json")
    with open(path) as f:
        branding = json.load(f)
    if entity is None:
        return branding
    return branding.get(entity, branding.get("_default", {}))


def get_entity_keywords(entity):
    """Get classification keywords for a specific entity by merging all
    verticals that default to that entity.

    Returns a set of lowercase keyword strings."""
    keywords = set()
    for vid, cfg in load_all_verticals().items():
        if cfg.get("entity_defaults", {}).get("entity") == entity:
            ck = cfg.get("classification_keywords", {})
            for key in ("industry", "transaction", "company_names", "lp_keywords"):
                for kw in ck.get(key, []):
                    keywords.add(kw.lower())
    return keywords


@lru_cache(maxsize=1)
def get_all_entity_keyword_sets():
    """Build keyword sets for every entity that has at least one vertical config.

    Returns {entity_slug: set_of_keywords}."""
    entity_sets = {}
    for vid, cfg in load_all_verticals().items():
        entity = cfg.get("entity_defaults", {}).get("entity")
        if not entity:
            continue
        if entity not in entity_sets:
            entity_sets[entity] = set()
        ck = cfg.get("classification_keywords", {})
        for key in ("industry", "transaction", "company_names", "lp_keywords"):
            for kw in ck.get(key, []):
                entity_sets[entity].add(kw.lower())
    return entity_sets


def get_market_multiples(vertical, multiples_file=None):
    """Look up valuation_multiples for a vertical or sub-vertical label.

    Args:
        vertical: vertical_id (e.g. 'home_services') OR a sub-vertical label
                  (e.g. 'hvac', 'healthcare').
        multiples_file: optional path to a JSON file with {label: {floor, median, ceiling}}.

    Returns: dict with keys 'floor', 'median', 'ceiling' or None if not found.
    """
    # If a custom file is provided, use it
    if multiples_file:
        with open(multiples_file) as f:
            data = json.load(f)
        label = vertical.lower()
        return data.get(label, data.get("_default"))

    # Search all vertical configs for a matching valuation_multiples entry
    vertical_lower = vertical.lower()
    for vid, cfg in load_all_verticals().items():
        vm = cfg.get("valuation_multiples", {})
        if vertical_lower in {k.lower(): k for k in vm}:
            # Find the actual key (case-insensitive match)
            for key in vm:
                if key.lower() == vertical_lower:
                    return vm[key]

    # Check if vertical is a vertical_id itself — return its _default multiples
    all_v = load_all_verticals()
    if vertical_lower in all_v:
        vm = all_v[vertical_lower].get("valuation_multiples", {})
        return vm.get("_default")

    return None


def reload_configs():
    """Clear all caches so configs are re-read from disk.
    Useful after editing JSON files at runtime."""
    load_all_verticals.cache_clear()
    load_shared_keywords.cache_clear()
    get_entity_branding.cache_clear()
    get_all_entity_keyword_sets.cache_clear()
