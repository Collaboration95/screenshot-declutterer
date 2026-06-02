"""Tests for the persistent memory store (Phase 1A).

Covers:
- Fingerprint computation
- FileRecord validation
- MemoryStore CRUD (record, lookup, update, remove)
- Persistence (save → load round-trip)
- Atomic write safety (corruption resistance)
- Status transitions (new → suggested → renamed/ignored/trashed)
- Prune stale entries
- Edge cases (empty store, missing keys, malformed data)
"""

import json
from datetime import datetime, timezone

import pytest
from src.ss_dcl.memory import (
    FileRecord,
    MemoryStore,
    atomic_write,
    compute_fingerprint,
)

# ── Fingerprint computation ──────────────────────────────────────


class TestComputeFingerprint:
    def test_basic(self):
        fp = compute_fingerprint("Screenshot 2024-01-01 at 12.00.00 PM.png", 204800)
        assert fp == "Screenshot 2024-01-01 at 12.00.00 PM.png|204800"

    def test_small_file(self):
        fp = compute_fingerprint("Screenshot tiny.png", 0)
        assert fp == "Screenshot tiny.png|0"

    def test_large_size(self):
        fp = compute_fingerprint("big.png", 10_000_000_000)
        assert fp == "big.png|10000000000"

    def test_unicode_name(self):
        fp = compute_fingerprint("Screenshot 日本語.png", 12345)
        assert fp == "Screenshot 日本語.png|12345"

    def test_name_with_spaces(self):
        fp = compute_fingerprint("Screenshot 2024-01-01 at 12.00.00 PM.png", 999)
        assert "|" in fp
        assert fp.endswith("|999")

    def test_deterministic(self):
        name, size = "Screenshot A.png", 500
        assert compute_fingerprint(name, size) == compute_fingerprint(name, size)

    def test_different_sizes_different_fingerprint(self):
        assert compute_fingerprint("f.png", 100) != compute_fingerprint("f.png", 200)

    def test_different_names_different_fingerprint(self):
        assert compute_fingerprint("a.png", 100) != compute_fingerprint("b.png", 100)


# ── FileRecord validation ────────────────────────────────────────


class TestFileRecord:
    def _make_record(self, **overrides):
        defaults = dict(
            fingerprint="test|100",
            original_name="test",
            last_known_name="test",
            size=100,
            extension=".png",
            status="new",
        )
        defaults.update(overrides)
        return FileRecord(**defaults)

    def test_valid_statuses(self):
        for status in ("new", "suggested", "renamed", "ignored", "trashed"):
            rec = self._make_record(status=status)
            assert rec.status == status

    def test_invalid_status_raises(self):
        with pytest.raises(ValueError, match="Invalid status"):
            self._make_record(status="unknown")

    def test_defaults(self):
        rec = self._make_record()
        assert rec.suggested_name is None
        assert rec.user_name is None
        assert rec.first_seen == ""
        assert rec.last_updated == ""
        assert rec.meta == {}

    def test_custom_fields(self):
        rec = self._make_record(
            suggested_name="report.png",
            user_name="quarterly-report.png",
            first_seen="2024-01-01T00:00:00",
            last_updated="2024-01-02T00:00:00",
            meta={"llm_model": "gemma-3b"},
        )
        assert rec.suggested_name == "report.png"
        assert rec.meta["llm_model"] == "gemma-3b"


# ── Atomic write ─────────────────────────────────────────────────


class TestAtomicWrite:
    def test_creates_file(self, tmp_path):
        target = tmp_path / "test.json"
        atomic_write(target, '{"hello": true}')
        assert target.exists()
        assert json.loads(target.read_text()) == {"hello": True}

    def test_creates_parent_dirs(self, tmp_path):
        target = tmp_path / "deep" / "nested" / "file.json"
        atomic_write(target, "content")
        assert target.exists()

    def test_overwrites_existing(self, tmp_path):
        target = tmp_path / "data.json"
        target.write_text('{"old": true}')
        atomic_write(target, '{"new": true}')
        assert json.loads(target.read_text()) == {"new": True}

    def test_temp_file_cleaned_up_on_os_error(self, tmp_path):
        """Verify temp file is removed when os.replace fails."""
        from unittest.mock import patch

        target = tmp_path / "data.json"
        target.write_text('{"original": true}')

        with (
            patch("os.replace", side_effect=PermissionError("denied")),
            pytest.raises(PermissionError),
        ):
            atomic_write(target, '{"updated": true}')

        # Original must be untouched
        assert json.loads(target.read_text()) == {"original": True}
        # No stale temp files left behind
        tmps = list(tmp_path.glob("*.tmp"))
        assert len(tmps) == 0

    def test_creates_parent_dirs_on_save(self, tmp_path):
        """atomic_write creates missing parent directories."""
        target = tmp_path / "deep" / "nested" / "file.json"
        atomic_write(target, "content")
        assert target.exists()


