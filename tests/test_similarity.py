"""Signal persistence, exact identity, and direct-neighbor graph invariants."""

import json
import os
from dataclasses import replace
from unittest.mock import patch

import pytest
from PIL import Image

from ss_dcl.memory import MemoryStore
from ss_dcl.similarity import Signals, cached_signals, direct_matches, near_distance


def textured_signal(value, *, width=640, height=400):
    return Signals("a" * 32, f"{value:064x}", width, height, "80" * 768, 40)


def test_direct_matches_are_symmetric_exact_first_and_not_transitive():
    # A-B and B-C each differ by ten bits; A-C differs by twenty.
    a = int("a" * 64, 16)
    b = a ^ ((1 << 10) - 1)
    c = b ^ (((1 << 10) - 1) << 10)
    files = [{"name": n, "source": "Desktop", "size": 100} for n in ("A", "B", "C", "D")]
    signals = [replace(textured_signal(v), byte_hash=str(i) * 32) for i, v in enumerate((a, b, c))]
    signals.append(signals[0])
    matches = direct_matches(files, signals)
    assert [(m["name"], m["kind"]) for m in matches[0]] == [("D", "identical"), ("B", "similar")]
    assert {m["name"] for m in matches[1]} == {"A", "C", "D"}
    assert {m["name"] for m in matches[2]} == {"B"}
    for i, peers in enumerate(matches):
        for peer in peers:
            j = next(j for j, f in enumerate(files) if f["name"] == peer["name"])
            assert any(
                m["name"] == files[i]["name"] and m["kind"] == peer["kind"] for m in matches[j]
            )


def test_same_hash_different_byte_size_is_not_exact():
    files = [{"name": n, "source": "Desktop", "size": size} for n, size in (("A", 1), ("B", 2))]
    assert direct_matches(files, [Signals("a" * 32), Signals("a" * 32)]) == [[], []]
    assert direct_matches(files, [None, Signals("a" * 32)]) == [[], []]


@pytest.mark.parametrize("bits", [0, 8, 248, 256])
def test_low_information_hashes_do_not_match(bits):
    signal = textured_signal((1 << bits) - 1)
    assert near_distance(signal, signal) is None


def test_hamming_and_aspect_boundaries():
    a = textured_signal(int("a" * 64, 16), width=1000, height=1000)
    assert a.dhash
    assert near_distance(a, replace(a, dhash=f"{int(a.dhash, 16) ^ 1023:064x}")) == 10
    assert near_distance(a, replace(a, dhash=f"{int(a.dhash, 16) ^ 2047:064x}")) is None
    assert near_distance(a, replace(a, width=1029)) == 0
    assert near_distance(a, replace(a, width=1030)) == 0
    assert near_distance(replace(a, width=1030), a) == 0
    assert near_distance(a, replace(a, width=1031)) is None
    assert near_distance(replace(a, width=1031), a) is None
    assert near_distance(a, replace(a, width=0)) is None


def test_cached_signals_persist_and_invalidate_same_size_restored_mtime(tmp_path):
    path = tmp_path / "Screenshot A.bmp"
    Image.new("RGB", (80, 60), "red").save(path)
    store = MemoryStore(tmp_path / "memory.json")
    record = store.record_file(path.name, path.stat().st_size)
    first, changed = cached_signals(path, record)
    assert first and changed
    store.save()
    store.load()
    record = store.lookup(record.fingerprint)
    assert record
    with patch("ss_dcl.similarity.compute_signals", side_effect=AssertionError("cache miss")):
        assert cached_signals(path, record) == (first, False)
    st = path.stat()
    Image.new("RGB", (80, 60), "blue").save(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))
    second, changed = cached_signals(path, record)
    assert second and changed and first.byte_hash != second.byte_hash
    assert path.stat().st_size == st.st_size


@pytest.mark.parametrize(
    "bad",
    [{}, {"byte_hash": "x"}, {"byte_hash": "x" * 32}, {"byte_hash": "a" * 32, "rgb": "zz"}],
)
def test_malformed_persisted_signals_recompute(tmp_path, bad):
    from ss_dcl.similarity import SIGNAL_VERSION, stat_key

    path = tmp_path / "Screenshot A.png"
    Image.new("RGB", (20, 20), "white").save(path)
    rec = MemoryStore(tmp_path / "memory.json").record_file(path.name, path.stat().st_size)
    rec.meta["similarity"] = {
        "version": SIGNAL_VERSION,
        "stat": stat_key(path.stat()),
        "signals": bad,
    }
    signals, changed = cached_signals(path, rec)
    assert signals and changed
    assert len(signals.byte_hash) == 32


def test_unreadable_and_changed_files_do_not_use_stale_signals(tmp_path):
    path = tmp_path / "Screenshot A.png"
    path.write_bytes(b"invalid image")
    rec = MemoryStore(tmp_path / "memory.json").record_file(path.name, path.stat().st_size)
    signal, changed = cached_signals(path, rec)
    assert signal and changed and signal.dhash is None
    # Race between hash and end-of-read stat: no newly computed cache published.
    with patch("ss_dcl.similarity.compute_signals") as compute:
        rec.meta.clear()

        def rewrite(_):
            path.write_bytes(b"changed image")
            return signal

        compute.side_effect = rewrite
        assert cached_signals(path, rec) == (None, False)
        assert "similarity" not in rec.meta
    path.unlink()
    assert cached_signals(path, rec) == (None, False)
    # Hashes serialize only as compact JSON strings/numbers.
    json.dumps(rec.meta)
