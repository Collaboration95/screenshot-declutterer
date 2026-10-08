from datetime import datetime, timedelta, timezone

import ss_dcl.app as flask_app
from ss_dcl import usage
from ss_dcl.sources import decision_key


def test_source_identity_decisions_sorting_and_rescan(client, monkeypatch):
    c, desktop = client
    tracked = desktop / "tracked"
    tracked.mkdir()
    name = "Screenshot same.png"
    (desktop / name).write_bytes(b"desktop")
    (tracked / name).write_bytes(b"tracked")
    (desktop / "Screenshot other.jpg").write_bytes(b"other")
    c.put("/api/settings", json={"tracked_folders": [str(tracked)]})
    created = datetime(2026, 10, 8, 9, tzinfo=timezone.utc)
    now = created + timedelta(minutes=13)
    monkeypatch.setattr(usage, "utc_now", lambda: now)
    records = {
        path.resolve(): usage.UsageMetadata(created, created + timedelta(minutes=2))
        for path in (desktop / name, tracked / name, desktop / "Screenshot other.jpg")
    }
    query = []

    def read(paths):
        query.append(paths)
        return records

    monkeypatch.setattr(usage, "read_usage", read)
    files = c.get("/api/screenshots?sort=name").get_json()
    assert len(files) == 3
    assert all(f["cleanup"]["eligible"] for f in files)
    assert len({f["fingerprint"] for f in files}) == 3
    assert all("_path" not in f for f in files)
    assert c.get("/api/state").get_json()["decisions"] == {}
    decisions = {name: "keep", decision_key(str(tracked), name): "trash"}
    c.put("/api/state", json={"decisions": decisions})
    files = c.get("/api/screenshots?sort=name_desc").get_json()
    assert [f["name"] for f in files] == sorted([f["name"] for f in files], reverse=True)
    assert all(not f["cleanup"]["eligible"] for f in files if f["name"] == name)
    assert all(f["cleanup"]["timing_match"] for f in files)
    records[(desktop / "Screenshot other.jpg").resolve()] = usage.UsageMetadata(
        created, created + timedelta(minutes=12)
    )
    assert not any(f["cleanup"]["eligible"] for f in c.get("/api/screenshots").get_json())
    assert len(query) == 3
    assert c.get("/api/state").get_json()["decisions"] == decisions


def test_optional_metadata_preserves_manual_scan(client):
    c, desktop = client
    (desktop / "Screenshot regular.png").write_bytes(b"image")
    file = c.get("/api/screenshots").get_json()[0]
    assert file["usage"] == {"created_at": None, "last_opened_at": None}
    assert file["cleanup"] == {"eligible": False, "timing_match": False, "reason": None}
    assert file["memory_status"] == "new"


def test_metadata_cannot_escape_source_via_symlink(client, monkeypatch, tmp_path):
    c, desktop = client
    outside = tmp_path.parent / "outside.png"
    outside.write_bytes(b"outside")
    (desktop / "Screenshot linked.png").symlink_to(outside)
    seen = []
    monkeypatch.setattr(usage, "read_usage", lambda paths: seen.extend(paths) or {})
    assert c.get("/api/screenshots").get_json() == []
    assert seen == []
    assert flask_app._resolve_source_file("Desktop", "Screenshot linked.png") is None
