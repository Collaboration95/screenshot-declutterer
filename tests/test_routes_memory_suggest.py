"""Integration tests for MemoryStore wired into Flask routes - suggest slice (audit #93)."""

import json
import socket
import time
import urllib.error
import urllib.request
from email.message import Message

import ss_dcl.app as flask_app
import ss_dcl.llm as llm
from helpers import _make_png

# ── /api/suggest-names (stub) ──────────────────────────────────────────────


def test_suggest_names_unknown_fingerprints_return_empty(client):
    """Fingerprints not in memory produce no suggestions (no crash)."""
    c, _ = client
    r = c.post(
        "/api/suggest-names",
        data=json.dumps({"fingerprints": ["fp1", "fp2"]}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert json.loads(r.data) == {"suggestions": {}, "failures": []}


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
    assert json.loads(r.data) == {"suggestions": {}, "failures": []}


def test_suggest_names_rejects_non_list_fingerprints(client):
    c, _ = client
    r = c.post(
        "/api/suggest-names",
        data=json.dumps({"fingerprints": "not-a-list"}),
        content_type="application/json",
    )
    assert r.status_code == 400


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

    # Mock the LiteRT call
    def mock_suggest(image_path, model, extension=".png"):
        return "customer-onboarding" + extension

    monkeypatch.setattr(llm, "_call_litert_suggest", mock_suggest)

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
    assert rec is not None
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

    monkeypatch.setattr(llm, "_call_litert_suggest", mock_suggest)

    r = c.post(
        "/api/suggest-names",
        data=json.dumps({"fingerprints": [fp]}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert json.loads(r.data) == {"suggestions": {}, "failures": []}
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

    monkeypatch.setattr(llm, "_call_litert_suggest", mock_suggest)

    r = c.post(
        "/api/suggest-names",
        data=json.dumps({"fingerprints": [fp]}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert json.loads(r.data) == {"suggestions": {}, "failures": [fp]}

    # Status should remain "new" (unchanged)
    memory = flask_app._get_memory()
    rec = memory.lookup(fp)
    assert rec is not None
    assert rec.status == "new"


def test_suggest_names_unknown_fingerprint_skipped(client, monkeypatch):
    c, _ = client
    r = c.post(
        "/api/suggest-names",
        data=json.dumps({"fingerprints": ["bogus|123"]}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert json.loads(r.data) == {"suggestions": {}, "failures": []}


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
    assert rec is not None
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
    assert rec is not None
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
    assert rec is not None
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
    rec = memory.lookup(fp)
    assert rec is not None
    assert rec.status == "ignored"


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


def test_sanitize_suggestion_basic(tmp_path):
    """Verify the sanitization logic produces safe filenames."""
    result = llm._sanitize_suggestion("  Hello World! This is GREAT  ")
    assert result == "hello-world-this-is-great.png"


def test_sanitize_suggestion_collapses_repeated_hyphens(tmp_path):
    """Multi-space / punctuation gaps should not produce '--'."""
    result = llm._sanitize_suggestion("foo   bar!!!baz")
    # "foo   bar!!!baz" → "foo---barbaz" → collapsed to "foo-barbaz"
    assert result == "foo-barbaz.png"
    assert "--" not in result


def test_sanitize_suggestion_strips_trailing_hyphen_after_truncation(tmp_path):
    """Truncation must not leave a trailing hyphen."""
    # A long string where the 120-char slice cuts right after a hyphen
    long_text = "a" * 119 + "-b"
    result = llm._sanitize_suggestion(long_text)
    assert result is not None
    assert not result.startswith("-")
    assert not result.rstrip(".png").endswith("-")


def test_sanitize_suggestion_preserves_extension(tmp_path):
    """The extension parameter is used, not hardcoded .png."""
    result = llm._sanitize_suggestion("sunny beach", extension=".jpg")
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

    monkeypatch.setattr(llm, "_call_litert_suggest", mock_suggest)

    r = c.post(
        "/api/suggest-names",
        data=json.dumps({"fingerprints": [fp]}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert json.loads(r.data)["suggestions"][fp] == "beach-photo.jpg"


# ── Phase 4D: LLM retry / error recovery ────────────────────────────────────


def test_suggest_names_returns_failures_list(client, monkeypatch):
    """Failures appear in response when LLM returns None."""
    c, desktop = client
    f = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    f.write_bytes(_make_png(10, 10))

    r = c.get("/api/screenshots")
    fp = json.loads(r.data)[0]["fingerprint"]

    def mock_suggest(image_path, model, extension=".png"):
        return None

    monkeypatch.setattr(llm, "_call_litert_suggest", mock_suggest)

    r = c.post(
        "/api/suggest-names",
        data=json.dumps({"fingerprints": [fp]}),
        content_type="application/json",
    )
    data = json.loads(r.data)
    assert data["suggestions"] == {}
    assert data["failures"] == [fp]


def test_suggest_names_parallelizes_llm_calls(client, monkeypatch):
    """Wall time must scale with worker count, not N (issue #81)."""
    c, desktop = client
    for i in range(4):
        f = desktop / f"Screenshot 2024-01-0{i + 1} at 12.00.00 PM.png"
        f.write_bytes(_make_png(10, 10))
    r = c.get("/api/screenshots")
    fps = [f["fingerprint"] for f in json.loads(r.data)]
    assert len(fps) == 4

    def slow_suggest(image_path, model, extension=".png"):
        time.sleep(0.3)
        return "suggestion" + extension

    monkeypatch.setattr(llm, "_call_litert_suggest", slow_suggest)

    t0 = time.monotonic()
    r = c.post(
        "/api/suggest-names",
        data=json.dumps({"fingerprints": fps}),
        content_type="application/json",
    )
    elapsed = time.monotonic() - t0

    data = json.loads(r.data)
    assert len(data["suggestions"]) == 4
    assert data["failures"] == []
    # Serial would take 4 * 0.3s = 1.2s; with 4 workers it must finish
    # well before the serial bound (generous 0.8s budget for CI noise).
    assert elapsed < 0.8, f"elapsed {elapsed:.2f}s suggests serial LLM calls"


def test_suggest_names_parallel_failure_preserved(client, monkeypatch):
    """Per-fingerprint failure reporting survives parallel execution."""
    c, desktop = client
    for i in range(3):
        f = desktop / f"Screenshot 2024-01-0{i + 1} at 12.00.00 PM.png"
        f.write_bytes(_make_png(10, 10))
    r = c.get("/api/screenshots")
    fps = [f["fingerprint"] for f in json.loads(r.data)]

    def flaky_suggest(image_path, model, extension=".png"):
        return None if "01-03" in image_path.name else "good" + extension

    monkeypatch.setattr(llm, "_call_litert_suggest", flaky_suggest)

    r = c.post(
        "/api/suggest-names",
        data=json.dumps({"fingerprints": fps}),
        content_type="application/json",
    )
    data = json.loads(r.data)
    assert len(data["suggestions"]) == 2
    assert len(data["failures"]) == 1
    assert data["failures"][0] == fps[2]


def test_suggest_names_empty_failures_on_success(client, monkeypatch):
    """failures: [] when all succeed."""
    c, desktop = client
    f = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    f.write_bytes(_make_png(10, 10))

    r = c.get("/api/screenshots")
    fp = json.loads(r.data)[0]["fingerprint"]

    def mock_suggest(image_path, model, extension=".png"):
        return "good-suggestion" + extension

    monkeypatch.setattr(llm, "_call_litert_suggest", mock_suggest)

    r = c.post(
        "/api/suggest-names",
        data=json.dumps({"fingerprints": [fp]}),
        content_type="application/json",
    )
    data = json.loads(r.data)
    assert data["failures"] == []
    assert fp in data["suggestions"]


def test_call_litert_suggest_retries_on_transient_error(tmp_path, monkeypatch):
    """Unrecognized URLError stays retryable — 3 attempts before giving up."""
    img = tmp_path / "test.png"
    img.write_bytes(_make_png(10, 10))

    call_count = 0

    def mock_urlopen(req, timeout=None):
        nonlocal call_count
        call_count += 1
        raise urllib.error.URLError("temporary failure")

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    monkeypatch.setattr(flask_app.time, "sleep", lambda s: None)

    result = llm._call_litert_suggest(img, "test-model")
    assert result is None
    assert call_count == 3  # initial + 2 retries = 3 attempts


def test_is_retryable_llm_error_classifier():
    """_is_retryable_llm_error classifies transient vs permanent errors."""
    # Not retryable: connection refused, DNS failure, 4xx (except 429)
    assert not llm._is_retryable_llm_error(ConnectionRefusedError(61, "Connection refused"))
    assert not llm._is_retryable_llm_error(
        urllib.error.URLError(ConnectionRefusedError(61, "Connection refused"))
    )
    assert not llm._is_retryable_llm_error(socket.gaierror())
    assert not llm._is_retryable_llm_error(
        urllib.error.HTTPError("http://x/api/chat", 404, "Not Found", Message(), None)
    )
    assert not llm._is_retryable_llm_error(
        urllib.error.HTTPError("http://x/api/chat", 400, "Bad Request", Message(), None)
    )

    # Retryable: timeouts, resets, broken pipes, 429, 5xx, unknown errors
    assert llm._is_retryable_llm_error(TimeoutError())
    assert llm._is_retryable_llm_error(TimeoutError())
    assert llm._is_retryable_llm_error(ConnectionResetError(54, "Connection reset by peer"))
    assert llm._is_retryable_llm_error(BrokenPipeError(32, "Broken pipe"))
    assert llm._is_retryable_llm_error(
        urllib.error.HTTPError("http://x/api/chat", 429, "Too Many Requests", Message(), None)
    )
    assert llm._is_retryable_llm_error(
        urllib.error.HTTPError("http://x/api/chat", 500, "Server Error", Message(), None)
    )
    assert llm._is_retryable_llm_error(urllib.error.URLError("temporary failure"))
    assert llm._is_retryable_llm_error(OSError("temporary failure"))


# ── Bug fix: category hint clearing ─────────────────────────────────────────


def test_accept_clears_suggested_category_in_meta(client):
    """Accepting a suggestion clears meta.suggested_category."""
    c, desktop = client
    f = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    f.write_bytes(_make_png(10, 10))

    r = c.get("/api/screenshots")
    fp = json.loads(r.data)[0]["fingerprint"]

    # Manually set suggested_category on the record
    memory = flask_app._get_memory()
    rec = memory.lookup(fp)
    assert rec is not None
    rec.suggested_name = "customer-onboarding.png"
    rec.meta["suggested_category"] = "keep"

    assert rec.meta.get("suggested_category") == "keep"

    c.post(
        "/api/accept-suggestion",
        data=json.dumps({"fingerprint": fp}),
        content_type="application/json",
    )

    rec = memory.lookup(fp)
    assert rec is not None
    assert rec.meta.get("suggested_category") is None


def test_reject_clears_suggested_category_in_meta(client):
    """Rejecting a suggestion clears meta.suggested_category."""
    c, desktop = client
    f = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    f.write_bytes(_make_png(10, 10))

    r = c.get("/api/screenshots")
    fp = json.loads(r.data)[0]["fingerprint"]

    memory = flask_app._get_memory()
    rec = memory.lookup(fp)
    assert rec is not None
    rec.meta["suggested_category"] = "keep"

    assert rec.meta.get("suggested_category") == "keep"

    c.post(
        "/api/reject-suggestion",
        data=json.dumps({"fingerprint": fp}),
        content_type="application/json",
    )

    rec = memory.lookup(fp)
    assert rec is not None
    assert rec.meta.get("suggested_category") is None


def test_rename_clears_suggested_category_in_meta(client):
    """Renaming a file clears meta.suggested_category."""
    c, desktop = client
    f = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    f.write_bytes(_make_png(10, 10))

    r = c.get("/api/screenshots")
    fp = json.loads(r.data)[0]["fingerprint"]

    memory = flask_app._get_memory()
    rec = memory.lookup(fp)
    assert rec is not None
    rec.meta["suggested_category"] = "trash"

    assert rec.meta.get("suggested_category") == "trash"

    c.post(
        "/api/rename",
        data=json.dumps(
            {
                "old_name": f.name,
                "new_name": "renamed-screenshot.png",
            }
        ),
        content_type="application/json",
    )

    rec = memory.lookup(fp)
    assert rec is not None
    assert rec.meta.get("suggested_category") is None


def test_accept_clears_category_hint_in_frontend(client, monkeypatch):
    """acceptSuggestion() must remove .category-hint-* class and dataset."""
    c, _ = client
    r = c.get("/static/app.js")
    assert r.status_code == 200
    # acceptSuggestion path
    assert b"category-hint-keep" in r.data
    assert b"category-hint-trash" in r.data
    # Must appear in the accept path (after the badge removal comment)
    assert b"delete card.dataset.suggestedCategory" in r.data


def test_reject_clears_category_hint_in_frontend(client):
    """rejectSuggestion() must remove .category-hint-* class and dataset."""
    c, _ = client
    r = c.get("/static/app.js")
    assert r.status_code == 200
    # rejectSuggestion references remove + delete after the badge removal
    # Count: helper applyRenameToCard + rejectSuggestion
    assert r.data.count(b"delete card.dataset.suggestedCategory") >= 2


def test_rename_clears_category_hint_in_frontend(client):
    """All rename paths must clear the category hint class and dataset."""
    c, _ = client
    r = c.get("/static/app.js")
    assert r.status_code == 200
    # 2 occurrences: shared applyRenameToCard helper + rejectSuggestion
    # (all three rename sites go through applyRenameToCard — issue #101)
    assert r.data.count(b"delete card.dataset.suggestedCategory") >= 2
    # The shared helper is used by the rename paths
    assert b"applyRenameToCard(renameTarget, oldName, newName)" in r.data
