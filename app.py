import contextlib
import os
import threading
import time
import webbrowser
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_file
from send2trash import send2trash

app = Flask(__name__)

DESKTOP = Path.home() / "Desktop"
SCREENSHOT_GLOB = "Screenshot*.png"


def get_screenshots():
    """Return sorted list of screenshot filenames from ~/Desktop (top-level only)."""
    return sorted(p.name for p in DESKTOP.glob(SCREENSHOT_GLOB) if p.is_file())


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/screenshots")
def api_screenshots():
    return jsonify(get_screenshots())


@app.route("/api/image/<filename>")
def api_image(filename):
    # Guard against path traversal
    if filename != Path(filename).name:
        abort(400)
    image_path = (DESKTOP / filename).resolve()
    if not str(image_path).startswith(str(DESKTOP.resolve())):
        abort(400)
    if not image_path.exists():
        abort(404)
    return send_file(image_path)


@app.route("/api/done", methods=["POST"])
def api_done():
    data = request.get_json(silent=True) or {}
    filenames = data.get("filenames", [])

    errors = []
    for filename in filenames:
        # Guard against path traversal
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

    if errors:
        return jsonify({"ok": False, "errors": errors}), 207
    return jsonify({"ok": True})


def _open_browser():
    # Wait briefly for Flask to finish binding the port, then open the browser.
    # Guard against Flask's reloader launching a second process.
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        time.sleep(1)
        with contextlib.suppress(Exception):
            webbrowser.open_new_tab("http://localhost:5000")


if __name__ == "__main__":
    threading.Thread(target=_open_browser, daemon=True).start()
    app.run(debug=False, port=5000)
