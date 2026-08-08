from unittest.mock import patch

from helpers import _make_png


def _screenshot(tmp_path, name="Screenshot 2024-01-01 at 12.00.00 PM.png"):
    (tmp_path / name).write_bytes(_make_png())
    return name


def test_reveal_valid_filename(client):
    c, desktop = client
    name = _screenshot(desktop)
    with patch("src.ss_dcl.app.subprocess.Popen") as mock_popen:
        r = c.post("/api/reveal", json={"filename": name})
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    mock_popen.assert_called_once()
    args = mock_popen.call_args[0][0]
    assert args[0] == "open"
    assert args[1] == "-R"
    assert args[2] == str(desktop / name)


def test_reveal_missing_file_returns_404(client):
    c, _ = client
    r = c.post("/api/reveal", json={"filename": "Does Not Exist.png"})
    assert r.status_code == 404


def test_reveal_path_traversal_rejected(client):
    c, desktop = client
    _screenshot(desktop)
    # Bare-name check + resolved-path-within-Desktop guard
    assert c.post("/api/reveal", json={"filename": "../state.json"}).status_code == 400
    assert c.post("/api/reveal", json={"filename": "sub/dir.png"}).status_code == 400


def test_reveal_rejects_bad_payloads(client):
    c, desktop = client
    _screenshot(desktop)
    assert c.post("/api/reveal", json={"filename": 123}).status_code == 400
    assert c.post("/api/reveal", json={}).status_code == 400


def test_reveal_off_macos_returns_clear_error(client, monkeypatch):
    c, desktop = client
    name = _screenshot(desktop)
    monkeypatch.setattr("src.ss_dcl.app.IS_MACOS", False)
    with patch("src.ss_dcl.app.subprocess.Popen") as mock_popen:
        r = c.post("/api/reveal", json={"filename": name})
    assert r.status_code == 400
    body = r.get_json()
    assert body["ok"] is False
    assert "macOS" in body["error"]
    mock_popen.assert_not_called()
