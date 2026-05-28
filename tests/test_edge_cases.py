import io
import json
from unittest.mock import patch

import pytest
import src.ss_dcl.app as flask_app
from src.ss_dcl.app import _atomic_write


def _make_png(width=10, height=10, color="red"):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    thumb_dir = tmp_path / "thumbs"
    thumb_dir.mkdir()
    monkeypatch.setattr(flask_app, "DESKTOP", tmp_path)
    monkeypatch.setattr(flask_app, "THUMB_DIR", thumb_dir)
    monkeypatch.setattr(flask_app, "STATE_FILE", tmp_path / "state.json")
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        yield c, tmp_path


def test_state_file_corruption(client):
    c, _desktop = client
    flask_app.STATE_FILE.write_text("{invalid json")
    r = c.get("/api/state")
    assert r.status_code == 200
    assert r.get_json() == {"decisions": {}}


def test_thumbnail_regeneration_on_mtime_change(client):
    c, desktop = client
    import time

    f = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    f.write_bytes(_make_png(100, 100))
    r1 = c.get("/api/thumb/Screenshot 2024-01-01 at 12.00.00 PM.png")
    assert r1.status_code == 200
    time.sleep(0.1)
    f.write_bytes(_make_png(200, 200, "blue"))
    r2 = c.get("/api/thumb/Screenshot 2024-01-01 at 12.00.00 PM.png")
    assert r2.status_code == 200


def test_invalid_sort_parameter_rejected(client):
    c, desktop = client
    (desktop / "Screenshot B.png").write_bytes(b"")
    (desktop / "Screenshot A.png").write_bytes(b"")
    r = c.get("/api/screenshots?sort=invalid_sort")
    assert r.status_code == 400


def test_state_file_unexpected_json_structure(client):
    c, _ = client
    flask_app.STATE_FILE.write_text('{"not_decisions": true}')
    r = c.get("/api/state")
    assert r.status_code == 200


def test_generate_thumbnail_unit(client):
    _c, desktop = client

    src = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    src.write_bytes(_make_png(500, 500))
    dst = desktop / "thumbs" / src.name
    flask_app._generate_thumbnail(src, dst)
    assert dst.exists()
    assert dst.stat().st_size < src.stat().st_size


def test_atomic_write_creates_file(client):
    _c, desktop = client
    target = desktop / "test_atomic.json"
    _atomic_write(target, '{"test": true}')
    assert target.exists()
    assert json.loads(target.read_text()) == {"test": True}


def test_atomic_write_cleanup_on_failure(tmp_path):
    target = tmp_path / "subdir" / "nonexistent" / "file.json"
    with pytest.raises(FileNotFoundError):
        _atomic_write(target, "content")
    assert not target.exists()


def test_done_with_pattern_mismatch(client):
    c, desktop = client
    non_screenshot = desktop / "photo.png"
    non_screenshot.write_bytes(b"data")
    r = c.post("/api/done", json={"filenames": ["photo.png"]})
    assert r.status_code == 207
    body = r.get_json()
    assert any("invalid filename pattern" in e for e in body["errors"])


def test_done_large_batch(client):
    c, desktop = client
    names = []
    for i in range(50):
        name = f"Screenshot {i:04d}.png"
        (desktop / name).write_bytes(b"")
        names.append(name)
    with patch("src.ss_dcl.app.send2trash"):
        r = c.post("/api/done", json={"filenames": names})
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_unicode_filename(client):
    c, desktop = client
    (desktop / "Screenshot 日本語.png").write_bytes(b"data")
    r = c.get("/api/screenshots")
    names = [f["name"] for f in r.get_json()]
    assert "Screenshot 日本語.png" in names


def test_filename_with_spaces(client):
    c, desktop = client
    (desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png").write_bytes(_make_png(50, 50))
    r = c.get("/api/thumb/Screenshot 2024-01-01 at 12.00.00 PM.png")
    assert r.status_code == 200


def test_empty_screenshots_with_saved_state(client):
    c, _ = client
    flask_app.STATE_FILE.write_text(json.dumps({"decisions": {"Screenshot old.png": "keep"}}))
    r = c.get("/api/screenshots")
    assert r.get_json() == []
