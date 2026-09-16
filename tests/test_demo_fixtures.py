"""Tests for the Phase 0 demo-fixture generator (``tools/demo_fixtures.py``).

The generator exists so UI documentation (and, later, visual baselines) can be
captured repeatably without reading a real Desktop or a real runtime state
directory. These tests assert both halves of that promise:

* the generated workspace reproduces every required UI state through the real
  HTTP API, and
* the real ``~/Desktop`` / ``~/.ss-dcl`` are neither read nor written.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:  # tools/ is not an installed package
    sys.path.insert(0, str(_REPO_ROOT))

from tools import demo_fixtures  # noqa: E402

import ss_dcl.app as flask_app  # noqa: E402
import ss_dcl.llm as llm_module  # noqa: E402
import ss_dcl.paths as paths  # noqa: E402
import ss_dcl.settings as settings_module  # noqa: E402
from ss_dcl.sources import decision_key  # noqa: E402


def _configure_app(
    manifest: dict[str, Any], thumb_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Point the app at a generated workspace with no real path in play."""
    state_dir = Path(manifest["state_dir"])
    thumb_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(flask_app, "DESKTOP", Path(manifest["desktop"]))
    monkeypatch.setattr(flask_app, "THUMB_DIR", thumb_dir)
    monkeypatch.setattr(flask_app, "STATE_FILE", state_dir / "state.json")
    monkeypatch.setattr(flask_app, "MEMORY_FILE", state_dir / "memory.json")
    monkeypatch.setattr(settings_module, "SETTINGS_FILE", state_dir / "settings.json")
    monkeypatch.setattr(flask_app, "_dirs_initialized", False)
    # The fixture asks for the LLM-offline state; hard-wire the unreachable URL
    # so a stray auto-suggest can never reach a real server from a test.
    monkeypatch.setattr(llm_module, "LITERT_BASE_URL", demo_fixtures.OFFLINE_LLM_URL)
    flask_app._reset_memory()
    flask_app.app.config["TESTING"] = True


