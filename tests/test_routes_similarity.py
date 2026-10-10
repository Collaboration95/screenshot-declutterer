"""Matches reference active files in their actual source and survive app restart."""

from unittest.mock import patch

from PIL import Image

import ss_dcl.app as flask_app


def test_exact_cross_source_cache_rename_disappear_and_restart(client):
    c, desktop = client
    tracked = desktop / "tracked"
    tracked.mkdir()
    name = "Screenshot duplicate.bmp"
    Image.new("RGB", (64, 48), "red").save(desktop / name)
    (tracked / name).write_bytes((desktop / name).read_bytes())
    assert c.put("/api/settings", json={"tracked_folders": [str(tracked)]}).status_code == 200
    files = c.get("/api/screenshots").json
    assert len(files) == 2
    desktop_file = next(f for f in files if f["source"] == "Desktop")
    peer = desktop_file["matches"][0]
    assert peer == {"source": str(tracked), "name": name, "kind": "identical", "distance": 0}
    assert "_record" not in desktop_file and "_path" not in desktop_file
    assert "byte_hash" not in desktop_file
    fp = desktop_file["fingerprint"]
    flask_app._reset_memory()
    with patch("ss_dcl.similarity.compute_signals", side_effect=AssertionError("warm cache")):
        assert len(c.get("/api/screenshots").json) == 2
    renamed = "Screenshot renamed.bmp"
    assert c.post("/api/rename", json={"old_name": name, "new_name": renamed}).status_code == 200
    files = c.get("/api/screenshots?sort=name_desc").json
    assert next(f for f in files if f["source"] == "Desktop")["fingerprint"] == fp
    assert next(f for f in files if f["source"] != "Desktop")["matches"][0]["name"] == renamed
    (tracked / name).unlink()
    assert c.get("/api/screenshots").json[0]["matches"] == []


def test_same_size_edit_and_untracking_remove_stale_matches(client):
    c, desktop = client
    name = "Screenshot A.bmp"
    Image.new("RGB", (50, 50), "red").save(desktop / name)
    other = desktop / "Screenshot B.bmp"
    other.write_bytes((desktop / name).read_bytes())
    assert c.get("/api/screenshots").json[0]["matches"][0]["kind"] == "identical"
    Image.new("RGB", (50, 50), "blue").save(other)
    assert all(not f["matches"] for f in c.get("/api/screenshots").json)


def test_outside_symlink_never_hashed(client, tmp_path):
    c, desktop = client
    outside = tmp_path.parent / "outside-similarity.png"
    Image.new("RGB", (10, 10), "red").save(outside)
    (desktop / "Screenshot escaped.png").symlink_to(outside)
    with patch("ss_dcl.similarity.compute_signals", side_effect=AssertionError("escaped file")):
        assert c.get("/api/screenshots").json == []
