"""Optional Spotlight activity; never infer user activity from image reads or atime."""

import math
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

CAPTURE_WINDOW_SECONDS = 300
LAST_OPEN_AGE_SECONDS = 600
METADATA_TIMEOUT_SECONDS = 0.75
SCAN_METADATA_BUDGET_SECONDS = 3.0
METADATA_WORKERS = 4
CLEANUP_REASON = "Recorded open within 5m of capture; last recorded open over 10m ago."


@dataclass(frozen=True)
class UsageMetadata:
    created_at: datetime | None = None
    last_opened_at: datetime | None = None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_last_used(value: str) -> datetime | None:
    """mdls dates have second precision and an explicit UTC offset."""
    try:
        return datetime.strptime(value.strip().strip("\x00"), "%Y-%m-%d %H:%M:%S %z").astimezone(
            timezone.utc
        )
    except ValueError:
        return None


def _birth_time(path: Path) -> datetime | None:
    try:
        birth = getattr(path.stat(), "st_birthtime", None)
        if birth is None or not math.isfinite(birth):
            return None
        return datetime.fromtimestamp(birth, timezone.utc)
    except (OSError, ValueError, OverflowError):
        return None


def _read_file(path: Path, deadline: float) -> UsageMetadata:
    created = _birth_time(path)
    remaining = deadline - time.monotonic()
    if created is None or remaining <= 0:
        return UsageMetadata(created)
    try:
        result = subprocess.run(
            ["/usr/bin/mdls", "-raw", "-name", "kMDItemLastUsedDate", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=min(METADATA_TIMEOUT_SECONDS, remaining),
            check=False,
        )
        opened = parse_last_used(result.stdout) if result.returncode == 0 else None
        return UsageMetadata(created, opened)
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        return UsageMetadata(created)


def read_usage(paths: list[Path]) -> dict[Path, UsageMetadata]:
    """Fresh reads per scan, capped concurrency and total query time.

    Queued work after the budget expires has no activity signal. A broken
    Spotlight service must not delay manual sorting by one timeout per file.
    No persistent cache: a rescan observes any later recorded use.
    """
    if sys.platform != "darwin" or not paths:
        return {}
    deadline = time.monotonic() + SCAN_METADATA_BUDGET_SECONDS
    with ThreadPoolExecutor(max_workers=METADATA_WORKERS) as executor:
        records = executor.map(lambda path: _read_file(path, deadline), paths)
        return dict(zip(paths, records, strict=True))


def cleanup_result(usage: UsageMetadata, now: datetime, *, unsorted: bool = True) -> dict:
    """Evaluate the fixed rule against aware dates on a common time base.

    Birth time and mdls values in the same second cannot establish a separate
    open. Keep timing_match independent of a decision so an undo can restore
    an eligible card without another scan.
    """
    created, opened = usage.created_at, usage.last_opened_at
    result = {"eligible": False, "timing_match": False, "reason": None}
    if any(value is None or value.utcoffset() is None for value in (created, opened, now)):
        return result
    assert created is not None and opened is not None
    created = created.astimezone(timezone.utc)
    opened = opened.astimezone(timezone.utc)
    now = now.astimezone(timezone.utc)
    after_capture = (opened - created).total_seconds()
    age = (now - opened).total_seconds()
    if (
        created > now
        or opened > now
        or created.replace(microsecond=0) == opened.replace(microsecond=0)
        or not 0 < after_capture <= CAPTURE_WINDOW_SECONDS
        or age <= LAST_OPEN_AGE_SECONDS
    ):
        return result
    return {
        "eligible": unsorted,
        "timing_match": True,
        "reason": CLEANUP_REASON,
        "opened_after_capture_seconds": after_capture,
        "last_opened_ago_seconds": age,
    }


def usage_payload(usage: UsageMetadata) -> dict:
    return {
        "created_at": usage.created_at.isoformat() if usage.created_at else None,
        "last_opened_at": usage.last_opened_at.isoformat() if usage.last_opened_at else None,
    }
