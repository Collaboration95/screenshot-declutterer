"""Deterministic, non-personal demo fixtures for UI documentation capture.

Generates a throwaway workspace that the app can be pointed at with two
environment variables:

    SS_DCL_DESKTOP=<workspace>/desktop    screenshots to scan
    SS_DCL_HOME=<workspace>/home          isolated runtime root (state, memory,
                                          settings, logs, thumbnails)

Nothing here reads the real Desktop or the real runtime state: every image is
drawn procedurally from a fixed seed, filenames and timestamps are fixed, and
state/memory/settings are written from the same catalogue. That is what makes
documentation screenshots safe to publish and captures repeatable.

Layout written under --root (default: .cache/ui-baseline-fixtures):

    desktop/                             scanning root (Desktop source)
    Reference/Screenshots/               one tracked-folder source
    home/.ss-dcl/state.json              keep/trash decisions
    home/.ss-dcl/memory.json             per-file status, suggestions, keywords
    home/.ss-dcl/settings.json           provider, prune age, tracked folders
    manifest.json                        slot -> file, state, and expectations

Usage:
    uv run python tools/demo_fixtures.py --root .cache/ui-baseline-fixtures --force
    uv run python tools/demo_fixtures.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _REPO_ROOT / "src"
if str(_SRC_DIR) not in sys.path:  # allow running the script without an install
    sys.path.insert(0, str(_SRC_DIR))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from ss_dcl.categorize import build_keyword_scores, suggest_category  # noqa: E402
from ss_dcl.memory import (  # noqa: E402
    VALID_STATUSES,
    MemoryStore,
    compute_source_fingerprint,
)
from ss_dcl.sources import decision_key  # noqa: E402

FIXTURE_VERSION = 1
#: Fixed seed: regenerating the workspace twice yields byte-identical images.
DEMO_SEED = 20260916
DEFAULT_ROOT = _REPO_ROOT / ".cache" / "ui-baseline-fixtures"
#: Port the capture tool asks Flask to bind (see tools/capture_ui_baseline.py).
DEFAULT_CAPTURE_PORT = 5311

DESKTOP_DIR = "desktop"
TRACKED_DIR = "Reference/Screenshots"
RUNTIME_DIR = "home"
STATE_DIR = ".ss-dcl"
#: Source id for the Desktop inbox (mirrors ss_dcl.sources.DEFAULT_SOURCE).
DESKTOP_SOURCE = "Desktop"

#: Fixed mtime origin so date sorting is stable across captures.
FIRST_MTIME = datetime(2026, 3, 1, 9, 0, 0, tzinfo=timezone.utc)
FIRST_SEEN = "2026-03-01T09:00:00+00:00"
LAST_UPDATED = "2026-03-10T02:15:00+00:00"
#: Point the app at a closed port to reproduce the LLM-offline state.
OFFLINE_LLM_URL = "http://127.0.0.1:1"

# ── Image rendering ──────────────────────────────────────────────────────────
# Flat, low-saturation mock windows. No text beyond a fixed vocabulary, no
# EXIF, no real content: thumbnails stay legible without being personal.

_PAGE_BG = "#e9e7dd"
_WINDOW_BG = "#ffffff"
_TITLE_BG = "#f3f2ed"
_SIDE_BG = "#f8f7f3"
_INK = "#1b1b19"
_HAIRLINE = "#d9d7cd"
_MUTED = "#b9b6ab"
_ACCENT_POOL = ("#2f6a5d", "#76508d", "#c95844", "#3f6d9e", "#8a6d3b", "#4d5f8a")
#: Window title per mock style: the caption should match what was drawn.
_WINDOW_TITLES = {
    "document": "Planning notes",
    "chart": "Charts",
    "code": "Terminal",
    "gallery": "Gallery",
    "table": "Spreadsheet",
    "email": "Inbox",
}


def _font(size: int) -> Any:
    """Return a font at *size*, falling back for Pillow without sized defaults."""
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1 exposes no sized built-in font
        return ImageFont.load_default()


def _bar(draw: Any, x: int, y: int, w: int, h: int, fill: str) -> None:
    """Draw a rounded horizontal bar (stand-in for a line of text)."""
    draw.rounded_rectangle((x, y, x + w, y + h), radius=max(2, min(h // 2, 8)), fill=fill)


def _content_box(width: int, height: int, margin: int, bar_h: int) -> tuple[int, int, int, int]:
    """Return the content area (right of the sidebar, below the title bar)."""
    x1 = margin
    y1 = margin + bar_h
    x2 = width - margin
    y2 = height - margin
    side = round((x2 - x1) * 0.18)
    return (
        x1 + side + round(bar_h * 0.5),
        y1 + round(bar_h * 0.6),
        x2 - round(bar_h * 0.5),
        y2 - round(bar_h * 0.5),
    )


def _draw_document(
    draw: Any, box: tuple[int, int, int, int], rng: random.Random, accent: str
) -> None:
    x1, y1, x2, _y2 = box
    width = x2 - x1
    line_h = max(6, round(width * 0.012))
    gap = line_h * 2
    _bar(draw, x1, y1, round(width * 0.45), line_h * 2, _INK)
    y = y1 + line_h * 4
    for _ in range(rng.randint(3, 5)):
        _bar(draw, x1, y, round(width * rng.uniform(0.6, 0.98)), line_h, _MUTED)
        y += gap
    y += gap
    draw.rounded_rectangle((x1, y, x1 + round(width * 0.08), y + line_h * 6), radius=4, fill=accent)
    for _ in range(3):
        _bar(
            draw,
            x1 + round(width * 0.12),
            y + line_h,
            round(width * rng.uniform(0.4, 0.7)),
            line_h,
            _MUTED,
        )
        y += gap


def _draw_chart(draw: Any, box: tuple[int, int, int, int], rng: random.Random, accent: str) -> None:
    x1, y1, x2, y2 = box
    width = x2 - x1
    height = y2 - y1
    _bar(draw, x1, y1, round(width * 0.35), max(6, round(width * 0.012)) * 2, _INK)
    base = y2 - round(height * 0.18)
    draw.line((x1, base, x2, base), fill=_HAIRLINE, width=3)
    count = rng.randint(5, 8)
    slot = round((width * 0.92) / count)
    for i in range(count):
        bar_h = round(height * rng.uniform(0.18, 0.62))
        color = accent if i % 3 else _MUTED
        draw.rounded_rectangle(
            (x1 + i * slot + slot // 4, base - bar_h, x1 + i * slot + slot * 3 // 4, base),
            radius=6,
            fill=color,
        )
    for i in range(3):
        draw.rounded_rectangle(
            (
                x1 + i * slot,
                y1 + round(height * 0.08),
                x1 + i * slot + slot // 3,
                y1 + round(height * 0.08) + 10,
            ),
            radius=4,
            fill=_MUTED,
        )


def _draw_code(draw: Any, box: tuple[int, int, int, int], rng: random.Random, accent: str) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle((x1, y1, x2, y2), radius=10, fill="#22231f")
    width = x2 - x1
    line_h = max(6, round((y2 - y1) * 0.035))
    y = y1 + line_h * 2
    while y < y2 - line_h * 2:
        indent = round(width * rng.choice((0.04, 0.08, 0.12)))
        length = round(width * rng.uniform(0.25, 0.7))
        color = accent if rng.random() < 0.3 else "#6f7266"
        _bar(draw, x1 + indent, y, length, line_h, color)
        y += line_h * 2


def _draw_gallery(
    draw: Any, box: tuple[int, int, int, int], rng: random.Random, accent: str
) -> None:
    x1, y1, x2, y2 = box
    cols, rows = 3, 2
    gap = round((x2 - x1) * 0.02)
    tile_w = ((x2 - x1) - gap * (cols - 1)) // cols
    tile_h = ((y2 - y1) - gap * (rows - 1)) // rows
    for row in range(rows):
        for col in range(cols):
            tx = x1 + col * (tile_w + gap)
            ty = y1 + row * (tile_h + gap)
            fill = accent if (row + col) % 4 == 0 else _SIDE_BG
            draw.rounded_rectangle((tx, ty, tx + tile_w, ty + tile_h), radius=12, fill=fill)
            _bar(
                draw,
                tx + gap,
                ty + tile_h - gap - 8,
                round(tile_w * rng.uniform(0.35, 0.7)),
                8,
                _MUTED,
            )


def _draw_table(draw: Any, box: tuple[int, int, int, int], rng: random.Random, accent: str) -> None:
    x1, y1, x2, y2 = box
    width = x2 - x1
    row_h = max(12, round((y2 - y1) * 0.11))
    cols = 4
    for row in range(min(6, (y2 - y1) // row_h)):
        top = y1 + row * row_h
        if row == 0:
            draw.rounded_rectangle((x1, top, x2, top + row_h - 4), radius=8, fill=accent)
        else:
            if row % 2 == 0:
                draw.rectangle((x1, top, x2, top + row_h - 4), fill=_SIDE_BG)
            for col in range(cols):
                cell_x = x1 + round(width * col / cols) + 12
                _bar(
                    draw,
                    cell_x,
                    top + row_h // 2 - 4,
                    round(width / cols * rng.uniform(0.35, 0.7)),
                    8,
                    _MUTED if row else _WINDOW_BG,
                )


def _draw_email(draw: Any, box: tuple[int, int, int, int], rng: random.Random, accent: str) -> None:
    x1, y1, x2, _y2 = box
    width = x2 - x1
    line_h = max(6, round(width * 0.011))
    _bar(draw, x1, y1, round(width * 0.5), line_h * 2, _INK)
    y = y1 + line_h * 4
    draw.ellipse((x1, y, x1 + line_h * 5, y + line_h * 5), fill=accent)
    _bar(draw, x1 + line_h * 7, y, round(width * 0.25), line_h, _MUTED)
    y += line_h * 8
    for _ in range(rng.randint(4, 6)):
        _bar(draw, x1, y, round(width * rng.uniform(0.5, 0.95)), line_h, _MUTED)
        y += line_h * 2
    chip_w = round(width * 0.18)
    y += line_h * 2
    for i in range(2):
        draw.rounded_rectangle(
            (x1 + i * (chip_w + 12), y, x1 + i * (chip_w + 12) + chip_w, y + line_h * 7),
            radius=8,
            fill=_SIDE_BG,
        )


_DRAWERS = {
    "document": _draw_document,
    "chart": _draw_chart,
    "code": _draw_code,
    "gallery": _draw_gallery,
    "table": _draw_table,
    "email": _draw_email,
}


def render_demo_image(
    path: Path, *, style: str, seed: int, index: int, width: int = 1600, height: int = 1000
) -> None:
    """Draw one deterministic mock screenshot and write it to *path*."""
    rng = random.Random(seed * 1000 + index)
    image = Image.new("RGB", (width, height), _PAGE_BG)
    draw = ImageDraw.Draw(image)
    margin = round(min(width, height) * 0.05)
    bar_h = round(height * 0.05)
    x1, y1, x2, y2 = margin, margin, width - margin, height - margin
    radius = 20

    draw.rounded_rectangle((x1, y1, x2, y2), radius=radius, fill=_WINDOW_BG)
    draw.rounded_rectangle((x1, y1, x2, y1 + bar_h + radius), radius=radius, fill=_TITLE_BG)
    draw.rectangle((x1 + 1, y1 + bar_h, x2 - 1, y1 + bar_h + radius), fill=_TITLE_BG)

    top = y1 + bar_h + radius
    side_w = round((x2 - x1) * 0.18)
    draw.rectangle((x1, top, x1 + side_w, y2), fill=_SIDE_BG)
    row_h = round((y2 - top) * 0.08)
    for row in range(5):
        row_y = top + round(row_h * (0.8 + row * 1.1))
        _bar(draw, x1 + 18, row_y, side_w - 36 - (0 if row % 3 else 40), 10, _MUTED)

    accent = rng.choice(_ACCENT_POOL)
    _DRAWERS[style](draw, _content_box(width, height, margin, bar_h), rng, accent)

    draw.rounded_rectangle((x1, y1, x2, y2), radius=radius, outline=_HAIRLINE, width=2)
    draw.line((x1 + 1, top - radius, x2 - 1, top - radius), fill=_HAIRLINE, width=2)

    dot_r = max(4, round(bar_h * 0.13))
    for i in range(3):
        cx = x1 + round(bar_h * 0.6) + i * dot_r * 3
        cy = y1 + bar_h // 2
        draw.ellipse(
            (cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r), fill=_HAIRLINE if i else accent
        )
    draw.text(
        (x1 + round(bar_h * 2.6), y1 + bar_h // 2),
        _WINDOW_TITLES.get(style, "Screenshot"),
        font=_font(round(bar_h * 0.42)),
        fill=_INK,
        anchor="lm",
    )

    if path.suffix.lower() in (".jpg", ".jpeg"):
        image.save(path, format="JPEG", quality=88, optimize=True)
    else:
        image.save(path, format="PNG", optimize=True)


# ── Catalogue ────────────────────────────────────────────────────────────────
# One entry per card. "decision" picks the Kanban column (None -> Unsorted) and
# "keywords" are the per-file keywords the app derives from an accepted
# suggestion. The category hint is never stored here: /api/screenshots scores
# these keywords against the keep/trash decisions below, so the fixture
# reproduces the real derivation instead of hard-coding its result.


@dataclass(frozen=True)
class DemoFile:
    """A single demo screenshot plus the UI state it is meant to reproduce."""

    slot: int
    name: str
    style: str
    inbox: str = "desktop"  # "desktop" | "tracked"
    decision: str | None = None  # "keep" | "trash" | None (Unsorted)
    status: str = "new"  # one of ss_dcl.memory.VALID_STATUSES
    suggested_name: str | None = None
    keywords: tuple[str, ...] = ()


#: Layered on purpose: several cards show more than one state at a time (an
#: undecided file that carries both a suggestion badge and a keep hint, a
#: tracked-folder file that is already decided, and so on).
CATALOGUE: tuple[DemoFile, ...] = (
    # Unsorted, untouched: scanned, never decided, no hint, no suggestion.
    DemoFile(1, "Screenshot 2026-02-14 at 10.22.31.png", "document"),
    DemoFile(2, "Screenshot 2026-02-14 at 11.05.47.png", "chart"),
    DemoFile(3, "Screenshot 2026-02-15 at 09.41.12.png", "code"),
    DemoFile(4, "Screenshot 2026-02-15 at 16.30.05.png", "email"),
    # A JPEG, so multi-format handling shows up in the baseline too.
    DemoFile(5, "Screenshot 2026-02-16 at 08.12.44.jpg", "gallery"),
    DemoFile(6, "Screenshot 2026-02-16 at 19.58.20.png", "table"),
    # Kept: this decision history is also the keyword evidence for the hints.
    DemoFile(
        7,
        "Screenshot 2026-02-17 at 09.03.11.png",
        "chart",
        decision="keep",
        keywords=("dashboard", "metrics"),
    ),
    DemoFile(
        8,
        "Screenshot 2026-02-17 at 14.27.56.png",
        "document",
        decision="keep",
        keywords=("dashboard", "metrics", "release"),
    ),
    DemoFile(
        9,
        "Screenshot 2026-02-18 at 10.15.39.png",
        "table",
        decision="keep",
        keywords=("dashboard", "quarterly"),
    ),
    # Trashed: parked in the Trash column, waiting for Done.
    DemoFile(
        10,
        "Screenshot 2026-02-18 at 21.44.02.png",
        "gallery",
        decision="trash",
        keywords=("meme", "wallpaper"),
    ),
    DemoFile(
        11,
        "Screenshot 2026-02-19 at 08.55.18.png",
        "gallery",
        decision="trash",
        keywords=("meme", "wallpaper", "funny"),
    ),
    # Category hints: undecided, but their keywords overlap decided files.
    DemoFile(
        12,
        "Screenshot 2026-02-19 at 13.07.41.png",
        "document",
        keywords=("dashboard", "metrics", "planning"),
    ),
    DemoFile(
        13,
        "Screenshot 2026-02-20 at 09.12.03.png",
        "email",
        keywords=("dashboard", "review"),
    ),
    DemoFile(
        14,
        "Screenshot 2026-02-20 at 15.48.29.png",
        "gallery",
        keywords=("meme", "wallpaper"),
    ),
    DemoFile(
        15,
        "Screenshot 2026-02-21 at 11.33.50.png",
        "gallery",
        keywords=("meme", "funny"),
    ),
    # Suggested names: a suggestion is waiting for accept/dismiss.
    DemoFile(
        16,
        "Screenshot 2026-02-22 at 09.20.14.png",
        "code",
        status="suggested",
        suggested_name="inbox-zero-checklist.png",
    ),
    DemoFile(
        17,
        "Screenshot 2026-02-22 at 17.02.36.png",
        "chart",
        status="suggested",
        suggested_name="release-dashboard-timeline.png",
        keywords=("dashboard",),
    ),
    # Tracked-folder source: same board, different inbox, "in: Screenshots" tag.
    DemoFile(18, "Screenshot 2026-03-02 at 10.11.26.png", "document", inbox="tracked"),
    DemoFile(
        19,
        "Screenshot 2026-03-02 at 15.42.08.png",
        "chart",
        inbox="tracked",
        decision="keep",
        keywords=("dashboard", "metrics"),
    ),
    DemoFile(
        20,
        "Screenshot 2026-03-03 at 09.30.55.png",
        "code",
        inbox="tracked",
        decision="trash",
        keywords=("meme", "wallpaper"),
    ),
)

#: States Phase 0 requires the fixture to make reproducible without a live LLM.
REQUIRED_STATES: tuple[str, ...] = (
    "unsorted",
    "kept",
    "trashed",
    "suggested-name",
    "category-hint-keep",
    "category-hint-trash",
    "multi-select",
    "llm-offline",
    "tracked-folder-source",
)


def _tracked_source(root: Path) -> str:
    """Canonical tracked-folder path, used verbatim as the source id."""
    return str((root / TRACKED_DIR).resolve())


def _source_for(entry: DemoFile, root: Path) -> str:
    return DESKTOP_SOURCE if entry.inbox == "desktop" else _tracked_source(root)


def _file_path(entry: DemoFile, root: Path) -> Path:
    base = root / (DESKTOP_DIR if entry.inbox == "desktop" else TRACKED_DIR)
    return base / entry.name


def _mtime_for(slot: int) -> float:
    """Fixed mtime: one hour per slot, so date sorting is stable everywhere."""
    return (FIRST_MTIME + timedelta(hours=slot)).timestamp()


def _validate_catalogue(catalogue: tuple[DemoFile, ...]) -> None:
    """Fail loudly on a catalogue mistake rather than writing a broken fixture."""
    slots: set[int] = set()
    names: set[tuple[str, str]] = set()
    extensions = (".png", ".jpg", ".jpeg", ".tiff", ".bmp")
    for entry in catalogue:
        if entry.slot in slots:
            raise ValueError(f"duplicate slot {entry.slot}")
        slots.add(entry.slot)
        if entry.style not in _DRAWERS:
            raise ValueError(f"unknown style {entry.style!r} for {entry.name}")
        if entry.inbox not in ("desktop", "tracked"):
            raise ValueError(f"unknown inbox {entry.inbox!r} for {entry.name}")
        if entry.decision not in (None, "keep", "trash"):
            raise ValueError(f"unknown decision {entry.decision!r} for {entry.name}")
        if entry.status not in VALID_STATUSES:
            raise ValueError(f"unknown status {entry.status!r} for {entry.name}")
        if entry.status == "suggested" and not entry.suggested_name:
            raise ValueError(f"{entry.name}: suggested status needs a suggested_name")
        if not entry.name.startswith("Screenshot"):
            raise ValueError(f"{entry.name}: must match the Desktop scan glob Screenshot*.*")
        if Path(entry.name).name != entry.name:
            raise ValueError(f"{entry.name}: must be a bare filename")
        if Path(entry.name).suffix.lower() not in extensions:
            raise ValueError(f"{entry.name}: unsupported extension")
        key = (entry.inbox, entry.name)
        if key in names:
            raise ValueError(f"duplicate entry {entry.name} in {entry.inbox}")
        names.add(key)


def _compute_expectations(memory_path: Path, decisions: dict[str, str]) -> dict[str, str | None]:
    """Recompute suggested_category exactly the way /api/screenshots does."""
    store = MemoryStore(memory_path)
    store.load()
    scores = build_keyword_scores(store, decisions)
    expected: dict[str, str | None] = {}
    for record in store.all_records():
        keywords = record.meta.get("keywords") or []
        expected[record.fingerprint] = (
            suggest_category(keywords, store, decisions, scores) if keywords else None
        )
    return expected


def _coverage(files: list[dict[str, Any]]) -> dict[str, int]:
    """Count how many fixture files demonstrate each required UI state."""

    def count(predicate: Callable[[dict[str, Any]], bool]) -> int:
        return sum(1 for entry in files if predicate(entry))

    return {
        "unsorted": count(lambda f: f["column"] == "unsorted"),
        "kept": count(lambda f: f["column"] == "keep"),
        "trashed": count(lambda f: f["column"] == "trash"),
        "suggested-name": count(lambda f: f["status"] == "suggested"),
        "category-hint-keep": count(lambda f: f["expected_category"] == "keep"),
        "category-hint-trash": count(lambda f: f["expected_category"] == "trash"),
        # Multi-select needs two or more selectable cards; any two will do.
        "multi-select": count(lambda f: f["column"] == "unsorted"),
        # The offline LLM comes from the env block (closed port), not a file.
        "llm-offline": 1,
        "tracked-folder-source": count(lambda f: f["inbox"] == "tracked"),
    }


def write_workspace(root: Path, *, force: bool = False, seed: int = DEMO_SEED) -> dict[str, Any]:
    """Generate the demo workspace under *root* and return its manifest."""
    _validate_catalogue(CATALOGUE)
    root = Path(root).expanduser()
    if root.exists() and any(root.iterdir()):
        if not force:
            raise FileExistsError(f"{root} is not empty -- pass --force to replace it")
        shutil.rmtree(root)

    desktop = root / DESKTOP_DIR
    tracked = root / TRACKED_DIR
    state_dir = root / RUNTIME_DIR / STATE_DIR
    for directory in (desktop, tracked, state_dir):
        directory.mkdir(parents=True, exist_ok=True)

    memory_files: dict[str, Any] = {}
    decisions: dict[str, str] = {}
    files: list[dict[str, Any]] = []
    for entry in CATALOGUE:
        path = _file_path(entry, root)
        render_demo_image(path, style=entry.style, seed=seed, index=entry.slot)
        mtime = _mtime_for(entry.slot)
        os.utime(path, (mtime, mtime))
        source = _source_for(entry, root)
        size = path.stat().st_size
        fingerprint = compute_source_fingerprint(source, entry.name, size)
        memory_files[fingerprint] = {
            "fingerprint": fingerprint,
            "original_name": entry.name,
            "last_known_name": entry.name,
            "size": size,
            "extension": Path(entry.name).suffix.lower(),
            "status": entry.status,
            "suggested_name": entry.suggested_name,
            "user_name": None,
            "first_seen": FIRST_SEEN,
            "last_updated": LAST_UPDATED,
            "meta": {"source": source, "keywords": list(entry.keywords)},
        }
        if entry.decision is not None:
            decisions[decision_key(source, entry.name)] = entry.decision
        files.append(
            {
                "slot": entry.slot,
                "name": entry.name,
                "inbox": entry.inbox,
                "source": source,
                "relative_path": str(path.relative_to(root)),
                "style": entry.style,
                "fingerprint": fingerprint,
                "size": size,
                "status": entry.status,
                "suggested_name": entry.suggested_name,
                "keywords": list(entry.keywords),
                "decision": entry.decision,
                "column": entry.decision or "unsorted",
                "mtime": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
            }
        )

    memory_path = state_dir / "memory.json"
    memory_path.write_text(json.dumps({"version": 2, "files": memory_files}, indent=2) + "\n")
    (state_dir / "state.json").write_text(json.dumps({"decisions": decisions}, indent=2) + "\n")
    # auto_suggest stays off: captures should show a quiet board, and the
    # offline-LLM states come from LITERT_BASE_URL pointing at a closed port.
    settings = {
        "llm_provider": "litert",
        "llm_model": "gemma4-e2b",
        "auto_suggest": False,
        "prune_max_age_days": 90,
        "tracked_folders": [_tracked_source(root)],
    }
    (state_dir / "settings.json").write_text(json.dumps(settings, indent=2) + "\n")

    expected = _compute_expectations(memory_path, decisions)
    for record in files:
        record["expected_category"] = expected.get(record["fingerprint"])

    manifest: dict[str, Any] = {
        "fixture_version": FIXTURE_VERSION,
        "seed": seed,
        "root": str(root),
        "desktop": str(desktop),
        "tracked_folder": str(tracked),
        "runtime_home": str(root / RUNTIME_DIR),
        "state_dir": str(state_dir),
        "env": {
            "SS_DCL_DESKTOP": str(desktop.resolve()),
            "SS_DCL_HOME": str((root / RUNTIME_DIR).resolve()),
            "LITERT_BASE_URL": OFFLINE_LLM_URL,
            "SS_DCL_PORT": str(DEFAULT_CAPTURE_PORT),
        },
        "counts": {
            "total": len(files),
            "desktop": sum(1 for entry in files if entry["inbox"] == "desktop"),
            "tracked": sum(1 for entry in files if entry["inbox"] == "tracked"),
        },
        "coverage": _coverage(files),
        "files": files,
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def load_manifest(root: Path) -> dict[str, Any]:
    """Read the manifest written by write_workspace."""
    path = Path(root).expanduser() / "manifest.json"
    return json.loads(path.read_text())


def verify_workspace(root: Path) -> list[str]:
    """Return the problems with an existing workspace; empty means sane."""
    root = Path(root).expanduser()
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        return [f"no manifest at {manifest_path} -- generate the fixture first"]
    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as exc:
        return [f"manifest is not valid JSON: {exc}"]

    problems: list[str] = []
    if manifest.get("fixture_version") != FIXTURE_VERSION:
        problems.append(
            f"fixture_version {manifest.get('fixture_version')} != {FIXTURE_VERSION}, regenerate"
        )
    files = manifest.get("files") or []
    if not files:
        problems.append("manifest lists no files")
        return problems

    state_dir = root / RUNTIME_DIR / STATE_DIR
    for name in ("memory.json", "state.json", "settings.json"):
        if not (state_dir / name).exists():
            problems.append(f"missing {RUNTIME_DIR}/{STATE_DIR}/{name}")

    decisions: dict[str, str] = {}
    state_path = state_dir / "state.json"
    if state_path.exists():
        try:
            decisions = json.loads(state_path.read_text()).get("decisions", {}) or {}
        except json.JSONDecodeError as exc:
            problems.append(f"state.json is not valid JSON: {exc}")

    expected: dict[str, str | None] = {}
    memory_path = state_dir / "memory.json"
    if memory_path.exists():
        try:
            expected = _compute_expectations(memory_path, decisions)
        except Exception as exc:  # pragma: no cover - only on a corrupted fixture
            problems.append(f"memory.json could not be read: {exc}")

    for record in files:
        path = root / record["relative_path"]
        if not path.is_file():
            problems.append(f"missing image {record['relative_path']}")
            continue
        size = path.stat().st_size
        if size != record["size"]:
            problems.append(f"{record['name']}: size {size} != recorded {record['size']}")
        if record["fingerprint"] not in expected:
            problems.append(f"{record['name']}: no memory record for {record['fingerprint']}")
        elif expected[record["fingerprint"]] != record["expected_category"]:
            problems.append(
                f"{record['name']}: category {expected[record['fingerprint']]!r} != "
                f"manifest {record['expected_category']!r}"
            )

    coverage = _coverage(files)
    if coverage != manifest.get("coverage"):
        problems.append("manifest coverage does not match its file list")
    for state in REQUIRED_STATES:
        if coverage.get(state, 0) < 1:
            problems.append(f"state not reproducible: {state}")
    return problems


def _describe(manifest: dict[str, Any]) -> str:
    counts = manifest["counts"]
    lines = [
        f"fixture v{manifest['fixture_version']} (seed {manifest['seed']}) at {manifest['root']}",
        f"  {counts['total']} images ({counts['desktop']} desktop, {counts['tracked']} tracked)",
    ]
    lines.extend(f"  {state:<24}{manifest['coverage'][state]}" for state in REQUIRED_STATES)
    lines.append("  env " + " ".join(f"{k}={v}" for k, v in manifest["env"].items()))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate (or verify) the deterministic, non-personal demo workspace used for "
            "UI documentation and visual baselines. Never reads the real Desktop."
        )
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="workspace root")
    parser.add_argument("--force", action="store_true", help="replace an existing root")
    parser.add_argument("--seed", type=int, default=DEMO_SEED, help="image rendering seed")
    parser.add_argument("--json", action="store_true", help="print the manifest as JSON")
    parser.add_argument("--verify", action="store_true", help="check an existing workspace")
    args = parser.parse_args(argv)

    if args.verify:
        problems = verify_workspace(args.root)
        for problem in problems:
            print(f"FAIL {problem}", file=sys.stderr)
        if not problems:
            print(f"OK {args.root}: all {len(REQUIRED_STATES)} required states reproducible")
        return 1 if problems else 0

    try:
        manifest = write_workspace(args.root, force=args.force, seed=args.seed)
    except FileExistsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(manifest, indent=2))
    else:
        print(_describe(manifest))
        print("\nCapture with: uv run python tools/capture_ui_baseline.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
