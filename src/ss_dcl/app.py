import base64
import contextlib
import errno
import json
import logging
import os
import socket
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

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
from PIL import Image
from send2trash import send2trash
from src.ss_dcl.memory import MemoryStore, atomic_write, compute_fingerprint

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent.parent.parent
app = Flask(__name__, template_folder=str(_HERE / "templates"), static_folder=str(_HERE / "static"))


@app.after_request
def set_security_headers(response: Response) -> Response:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
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
SETTINGS_FILE = Path.home() / ".ss-dcl" / "settings.json"
DEFAULT_LLM_MODEL = "gemma4:e2b"
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_HEALTH_TIMEOUT = 3  # seconds
_OLLAMA_HEALTH_TTL = 5.0  # seconds
_ollama_health_cache: Optional[tuple[float, bool]] = None
# TODO Need to check if rendering changes for .tiff or .bmp needs to be handled seperately
SUPPORTED_IMAGE_EXTENSION = (".png", ".jpg", ".jpeg", ".tiff", ".bmp")


def _parse_thumb_size(raw: str) -> tuple[int, int]:
    try:
        parts = raw.split("x")
        return (int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return (400, 300)


THUMB_SIZE: tuple[int, int] = _parse_thumb_size(os.environ.get("THUMB_SIZE", "400x300"))

SORT_OPTIONS = {
    "name": ("name", False),
    "name_desc": ("name", True),
    "date": ("mtime", False),
    "date_desc": ("mtime", True),
    "size": ("size", False),
    "size_desc": ("size", True),
}


_memory_store: Optional[MemoryStore] = None
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
    global _prune_max_age_cache
    with _memory_lock:
        _memory_store = None
    _prune_max_age_cache = None


# ── Settings cache (prune age) ──────────────────────────────────────────────
_prune_max_age_cache: Optional[int] = None


def _prune_max_age() -> int:
    global _prune_max_age_cache
    if _prune_max_age_cache is None:
        _prune_max_age_cache = _load_settings().get("prune_max_age_days", 90)
    # Global could be None in theory, but we just ensured it's set above
    age: int = _prune_max_age_cache  # type: ignore[assignment]
    return age


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
            suggested_category = suggest_category(
                existing.meta["keywords"], memory, _read_decisions()
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
    pruned = memory.prune_stale(active_fps, max_age_days=_prune_max_age())
    if pruned > 0:
        logger.info("Pruned %d stale memory entries (max age: %d days)", pruned, _prune_max_age())
        memory.save()

    key, reverse = SORT_OPTIONS.get(sort, ("name", False))
    return sorted(files, key=lambda f: f[key], reverse=reverse)


_THUMB_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="thumb")


def _generate_thumbnail(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as img:
        img.thumbnail(THUMB_SIZE)
        img.save(dst, "PNG")


def _validate_desktop_path(filename: str) -> Optional[Path]:
    if filename != Path(filename).name:
        return None
    resolved = (DESKTOP / filename).resolve()
    if not resolved.is_relative_to(DESKTOP.resolve()):
        return None
    return resolved


@app.route("/")
def index():
    return render_template("index.html")


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
            future = _THUMB_EXECUTOR.submit(_generate_thumbnail, image_path, thumb_path)
            future.result(timeout=5)
        except Exception:
            logger.warning("Thumbnail generation failed for %s, serving full image", filename)
            return api_image(filename)
    response = make_response(send_file(thumb_path))
    response.headers["Cache-Control"] = "private, max-age=86400"
    return response


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
            for fn in filenames:
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

    old_thumb = THUMB_DIR / old_name
    new_thumb = THUMB_DIR / new_name
    with contextlib.suppress(Exception):
        if old_thumb.exists():
            old_thumb.rename(new_thumb)

    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
            decisions = state.get("decisions", {})
            if old_name in decisions:
                decisions[new_name] = decisions.pop(old_name)
                atomic_write(STATE_FILE, json.dumps(state))
        except (json.JSONDecodeError, KeyError):
            logger.warning("State file corruption detected during rename")

    # Update memory: record rename (best-effort)
    try:
        memory = _get_memory()
        rec = memory.lookup_by_name(old_name)
        if rec is not None:
            memory.record_rename(rec.fingerprint, new_name)
            memory.save()
    except Exception as exc:
        logger.warning("Memory update failed during rename for %s: %s", old_name, exc)

    logger.info("Renamed %s -> %s", old_name, new_name)
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


def _is_retryable_ollama_error(exc: BaseException) -> bool:
    """Return True if *exc* is transient and worth retrying.

    Unwraps ``urllib.error.URLError`` (whose ``.reason`` may itself be an
    exception) and classifies the underlying cause.  Connection refused and
    DNS lookup failures mean the server is down — retrying is futile — while
    timeouts, resets, broken pipes, HTTP 429 and HTTP 5xx are transient.
    Unrecognized errors default to retryable to stay conservative.
    """
    if isinstance(exc, urllib.error.HTTPError):
        # HTTPError is a URLError subclass carrying an HTTP status code.
        return exc.code == 429 or exc.code >= 500

    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, BaseException):
            return _is_retryable_ollama_error(reason)
        # Non-exception reason (e.g. plain string) — unknown, stay conservative.
        return True

    if isinstance(exc, (socket.timeout, TimeoutError)):
        return True
    if isinstance(exc, (ConnectionResetError, BrokenPipeError)):
        return True
    if isinstance(exc, socket.gaierror):
        return False
    if isinstance(exc, ConnectionRefusedError):
        return False
    if isinstance(exc, OSError):
        if exc.errno == errno.ECONNREFUSED:
            return False
        if exc.errno in (errno.EPIPE, errno.ECONNRESET):
            return True
        # Unknown OSError (possibly no errno) — conservative default.
        return True
    return True


def _ollama_healthy() -> bool:
    """Cheap reachability probe (GET /api/tags).

    Negative AND positive verdicts are cached for ``_OLLAMA_HEALTH_TTL``
    seconds so a down server is probed at most once per batch instead of
    once per file.
    """
    global _ollama_health_cache
    now = time.monotonic()
    if _ollama_health_cache is not None and now - _ollama_health_cache[0] < _OLLAMA_HEALTH_TTL:
        return _ollama_health_cache[1]

    ok = False
    try:
        with urllib.request.urlopen(
            f"{OLLAMA_BASE_URL}/api/tags", timeout=OLLAMA_HEALTH_TIMEOUT
        ) as resp:
            ok = resp.status == 200
    except (urllib.error.URLError, OSError):
        ok = False

    _ollama_health_cache = (time.monotonic(), ok)
    return ok


def _call_ollama_suggest(image_path: Path, model: str, extension: str = ".png") -> Optional[str]:
    """Call Ollama API with an image and return a suggested filename.

    Extracted as a module-level function so tests can monkeypatch it
    without needing Ollama running.

    *extension* is appended to the sanitized name and should include
    the leading dot (e.g. ``".jpg"``).  Defaults to ``".png"`` for
    backward compatibility.

    Retries up to 2 times on transient connection/timeout errors with
    1s/2s backoff.  Permanent errors (connection refused, DNS failure,
    HTTP 4xx) fail fast.  JSON decode errors are not retried (malformed
    response won't fix itself).
    """
    max_retries = 2
    with open(image_path, "rb") as fh:
        image_b64 = base64.b64encode(fh.read()).decode("ascii")

    prompt = (
        "Describe this screenshot in 3-5 words as a filename. "
        "Return only the filename, no explanation, no quotes."
    )

    payload = json.dumps(
        {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_b64],
                }
            ],
            "stream": False,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                raw = result.get("message", {}).get("content", "").strip()
                break
        except json.JSONDecodeError as exc:
            logger.warning("Ollama returned malformed JSON for %s: %s", image_path.name, exc)
            return None
        except (urllib.error.URLError, OSError) as exc:
            if not _is_retryable_ollama_error(exc):
                logger.warning(
                    "Ollama unreachable for %s, not retrying: %s",
                    image_path.name,
                    exc,
                )
                return None
            if attempt < max_retries:
                wait = 2**attempt
                logger.warning(
                    "Ollama attempt %d/%d failed for %s, retrying in %ds: %s",
                    attempt + 1,
                    max_retries + 1,
                    image_path.name,
                    wait,
                    exc,
                )
                time.sleep(wait)
            else:
                logger.warning(
                    "Ollama suggest failed after %d attempts for %s: %s",
                    max_retries + 1,
                    image_path.name,
                    exc,
                )
                return None

    if not raw:
        return None

    # Sanitize: lowercase, replace spaces with hyphens, strip punctuation
    sanitized = raw.lower().replace(" ", "-")
    sanitized = "".join(c for c in sanitized if c.isalnum() or c in "-_")
    # Collapse repeated hyphens (from multi-space / punctuation gaps)
    while "--" in sanitized:
        sanitized = sanitized.replace("--", "-")
    # Truncate then strip so trailing hyphen after slice is removed
    sanitized = sanitized[:120].strip("-_").strip()
    if not sanitized:
        return None
    return sanitized + extension


