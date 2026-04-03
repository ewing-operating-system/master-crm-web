"""
_config_bridge.py — Bridge to repo-level vertical config from backend/lib/.

Resolves the sys.path namespace collision between backend/lib/ and the
repo-level lib/ directory by using importlib.util to load the vertical
config schema module directly by file path.

Usage:
    from lib._config_bridge import DEFAULT_ENTITY, load_vertical

    # DEFAULT_ENTITY is loaded from the primary vertical config at import time.
    # Falls back to "next_chapter" if config is unavailable.
    entity = record.get("entity", DEFAULT_ENTITY)

    # load_vertical() returns a config dict for a given vertical.
    vcfg = load_vertical("home_services")
"""

import importlib.util
import os

# Compute repo root: backend/lib/_config_bridge.py → backend/lib/ → backend/ → repo root
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_VCFG_PATH = os.path.join(_REPO_ROOT, "lib", "config", "vertical_config_schema.py")

try:
    _spec = importlib.util.spec_from_file_location("vertical_config_schema", _VCFG_PATH)
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    load_vertical = _mod.load_vertical
    list_verticals = _mod.list_verticals
    load_all_verticals = _mod.load_all_verticals
    validate = _mod.validate
except Exception:
    load_vertical = None
    list_verticals = lambda: []
    load_all_verticals = lambda: {}
    validate = lambda cfg: ["Config module not available"]

# Default entity: read from the primary vertical config (home_services).
# This replaces 15+ hardcoded .get("entity", "next_chapter") fallbacks.
try:
    _primary_cfg = load_vertical("home_services") if load_vertical else None
    DEFAULT_ENTITY = _primary_cfg["entity_defaults"]["entity"] if _primary_cfg else "next_chapter"
except Exception:
    DEFAULT_ENTITY = "next_chapter"
