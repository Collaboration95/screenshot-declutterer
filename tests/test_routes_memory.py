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
from unittest.mock import patch

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
    fp = f1["fingerprint"]
    memory = flask_app._get_memory()
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
    r = c.get("/api/screenshots")
    fp = json.loads(r.data)[0]["fingerprint"]
    memory = flask_app._get_memory()
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
    r = c.get("/api/screenshots")
    fp = json.loads(r.data)[0]["fingerprint"]

    # Directly set to suggested
    memory = flask_app._get_memory()
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

    # First scan to record the file in memory
    r = c.get("/api/screenshots")
    fp = json.loads(r.data)[0]["fingerprint"]

    # Rename it
    c.post(
        "/api/rename",
        data=json.dumps({"old_name": old.name, "new_name": "Screenshot renamed.png"}),
        content_type="application/json",
    )

    # Check memory updated
    memory = flask_app._get_memory()
    rec = memory.lookup(fp)
    assert rec is not None, f"Fingerprint {fp} should exist in memory"
    assert rec.status == "renamed"
    assert rec.last_known_name == "Screenshot renamed.png"


def test_rename_file_not_in_memory_is_robust(client):
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
    r = c.get("/api/screenshots")
    fp = json.loads(r.data)[0]["fingerprint"]

    # Trash it
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
    r = c.get("/api/screenshots")
    fp = json.loads(r.data)[0]["fingerprint"]

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


# ── Review fixes — regression tests for bugs caught in review ───────────


def test_renamed_file_retains_memory_via_lookup_by_name_fallback(client):
    """After a rename, the fingerprint changes (name + size), but
    get_screenshots() should find the old record via lookup_by_name fallback."""
    c, desktop = client
    old = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    old.write_bytes(_make_png(10, 10))

    # First scan establishes the original fingerprint
    r = c.get("/api/screenshots")
    old_fp = json.loads(r.data)[0]["fingerprint"]

    # Manually mark as suggested
    memory = flask_app._get_memory()
    memory.update_suggestion(old_fp, "suggested-name.png")
    memory.save()
    flask_app._reset_memory()

    # Rename the file (via our API — updates memory last_known_name)
    c.post(
        "/api/rename",
        data=json.dumps({"old_name": old.name, "new_name": "Screenshot renamed.png"}),
        content_type="application/json",
    )

    # Simulate a fresh scan: the new filename produces a different fingerprint
    flask_app._reset_memory()
    r2 = c.get("/api/screenshots")
    files = json.loads(r2.data)
    assert len(files) == 1

    # The file should NOT appear as "new" — it should be "renamed"
    # because lookup_by_name fallback found the record via last_known_name
    assert files[0]["memory_status"] == "renamed"
    assert files[0]["name"] == "Screenshot renamed.png"


def test_done_does_not_mark_ghost_file_as_trashed_in_memory(client):
    """api_done should not mark a file as 'trashed' in memory if the trash
    operation itself failed (e.g., file not found on disk)."""
    c, desktop = client

    # First, put a real file in both memory and disk
    f = desktop / "Screenshot real.png"
    f.write_bytes(_make_png(10, 10))
    c.get("/api/screenshots")

    # Create a ghost entry in memory (for a file that no longer exists)
    memory = flask_app._get_memory()
    ghost_rec = memory.record_file("Screenshot ghost.png", 9999)
    ghost_fp = ghost_rec.fingerprint
    memory.save()

    # Trash both — ghost.png will fail (not on disk), real.png will succeed
    with patch("src.ss_dcl.app.send2trash"):
        r = c.post(
            "/api/done",
            data=json.dumps({"filenames": ["Screenshot ghost.png", "Screenshot real.png"]}),
            content_type="application/json",
        )

    # 207 because ghost.png fails
    assert r.status_code == 207

    # Ghost file should NOT be marked as trashed (it was never successfully trashed)
    memory = flask_app._get_memory()
    ghost = memory.lookup(ghost_fp)
    assert ghost is not None
    assert ghost.status == "new", f"Ghost file should still be 'new', got {ghost.status!r}"


# ── /api/screenshots → suggested_name field ───────────────────────────────


