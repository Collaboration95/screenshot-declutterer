"""Integration tests for MemoryStore wired into Flask routes (Phase 1B).

Tests that:
- /api/screenshots returns ``fingerprint`` and ``memory_status``
- New files get ``memory_status = "new"``, previously-seen get their existing status
- /api/rename updates memory (record_rename)
- /api/done updates memory (mark_trashed)
- /api/memory returns all recorded file data
- /api/suggest-names (stub) returns empty {}
- Memory survives across multiple requests in the same session
"""

import json

import src.ss_dcl.app as flask_app

from helpers import _make_png

# ── /api/screenshots enrichment ────────────────────────────────────────────


def test_screenshots_includes_fingerprint_and_memory_status(client):
    c, desktop = client
    (desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png").write_bytes(b"hello")

    r = c.get("/api/screenshots")
    data = json.loads(r.data)
    assert len(data) == 1
    assert data[0]["fingerprint"] == "Screenshot 2024-01-01 at 12.00.00 PM.png|5"
    assert data[0]["memory_status"] == "new"


def test_screenshots_new_file_gets_new_status(client):
    c, desktop = client
    (desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png").write_bytes(b"abc")

    r = c.get("/api/screenshots")
    file_data = json.loads(r.data)[0]
    assert file_data["memory_status"] == "new"


def test_screenshots_previously_seen_file_retains_status(client):
    c, desktop = client

    # First scan — file is new
    (desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png").write_bytes(b"hello")
    r1 = c.get("/api/screenshots")
    f1 = json.loads(r1.data)[0]
    assert f1["memory_status"] == "new"

    # Simulate LLM suggestion: update memory status directly
    memory = flask_app._get_memory()
    fp = "Screenshot 2024-01-01 at 12.00.00 PM.png|5"
    memory.update_suggestion(fp, "customer-onboarding.png")
    memory.save()

    # Reset memory store so next request re-reads from disk
    flask_app._reset_memory()

    # Second scan — file should retain "suggested" status
    r2 = c.get("/api/screenshots")
    f2 = json.loads(r2.data)[0]
    assert f2["memory_status"] == "suggested"


def test_screenshots_idempotent_scan_does_not_reset_suggested(client):
    c, desktop = client

    (desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png").write_bytes(b"data")
    # First call: records it as "new"
    c.get("/api/screenshots")

    # Manually set to "suggested" and persist
    memory = flask_app._get_memory()
    fp = "Screenshot 2024-01-01 at 12.00.00 PM.png|4"
    memory.update_suggestion(fp, "suggested-name.png")
    memory.save()
    flask_app._reset_memory()

    # Second call: should not reset to "new"
    r = c.get("/api/screenshots")
    file_data = json.loads(r.data)[0]
    assert file_data["memory_status"] == "suggested"


def test_screenshots_fingerprint_changes_on_size_change(client):
    c, desktop = client

    (desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png").write_bytes(b"hello")
    r = c.get("/api/screenshots")
    fp1 = json.loads(r.data)[0]["fingerprint"]
    assert fp1 == "Screenshot 2024-01-01 at 12.00.00 PM.png|5"

    # Overwrite with different size
    (desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png").write_bytes(b"hello world")
    flask_app._reset_memory()
    r2 = c.get("/api/screenshots")
    fp2 = json.loads(r2.data)[0]["fingerprint"]
    assert fp2 == "Screenshot 2024-01-01 at 12.00.00 PM.png|11"
    assert fp1 != fp2


def test_screenshots_multiple_files_all_enriched(client):
    c, desktop = client
    (desktop / "Screenshot A.png").write_bytes(b"aa")
    (desktop / "Screenshot B.png").write_bytes(b"bbb")

    r = c.get("/api/screenshots")
    files = json.loads(r.data)
    assert len(files) == 2
    for f in files:
        assert "fingerprint" in f
        assert "memory_status" in f
        assert f["memory_status"] == "new"


# ── /api/memory endpoint ───────────────────────────────────────────────────


def test_api_memory_returns_empty_when_no_files(client):
    c, _ = client
    r = c.get("/api/memory")
    data = json.loads(r.data)
    assert data == {"files": {}}


def test_api_memory_returns_recorded_files(client):
    c, desktop = client

    # Scan a file so it's recorded in memory
    (desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png").write_bytes(b"data")
    c.get("/api/screenshots")

    r = c.get("/api/memory")
    data = json.loads(r.data)
    assert "files" in data
    # Parsing the file size
    assert len(data["files"]) >= 1
    for _fp, entry in data["files"].items():
        assert "status" in entry
        assert "suggested_name" in entry
        assert "last_updated" in entry


def test_api_memory_reflects_status_changes(client):
    c, desktop = client

    (desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png").write_bytes(b"data")
    c.get("/api/screenshots")

    # Directly set to suggested
    memory = flask_app._get_memory()
    fp = "Screenshot 2024-01-01 at 12.00.00 PM.png|4"
    memory.update_suggestion(fp, "my-suggestion.png")
    memory.save()

    r = c.get("/api/memory")
    files = json.loads(r.data)["files"]
    entry = files.get(fp)
    assert entry is not None
    assert entry["status"] == "suggested"
    assert entry["suggested_name"] == "my-suggestion.png"


# ── /api/rename → memory update ────────────────────────────────────────────


def test_rename_updates_memory_status(client):
    c, desktop = client
    old = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    old.write_bytes(_make_png(10, 10))
    old_size = old.stat().st_size

    # First scan to record the file in memory
    c.get("/api/screenshots")

    # Rename it
    c.post(
        "/api/rename",
        data=json.dumps({"old_name": old.name, "new_name": "Screenshot renamed.png"}),
        content_type="application/json",
    )

    # Check memory updated
    memory = flask_app._get_memory()
    fp = f"{old.name}|{old_size}"
    rec = memory.lookup(fp)
    assert rec is not None, f"Fingerprint {fp} should exist in memory"
    assert rec.status == "renamed"
    assert rec.last_known_name == "Screenshot renamed.png"


def test_rename_to_ignored_file_is_robust(client):
    """If a file isn't in memory (e.g., old screenshot before Phase 1), rename shouldn't crash."""
    c, desktop = client
    f = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    f.write_bytes(_make_png(10, 10))

    # Skip scan — file not in memory
    r = c.post(
        "/api/rename",
        data=json.dumps({"old_name": f.name, "new_name": "Screenshot new.png"}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert json.loads(r.data)["ok"] is True


# ── /api/done → memory update ──────────────────────────────────────────────


def test_done_updates_memory_to_trashed(client):
    c, desktop = client
    f = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    f.write_bytes(_make_png(10, 10))

    # First scan to record the file in memory
    c.get("/api/screenshots")

    fp = f"Screenshot 2024-01-01 at 12.00.00 PM.png|{f.stat().st_size}"

    # Trash it
    from unittest.mock import patch

    with patch("src.ss_dcl.app.send2trash"):
        r = c.post(
            "/api/done",
            data=json.dumps({"filenames": [f.name]}),
            content_type="application/json",
        )
    assert r.status_code == 200

    # Check memory
    memory = flask_app._get_memory()
    rec = memory.lookup(fp)
    assert rec is not None, f"Fingerprint {fp} should exist in memory"
    assert rec.status == "trashed"


def test_done_handles_files_not_in_memory(client):
    """Trashing a file not in memory should not crash."""
    c, desktop = client
    f = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    f.write_bytes(_make_png(10, 10))

    from unittest.mock import patch

    with patch("src.ss_dcl.app.send2trash"):
        r = c.post(
            "/api/done",
            data=json.dumps({"filenames": [f.name]}),
            content_type="application/json",
        )
    assert r.status_code == 200
    assert json.loads(r.data)["ok"] is True


# ── /api/suggest-names (stub) ──────────────────────────────────────────────


def test_suggest_names_stub_returns_empty(client):
    c, _ = client
    r = c.post(
        "/api/suggest-names",
        data=json.dumps({"fingerprints": ["fp1", "fp2"]}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert json.loads(r.data) == {"suggestions": {}}


def test_suggest_names_rejects_non_json(client):
    c, _ = client
    r = c.post("/api/suggest-names", data="not json", content_type="text/plain")
    assert r.status_code == 400


def test_suggest_names_rejects_missing_fingerprints(client):
    c, _ = client
    r = c.post(
        "/api/suggest-names",
        data=json.dumps({}),
        content_type="application/json",
    )
    # fingerprints defaults to [] and is a list, so it passes validation
    assert r.status_code == 200
    assert json.loads(r.data) == {"suggestions": {}}


def test_suggest_names_rejects_non_list_fingerprints(client):
    c, _ = client
    r = c.post(
        "/api/suggest-names",
        data=json.dumps({"fingerprints": "not-a-list"}),
        content_type="application/json",
    )
    assert r.status_code == 400


# ── Memory persistence across sessions ─────────────────────────────────────


def test_memory_survives_across_scan_cycles(client):
    c, desktop = client

    # Session 1: scan + trash a file
    (desktop / "Screenshot A.png").write_bytes(b"hello")
    c.get("/api/screenshots")

    fp = "Screenshot A.png|5"

    from unittest.mock import patch

    with patch("src.ss_dcl.app.send2trash"):
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
    c.get("/api/screenshots")

    # Manually update to "suggested" and save
    memory = flask_app._get_memory()
    fp = "Screenshot A.png|5"
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


# ── Edge cases ─────────────────────────────────────────────────────────────


def test_screenshots_with_no_screenshot_files_still_works(client):
    c, desktop = client
    (desktop / "not-a-screenshot.png").write_bytes(b"hello")
    (desktop / "Screenshot 2024.txt").write_bytes(b"text")

    r = c.get("/api/screenshots")
    assert r.status_code == 200
    assert json.loads(r.data) == []


def test_memory_empty_after_no_screenshots(client):
    c, _ = client
    r = c.get("/api/memory")
    assert json.loads(r.data) == {"files": {}}


def test_screenshots_supports_non_png_extensions(client):
    c, desktop = client
    (desktop / "Screenshot 2024-01-01 at 12.00.00 PM.jpg").write_bytes(b"jpg-data")

    r = c.get("/api/screenshots")
    files = json.loads(r.data)
    assert len(files) == 1
    assert "fingerprint" in files[0]
    assert files[0]["memory_status"] == "new"
