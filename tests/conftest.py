import io

import pytest
import src.ss_dcl.app as flask_app


def _make_png(width=10, height=10, color="red"):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    thumb_dir = tmp_path / "thumbs"
    thumb_dir.mkdir()
    monkeypatch.setattr(flask_app, "DESKTOP", tmp_path)
    monkeypatch.setattr(flask_app, "THUMB_DIR", thumb_dir)
    monkeypatch.setattr(flask_app, "STATE_FILE", tmp_path / "state.json")
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        yield c, tmp_path
