"""Thumbnail generation: size parsing, worker pool, and the generator itself."""

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)


def _parse_thumb_size(raw: str) -> tuple[int, int]:
    try:
        parts = raw.split("x")
        return (int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return (400, 300)


THUMB_SIZE: tuple[int, int] = _parse_thumb_size(os.environ.get("THUMB_SIZE", "400x300"))

_THUMB_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="thumb")


def _generate_thumbnail(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as img:
        img.thumbnail(THUMB_SIZE)
        img.save(dst, "PNG")
