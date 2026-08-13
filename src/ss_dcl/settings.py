"""App settings persistence and the prune-age cache.

LiteRT is the only LLM provider; the stored provider value is normalized
to ``"litert"`` on every read (legacy values from earlier phases).
"""

import json
import logging
from pathlib import Path
from typing import Any

from src.ss_dcl.memory import atomic_write

logger = logging.getLogger(__name__)

SETTINGS_FILE = Path.home() / ".ss-dcl" / "settings.json"
DEFAULT_LLM_MODEL = "gemma4-e2b"

# Valid range for prune_max_age_days (mirrors the settings UI min/max).
PRUNE_MIN_DAYS = 1
PRUNE_MAX_DAYS = 730

# ── Settings cache (prune age) ──────────────────────────────────────────────
_prune_max_age_cache: int | None = None


def reset_prune_cache() -> None:
    """Invalidate the cached prune age so the next read hits disk."""
    global _prune_max_age_cache
    _prune_max_age_cache = None


def _prune_max_age() -> int:
    global _prune_max_age_cache
    if _prune_max_age_cache is None:
        _prune_max_age_cache = _load_settings().get("prune_max_age_days", 90)
    # Global could be None in theory, but we just ensured it's set above
    age: int = _prune_max_age_cache  # type: ignore[assignment]
    return age


def _load_settings() -> dict[str, Any]:
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
        # LiteRT is the only provider; normalize any legacy/stale value.
        if data.get("llm_provider") != "litert":
            data["llm_provider"] = "litert"
        return data
    return {}


def _save_settings(settings: dict[str, Any]) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(SETTINGS_FILE, json.dumps(settings, indent=2))
