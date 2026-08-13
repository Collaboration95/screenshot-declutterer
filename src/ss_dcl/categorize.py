"""Auto-categorization: turn LLM-suggested filenames into keep/trash hints
using the user's past decisions and keyword overlap."""

from pathlib import Path

from src.ss_dcl.memory import MemoryStore


def extract_keywords(suggested_name: str) -> list[str]:
    """Extract keywords from a kebab-case filename stem.

    >>> extract_keywords("customer-onboarding-discussion.png")
    ['customer', 'onboarding', 'discussion']
    """
    stem = Path(suggested_name).stem
    return [w.lower() for w in stem.split("-") if len(w) > 2]


def suggest_category(
    keywords: list[str],
    memory: MemoryStore,
    decisions: dict[str, str],
) -> str | None:
    """Return 'keep', 'trash', or None based on the user's past decisions."""
    kw = set(keywords)
    keep_score = 0
    trash_score = 0

    for filename, decision in decisions.items():
        if decision not in ("keep", "trash"):
            continue
        rec = memory.lookup_by_name(filename)
        if rec is None:
            continue
        overlap = len(kw & set(rec.meta.get("keywords", [])))
        if decision == "keep":
            keep_score += overlap
        else:
            trash_score += overlap

    if keep_score > trash_score:
        return "keep"
    if trash_score > keep_score:
        return "trash"
    return None
