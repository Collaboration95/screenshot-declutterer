"""Tests for the LiteRT-LM provider integration.

Covers ``_call_litert_suggest`` (OpenAI-compatible client), the litert
health probe + ``/api/llm/health`` route, and image normalization to PNG
data URIs. All tests run offline — the network layer is monkeypatched.
"""

import json
import urllib.error
from pathlib import Path

import src.ss_dcl.app as flask_app
from PIL import Image

from helpers import _make_png


class _FakeResponse:
    """Minimal urllib response stand-in with .status, .read(), context mgmt."""

    def __init__(self, body: bytes, status: int = 200):
        self._body = body
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None


class _FakeHealthResponse(_FakeResponse):
    def __init__(self, status: int):
        super().__init__(b"{}", status)


def _openai_response(content: str) -> bytes:
    return json.dumps(
        {"choices": [{"message": {"role": "assistant", "content": content}}]}
    ).encode()


# ── _image_to_png_data_uri ────────────────────────────────────────────────


def test_image_to_png_data_uri_has_png_prefix(tmp_path):
    img = tmp_path / "shot.png"
    img.write_bytes(_make_png(20, 20))

    uri = flask_app._image_to_png_data_uri(img)
    assert uri.startswith("data:image/png;base64,")
    # PNG base64 of a 20x20 image should be small (well under 1 KB)
    assert len(uri) < 1024


def test_image_to_png_data_uri_normalizes_bmp(tmp_path):
    """A BMP whose raw base64 would be large collapses to a small PNG URI."""
    img = tmp_path / "shot.bmp"
    with Image.new("RGB", (200, 200), "blue") as im:
        im.save(img, "BMP")

    raw_b64 = len(__import__("base64").b64encode(img.read_bytes()))
    uri = flask_app._image_to_png_data_uri(img)

    assert uri.startswith("data:image/png;base64,")
    # 200x200 BMP ≈ 120 KB raw; PNG re-encode should be a fraction of that
    assert len(uri) < raw_b64 // 10


def test_image_to_png_data_uri_strips_alpha(tmp_path):
    """RGBA images are converted to RGB (some vision encoders reject alpha)."""
    img = tmp_path / "shot.png"
    with Image.new("RGBA", (10, 10), (255, 0, 0, 128)) as im:
        im.save(img, "PNG")

    uri = flask_app._image_to_png_data_uri(img)
    assert uri.startswith("data:image/png;base64,")


# ── _call_litert_suggest ──────────────────────────────────────────────────


def test_call_litert_suggest_parses_openai_response(tmp_path, monkeypatch):
    """Standard OpenAI chat.completions shape → sanitized name + extension."""
    img = tmp_path / "shot.png"
    img.write_bytes(_make_png(10, 10))

    monkeypatch.setattr(
        flask_app.urllib.request,
        "urlopen",
        lambda req, timeout=None: _FakeResponse(_openai_response("Q3 Budget Planning")),
    )

    result = flask_app._call_litert_suggest(img, "gemma4-e2b")
    assert result == "q3-budget-planning.png"


def test_call_litert_suggest_empty_choices_returns_none(tmp_path, monkeypatch):
    """A response with no choices is treated as a failure, not a crash."""
    img = tmp_path / "shot.png"
    img.write_bytes(_make_png(10, 10))

    monkeypatch.setattr(
        flask_app.urllib.request,
        "urlopen",
        lambda req, timeout=None: _FakeResponse(json.dumps({"choices": []}).encode()),
    )

    assert flask_app._call_litert_suggest(img, "gemma4-e2b") is None


def test_call_litert_suggest_missing_message_returns_none(tmp_path, monkeypatch):
    """choices[0] without a message.content yields None."""
    img = tmp_path / "shot.png"
    img.write_bytes(_make_png(10, 10))

    body = json.dumps({"choices": [{"message": {}}]}).encode()
    monkeypatch.setattr(
        flask_app.urllib.request, "urlopen", lambda req, timeout=None: _FakeResponse(body)
    )

    assert flask_app._call_litert_suggest(img, "gemma4-e2b") is None


def test_call_litert_suggest_fails_fast_on_connection_refused(tmp_path, monkeypatch):
    """Connection refused → no retries, returns None."""
    img = tmp_path / "shot.png"
    img.write_bytes(_make_png(10, 10))

    def mock_urlopen(req, timeout=None):
        raise urllib.error.URLError(ConnectionRefusedError(61, "Connection refused"))

    monkeypatch.setattr(flask_app.urllib.request, "urlopen", mock_urlopen)

    assert flask_app._call_litert_suggest(img, "gemma4-e2b") is None


