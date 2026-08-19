"""LiteRT HTTP contract tests against an in-process OpenAI-compatible stub (audit #95).

The real ``_call_litert_suggest`` / ``_litert_healthy`` code paths are driven
against a local werkzeug server that replays the LiteRT-LM response shape,
validating the HTTP contract without a real model or network. The opt-in
real-server tests live in test_litert_integration.py.
"""

import json
import threading

import flask
import pytest
from werkzeug.serving import make_server

import ss_dcl.llm as llm
import ss_dcl.settings as settings
from helpers import _make_png

stub = flask.Flask("litert-stub")
stub_state = {"posts": [], "fail": False, "malformed": False}


@stub.get("/v1/models")
def stub_models():
    if stub_state["fail"]:
        return flask.jsonify({"error": "boom"}), 500
    return flask.jsonify({"object": "list", "data": [{"id": "test-model"}]})


@stub.post("/v1/chat/completions")
def stub_completions():
    stub_state["posts"].append(flask.request.get_json(silent=True))
    if stub_state["fail"]:
        return flask.jsonify({"error": "boom"}), 500
    if stub_state["malformed"]:
        return "this is not json", 200
    reply = '{"filename": "Monthly Report"}'
    return flask.jsonify({"choices": [{"message": {"role": "assistant", "content": reply}}]})


class _StubServer:
    def __init__(self, app):
        self._server = make_server("127.0.0.1", 0, app)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}"

    def shutdown(self) -> None:
        self._server.shutdown()
        self._thread.join(timeout=2)


@pytest.fixture()
def litert_stub():
    stub_state["posts"] = []
    stub_state["fail"] = False
    stub_state["malformed"] = False
    server = _StubServer(stub)
    yield server
    server.shutdown()


@pytest.fixture()
def stub_client(client, monkeypatch, litert_stub):
    monkeypatch.setattr(llm, "LITERT_BASE_URL", litert_stub.url)
    llm.reset_health_cache()
    return client


def test_health_route_against_stub(stub_client):
    c, _ = stub_client
    r = c.get("/api/llm/health")
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_health_route_503_when_stub_errors(stub_client, litert_stub):
    c, _ = stub_client
    stub_state["fail"] = True
    llm.reset_health_cache()
    r = c.get("/api/llm/health")
    assert r.status_code == 503
    assert r.get_json()["ok"] is False


def test_suggest_route_contract_against_stub(stub_client):
    """Request shape: POST /v1/chat/completions, model field, streaming off."""
    c, desktop = stub_client
    (desktop / "Screenshot A.png").write_bytes(_make_png())
    c.get("/api/screenshots")
    fp = json.loads(c.get("/api/screenshots").data)[0]["fingerprint"]

    r = c.post(
        "/api/suggest-names",
        data=json.dumps({"fingerprints": [fp]}),
        content_type="application/json",
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["failures"] == []
    assert data["suggestions"][fp] == "monthly-report.png"

    assert len(stub_state["posts"]) == 1
    post = stub_state["posts"][0]
    assert post["model"] == settings.DEFAULT_LLM_MODEL
    assert post["stream"] is False
    assert post["max_tokens"] == 60
    assert post["response_format"] == {"type": "json_object"}
    content = post["messages"][0]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_suggest_direct_against_stub(litert_stub, monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "LITERT_BASE_URL", litert_stub.url)
    img = tmp_path / "Screenshot A.png"
    img.write_bytes(_make_png())
    name = llm._call_litert_suggest(img, "test-model", ".png")
    assert name == "monthly-report.png"


def test_suggest_malformed_json_returns_none(stub_client, litert_stub):
    stub_state["malformed"] = True
    c, desktop = stub_client
    (desktop / "Screenshot B.png").write_bytes(_make_png())
    c.get("/api/screenshots")
    fp = json.loads(c.get("/api/screenshots").data)[0]["fingerprint"]
    r = c.post(
        "/api/suggest-names",
        data=json.dumps({"fingerprints": [fp]}),
        content_type="application/json",
    )
    data = r.get_json()
    assert data["suggestions"] == {}
    assert fp in data["failures"]


def test_suggest_500_retries_then_fails(stub_client, litert_stub, monkeypatch):
    stub_state["fail"] = True
    monkeypatch.setattr("ss_dcl.llm.time.sleep", lambda _s: None)
    c, desktop = stub_client
    (desktop / "Screenshot C.png").write_bytes(_make_png())
    c.get("/api/screenshots")
    fp = json.loads(c.get("/api/screenshots").data)[0]["fingerprint"]
    r = c.post(
        "/api/suggest-names",
        data=json.dumps({"fingerprints": [fp]}),
        content_type="application/json",
    )
    assert r.get_json()["suggestions"] == {}
    assert fp in r.get_json()["failures"]
    assert len(stub_state["posts"]) == 3  # initial + 2 retries
