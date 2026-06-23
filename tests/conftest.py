import pytest
import src.ss_dcl.app as flask_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    thumb_dir = tmp_path / "thumbs"
    thumb_dir.mkdir()
    monkeypatch.setattr(flask_app, "DESKTOP", tmp_path)
    monkeypatch.setattr(flask_app, "THUMB_DIR", thumb_dir)
    monkeypatch.setattr(flask_app, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(flask_app, "MEMORY_FILE", tmp_path / "memory.json")
    flask_app._reset_memory()
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        yield c, tmp_path
