import contextlib
import fnmatch
import json
import logging
import os
import tempfile
import threading
import time
import webbrowser
from pathlib import Path

from flask import Flask, abort, jsonify, make_response, render_template, request, send_file
from send2trash import send2trash

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent.parent.parent
app = Flask(__name__, template_folder=str(_HERE / "templates"), static_folder=str(_HERE / "static"))


@app.after_request
def set_security_headers(response):
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


DESKTOP = Path.home() / "Desktop"
SCREENSHOT_GLOB = "Screenshot*.png"
THUMB_DIR = Path.home() / ".cache" / "ss-dcl" / "thumbs"
STATE_FILE = Path.home() / ".ss-dcl" / "state.json"
THUMB_SIZE = (400, 300)

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


def get_screenshots(sort="name"):
    files = [
        {"name": p.name, "size": p.stat().st_size, "mtime": p.stat().st_mtime}
        for p in DESKTOP.glob(SCREENSHOT_GLOB)
        if p.is_file()
    ]
    key, reverse = SORT_OPTIONS.get(sort, ("name", False))
    return sorted(files, key=lambda f: f[key], reverse=reverse)


def _generate_thumbnail(src, dst):
    from PIL import Image

    dst.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as img:
        img.thumbnail(THUMB_SIZE)
        img.save(dst, "PNG")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/screenshots")
def api_screenshots():
    sort = request.args.get("sort", "name")
    return jsonify(get_screenshots(sort))


@app.route("/api/image/<filename>")
def api_image(filename):
    if filename != Path(filename).name:
        abort(400)
    image_path = (DESKTOP / filename).resolve()
    if not image_path.is_relative_to(DESKTOP.resolve()):
        abort(400)
    if not image_path.exists():
        abort(404)
    response = make_response(send_file(image_path))
    response.headers["Cache-Control"] = "private, max-age=3600"
    return response


@app.route("/api/thumb/<filename>")
def api_thumb(filename):
    if filename != Path(filename).name:
        abort(400)
    image_path = (DESKTOP / filename).resolve()
    if not image_path.is_relative_to(DESKTOP.resolve()):
        abort(400)
    if not image_path.exists():
        abort(404)
    thumb_path = THUMB_DIR / filename
    if not thumb_path.exists() or image_path.stat().st_mtime > thumb_path.stat().st_mtime:
        try:
            _generate_thumbnail(image_path, thumb_path)
        except Exception:
            logger.warning("Thumbnail generation failed for %s, serving full image", filename)
            return api_image(filename)
    response = make_response(send_file(thumb_path))
    response.headers["Cache-Control"] = "private, max-age=86400"
    return response


@app.route("/api/state", methods=["GET"])
def api_get_state():
    if STATE_FILE.exists():
        return jsonify(json.loads(STATE_FILE.read_text()))
    return jsonify({"decisions": {}})


def _atomic_write(path, content):
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
    data = request.get_json(silent=True) or {}
    _atomic_write(STATE_FILE, json.dumps(data))
    return jsonify({"ok": True})


@app.route("/api/done", methods=["POST"])
def api_done():
    data = request.get_json(silent=True) or {}
    filenames = data.get("filenames", [])

    errors = []
    for filename in filenames:
        if filename != Path(filename).name:
            errors.append(f"{filename}: invalid path")
            continue
        if not fnmatch.fnmatch(filename, SCREENSHOT_GLOB):
            errors.append(f"{filename}: invalid filename pattern")
            continue
        file_path = (DESKTOP / filename).resolve()
        if not file_path.is_relative_to(DESKTOP.resolve()):
            errors.append(f"{filename}: invalid path")
            continue
        if not file_path.exists():
            errors.append(f"{filename}: not found")
            continue
        send2trash(str(file_path))
        logger.info("Trashed file: %s", filename)
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


def _open_browser():
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        time.sleep(1)
        with contextlib.suppress(Exception):
            webbrowser.open_new_tab("http://localhost:5002")


if __name__ == "__main__":
    threading.Thread(target=_open_browser, daemon=True).start()
    app.run(debug=False, port=5002)
