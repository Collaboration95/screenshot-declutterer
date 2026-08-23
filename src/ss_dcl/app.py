import contextlib
import importlib.metadata
import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    make_response,
    render_template,
    request,
    send_file,
)
from send2trash import send2trash
from werkzeug.serving import WSGIRequestHandler

from ss_dcl import categorize, llm, server, settings, thumbs
from ss_dcl.logging_config import configure_logging, new_request_id, request_id_var
from ss_dcl.memory import MemoryStore, atomic_write, compute_source_fingerprint
from ss_dcl.sources import (
    DEFAULT_SOURCE,
    decision_key,
    get_all_sources,
    pick_folder_via_panel,
    resolve_source_root,
    thumb_path_for_source,
    validate_file_path,
    validate_tracked_folders,
)

configure_logging()
# Named loggers (not __name__: app.py runs as __main__ when launched directly,
# which would hide every route behind an anonymous "__main__" label). Split by
# subsystem so a log line is attributable at a glance:
#   ss_dcl.http   — request middleware ACCESS lines
#   ss_dcl.files  — Desktop scan/refresh, pruning, thumbnails
#   ss_dcl.llm    — LLM suggest/accept/reject + /api/llm/* routes
#   ss_dcl.app    — lifecycle, trash, rename, state, reveal
logger = logging.getLogger("ss_dcl.app")
http_logger = logging.getLogger("ss_dcl.http")
files_logger = logging.getLogger("ss_dcl.files")
llm_logger = logging.getLogger("ss_dcl.llm")


def _resource_root() -> Path:
    """Directory holding ``templates/`` and ``static/``.

    Running from source (``src/ss_dcl/app.py``) this is the repo root;
    installed as a wheel (``site-packages/ss_dcl/app.py``) it is the
    ``site-packages`` root where hatchling's ``force-include`` places the
    assets.
    """
    pkg_dir = Path(__file__).resolve().parent
    for base in (pkg_dir.parent.parent, pkg_dir.parent):
        if (base / "templates").is_dir() and (base / "static").is_dir():
            return base
    return pkg_dir.parent.parent


_HERE = _resource_root()
app = Flask(__name__, template_folder=str(_HERE / "templates"), static_folder=str(_HERE / "static"))
# Local tool: never let the browser serve stale static assets. Flask's default
# 12h SEND_FILE_MAX_AGE_DEFAULT caused a broken UI after frontend changes — the
# browser ran old JS/CSS against new HTML (issue: settings dropdown dead).
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


@app.before_request
def _set_request_id():
    request.environ["_ss_dcl_start"] = time.perf_counter()
    request_id_var.set(new_request_id())


@app.after_request
def _log_request(response: Response) -> Response:
    request_id = request_id_var.get() or "-"
    response.headers["X-Request-ID"] = request_id
    start = request.environ.get("_ss_dcl_start", time.perf_counter())
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    path = request.path
    if request.query_string:
        path = f"{path}?{request.query_string.decode()}"
    http_logger.info(
        "ACCESS %s %s -> %s (%sms)",
        request.method,
        path,
        response.status_code,
        duration_ms,
    )
    request_id_var.set("")
    return response


@app.after_request
def set_security_headers(response: Response) -> Response:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self'; "
        "style-src 'self'; "
        "script-src 'self'; "
        "connect-src 'self'"
    )
    return response


DESKTOP = Path(os.environ.get("SS_DCL_DESKTOP", str(Path.home() / "Desktop")))
# Cache dir is keyed by thumbnail size so a THUMB_SIZE change gets a fresh
# cache instead of reusing old-resolution thumbs (mtime-based staleness check
# would otherwise keep serving them).
_thumb_size_key = f"{thumbs.THUMB_SIZE[0]}x{thumbs.THUMB_SIZE[1]}"
THUMB_DIR = Path.home() / ".cache" / "ss-dcl" / "thumbs" / _thumb_size_key
STATE_FILE = Path.home() / ".ss-dcl" / "state.json"
MEMORY_FILE = Path.home() / ".ss-dcl" / "memory.json"
IS_MACOS = sys.platform == "darwin"
# TODO Need to check if rendering changes for .tiff or .bmp needs to be handled seperately
SUPPORTED_IMAGE_EXTENSION = (".png", ".jpg", ".jpeg", ".tiff", ".bmp")

SORT_OPTIONS = {
    "name": ("name", False),
    "name_desc": ("name", True),
    "date": ("mtime", False),
    "date_desc": ("mtime", True),
}


_memory_store: MemoryStore | None = None
_memory_lock = threading.Lock()


