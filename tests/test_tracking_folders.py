"""Tests for tracking folders feature (issue #70)."""

import json
from unittest.mock import patch

import ss_dcl.app as flask_app
from helpers import _make_png
from ss_dcl.sources import (
    compute_source_fingerprint,
    decision_key,
    parse_decision_key,
    sanitize_source_dir,
    validate_tracked_folders,
)

# ── Settings tracked_folders validation ──────────────────────────


class TestTrackedFoldersSettings:
    def test_get_settings_includes_tracked_folders(self, client):
        c, _ = client
        r = c.get("/api/settings")
        data = json.loads(r.data)
        assert "tracked_folders" in data
        assert "tracked_folder_info" in data
        assert isinstance(data["tracked_folders"], list)
        assert isinstance(data["tracked_folder_info"], list)

    def test_put_settings_with_valid_tracked_folder(self, client, tmp_path):
        c, _ = client
        extra = tmp_path / "extra"
        extra.mkdir()
        # Create a valid absolute path
        r = c.put(
            "/api/settings",
            data=json.dumps({"tracked_folders": [str(extra)]}),
            content_type="application/json",
        )
        assert r.status_code == 200
        assert json.loads(r.data)["ok"] is True
        r2 = c.get("/api/settings")
        data = json.loads(r2.data)
        assert str(extra) in data["tracked_folders"]

    def test_put_settings_rejects_relative_path(self, client):
        c, _ = client
        r = c.put(
            "/api/settings",
            data=json.dumps({"tracked_folders": ["relative/path"]}),
            content_type="application/json",
        )
        assert r.status_code == 400
        assert "absolute path" in json.loads(r.data)["error"].lower()

    def test_put_settings_rejects_desktop_itself(self, client):
        c, desktop = client
        r = c.put(
            "/api/settings",
            data=json.dumps({"tracked_folders": [str(desktop)]}),
            content_type="application/json",
        )
        assert r.status_code == 400
        assert "desktop" in json.loads(r.data)["error"].lower()

    def test_put_settings_rejects_duplicate(self, client, tmp_path):
        c, _ = client
        extra = tmp_path / "extra"
        extra.mkdir()
        r = c.put(
            "/api/settings",
            data=json.dumps({"tracked_folders": [str(extra), str(extra)]}),
            content_type="application/json",
        )
        assert r.status_code == 400
        assert "already tracked" in json.loads(r.data)["error"].lower()

    def test_put_settings_rejects_nested(self, client, tmp_path):
        c, _ = client
        parent = tmp_path / "parent"
        parent.mkdir()
        child = parent / "child"
        child.mkdir()
        r = c.put(
            "/api/settings",
            data=json.dumps({"tracked_folders": [str(parent), str(child)]}),
            content_type="application/json",
        )
        assert r.status_code == 400
        assert "inside" in json.loads(r.data)["error"].lower()

    def test_put_settings_rejects_nonexistent_new(self, client, tmp_path):
        c, _ = client
        missing = tmp_path / "missing"
        # Not creating it -> should reject
        r = c.put(
            "/api/settings",
            data=json.dumps({"tracked_folders": [str(missing)]}),
            content_type="application/json",
        )
        assert r.status_code == 400
        assert "does not exist" in json.loads(r.data)["error"].lower()

    def test_put_settings_allows_missing_already_tracked(self, client, tmp_path):
        c, _ = client
        extra = tmp_path / "extra"
        extra.mkdir()
        # First, add it
        c.put(
            "/api/settings",
            data=json.dumps({"tracked_folders": [str(extra)]}),
            content_type="application/json",
        )
        # Now remove dir externally
        extra.rmdir()
        # Saving same list should be allowed (preserve missing)
        r = c.put(
            "/api/settings",
            data=json.dumps({"tracked_folders": [str(extra)]}),
            content_type="application/json",
        )
        assert r.status_code == 200
        # Info should flag exists False
        r2 = c.get("/api/settings")
        info = json.loads(r2.data)["tracked_folder_info"]
        matching = [i for i in info if i["path"] == str(extra)]
        assert len(matching) == 1
        assert matching[0]["exists"] is False

    def test_put_settings_cap_10(self, client, tmp_path):
        c, _ = client
        dirs = []
        for i in range(11):
            d = tmp_path / f"dir{i}"
            d.mkdir()
            dirs.append(str(d))
        r = c.put(
            "/api/settings",
            data=json.dumps({"tracked_folders": dirs}),
            content_type="application/json",
        )
        assert r.status_code == 400
        assert "too many" in json.loads(r.data)["error"].lower()

    def test_put_settings_rejects_non_list(self, client):
        c, _ = client
        r = c.put(
            "/api/settings",
            data=json.dumps({"tracked_folders": "not-a-list"}),
            content_type="application/json",
        )
        assert r.status_code == 400


