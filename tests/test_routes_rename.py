import json

from helpers import _make_png


def test_api_rename_success(client):
    c, desktop = client
    old = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    old.write_bytes(_make_png(10, 10))

    r = c.post(
        "/api/rename",
        data=json.dumps({"old_name": old.name, "new_name": "Screenshot renamed.png"}),
        content_type="application/json",
    )
    assert r.status_code == 200
    body = json.loads(r.data)
    assert body["ok"] is True
    assert body["new_name"] == "Screenshot renamed.png"
    assert not old.exists()
    assert (desktop / "Screenshot renamed.png").exists()


def test_api_rename_updates_state(client):
    c, desktop = client
    old = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    old.write_bytes(b"")
    c.put(
        "/api/state",
        data=json.dumps({"decisions": {old.name: "keep"}}),
        content_type="application/json",
    )

    c.post(
        "/api/rename",
        data=json.dumps({"old_name": old.name, "new_name": "Screenshot new.png"}),
        content_type="application/json",
    )

    r = c.get("/api/state")
    state = json.loads(r.data)
    assert old.name not in state["decisions"]
    assert state["decisions"]["Screenshot new.png"] == "keep"


def test_api_rename_moves_thumbnail(client):
    c, desktop = client
    old = desktop / "Screenshot 2024-01-01 at 12.00.00 PM.png"
    old.write_bytes(_make_png(50, 50))
    c.get(f"/api/thumb/{old.name}")

    thumb_dir = desktop / "thumbs"
    assert (thumb_dir / old.name).exists()

    c.post(
        "/api/rename",
        data=json.dumps({"old_name": old.name, "new_name": "Screenshot renamed.png"}),
        content_type="application/json",
    )

    assert not (thumb_dir / old.name).exists()
    assert (thumb_dir / "Screenshot renamed.png").exists()


def test_api_rename_rejects_missing_fields(client):
    c, _ = client
    r = c.post(
        "/api/rename",
        data=json.dumps({"old_name": "foo.png"}),
        content_type="application/json",
    )
    assert r.status_code == 400

    r = c.post(
        "/api/rename",
        data=json.dumps({"new_name": "bar.png"}),
        content_type="application/json",
    )
    assert r.status_code == 400


def test_api_rename_rejects_path_traversal(client):
    c, desktop = client
    old = desktop / "Screenshot 2024-01-01.png"
    old.write_bytes(b"")

    r = c.post(
        "/api/rename",
        data=json.dumps({"old_name": old.name, "new_name": "../evil.png"}),
        content_type="application/json",
    )
    assert r.status_code == 400

    r = c.post(
        "/api/rename",
        data=json.dumps({"old_name": "../etc/passwd", "new_name": "innocent.png"}),
        content_type="application/json",
    )
    assert r.status_code == 400


def test_api_rename_file_not_found(client):
    c, _ = client
    r = c.post(
        "/api/rename",
        data=json.dumps({"old_name": "ghost.png", "new_name": "phantom.png"}),
        content_type="application/json",
    )
    assert r.status_code == 404


def test_api_rename_conflict(client):
    c, desktop = client
    old = desktop / "Screenshot 2024-01-01.png"
    existing = desktop / "Screenshot 2024-01-02.png"
    old.write_bytes(b"")
    existing.write_bytes(b"")

    r = c.post(
        "/api/rename",
        data=json.dumps({"old_name": old.name, "new_name": existing.name}),
        content_type="application/json",
    )
    assert r.status_code == 409


def test_api_rename_rejects_non_json(client):
    c, _ = client
    r = c.post("/api/rename", data="not json", content_type="text/plain")
    assert r.status_code == 400


def test_api_rename_same_name_is_noop(client):
    c, desktop = client
    old = desktop / "Screenshot 2024-01-01.png"
    old.write_bytes(b"")

    r = c.post(
        "/api/rename",
        data=json.dumps({"old_name": old.name, "new_name": old.name}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert old.exists()
