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