# ── Scanning with tracked folders ───────────────────────────────


class TestScanningTrackedFolders:
    def test_screenshots_merges_desktop_and_tracked(self, client, tmp_path):
        c, desktop = client
        # Desktop file
        (desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png").write_bytes(b"desktop")
        # Tracked folder
        extra = tmp_path / "extra"
        extra.mkdir()
        (extra / "Screenshot 2024-01-02 at 12.00.00 PM.png").write_bytes(b"extra")
        c.put(
            "/api/settings",
            data=json.dumps({"tracked_folders": [str(extra)]}),
            content_type="application/json",
        )
        r = c.get("/api/screenshots")
        files = json.loads(r.data)
        assert len(files) == 2
        sources = {f["source"] for f in files}
        assert "Desktop" in sources
        assert str(extra) in sources

    def test_same_name_in_two_sources_two_cards(self, client, tmp_path):
        c, desktop = client
        name = "Screenshot 2024-01-01 at 12.00.00 PM.png"
        (desktop / name).write_bytes(_make_png(10, 10))
        extra = tmp_path / "extra"
        extra.mkdir()
        (extra / name).write_bytes(_make_png(20, 20))
        c.put(
            "/api/settings",
            data=json.dumps({"tracked_folders": [str(extra)]}),
            content_type="application/json",
        )
        r = c.get("/api/screenshots")
        files = json.loads(r.data)
        assert len(files) == 2
        # Both have same name but different source
        assert files[0]["name"] == name
        assert files[1]["name"] == name
        assert files[0]["source"] != files[1]["source"]
        # Fingerprints must differ - even same size should differ due to source
        # Create same size in both
        (desktop / name).write_bytes(b"same")
        (extra / name).write_bytes(b"same")
        flask_app._reset_memory()
        r = c.get("/api/screenshots")
        files = json.loads(r.data)
        assert len(files) == 2
        fps = [f["fingerprint"] for f in files]
        assert fps[0] != fps[1]

    def test_missing_tracked_folder_skipped(self, client, tmp_path):
        c, desktop = client
        (desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png").write_bytes(b"hello")
        missing = tmp_path / "missing"
        missing.mkdir()
        c.put(
            "/api/settings",
            data=json.dumps({"tracked_folders": [str(missing)]}),
            content_type="application/json",
        )
        # Remove before scan
        missing.rmdir()
        r = c.get("/api/screenshots")
        assert r.status_code == 200
        files = json.loads(r.data)
        assert len(files) == 1
        assert files[0]["source"] == "Desktop"

    def test_screenshots_include_source_field(self, client):
        c, desktop = client
        (desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png").write_bytes(b"data")
        r = c.get("/api/screenshots")
        files = json.loads(r.data)
        assert len(files) == 1
        assert "source" in files[0]
        assert files[0]["source"] == "Desktop"


# ── Source-aware image / thumb / reveal ────────────────────────


class TestSourceAwareRoutes:
    def test_image_with_source_param(self, client, tmp_path):
        c, _ = client
        name = "Screenshot 2024-01-01 at 12.00.00 PM.png"
        extra = tmp_path / "extra"
        extra.mkdir()
        (extra / name).write_bytes(b"\x89PNG\r\n\x1a\n")
        c.put(
            "/api/settings",
            data=json.dumps({"tracked_folders": [str(extra)]}),
            content_type="application/json",
        )
        # Desktop should 404 for same name not on Desktop
        r = c.get(f"/api/image/{name}?source={extra}")
        assert r.status_code == 200
        # Without source, should 404 because not on Desktop
        r2 = c.get(f"/api/image/{name}")
        assert r2.status_code == 404

    def test_thumb_with_source_returns_correct_image(self, client, tmp_path):
        c, desktop = client
        name = "Screenshot 2024-01-01 at 12.00.00 PM.png"
        (desktop / name).write_bytes(_make_png(10, 10, "red"))
        extra = tmp_path / "extra"
        extra.mkdir()
        (extra / name).write_bytes(_make_png(10, 10, "blue"))
        c.put(
            "/api/settings",
            data=json.dumps({"tracked_folders": [str(extra)]}),
            content_type="application/json",
        )
        r1 = c.get(f"/api/thumb/{name}?source=Desktop")
        assert r1.status_code == 200
        r2 = c.get(f"/api/thumb/{name}?source={extra}")
        assert r2.status_code == 200
        # Thumbnails should be distinct files on disk
        thumb_base = desktop / "thumbs"
        # Desktop thumb flat
        assert (thumb_base / name).exists()
        # Tracked thumb in subdir (hash)
        # Find subdir
        subdirs = [p for p in thumb_base.iterdir() if p.is_dir()]
        assert len(subdirs) >= 1
        # There should be a file in subdir
        found = False
        for sd in subdirs:
            if (sd / name).exists():
                found = True
                break
        assert found

    def test_reveal_with_source_param(self, client, tmp_path):
        c, _ = client
        name = "Screenshot 2024-01-01 at 12.00.00 PM.png"
        extra = tmp_path / "extra"
        extra.mkdir()
        (extra / name).write_bytes(b"data")
        c.put(
            "/api/settings",
            data=json.dumps({"tracked_folders": [str(extra)]}),
            content_type="application/json",
        )
        with patch("ss_dcl.app.subprocess.Popen"):
            r = c.post(
                "/api/reveal",
                data=json.dumps({"source": str(extra), "name": name}),
                content_type="application/json",
            )
            # Off-macOS returns 400, but should not be 404
            assert r.status_code in (200, 400)
            # Legacy filename should still work for Desktop (404 because file not on Desktop)
            r2 = c.post(
                "/api/reveal",
                data=json.dumps({"filename": name}),
                content_type="application/json",
            )
            assert r2.status_code == 404  # not on Desktop

    def test_path_traversal_rejected_per_source(self, client, tmp_path):
        c, _ = client
        extra = tmp_path / "extra"
        extra.mkdir()
        c.put(
            "/api/settings",
            data=json.dumps({"tracked_folders": [str(extra)]}),
            content_type="application/json",
        )
        r = c.get(f"/api/image/../etc/passwd?source={extra}")
        assert r.status_code in (400, 404)
        r = c.get("/api/image/../etc/passwd")
        assert r.status_code in (400, 404)


# ── Rename / Done source-aware ────────────────────────────────


class TestRenameDoneSourceAware:
    def test_rename_in_tracked_folder(self, client, tmp_path):
        c, desktop = client
        name = "Screenshot 2024-01-01 at 12.00.00 PM.png"
        extra = tmp_path / "extra"
        extra.mkdir()
        (extra / name).write_bytes(b"data")
        c.put(
            "/api/settings",
            data=json.dumps({"tracked_folders": [str(extra)]}),
            content_type="application/json",
        )
        r = c.post(
            "/api/rename",
            data=json.dumps(
                {"old_name": name, "new_name": "Screenshot renamed.png", "source": str(extra)}
            ),
            content_type="application/json",
        )
        assert r.status_code == 200
        assert not (extra / name).exists()
        assert (extra / "Screenshot renamed.png").exists()
        # Desktop file with same name should not be affected (doesn't exist, but ensure no conflict)
        assert not (desktop / "Screenshot renamed.png").exists()

    def test_rename_conflict_only_within_source(self, client, tmp_path):
        c, desktop = client
        name1 = "Screenshot 2024-01-01 at 12.00.00 PM.png"
        name2 = "Screenshot 2024-01-02 at 12.00.00 PM.png"
        extra = tmp_path / "extra"
        extra.mkdir()
        (desktop / name1).write_bytes(b"a")
        (desktop / name2).write_bytes(b"b")
        (extra / name1).write_bytes(b"c")
        c.put(
            "/api/settings",
            data=json.dumps({"tracked_folders": [str(extra)]}),
            content_type="application/json",
        )
        # Rename desktop file to name2 should conflict (same source)
        r = c.post(
            "/api/rename",
            data=json.dumps({"old_name": name1, "new_name": name2, "source": "Desktop"}),
            content_type="application/json",
        )
        assert r.status_code == 409
        # Rename extra file to name that exists on Desktop should NOT conflict (different source)
        r2 = c.post(
            "/api/rename",
            data=json.dumps({"old_name": name1, "new_name": name2, "source": str(extra)}),
            content_type="application/json",
        )
        assert r2.status_code == 200

    def test_done_with_files_payload(self, client, tmp_path):
        c, desktop = client
        name = "Screenshot 2024-01-01 at 12.00.00 PM.png"
        extra = tmp_path / "extra"
        extra.mkdir()
        (desktop / name).write_bytes(b"data")
        (extra / name).write_bytes(b"data")
        c.put(
            "/api/settings",
            data=json.dumps({"tracked_folders": [str(extra)]}),
            content_type="application/json",
        )
        with patch("ss_dcl.app.send2trash") as mock:
            r = c.post(
                "/api/done",
                data=json.dumps(
                    {
                        "files": [
                            {"source": "Desktop", "name": name},
                            {"source": str(extra), "name": name},
                        ]
                    }
                ),
                content_type="application/json",
            )
            assert r.status_code == 200
            assert mock.call_count == 2

    def test_done_legacy_filenames_still_work(self, client):
        c, desktop = client
        name = "Screenshot 2024-01-01 at 12.00.00 PM.png"
        (desktop / name).write_bytes(b"data")
        with patch("ss_dcl.app.send2trash"):
            r = c.post(
                "/api/done",
                data=json.dumps({"filenames": [name]}),
                content_type="application/json",
            )
            assert r.status_code == 200


# ── Memory source-aware ───────────────────────────────────────


class TestMemorySourceAware:
    def test_same_name_same_size_different_source_two_records(self, tmp_path):
        from ss_dcl.memory import MemoryStore

        store = MemoryStore(tmp_path / "memory.json")
        rec1 = store.record_file("Screenshot A.png", 100, source="Desktop")
        rec2 = store.record_file("Screenshot A.png", 100, source="/tmp/extra")
        assert rec1.fingerprint != rec2.fingerprint
        assert rec1.fingerprint == "Screenshot A.png|100"
        assert rec2.fingerprint == "/tmp/extra|Screenshot A.png|100"
        assert len(store._files) == 2
        # Lookup source-aware
        assert store.lookup_by_name("Screenshot A.png", source="Desktop") is rec1
        assert store.lookup_by_name("Screenshot A.png", source="/tmp/extra") is rec2
        # Legacy lookup returns one of them (bare)
        assert store.lookup_by_name("Screenshot A.png") is not None

    def test_memory_persistence_with_source(self, tmp_path):
        from ss_dcl.memory import MemoryStore

        path = tmp_path / "memory.json"
        store = MemoryStore(path)
        rec = store.record_file("Screenshot A.png", 100, source="/tmp/extra")
        rec.meta["keywords"] = ["test"]
        store.save()
        store2 = MemoryStore(path)
        store2.load()
        assert len(store2._files) == 1
        loaded = store2.lookup(rec.fingerprint)
        assert loaded is not None
        assert loaded.meta["source"] == "/tmp/extra"

    def test_prune_stale_source_aware(self, tmp_path):
        from datetime import datetime, timedelta, timezone

        from ss_dcl.memory import MemoryStore

        store = MemoryStore(tmp_path / "memory.json")
        rec1 = store.record_file("Screenshot A.png", 100, source="Desktop")
        rec2 = store.record_file("Screenshot A.png", 100, source="/tmp/extra")
        # Make rec2 old
        old_time = datetime.now(tz=timezone.utc) - timedelta(days=100)
        rec2.last_updated = old_time.isoformat()
        # Active only rec1
        pruned = store.prune_stale(active_fingerprints={rec1.fingerprint}, max_age_days=90)
        assert pruned == 1
        assert store.lookup(rec1.fingerprint) is not None
        assert store.lookup(rec2.fingerprint) is None

    def test_suggest_names_source_aware(self, client, tmp_path, monkeypatch):
        import ss_dcl.llm as llm

        c, desktop = client
        name = "Screenshot 2024-01-01 at 12.00.00 PM.png"
        extra = tmp_path / "extra"
        extra.mkdir()
        (desktop / name).write_bytes(_make_png(10, 10))
        (extra / name).write_bytes(_make_png(10, 10))
        c.put(
            "/api/settings",
            data=json.dumps({"tracked_folders": [str(extra)]}),
            content_type="application/json",
        )
        r = c.get("/api/screenshots")
        files = json.loads(r.data)
        assert len(files) == 2
        fps = [f["fingerprint"] for f in files]
        assert fps[0] != fps[1]

        # Mock LLM
        def mock_suggest(path, model, ext=".png"):
            return "suggested" + ext

        monkeypatch.setattr(llm, "_call_litert_suggest", mock_suggest)
        r = c.post(
            "/api/suggest-names",
            data=json.dumps({"fingerprints": fps}),
            content_type="application/json",
        )
        assert r.status_code == 200
        data = json.loads(r.data)
        assert len(data["suggestions"]) == 2


# ── Pick folder ───────────────────────────────────────────────


class TestPickFolder:
    def test_pick_folder_off_macos(self, client):
        c, _ = client
        # Simulate non-darwin via mocking the helper to return off-macos error
        with patch(
            "ss_dcl.app.pick_folder_via_panel",
            return_value=(None, "Folder picker is only available on macOS."),
        ):
            r = c.post("/api/pick-folder")
            assert r.status_code == 400
            assert "macOS" in json.loads(r.data)["error"]

    def test_pick_folder_success(self, client):
        c, _ = client
        with patch("ss_dcl.app.pick_folder_via_panel", return_value=("/tmp/picked", None)):
            r = c.post("/api/pick-folder")
            assert r.status_code == 200
            assert json.loads(r.data)["path"] == "/tmp/picked"

    def test_pick_folder_cancel(self, client):
        c, _ = client
        with patch("ss_dcl.app.pick_folder_via_panel", return_value=(None, None)):
            r = c.post("/api/pick-folder")
            assert r.status_code == 200
            assert json.loads(r.data)["path"] is None

    def test_pick_folder_error(self, client):
        c, _ = client
        with patch("ss_dcl.app.pick_folder_via_panel", return_value=(None, "Some error")):
            r = c.post("/api/pick-folder")
            # Our app returns 500 for generic errors, 400 for off-macOS
            assert r.status_code in (400, 500)
            assert "error" in json.loads(r.data)


# ── Sources helpers ────────────────────────────────────────────


class TestSourcesHelpers:
    def test_decision_key(self):
        assert decision_key("Desktop", "a.png") == "a.png"
        assert decision_key("/tmp/extra", "a.png") == "/tmp/extra|a.png"

    def test_parse_decision_key(self):
        assert parse_decision_key("a.png") == ("Desktop", "a.png")
        assert parse_decision_key("Desktop|a.png") == ("Desktop", "a.png")
        assert parse_decision_key("/tmp/extra|a.png") == ("/tmp/extra", "a.png")

    def test_compute_source_fingerprint(self):
        assert compute_source_fingerprint("Desktop", "a.png", 100) == "a.png|100"
        assert compute_source_fingerprint("/tmp/extra", "a.png", 100) == "/tmp/extra|a.png|100"

    def test_sanitize_source_dir_deterministic(self):
        a = sanitize_source_dir("/tmp/extra")
        b = sanitize_source_dir("/tmp/extra")
        c = sanitize_source_dir("/tmp/other")
        assert a == b
        assert a != c
        assert len(a) == 16

    def test_validate_tracked_folders_ok(self, tmp_path):
        desktop = tmp_path / "Desktop"
        desktop.mkdir()
        extra = tmp_path / "extra"
        extra.mkdir()
        ok, err = validate_tracked_folders([str(extra)], desktop, [])
        assert err is None
        assert ok == [str(extra.resolve())]

    def test_validate_tracked_folders_rejects_inside(self, tmp_path):
        desktop = tmp_path / "Desktop"
        desktop.mkdir()
        parent = tmp_path / "parent"
        parent.mkdir()
        child = parent / "child"
        child.mkdir()
        _, err = validate_tracked_folders([str(parent), str(child)], desktop, [])
        assert err is not None
        assert "inside" in err.lower()

    def test_thumb_path_source(self, tmp_path):
        from ss_dcl.sources import thumb_path_for_source

        base = tmp_path / "thumbs"
        p1 = thumb_path_for_source(base, "Desktop", "a.png")
        p2 = thumb_path_for_source(base, "/tmp/extra", "a.png")
        assert p1 == base / "a.png"
        assert p2 != p1
        assert p2.parent != base

    def test_non_recursive_scan_tracked(self, client, tmp_path):
        c, _ = client
        extra = tmp_path / "extra"
        extra.mkdir()
        sub = extra / "subdir"
        sub.mkdir()
        (extra / "Screenshot 2024-01-01 at 12.00.00 PM.png").write_bytes(b"top")
        (sub / "Screenshot 2024-01-02 at 12.00.00 PM.png").write_bytes(b"nested")
        c.put(
            "/api/settings",
            data=json.dumps({"tracked_folders": [str(extra)]}),
            content_type="application/json",
        )
        r = c.get("/api/screenshots")
        files = json.loads(r.data)
        # Only top-level file should be found, not nested
        names = [f["name"] for f in files]
        assert "Screenshot 2024-01-01 at 12.00.00 PM.png" in names
        assert "Screenshot 2024-01-02 at 12.00.00 PM.png" not in names

    def test_delimiter_collision_encoded(self, tmp_path):
        # Two different source|name combos that would collide with raw `|` delimiter
        from ss_dcl.memory import MemoryStore
        from ss_dcl.sources import compute_source_fingerprint, decision_key

        s1 = "/root/a"
        n1 = "Screenshot|Screenshot x.png"
        s2 = "/root/a|Screenshot"
        n2 = "Screenshot x.png"
        size = 123
        fp1 = compute_source_fingerprint(s1, n1, size)
        fp2 = compute_source_fingerprint(s2, n2, size)
        assert fp1 != fp2, "Encoded fingerprints must not collide"
        dk1 = decision_key(s1, n1)
        dk2 = decision_key(s2, n2)
        assert dk1 != dk2, "Encoded decision keys must not collide"
        # Memory must create two distinct records
        store = MemoryStore(tmp_path / "memory.json")
        rec1 = store.record_file(n1, size, source=s1)
        rec2 = store.record_file(n2, size, source=s2)
        assert rec1.fingerprint == fp1
        assert rec2.fingerprint == fp2
        assert len(store._files) == 2
        assert store.lookup_by_name(n1, source=s1) is rec1
        assert store.lookup_by_name(n2, source=s2) is rec2


class TestDoneValidation:
    def test_done_rejects_invalid_source_explicit(self, client, tmp_path):
        c, desktop = client
        name = "Screenshot 2024-01-01 at 12.00.00 PM.png"
        (desktop / name).write_bytes(b"data")
        extra = tmp_path / "extra"
        extra.mkdir()
        (extra / name).write_bytes(b"data")
        c.put(
            "/api/settings",
            data=json.dumps({"tracked_folders": [str(extra)]}),
            content_type="application/json",
        )
        # Explicit null source should be rejected, not coerced to Desktop
        with patch("ss_dcl.app.send2trash"):
            r = c.post(
                "/api/done",
                data=json.dumps({"files": [{"source": None, "name": name}]}),
                content_type="application/json",
            )
            # Should be 207 with error, not 200 success that trashes Desktop file
            assert r.status_code == 207
            data = json.loads(r.data)
            assert data["ok"] is False
            assert len(data["errors"]) == 1
            # Ensure Desktop file still exists (not trashed)
            assert (desktop / name).exists()
            assert (extra / name).exists()

    def test_done_malformed_entries_reported(self, client):
        c, _ = client
        r = c.post(
            "/api/done",
            data=json.dumps(
                {"files": [{"source": "/tmp/extra", "name": ""}, "not-a-dict", {"name": "a.png"}]}
            ),
            content_type="application/json",
        )
        # Should report errors for each invalid entry, not 200 ok
        assert r.status_code == 207
        data = json.loads(r.data)
        assert data["ok"] is False
        assert len(data["errors"]) >= 2

    def test_done_only_invalid_returns_207(self, client):
        c, _ = client
        r = c.post(
            "/api/done",
            data=json.dumps({"files": [{"source": None, "name": ""}]}),
            content_type="application/json",
        )
        assert r.status_code == 207
        assert json.loads(r.data)["ok"] is False

    def test_done_rejects_non_list_files(self, client):
        c, _ = client
        r = c.post(
            "/api/done",
            data=json.dumps({"files": "not-a-list"}),
            content_type="application/json",
        )
        assert r.status_code == 400

    def test_done_does_not_fallback_to_filenames_when_files_present(self, client, tmp_path):
        c, desktop = client
        name = "Screenshot 2024-01-01 at 12.00.00 PM.png"
        (desktop / name).write_bytes(b"data")
        # Valid file in filenames but files payload is invalid (explicit null source)
        # Should report error for files, not silently trash via filenames
        with patch("ss_dcl.app.send2trash") as mock:
            r = c.post(
                "/api/done",
                data=json.dumps({"files": [{"source": None, "name": name}], "filenames": [name]}),
                content_type="application/json",
            )
            assert r.status_code == 207
            assert json.loads(r.data)["ok"] is False
            mock.assert_not_called()
            assert (desktop / name).exists()


class TestInvalidSourceHandling:
    def test_rename_rejects_explicit_invalid_source(self, client, tmp_path):
        c, desktop = client
        name = "Screenshot 2024-01-01 at 12.00.00 PM.png"
        (desktop / name).write_bytes(b"data")
        r = c.post(
            "/api/rename",
            data=json.dumps({"old_name": name, "new_name": "Screenshot new.png", "source": None}),
            content_type="application/json",
        )
        assert r.status_code == 400
        assert "invalid source" in json.loads(r.data)["error"].lower()
        assert (desktop / name).exists()

    def test_rename_with_missing_source_defaults_to_desktop(self, client, tmp_path):
        c, desktop = client
        name = "Screenshot 2024-01-01 at 12.00.00 PM.png"
        (desktop / name).write_bytes(b"data")
        r = c.post(
            "/api/rename",
            data=json.dumps({"old_name": name, "new_name": "Screenshot new.png"}),
            content_type="application/json",
        )
        assert r.status_code == 200

    def test_reveal_rejects_explicit_invalid_source(self, client):
        c, _ = client
        r = c.post(
            "/api/reveal",
            data=json.dumps({"source": "", "name": "Screenshot 2024-01-01 at 12.00.00 PM.png"}),
            content_type="application/json",
        )
        assert r.status_code == 400

    def test_reveal_with_missing_source_uses_desktop(self, client, tmp_path):
        c, desktop = client
        name = "Screenshot 2024-01-01 at 12.00.00 PM.png"
        (desktop / name).write_bytes(b"data")
        with patch("ss_dcl.app.subprocess.Popen"):
            r = c.post(
                "/api/reveal",
                data=json.dumps({"filename": name}),
                content_type="application/json",
            )
            # Desktop file exists but off-macOS returns 400 for reveal not supported
            assert r.status_code in (200, 400)
            # Ensure it didn't treat as invalid source
            if r.status_code == 400:
                assert "invalid" not in json.loads(r.data).get(
                    "error", ""
                ).lower() or "macOS" in json.loads(r.data).get("error", "")

    def test_rename_invalid_source_does_not_affect_other_source(self, client, tmp_path):
        c, desktop = client
        name = "Screenshot 2024-01-01 at 12.00.00 PM.png"
        extra = tmp_path / "extra"
        extra.mkdir()
        (desktop / name).write_bytes(b"desktop")
        (extra / name).write_bytes(b"extra")
        c.put(
            "/api/settings",
            data=json.dumps({"tracked_folders": [str(extra)]}),
            content_type="application/json",
        )
        # Try to rename with invalid source null but name matches Desktop file
        # Should be rejected, not trash/rename Desktop file
        r = c.post(
            "/api/rename",
            data=json.dumps({"old_name": name, "new_name": "new.png", "source": ""}),
            content_type="application/json",
        )
        assert r.status_code == 400
        assert (desktop / name).exists()
        assert (extra / name).exists()


class TestFrontendRegressions:
    def test_app_js_updates_current_file_keys_on_rename(self, client):
        c, _ = client
        r = c.get("/static/app.js")
        assert r.status_code == 200
        body = r.data.decode()
        # Rename must keep currentFileKeys in sync (fixes count bug)
        assert "currentFileKeys.delete(oldKey)" in body
        assert "currentFileKeys.add(newKey)" in body

    def test_app_js_builds_valid_cache_busting_url(self, client):
        c, _ = client
        r = c.get("/static/app.js")
        body = r.data.decode()
        # Must construct ?t= vs &t= correctly, not via .replace("?&", "?") for Desktop
        assert 'thumbBase.includes("?")' in body
        assert 'imgBase.includes("?")' in body
        assert "thumbBase + (thumbBase.includes" in body
        assert "imgBase + (imgBase.includes" in body

    def test_app_js_decision_key_encodes_delimiter(self, client):
        c, _ = client
        r = c.get("/static/app.js")
        body = r.data.decode()
        # Frontend decisionKey should encode `|`
        assert "fileKey(" in body
        assert "SsDcl.decisionKey" in body or "SsDcl.fileKey" in body


class TestUntrackRestore:
    def test_untrack_then_readd_restores_decision(self, client, tmp_path):
        c, _ = client
        name = "Screenshot 2024-01-01 at 12.00.00 PM.png"
        extra = tmp_path / "extra"
        extra.mkdir()
        (extra / name).write_bytes(b"extra")
        # Track folder
        c.put(
            "/api/settings",
            data=json.dumps({"tracked_folders": [str(extra)]}),
            content_type="application/json",
        )
        r = c.get("/api/screenshots")
        files = json.loads(r.data)
        assert any(f["name"] == name and f["source"] == str(extra) for f in files)
        # Set decision for tracked file to keep
        from ss_dcl.sources import decision_key

        key = decision_key(str(extra), name)
        c.put(
            "/api/state",
            data=json.dumps({"decisions": {key: "keep"}}),
            content_type="application/json",
        )
        # Verify decision persisted
        r = c.get("/api/state")
        assert json.loads(r.data)["decisions"][key] == "keep"
        # Untrack folder
        c.put(
            "/api/settings",
            data=json.dumps({"tracked_folders": []}),
            content_type="application/json",
        )
        r = c.get("/api/screenshots")
        files = json.loads(r.data)
        assert not any(f["source"] == str(extra) for f in files)
        # Decision should still be in state (not deleted)
        r = c.get("/api/state")
        assert json.loads(r.data)["decisions"].get(key) == "keep"
        # Re-add folder
        c.put(
            "/api/settings",
            data=json.dumps({"tracked_folders": [str(extra)]}),
            content_type="application/json",
        )
        r = c.get("/api/screenshots")
        files = json.loads(r.data)
        assert any(f["name"] == name and f["source"] == str(extra) for f in files)
        # Decision should still be keep, so card would be in Keep column
        r = c.get("/api/state")
        assert json.loads(r.data)["decisions"].get(key) == "keep"
        # Verify that get_screenshots with that decision returns suggested_category correctly?
        # Just ensure the decision is still there and not pruned
        assert key in json.loads(c.get("/api/state").data)["decisions"]
