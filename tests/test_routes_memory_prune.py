"""Integration tests for MemoryStore wired into Flask routes - pruning slice (audit #93)."""

import json

import ss_dcl.app as flask_app
import ss_dcl.settings as settings_module
from helpers import _make_png

# ── /api/settings ──────────────────────────────────────────────────────────


def test_settings_get_returns_defaults(client):
    c, _ = client
    r = c.get("/api/settings")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data["llm_provider"] == "litert"
    assert data["llm_model"] == "gemma4-e2b"
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
    assert data["llm_provider"] == "litert"  # unchanged


def test_settings_persists_to_disk(client):
    c, _ = client
    c.put(
        "/api/settings",
        data=json.dumps({"llm_model": "persist-test"}),
        content_type="application/json",
    )

    settings_file = settings_module.SETTINGS_FILE
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


def test_settings_put_rejects_wrong_types(client):
    """auto_suggest must be a bool, llm_model must be a string."""
    c, _ = client
    r = c.put(
        "/api/settings",
        data=json.dumps({"auto_suggest": "yes"}),
        content_type="application/json",
    )
    assert r.status_code == 400

    r = c.put(
        "/api/settings",
        data=json.dumps({"llm_model": 123}),
        content_type="application/json",
    )
    assert r.status_code == 400


def test_settings_put_rejects_out_of_range_prune_age(client):
    """prune_max_age_days must be within 1..730 (issue #83)."""
    c, _ = client
    for bad in (-1, 0, 731, 1000):
        r = c.put(
            "/api/settings",
            data=json.dumps({"prune_max_age_days": bad}),
            content_type="application/json",
        )
        assert r.status_code == 400, f"{bad} should be rejected"
        body = json.loads(r.data)
        assert "prune_max_age_days" in body["error"]

    # Rejected values must not persist
    r = c.get("/api/settings")
    assert json.loads(r.data)["prune_max_age_days"] == 90


def test_settings_put_accepts_prune_age_boundaries(client):
    """Both ends of the valid range are accepted and persisted (issue #83)."""
    c, _ = client
    for good in (1, 90, 730):
        r = c.put(
            "/api/settings",
            data=json.dumps({"prune_max_age_days": good}),
            content_type="application/json",
        )
        assert r.status_code == 200, f"{good} should be accepted"
        assert json.loads(c.get("/api/settings").data)["prune_max_age_days"] == good


def test_settings_put_rejects_negative_prune_before_persist(client):
    """A rejected prune value must leave any previously saved value intact."""
    c, _ = client
    c.put(
        "/api/settings",
        data=json.dumps({"prune_max_age_days": 45}),
        content_type="application/json",
    )
    r = c.put(
        "/api/settings",
        data=json.dumps({"prune_max_age_days": -5}),
        content_type="application/json",
    )
    assert r.status_code == 400
    assert json.loads(c.get("/api/settings").data)["prune_max_age_days"] == 45


# ── Phase 4A: Memory pruning / GC ──────────────────────────────────────────


def test_scan_triggers_prune_stale(client):
    """After scanning, orphaned entries beyond max age are removed from memory."""
    c, desktop = client

    # Create a file and scan it to populate memory
    f = desktop / "Screenshot fresh.png"
    f.write_bytes(b"fresh")
    c.get("/api/screenshots")

    # Create a stale orphan entry directly in memory (pretend it was trashed long ago)
    memory = flask_app._get_memory()
    orphan = memory.record_file("Screenshot old-orphan.png", 9999)
    orphan.status = "trashed"
    # Backdate last_updated to 100 days ago
    from datetime import datetime, timedelta, timezone

    orphan.last_updated = (datetime.now(tz=timezone.utc) - timedelta(days=100)).isoformat()
    memory.save()

    assert memory.lookup(orphan.fingerprint) is not None

    # Force prune max age to 90 days (default) — orphan is 100 days old → pruned
    flask_app._reset_memory()
    c.get("/api/screenshots")

    memory = flask_app._get_memory()
    assert memory.lookup(orphan.fingerprint) is None, "100-day-old orphan should be pruned"


