from helpers import _make_png


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
