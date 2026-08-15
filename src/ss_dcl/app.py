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
from ss_dcl.memory import MemoryStore, atomic_write, compute_fingerprint

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
THUMB_DIR = Path.home() / ".cache" / "ss-dcl" / "thumbs"
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
    "size": ("size", False),
    "size_desc": ("size", True),
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


def get_screenshots(sort: str = "name") -> list[dict[str, Any]]:
    memory = _get_memory()
    files: list[dict[str, Any]] = []
    any_new = False
    active_fps: set[str] = set()
    decisions = _read_decisions()
    # Per-request accumulator: one pass over decisions instead of one per file
    # with keywords (issue #79 — drops the D term from O(F*D*R)).
    keyword_scores = categorize.build_keyword_scores(memory, decisions)
    for p in DESKTOP.glob("Screenshot*.*"):
        if not p.is_file() or (p.suffix.lower() not in SUPPORTED_IMAGE_EXTENSION):
            continue
        name = p.name
        st = p.stat()
        size = st.st_size
        fp = compute_fingerprint(name, size)
        existing = memory.lookup(fp)
        # Fallback: after a rename the fingerprint changes (new name + same size),
        # so try lookup_by_name which scans last_known_name / original_name.
        if existing is None:
            existing = memory.lookup_by_name(name)
        if existing is not None:
            memory_status = existing.status
            active_fps.add(existing.fingerprint)
        else:
            rec = memory.record_file(name, size)
            memory_status = "new"
            active_fps.add(rec.fingerprint)
            any_new = True
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
                "size": size,
                "mtime": st.st_mtime,
                "fingerprint": fp,
                "memory_status": memory_status,
                "suggested_name": suggested_name,
                "suggested_category": suggested_category,
            }
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
    return sorted(files, key=lambda f: f[key], reverse=reverse)


def _validate_desktop_path(filename: str) -> Path | None:
    if filename != Path(filename).name:
        return None
    resolved = (DESKTOP / filename).resolve()
    if not resolved.is_relative_to(DESKTOP.resolve()):
        return None
    return resolved


def _apply_rename(old_name: str, new_name: str, fingerprint: str | None = None) -> dict[str, bool]:
    """Shared post-rename bookkeeping used by /api/rename and
    /api/accept-suggestion: move the thumbnail, update the state.json
    decisions key, record the rename in memory, and log (issue #101).

    *fingerprint* pins the memory record when known (accept-suggestion);
    otherwise the record is resolved via the name index (rename).
    Returns which bookkeeping steps actually changed something.
    """
    thumb_moved = False
    old_thumb = THUMB_DIR / old_name
    new_thumb = THUMB_DIR / new_name
    with contextlib.suppress(Exception):
        if old_thumb.exists():
            old_thumb.rename(new_thumb)
            thumb_moved = True

    state_updated = False
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
            decisions = state.get("decisions", {})
            if old_name in decisions:
                decisions[new_name] = decisions.pop(old_name)
                atomic_write(STATE_FILE, json.dumps(state))
                state_updated = True
        except (json.JSONDecodeError, KeyError):
            logger.warning("State file corruption detected during rename of %s", old_name)

    memory_updated = False
    try:
        memory = _get_memory()
        rec = memory.lookup(fingerprint) if fingerprint else memory.lookup_by_name(old_name)
        if rec is not None:
            memory.record_rename(rec.fingerprint, new_name)
            memory.save()
            memory_updated = True
    except Exception as exc:
        logger.warning("Memory update failed during rename for %s: %s", old_name, exc)

    logger.info("Renamed %s -> %s", old_name, new_name)
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
    memory_records = len(_get_memory().all_records())
    try:
        version = importlib.metadata.version("screenshot-declutterer")
    except importlib.metadata.PackageNotFoundError:
        version = "dev"
    return jsonify(
        {
            "ok": desktop_ok,
            "version": version,
            "desktop_scanable": desktop_ok,
            "memory_records": memory_records,
        }
    ), (200 if desktop_ok else 503)


@app.route("/api/screenshots")
def api_screenshots():
    sort = request.args.get("sort", "name")
    if sort not in SORT_OPTIONS:
        abort(400)
    return jsonify(get_screenshots(sort))


@app.route("/api/image/<filename>")
def api_image(filename: str):
    image_path = _validate_desktop_path(filename)
    if image_path is None:
        abort(400)
    if not image_path.exists():
        abort(404)
    response = make_response(send_file(image_path))
    response.headers["Cache-Control"] = "private, max-age=3600"
    return response


@app.route("/api/thumb/<filename>")
def api_thumb(filename: str):
    image_path = _validate_desktop_path(filename)
    if image_path is None:
        abort(400)
    if not image_path.exists():
        abort(404)
    thumb_path = THUMB_DIR / filename
    if not thumb_path.exists() or image_path.stat().st_mtime > thumb_path.stat().st_mtime:
        try:
            thumbs._generate_thumbnail(image_path, thumb_path)
        except Exception:
            files_logger.warning("Thumbnail generation failed for %s, serving full image", filename)
            return api_image(filename)
    response = make_response(send_file(thumb_path))
    response.headers["Cache-Control"] = "private, max-age=86400"
    return response