def test_call_litert_suggest_succeeds_on_retry(tmp_path, monkeypatch):
    """Transient error then success → suggestion returned, two calls made."""
    img = tmp_path / "shot.png"
    img.write_bytes(_make_png(10, 10))

    call_count = 0

    def mock_urlopen(req, timeout=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise OSError("temporary failure")
        return _FakeResponse(_openai_response("retry-success"))

    monkeypatch.setattr(flask_app.urllib.request, "urlopen", mock_urlopen)
    monkeypatch.setattr(flask_app.time, "sleep", lambda s: None)

    result = flask_app._call_litert_suggest(img, "gemma4-e2b")
    assert result == "retry-success.png"
    assert call_count == 2


def test_call_litert_suggest_no_retry_on_bad_json(tmp_path, monkeypatch):
    """Malformed JSON fails fast (no retries)."""
    img = tmp_path / "shot.png"
    img.write_bytes(_make_png(10, 10))

    call_count = 0

    def mock_urlopen(req, timeout=None):
        nonlocal call_count
        call_count += 1
        return _FakeResponse(b"not json at all")

    monkeypatch.setattr(flask_app.urllib.request, "urlopen", mock_urlopen)
    monkeypatch.setattr(flask_app.time, "sleep", lambda s: None)

    assert flask_app._call_litert_suggest(img, "gemma4-e2b") is None
    assert call_count == 1


def test_call_litert_suggest_sends_openai_payload(tmp_path, monkeypatch):
    """The request body must use the OpenAI image_url content format."""
    img = tmp_path / "shot.png"
    img.write_bytes(_make_png(10, 10))

    captured = {}

    def mock_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data)
        return _FakeResponse(_openai_response("name"))

    monkeypatch.setattr(flask_app.urllib.request, "urlopen", mock_urlopen)

    flask_app._call_litert_suggest(img, "gemma4-e2b", ".jpg")

    assert captured["url"].endswith("/v1/chat/completions")
    body = captured["body"]
    assert body["model"] == "gemma4-e2b"
    content = body["messages"][0]["content"]
    assert content[0]["type"] == "text"
    assert content[0]["text"]
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


# ── _litert_healthy ───────────────────────────────────────────────────────


def test_litert_healthy_true_on_200(monkeypatch):
    monkeypatch.setattr(flask_app, "_litert_health_cache", None)
    monkeypatch.setattr(
        flask_app.urllib.request,
        "urlopen",
        lambda url, timeout=None: _FakeHealthResponse(200),
    )
    assert flask_app._litert_healthy() is True


def test_litert_healthy_false_on_connection_refused(monkeypatch):
    def mock_urlopen(url, timeout=None):
        raise urllib.error.URLError(ConnectionRefusedError(61, "Connection refused"))

    monkeypatch.setattr(flask_app, "_litert_health_cache", None)
    monkeypatch.setattr(flask_app.urllib.request, "urlopen", mock_urlopen)

    assert flask_app._litert_healthy() is False


def test_litert_healthy_caches_negative_verdict(monkeypatch):
    """A False verdict is cached for the TTL even if the server comes back."""
    calls = []

    def mock_urlopen(url, timeout=None):
        calls.append(1)
        raise urllib.error.URLError(ConnectionRefusedError(61, "Connection refused"))

    monkeypatch.setattr(flask_app, "_litert_health_cache", None)
    monkeypatch.setattr(flask_app.urllib.request, "urlopen", mock_urlopen)

    assert flask_app._litert_healthy() is False
    assert len(calls) == 1

    monkeypatch.setattr(
        flask_app.urllib.request,
        "urlopen",
        lambda url, timeout=None: _FakeHealthResponse(200),
    )
    assert flask_app._litert_healthy() is False  # served from cache


# ── /api/llm/health ───────────────────────────────────────────────────────


def test_api_llm_health_litert_ok(client, monkeypatch):
    c, _ = client
    c.put(
        "/api/settings",
        data=json.dumps({"llm_provider": "litert"}),
        content_type="application/json",
    )

    monkeypatch.setattr(flask_app, "_litert_healthy", lambda: True)
    r = c.get("/api/llm/health")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data["ok"] is True
    assert data["provider"] == "litert"
    assert data["error"] == ""


