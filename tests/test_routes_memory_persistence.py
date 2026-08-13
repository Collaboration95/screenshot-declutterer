"""Integration tests for MemoryStore wired into Flask routes - persistence slice (audit #93)."""

import json
from unittest.mock import patch

import ss_dcl.app as flask_app

# ── Memory persistence across sessions ─────────────────────────────────────


def test_memory_survives_across_scan_cycles(client):
    c, desktop = client

    # Session 1: scan + trash a file
    (desktop / "Screenshot A.png").write_bytes(b"hello")
    r = c.get("/api/screenshots")
    fp = json.loads(r.data)[0]["fingerprint"]

    with patch("ss_dcl.app.send2trash"):
        c.post(
            "/api/done",
            data=json.dumps({"filenames": ["Screenshot A.png"]}),
            content_type="application/json",
        )

    # The trash loop removes the file from disk, so the file is gone now
    # Memory should still have the "trashed" record
    memory = flask_app._get_memory()
    rec = memory.lookup(fp)
    assert rec is not None
    assert rec is not None
    assert rec.status == "trashed"

    # Simulate a fresh app start: reset memory to force re-read from disk
    flask_app._reset_memory()
    memory2 = flask_app._get_memory()
    rec2 = memory2.lookup(fp)
    assert rec2 is not None
    assert rec2.status == "trashed"


def test_memory_persists_to_disk(client):
    c, desktop = client

    (desktop / "Screenshot A.png").write_bytes(b"hello")
    r = c.get("/api/screenshots")
    fp = json.loads(r.data)[0]["fingerprint"]

    # Manually update to "suggested" and save
    memory = flask_app._get_memory()
    memory.update_suggestion(fp, "test-suggestion.png")
    memory.save()

    # The MEMORY_FILE should exist on disk now
    memory_file = flask_app.MEMORY_FILE
    assert memory_file.exists()

    raw = json.loads(memory_file.read_text())
    assert "files" in raw
    assert fp in raw["files"]
    assert raw["files"][fp]["status"] == "suggested"
    assert raw["files"][fp]["suggested_name"] == "test-suggestion.png"