def _load_settings() -> dict[str, Any]:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_settings(settings: dict[str, Any]) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(SETTINGS_FILE, json.dumps(settings, indent=2))


# ── Auto-categorization helpers (4C) ──────────────────────────────────────────


def extract_keywords(suggested_name: str) -> list[str]:
    """Extract keywords from a kebab-case filename stem.

    >>> extract_keywords("customer-onboarding-discussion.png")
    ['customer', 'onboarding', 'discussion']
    """
    stem = Path(suggested_name).stem
    return [w.lower() for w in stem.split("-") if len(w) > 2]


def _read_decisions() -> dict[str, str]:
    """Read state.json decisions, returning {} on miss/corruption."""
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
            return state.get("decisions", {})
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def suggest_category(
    keywords: list[str],
    memory: MemoryStore,
    decisions: dict[str, str],
) -> Optional[str]:
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


@app.route("/api/suggest-names", methods=["POST"])
def api_suggest_names():
    """Generate AI filename suggestions for unprocessed screenshots."""
    if not request.is_json:
        abort(400)
    data = request.get_json(silent=True) or {}
    fingerprints = data.get("fingerprints", [])
    if not isinstance(fingerprints, list):
        abort(400)

    settings = _load_settings()
    provider = settings.get("llm_provider", "ollama")
    if provider != "ollama":
        msg = f"Provider {provider!r} is not yet supported. Only 'ollama' is available."
        return jsonify({"error": msg}), 400
    model = settings.get("llm_model", DEFAULT_LLM_MODEL)

    memory = _get_memory()
    suggestions: dict[str, str] = {}
    failures: list[str] = []
    decisions = _read_decisions()

    for fp in fingerprints:
        rec = memory.lookup(fp)
        if rec is None:
            continue
        if rec.status != "new":
            continue

        # Locate file on disk via last_known_name or original_name
        file_path: Optional[Path] = None
        for candidate_name in (rec.last_known_name, rec.original_name):
            if not candidate_name:
                continue
            p = DESKTOP / candidate_name
            if p.exists() and p.is_file():
                file_path = p
                break

        if file_path is None:
            continue

        suggested = _call_ollama_suggest(file_path, model, rec.extension)
        if suggested:
            keywords = extract_keywords(suggested)
            rec.meta["keywords"] = keywords
            memory.update_suggestion(fp, suggested)
            category = suggest_category(keywords, memory, decisions)
            if category:
                rec.meta["suggested_category"] = category
            suggestions[fp] = suggested
        else:
            failures.append(fp)

    if suggestions:
        memory.save()

    return jsonify({"suggestions": suggestions, "failures": failures})