def test_api_llm_health_litert_down(client, monkeypatch):
    c, _ = client
    c.put(
        "/api/settings",
        data=json.dumps({"llm_provider": "litert"}),
        content_type="application/json",
    )

    monkeypatch.setattr(flask_app, "_litert_healthy", lambda: False)
    r = c.get("/api/llm/health")
    assert r.status_code == 503
    data = json.loads(r.data)
    assert data["ok"] is False
    assert data["provider"] == "litert"
    assert "litert" in data["error"].lower()


# ── end-to-end suggest with the litert provider ───────────────────────────


def test_suggest_names_with_litert_provider(client, monkeypatch):
    """Settings provider=litert + mocked LiteRT call → suggestions populated."""
    c, desktop = client
    f = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    f.write_bytes(_make_png(10, 10))

    r = c.get("/api/screenshots")
    fp = json.loads(r.data)[0]["fingerprint"]

    c.put(
        "/api/settings",
        data=json.dumps({"llm_provider": "litert", "llm_model": "gemma4-e2b"}),
        content_type="application/json",
    )

    def mock_litert(image_path, model, extension=".png"):
        assert model == "gemma4-e2b"
        return "budget-review" + extension

    monkeypatch.setattr(flask_app, "_call_litert_suggest", mock_litert)

    r = c.post(
        "/api/suggest-names",
        data=json.dumps({"fingerprints": [fp]}),
        content_type="application/json",
    )
    assert r.status_code == 200
    result = json.loads(r.data)
    assert result["suggestions"] == {fp: "budget-review.png"}

    memory = flask_app._get_memory()
    rec = memory.lookup(fp)
    assert rec.status == "suggested"
    assert rec.suggested_name == "budget-review.png"


# ── managed server process (Phase C) ───────────────────────────────────────


class _FakeProc:
    def __init__(self, pid: int = 12345):
        self.pid = pid


def _isolate_server_files(monkeypatch, tmp_path):
    """Point pidfile + log at temp paths so tests never touch ~/.ss-dcl."""
    monkeypatch.setattr(flask_app, "LITERT_PIDFILE", str(tmp_path / "litert.pid"))
    monkeypatch.setattr(flask_app, "LITERT_LOG_FILE", str(tmp_path / "litert.log"))


def test_litert_serve_cmd_resolves_via_path(monkeypatch):
    monkeypatch.setattr(flask_app.shutil, "which", lambda name: "/usr/local/bin/litert-lm")
    assert flask_app._litert_serve_cmd() == ["/usr/local/bin/litert-lm", "serve"]


def test_litert_serve_cmd_falls_back_to_venv(monkeypatch, tmp_path):
    venv_bin = tmp_path / "litert-lm" / ".venv" / "bin" / "litert-lm"
    venv_bin.parent.mkdir(parents=True)
    venv_bin.write_text("#!/bin/sh\n")
    monkeypatch.setattr(flask_app.shutil, "which", lambda name: None)
    monkeypatch.setattr(flask_app, "LITERT_VENV_FALLBACK", str(venv_bin))
    assert flask_app._litert_serve_cmd() == [str(venv_bin), "serve"]


def test_litert_serve_cmd_unresolved_keeps_tokens(monkeypatch, tmp_path):
    monkeypatch.setattr(flask_app.shutil, "which", lambda name: None)
    monkeypatch.setattr(flask_app, "LITERT_VENV_FALLBACK", str(tmp_path / "nope" / "litert-lm"))
    assert flask_app._litert_serve_cmd() == ["litert-lm", "serve"]


def test_start_when_already_healthy_skips_spawn(client, monkeypatch, tmp_path):
    c, _ = client
    _isolate_server_files(monkeypatch, tmp_path)
    c.put(
        "/api/settings",
        data=json.dumps({"llm_provider": "litert"}),
        content_type="application/json",
    )
    monkeypatch.setattr(flask_app, "_litert_healthy", lambda: True)

    def boom(*a, **k):
        raise AssertionError("must not spawn when healthy")

    monkeypatch.setattr(flask_app.subprocess, "Popen", boom)
    r = c.post("/api/llm/start")
    assert r.status_code == 200
    assert json.loads(r.data)["ok"] is True


