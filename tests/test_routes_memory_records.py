"""Integration tests for MemoryStore wired into Flask routes - enrichment slice (audit #93)."""

import json
from unittest.mock import patch

import ss_dcl.app as flask_app
import ss_dcl.categorize as categorize
import ss_dcl.llm as llm
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
    assert rec is not None
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
    with patch("ss_dcl.app.send2trash"):
        r = c.post(
            "/api/done",
            data=json.dumps({"filenames": [f.name]}),
            content_type="application/json",
        )
    assert r.status_code == 200

    # Check memory
    memory = flask_app._get_memory()
    rec = memory.lookup(fp)
    assert rec is not None
    assert rec is not None, f"Fingerprint {fp} should exist in memory"
    assert rec.status == "trashed"


def test_done_handles_files_not_in_memory(client):
    """Trashing a file not in memory should not crash."""
    c, desktop = client
    f = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    f.write_bytes(_make_png(10, 10))

    with patch("ss_dcl.app.send2trash"):
        r = c.post(
            "/api/done",
            data=json.dumps({"filenames": [f.name]}),
            content_type="application/json",
        )
    assert r.status_code == 200
    assert json.loads(r.data)["ok"] is True


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
    with patch("ss_dcl.app.send2trash"):
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


# ── Phase 4C: Auto-categorization ──────────────────────────────────────────


def test_extract_keywords_from_suggested_name():
    """extract_keywords parses kebab-case filename stems."""
    assert categorize.extract_keywords("foo-bar-baz.png") == ["foo", "bar", "baz"]


def test_extract_keywords_filters_short_words():
    """Words with length <= 2 are filtered out."""
    assert categorize.extract_keywords("a-b-cat.png") == ["cat"]


def test_suggest_category_no_decisions_returns_none(client):
    """Empty decisions → no categorization."""
    _, _t = client
    memory = flask_app._get_memory()
    result = categorize.suggest_category(["foo", "bar"], memory, {})
    assert result is None


def test_suggest_category_keep_when_keywords_match_kept(client):
    """Files marked 'keep' in decisions with matching keywords → 'keep'."""
    _, _t = client
    memory = flask_app._get_memory()

    # Create a memory record for a file that was kept
    rec = memory.record_file("kept-file.png", 100)
    rec.meta["keywords"] = ["customer", "onboarding"]

    decisions = {"kept-file.png": "keep"}
    result = categorize.suggest_category(["customer", "discussion"], memory, decisions)
    assert result == "keep"


def test_suggest_category_trash_when_keywords_match_trashed(client):
    """Files marked 'trash' in decisions with matching keywords → 'trash'."""
    _, _t = client
    memory = flask_app._get_memory()

    rec = memory.record_file("trashed-file.png", 200)
    rec.meta["keywords"] = ["meme", "funny"]

    decisions = {"trashed-file.png": "trash"}
    result = categorize.suggest_category(["funny", "joke"], memory, decisions)
    assert result == "trash"


def test_suggest_category_ignores_renamed_but_undecided(client):
    """A renamed (but undecided) file does not count as a keep signal."""
    _, _t = client
    memory = flask_app._get_memory()

    # Create a file that was renamed (not in decisions)
    rec = memory.record_file("renamed-file.png", 300)
    rec.meta["keywords"] = ["work", "report"]
    rec.status = "renamed"

    decisions = {}  # Not decided → should not contribute
    result = categorize.suggest_category(["work"], memory, decisions)
    assert result is None


def test_suggest_category_tie_returns_none(client):
    """Equal keep/trash scores → None."""
    _, _t = client
    memory = flask_app._get_memory()

    rec1 = memory.record_file("kept.png", 100)
    rec1.meta["keywords"] = ["shared"]
    rec2 = memory.record_file("trashed.png", 200)
    rec2.meta["keywords"] = ["shared"]

    decisions = {"kept.png": "keep", "trashed.png": "trash"}
    result = categorize.suggest_category(["shared"], memory, decisions)
    assert result is None


def test_build_keyword_scores_matches_legacy_path(client):
    """Precomputed scores must yield identical categories to the per-decision scan (issue #79)."""
    _, _t = client
    memory = flask_app._get_memory()

    rec1 = memory.record_file("kept-a.png", 100)
    rec1.meta["keywords"] = ["customer", "onboarding", "shared"]
    rec2 = memory.record_file("kept-b.png", 200)
    rec2.meta["keywords"] = ["customer"]
    rec3 = memory.record_file("trashed.png", 300)
    rec3.meta["keywords"] = ["meme", "shared"]

    decisions = {
        "kept-a.png": "keep",
        "kept-b.png": "keep",
        "trashed.png": "trash",
    }
    scores = categorize.build_keyword_scores(memory, decisions)

    for keywords in (
        ["customer"],
        ["customer", "onboarding", "meme"],
        ["shared"],
        ["shared", "meme"],
        ["unrelated"],
    ):
        legacy = categorize.suggest_category(keywords, memory, decisions)
        indexed = categorize.suggest_category(keywords, memory, decisions, scores)
        assert indexed == legacy, f"mismatch for {keywords}: {indexed} != {legacy}"

    assert scores == {
        "customer": (2, 0),
        "onboarding": (1, 0),
        "shared": (1, 1),
        "meme": (0, 1),
    }


def test_suggest_names_stores_keywords_in_meta(client, monkeypatch):
    """After LLM suggest, rec.meta.keywords is populated."""
    c, desktop = client
    f = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    f.write_bytes(_make_png(10, 10))

    r = c.get("/api/screenshots")
    fp = json.loads(r.data)[0]["fingerprint"]

    def mock_suggest(image_path, model, extension=".png"):
        return "customer-onboarding-discussion" + extension

    monkeypatch.setattr(llm, "_call_litert_suggest", mock_suggest)

    c.post(
        "/api/suggest-names",
        data=json.dumps({"fingerprints": [fp]}),
        content_type="application/json",
    )

    memory = flask_app._get_memory()
    rec = memory.lookup(fp)
    assert rec is not None
    assert rec.meta.get("keywords") == ["customer", "onboarding", "discussion"]


def test_screenshots_includes_suggested_category(client, monkeypatch):
    """Response includes suggested_category field."""
    c, desktop = client
    f = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    f.write_bytes(_make_png(10, 10))

    c.get("/api/screenshots")
    r = c.get("/api/screenshots")
    file_data = json.loads(r.data)[0]
    # Without any suggestion, field should be None
    assert "suggested_category" in file_data
    assert file_data["suggested_category"] is None