@pytest.fixture(scope="module")
def workspace(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Generate the demo workspace once per module (image rendering is slow)."""
    root = tmp_path_factory.mktemp("demo-fixtures") / "ws"
    return demo_fixtures.write_workspace(root, force=True)


@pytest.fixture()
def demo_client(
    workspace: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[Any, dict[str, Any]]]:
    _configure_app(workspace, tmp_path / "thumbs", monkeypatch)
    with flask_app.app.test_client() as client:
        yield client, workspace


def _fingerprints(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {record["fingerprint"]: record for record in manifest["files"]}


def _snapshot(directory: Path) -> dict[str, tuple[int, int]]:
    """Name -> (size, mtime_ns) for a real user directory, or {} when missing."""
    if not directory.is_dir():
        return {}
    return {
        child.name: (child.stat().st_size, child.stat().st_mtime_ns)
        for child in sorted(directory.iterdir())
    }


def _hash_tree(root: Path) -> dict[str, str]:
    """Relative path -> sha256 for every generated file under *root*."""
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _image_hashes(root: Path) -> dict[str, str]:
    """Relative path -> sha256 for the generated images only."""
    return {
        path: digest
        for path, digest in _hash_tree(root).items()
        if Path(path).suffix.lower() in (".png", ".jpg", ".jpeg", ".tiff", ".bmp")
    }


def _relative_manifest(value: Any, root: str) -> Any:
    """Rewrite the workspace root to ``<root>`` so two manifests compare equal."""
    if isinstance(value, str):
        return value.replace(root, "<root>")
    if isinstance(value, dict):
        return {key: _relative_manifest(item, root) for key, item in value.items()}
    if isinstance(value, list):
        return [_relative_manifest(item, root) for item in value]
    return value


# ── Generator behaviour ──────────────────────────────────────────────────────


def test_workspace_covers_every_required_state(workspace: dict[str, Any]) -> None:
    coverage = workspace["coverage"]
    assert set(coverage) == set(demo_fixtures.REQUIRED_STATES)
    assert all(coverage[state] >= 1 for state in demo_fixtures.REQUIRED_STATES)
    assert workspace["counts"] == {"total": 20, "desktop": 17, "tracked": 3}
    assert demo_fixtures.verify_workspace(workspace["root"]) == []


def test_workspace_states_are_independent_of_the_llm(workspace: dict[str, Any]) -> None:
    """Offline LLM is an env property, and auto-suggest stays off."""
    assert workspace["env"]["LITERT_BASE_URL"] == demo_fixtures.OFFLINE_LLM_URL
    settings = json.loads((Path(workspace["state_dir"]) / "settings.json").read_text())
    assert settings["auto_suggest"] is False


def test_regeneration_is_byte_identical(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    first = demo_fixtures.write_workspace(root)
    before = _hash_tree(root)
    assert demo_fixtures.write_workspace(root, force=True) == first
    assert _hash_tree(root) == before


def test_images_are_identical_across_roots(workspace: dict[str, Any], tmp_path: Path) -> None:
    """Only the absolute paths differ; pixels and layout do not."""
    regenerated = demo_fixtures.write_workspace(
        tmp_path / "again", force=True, seed=workspace["seed"]
    )
    assert _relative_manifest(regenerated, regenerated["root"]) == _relative_manifest(
        workspace, workspace["root"]
    )
    assert _image_hashes(Path(regenerated["root"])) == _image_hashes(Path(workspace["root"]))


def test_existing_root_needs_force(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    demo_fixtures.write_workspace(root)
    with pytest.raises(FileExistsError):
        demo_fixtures.write_workspace(root)


def test_verify_reports_a_broken_workspace(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    demo_fixtures.write_workspace(root)
    assert demo_fixtures.verify_workspace(root) == []

    (root / demo_fixtures.DESKTOP_DIR / demo_fixtures.CATALOGUE[0].name).unlink()
    problems = demo_fixtures.verify_workspace(root)
    assert any("missing image" in problem for problem in problems)
    assert demo_fixtures.verify_workspace(tmp_path / "nothing") != []


def test_cli_json_and_verify(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "cli-ws"
    assert demo_fixtures.main(["--root", str(root), "--force", "--json"]) == 0
    manifest = json.loads(capsys.readouterr().out)
    assert manifest["fixture_version"] == demo_fixtures.FIXTURE_VERSION
    assert demo_fixtures.main(["--root", str(root), "--verify"]) == 0
    assert "OK" in capsys.readouterr().out
    # A second run without --force is a loud failure, not a silent overwrite.
    assert demo_fixtures.main(["--root", str(root)]) == 2
    assert "--force" in capsys.readouterr().err


def test_runtime_paths_follow_ss_dcl_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    isolated = tmp_path / "runtime"
    monkeypatch.setenv(paths.ENV_RUNTIME_HOME, str(isolated))
    assert paths.runtime_home() == isolated
    assert paths.state_dir() == isolated / paths.STATE_DIR_NAME
    assert paths.cache_dir() == isolated / ".cache" / paths.CACHE_DIR_NAME

    monkeypatch.delenv(paths.ENV_RUNTIME_HOME)
    assert paths.runtime_home() == Path.home()
    # A blank value is treated as unset rather than as the empty path.
    monkeypatch.setenv(paths.ENV_RUNTIME_HOME, "   ")
    assert paths.runtime_home() == Path.home()


def test_manifest_paths_stay_inside_the_workspace(workspace: dict[str, Any]) -> None:
    root = Path(workspace["root"]).resolve()
    for key in ("desktop", "tracked_folder", "runtime_home", "state_dir"):
        assert Path(workspace[key]).resolve().is_relative_to(root)
    assert Path(workspace["env"]["SS_DCL_DESKTOP"]).resolve().is_relative_to(root)
    assert Path(workspace["env"]["SS_DCL_HOME"]).resolve().is_relative_to(root)
    assert root != Path.home() / "Desktop"


# ── Fixture through the real API ─────────────────────────────────────────────


def test_screenshots_returns_every_fixture_file(
    demo_client: tuple[Any, dict[str, Any]],
) -> None:
    client, manifest = demo_client
    response = client.get("/api/screenshots?sort=date_desc")
    assert response.status_code == 200
    files = response.get_json()
    assert len(files) == manifest["counts"]["total"]

    expected = _fingerprints(manifest)
    for entry in files:
        record = expected[entry["fingerprint"]]
        assert entry["name"] == record["name"]
        assert entry["source"] == record["source"]
        assert entry["memory_status"] == record["status"]
        assert entry["suggested_name"] == record["suggested_name"]
        assert entry["suggested_category"] == record["expected_category"]
    # date_desc is the order the frontend boots with.
    assert [entry["mtime"] for entry in files] == sorted(
        (entry["mtime"] for entry in files), reverse=True
    )


def test_tracked_folder_files_come_from_their_own_source(
    demo_client: tuple[Any, dict[str, Any]],
) -> None:
    client, manifest = demo_client
    files = {entry["fingerprint"]: entry for entry in client.get("/api/screenshots").get_json()}
    tracked = [record for record in manifest["files"] if record["inbox"] == "tracked"]
    assert len(tracked) == manifest["counts"]["tracked"] > 0
    for record in tracked:
        source = files[record["fingerprint"]]["source"]
        assert source == str(Path(manifest["tracked_folder"]).resolve())
        assert source != demo_fixtures.DESKTOP_SOURCE
    for record in manifest["files"]:
        if record["inbox"] == "desktop":
            assert files[record["fingerprint"]]["source"] == demo_fixtures.DESKTOP_SOURCE


def test_settings_expose_the_tracked_folder(
    demo_client: tuple[Any, dict[str, Any]],
) -> None:
    client, manifest = demo_client
    settings = client.get("/api/settings").get_json()
    assert settings["tracked_folders"] == [str(Path(manifest["tracked_folder"]).resolve())]
    assert settings["tracked_folder_info"] == [
        {"path": str(Path(manifest["tracked_folder"]).resolve()), "exists": True}
    ]
    assert settings["auto_suggest"] is False


def test_health_reports_the_fixture_inbox(demo_client: tuple[Any, dict[str, Any]]) -> None:
    client, manifest = demo_client
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.get_json()["desktop_scanable"] is True
    assert response.get_json()["memory_records"] == manifest["counts"]["total"]


def test_thumbs_render_for_desktop_and_tracked_sources(
    demo_client: tuple[Any, dict[str, Any]],
) -> None:
    client, manifest = demo_client
    by_inbox = {record["inbox"]: record for record in manifest["files"]}
    for inbox in ("desktop", "tracked"):
        record = by_inbox[inbox]
        response = client.get(f"/api/thumb/{record['name']}?source={record['source']}")
        assert response.status_code == 200
        assert response.mimetype.startswith("image/")
        assert response.data


def test_suggestion_badge_flows_can_be_rejected_offline(
    demo_client: tuple[Any, dict[str, Any]],
) -> None:
    """Dismissing a suggestion works without any LLM reachable."""
    client, manifest = demo_client
    memory_file = Path(manifest["state_dir"]) / "memory.json"
    original = memory_file.read_text()
    record = next(item for item in manifest["files"] if item["status"] == "suggested")
    try:
        response = client.post(
            "/api/reject-suggestion", json={"fingerprint": record["fingerprint"]}
        )
        assert response.status_code == 200
        assert response.get_json() == {"ok": True}
        refreshed = {
            entry["fingerprint"]: entry for entry in client.get("/api/screenshots").get_json()
        }[record["fingerprint"]]
        assert refreshed["memory_status"] == "ignored"
        # Rejecting also withdraws the category hint it had accumulated.
        assert refreshed["suggested_category"] is None
    finally:
        # The workspace is shared by the whole module; leave it as generated.
        memory_file.write_text(original)


def test_state_round_trips_through_the_api(
    demo_client: tuple[Any, dict[str, Any]],
) -> None:
    client, manifest = demo_client
    state_file = Path(manifest["state_dir"]) / "state.json"
    original = state_file.read_text()
    try:
        decisions = dict(client.get("/api/state").get_json()["decisions"])
        assert decisions == {
            decision_key(record["source"], record["name"]): record["decision"]
            for record in manifest["files"]
            if record["decision"]
        }
        assert len(decisions) == manifest["coverage"]["kept"] + manifest["coverage"]["trashed"]

        undecided = next(record for record in manifest["files"] if record["column"] == "unsorted")
        decisions[decision_key(undecided["source"], undecided["name"])] = "keep"
        assert client.put("/api/state", json={"decisions": decisions}).status_code == 200
        assert client.get("/api/state").get_json()["decisions"] == decisions
        assert json.loads(state_file.read_text())["decisions"] == decisions
        refreshed = {
            entry["fingerprint"]: entry for entry in client.get("/api/screenshots").get_json()
        }
        assert refreshed[undecided["fingerprint"]]["fingerprint"] == undecided["fingerprint"]
    finally:
        state_file.write_text(original)


# ── Isolation guarantee ──────────────────────────────────────────────────────


def test_real_desktop_and_runtime_state_are_never_touched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_desktop = Path.home() / "Desktop"
    real_state_dir = Path.home() / ".ss-dcl"
    before = (_snapshot(real_desktop), _snapshot(real_state_dir))

    manifest = demo_fixtures.write_workspace(tmp_path / "isolated", force=True)
    _configure_app(manifest, tmp_path / "thumbs", monkeypatch)
    assert not flask_app.THUMB_DIR.resolve().is_relative_to(Path.home() / ".cache")
    with flask_app.app.test_client() as client:
        screenshots = client.get("/api/screenshots").get_json()
        record = screenshots[0]
        client.get(f"/api/thumb/{record['name']}?source={record['source']}")
        client.get("/api/state")
        client.get("/api/settings")

    assert (_snapshot(real_desktop), _snapshot(real_state_dir)) == before
    assert all("Screenshot" in record["name"] for record in screenshots)