def test_start_spawns_and_writes_pidfile(client, monkeypatch, tmp_path):
    c, _ = client
    _isolate_server_files(monkeypatch, tmp_path)
    c.put(
        "/api/settings",
        data=json.dumps({"llm_provider": "litert"}),
        content_type="application/json",
    )

    healths = iter([False, False, True])

    def fake_healthy():
        return next(healths, True)

    monkeypatch.setattr(flask_app, "_litert_healthy", fake_healthy)
    monkeypatch.setattr(flask_app.subprocess, "Popen", lambda *a, **k: _FakeProc(4242))
    monkeypatch.setattr(flask_app.time, "sleep", lambda s: None)

    r = c.post("/api/llm/start")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data["ok"] is True
    assert "4242" in data["message"]
    assert Path(tmp_path / "litert.pid").read_text().strip() == "4242"


def test_start_not_ready_within_timeout(client, monkeypatch, tmp_path):
    c, _ = client
    _isolate_server_files(monkeypatch, tmp_path)
    c.put(
        "/api/settings",
        data=json.dumps({"llm_provider": "litert"}),
        content_type="application/json",
    )
    monkeypatch.setattr(flask_app, "_litert_healthy", lambda: False)
    monkeypatch.setattr(flask_app.subprocess, "Popen", lambda *a, **k: _FakeProc(777))
    monkeypatch.setattr(flask_app.time, "sleep", lambda s: None)
    monkeypatch.setattr(flask_app, "LITERT_SERVE_READY_TIMEOUT", 0)  # deadline passes immediately

    r = c.post("/api/llm/start")
    assert r.status_code == 502
    data = json.loads(r.data)
    assert data["ok"] is False
    assert "not ready" in data["message"]


def test_start_refuses_when_live_pid_present(client, monkeypatch, tmp_path):
    """A recorded live-but-unresponsive pid blocks re-spawn (no double-spawn)."""
    c, _ = client
    _isolate_server_files(monkeypatch, tmp_path)
    (tmp_path / "litert.pid").write_text("9999")
    c.put(
        "/api/settings",
        data=json.dumps({"llm_provider": "litert"}),
        content_type="application/json",
    )
    monkeypatch.setattr(flask_app, "_litert_healthy", lambda: False)
    monkeypatch.setattr(flask_app, "_pid_alive", lambda pid: True)

    def boom(*a, **k):
        raise AssertionError("must not spawn when a live pid is recorded")

    monkeypatch.setattr(flask_app.subprocess, "Popen", boom)
    monkeypatch.setattr(flask_app.time, "sleep", lambda s: None)

    r = c.post("/api/llm/start")
    assert r.status_code == 502
    assert "double-spawn" in json.loads(r.data)["message"]


def test_stop_without_pidfile_returns_409(client, monkeypatch, tmp_path):
    c, _ = client
    _isolate_server_files(monkeypatch, tmp_path)
    r = c.post("/api/llm/stop")
    assert r.status_code == 409


def test_stop_cleans_stale_pidfile(client, monkeypatch, tmp_path):
    c, _ = client
    _isolate_server_files(monkeypatch, tmp_path)
    pidfile = tmp_path / "litert.pid"
    pidfile.write_text("4242")
    monkeypatch.setattr(flask_app, "_pid_alive", lambda pid: False)

    r = c.post("/api/llm/stop")
    assert r.status_code == 200
    assert json.loads(r.data)["ok"] is True
    assert not pidfile.exists()


def test_stop_terminates_recorded_pid(client, monkeypatch, tmp_path):
    c, _ = client
    _isolate_server_files(monkeypatch, tmp_path)
    pidfile = tmp_path / "litert.pid"
    pidfile.write_text("4242")
    # Alive on the first check, dead once the signal lands.
    alive = iter([True, False])
    monkeypatch.setattr(flask_app, "_pid_alive", lambda pid: next(alive))

    killed = []

    def fake_kill(pid, sig):
        killed.append((pid, sig))

    monkeypatch.setattr(flask_app.os, "kill", fake_kill)

    r = c.post("/api/llm/stop")
    assert r.status_code == 200
    assert killed == [(4242, flask_app.signal.SIGTERM)]
    assert not pidfile.exists()


def test_stop_refuses_foreign_pid(client, monkeypatch, tmp_path):
    c, _ = client
    _isolate_server_files(monkeypatch, tmp_path)
    (tmp_path / "litert.pid").write_text("4242")
    monkeypatch.setattr(flask_app, "_pid_alive", lambda pid: True)

    def fake_kill(pid, sig):
        raise PermissionError("not yours")

    monkeypatch.setattr(flask_app.os, "kill", fake_kill)

    r = c.post("/api/llm/stop")
    assert r.status_code == 403