@app.route("/api/reveal", methods=["POST"])
def api_reveal():
    """Reveal a screenshot in Finder (macOS) via `open -R`."""
    data = request.get_json(silent=True) or {}
    filename = data.get("filename")
    if not isinstance(filename, str) or not filename:
        abort(400)
    reveal_path = _validate_desktop_path(filename)
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
    filenames = data.get("filenames", [])

    errors = []
    trashed_ok: list[str] = []
    logger.info("Starting trash batch: %d files", len(filenames))
    for filename in filenames:
        file_path = _validate_desktop_path(filename)
        if file_path is None:
            errors.append(f"{filename}: invalid path")
            continue
        if Path(filename).suffix.lower() not in SUPPORTED_IMAGE_EXTENSION:
            errors.append(f"{filename}: invalid filename pattern")
            continue
        if not file_path.exists():
            errors.append(f"{filename}: not found")
            continue
        try:
            send2trash(str(file_path))
            logger.info("Trashed file: %s", filename)
        except Exception as exc:
            logger.error("Failed to trash %s: %s", filename, exc)
            errors.append(f"{filename}: trash failed ({exc})")
            continue
        trashed_ok.append(filename)
        thumb = THUMB_DIR / filename
        with contextlib.suppress(Exception):
            if thumb.exists():
                thumb.unlink()

    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
            decisions = state.get("decisions", {})
            for fn in trashed_ok:
                decisions.pop(fn, None)
            atomic_write(STATE_FILE, json.dumps(state))
        except (json.JSONDecodeError, KeyError):
            logger.warning("State file corruption detected during cleanup")

    # Best-effort memory update: only mark files that were actually trashed
    try:
        memory = _get_memory()
        for filename in trashed_ok:
            rec = memory.lookup_by_name(filename)
            if rec is not None:
                try:
                    memory.mark_trashed(rec.fingerprint)
                except KeyError:
                    logger.debug("Cannot mark %s as trashed: not in memory", filename)
        memory.save()
    except Exception as exc:
        logger.warning("Memory update failed during trash batch: %s", exc)

    if errors:
        logger.error("Trash operation had errors: %s", errors)
        return jsonify({"ok": False, "errors": errors}), 207
    return jsonify({"ok": True})


@app.route("/api/rename", methods=["POST"])
def api_rename():
    if not request.is_json:
        abort(400)
    data = request.get_json(silent=True) or {}
    old_name = data.get("old_name", "")
    new_name = data.get("new_name", "")

    if not old_name or not new_name:
        return jsonify({"ok": False, "error": "old_name and new_name are required"}), 400

    old_path = _validate_desktop_path(old_name)
    if old_path is None:
        return jsonify({"ok": False, "error": "invalid old_name"}), 400
    if not old_path.exists():
        return jsonify({"ok": False, "error": "file not found"}), 404

    new_path = _validate_desktop_path(new_name)
    if new_path is None:
        return jsonify({"ok": False, "error": "invalid new_name"}), 400
    if new_path.exists() and new_path != old_path:
        return jsonify({"ok": False, "error": "a file with that name already exists"}), 409

    try:
        old_path.rename(new_path)
    except OSError as exc:
        logger.error("Failed to rename %s to %s: %s", old_name, new_name, exc)
        return jsonify({"ok": False, "error": str(exc)}), 500

    _apply_rename(old_name, new_name)
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
        for candidate_name in (rec.last_known_name, rec.original_name):
            if not candidate_name:
                continue
            p = DESKTOP / candidate_name
            if p.exists() and p.is_file():
                pending.append((fp, rec.extension, p))
                break

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

    # Defensive: guard against empty/corrupt names from memory.json
    if not old_name or not new_name:
        return jsonify({"ok": False, "error": "invalid filename in memory record"}), 400

    # Validate old_name via the same path-traversal guard used by /api/rename
    old_path = _validate_desktop_path(old_name)
    if old_path is None:
        return jsonify({"ok": False, "error": "invalid old_name"}), 400
    if not old_path.is_file():
        return jsonify({"ok": False, "error": "source file not found on disk"}), 404

    new_path = DESKTOP / new_name
    if new_path.exists():
        # Append a counter to avoid overwriting
        stem = Path(new_name).stem
        suffix = Path(new_name).suffix
        counter = 2
        while (DESKTOP / f"{stem}-{counter}{suffix}").exists():
            counter += 1
        new_name = f"{stem}-{counter}{suffix}"
        new_path = DESKTOP / new_name

    try:
        old_path.rename(new_path)
    except OSError as exc:
        llm_logger.error("Failed to rename %s to %s: %s", old_name, new_name, exc)
        return jsonify({"ok": False, "error": str(exc)}), 500

    _apply_rename(old_name, new_name, fingerprint=fingerprint)
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
    settings._save_settings(current)
    settings.reset_prune_cache()
    return jsonify({"ok": True})


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
