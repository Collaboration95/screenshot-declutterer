"""Source handling for tracking folders feature.

Owns:
- DEFAULT_SOURCE constant
- path normalization and realpath de-duplication
- validation of tracked folder lists
- source-aware file path resolution
- decision key helpers
- thumbnail directory helpers
- JXA folder picker adapter
"""

from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_SOURCE = "Desktop"
TRACKED_FOLDERS_MAX = 10

# JXA script to show NSOpenPanel for directory selection.
# Uses AppKit via JavaScript for Automation (JXA).
JXA_PICK_SCRIPT = """
ObjC.import('AppKit');
var panel = $.NSOpenPanel.openPanel;
panel.setCanChooseFiles(false);
panel.setCanChooseDirectories(true);
panel.setAllowsMultipleSelection(false);
panel.setResolvesAliases(true);
panel.setCanCreateDirectories(false);
var resp = panel.runModal();
if (resp == $.NSModalResponseOK) {
    var urls = panel.URLs;
    if (urls.count == 0) {
        $.NSFileHandle.fileHandleWithStandardOutput.writeData($.NSString.alloc.initWithString("").dataUsingEncoding($.NSUTF8StringEncoding));
    } else {
        var url = urls.objectAtIndex(0);
        var p = url.path;
        // Coerce JSString to NSString for write
        var s = $.NSString.stringWithString(p);
        $.NSFileHandle.fileHandleWithStandardOutput.writeData(s.dataUsingEncoding($.NSUTF8StringEncoding));
    }
} else {
    // Cancel -> no output (empty)
}
""".strip()


def canonical_path(raw: str) -> Path:
    """Return canonical absolute Path for *raw* (expanduser + resolve)."""
    return Path(raw).expanduser().resolve()


def _is_subpath(child: Path, parent: Path) -> bool:
    """True if *child* is inside *parent* (or is parent itself if same)."""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _enc(s: str) -> str:
    """Encode `|` so `|` can be used as an unambiguous delimiter."""
    return s.replace("|", "%7C")


def _dec(s: str) -> str:
    """Decode the encoding applied by `_enc`."""
    return s.replace("%7C", "|")


def sanitize_source_dir(source: str) -> str:
    """Return a collision-proof directory name for *source*.

    Uses a truncated sha256 hash of the canonical path to guarantee
    uniqueness; the hash is deterministic and filesystem-safe.
    """
    # Use first 16 hex chars (64 bits) — more than enough
    h = hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]
    return h


def thumb_path_for_source(thumb_base: Path, source: str, filename: str) -> Path:
    """Return thumbnail path for a given source and filename."""
    if source == DEFAULT_SOURCE:
        return thumb_base / filename
    # collision-proof subdirectory
    subdir = sanitize_source_dir(source)
    return thumb_base / subdir / filename


def decision_key(source: str, name: str) -> str:
    """Return canonical decision key for source+name.

    Desktop stays as bare filename for backward compatibility (existing
    tests and state files use bare keys). Tracked folders use
    ``source|name`` to guarantee uniqueness, with ``|`` encoded
    so valid paths/names containing ``|`` cannot collide. Parsing handles
    both bare and ``Desktop|name`` forms for forward compatibility.
    """
    if source == DEFAULT_SOURCE:
        # Encode `|` in Desktop names so a name containing `|` does not
        # look like a tracked key; bare names without `|` remain unchanged.
        if "|" in name:
            return _enc(name)
        return name
    return f"{_enc(source)}|{_enc(name)}"


def parse_decision_key(key: str) -> tuple[str, str]:
    """Parse a decision key into (source, name). Legacy keys without '|' map to Desktop."""
    if key.startswith(f"{DEFAULT_SOURCE}|"):
        return (DEFAULT_SOURCE, _dec(key[len(DEFAULT_SOURCE) + 1 :]))
    if "|" not in key:
        # No delimiter: Desktop key. Decode if it was encoded (`%7C`).
        if "%7C" in key:
            return (DEFAULT_SOURCE, _dec(key))
        return (DEFAULT_SOURCE, key)
    # Split on first '|' — source part is encoded, so a literal `|` inside
    # the original source/name cannot appear as a delimiter.
    source_enc, name_enc = key.split("|", 1)
    source = _dec(source_enc)
    name = _dec(name_enc)
    if not source:
        return (DEFAULT_SOURCE, key)
    # If source is not an absolute path and not Desktop, treat as Desktop legacy
    # This handles rare case where bare filename contains '|' (unlikely for screenshots)
    if source != DEFAULT_SOURCE and not source.startswith("/"):
        # Ambiguous: treat as Desktop bare key containing '|'
        return (DEFAULT_SOURCE, _dec(key) if "%7C" in key else key)
    return (source, name)


