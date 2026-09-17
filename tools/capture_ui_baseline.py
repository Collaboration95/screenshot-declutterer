"""Capture the deterministic UI baseline images for the Phase 0 revamp plan.

The tool is self-contained. It generates (or reuses) the demo fixture from
``tools/demo_fixtures.py``, serves the app against that fixture with an isolated
``SS_DCL_DESKTOP`` / ``SS_DCL_HOME`` pair and a deliberately unreachable
``LITERT_BASE_URL``, drives headless Chrome over the DevTools protocol, and
writes one PNG per (viewport, state, theme) into ``docs/assets/ui-baseline``.

Nothing here reads the real Desktop or the real ``~/.ss-dcl`` runtime tree, and
no language model is needed: every state documented in
``docs/ui-inventory-phase0.md`` is reachable with the fixture alone.

Usage:
    uv run python tools/capture_ui_baseline.py
    uv run python tools/capture_ui_baseline.py --force --out docs/assets/ui-baseline
    uv run python tools/capture_ui_baseline.py --states board,multi-select --themes dark
    uv run python tools/capture_ui_baseline.py --url http://127.0.0.1:5311
    uv run python tools/capture_ui_baseline.py --list

Chrome is discovered from ``SS_DCL_CHROME`` or the usual macOS/Linux install
locations; when it is missing the tool explains how to point at one instead of
failing with a traceback.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _REPO_ROOT / "src"
_TOOLS_DIR = Path(__file__).resolve().parent
for _extra in (str(_SRC_DIR), str(_TOOLS_DIR)):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

import demo_fixtures  # noqa: E402

#: Chrome flags that keep the headless run reproducible and quiet.
HEADLESS_FLAG = "--headless=new"
#: Default output directory for the baseline images.
DEFAULT_OUT = _REPO_ROOT / "docs" / "assets" / "ui-baseline"
#: Directory holding the capture Chrome profile (gitignored, disposable).
DEFAULT_PROFILE = _REPO_ROOT / ".cache" / "ui-baseline-chrome"

#: Cards in the Unsorted column, the column the triage states are built on.
UNSORTED_CARD = "#cards-unsorted .card"

_SERVER_BOOTSTRAP = """
import sys

from werkzeug.serving import make_server

from ss_dcl.app import app

