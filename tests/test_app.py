"""Tests for app.py routes and screenshot scanning."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

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