def legacy_fingerprint_to_source(fingerprint: str) -> str:
    """Extract source from a fingerprint string (legacy fallback)."""
    # Legacy fingerprints are "name|size" — no source
    # Source-aware are "source|name|size" — three parts with encoded components
    parts = fingerprint.split("|")
    if len(parts) >= 3:
        # Encoded source does not contain `|` (it is %7C), so split is unambiguous
        return _dec(parts[0])
    return DEFAULT_SOURCE


def compute_source_fingerprint(source: str, name: str, size: int) -> str:
    """Compute source-aware fingerprint. Desktop stays legacy 'name|size'."""
    if source == DEFAULT_SOURCE:
        # Encode `|` in the name so the `|` before size remains unambiguous
        return f"{_enc(name)}|{size}"
    # For non-Desktop, use source prefix to guarantee uniqueness, encoded
    return f"{_enc(source)}|{_enc(name)}|{size}"


def resolve_source_root(source: str, desktop: Path, tracked_folders: list[str]) -> Path | None:
    """Resolve *source* to its trusted root Path, or None if not allowed."""
    if source == DEFAULT_SOURCE:
        return desktop
    # Compare canonical forms: source must be exactly one of tracked_folders (canonical)
    # Use canonical equality (resolve)
    try:
        canon_source = canonical_path(source)
    except Exception:
        return None
    for tf in tracked_folders:
        try:
            canon_tf = canonical_path(tf)
        except Exception:
            continue
        if canon_source == canon_tf:
            # Return the original path object but resolved for security
            return canon_tf
    return None


def validate_file_path(
    source: str, filename: str, desktop: Path, tracked_folders: list[str]
) -> Path | None:
    """Validate (source, filename) and return resolved absolute Path, or None.

    Two-layer guard:
    1. Bare name check (no separators)
    2. Resolved path must be inside the source's root (is_relative_to)
    """
    if filename != Path(filename).name:
        return None
    root = resolve_source_root(source, desktop, tracked_folders)
    if root is None:
        return None
    try:
        candidate = (root / filename).resolve()
        if not candidate.is_relative_to(root.resolve()):
            return None
    except Exception:
        return None
    # Reject symlink escapes already handled by is_relative_to after resolve
    return candidate


def get_all_sources(desktop: Path, tracked_folders: list[str]) -> list[tuple[str, Path]]:
    """Return ordered list of (source_id, root_path) including Desktop first."""
    sources: list[tuple[str, Path]] = [(DEFAULT_SOURCE, desktop)]
    for tf in tracked_folders:
        # Validate existence will be handled at scan time; here just normalize
        # Keep original string as source id (canonical absolute)
        try:
            # Normalize to canonical string for consistency
            canon = str(canonical_path(tf))
        except Exception:
            canon = tf
        # Avoid duplicate of Desktop
        try:
            if canonical_path(canon) == desktop.resolve():
                continue
        except Exception:
            pass
        # Deduplicate exact canonical duplicates already handled by validation
        sources.append((canon, Path(canon)))
    return sources


