"""Opt-in integration tests against a real LiteRT-LM server (audit #95).

Skipped unless ``SS_DCL_LITERT_URL`` is set (e.g.
``SS_DCL_LITERT_URL=http://localhost:9379 uv run pytest -m integration``).
"""

import json
import os

import pytest

import ss_dcl.llm as llm
from helpers import _make_png

pytestmark = pytest.mark.integration


@pytest.fixture()
def litert_url() -> str:
    url = os.environ.get("SS_DCL_LITERT_URL")
    if not url:
        pytest.skip("SS_DCL_LITERT_URL not set — opt-in integration test")
    return url


@pytest.fixture()
def live_client(client, monkeypatch, litert_url):
    monkeypatch.setattr(llm, "LITERT_BASE_URL", litert_url)
    llm.reset_health_cache()
    return client


def test_health_against_real_server(live_client):
    c, _ = live_client
    r = c.get("/api/llm/health")
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_suggest_roundtrip_against_real_server(live_client):
    c, desktop = live_client
    (desktop / "Screenshot Integration.png").write_bytes(_make_png())
    c.get("/api/screenshots")
    fp = json.loads(c.get("/api/screenshots").data)[0]["fingerprint"]

    r = c.post(
        "/api/suggest-names",
        data=json.dumps({"fingerprints": [fp]}),
        content_type="application/json",
    )
    assert r.status_code == 200
    data = r.get_json()
    if fp in data["failures"]:
        pytest.skip(f"server refused request: {data['failures']}")
    suggestion = data["suggestions"][fp]
    assert suggestion.endswith(".png")
