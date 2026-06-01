from unittest.mock import patch

from helpers import _make_png


def _screenshot(tmp_path, name="Screenshot 2024-01-01 at 12.00.00 PM.png"):
    (tmp_path / name).write_bytes(_make_png())
    return name


def test_index_html_references_app_js(client):
    c, _ = client
    r = c.get("/")
    assert b"app.js" in r.data


def test_index_html_references_style_css(client):
    c, _ = client
    r = c.get("/")
    assert b"style.css" in r.data


def test_index_has_three_columns(client):
    c, _ = client
    html = c.get("/").data.decode()
    assert 'id="col-keep"' in html
    assert 'id="col-unsorted"' in html
    assert 'id="col-trash"' in html


def test_index_has_lightbox(client):
    c, _ = client
    html = c.get("/").data.decode()
    assert 'id="lightbox"' in html


def test_index_has_confirm_modal(client):
    c, _ = client
    html = c.get("/").data.decode()
    assert 'id="confirm-modal"' in html


def test_index_has_rename_modal(client):
    c, _ = client
    html = c.get("/").data.decode()
    assert 'id="rename-modal"' in html


def test_card_creation_with_screenshot(client):
    c, desktop = client
    _screenshot(desktop)
    r = c.get("/api/screenshots")
    files = r.get_json()
    assert len(files) == 1
    assert files[0]["name"].startswith("Screenshot")


def test_card_thumbnail_and_image_endpoints(client):
    c, desktop = client
    name = _screenshot(desktop)
    r = c.get(f"/api/thumb/{name}")
    assert r.status_code == 200
    r = c.get(f"/api/image/{name}")
    assert r.status_code == 200


def test_full_sort_and_trash_flow(client):
    c, desktop = client
    name = _screenshot(desktop)
    state = {"decisions": {name: "trash"}}
    c.put("/api/state", json=state)
    r = c.get("/api/state")
    assert r.get_json()["decisions"][name] == "trash"
    with patch("src.ss_dcl.app.send2trash"):
        r = c.post("/api/done", json={"filenames": [name]})
    assert r.status_code == 200


def test_static_js_served(client):
    c, _ = client
    r = c.get("/static/app.js")
    assert r.status_code == 200
    assert b"function init()" in r.data


def test_static_css_served(client):
    c, _ = client
    r = c.get("/static/style.css")
    assert r.status_code == 200
    assert b"kanban" in r.data