# ── MemoryStore CRUD ─────────────────────────────────────────────


class TestMemoryStoreCRUD:
    def _store(self, tmp_path):
        return MemoryStore(tmp_path / "memory.json")

    def test_empty_store(self, tmp_path):
        store = self._store(tmp_path)
        assert store.count == 0
        assert store.lookup("nonexistent") is None
        assert store.lookup_by_name("nonexistent") is None
        assert store.get_status("nonexistent") is None

    def test_record_file_creates_new(self, tmp_path):
        store = self._store(tmp_path)
        rec = store.record_file("Screenshot 2024-01-01.png", 204800)
        assert rec.fingerprint == "Screenshot 2024-01-01.png|204800"
        assert rec.original_name == "Screenshot 2024-01-01.png"
        assert rec.last_known_name == "Screenshot 2024-01-01.png"
        assert rec.size == 204800
        assert rec.extension == ".png"
        assert rec.status == "new"
        assert rec.first_seen != ""
        assert rec.last_updated != ""

    def test_record_file_idempotent(self, tmp_path):
        store = self._store(tmp_path)
        rec1 = store.record_file("Screenshot A.png", 100)
        rec2 = store.record_file("Screenshot A.png", 100)
        assert rec1 is rec2
        assert store.count == 1

    def test_record_different_files(self, tmp_path):
        store = self._store(tmp_path)
        store.record_file("Screenshot A.png", 100)
        store.record_file("Screenshot B.png", 200)
        assert store.count == 2

    def test_lookup_by_fingerprint(self, tmp_path):
        store = self._store(tmp_path)
        store.record_file("Screenshot A.png", 100)
        fp = compute_fingerprint("Screenshot A.png", 100)
        found = store.lookup(fp)
        assert found is not None
        assert found.original_name == "Screenshot A.png"

    def test_lookup_by_name(self, tmp_path):
        store = self._store(tmp_path)
        store.record_file("Screenshot 2024-01-01.png", 5000)
        found = store.lookup_by_name("Screenshot 2024-01-01.png")
        assert found is not None
        assert found.size == 5000

    def test_lookup_by_name_after_rename(self, tmp_path):
        store = self._store(tmp_path)
        store.record_file("Screenshot A.png", 100)
        fp = compute_fingerprint("Screenshot A.png", 100)
        store.record_rename(fp, "renamed.png")
        # Should find by new name
        assert store.lookup_by_name("renamed.png") is not None
        # Should also find by original name
        assert store.lookup_by_name("Screenshot A.png") is not None

    def test_lookup_by_name_not_found(self, tmp_path):
        store = self._store(tmp_path)
        assert store.lookup_by_name("ghost.png") is None

    def test_get_status(self, tmp_path):
        store = self._store(tmp_path)
        rec = store.record_file("Screenshot A.png", 100)
        assert store.get_status(rec.fingerprint) == "new"
        assert store.get_status("nonexistent") is None

    def test_remove(self, tmp_path):
        store = self._store(tmp_path)
        rec = store.record_file("Screenshot A.png", 100)
        assert store.count == 1
        store.remove(rec.fingerprint)
        assert store.count == 0
        assert store.lookup(rec.fingerprint) is None

    def test_remove_nonexistent_is_noop(self, tmp_path):
        store = self._store(tmp_path)
        store.remove("nonexistent")  # should not raise
        assert store.count == 0

    def test_all_records(self, tmp_path):
        store = self._store(tmp_path)
        store.record_file("Screenshot A.png", 100)
        store.record_file("Screenshot B.png", 200)
        records = store.all_records()
        assert len(records) == 2
        names = {r.original_name for r in records}
        assert names == {"Screenshot A.png", "Screenshot B.png"}


# ── Status transitions ───────────────────────────────────────────