def _get_memory() -> MemoryStore:
    global _memory_store
    with _memory_lock:
        if _memory_store is None:
            MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            _memory_store = MemoryStore(MEMORY_FILE)
            _memory_store.load()
    return _memory_store


def _reset_memory() -> None:
    global _memory_store
    with _memory_lock:
        _memory_store = None
    settings.reset_prune_cache()


_dirs_initialized = False


@app.before_request
def _init_dirs():
    global _dirs_initialized
    if not _dirs_initialized:
        THUMB_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _dirs_initialized = True


def _get_tracked_folders() -> list[str]:
    """Return current tracked folders (canonical strings)."""
    return settings._get_tracked_folders()


def _get_all_sources() -> list[tuple[str, Path]]:
    """Return ordered list of (source_id, root_path) including Desktop."""
    desktop = DESKTOP
    tracked = _get_tracked_folders()
    # Use sources helper for canonicalization and deduplication
    return get_all_sources(desktop, tracked)


def _thumb_path(source: str, filename: str) -> Path:
    """Return thumbnail path for a given source."""
    return thumb_path_for_source(THUMB_DIR, source, filename)


def _resolve_source_file(source: str, filename: str) -> Path | None:
    """Resolve source+filename to an absolute path with two-layer guard."""
    tracked = _get_tracked_folders()
    return validate_file_path(source, filename, DESKTOP, tracked)


def _scan_source(
    root: Path,
    source: str,
    memory,
    decisions,
    keyword_scores,
    files,
    active_fps,
    any_new_flag,
):
    """Scan a single source root and append to *files* list."""
    if not root.is_dir():
        files_logger.warning("Tracked folder not found or not a directory, skipping: %s", root)
        return any_new_flag
    for p in root.glob("Screenshot*.*"):
        if not p.is_file() or (p.suffix.lower() not in SUPPORTED_IMAGE_EXTENSION):
            continue
        name = p.name
        st = p.stat()
        size = st.st_size
        fp = compute_source_fingerprint(source, name, size)
        existing = memory.lookup(fp)
        # Fallback: after a rename the fingerprint changes (new name + same size),
        # so try lookup_by_name which scans last_known_name / original_name.
        if existing is None:
            existing = memory.lookup_by_name(name, source=source)
            # For Desktop, also try legacy bare lookup (pre-source records)
            if existing is None and source == DEFAULT_SOURCE:
                existing = memory.lookup_by_name(name)
        if existing is not None:
            memory_status = existing.status
            active_fps.add(existing.fingerprint)
        else:
            rec = memory.record_file(name, size, source=source)
            memory_status = "new"
            active_fps.add(rec.fingerprint)
            any_new_flag = True
            existing = rec
        suggested_name = existing.suggested_name if existing else None
        # Recompute suggested_category from keywords + current decisions
        # (refreshes hints as user history accumulates)
        if existing and existing.meta.get("keywords"):
            suggested_category = categorize.suggest_category(
                existing.meta["keywords"], memory, decisions, keyword_scores
            )
            if suggested_category != existing.meta.get("suggested_category"):
                existing.meta["suggested_category"] = suggested_category
        else:
            suggested_category = existing.meta.get("suggested_category") if existing else None
        files.append(
            {
                "name": name,
                "source": source,
                "size": size,
                "mtime": st.st_mtime,
                "fingerprint": fp,
                "memory_status": memory_status,
                "suggested_name": suggested_name,
                "suggested_category": suggested_category,
            }
        )
    return any_new_flag


def get_screenshots(sort: str = "name") -> list[dict[str, Any]]:
    memory = _get_memory()
    files: list[dict[str, Any]] = []
    any_new = False
    active_fps: set[str] = set()
    decisions = _read_decisions()
    # Per-request accumulator: one pass over decisions instead of one per file
    # with keywords (issue #79 — drops the D term from O(F*D*R)).
    keyword_scores = categorize.build_keyword_scores(memory, decisions)
    # Build source list: Desktop first, then tracked in order
    all_sources = _get_all_sources()
    for source_id, root in all_sources:
        any_new = _scan_source(
            root, source_id, memory, decisions, keyword_scores, files, active_fps, any_new
        )
    if any_new:
        memory.save()

    # ── Memory pruning (4A) ──────────────────────────────────────────
    pruned = memory.prune_stale(active_fps, max_age_days=settings._prune_max_age())
    if pruned > 0:
        files_logger.info(
            "Pruned %d stale memory entries (max age: %d days)",
            pruned,
            settings._prune_max_age(),
        )
        memory.save()

    key, reverse = SORT_OPTIONS.get(sort, ("name", False))

    # Global sorting with deterministic source/name tie-breaker
    # Sorting by primary key, then source, then name
    def _sort_key(f):
        return (f[key], f["source"], f["name"])

    return sorted(files, key=_sort_key, reverse=reverse)