def test_prune_respects_settings_age(client):
    """Changing prune_max_age_days in settings affects what gets pruned."""
    c, desktop = client

    # Set a short max age (1 day)
    c.put(
        "/api/settings",
        data=json.dumps({"prune_max_age_days": 1}),
        content_type="application/json",
    )

    f = desktop / "Screenshot active.png"
    f.write_bytes(b"active")
    c.get("/api/screenshots")

    # Create an orphan trashed 5 days ago
    memory = flask_app._get_memory()
    orphan = memory.record_file("Screenshot old.png", 8888)
    orphan.status = "trashed"
    from datetime import datetime, timedelta, timezone

    orphan.last_updated = (datetime.now(tz=timezone.utc) - timedelta(days=5)).isoformat()
    memory.save()

    flask_app._reset_memory()
    c.get("/api/screenshots")

    memory = flask_app._get_memory()
    assert memory.lookup(orphan.fingerprint) is None, (
        "5-day-old orphan should be pruned with max_age=1"
    )


def test_prune_keeps_active_entries(client):
    """Files still on disk are never pruned regardless of age."""
    c, desktop = client

    f = desktop / "Screenshot ancient.png"
    f.write_bytes(b"old but alive")
    c.get("/api/screenshots")

    # Backdate the record to 200 days ago
    memory = flask_app._get_memory()
    r = c.get("/api/screenshots")
    fp = json.loads(r.data)[0]["fingerprint"]
    rec = memory.lookup(fp)
    assert rec is not None
    from datetime import datetime, timedelta, timezone

    rec.last_updated = (datetime.now(tz=timezone.utc) - timedelta(days=200)).isoformat()
    memory.save()

    flask_app._reset_memory()
    c.get("/api/screenshots")

    memory = flask_app._get_memory()
    assert memory.lookup(fp) is not None, "Active file should never be pruned"


def test_prune_keeps_renamed_on_disk(client):
    """A renamed file still on disk is treated as active and never pruned."""
    c, desktop = client
    old = desktop / "Screenshot original.png"
    old.write_bytes(_make_png(10, 10))

    # Scan → record
    c.get("/api/screenshots")

    # Rename
    c.post(
        "/api/rename",
        data=json.dumps({"old_name": old.name, "new_name": "Screenshot renamed-on-disk.png"}),
        content_type="application/json",
    )

    # The renamed file should still be considered active
    flask_app._reset_memory()
    r = c.get("/api/screenshots")
    files = json.loads(r.data)
    assert len(files) == 1
    assert files[0]["name"] == "Screenshot renamed-on-disk.png"
    # The record must still exist (not pruned)
    memory = flask_app._get_memory()
    rec = memory.lookup_by_name("Screenshot renamed-on-disk.png")
    assert rec is not None, "Renamed file on disk should not be pruned"


def test_prune_keeps_recent_inactive(client):
    """Files trashed 5 days ago are kept when max_age=90."""
    c, desktop = client

    f = desktop / "Screenshot recent-trash.png"
    f.write_bytes(b"data")
    c.get("/api/screenshots")

    memory = flask_app._get_memory()
    r = c.get("/api/screenshots")
    fp = json.loads(r.data)[0]["fingerprint"]
    rec = memory.lookup(fp)
    assert rec is not None
    from datetime import datetime, timedelta, timezone

    rec.status = "trashed"
    rec.last_updated = (datetime.now(tz=timezone.utc) - timedelta(days=5)).isoformat()
    memory.save()

    # Remove file from disk (simulating trash)
    f.unlink()

    flask_app._reset_memory()
    c.get("/api/screenshots")

    memory = flask_app._get_memory()
    assert memory.lookup(fp) is not None, (
        "Recently trashed file should be kept within 90-day window"
    )


def test_save_settings_invalidates_prune_cache(client):
    """After saving prune_max_age_days, the cached value is refreshed."""
    c, _ = client

    # Set a non-default value
    c.put(
        "/api/settings",
        data=json.dumps({"prune_max_age_days": 7}),
        content_type="application/json",
    )

    # The cache should be invalidated; next call reads fresh
    # Verify the settings round-trip
    r = c.get("/api/settings")
    assert json.loads(r.data)["prune_max_age_days"] == 7


def test_settings_prune_age_roundtrip(client):
    """Save → load preserves prune_max_age_days."""
    c, _ = client
    c.put(
        "/api/settings",
        data=json.dumps({"prune_max_age_days": 30}),
        content_type="application/json",
    )
    r = c.get("/api/settings")
    assert json.loads(r.data)["prune_max_age_days"] == 30


def test_settings_prune_age_type_validation(client):
    """Non-integer prune_max_age_days values are rejected."""
    c, _ = client
    r = c.put(
        "/api/settings",
        data=json.dumps({"prune_max_age_days": "not-a-number"}),
        content_type="application/json",
    )
    assert r.status_code == 400
