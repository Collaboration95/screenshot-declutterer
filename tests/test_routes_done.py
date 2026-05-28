import json
from unittest.mock import patch

import src.ss_dcl.app as flask_app

from conftest import _make_png


def test_api_done_moves_files_to_trash(client):
    c, desktop = client
    f = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    f.write_bytes(b"")

    with patch("src.ss_dcl.app.send2trash") as mock_trash:
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

    with patch("src.ss_dcl.app.send2trash"):
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

    with patch("src.ss_dcl.app.send2trash") as mock_trash:
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

    with patch("src.ss_dcl.app.send2trash"):
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

    with patch("src.ss_dcl.app.send2trash"):
        c.post(
            "/api/done",
            data=json.dumps({"filenames": [f.name]}),
            content_type="application/json",
        )

    assert not (thumb_dir / f.name).exists()


def test_api_screenshots_ignores_non_png_screenshot_files(client):
    c, desktop = client
    (desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png").write_bytes(b"")
    (desktop / "Screenshot 2024-01-01 at 12.00.00 PM.jpg").write_bytes(b"")

    names = [f["name"] for f in json.loads(c.get("/api/screenshots").data)]
    assert len(names) == 1
    assert names[0].endswith(".png")


def test_open_browser_skips_when_werkzeug_reloader(monkeypatch):
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")

    from src.ss_dcl import app as flask_app

    with patch("src.ss_dcl.app.webbrowser") as mock_wb:
        flask_app._open_browser()
    mock_wb.open_new_tab.assert_not_called()


def test_open_browser_opens_tab(monkeypatch):
    monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)

    from src.ss_dcl import app as flask_app

    with patch("src.ss_dcl.app.time.sleep"), patch("src.ss_dcl.app.webbrowser") as mock_wb:
        flask_app._open_browser()
    mock_wb.open_new_tab.assert_called_once_with("http://localhost:5002")


def test_get_screenshots_returns_list(client):
    _, desktop = client
    (desktop / "Screenshot 2024-02-01 at 09.00.00 AM.png").write_bytes(b"")
    result = flask_app.get_screenshots()
    assert isinstance(result, list)
    assert all(isinstance(f, dict) for f in result)
    assert all("name" in f and "size" in f and "mtime" in f for f in result)
