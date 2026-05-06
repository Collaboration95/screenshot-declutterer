import contextlib
import json
import os
import threading
import time
import webbrowser
from pathlib import Path

from flask import Flask, abort, jsonify, make_response, render_template, request, send_file
from send2trash import send2trash

app = Flask(__name__)

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


def _ensure_dirs():
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)


_ensure_dirs()


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
    if not str(image_path).startswith(str(DESKTOP.resolve())):
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
    if not str(image_path).startswith(str(DESKTOP.resolve())):
        abort(400)
    if not image_path.exists():
        abort(404)
    thumb_path = THUMB_DIR / filename
    if not thumb_path.exists() or image_path.stat().st_mtime > thumb_path.stat().st_mtime:
        try:
            _generate_thumbnail(image_path, thumb_path)
        except Exception:
            return api_image(filename)
    response = make_response(send_file(thumb_path))
    response.headers["Cache-Control"] = "private, max-age=86400"
    return response


@app.route("/api/state", methods=["GET"])
def api_get_state():
    if STATE_FILE.exists():
        return jsonify(json.loads(STATE_FILE.read_text()))
    return jsonify({"decisions": {}})


@app.route("/api/state", methods=["PUT"])
def api_save_state():
    data = request.get_json(silent=True) or {}
    STATE_FILE.write_text(json.dumps(data))
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
        file_path = (DESKTOP / filename).resolve()
        if not str(file_path).startswith(str(DESKTOP.resolve())):
            errors.append(f"{filename}: invalid path")
            continue
        if not file_path.exists():
            errors.append(f"{filename}: not found")
            continue
        send2trash(str(file_path))
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
            STATE_FILE.write_text(json.dumps(state))
        except (json.JSONDecodeError, KeyError):
            pass

    if errors:
        return jsonify({"ok": False, "errors": errors}), 207
    return jsonify({"ok": True})


def _open_browser():
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        time.sleep(1)
        with contextlib.suppress(Exception):
            webbrowser.open_new_tab("http://localhost:5001")


if __name__ == "__main__":
    threading.Thread(target=_open_browser, daemon=True).start()
    app.run(debug=False, port=5001)