def validate_tracked_folders(
    proposed: list,
    desktop: Path,
    current_persisted: list[str] | None = None,
) -> tuple[list[str] | None, str | None]:
    """Validate the complete proposed tracked_folders list atomically.

    Returns (normalized_list, error_message). On success, normalized_list is a
    list of canonical absolute path strings (resolved). On failure, normalized_list is None
    and error_message contains a user-friendly string.
    Validation is ordered per spec:
    1. Absolute path and existing directory (for newly added paths)
    2. Desktop itself rejected
    3. Already tracked (duplicate canonical)
    4. Inside an already-tracked folder (nested)
    5. Hard cap 10
    Existing persisted entries that have gone missing are preserved (not rejected).
    """
    if current_persisted is None:
        current_persisted = []

    if not isinstance(proposed, list):
        return None, "tracked_folders must be a list"

    # Type check each entry
    for entry in proposed:
        if not isinstance(entry, str):
            return None, "Each tracked folder must be a string"

    if len(proposed) > TRACKED_FOLDERS_MAX:
        return None, f"Too many tracked folders: maximum is {TRACKED_FOLDERS_MAX}"

    # Build canonical sets for comparison
    try:
        desktop_canon = desktop.resolve()
    except Exception:
        desktop_canon = desktop

    # For preserved missing: canonical of current persisted
    import contextlib as _ctx

    persisted_canonicals: set[Path] = set()
    for p in current_persisted:
        with _ctx.suppress(Exception):
            persisted_canonicals.add(canonical_path(p))

    # Track seen canonicals within proposed to detect duplicates
    seen_canonicals: dict[Path, str] = {}
    normalized: list[str] = []

    for raw in proposed:
        # Expanduser before is_absolute check
        expanded = Path(raw).expanduser()
        if not expanded.is_absolute():
            return None, f"Folder must be an absolute path: {raw}"

        # Canonical for dedup and nested checks (resolve without strict)
        try:
            canon = Path(raw).expanduser().resolve()
        except Exception as exc:
            return None, f"Invalid path {raw}: {exc}"

        canon_str = str(canon)

        # Rule 1: existing directory — allow if already persisted and now missing
        if not canon.is_dir() and canon not in persisted_canonicals:
            return None, f"Folder does not exist: {raw}"

        # Rule 2: Desktop itself rejected
        try:
            if canon == desktop_canon or (
                canon.is_relative_to(desktop_canon) and canon == desktop_canon
            ):
                return None, "Desktop is already the default"
            # Exact equality with desktopc anon
            if canon == desktop_canon:
                return None, "Desktop is already the default"
        except Exception:
            pass
        if canon == desktop_canon:
            return None, "Desktop is already the default"

        # Rule 3: Already tracked (duplicate canonical)
        if canon in seen_canonicals:
            return None, f"That folder is already tracked: {raw}"
        # Also check if duplicate of earlier normalized? Already via seen
        seen_canonicals[canon] = canon_str

        # Rule 4: Inside an already-tracked folder (nested)
        # Check against all other seen entries (previous in list)
        for other_canon in seen_canonicals:
            if other_canon == canon:
                continue
            # If canon is inside other_canon
            try:
                if canon.is_relative_to(other_canon):
                    return None, f"Rejected: inside {other_canon}"
                # Also handle reverse: earlier entry inside new parent
                if other_canon.is_relative_to(canon):
                    return (
                        None,
                        f"Rejected: inside {canon} (contains {other_canon})",
                    )
            except Exception:
                # Fallback string prefix check
                if str(canon).startswith(str(other_canon) + os.sep):
                    return None, f"Rejected: inside {other_canon}"
                if str(other_canon).startswith(str(canon) + os.sep):
                    return None, f"Rejected: inside {canon}"

        normalized.append(canon_str)

    # Desktop inside check: tracked folder inside Desktop is not
    # considered nested (Desktop is not tracked). Allow it — scanning
    # is non-recursive so ~/Desktop/SomeFolder would not be found anyway.
    return normalized, None


def pick_folder_via_panel() -> tuple[str | None, str | None]:
    """Invoke native NSOpenPanel to pick a folder.

    Returns (path, error). On cancel: (None, None). On success: (path_str, None).
    On failure: (None, error_message).
    """
    if sys.platform != "darwin":
        return None, "Folder picker is only available on macOS."

    try:
        result = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", JXA_PICK_SCRIPT],
            capture_output=True,
            text=True,
            timeout=60,
            shell=False,
        )
    except FileNotFoundError:
        return None, "osascript not found — folder picker unavailable."
    except subprocess.TimeoutExpired:
        return None, "Folder picker timed out."
    except OSError as exc:
        return None, f"Folder picker failed: {exc}"

    if result.returncode != 0:
        err = (result.stderr or "").strip() or f"osascript failed with code {result.returncode}"
        logger.warning("Pick folder failed: %s", err)
        return None, f"Folder picker failed: {err}"

    out = (result.stdout or "").strip()
    # Strip possible trailing newlines/carriage returns
    # JXA may emit with newline; also handle quoted output?
    if not out:
        # Cancel or empty selection
        return None, None
    # Output should be an absolute path
    # Validate it's absolute (defense)
    if not Path(out).is_absolute():
        logger.warning("Pick folder returned non-absolute path: %r", out)
        return None, f"Folder picker returned invalid path: {out}"
    return out, None