make_server("127.0.0.1", int(sys.argv[1]), app, threaded=True).serve_forever()
"""

#: Board is populated, every card image in the viewport has decoded, and the
#: app is no longer showing its loading notice. Lazy images below the fold are
#: deliberately ignored.
_PAGE_READY = (
    "(function () {"
    "  var loading = document.getElementById('loading-msg');"
    "  if (loading && !loading.hidden) return false;"
    "  if (document.querySelectorAll('.card').length === 0) return false;"
    "  var imgs = Array.prototype.slice.call(document.querySelectorAll('.card img'));"
    "  var visible = imgs.filter(function (img) {"
    "    var r = img.getBoundingClientRect();"
    "    return r.width > 0 && r.bottom > 0 && r.top < window.innerHeight"
    "      && r.right > 0 && r.left < window.innerWidth;"
    "  });"
    "  for (var i = 0; i < visible.length; i += 1) {"
    "    if (!visible[i].complete || visible[i].naturalWidth === 0) return false;"
    "  }"
    "  return visible.length > 0;"
    "})()"
)


class CaptureError(RuntimeError):
    """Raised when a capture step cannot complete."""


@dataclass(frozen=True)
class Viewport:
    """A canonical baseline viewport (CSS pixels)."""

    name: str
    width: int
    height: int
    role: str


VIEWPORTS: tuple[Viewport, ...] = (
    Viewport("1440x900", 1440, 900, "primary"),
    Viewport("1280x800", 1280, 800, "secondary"),
    Viewport("1024x768", 1024, 768, "compact"),
)

THEMES: tuple[str, ...] = ("light", "dark")


@dataclass(frozen=True)
class CaptureState:
    """One UI state worth comparing between phases."""

    name: str
    description: str
    prepare: Callable[[CdpSession], str] | None = None
    #: Board captures run at every viewport; overlays only at the primary one.
    all_viewports: bool = False


def _click(cdp: CdpSession, selector: str, index: int = 0) -> None:
    clicked = cdp.evaluate(
        "(function () {"
        f"  var el = document.querySelectorAll({json.dumps(selector)})[{index}];"
        "  if (!el) return false;"
        "  el.click();"
        "  return true;"
        "})()"
    )
    if not clicked:
        raise CaptureError(f"could not click {selector}[{index}]")


def _prepare_hover(cdp: CdpSession) -> str:
    point = cdp.evaluate(
        "(function () {"
        f"  var el = document.querySelectorAll({json.dumps(UNSORTED_CARD)})[1];"
        "  if (!el) return null;"
        "  var r = el.getBoundingClientRect();"
        "  return {x: r.left + r.width / 2, y: r.top + Math.min(80, r.height / 2)};"
        "})()"
    )
    if not point:
        raise CaptureError("no unsorted card available for the hover state")
    cdp.call(
        "Input.dispatchMouseEvent",
        {"type": "mouseMoved", "x": point["x"], "y": point["y"], "button": "none"},
    )
    cdp.wait_for(
        "(function () {"
        f"  var el = document.querySelectorAll({json.dumps(UNSORTED_CARD)})[1];"
        "  if (!el) return false;"
        "  var actions = el.querySelector('.card-actions');"
        "  return actions && window.getComputedStyle(actions).opacity === '1';"
        "})()",
        "card action overlay to appear on hover",
    )
    return "hovering the triage overlay of one unsorted card"


def _prepare_multi_select(cdp: CdpSession) -> str:
    for index in range(3):
        _click(cdp, UNSORTED_CARD, index)
    cdp.wait_for(
        "(function () {"
        "  var bar = document.getElementById('batch-bar');"
        "  return bar && !bar.hidden && document.querySelectorAll('.card.selected').length;"
        "})()",
        "the batch bar with three selected cards",
    )
    count = cdp.evaluate("document.querySelectorAll('.card.selected').length")
    return f"{count} cards selected, batch bar visible"


def _prepare_lightbox(cdp: CdpSession) -> str:
    cdp.evaluate(
        "(function () {"
        f"  var el = document.querySelectorAll({json.dumps(UNSORTED_CARD)})[0];"
        "  if (el) el.dispatchEvent(new MouseEvent('dblclick', {bubbles: true}));"
        "})()"
    )
    cdp.wait_for(
        "(function () {"
        "  var box = document.getElementById('lightbox');"
        "  var img = document.getElementById('lightbox-img');"
        "  return box && !box.hidden && img && img.complete && img.naturalWidth > 0;"
        "})()",
        "the lightbox and its full-size image",
    )
    return "lightbox open on the first unsorted screenshot"


def _prepare_confirm(cdp: CdpSession) -> str:
    pending = cdp.evaluate("document.getElementById('done-btn').disabled")
    if pending:
        raise CaptureError("the Done button is disabled, so the confirm dialog cannot open")
    _click(cdp, "#done-btn")
    cdp.wait_for(
        "(function () {"
        "  var modal = document.getElementById('confirm-modal');"
        "  return modal && !modal.hidden;"
        "})()",
        "the trash confirmation dialog",
    )
    return "trash confirmation dialog open"


def _prepare_rename(cdp: CdpSession) -> str:
    _click(cdp, "#cards-trash .card .btn-rename")
    cdp.wait_for(
        "(function () {"
        "  var modal = document.getElementById('rename-modal');"
        "  return modal && !modal.hidden;"
        "})()",
        "the rename dialog",
    )
    return "rename dialog open on a card in the Trash column"


def _prepare_settings(cdp: CdpSession) -> str:
    _click(cdp, "#settings-btn")
    cdp.wait_for(
        "(function () {"
        "  var menu = document.getElementById('settings-menu');"
        "  if (!menu || menu.hidden) return false;"
        "  return document.querySelectorAll('#tracked-folders-list .tracked-folder-row').length;"
        "})()",
        "the settings panel and its tracked folder rows",
    )
    return "settings panel open with the tracked folder listed"


STATES: tuple[CaptureState, ...] = (
    CaptureState(
        "board",
        "Populated board: unsorted, kept and trashed cards, a suggested-name badge, "
        "category hints, a tracked-folder source tag, and the LLM-offline header control",
        all_viewports=True,
    ),
    CaptureState("hover", "Card action overlay revealed on hover", _prepare_hover),
    CaptureState("multi-select", "Multi-select with the batch action bar", _prepare_multi_select),
    CaptureState("lightbox", "Full-size lightbox preview", _prepare_lightbox),
    CaptureState("confirm", "Trash confirmation dialog", _prepare_confirm),
    CaptureState("rename", "Rename dialog", _prepare_rename),
    CaptureState("settings", "Settings panel with tracked folders", _prepare_settings),
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _preferred_port(workspace: Path, requested: int = 0) -> int:
    """Bind the fixture's advertised port when it is free, else any free port.

    Keeping the port stable makes the generated index (which records the URL)
    identical across captures.
    """
    if requested:
        return requested
    try:
        advertised = int(demo_fixtures.load_manifest(workspace)["env"]["SS_DCL_PORT"])
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
        advertised = 0
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", advertised))
        except OSError:
            return _free_port()
    return advertised


# ── Minimal WebSocket client ────────────────────────────────────────────────


class _WebSocket:
    """Bare RFC 6455 client: masked text frames, enough for the DevTools protocol."""

    def __init__(self, url: str, timeout: float = 30.0) -> None:
        parts = urllib.parse.urlsplit(url)
        host = parts.hostname or "127.0.0.1"
        port = parts.port or (443 if parts.scheme == "wss" else 80)
        target = parts.path or "/"
        if parts.query:
            target = f"{target}?{parts.query}"
        self._timeout = timeout
        self._buffer = b""
        self._sock = socket.create_connection((host, port), timeout=timeout)
        self._sock.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        handshake = (
            f"GET {target} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        # No Origin header on purpose: Chrome 111+ rejects DevTools websocket
        # handshakes that carry one unless --remote-allow-origins lists it.
        self._sock.sendall(handshake.encode("ascii"))
        header = self._read_until(b"\r\n\r\n")
        status = header.split(b"\r\n", 1)[0].decode("latin-1")
        if " 101 " not in status:
            raise CaptureError(f"websocket handshake rejected for {url}: {status}")

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self._sock.close()

    def _read_until(self, marker: bytes) -> bytes:
        while marker not in self._buffer:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise CaptureError("websocket closed during handshake")
            self._buffer += chunk
        head, _, rest = self._buffer.partition(marker)
        self._buffer = rest
        return head + marker

    def _recv_exact(self, count: int) -> bytes:
        while len(self._buffer) < count:
            chunk = self._sock.recv(max(4096, count - len(self._buffer)))
            if not chunk:
                raise CaptureError("websocket closed by the browser")
            self._buffer += chunk
        data, self._buffer = self._buffer[:count], self._buffer[count:]
        return data

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        header = bytearray([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 1 << 16:
            header.append(0x80 | 126)
            header += length.to_bytes(2, "big")
        else:
            header.append(0x80 | 127)
            header += length.to_bytes(8, "big")
        mask = os.urandom(4)
        header += mask
        masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
        self._sock.sendall(bytes(header) + masked)

    def _read_frame(self) -> tuple[bool, int, bytes]:
        first, second = self._recv_exact(2)
        fin = bool(first & 0x80)
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F
        if length == 126:
            length = int.from_bytes(self._recv_exact(2), "big")
        elif length == 127:
            length = int.from_bytes(self._recv_exact(8), "big")
        mask = self._recv_exact(4) if masked else b""
        payload = self._recv_exact(length) if length else b""
        if masked:
            payload = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
        return fin, opcode, payload

    def send_text(self, text: str) -> None:
        self._send_frame(0x1, text.encode("utf-8"))

    def recv_text(self) -> str:
        chunks: list[bytes] = []
        while True:
            fin, opcode, payload = self._read_frame()
            if opcode == 0x9:
                self._send_frame(0xA, payload)
                continue
            if opcode == 0xA:
                continue
            if opcode == 0x8:
                raise CaptureError("websocket closed by the browser")
            chunks.append(payload)
            if fin:
                return b"".join(chunks).decode("utf-8", "replace")


class CdpSession:
    """Tiny Chrome DevTools Protocol client bound to one page target."""

    def __init__(self, ws_url: str, timeout: float = 30.0) -> None:
        self._timeout = timeout
        self._ws = _WebSocket(ws_url, timeout=timeout)
        self._next_id = 0
        self.exceptions: list[str] = []

    def close(self) -> None:
        self._ws.close()

    def call(
        self, method: str, params: dict[str, Any] | None = None, timeout: float | None = None
    ) -> dict[str, Any]:
        self._next_id += 1
        message: dict[str, Any] = {"id": self._next_id, "method": method}
        if params:
            message["params"] = params
        self._ws.send_text(json.dumps(message))
        deadline = time.monotonic() + (timeout or self._timeout)
        while True:
            if time.monotonic() > deadline:
                raise CaptureError(f"{method} timed out")
            try:
                event = json.loads(self._ws.recv_text())
            except (TimeoutError, OSError) as exc:
                raise CaptureError(f"{method} timed out: {exc}") from exc
            if event.get("id") == self._next_id:
                if "error" in event:
                    raise CaptureError(f"{method} failed: {json.dumps(event['error'])}")
                result = event.get("result")
                return result if isinstance(result, dict) else {}
            self._record(event)

    def _record(self, event: dict[str, Any]) -> None:
        if event.get("method") != "Runtime.exceptionThrown":
            return
        details = event.get("params", {}).get("exceptionDetails", {})
        text = details.get("exception", {}).get("description") or details.get("text")
        if text:
            self.exceptions.append(str(text).splitlines()[0])

    def evaluate(self, expression: str, *, await_promise: bool = False) -> Any:
        result = self.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": await_promise},
        )
        if result.get("exceptionDetails"):
            details = result["exceptionDetails"]
            text = details.get("exception", {}).get("description") or details.get("text", "")
            raise CaptureError(f"page script error: {str(text).splitlines()[0]}")
        value = result.get("result", {}).get("value")
        return value

    def wait_for(self, expression: str, description: str, timeout: float = 30.0) -> Any:
        deadline = time.monotonic() + timeout
        last: Any = None
        while time.monotonic() < deadline:
            last = self.evaluate(expression)
            if last:
                return last
            time.sleep(0.1)
        raise CaptureError(f"timed out waiting for {description} (last value: {last!r})")


# ── Chrome ──────────────────────────────────────────────────────────────────


def find_chrome() -> str | None:
    """Return a Chrome/Chromium binary path, or None when none is installed."""
    override = os.environ.get("SS_DCL_CHROME")
    if override:
        return override if Path(override).exists() else None
    candidates = (
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    )
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    for name in ("google-chrome", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    return None


class ChromeSession:
    """Headless Chrome process exposing one reusable page target."""

    def __init__(
        self, binary: str, profile_dir: Path, window: tuple[int, int] = (1440, 900)
    ) -> None:
        self._binary = binary
        self._profile = profile_dir
        self._window = window
        self._process: subprocess.Popen[bytes] | None = None
        self._log: IO[bytes] | None = None
        self._port = 0

    def __enter__(self) -> ChromeSession:
        self._profile.mkdir(parents=True, exist_ok=True)
        width, height = self._window
        args = [
            self._binary,
            HEADLESS_FLAG,
            "--remote-debugging-port=0",
            f"--user-data-dir={self._profile}",
            f"--window-size={width},{height}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-extensions",
            "--disable-sync",
            "--disable-gpu",
            "--force-color-profile=srgb",
            "--no-service-autorun",
            "--password-store=basic",
            "about:blank",
        ]
        self._log = open(self._profile / "chrome.log", "wb")
        self._process = subprocess.Popen(args, stdout=self._log, stderr=subprocess.STDOUT)
        self._port = self._wait_for_port()
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                self._process.wait(timeout=10)
        if self._log is not None:
            self._log.close()

    @property
    def port(self) -> int:
        return self._port

    def _wait_for_port(self, timeout: float = 30.0) -> int:
        port_file = self._profile / "DevToolsActivePort"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if port_file.exists():
                lines = port_file.read_text().splitlines()
                if lines and lines[0].strip().isdigit() and self._version(int(lines[0])):
                    return int(lines[0])
            if self._process is not None and self._process.poll() is not None:
                raise CaptureError(
                    f"Chrome exited (code {self._process.returncode}) before DevTools was ready; "
                    f"see {self._profile / 'chrome.log'}"
                )
            time.sleep(0.2)
        raise CaptureError("Chrome did not expose a DevTools port in time")

    def _version(self, port: int) -> dict[str, Any] | None:
        try:
            return _http_json(f"http://127.0.0.1:{port}/json/version", timeout=2.0)
        except (urllib.error.URLError, OSError, ValueError):
            return None

    def version(self) -> str:
        info = self._version(self._port) or {}
        return str(info.get("Browser", "unknown"))

    def new_page(self) -> CdpSession:
        target = _http_json(
            f"http://127.0.0.1:{self._port}/json/new?{urllib.parse.quote('about:blank')}",
            method="PUT",
        )
        ws_url = target.get("webSocketDebuggerUrl")
        if not ws_url:
            raise CaptureError("Chrome did not return a page WebSocket URL")
        return CdpSession(str(ws_url))


def _http_json(url: str, method: str = "GET", timeout: float = 5.0) -> dict[str, Any]:
    request = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


# ── Fixture-backed server ───────────────────────────────────────────────────


def ensure_workspace(root: Path, *, force: bool = False) -> dict[str, Any]:
    """Generate or reuse the demo fixture workspace under *root*."""
    if root.exists() and any(root.iterdir()) and not force:
        problems = demo_fixtures.verify_workspace(root)
        if problems:
            raise CaptureError(
                f"{root} is not a healthy fixture: {problems[0]} (re-run with --force)"
            )
        print(f"reusing fixture at {root}")
        return demo_fixtures.load_manifest(root)
    manifest = demo_fixtures.write_workspace(root, force=force)
    counts = manifest["counts"]
    print(f"generated fixture at {root} ({counts['total']} images, seed {manifest['seed']})")
    return manifest


class AppServer:
    """The Flask app, served against an isolated fixture workspace."""

    def __init__(self, workspace: Path, port: int = 0) -> None:
        self._workspace = workspace
        self._port = _preferred_port(workspace, port)
        self._process: subprocess.Popen[bytes] | None = None
        self._log: IO[bytes] | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    @property
    def log_path(self) -> Path:
        state_dir = self._workspace / demo_fixtures.RUNTIME_DIR / demo_fixtures.STATE_DIR
        return state_dir / "capture-server.log"

    def __enter__(self) -> AppServer:
        manifest = demo_fixtures.load_manifest(self._workspace)
        env = os.environ.copy()
        env.update({str(k): str(v) for k, v in manifest["env"].items()})
        env["SS_DCL_PORT"] = str(self._port)
        env["LITERT_BASE_URL"] = demo_fixtures.OFFLINE_LLM_URL
        env["SS_DCL_LOG_FILE"] = str(self.log_path)
        env["PYTHONPATH"] = os.pathsep.join([str(_SRC_DIR), env.get("PYTHONPATH", "")]).rstrip(
            os.pathsep
        )
        env["PYTHONUNBUFFERED"] = "1"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = open(self.log_path, "wb")
        self._process = subprocess.Popen(
            [sys.executable, "-c", _SERVER_BOOTSTRAP, str(self._port)],
            env=env,
            stdout=self._log,
            stderr=subprocess.STDOUT,
            cwd=str(_REPO_ROOT),
        )
        self._wait_until_ready()
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                self._process.wait(timeout=10)
        if self._log is not None:
            self._log.close()

    def _wait_until_ready(self, timeout: float = 30.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._process is not None and self._process.poll() is not None:
                raise CaptureError(
                    f"the fixture server exited with code {self._process.returncode}; "
                    f"see {self.log_path}"
                )
            try:
                health = _http_json(f"{self.base_url}/api/health", timeout=2.0)
            except (urllib.error.URLError, OSError, ValueError):
                time.sleep(0.2)
                continue
            if health.get("ok"):
                return
            time.sleep(0.2)
        raise CaptureError(f"the fixture server never became healthy; see {self.log_path}")


# ── Capture ─────────────────────────────────────────────────────────────────


@dataclass
class Shot:
    """One written baseline image."""

    path: Path
    viewport: Viewport
    state: CaptureState
    theme: str
    detail: str


def _theme_source(theme: str) -> str:
    return f"try {{ localStorage.setItem('ss-dcl-theme', {json.dumps(theme)}); }} catch (e) {{}}"


def capture(
    cdp: CdpSession,
    *,
    base_url: str,
    viewport: Viewport,
    state: CaptureState,
    out_dir: Path,
    theme: str,
    scale: int,
    settle: float,
    timeout: float,
) -> Shot:
    """Load the board at one viewport, apply one state, and write the PNG."""
    cdp.call(
        "Emulation.setDeviceMetricsOverride",
        {
            "width": viewport.width,
            "height": viewport.height,
            "deviceScaleFactor": scale,
            "mobile": False,
        },
    )
    cdp.call("Page.navigate", {"url": f"{base_url}/"})
    cdp.wait_for(_PAGE_READY, f"the board to load at {viewport.name}", timeout=timeout)
    detail = ""
    if state.prepare is not None:
        detail = state.prepare(cdp)
    time.sleep(settle)
    result = cdp.call("Page.captureScreenshot", {"format": "png", "fromSurface": True})
    data = base64.b64decode(result.get("data", ""))
    if not data:
        raise CaptureError(f"empty screenshot for {state.name}/{theme}")
    path = out_dir / f"{viewport.name}-{state.name}-{theme}.png"
    path.write_bytes(data)
    return Shot(path=path, viewport=viewport, state=state, theme=theme, detail=detail)


def write_index(out_dir: Path, shots: Sequence[Shot], *, chrome: str, base_url: str) -> Path:
    """Write the README that indexes the freshly captured baseline images."""
    lines = [
        "# UI baseline images (Phase 0)",
        "",
        "Generated by `tools/capture_ui_baseline.py` from the deterministic demo fixture in",
        "`tools/demo_fixtures.py`.",
        "",
        "The fixture renders every screenshot procedurally from a fixed seed, so these images",
        "contain no personal content and no file from the real Desktop. Captures run with",
        f"`LITERT_BASE_URL={demo_fixtures.OFFLINE_LLM_URL}` (LLM offline) and with",
        "`SS_DCL_DESKTOP` / `SS_DCL_HOME` pointed inside the fixture workspace.",
        "",
        "The images are a comparison baseline for later phases. The README media in",
        "`docs/assets/screenshot-sorted.png` and `docs/assets/screenshot-confirm.png` is",
        "deliberately left untouched until Phase 5.",
        "",
        "## Regenerate",
        "",
        "```sh",
        "uv run python tools/capture_ui_baseline.py --force",
        "```",
        "",
        "## Matrix",
        "",
        "| Image | Viewport | State | Theme | Captured as |",
        "| --- | --- | --- | --- | --- |",
    ]
    for shot in shots:
        lines.append(
            f"| [`{shot.path.name}`]({shot.path.name}) | {shot.viewport.name}"
            f" ({shot.viewport.role}) | {shot.state.name} | {shot.theme} |"
            f" {shot.detail or shot.state.description} |"
        )
    lines += [
        "",
        "## States",
        "",
    ]
    for state in STATES:
        scope = "every viewport" if state.all_viewports else "primary viewport"
        lines.append(f"- **{state.name}** ({scope}): {state.description}")
    lines += [
        "",
        "## Environment used for this capture",
        "",
        f"- Chrome: `{chrome}`",
        f"- App served from: `{base_url}`",
        "- Viewports: " + ", ".join(f"{v.name} ({v.role})" for v in VIEWPORTS),
        "- Themes: " + ", ".join(THEMES),
        "",
    ]
    path = out_dir / "README.md"
    path.write_text("\n".join(lines))
    return path


def _select(items: Sequence[Any], requested: str, attribute: str) -> list[Any]:
    if not requested.strip():
        return list(items)
    wanted = [part.strip() for part in requested.split(",") if part.strip()]
    available = {getattr(item, attribute): item for item in items}
    unknown = [name for name in wanted if name not in available]
    if unknown:
        raise CaptureError(
            f"unknown {attribute}(s): {', '.join(unknown)} (known: {', '.join(sorted(available))})"
        )
    return [available[name] for name in wanted]


def build_matrix(
    viewports: Sequence[Viewport], states: Sequence[CaptureState], themes: Sequence[str]
) -> list[tuple[Viewport, CaptureState, str]]:
    """Return the (viewport, state, theme) triples to capture, primary first."""
    matrix: list[tuple[Viewport, CaptureState, str]] = []
    for viewport in viewports:
        for state in states:
            if not state.all_viewports and viewport is not viewports[0]:
                continue
            for theme in themes:
                matrix.append((viewport, state, theme))
    return matrix


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Capture the Phase 0 UI baseline from the deterministic demo fixture. "
            "Never reads the real Desktop and never needs a language model."
        )
    )
    parser.add_argument(
        "--root", type=Path, default=demo_fixtures.DEFAULT_ROOT, help="fixture workspace root"
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="directory for the PNGs")
    parser.add_argument(
        "--url", default="", help="capture an already-running server instead of starting one"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="port for the fixture server (0 = the fixture's advertised port, else any free port)",
    )
    parser.add_argument("--states", default="", help="comma-separated state names")
    parser.add_argument("--themes", default="", help="comma-separated themes")
    parser.add_argument("--viewports", default="", help="comma-separated viewport names")
    parser.add_argument("--scale", type=int, default=2, help="device pixel ratio (default 2)")
    parser.add_argument("--settle", type=float, default=0.4, help="seconds to wait before a shot")
    parser.add_argument("--timeout", type=float, default=45.0, help="per-step timeout in seconds")
    parser.add_argument("--force", action="store_true", help="regenerate the fixture from scratch")
    parser.add_argument("--keep-profile", action="store_true", help="keep the Chrome profile")
    parser.add_argument("--list", action="store_true", help="print the capture matrix and exit")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        viewports = _select(VIEWPORTS, args.viewports, "name")
        states = _select(STATES, args.states, "name")
        themes: list[str] = [t for t in args.themes.split(",") if t.strip()] or list(THEMES)
        unknown_themes = [t for t in themes if t not in THEMES]
        if unknown_themes:
            raise CaptureError(
                f"unknown theme(s): {', '.join(unknown_themes)} (known: {', '.join(THEMES)})"
            )
    except CaptureError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    matrix = build_matrix(viewports, states, themes)
    if args.list:
        for viewport, state, theme in matrix:
            print(f"{viewport.name}\t{state.name}\t{theme}\t{state.description}")
        print(f"{len(matrix)} images")
        return 0

    chrome = find_chrome()
    if chrome is None:
        print(
            "No Chrome or Chromium installation found, so no images were captured.\n"
            "Set SS_DCL_CHROME=/path/to/chrome (or install Google Chrome) and run this "
            "command again; the fixture and the manual flow in "
            "docs/ui-inventory-phase0.md still work without it.",
            file=sys.stderr,
        )
        return 2

    try:
        args.out.mkdir(parents=True, exist_ok=True)
        shots: list[Shot] = []
        browser_version = "unknown"
        with contextlib.ExitStack() as stack:
            if args.url:
                base_url = args.url.rstrip("/")
                print(f"capturing {len(matrix)} images from {base_url}")
            else:
                workspace = Path(args.root).expanduser()
                ensure_workspace(workspace, force=args.force)
                server = stack.enter_context(AppServer(workspace, port=args.port))
                base_url = server.base_url
                print(f"fixture server on {base_url} (log: {server.log_path})")

            profile = Path(tempfile.mkdtemp(prefix="ss-dcl-chrome-"))
            if args.keep_profile:
                profile = DEFAULT_PROFILE
                shutil.rmtree(profile, ignore_errors=True)
            else:
                stack.callback(shutil.rmtree, profile, True)
            browser = stack.enter_context(ChromeSession(chrome, profile))
            page = browser.new_page()
            stack.callback(page.close)
            page.call("Page.enable")
            page.call("Runtime.enable")
            browser_version = browser.version()

            for theme in themes:
                injected = page.call(
                    "Page.addScriptToEvaluateOnNewDocument", {"source": _theme_source(theme)}
                )
                identifier = str(injected.get("identifier", ""))
                for viewport, state, shot_theme in build_matrix(viewports, states, [theme]):
                    shot = capture(
                        page,
                        base_url=base_url,
                        viewport=viewport,
                        state=state,
                        out_dir=args.out,
                        theme=shot_theme,
                        scale=args.scale,
                        settle=args.settle,
                        timeout=args.timeout,
                    )
                    shots.append(shot)
                    size_kb = shot.path.stat().st_size / 1024
                    print(f"  {shot.path.name} ({size_kb:.0f} KB) {shot.detail}".rstrip())
                if identifier:
                    page.call(
                        "Page.removeScriptToEvaluateOnNewDocument", {"identifier": identifier}
                    )

            if page.exceptions:
                print(f"warning: {len(page.exceptions)} page script error(s):", file=sys.stderr)
                for message in dict.fromkeys(page.exceptions):
                    print(f"  {message}", file=sys.stderr)

        index = write_index(args.out, shots, chrome=browser_version, base_url=base_url)
        total_mb = sum(shot.path.stat().st_size for shot in shots) / (1024 * 1024)
        print(f"wrote {len(shots)} images ({total_mb:.1f} MB) to {args.out}")
        print(f"index: {index}")
    except CaptureError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
