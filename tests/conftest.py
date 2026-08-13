from collections.abc import Iterator
from pathlib import Path

import pytest
from flask.testing import FlaskClient

import ss_dcl.app as flask_app
import ss_dcl.settings as settings_module


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[FlaskClient, Path]]:
    thumb_dir = tmp_path / "thumbs"
    thumb_dir.mkdir()
    monkeypatch.setattr(flask_app, "DESKTOP", tmp_path)
    monkeypatch.setattr(flask_app, "THUMB_DIR", thumb_dir)
    monkeypatch.setattr(flask_app, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(flask_app, "MEMORY_FILE", tmp_path / "memory.json")
    monkeypatch.setattr(settings_module, "SETTINGS_FILE", tmp_path / "settings.json")
    flask_app._reset_memory()
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        yield c, tmp_path
