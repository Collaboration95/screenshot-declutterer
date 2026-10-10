"""Cached local image signals and direct (never transitive) duplicate matches."""

from __future__ import annotations

import hashlib
import logging
import math
import os
import warnings
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, ImageStat

from ss_dcl.memory import FileRecord

logger = logging.getLogger(__name__)
SIGNAL_VERSION = 1
MAX_DISTANCE = 10
ASPECT_TOLERANCE_PERCENT = 3


@dataclass(frozen=True)
class Signals:
    byte_hash: str
    dhash: str | None = None
    width: int = 0
    height: int = 0
    rgb: str | None = None
    contrast: float = 0


def stat_key(st: os.stat_result) -> list[int]:
    """Also detect same-size edits, restored mtimes, and replaced files."""
    return [st.st_size, st.st_mtime_ns, st.st_ctime_ns, st.st_dev, st.st_ino]


def compute_signals(path: Path) -> Signals:
    digest = hashlib.blake2b(digest_size=16)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                image = ImageOps.exif_transpose(image)
                width, height = image.size
                # Composite transparency on white rather than comparing hidden RGB.
                rgba = image.convert("RGBA")
                rgb = Image.new("RGBA", image.size, "white")
                rgb.alpha_composite(rgba)
                rgb = rgb.convert("RGB")
                small = rgb.convert("L").resize((17, 16), Image.Resampling.LANCZOS)
                pixels = small.tobytes()
                value = 0
                for y in range(16):
                    for x in range(16):
                        value = (value << 1) | (pixels[y * 17 + x] > pixels[y * 17 + x + 1])
                color = rgb.resize((16, 16), Image.Resampling.LANCZOS)
                return Signals(
                    digest.hexdigest(),
                    f"{value:064x}",
                    width,
                    height,
                    color.tobytes().hex(),
                    ImageStat.Stat(small).stddev[0],
                )
    except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        # Identical bytes remain useful even if a preview cannot be decoded.
        return Signals(digest.hexdigest())


def cached_signals(path: Path, record: FileRecord) -> tuple[Signals | None, bool]:
    """Persist successful signals only after an unchanged before/after stat."""
    try:
        key = stat_key(path.stat())
        cached = record.meta.get("similarity")
        if (
            isinstance(cached, dict)
            and cached.get("version") == SIGNAL_VERSION
            and cached.get("stat") == key
        ):
            try:
                signals = Signals(**cached["signals"])
                if (
                    isinstance(signals.byte_hash, str)
                    and len(signals.byte_hash) == 32
                    and len(bytes.fromhex(signals.byte_hash)) == 16
                    and isinstance(signals.width, int)
                    and isinstance(signals.height, int)
                    and isinstance(signals.contrast, int | float)
                    and math.isfinite(signals.contrast)
                    and (signals.rgb is None or len(bytes.fromhex(signals.rgb)) == 768)
                    and (
                        signals.dhash is None
                        or (len(signals.dhash) == 64 and 0 <= int(signals.dhash, 16) < 2**256)
                    )
                ):
                    return signals, False
            except (KeyError, TypeError, ValueError):
                pass
        signals = compute_signals(path)
        if stat_key(path.stat()) != key:
            return None, False
        record.meta["similarity"] = {
            "version": SIGNAL_VERSION,
            "stat": key,
            "signals": asdict(signals),
        }
        return signals, True
    except OSError:
        logger.debug("File disappeared or became unreadable during similarity scan")
        return None, False


def near_distance(a: Signals, b: Signals) -> int | None:
    if not a.dhash or not b.dhash or min(a.width, a.height, b.width, b.height) <= 0:
        return None
    # Cross products keep the inclusive 3% boundary exact, in both directions.
    cross_a, cross_b = a.width * b.height, b.width * a.height
    if abs(cross_a - cross_b) * 100 > min(cross_a, cross_b) * ASPECT_TOLERANCE_PERCENT:
        return None
    hash_a, hash_b = int(a.dhash, 16), int(b.dhash, 16)
    # Suppress uniform/monotonic images in either gradient direction.
    if not (8 < hash_a.bit_count() < 248 and 8 < hash_b.bit_count() < 248):
        return None
    distance = (hash_a ^ hash_b).bit_count()
    if distance > MAX_DISTANCE or min(a.contrast, b.contrast) < 8 or not a.rgb or not b.rgb:
        return None
    colors_a, colors_b = bytes.fromhex(a.rgb), bytes.fromhex(b.rgb)
    differences = [abs(x - y) for x, y in zip(colors_a, colors_b, strict=True)]
    if sum(differences) / len(differences) > 12:
        return None
    # One changed region must not disappear inside a mostly unchanged window.
    for row in range(0, 16, 4):
        for col in range(0, 16, 4):
            region = [
                differences[(y * 16 + x) * 3 + channel]
                for y in range(row, row + 4)
                for x in range(col, col + 4)
                for channel in range(3)
            ]
            if sum(region) / len(region) > 30:
                return None
    return distance


def direct_matches(
    files: list[dict[str, Any]], signals: Sequence[Signals | None]
) -> list[list[dict[str, Any]]]:
    """Symmetric per-file neighbors, with exact matches taking precedence."""
    matches: list[list[dict[str, Any]]] = [[] for _ in files]
    for i, a in enumerate(signals):
        if a is None:
            continue
        for j in range(i + 1, len(files)):
            b = signals[j]
            if b is None:
                continue
            exact = files[i]["size"] == files[j]["size"] and a.byte_hash == b.byte_hash
            distance = None if exact else near_distance(a, b)
            if not exact and distance is None:
                continue
            for origin, peer in ((i, j), (j, i)):
                other = files[peer]
                matches[origin].append(
                    {
                        "source": other["source"],
                        "name": other["name"],
                        "kind": "identical" if exact else "similar",
                        "distance": 0 if exact else distance,
                    }
                )
    for neighbors in matches:
        neighbors.sort(key=lambda m: (m["kind"], m["distance"], m["source"], m["name"]))
    return matches
