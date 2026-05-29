import json


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