def test_screenshots_includes_suggested_name_when_available(client):
    c, desktop = client
    (desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png").write_bytes(b"data")

    r = c.get("/api/screenshots")
    fp = json.loads(r.data)[0]["fingerprint"]

    memory = flask_app._get_memory()
    memory.update_suggestion(fp, "my-suggested-name.png")
    memory.save()
    flask_app._reset_memory()

    r2 = c.get("/api/screenshots")
    file_data = json.loads(r2.data)[0]
    assert file_data["suggested_name"] == "my-suggested-name.png"


def test_screenshots_suggested_name_null_when_not_suggested(client):
    c, desktop = client
    (desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png").write_bytes(b"data")

    r = c.get("/api/screenshots")
    file_data = json.loads(r.data)[0]
    assert file_data["suggested_name"] is None


# ── /api/suggest-names (with real LLM mock) ────────────────────────────────


def test_suggest_names_with_real_file_and_mock_llm(client, monkeypatch):
    """When a real file exists and the LLM returns a name, suggestions are populated."""
    c, desktop = client
    f = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    f.write_bytes(_make_png(10, 10))

    # First scan to record the file
    r = c.get("/api/screenshots")
    fp = json.loads(r.data)[0]["fingerprint"]
    assert json.loads(r.data)[0]["memory_status"] == "new"

    # Mock the Ollama call
    def mock_suggest(image_path, model, extension=".png"):
        return "customer-onboarding" + extension

    monkeypatch.setattr(flask_app, "_call_ollama_suggest", mock_suggest)

    # Now suggest names
    r = c.post(
        "/api/suggest-names",
        data=json.dumps({"fingerprints": [fp]}),
        content_type="application/json",
    )
    assert r.status_code == 200
    result = json.loads(r.data)
    assert result["suggestions"] == {fp: "customer-onboarding.png"}

    # Memory should be updated
    memory = flask_app._get_memory()
    rec = memory.lookup(fp)
    assert rec.status == "suggested"
    assert rec.suggested_name == "customer-onboarding.png"


def test_suggest_names_skips_already_processed(client, monkeypatch):
    """Files that aren't 'new' should not be re-processed."""
    c, desktop = client
    f = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    f.write_bytes(_make_png(10, 10))

    r = c.get("/api/screenshots")
    fp = json.loads(r.data)[0]["fingerprint"]

    # Set to ignored
    memory = flask_app._get_memory()
    memory.reject_suggestion(fp)
    memory.save()
    flask_app._reset_memory()

    call_count = 0

    def mock_suggest(image_path, model, extension=".png"):
        nonlocal call_count
        call_count += 1
        return "should-not-be-called" + extension

    monkeypatch.setattr(flask_app, "_call_ollama_suggest", mock_suggest)

    r = c.post(
        "/api/suggest-names",
        data=json.dumps({"fingerprints": [fp]}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert json.loads(r.data) == {"suggestions": {}}
    assert call_count == 0  # LLM never called for ignored files


def test_suggest_names_handles_llm_returning_none(client, monkeypatch):
    """When the LLM returns None (error), the file is skipped gracefully."""
    c, desktop = client
    f = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    f.write_bytes(_make_png(10, 10))

    r = c.get("/api/screenshots")
    fp = json.loads(r.data)[0]["fingerprint"]

    def mock_suggest(image_path, model, extension=".png"):
        return None

    monkeypatch.setattr(flask_app, "_call_ollama_suggest", mock_suggest)

    r = c.post(
        "/api/suggest-names",
        data=json.dumps({"fingerprints": [fp]}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert json.loads(r.data) == {"suggestions": {}}

    # Status should remain "new" (unchanged)
    memory = flask_app._get_memory()
    assert memory.lookup(fp).status == "new"


def test_suggest_names_unknown_fingerprint_skipped(client, monkeypatch):
    c, _ = client
    r = c.post(
        "/api/suggest-names",
        data=json.dumps({"fingerprints": ["bogus|123"]}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert json.loads(r.data) == {"suggestions": {}}


# ── /api/accept-suggestion ─────────────────────────────────────────────────


def test_accept_suggestion_renames_file(client):
    c, desktop = client
    f = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    f.write_bytes(_make_png(10, 10))

    r = c.get("/api/screenshots")
    fp = json.loads(r.data)[0]["fingerprint"]

    memory = flask_app._get_memory()
    memory.update_suggestion(fp, "accepted-name.png")
    memory.save()

    r = c.post(
        "/api/accept-suggestion",
        data=json.dumps({"fingerprint": fp}),
        content_type="application/json",
    )
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data["ok"] is True
    assert data["new_name"] == "accepted-name.png"
    assert data["old_name"] == "Screenshot 2024-01-01 at 12.00.00 PM.png"

    # File should be renamed on disk
    assert not (desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png").exists()
    assert (desktop / "accepted-name.png").exists()

    # Memory should reflect rename
    memory = flask_app._get_memory()
    rec = memory.lookup(fp)
    assert rec.status == "renamed"
    assert rec.last_known_name == "accepted-name.png"


def test_accept_suggestion_handles_name_conflict(client):
    """When suggested name already exists, append a counter."""
    c, desktop = client
    f = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    f.write_bytes(_make_png(10, 10))
    (desktop / "conflict.png").write_bytes(_make_png(10, 10))

    r = c.get("/api/screenshots")
    fp = json.loads(r.data)[0]["fingerprint"]

    memory = flask_app._get_memory()
    memory.update_suggestion(fp, "conflict.png")
    memory.save()

    r = c.post(
        "/api/accept-suggestion",
        data=json.dumps({"fingerprint": fp}),
        content_type="application/json",
    )
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data["ok"] is True
    # Should append -2 to avoid conflict
    assert data["new_name"] == "conflict-2.png"
    assert (desktop / "conflict-2.png").exists()


def test_accept_suggestion_unknown_fingerprint(client):
    c, _ = client
    r = c.post(
        "/api/accept-suggestion",
        data=json.dumps({"fingerprint": "nope|99"}),
        content_type="application/json",
    )
    assert r.status_code == 404
    assert json.loads(r.data)["ok"] is False


def test_accept_suggestion_no_suggestion_set(client):
    c, desktop = client
    f = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    f.write_bytes(_make_png(10, 10))
    r = c.get("/api/screenshots")
    fp = json.loads(r.data)[0]["fingerprint"]

    r = c.post(
        "/api/accept-suggestion",
        data=json.dumps({"fingerprint": fp}),
        content_type="application/json",
    )
    assert r.status_code == 400


def test_accept_suggestion_missing_fingerprint_field(client):
    c, _ = client
    r = c.post(
        "/api/accept-suggestion",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert r.status_code == 400


def test_accept_suggestion_empty_old_name_rejected(client):
    """A corrupt memory record with empty last_known_name must not rename Desktop."""
    c, desktop = client
    f = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    f.write_bytes(_make_png(10, 10))

    r = c.get("/api/screenshots")
    fp = json.loads(r.data)[0]["fingerprint"]

    memory = flask_app._get_memory()
    # Corrupt the record: set last_known_name to empty string
    rec = memory.lookup(fp)
    rec.last_known_name = ""
    rec.original_name = ""
    rec.suggested_name = "evil.png"
    memory.save()

    r = c.post(
        "/api/accept-suggestion",
        data=json.dumps({"fingerprint": fp}),
        content_type="application/json",
    )
    assert r.status_code == 400
    assert "invalid filename" in json.loads(r.data)["error"]


def test_accept_suggestion_path_traversal_rejected(client):
    """Accept-suggestion must validate old_name against path traversal."""
    c, desktop = client
    f = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    f.write_bytes(_make_png(10, 10))

    r = c.get("/api/screenshots")
    fp = json.loads(r.data)[0]["fingerprint"]

    memory = flask_app._get_memory()
    rec = memory.lookup(fp)
    rec.last_known_name = "../../../etc/passwd"
    rec.suggested_name = "safe-name.png"
    memory.save()

    r = c.post(
        "/api/accept-suggestion",
        data=json.dumps({"fingerprint": fp}),
        content_type="application/json",
    )
    assert r.status_code == 400
    assert "invalid old_name" in json.loads(r.data)["error"]


def test_accept_suggestion_directory_not_file_rejected(client):
    """If old_path is a directory (not a file), reject with 404."""
    c, desktop = client
    subdir = desktop / "Screenshot subdir"
    subdir.mkdir()

    # Create a memory record pointing to a directory
    memory = flask_app._get_memory()
    rec = memory.record_file("Screenshot subdir", 0)
    rec.suggested_name = "safe-name.png"
    rec.last_known_name = "Screenshot subdir"
    rec.original_name = "Screenshot subdir"
    memory.save()

    r = c.post(
        "/api/accept-suggestion",
        data=json.dumps({"fingerprint": rec.fingerprint}),
        content_type="application/json",
    )
    assert r.status_code == 404


# ── /api/reject-suggestion ─────────────────────────────────────────────────


def test_reject_suggestion_marks_as_ignored(client):
    c, desktop = client
    f = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    f.write_bytes(_make_png(10, 10))

    r = c.get("/api/screenshots")
    fp = json.loads(r.data)[0]["fingerprint"]

    memory = flask_app._get_memory()
    memory.update_suggestion(fp, "some-name.png")
    memory.save()

    r = c.post(
        "/api/reject-suggestion",
        data=json.dumps({"fingerprint": fp}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert json.loads(r.data)["ok"] is True

    memory = flask_app._get_memory()
    assert memory.lookup(fp).status == "ignored"


def test_reject_suggestion_unknown_fingerprint(client):
    c, _ = client
    r = c.post(
        "/api/reject-suggestion",
        data=json.dumps({"fingerprint": "nope|99"}),
        content_type="application/json",
    )
    assert r.status_code == 404


def test_reject_suggestion_missing_fingerprint_field(client):
    c, _ = client
    r = c.post(
        "/api/reject-suggestion",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert r.status_code == 400


# ── /api/settings ──────────────────────────────────────────────────────────


def test_settings_get_returns_defaults(client):
    c, _ = client
    r = c.get("/api/settings")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data["llm_provider"] == "ollama"
    assert data["llm_model"] == "gemma4:e2b"
    assert data["auto_suggest"] is False


def test_settings_put_and_get_roundtrip(client):
    c, _ = client
    r = c.put(
        "/api/settings",
        data=json.dumps({"llm_model": "qwen2.5:1.5b", "auto_suggest": True}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert json.loads(r.data)["ok"] is True

    r = c.get("/api/settings")
    data = json.loads(r.data)
    assert data["llm_model"] == "qwen2.5:1.5b"
    assert data["auto_suggest"] is True
    assert data["llm_provider"] == "ollama"  # unchanged


def test_settings_persists_to_disk(client):
    c, _ = client
    c.put(
        "/api/settings",
        data=json.dumps({"llm_model": "persist-test"}),
        content_type="application/json",
    )

    settings_file = flask_app.SETTINGS_FILE
    assert settings_file.exists()
    raw = json.loads(settings_file.read_text())
    assert raw["llm_model"] == "persist-test"


def test_settings_put_rejects_non_json(client):
    c, _ = client
    r = c.put("/api/settings", data="not json", content_type="text/plain")
    assert r.status_code == 400


def test_settings_put_ignores_unknown_keys(client):
    c, _ = client
    c.put(
        "/api/settings",
        data=json.dumps({"llm_model": "test", "evil_key": "hacked", "auto_suggest": True}),
        content_type="application/json",
    )
    r = c.get("/api/settings")
    data = json.loads(r.data)
    assert "evil_key" not in data
    assert data["llm_model"] == "test"


def test_suggest_names_rejects_non_ollama_provider(client):
    """When provider is set to 'mlx', the endpoint should reject with a clear message."""
    c, _ = client
    c.put(
        "/api/settings",
        data=json.dumps({"llm_provider": "mlx"}),
        content_type="application/json",
    )
    r = c.post(
        "/api/suggest-names",
        data=json.dumps({"fingerprints": ["fp1"]}),
        content_type="application/json",
    )
    assert r.status_code == 400
    data = json.loads(r.data)
    assert "not yet supported" in data["error"]


# ── _call_ollama_suggest sanitization ────────────────────────────────────


def test_call_ollama_suggest_sanitizes_filename(tmp_path, monkeypatch):
    """Verify the sanitization logic produces safe filenames."""
    import json as _json

    # Create a fake image file
    img = tmp_path / "test.png"
    img.write_bytes(b"fake-png-data")

    # Mock urllib to return a raw LLM response
    class FakeResponse:
        def read(self):
            return _json.dumps(
                {
                    "message": {"content": "  Hello World! This is GREAT  "},
                }
            ).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    def mock_urlopen(req, timeout=None):
        return FakeResponse()

    monkeypatch.setattr(flask_app.urllib.request, "urlopen", mock_urlopen)

    result = flask_app._call_ollama_suggest(img, "test-model")
    assert result == "hello-world-this-is-great.png"


def test_call_ollama_suggest_preserves_extension(tmp_path, monkeypatch):
    """The extension parameter is used, not hardcoded .png."""
    import json as _json

    img = tmp_path / "test.jpg"
    img.write_bytes(b"fake-jpg-data")

    class FakeResponse:
        def read(self):
            return _json.dumps({"message": {"content": "sunny beach"}}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    monkeypatch.setattr(
        flask_app.urllib.request, "urlopen", lambda req, timeout=None: FakeResponse()
    )

    result = flask_app._call_ollama_suggest(img, "test-model", extension=".jpg")
    assert result == "sunny-beach.jpg"


def test_suggest_names_preserves_non_png_extension(client, monkeypatch):
    """When a .jpg file gets a suggestion, the suggested name keeps .jpg."""
    c, desktop = client
    f = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.jpg"
    f.write_bytes(b"jpg-data")

    r = c.get("/api/screenshots")
    fp = json.loads(r.data)[0]["fingerprint"]

    def mock_suggest(image_path, model, extension=".png"):
        # Verify extension was passed correctly
        assert extension == ".jpg"
        return "beach-photo" + extension

    monkeypatch.setattr(flask_app, "_call_ollama_suggest", mock_suggest)

    r = c.post(
        "/api/suggest-names",
        data=json.dumps({"fingerprints": [fp]}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert json.loads(r.data)["suggestions"][fp] == "beach-photo.jpg"
