"""Tests for app.py routes, screenshot scanning, thumbnails, state, and ordering."""

import io
import json
from unittest.mock import patch

import pytest

import app as flask_app


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


# ── GET / ─────────────────────────────────────────────────────────────────────


def test_index_returns_html(client):
    c, _ = client
    r = c.get("/")
    assert r.status_code == 200
    assert b"Screenshot Declutterer" in r.data


def test_index_has_undo_button(client):
    c, _ = client
    r = c.get("/")
    assert b'id="undo-btn"' in r.data


def test_index_column_order_keep_unsorted_trash(client):
    c, _ = client
    html = c.get("/").data.decode()
    keep_pos = html.index('id="col-keep"')
    unsorted_pos = html.index('id="col-unsorted"')
    trash_pos = html.index('id="col-trash"')
    assert keep_pos < unsorted_pos < trash_pos


def test_index_has_sort_select(client):
    c, _ = client
    r = c.get("/")
    assert b'id="sort-select"' in r.data


# ── GET /api/screenshots ──────────────────────────────────────────────────────


def test_api_screenshots_empty(client):
    c, _ = client
    r = c.get("/api/screenshots")
    assert r.status_code == 200
    assert json.loads(r.data) == []


def test_api_screenshots_returns_only_top_level_pngs(client):
    c, desktop = client

    (desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png").write_bytes(b"")
    (desktop / "Screenshot 2024-01-02 at 09.00.00 AM.png").write_bytes(b"")

    sub = desktop / "subdir"
    sub.mkdir()
    (sub / "Screenshot 2024-01-03 at 08.00.00 AM.png").write_bytes(b"")

    (desktop / "photo.png").write_bytes(b"")

    r = c.get("/api/screenshots")
    names = [f["name"] for f in json.loads(r.data)]
    assert len(names) == 2
    assert all(n.startswith("Screenshot") for n in names)


def test_api_screenshots_sorted_by_name(client):
    c, desktop = client
    (desktop / "Screenshot 2024-03-01 at 10.00.00 AM.png").write_bytes(b"")
    (desktop / "Screenshot 2024-01-01 at 10.00.00 AM.png").write_bytes(b"")
    names = [f["name"] for f in json.loads(c.get("/api/screenshots").data)]
    assert names == sorted(names)


def test_api_screenshots_returns_enriched_data(client):
    c, desktop = client
    (desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png").write_bytes(b"hello")
    r = c.get("/api/screenshots")
    files = json.loads(r.data)
    assert len(files) == 1
    f = files[0]
    assert "name" in f
    assert "size" in f
    assert "mtime" in f
    assert f["size"] == 5


def test_api_screenshots_sort_by_date(client):
    c, desktop = client
    import time

    f1 = desktop / "Screenshot 2024-01-01 at 10.00.00 AM.png"
    f2 = desktop / "Screenshot 2024-06-01 at 10.00.00 AM.png"
    f1.write_bytes(b"a")
    time.sleep(0.1)
    f2.write_bytes(b"b")

    names_asc = [f["name"] for f in json.loads(c.get("/api/screenshots?sort=date").data)]
    names_desc = [f["name"] for f in json.loads(c.get("/api/screenshots?sort=date_desc").data)]
    assert names_asc[0] == f1.name
    assert names_desc[0] == f2.name


def test_api_screenshots_sort_by_size(client):
    c, desktop = client
    (desktop / "Screenshot 2024-01-01 at 10.00.00 AM.png").write_bytes(b"aa")
    (desktop / "Screenshot 2024-06-01 at 10.00.00 AM.png").write_bytes(b"bbbbbb")

    names_asc = [f["name"] for f in json.loads(c.get("/api/screenshots?sort=size").data)]
    names_desc = [f["name"] for f in json.loads(c.get("/api/screenshots?sort=size_desc").data)]
    assert names_asc[0] == "Screenshot 2024-01-01 at 10.00.00 AM.png"
    assert names_desc[0] == "Screenshot 2024-06-01 at 10.00.00 AM.png"


def test_api_screenshots_default_sort_is_name(client):
    c, desktop = client
    (desktop / "Screenshot B.png").write_bytes(b"")
    (desktop / "Screenshot A.png").write_bytes(b"")
    names = [f["name"] for f in json.loads(c.get("/api/screenshots").data)]
    assert names == ["Screenshot A.png", "Screenshot B.png"]


# ── GET /api/image/<filename> ─────────────────────────────────────────────────


def test_api_image_serves_file(client):
    c, desktop = client
    img = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")

    r = c.get("/api/image/Screenshot 2024-01-01 at 12.00.00 PM.png")
    assert r.status_code == 200


def test_api_image_rejects_path_traversal(client):
    c, _ = client
    r = c.get("/api/image/../etc/passwd")
    assert r.status_code in (400, 404)


def test_api_image_rejects_subdir_path(client):
    c, _ = client
    r = c.get("/api/image/subdir/Screenshot.png")
    assert r.status_code in (400, 404)


def test_api_image_404_for_missing_file(client):
    c, _ = client
    r = c.get("/api/image/Screenshot_does_not_exist.png")
    assert r.status_code == 404


def test_api_image_content_type_png(client):
    c, desktop = client
    img = desktop / "Screenshot 2024-05-01 at 12.00.00 PM.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")

    r = c.get("/api/image/Screenshot 2024-05-01 at 12.00.00 PM.png")
    assert r.status_code == 200
    assert "image/png" in r.content_type


def test_api_image_has_cache_control_header(client):
    c, desktop = client
    img = desktop / "Screenshot 2024-05-01 at 12.00.00 PM.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")

    r = c.get("/api/image/Screenshot 2024-05-01 at 12.00.00 PM.png")
    assert r.status_code == 200
    assert "Cache-Control" in r.headers
    assert "max-age" in r.headers["Cache-Control"]


