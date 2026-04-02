"""Tests for app.py routes and screenshot scanning."""

import json
from unittest.mock import patch

import pytest

import app as flask_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Flask test client with a temporary Desktop."""
    monkeypatch.setattr(flask_app, "DESKTOP", tmp_path)
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
    """Global undo button should be present in the header."""
    c, _ = client
    r = c.get("/")
    assert b'id="undo-btn"' in r.data


def test_index_column_order_keep_unsorted_trash(client):
    """Keep column should appear before Unsorted, Trash should appear last."""
    c, _ = client
    html = c.get("/").data.decode()
    keep_pos = html.index('id="col-keep"')
    unsorted_pos = html.index('id="col-unsorted"')
    trash_pos = html.index('id="col-trash"')
    assert keep_pos < unsorted_pos < trash_pos


# ── GET /api/screenshots ──────────────────────────────────────────────────────


def test_api_screenshots_empty(client):
    c, _ = client
    r = c.get("/api/screenshots")
    assert r.status_code == 200
    assert json.loads(r.data) == []


def test_api_screenshots_returns_only_top_level_pngs(client):
    c, desktop = client

    # Top-level screenshots — should appear
    (desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png").write_bytes(b"")
    (desktop / "Screenshot 2024-01-02 at 09.00.00 AM.png").write_bytes(b"")

    # Sub-directory screenshot — must NOT appear
    sub = desktop / "subdir"
    sub.mkdir()
    (sub / "Screenshot 2024-01-03 at 08.00.00 AM.png").write_bytes(b"")

    # Non-screenshot png — must NOT appear
    (desktop / "photo.png").write_bytes(b"")

    r = c.get("/api/screenshots")
    names = json.loads(r.data)
    assert len(names) == 2
    assert all(n.startswith("Screenshot") for n in names)


def test_api_screenshots_sorted(client):
    c, desktop = client
    (desktop / "Screenshot 2024-03-01 at 10.00.00 AM.png").write_bytes(b"")
    (desktop / "Screenshot 2024-01-01 at 10.00.00 AM.png").write_bytes(b"")
    names = json.loads(c.get("/api/screenshots").data)
    assert names == sorted(names)


# ── GET /api/image/<filename> ─────────────────────────────────────────────────


def test_api_image_serves_file(client):
    c, desktop = client
    img = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")  # PNG magic bytes

    r = c.get("/api/image/Screenshot 2024-01-01 at 12.00.00 PM.png")
    assert r.status_code == 200


def test_api_image_rejects_path_traversal(client):
    # Flask normalizes ../ before the route handler fires, so 404 is acceptable too
    c, _ = client
    r = c.get("/api/image/../etc/passwd")
    assert r.status_code in (400, 404)


def test_api_image_rejects_subdir_path(client):
    # Slashes in the filename segment are not matched by Flask's <filename> rule
    c, _ = client
    r = c.get("/api/image/subdir/Screenshot.png")
    assert r.status_code in (400, 404)


def test_api_image_404_for_missing_file(client):
    c, _ = client
    r = c.get("/api/image/Screenshot_does_not_exist.png")
    assert r.status_code == 404


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


# ── Additional tests ─────────────────────────────────────────────────────────


def test_api_done_mixed_valid_and_invalid(client):
    """One valid file + one missing file → 207 with partial errors."""
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
    """POST with no body at all — should treat filenames as empty list."""
    c, _ = client
    r = c.post("/api/done", content_type="application/json")
    assert r.status_code == 200
    assert json.loads(r.data) == {"ok": True}


def test_api_done_multiple_files_trashed(client):
    """Multiple valid files should all be sent to trash."""
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


def test_api_image_content_type_png(client):
    """Served image should have a PNG-compatible content type."""
    c, desktop = client
    img = desktop / "Screenshot 2024-05-01 at 12.00.00 PM.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")

    r = c.get("/api/image/Screenshot 2024-05-01 at 12.00.00 PM.png")
    assert r.status_code == 200
    assert "image/png" in r.content_type


def test_api_image_has_cache_control_header(client):
    """Image endpoint should include a Cache-Control header for browser caching."""
    c, desktop = client
    img = desktop / "Screenshot 2024-05-01 at 12.00.00 PM.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")

    r = c.get("/api/image/Screenshot 2024-05-01 at 12.00.00 PM.png")
    assert r.status_code == 200
    assert "Cache-Control" in r.headers
    assert "max-age" in r.headers["Cache-Control"]


def test_api_screenshots_ignores_non_png_screenshot_files(client):
    """Files like Screenshot*.jpg should not appear in the listing."""
    c, desktop = client
    (desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png").write_bytes(b"")
    (desktop / "Screenshot 2024-01-01 at 12.00.00 PM.jpg").write_bytes(b"")

    names = json.loads(c.get("/api/screenshots").data)
    assert len(names) == 1
    assert names[0].endswith(".png")


def test_open_browser_skips_when_werkzeug_reloader(monkeypatch):
    """_open_browser should not open a tab when WERKZEUG_RUN_MAIN=true."""
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")

    import app as flask_app

    with patch("app.webbrowser") as mock_wb:
        flask_app._open_browser()
    mock_wb.open_new_tab.assert_not_called()


def test_open_browser_opens_tab(monkeypatch):
    """_open_browser should open a browser tab when not in reloader subprocess."""
    monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)

    import app as flask_app

    with patch("app.time.sleep"), patch("app.webbrowser") as mock_wb:
        flask_app._open_browser()
    mock_wb.open_new_tab.assert_called_once_with("http://localhost:5001")


def test_get_screenshots_returns_list(client):
    """get_screenshots() should return a plain list of strings."""
    import app as flask_app

    _, desktop = client
    (desktop / "Screenshot 2024-02-01 at 09.00.00 AM.png").write_bytes(b"")
    result = flask_app.get_screenshots()
    assert isinstance(result, list)
    assert all(isinstance(s, str) for s in result)