def _validate_desktop_path(filename: str) -> Path | None:
    """Legacy validator for Desktop-only paths (kept for backward compatibility and tests)."""
    return _resolve_source_file(DEFAULT_SOURCE, filename)


def _validate_source_path(source: str, filename: str) -> Path | None:
    """Validate source-aware file path."""
    return _resolve_source_file(source, filename)


def _apply_rename(
    old_name: str, new_name: str, fingerprint: str | None = None, source: str = DEFAULT_SOURCE
) -> dict[str, bool]:
    """Shared post-rename bookkeeping used by /api/rename and
    /api/accept-suggestion: move the thumbnail, update the state.json
    decisions key, record the rename in memory, and log (issue #101).

    *fingerprint* pins the memory record when known (accept-suggestion);
    otherwise the record is resolved via the name index (rename).
    Returns which bookkeeping steps actually changed something.
    """
    thumb_moved = False
    old_thumb = _thumb_path(source, old_name)
    new_thumb = _thumb_path(source, new_name)
    with contextlib.suppress(Exception):
        if old_thumb.exists():
            new_thumb.parent.mkdir(parents=True, exist_ok=True)
            old_thumb.rename(new_thumb)
            thumb_moved = True

    state_updated = False
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
            decisions = state.get("decisions", {})
            # Handle both canonical and legacy Desktop keys
            old_key = decision_key(source, old_name)
            new_key = decision_key(source, new_name)
            moved = False
            if old_key in decisions:
                decisions[new_key] = decisions.pop(old_key)
                moved = True
            # For Desktop, also handle prefixed "Desktop|name" for forward compat
            if source == DEFAULT_SOURCE:
                prefixed_old = f"Desktop|{old_name}"
                prefixed_new = f"Desktop|{new_name}"
                if prefixed_old in decisions:
                    val = decisions.pop(prefixed_old)
                    # Prefer bare key for backward compat; overwrite if needed
                    if (
                        new_key not in decisions and prefixed_new not in decisions
                    ) or new_key not in decisions:
                        decisions[new_key] = val
                    moved = True
                # Also handle case where old_name is bare but we stored prefixed
                # Already covered: old_key is bare, so bare handled via old_key check above
                # For new_name, ensure prefixed not left (if exists, clean)
                if prefixed_new in decisions and new_key != prefixed_new:
                    # Keep bare canonical, remove prefixed duplicate if any
                    with contextlib.suppress(KeyError):
                        decisions.pop(prefixed_new)
            # For non-Desktop, ensure we move the prefixed key correctly (already done via old_key)
            if moved:
                atomic_write(STATE_FILE, json.dumps(state))
                state_updated = True
        except (json.JSONDecodeError, KeyError):
            logger.warning("State file corruption detected during rename of %s", old_name)

    memory_updated = False
    try:
        memory = _get_memory()
        rec = None
        if fingerprint:
            rec = memory.lookup(fingerprint)
        if rec is None:
            # Try source-aware lookup
            rec = memory.lookup_by_name(old_name, source=source)
            if rec is None and source == DEFAULT_SOURCE:
                rec = memory.lookup_by_name(old_name)
        if rec is not None:
            memory.record_rename(rec.fingerprint, new_name)
            memory.save()
            memory_updated = True
    except Exception as exc:
        logger.warning("Memory update failed during rename for %s: %s", old_name, exc)

    logger.info("Renamed %s -> %s (source=%s)", old_name, new_name, source)
    return {
        "thumb_moved": thumb_moved,
        "state_updated": state_updated,
        "memory_updated": memory_updated,
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/health")
def api_health():
    """Cheap liveness probe: no disk scan, no LLM calls (issue #86)."""
    desktop_ok = DESKTOP.is_dir()
    # Also check tracked folders: desktop_scanable true if any source is scannable
    tracked_ok = False
    for _src, root in _get_all_sources():
        if root.is_dir():
            tracked_ok = True
            break
    # Desktop missing but tracked exists should still be considered ok.
    # Valid tracked root should not make app look unusable merely because
    # default is missing.
    overall_ok = desktop_ok or tracked_ok
    memory_records = len(_get_memory().all_records())
    try:
        version = importlib.metadata.version("screenshot-declutterer")
    except importlib.metadata.PackageNotFoundError:
        version = "dev"
    return jsonify(
        {
            "ok": overall_ok,
            "version": version,
            "desktop_scanable": desktop_ok,
            "memory_records": memory_records,
        }
    ), (200 if overall_ok else 503)


@app.route("/api/screenshots")
def api_screenshots():
    sort = request.args.get("sort", "name")
    if sort not in SORT_OPTIONS:
        abort(400)
    return jsonify(get_screenshots(sort))


@app.route("/api/image/<filename>")
def api_image(filename: str):
    source = request.args.get("source", DEFAULT_SOURCE)
    # Handle legacy URL-encoded source param default
    image_path = _validate_source_path(source, filename)
    if image_path is None:
        abort(400)
    if not image_path.exists():
        abort(404)
    response = make_response(send_file(image_path))
    response.headers["Cache-Control"] = "private, max-age=3600"
    return response


@app.route("/api/thumb/<filename>")
def api_thumb(filename: str):
    source = request.args.get("source", DEFAULT_SOURCE)
    image_path = _validate_source_path(source, filename)
    if image_path is None:
        abort(400)
    if not image_path.exists():
        abort(404)
    thumb_path = _thumb_path(source, filename)
    if not thumb_path.exists() or image_path.stat().st_mtime > thumb_path.stat().st_mtime:
        try:
            thumb_path.parent.mkdir(parents=True, exist_ok=True)
            thumbs._generate_thumbnail(image_path, thumb_path)
        except Exception:
            files_logger.warning(
                "Thumbnail generation failed for %s (source=%s), serving full image",
                filename,
                source,
            )
            return api_image(filename)
    response = make_response(send_file(thumb_path))
    response.headers["Cache-Control"] = "private, max-age=86400"
    return response


@app.route("/api/reveal", methods=["POST"])
def api_reveal():
    """Reveal a screenshot in Finder (macOS) via `open -R`."""
    data = request.get_json(silent=True) or {}
    # Support both new {source, name} and legacy {filename}
    if "source" in data:
        src_raw = data.get("source")
        if not isinstance(src_raw, str) or not src_raw.strip():
            abort(400)
        source = src_raw
    else:
        source = DEFAULT_SOURCE
    filename = data.get("name") or data.get("filename")
    if not isinstance(filename, str) or not filename:
        abort(400)
    reveal_path = _validate_source_path(source, filename)
    if reveal_path is None:
        abort(400)
    if not reveal_path.exists():
        abort(404)
    if not IS_MACOS:
        return jsonify({"ok": False, "error": "Reveal in Finder is only supported on macOS."}), 400
    try:
        subprocess.Popen(
            ["open", "-R", str(reveal_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        logger.warning("Reveal in Finder failed for %s: %s", filename, exc)
        return jsonify({"ok": False, "error": "Could not launch Finder."}), 500
    return jsonify({"ok": True})


@app.route("/api/state", methods=["GET"])
def api_get_state():
    if STATE_FILE.exists():
        try:
            return jsonify(json.loads(STATE_FILE.read_text()))
        except json.JSONDecodeError:
            logger.warning("State file corruption detected on read, resetting")
            atomic_write(STATE_FILE, json.dumps({"decisions": {}}))
            return jsonify({"decisions": {}})
    return jsonify({"decisions": {}})


@app.route("/api/state", methods=["PUT"])
def api_save_state():
    if not request.is_json:
        abort(400)
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict) or "decisions" not in data:
        abort(400)
    atomic_write(STATE_FILE, json.dumps(data))
    return jsonify({"ok": True})


@app.route("/api/done", methods=["POST"])
def api_done():
    if not request.is_json:
        abort(400)
    data = request.get_json(silent=True) or {}
    # New contract: {files: [{source, name}, ...]} ; legacy: {filenames: [...] } => Desktop
    # If `files` key is present, it takes precedence and is validated strictly;
    # legacy `filenames` is only used when `files` is absent.
    targets: list[tuple[str, str]] = []
    errors: list[str] = []
    errors_detail: list[dict[str, str]] = []
    if "files" in data:
        files_raw = data["files"]
        if not isinstance(files_raw, list):
            return jsonify({"ok": False, "error": "files must be a list"}), 400
        for idx, entry in enumerate(files_raw):
            if not isinstance(entry, dict):
                msg = f"files[{idx}]: invalid entry"
                errors.append(msg)
                errors_detail.append({"source": "", "name": "", "error": "invalid entry"})
                continue
            # Source: missing → Desktop, explicit present but invalid → error
            if "source" not in entry:
                src = DEFAULT_SOURCE
            else:
                src_raw = entry.get("source")
                if not isinstance(src_raw, str) or not src_raw.strip():
                    msg = f"files[{idx}]: invalid source"
                    errors.append(msg)
                    # Try to capture name for detail if available
                    n = entry.get("name") or entry.get("filename") or ""
                    errors_detail.append(
                        {"source": str(src_raw), "name": str(n), "error": "invalid source"}
                    )
                    continue
                src = src_raw
            name = entry.get("name") or entry.get("filename")
            if not isinstance(name, str) or not name:
                msg = f"files[{idx}]: invalid name"
                errors.append(msg)
                errors_detail.append({"source": src, "name": str(name), "error": "invalid name"})
                continue
            targets.append((src, name))
        # `files` was explicitly provided: do not fall back to `filenames`
        # (empty `targets` with errors will result in 207 below)
    else:
        filenames = data.get("filenames", [])
        if isinstance(filenames, list):
            for fn in filenames:
                if isinstance(fn, str) and fn:
                    targets.append((DEFAULT_SOURCE, fn))
                elif fn is not None:
                    # Invalid filename entry in legacy payload → error
                    msg = f"{fn}: invalid entry"
                    errors.append(msg)
                    errors_detail.append(
                        {"source": DEFAULT_SOURCE, "name": str(fn), "error": "invalid entry"}
                    )

    trashed_ok: list[tuple[str, str]] = []
    logger.info("Starting trash batch: %d files", len(targets))
    for source, filename in targets:
        file_path = _validate_source_path(source, filename)
        if file_path is None:
            msg = (
                f"{source}|{filename}: invalid path"
                if source != DEFAULT_SOURCE
                else f"{filename}: invalid path"
            )
            errors.append(msg)
            errors_detail.append({"source": source, "name": filename, "error": "invalid path"})
            continue
        if Path(filename).suffix.lower() not in SUPPORTED_IMAGE_EXTENSION:
            msg = (
                f"{source}|{filename}: invalid filename pattern"
                if source != DEFAULT_SOURCE
                else f"{filename}: invalid filename pattern"
            )
            errors.append(msg)
            errors_detail.append(
                {"source": source, "name": filename, "error": "invalid filename pattern"}
            )
            continue
        if not file_path.exists():
            msg = (
                f"{source}|{filename}: not found"
                if source != DEFAULT_SOURCE
                else f"{filename}: not found"
            )
            errors.append(msg)
            errors_detail.append({"source": source, "name": filename, "error": "not found"})
            continue
        try:
            send2trash(str(file_path))
            logger.info("Trashed file: %s (source=%s)", filename, source)
        except Exception as exc:
            logger.error("Failed to trash %s (source=%s): %s", filename, source, exc)
            msg = (
                f"{source}|{filename}: trash failed ({exc})"
                if source != DEFAULT_SOURCE
                else f"{filename}: trash failed ({exc})"
            )
            errors.append(msg)
            errors_detail.append(
                {"source": source, "name": filename, "error": f"trash failed ({exc})"}
            )
            continue
        trashed_ok.append((source, filename))
        thumb = _thumb_path(source, filename)
        with contextlib.suppress(Exception):
            if thumb.exists():
                thumb.unlink()

    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
            decisions = state.get("decisions", {})
            for src, fn in trashed_ok:
                key = decision_key(src, fn)
                decisions.pop(key, None)
                # Remove legacy forms for Desktop (bare vs prefixed) as well
                if src == DEFAULT_SOURCE:
                    decisions.pop(fn, None)
                    decisions.pop(f"Desktop|{fn}", None)
            atomic_write(STATE_FILE, json.dumps(state))
        except (json.JSONDecodeError, KeyError):
            logger.warning("State file corruption detected during cleanup")

    # Best-effort memory update: only mark files that were actually trashed
    try:
        memory = _get_memory()
        for src, filename in trashed_ok:
            rec = memory.lookup_by_name(filename, source=src)
            if rec is None and src == DEFAULT_SOURCE:
                rec = memory.lookup_by_name(filename)
            if rec is not None:
                try:
                    memory.mark_trashed(rec.fingerprint)
                except KeyError:
                    logger.debug(
                        "Cannot mark %s (source=%s) as trashed: not in memory", filename, src
                    )
        memory.save()
    except Exception as exc:
        logger.warning("Memory update failed during trash batch: %s", exc)

    if errors:
        logger.error("Trash operation had errors: %s", errors)
        return jsonify(
            {"ok": False, "errors": errors, "errors_detail": errors_detail, "failed": errors_detail}
        ), 207
    return jsonify({"ok": True})


@app.route("/api/rename", methods=["POST"])
def api_rename():
    if not request.is_json:
        abort(400)
    data = request.get_json(silent=True) or {}
    old_name = data.get("old_name", "")
    new_name = data.get("new_name", "")
    if "source" in data:
        src_raw = data.get("source")
        if not isinstance(src_raw, str) or not src_raw.strip():
            return jsonify({"ok": False, "error": "invalid source"}), 400
        source = src_raw
    else:
        source = DEFAULT_SOURCE

    if not old_name or not new_name:
        return jsonify({"ok": False, "error": "old_name and new_name are required"}), 400

    old_path = _validate_source_path(source, old_name)
    if old_path is None:
        return jsonify({"ok": False, "error": "invalid old_name"}), 400
    if not old_path.exists():
        return jsonify({"ok": False, "error": "file not found"}), 404

    new_path = _validate_source_path(source, new_name)
    if new_path is None:
        return jsonify({"ok": False, "error": "invalid new_name"}), 400
    if new_path.exists() and new_path != old_path:
        return jsonify({"ok": False, "error": "a file with that name already exists"}), 409

    try:
        new_path.parent.mkdir(parents=True, exist_ok=True)
        old_path.rename(new_path)
    except OSError as exc:
        logger.error("Failed to rename %s to %s (source=%s): %s", old_name, new_name, source, exc)
        return jsonify({"ok": False, "error": str(exc)}), 500

    _apply_rename(old_name, new_name, source=source)
    return jsonify({"ok": True, "new_name": new_name})


@app.route("/api/memory")
def api_memory():
    """Return memory status for all recorded files."""
    memory = _get_memory()
    result: dict[str, dict[str, Any]] = {}
    for rec in memory.all_records():
        result[rec.fingerprint] = {
            "status": rec.status,
            "suggested_name": rec.suggested_name,
            "last_updated": rec.last_updated,
        }
    return jsonify({"files": result})


@app.route("/api/suggest-names", methods=["POST"])
def api_suggest_names():
    """Generate AI filename suggestions for unprocessed screenshots."""
    if not request.is_json:
        abort(400)
    data = request.get_json(silent=True) or {}
    fingerprints = data.get("fingerprints", [])
    if not isinstance(fingerprints, list):
        abort(400)

    settings_dict = settings._load_settings()
    model = settings_dict.get("llm_model", settings.DEFAULT_LLM_MODEL)

    memory = _get_memory()
    suggestions: dict[str, str] = {}
    failures: list[str] = []
    decisions = _read_decisions()
    keyword_scores = categorize.build_keyword_scores(memory, decisions)

    # Preflight: resolve each fingerprint to a record + on-disk path. Records
    # are I/O-free here; the LLM calls (HTTP to LiteRT) run in a bounded
    # thread pool since they're the only slow part (issue #81). Memory
    # mutations are applied serially in the main thread after each call.
    pending: list[tuple[str, str, Path]] = []
    for fp in fingerprints:
        rec = memory.lookup(fp)
        if rec is None or rec.status != "new":
            continue
        # Resolve source from rec.meta
        source = (
            rec.meta.get("source", DEFAULT_SOURCE) if isinstance(rec.meta, dict) else DEFAULT_SOURCE
        )
        if not isinstance(source, str):
            source = DEFAULT_SOURCE
        for candidate_name in (rec.last_known_name, rec.original_name):
            if not candidate_name:
                continue
            p = _validate_source_path(source, candidate_name)
            if p is not None and p.exists() and p.is_file():
                pending.append((fp, rec.extension, p))
                break
            # Legacy fallback for Desktop already handled via
            # validate_file_path for Desktop.

    if pending:
        workers = min(len(pending), int(os.environ.get("SS_DCL_SUGGEST_WORKERS", "4")))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="suggest") as pool:
            futures = {
                pool.submit(llm._call_litert_suggest, path, model, ext): fp
                for fp, ext, path in pending
            }
            for future in as_completed(futures):
                fp = futures[future]
                try:
                    suggested = future.result()
                except Exception as exc:
                    llm_logger.warning("Suggestion failed for %s: %s", fp, exc)
                    failures.append(fp)
                    continue
                if not suggested:
                    failures.append(fp)
                    continue

                rec = memory.lookup(fp)
                if rec is None:
                    failures.append(fp)
                    continue
                keywords = categorize.extract_keywords(suggested)
                rec.meta["keywords"] = keywords
                memory.update_suggestion(fp, suggested)
                category = categorize.suggest_category(keywords, memory, decisions, keyword_scores)
                if category:
                    rec.meta["suggested_category"] = category
                suggestions[fp] = suggested

    if suggestions:
        memory.save()

    return jsonify({"suggestions": suggestions, "failures": failures})


@app.route("/api/llm/health")
def api_llm_health():
    """LiteRT reachability check used by the frontend before a suggest batch."""
    ok = llm._litert_healthy()
    message = (
        "" if ok else "LiteRT server is not running — use the Start button above and try again."
    )
    return jsonify({"ok": ok, "provider": "litert", "error": message}), 200 if ok else 503


@app.route("/api/llm/start", methods=["POST"])
def api_llm_start():
    """Start the LiteRT server as a detached subprocess."""
    ok, message = server.start_server()
    return jsonify({"ok": ok, "message": message}), 200 if ok else 502


@app.route("/api/llm/stop", methods=["POST"])
def api_llm_stop():
    """Stop a LiteRT server this app started. Never touches foreign PIDs."""
    payload, status = server.stop_server()
    return jsonify(payload), status


@app.route("/api/accept-suggestion", methods=["POST"])
def api_accept_suggestion():
    """Accept an AI suggested name: rename the file on disk."""
    if not request.is_json:
        abort(400)
    data = request.get_json(silent=True) or {}
    fingerprint = data.get("fingerprint", "")
    if not fingerprint or not isinstance(fingerprint, str):
        return jsonify({"ok": False, "error": "fingerprint is required"}), 400

    memory = _get_memory()
    rec = memory.lookup(fingerprint)
    if rec is None:
        return jsonify({"ok": False, "error": "fingerprint not found in memory"}), 404
    if not rec.suggested_name:
        return jsonify({"ok": False, "error": "no suggestion to accept"}), 400

    old_name = rec.last_known_name or rec.original_name
    new_name = rec.suggested_name
    source = (
        rec.meta.get("source", DEFAULT_SOURCE) if isinstance(rec.meta, dict) else DEFAULT_SOURCE
    )
    if not isinstance(source, str):
        source = DEFAULT_SOURCE

    # Defensive: guard against empty/corrupt names from memory.json
    if not old_name or not new_name:
        return jsonify({"ok": False, "error": "invalid filename in memory record"}), 400

    # Validate old_name via the same path-traversal guard used by /api/rename
    old_path = _validate_source_path(source, old_name)
    if old_path is None:
        return jsonify({"ok": False, "error": "invalid old_name"}), 400
    if not old_path.is_file():
        return jsonify({"ok": False, "error": "source file not found on disk"}), 404

    new_path = _validate_source_path(source, new_name)
    if new_path is None:
        # Fallback: construct via source root for conflict check (should be valid name)
        # If new_name contains separators, it's invalid
        return jsonify({"ok": False, "error": "invalid suggested name"}), 400
    if new_path.exists():
        # Append a counter to avoid overwriting
        stem = Path(new_name).stem
        suffix = Path(new_name).suffix
        counter = 2
        # Need source-aware conflict loop: check only inside source root
        src_root = resolve_source_root(source, DESKTOP, _get_tracked_folders())
        if src_root is None:
            src_root = DESKTOP
        while (src_root / f"{stem}-{counter}{suffix}").exists():
            counter += 1
        new_name = f"{stem}-{counter}{suffix}"
        new_path = src_root / new_name

    try:
        old_path.rename(new_path)
    except OSError as exc:
        llm_logger.error("Failed to rename %s to %s: %s", old_name, new_name, exc)
        return jsonify({"ok": False, "error": str(exc)}), 500

    _apply_rename(old_name, new_name, fingerprint=fingerprint, source=source)
    return jsonify({"ok": True, "old_name": old_name, "new_name": new_name})


@app.route("/api/reject-suggestion", methods=["POST"])
def api_reject_suggestion():
    """Reject/dismiss an AI suggested name."""
    if not request.is_json:
        abort(400)
    data = request.get_json(silent=True) or {}
    fingerprint = data.get("fingerprint", "")
    if not fingerprint or not isinstance(fingerprint, str):
        return jsonify({"ok": False, "error": "fingerprint is required"}), 400

    memory = _get_memory()
    rec = memory.lookup(fingerprint)
    if rec is None:
        return jsonify({"ok": False, "error": "fingerprint not found in memory"}), 404

    memory.reject_suggestion(fingerprint)
    memory.save()
    return jsonify({"ok": True})


@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    """Return current LLM/settings configuration."""
    s = settings._load_settings()
    return jsonify(
        {
            "llm_provider": s.get("llm_provider", "litert"),
            "llm_model": s.get("llm_model", settings.DEFAULT_LLM_MODEL),
            "auto_suggest": s.get("auto_suggest", False),
            "prune_max_age_days": s.get("prune_max_age_days", 90),
            "tracked_folders": s.get("tracked_folders", []),
            "tracked_folder_info": settings._get_tracked_folder_info(),
        }
    )


@app.route("/api/settings", methods=["PUT"])
def api_save_settings():
    """Save LLM/settings configuration."""
    if not request.is_json:
        abort(400)
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        abort(400)

    current = settings._load_settings()
    type_checks = {
        "llm_provider": str,
        "llm_model": str,
        "auto_suggest": bool,
        "prune_max_age_days": int,
    }
    for key in ("llm_provider", "llm_model", "auto_suggest", "prune_max_age_days"):
        if key in data:
            if not isinstance(data[key], type_checks[key]):
                return (
                    jsonify(
                        {
                            "ok": False,
                            "error": f"{key!r} must be {type_checks[key].__name__}",
                        }
                    ),
                    400,
                )
            if key == "prune_max_age_days" and not (
                settings.PRUNE_MIN_DAYS <= data[key] <= settings.PRUNE_MAX_DAYS
            ):
                return (
                    jsonify(
                        {
                            "ok": False,
                            "error": (
                                f"prune_max_age_days must be between "
                                f"{settings.PRUNE_MIN_DAYS} and {settings.PRUNE_MAX_DAYS}"
                            ),
                        }
                    ),
                    400,
                )
            current[key] = data[key]

    # Handle tracked_folders separately with validation
    if "tracked_folders" in data:
        proposed = data["tracked_folders"]
        if not isinstance(proposed, list):
            return jsonify({"ok": False, "error": "tracked_folders must be a list"}), 400
        # Validate each entry is string
        for entry in proposed:
            if not isinstance(entry, str):
                return jsonify({"ok": False, "error": "Each tracked folder must be a string"}), 400
        # Use current persisted for allowing missing already-tracked
        persisted = current.get("tracked_folders", [])
        if not isinstance(persisted, list):
            persisted = []
        normalized, err = validate_tracked_folders(proposed, DESKTOP, persisted)
        if err:
            return jsonify({"ok": False, "error": err}), 400
        current["tracked_folders"] = normalized if normalized is not None else []

    settings._save_settings(current)
    settings.reset_prune_cache()
    return jsonify({"ok": True})


@app.route("/api/pick-folder", methods=["POST"])
def api_pick_folder():
    """Native folder picker via NSOpenPanel (macOS only)."""
    path, error = pick_folder_via_panel()
    if error:
        # Determine status code: off-macOS is 400, picker error is 500-ish
        if "only available on macOS" in error:
            return jsonify({"ok": False, "error": error}), 400
        return jsonify({"ok": False, "error": error}), 500
    if path is None:
        # Cancel
        return jsonify({"path": None}), 200
    return jsonify({"path": path}), 200


def _read_decisions() -> dict[str, str]:
    """Read state.json decisions, returning {} on miss/corruption."""
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
            return state.get("decisions", {})
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _find_free_port(start: int, max_tries: int = 100) -> int:
    for port in range(start, start + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found in range {start}-{start + max_tries - 1}")


SELECTED_PORT: int = int(os.environ.get("SS_DCL_PORT", "0")) or _find_free_port(5002)


def _open_browser() -> None:
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        time.sleep(1)
        with contextlib.suppress(Exception):
            webbrowser.open_new_tab(f"http://localhost:{SELECTED_PORT}")


class _QuietRequestHandler(WSGIRequestHandler):
    """werkzeug dev-server access logger: suppress per-request INFO lines.

    The app emits its own richer ACCESS line via ``ss_dcl.http`` (request id +
    duration + query string); werkzeug's copy is redundant noise that embeds
    its own timestamp. Only ``log_request`` is silenced — error/exception
    lines still flow through the ``werkzeug`` logger.
    """

    def log_request(self, code="-", size="-"):
        pass


if __name__ == "__main__":
    threading.Thread(target=_open_browser, daemon=True).start()
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    logger.info("Starting server on port %d", SELECTED_PORT)
    app.run(debug=debug, port=SELECTED_PORT, request_handler=_QuietRequestHandler)