class TestStatusTransitions:
    def _store_with_file(self, tmp_path, name="Screenshot A.png", size=100):
        store = MemoryStore(tmp_path / "memory.json")
        rec = store.record_file(name, size)
        return store, rec

    def test_initial_status_is_new(self, tmp_path):
        _, rec = self._store_with_file(tmp_path)
        assert rec.status == "new"

    def test_new_to_suggested(self, tmp_path):
        store, rec = self._store_with_file(tmp_path)
        store.update_suggestion(rec.fingerprint, "quarterly report.png")
        assert rec.status == "suggested"
        assert rec.suggested_name == "quarterly report.png"
        assert rec.last_updated != ""

    def test_suggested_to_renamed_via_accept(self, tmp_path):
        store, rec = self._store_with_file(tmp_path)
        store.update_suggestion(rec.fingerprint, "report.png")
        store.accept_suggestion(rec.fingerprint, "quarterly-report.png")
        assert rec.status == "renamed"
        assert rec.user_name == "quarterly-report.png"
        assert rec.last_known_name == "quarterly-report.png"

    def test_suggested_to_ignored_via_reject(self, tmp_path):
        store, rec = self._store_with_file(tmp_path)
        store.update_suggestion(rec.fingerprint, "report.png")
        store.reject_suggestion(rec.fingerprint)
        assert rec.status == "ignored"

    def test_new_to_renamed_via_record_rename(self, tmp_path):
        store, rec = self._store_with_file(tmp_path)
        store.record_rename(rec.fingerprint, "my-screenshot.png")
        assert rec.status == "renamed"
        assert rec.last_known_name == "my-screenshot.png"
        assert rec.user_name == "my-screenshot.png"
        # Fingerprint should NOT change — it's keyed on original name
        assert "Screenshot A.png" in rec.fingerprint

    def test_new_to_trashed(self, tmp_path):
        store, rec = self._store_with_file(tmp_path)
        store.mark_trashed(rec.fingerprint)
        assert rec.status == "trashed"

    def test_update_suggestion_unknown_key_raises(self, tmp_path):
        store, _ = self._store_with_file(tmp_path)
        with pytest.raises(KeyError):
            store.update_suggestion("nonexistent", "name.png")

    def test_accept_suggestion_unknown_key_raises(self, tmp_path):
        store, _ = self._store_with_file(tmp_path)
        with pytest.raises(KeyError):
            store.accept_suggestion("nonexistent", "name.png")

    def test_reject_suggestion_unknown_key_raises(self, tmp_path):
        store, _ = self._store_with_file(tmp_path)
        with pytest.raises(KeyError):
            store.reject_suggestion("nonexistent")

    def test_record_rename_unknown_key_raises(self, tmp_path):
        store, _ = self._store_with_file(tmp_path)
        with pytest.raises(KeyError):
            store.record_rename("nonexistent", "name.png")

    def test_mark_trashed_unknown_key_raises(self, tmp_path):
        store, _ = self._store_with_file(tmp_path)
        with pytest.raises(KeyError):
            store.mark_trashed("nonexistent")


# ── Persistence (save → load round-trip) ─────────────────────────


