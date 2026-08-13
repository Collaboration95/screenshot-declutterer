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


def test_index_sets_security_headers(client):
    c, _ = client
    r = c.get("/")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert r.headers.get("Referrer-Policy") == "no-referrer"
    assert r.headers.get("Permissions-Policy") == "camera=(), microphone=(), geolocation=()"
    assert "default-src 'self'" in r.headers.get("Content-Security-Policy", "")
