import contextlib
import json
import logging
import os
import tempfile
import threading
import time
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


_dirs_initialized = False


@app.before_request
def _init_dirs():
    global _dirs_initialized
    if not _dirs_initialized:
        THUMB_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _dirs_initialized = True


def get_screenshots(sort: str = "name") -> list[dict[str, Any]]:
    files = []
    for p in DESKTOP.glob("Screenshot*.*"):
        # only continue if it's a file and has a supported image extension (case-insensitive)
        if not p.is_file() or (p.suffix.lower() not in SUPPORTED_IMAGE_EXTENSION):
            continue
        files.append(
            {
                "name": p.name,
                "size": p.stat().st_size,
                "mtime": p.stat().st_mtime,
            }
        )
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
            _atomic_write(STATE_FILE, json.dumps({"decisions": {}}))
            return jsonify({"decisions": {}})
    return jsonify({"decisions": {}})


def _atomic_write(path: Path, content: str) -> None:
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w") as f:
            f.write(content)
        os.replace(tmp_path, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


@app.route("/api/state", methods=["PUT"])
def api_save_state():
    if not request.is_json:
        abort(400)
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict) or "decisions" not in data:
        abort(400)
    _atomic_write(STATE_FILE, json.dumps(data))
    return jsonify({"ok": True})


@app.route("/api/done", methods=["POST"])
def api_done():
    if not request.is_json:
        abort(400)
    data = request.get_json(silent=True) or {}
    filenames = data.get("filenames", [])

    errors = []
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
            _atomic_write(STATE_FILE, json.dumps(state))
        except (json.JSONDecodeError, KeyError):
            logger.warning("State file corruption detected during cleanup")

    if errors:
        logger.error("Trash operation had errors: %s", errors)
        return jsonify({"ok": False, "errors": errors}), 207
    return jsonify({"ok": True})


def _open_browser() -> None:
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        time.sleep(1)
        with contextlib.suppress(Exception):
            webbrowser.open_new_tab("http://localhost:5002")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    threading.Thread(target=_open_browser, daemon=True).start()
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug, port=5002)