class TestPersistence:
    def test_save_and_load_empty(self, tmp_path):
        path = tmp_path / "memory.json"
        store = MemoryStore(path)
        store.save()

        store2 = MemoryStore(path)
        store2.load()
        assert store2.count == 0

    def test_save_and_load_with_records(self, tmp_path):
        path = tmp_path / "memory.json"
        store = MemoryStore(path)
        rec = store.record_file("Screenshot 2024-01-01.png", 5000)
        store.update_suggestion(rec.fingerprint, "report.png")
        store.save()

        store2 = MemoryStore(path)
        store2.load()
        assert store2.count == 1
        loaded = store2.lookup(rec.fingerprint)
        assert loaded is not None
        assert loaded.original_name == "Screenshot 2024-01-01.png"
        assert loaded.status == "suggested"
        assert loaded.suggested_name == "report.png"

    def test_save_and_load_multiple_records(self, tmp_path):
        path = tmp_path / "memory.json"
        store = MemoryStore(path)
        store.record_file("Screenshot A.png", 100)
        store.record_file("Screenshot B.png", 200)
        store.record_file("Screenshot C.png", 300)
        store.save()

        store2 = MemoryStore(path)
        store2.load()
        assert store2.count == 3
        assert store2.lookup_by_name("Screenshot B.png") is not None

    def test_load_preserves_meta(self, tmp_path):
        path = tmp_path / "memory.json"
        store = MemoryStore(path)
        rec = store.record_file("Screenshot A.png", 100)
        rec.meta = {"llm_model": "gemma-3b", "tokens": 42}
        store.save()

        store2 = MemoryStore(path)
        store2.load()
        loaded = store2.lookup(rec.fingerprint)
        assert loaded is not None
        assert loaded.meta["llm_model"] == "gemma-3b"
        assert loaded.meta["tokens"] == 42

    def test_load_corrupted_json_resets(self, tmp_path):
        path = tmp_path / "memory.json"
        path.write_text("{invalid json!!!")
        store = MemoryStore(path)
        store.load()
        assert store.count == 0

    def test_load_missing_version_key_resets(self, tmp_path):
        path = tmp_path / "memory.json"
        path.write_text(json.dumps({"not_files": True}))
        store = MemoryStore(path)
        store.load()
        assert store.count == 0

    def test_load_skips_malformed_entry(self, tmp_path):
        path = tmp_path / "memory.json"
        # One good entry, one bad entry with invalid status
        data = {
            "version": 1,
            "files": {
                "good.png|100": {
                    "fingerprint": "good.png|100",
                    "original_name": "good.png",
                    "last_known_name": "good.png",
                    "size": 100,
                    "extension": ".png",
                    "status": "new",
                },
                "bad.png|200": {
                    "fingerprint": "bad.png|200",
                    "status": "invalid_status",
                },
            },
        }
        path.write_text(json.dumps(data))

        store = MemoryStore(path)
        store.load()
        assert store.count == 1
        assert store.lookup("good.png|100") is not None

    def test_load_replaces_in_memory_data(self, tmp_path):
        """Loading replaces whatever was in memory."""
        path = tmp_path / "memory.json"
        store = MemoryStore(path)
        store.record_file("Old.png", 1)
        store.save()

        store2 = MemoryStore(path)
        store2.record_file("Transient.png", 2)  # in-memory only
        assert store2.count == 1  # not loaded from disk yet

        store2.load()  # load from disk replaces in-memory state
        assert store2.count == 1
        assert store2.lookup_by_name("Old.png") is not None
        assert store2.lookup_by_name("Transient.png") is None

    def test_file_created_on_save(self, tmp_path):
        path = tmp_path / "subdir" / "memory.json"
        store = MemoryStore(path)
        store.save()
        assert path.exists()


# ── get_unprocessed ──────────────────────────────────────────────


class TestGetUnprocessed:
    def test_returns_only_new(self, tmp_path):
        store = MemoryStore(tmp_path / "memory.json")
        rec1 = store.record_file("Screenshot A.png", 100)  # new
        rec2 = store.record_file("Screenshot B.png", 200)  # new
        rec3 = store.record_file("Screenshot C.png", 300)  # will be suggested
        store.update_suggestion(rec3.fingerprint, "report.png")

        active = {rec1.fingerprint, rec2.fingerprint, rec3.fingerprint}
        unprocessed = store.get_unprocessed(active)
        fps = {r.fingerprint for r in unprocessed}
        assert rec1.fingerprint in fps
        assert rec2.fingerprint in fps
        assert rec3.fingerprint not in fps

    def test_ignores_unknown_fingerprints(self, tmp_path):
        store = MemoryStore(tmp_path / "memory.json")
        active = {"nonexistent.png|999"}
        assert store.get_unprocessed(active) == []

    def test_empty_active_set(self, tmp_path):
        store = MemoryStore(tmp_path / "memory.json")
        store.record_file("Screenshot A.png", 100)
        assert store.get_unprocessed(set()) == []


# ── Prune stale ──────────────────────────────────────────────────


