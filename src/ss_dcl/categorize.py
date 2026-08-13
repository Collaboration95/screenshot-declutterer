"""Auto-categorization: turn LLM-suggested filenames into keep/trash hints
using the user's past decisions and keyword overlap."""

from pathlib import Path

from ss_dcl.memory import MemoryStore


def extract_keywords(suggested_name: str) -> list[str]:
    """Extract keywords from a kebab-case filename stem.

    >>> extract_keywords("customer-onboarding-discussion.png")
    ['customer', 'onboarding', 'discussion']
    """
    stem = Path(suggested_name).stem
    return [w.lower() for w in stem.split("-") if len(w) > 2]


def build_keyword_scores(
    memory: MemoryStore,
    decisions: dict[str, str],
) -> dict[str, tuple[int, int]]:
    """Accumulate per-keyword keep/trash scores from the user's past decisions.

    Returns ``{keyword: (keep_score, trash_score)}``. Built once per request
    instead of re-scanning every decision for every file (issue #79 —
    turns ``suggest_category`` into an O(keywords) lookup per file).
    """
    scores: dict[str, tuple[int, int]] = {}
    for filename, decision in decisions.items():
        if decision not in ("keep", "trash"):
            continue
        rec = memory.lookup_by_name(filename)
        if rec is None:
            continue
        for kw in set(rec.meta.get("keywords", [])):
            keep, trash = scores.get(kw, (0, 0))
            if decision == "keep":
                scores[kw] = (keep + 1, trash)
            else:
                scores[kw] = (keep, trash + 1)
    return scores


def suggest_category(
    keywords: list[str],
    memory: MemoryStore,
    decisions: dict[str, str],
    keyword_scores: dict[str, tuple[int, int]] | None = None,
) -> str | None:
    """Return 'keep', 'trash', or None based on the user's past decisions.

    *keyword_scores* may be precomputed with :func:`build_keyword_scores`
    (per request); when omitted it is derived on the fly for the given
    *decisions* — same results, slower.
    """
    if keyword_scores is None:
        keyword_scores = build_keyword_scores(memory, decisions)
    keep_score = 0
    trash_score = 0

    for kw in set(keywords):
        keep, trash = keyword_scores.get(kw, (0, 0))
        keep_score += keep
        trash_score += trash

    if keep_score > trash_score:
        return "keep"
    if trash_score > keep_score:
        return "trash"
    return None
