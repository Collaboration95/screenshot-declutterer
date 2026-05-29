import json


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
