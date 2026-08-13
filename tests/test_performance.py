"""Performance/load benchmarks for the hot paths (audit #94).

Marked ``perf`` and excluded from the default suite (see pyproject.toml
addopts). Run explicitly with: ``uv run pytest -m perf``.

Bounds are deliberately generous — they exist to catch algorithmic
regressions (e.g. O(FxDxR) rescans, serial suggest), not to benchmark
the machine.
"""

import json
import time
from unittest.mock import patch

import pytest

from helpers import _make_png

pytestmark = pytest.mark.perf

SCAN_COUNT = 500
THUMB_COUNT = 50
SUGGEST_COUNT = 50


def _seed_files(desktop, count, prefix="Screenshot"):
    for i in range(count):
        (desktop / f"{prefix} {i:04d}.png").write_bytes(_make_png())


def test_scan_500_files_within_budget(client):
    c, desktop = client
    _seed_files(desktop, SCAN_COUNT)
    start = time.perf_counter()
    r = c.get("/api/screenshots")
    elapsed = time.perf_counter() - start
    assert r.status_code == 200
    data = json.loads(r.data)
    assert len(data) == SCAN_COUNT
    assert elapsed < 3.0, f"/api/screenshots took {elapsed:.2f}s for {SCAN_COUNT} files"


def test_batch_thumbnail_generation_within_budget(client):
    c, desktop = client
    _seed_files(desktop, THUMB_COUNT)
    start = time.perf_counter()
    for i in range(THUMB_COUNT):
        r = c.get(f"/api/thumb/Screenshot%20{i:04d}.png")
        assert r.status_code == 200
    elapsed = time.perf_counter() - start
    assert elapsed < 3.0, f"{THUMB_COUNT} thumbnail generations took {elapsed:.2f}s"


def test_suggest_50_files_with_mock_llm_within_budget(client):
    c, desktop = client
    _seed_files(desktop, SUGGEST_COUNT)
    c.get("/api/screenshots")
    fps = [f["fingerprint"] for f in json.loads(c.get("/api/screenshots").data)]

    with patch(
        "ss_dcl.llm._call_litert_suggest",
        side_effect=lambda path, model, extension=".png": (time.sleep(0.01), "suggested.png")[1],
    ):
        start = time.perf_counter()
        r = c.post(
            "/api/suggest-names",
            data=json.dumps({"fingerprints": fps}),
            content_type="application/json",
        )
        elapsed = time.perf_counter() - start

    assert r.status_code == 200
    data = json.loads(r.data)
    assert len(data["suggestions"]) == SUGGEST_COUNT
    assert data["failures"] == []
    assert elapsed < 3.0, f"suggest for {SUGGEST_COUNT} files took {elapsed:.2f}s"
