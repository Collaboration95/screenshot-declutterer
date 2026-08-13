"""Module-boundary tests for the app.py monolith split (issue #98).

Verifies that helper subsystems moved out of ``src/ss_dcl/app.py`` live in
their canonical modules and that the route module no longer defines them.
"""

import importlib

import ss_dcl.app as app
import ss_dcl.categorize as categorize
import ss_dcl.llm as llm
import ss_dcl.server as server
import ss_dcl.settings as settings
import ss_dcl.thumbs as thumbs


def test_app_module_no_longer_defines_moved_helpers():
    """The route module must not re-implement moved subsystems."""
    moved = [
        "_call_litert_suggest",
        "_is_retryable_llm_error",
        "_sanitize_suggestion",
        "_image_to_png_data_uri",
        "_litert_healthy",
        "_spawn_litert_server",
        "_litert_serve_cmd",
        "_pid_alive",
        "_generate_thumbnail",
        "_load_settings",
        "_save_settings",
        "_prune_max_age",
        "suggest_category",
        "extract_keywords",
    ]
    for name in moved:
        assert not hasattr(app, name), f"{name} should not be defined in app.py"


def test_llm_module_exposes_client_helpers():
    for name in (
        "_call_litert_suggest",
        "_is_retryable_llm_error",
        "_sanitize_suggestion",
        "_image_to_png_data_uri",
        "_litert_healthy",
        "reset_health_cache",
    ):
        assert callable(getattr(llm, name, None)), f"llm.{name} missing"


def test_server_module_exposes_process_lifecycle():
    for name in (
        "_litert_serve_cmd",
        "_read_litert_pid",
        "_pid_alive",
        "start_server",
        "stop_server",
    ):
        assert callable(getattr(server, name, None)), f"server.{name} missing"


def test_thumbs_module_exposes_generator_and_size():
    assert callable(thumbs._generate_thumbnail)
    assert thumbs.THUMB_SIZE == (400, 300)
    # Issue #80: no executor — generation is synchronous in the request thread.
    assert not hasattr(thumbs, "_THUMB_EXECUTOR")


def test_settings_module_exposes_persistence():
    for name in ("_load_settings", "_save_settings", "_prune_max_age", "reset_prune_cache"):
        assert callable(getattr(settings, name, None)), f"settings.{name} missing"


def test_categorize_module_exposes_helpers():
    assert callable(categorize.extract_keywords)
    assert callable(categorize.suggest_category)


def test_app_module_keeps_route_facing_helpers():
    for name in ("get_screenshots", "_get_memory", "_read_decisions", "_validate_desktop_path"):
        assert callable(getattr(app, name, None)), f"app.{name} missing"


def test_modules_import_independently():
    """Each split module must import standalone (no circular deps)."""
    for mod in (
        "ss_dcl.llm",
        "ss_dcl.server",
        "ss_dcl.thumbs",
        "ss_dcl.settings",
        "ss_dcl.categorize",
    ):
        importlib.import_module(mod)


def test_resource_root_resolves_assets():
    """_HERE must point at a dir containing templates/ and static/ (issue #97).

    Holds both when running from the repo and when installed as a wheel
    (where hatchling force-includes the assets at the site-packages root).
    """
    root = app._HERE
    assert (root / "templates" / "index.html").is_file()
    assert (root / "static" / "app.js").is_file()