@app.route("/api/ollama/health")
def api_ollama_health():
    """Reachability check used by the frontend before running a suggest batch."""
    ok = _ollama_healthy()
    message = "" if ok else "Ollama is not reachable — start it with 'ollama serve' and try again."
    return jsonify({"ok": ok, "error": message}), 200 if ok else 503


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
        logger.error("Failed to rename %s to %s: %s", old_name, new_name, exc)
        return jsonify({"ok": False, "error": str(exc)}), 500

    # Move thumbnail
    old_thumb = THUMB_DIR / old_name
    new_thumb = THUMB_DIR / new_name
    with contextlib.suppress(Exception):
        if old_thumb.exists():
            old_thumb.rename(new_thumb)

    # Update state.json
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
            decisions = state.get("decisions", {})
            if old_name in decisions:
                decisions[new_name] = decisions.pop(old_name)
                atomic_write(STATE_FILE, json.dumps(state))
        except (json.JSONDecodeError, KeyError):
            logger.warning("State file corruption during accept-suggestion")

    # Update memory
    memory.accept_suggestion(fingerprint, new_name)
    memory.save()

    logger.info("Accepted suggestion: %s → %s", old_name, new_name)
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
    s = _load_settings()
    return jsonify(
        {
            "llm_provider": s.get("llm_provider", "ollama"),
            "llm_model": s.get("llm_model", DEFAULT_LLM_MODEL),
            "auto_suggest": s.get("auto_suggest", False),
            "prune_max_age_days": s.get("prune_max_age_days", 90),
        }
    )


@app.route("/api/settings", methods=["PUT"])
def api_save_settings():
    """Save LLM/settings configuration."""
    global _prune_max_age_cache
    if not request.is_json:
        abort(400)
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        abort(400)

    current = _load_settings()
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
            current[key] = data[key]
    _save_settings(current)
    _prune_max_age_cache = None
    return jsonify({"ok": True})


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


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    threading.Thread(target=_open_browser, daemon=True).start()
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    logger.info("Starting server on port %d", SELECTED_PORT)
    app.run(debug=debug, port=SELECTED_PORT)
