"""Persistent, fingerprint-keyed file memory store.

Provides content-independent file identity via metadata fingerprints
(``"{original_name}|{size}"``) and a JSON-backed store that survives
across application restarts.  Used to track which files have been
processed by the LLM, what names were suggested, and what the user
decided.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# File identity
# ---------------------------------------------------------------------------


def compute_fingerprint(name: str, size: int) -> str:
    """Return a stable identity string derived from file metadata.

    Uses ``"{name}|{size}"`` — zero file I/O, just string formatting.
    macOS screenshot names encode second-precision timestamps with
    automatic dedup suffixes ``(2)``, ``(3)``, … so ``(name, size)`` is
    practically collision-free for a single-user desktop tool.
    """
    return f"{name}|{size}"


# ---------------------------------------------------------------------------
# Atomic write (shared with app.py)
# ---------------------------------------------------------------------------


def atomic_write(path: Path, content: str) -> None:
    """Write *content* to *path* atomically via temp-file + ``os.replace``.

    On crash the temp file is cleaned up; the original file is never
    left in a partial state.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w") as f:
            f.write(content)
        os.replace(tmp_path, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

#: Valid status values for a :class:`FileRecord`.
VALID_STATUSES = frozenset({"new", "suggested", "renamed", "ignored", "trashed"})


@dataclass
class FileRecord:
    """A single file's persistent memory entry."""

    fingerprint: str
    original_name: str
    last_known_name: str
    size: int
    extension: str
    status: str  # one of VALID_STATUSES
    suggested_name: str | None = None
    user_name: str | None = None
    first_seen: str = ""
    last_updated: str = ""
    meta: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in VALID_STATUSES:
            valid = ", ".join(sorted(VALID_STATUSES))
            raise ValueError(f"Invalid status {self.status!r}; expected one of {valid}")


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _parse_iso(dt_str: str) -> datetime:
    """Parse an ISO 8601 datetime string, returning epoch on failure."""
    try:
        return datetime.fromisoformat(dt_str)
    except (ValueError, TypeError):
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# MemoryStore
# ---------------------------------------------------------------------------


class MemoryStore:
    """Persistent, fingerprint-keyed file memory.

    On-disk format is a single JSON file::

        {
          "version": 1,
          "files": {
            "<fingerprint>": { ... FileRecord dict ... },
            ...
          }
        }

    All mutating operations are in-memory only until :meth:`save` is
    called.  Callers are responsible for calling ``save()`` after a
    batch of changes.
    """

    VERSION = 1

    def __init__(self, path: Path) -> None:
        self._path = path
        self._files: dict[str, FileRecord] = {}

    # ── Load / Save ──────────────────────────────────────────────

    def load(self) -> None:
        """Load memory from disk.  Resets to empty on corruption."""
        self._files.clear()
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Memory file corruption detected on load, resetting: %s", exc)
            return
        if not isinstance(raw, dict) or "files" not in raw:
            logger.warning("Memory file has unexpected structure, resetting")
            return
        if raw.get("version") != self.VERSION:
            logger.warning(
                "Memory file version mismatch (got %s, expected %s), resetting",
                raw.get("version"),
                self.VERSION,
            )
            return
        for fp, entry in raw["files"].items():
            if not isinstance(entry, dict):
                continue
            try:
                self._files[fp] = FileRecord(
                    fingerprint=fp,
                    original_name=entry.get("original_name", ""),
                    last_known_name=entry.get("last_known_name", ""),
                    size=entry.get("size", 0),
                    extension=entry.get("extension", ""),
                    status=entry.get("status", "new"),
                    suggested_name=entry.get("suggested_name"),
                    user_name=entry.get("user_name"),
                    first_seen=entry.get("first_seen", ""),
                    last_updated=entry.get("last_updated", ""),
                    meta=entry.get("meta", {}),
                )
            except (ValueError, TypeError) as exc:
                logger.warning("Skipping malformed memory entry %s: %s", fp, exc)

    def save(self) -> None:
        """Persist current state to disk atomically."""
        data = {
            "version": self.VERSION,
            "files": {fp: asdict(rec) for fp, rec in self._files.items()},
        }
        atomic_write(self._path, json.dumps(data, indent=2))

    # ── Queries ──────────────────────────────────────────────────

    def lookup(self, fingerprint: str) -> FileRecord | None:
        """Look up a record by its fingerprint."""
        return self._files.get(fingerprint)

    def lookup_by_name(self, filename: str) -> FileRecord | None:
        """Look up a record by its last-known or original filename.

        Scans all records since the primary key is the fingerprint.
        """
        for rec in self._files.values():
            if rec.last_known_name == filename or rec.original_name == filename:
                return rec
        return None

    def get_status(self, fingerprint: str) -> str | None:
        """Return the status for *fingerprint*, or ``None`` if unknown."""
        rec = self._files.get(fingerprint)
        return rec.status if rec else None

    def get_unprocessed(self, active_fingerprints: set[str]) -> list[FileRecord]:
        """Return records whose fingerprint is in *active_fingerprints* and
        whose status is ``"new"`` (not yet processed by the LLM).
        """
        return [
            self._files[fp]
            for fp in active_fingerprints
            if fp in self._files and self._files[fp].status == "new"
        ]

    def all_records(self) -> list[FileRecord]:
        """Return all stored records."""
        return list(self._files.values())

    @property
    def count(self) -> int:
        return len(self._files)

    # ── Mutations ────────────────────────────────────────────────

    def record_file(self, name: str, size: int) -> FileRecord:
        """Record a newly discovered file and return its record.

        If the fingerprint already exists the existing record is
        returned unchanged (idempotent).
        """
        fp = compute_fingerprint(name, size)
        existing = self._files.get(fp)
        if existing is not None:
            return existing

        now = _now_iso()
        rec = FileRecord(
            fingerprint=fp,
            original_name=name,
            last_known_name=name,
            size=size,
            extension=Path(name).suffix.lower(),
            status="new",
            first_seen=now,
            last_updated=now,
        )
        self._files[fp] = rec
        return rec

    def update_suggestion(self, fingerprint: str, suggested_name: str) -> None:
        """Set the LLM-suggested name for a file (status → ``suggested``)."""
        rec = self._files.get(fingerprint)
        if rec is None:
            raise KeyError(f"Unknown fingerprint: {fingerprint}")
        rec.suggested_name = suggested_name
        rec.status = "suggested"
        rec.last_updated = _now_iso()

    def accept_suggestion(self, fingerprint: str, user_name: str) -> None:
        """Accept the LLM suggestion (status → ``renamed``)."""
        rec = self._files.get(fingerprint)
        if rec is None:
            raise KeyError(f"Unknown fingerprint: {fingerprint}")
        rec.user_name = user_name
        rec.last_known_name = user_name
        rec.status = "renamed"
        rec.last_updated = _now_iso()
        rec.meta.pop("suggested_category", None)

    def reject_suggestion(self, fingerprint: str) -> None:
        """Reject / dismiss the LLM suggestion (status → ``ignored``)."""
        rec = self._files.get(fingerprint)
        if rec is None:
            raise KeyError(f"Unknown fingerprint: {fingerprint}")
        rec.status = "ignored"
        rec.last_updated = _now_iso()
        rec.meta.pop("suggested_category", None)

    def record_rename(self, fingerprint: str, new_name: str) -> None:
        """Record a user-initiated rename (status → ``renamed``).

        Updates ``last_known_name`` to reflect the new filename while
        leaving the fingerprint (which is keyed on the original name)
        unchanged.
        """
        rec = self._files.get(fingerprint)
        if rec is None:
            raise KeyError(f"Unknown fingerprint: {fingerprint}")
        rec.last_known_name = new_name
        rec.user_name = new_name
        rec.status = "renamed"
        rec.last_updated = _now_iso()
        rec.meta.pop("suggested_category", None)

    def mark_trashed(self, fingerprint: str) -> None:
        """Mark a file as trashed (status → ``trashed``)."""
        rec = self._files.get(fingerprint)
        if rec is None:
            raise KeyError(f"Unknown fingerprint: {fingerprint}")
        rec.status = "trashed"
        rec.last_updated = _now_iso()

    def remove(self, fingerprint: str) -> None:
        """Remove a record entirely."""
        self._files.pop(fingerprint, None)

    # ── Maintenance ──────────────────────────────────────────────

    def prune_stale(self, active_fingerprints: set[str], max_age_days: int = 90) -> int:
        """Remove records not in *active_fingerprints* and older than *max_age_days*.

        Records that are still within the age window are kept even if
        inactive (no longer on disk), preserving the ability to recognize
        recently trashed or renamed files if they reappear.

        Returns the number of pruned records.
        """
        now = datetime.now(tz=timezone.utc)
        to_prune: list[str] = []
        for fp, rec in self._files.items():
            if fp in active_fingerprints:
                continue
            updated = _parse_iso(rec.last_updated)
            if (now - updated).days > max_age_days:
                to_prune.append(fp)
        for fp in to_prune:
            del self._files[fp]
        return len(to_prune)