# ── GET /api/thumb/<filename> ─────────────────────────────────────────────────


def test_api_thumb_returns_thumbnail(client):
    c, desktop = client
    (desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png").write_bytes(_make_png(200, 200))

    r = c.get("/api/thumb/Screenshot 2024-01-01 at 12.00.00 PM.png")
    assert r.status_code == 200
    assert "image/png" in r.content_type


def test_api_thumb_caches_on_disk(client):
    c, desktop = client
    (desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png").write_bytes(_make_png(200, 200))

    c.get("/api/thumb/Screenshot 2024-01-01 at 12.00.00 PM.png")
    thumb_dir = desktop / "thumbs"
    assert (thumb_dir / "Screenshot 2024-01-01 at 12.00.00 PM.png").exists()


def test_api_thumb_has_longer_cache(client):
    c, desktop = client
    (desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png").write_bytes(_make_png(50, 50))

    r = c.get("/api/thumb/Screenshot 2024-01-01 at 12.00.00 PM.png")
    assert r.status_code == 200
    assert "max-age=86400" in r.headers["Cache-Control"]


def test_api_thumb_rejects_path_traversal(client):
    c, _ = client
    r = c.get("/api/thumb/../etc/passwd")
    assert r.status_code in (400, 404)


def test_api_thumb_404_for_missing_file(client):
    c, _ = client
    r = c.get("/api/thumb/Screenshot_does_not_exist.png")
    assert r.status_code == 404


def test_api_thumb_fallback_on_invalid_image(client):
    c, desktop = client
    (desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png").write_bytes(b"not-a-real-image")

    r = c.get("/api/thumb/Screenshot 2024-01-01 at 12.00.00 PM.png")
    assert r.status_code == 200


# ── GET/PUT /api/state ────────────────────────────────────────────────────────


def test_api_state_get_empty(client):
    c, _ = client
    r = c.get("/api/state")
    assert r.status_code == 200
    assert json.loads(r.data) == {"decisions": {}}


def test_api_state_save_and_load(client):
    c, _ = client
    state = {"decisions": {"Screenshot a.png": "keep", "Screenshot b.png": "trash"}}
    r = c.put("/api/state", data=json.dumps(state), content_type="application/json")
    assert r.status_code == 200
    assert json.loads(r.data) == {"ok": True}

    r = c.get("/api/state")
    assert json.loads(r.data) == state


def test_api_state_save_empty(client):
    c, _ = client
    c.put(
        "/api/state",
        data=json.dumps({"decisions": {"a.png": "keep"}}),
        content_type="application/json",
    )
    c.put(
        "/api/state",
        data=json.dumps({"decisions": {}}),
        content_type="application/json",
    )

    r = c.get("/api/state")
    assert json.loads(r.data) == {"decisions": {}}


# ── POST /api/done ────────────────────────────────────────────────────────────


def test_api_done_moves_files_to_trash(client):
    c, desktop = client
    f = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    f.write_bytes(b"")

    with patch("app.send2trash") as mock_trash:
        r = c.post(
            "/api/done",
            data=json.dumps({"filenames": [f.name]}),
            content_type="application/json",
        )
    assert r.status_code == 200
    assert json.loads(r.data) == {"ok": True}
    mock_trash.assert_called_once_with(str(f))


def test_api_done_returns_207_for_missing_file(client):
    c, _ = client
    r = c.post(
        "/api/done",
        data=json.dumps({"filenames": ["ghost.png"]}),
        content_type="application/json",
    )
    assert r.status_code == 207
    body = json.loads(r.data)
    assert body["ok"] is False
    assert len(body["errors"]) == 1


def test_api_done_rejects_path_traversal(client):
    c, _ = client
    r = c.post(
        "/api/done",
        data=json.dumps({"filenames": ["../etc/passwd"]}),
        content_type="application/json",
    )
    assert r.status_code == 207
    body = json.loads(r.data)
    assert any("invalid path" in e for e in body["errors"])


def test_api_done_empty_list(client):
    c, _ = client
    r = c.post(
        "/api/done",
        data=json.dumps({"filenames": []}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert json.loads(r.data) == {"ok": True}


def test_api_done_mixed_valid_and_invalid(client):
    c, desktop = client
    valid = desktop / "Screenshot 2024-06-01 at 10.00.00 AM.png"
    valid.write_bytes(b"")

    with patch("app.send2trash"):
        r = c.post(
            "/api/done",
            data=json.dumps({"filenames": [valid.name, "ghost.png"]}),
            content_type="application/json",
        )
    assert r.status_code == 207
    body = json.loads(r.data)
    assert body["ok"] is False
    assert len(body["errors"]) == 1
    assert "ghost.png" in body["errors"][0]


def test_api_done_no_json_body(client):
    c, _ = client
    r = c.post("/api/done", content_type="application/json")
    assert r.status_code == 200
    assert json.loads(r.data) == {"ok": True}


def test_api_done_multiple_files_trashed(client):
    c, desktop = client
    f1 = desktop / "Screenshot 2024-01-01 at 10.00.00 AM.png"
    f2 = desktop / "Screenshot 2024-01-02 at 10.00.00 AM.png"
    f1.write_bytes(b"")
    f2.write_bytes(b"")

    with patch("app.send2trash") as mock_trash:
        r = c.post(
            "/api/done",
            data=json.dumps({"filenames": [f1.name, f2.name]}),
            content_type="application/json",
        )
    assert r.status_code == 200
    assert mock_trash.call_count == 2


def test_api_done_cleans_up_state(client):
    c, desktop = client
    f = desktop / "Screenshot 2024-01-01 at 10.00.00 AM.png"
    f.write_bytes(b"")

    state = {"decisions": {f.name: "trash", "Screenshot other.png": "keep"}}
    c.put("/api/state", data=json.dumps(state), content_type="application/json")

    with patch("app.send2trash"):
        c.post(
            "/api/done",
            data=json.dumps({"filenames": [f.name]}),
            content_type="application/json",
        )

    r = c.get("/api/state")
    saved = json.loads(r.data)
    assert f.name not in saved["decisions"]
    assert "Screenshot other.png" in saved["decisions"]


def test_api_done_cleans_up_thumbnail(client):
    c, desktop = client
    f = desktop / "Screenshot 2024-01-01 at 10.00.00 AM.png"
    f.write_bytes(_make_png(50, 50))
    c.get("/api/thumb/Screenshot 2024-01-01 at 10.00.00 AM.png")

    thumb_dir = desktop / "thumbs"
    assert (thumb_dir / f.name).exists()

    with patch("app.send2trash"):
        c.post(
            "/api/done",
            data=json.dumps({"filenames": [f.name]}),
            content_type="application/json",
        )

    assert not (thumb_dir / f.name).exists()


# ── Additional tests ─────────────────────────────────────────────────────────


def test_api_screenshots_ignores_non_png_screenshot_files(client):
    c, desktop = client
    (desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png").write_bytes(b"")
    (desktop / "Screenshot 2024-01-01 at 12.00.00 PM.jpg").write_bytes(b"")

    names = [f["name"] for f in json.loads(c.get("/api/screenshots").data)]
    assert len(names) == 1
    assert names[0].endswith(".png")


def test_open_browser_skips_when_werkzeug_reloader(monkeypatch):
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")

    import app as flask_app

    with patch("app.webbrowser") as mock_wb:
        flask_app._open_browser()
    mock_wb.open_new_tab.assert_not_called()


def test_open_browser_opens_tab(monkeypatch):
    monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)

    import app as flask_app

    with patch("app.time.sleep"), patch("app.webbrowser") as mock_wb:
        flask_app._open_browser()
    mock_wb.open_new_tab.assert_called_once_with("http://localhost:5001")


def test_get_screenshots_returns_list(client):
    _, desktop = client
    (desktop / "Screenshot 2024-02-01 at 09.00.00 AM.png").write_bytes(b"")
    result = flask_app.get_screenshots()
    assert isinstance(result, list)
    assert all(isinstance(f, dict) for f in result)
    assert all("name" in f and "size" in f and "mtime" in f for f in result)