class TestPruneStale:
    def _make_old_record(self, store, name, size, days_old=100):
        """Create a record with last_updated set to days_old days ago."""
        from datetime import timedelta

        rec = store.record_file(name, size)
        # Wind back last_updated to simulate age
        old_time = datetime.now(tz=timezone.utc) - timedelta(days=days_old)
        rec.last_updated = old_time.isoformat()
        return rec

    def test_prunes_old_inactive_records(self, tmp_path):
        store = MemoryStore(tmp_path / "memory.json")
        rec1 = store.record_file("Screenshot A.png", 100)
        # Make B old and inactive
        self._make_old_record(store, "Screenshot B.png", 200, days_old=100)

        pruned = store.prune_stale(active_fingerprints={rec1.fingerprint})
        assert pruned == 1
        assert store.count == 1
        assert store.lookup(rec1.fingerprint) is not None

    def test_keeps_recent_inactive_records(self, tmp_path):
        """Recently trashed/renamed files should not be pruned."""
        store = MemoryStore(tmp_path / "memory.json")
        rec1 = store.record_file("Screenshot A.png", 100)
        # B is inactive but was updated only 10 days ago
        rec2 = self._make_old_record(store, "Screenshot B.png", 200, days_old=10)

        pruned = store.prune_stale(active_fingerprints={rec1.fingerprint}, max_age_days=90)
        assert pruned == 0
        assert store.count == 2
        assert store.lookup(rec2.fingerprint) is not None

    def test_prune_all_old(self, tmp_path):
        store = MemoryStore(tmp_path / "memory.json")
        self._make_old_record(store, "Screenshot A.png", 100, days_old=100)
        self._make_old_record(store, "Screenshot B.png", 200, days_old=100)
        pruned = store.prune_stale(active_fingerprints=set(), max_age_days=90)
        assert pruned == 2
        assert store.count == 0

    def test_prune_none_when_all_active(self, tmp_path):
        store = MemoryStore(tmp_path / "memory.json")
        rec = store.record_file("Screenshot A.png", 100)
        pruned = store.prune_stale(active_fingerprints={rec.fingerprint})
        assert pruned == 0
        assert store.count == 1

    def test_prune_respects_age_threshold_boundary(self, tmp_path):
        """A record exactly at the threshold should NOT be pruned."""
        store = MemoryStore(tmp_path / "memory.json")
        # Record is exactly 90 days old — should be kept (uses >, not >=)
        self._make_old_record(store, "Screenshot A.png", 100, days_old=90)
        pruned = store.prune_stale(active_fingerprints=set(), max_age_days=90)
        assert pruned == 0
        assert store.count == 1

    def test_trashed_file_preserved_within_window(self, tmp_path):
        """Simulate the restore-from-trash scenario."""
        store = MemoryStore(tmp_path / "memory.json")
        rec = store.record_file("Screenshot A.png", 100)
        store.mark_trashed(rec.fingerprint)
        # File was just trashed (last_updated is now), not on Desktop
        pruned = store.prune_stale(active_fingerprints=set(), max_age_days=90)
        assert pruned == 0
        assert store.count == 1
        # If file reappears, record_file is idempotent and returns the trashed record
        rec2 = store.record_file("Screenshot A.png", 100)
        assert rec2.status == "trashed"


# ── Edge cases ───────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_file_size(self, tmp_path):
        store = MemoryStore(tmp_path / "memory.json")
        rec = store.record_file("Screenshot empty.png", 0)
        assert rec.size == 0
        assert rec.fingerprint == "Screenshot empty.png|0"

    def test_special_characters_in_name(self, tmp_path):
        store = MemoryStore(tmp_path / "memory.json")
        name = "Screenshot (2) [copy] & stuff@#$%.png"
        rec = store.record_file(name, 100)
        assert store.lookup_by_name(name) is not None
        assert name in rec.fingerprint

    def test_long_filename(self, tmp_path):
        store = MemoryStore(tmp_path / "memory.json")
        name = "Screenshot " + "x" * 200 + ".png"
        rec = store.record_file(name, 100)
        assert len(rec.fingerprint) > 200

    def test_multiple_saves(self, tmp_path):
        """Multiple save cycles don't corrupt data."""
        path = tmp_path / "memory.json"
        store = MemoryStore(path)
        rec = store.record_file("Screenshot A.png", 100)
        store.save()
        store.update_suggestion(rec.fingerprint, "report.png")
        store.save()
        store.accept_suggestion(rec.fingerprint, "final.png")
        store.save()

        store2 = MemoryStore(path)
        store2.load()
        loaded = store2.lookup(rec.fingerprint)
        assert loaded is not None
        assert loaded.status == "renamed"
        assert loaded.last_known_name == "final.png"
        assert loaded.suggested_name == "report.png"

    def test_record_after_trashed_stays_trashed(self, tmp_path):
        """If a file was trashed and reappears, record_file returns existing record."""
        store = MemoryStore(tmp_path / "memory.json")
        rec = store.record_file("Screenshot A.png", 100)
        store.mark_trashed(rec.fingerprint)
        assert rec.status == "trashed"

        # Same file appears again (e.g., restored from trash)
        rec2 = store.record_file("Screenshot A.png", 100)
        assert rec2.status == "trashed"  # still tracked as trashed
        assert rec2 is rec
