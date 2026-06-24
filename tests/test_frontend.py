from unittest.mock import patch

from helpers import _make_png


def _screenshot(tmp_path, name="Screenshot 2024-01-01 at 12.00.00 PM.png"):
    (tmp_path / name).write_bytes(_make_png())
    return name


def test_index_html_references_app_js(client):
    c, _ = client
    r = c.get("/")
    assert b"app.js" in r.data


def test_index_html_references_style_css(client):
    c, _ = client
    r = c.get("/")
    assert b"style.css" in r.data


def test_index_has_three_columns(client):
    c, _ = client
    html = c.get("/").data.decode()
    assert 'id="col-keep"' in html
    assert 'id="col-unsorted"' in html
    assert 'id="col-trash"' in html


def test_index_has_lightbox(client):
    c, _ = client
    html = c.get("/").data.decode()
    assert 'id="lightbox"' in html


def test_index_has_lightbox_rename_bar(client):
    c, _ = client
    html = c.get("/").data.decode()
    assert 'id="lightbox-filename"' in html
    assert 'id="lightbox-rename-input"' in html
    assert 'id="lightbox-rename-error"' in html
    assert "lightbox-bar" in html


def test_index_has_card_tooltip(client):
    c, _ = client
    html = c.get("/").data.decode()
    assert 'id="card-tooltip"' in html
    assert "card-tooltip" in html


def test_index_has_confirm_modal(client):
    c, _ = client
    html = c.get("/").data.decode()
    assert 'id="confirm-modal"' in html


def test_index_has_rename_modal(client):
    c, _ = client
    html = c.get("/").data.decode()
    assert 'id="rename-modal"' in html


def test_card_creation_with_screenshot(client):
    c, desktop = client
    _screenshot(desktop)
    r = c.get("/api/screenshots")
    files = r.get_json()
    assert len(files) == 1
    assert files[0]["name"].startswith("Screenshot")


def test_card_thumbnail_and_image_endpoints(client):
    c, desktop = client
    name = _screenshot(desktop)
    r = c.get(f"/api/thumb/{name}")
    assert r.status_code == 200
    r = c.get(f"/api/image/{name}")
    assert r.status_code == 200


def test_full_sort_and_trash_flow(client):
    c, desktop = client
    name = _screenshot(desktop)
    state = {"decisions": {name: "trash"}}
    c.put("/api/state", json=state)
    r = c.get("/api/state")
    assert r.get_json()["decisions"][name] == "trash"
    with patch("src.ss_dcl.app.send2trash"):
        r = c.post("/api/done", json={"filenames": [name]})
    assert r.status_code == 200


def test_static_js_served(client):
    c, _ = client
    r = c.get("/static/app.js")
    assert r.status_code == 200
    assert b"function init()" in r.data


def test_static_css_served(client):
    c, _ = client
    r = c.get("/static/style.css")
    assert r.status_code == 200
    assert b"kanban" in r.data


def test_app_js_sets_fingerprint_dataset(client):
    """Cards must carry data-fingerprint from /api/screenshots response."""
    c, _ = client
    r = c.get("/static/app.js")
    assert r.status_code == 200
    assert b"dataset.fingerprint" in r.data


def test_app_js_sets_memory_status_dataset(client):
    """Cards must carry data-memory-status from /api/screenshots response."""
    c, _ = client
    r = c.get("/static/app.js")
    assert r.status_code == 200
    assert b"dataset.memoryStatus" in r.data


def test_app_js_updates_memory_status_on_rename(client):
    """Rename handlers must set memoryStatus to 'renamed' after successful rename."""
    c, _ = client
    r = c.get("/static/app.js")
    assert r.status_code == 200
    assert b'memoryStatus = "renamed"' in r.data


# ── Phase 3 UI elements ─────────────────────────────────────────────────


def test_index_has_suggest_all_button(client):
    c, _ = client
    html = c.get("/").data.decode()
    assert 'id="suggest-all-btn"' in html
    assert "Suggest All" in html


def test_index_has_settings_button(client):
    c, _ = client
    html = c.get("/").data.decode()
    assert 'id="settings-btn"' in html


def test_index_has_suggest_progress_bar(client):
    c, _ = client
    html = c.get("/").data.decode()
    assert 'id="suggest-progress"' in html
    assert 'id="suggest-progress-fill"' in html
    assert 'id="suggest-progress-text"' in html


def test_index_has_settings_modal(client):
    c, _ = client
    html = c.get("/").data.decode()
    assert 'id="settings-modal"' in html
    assert 'id="settings-provider"' in html
    assert 'id="settings-model"' in html
    assert 'id="settings-auto"' in html


def test_app_js_defines_suggest_batch(client):
    """JS must define suggestBatch function for batch LLM suggestions."""
    c, _ = client
    r = c.get("/static/app.js")
    assert r.status_code == 200
    assert b"function suggestBatch(" in r.data


def test_app_js_defines_accept_suggestion(client):
    """JS must define acceptSuggestion for accepting LLM suggestions."""
    c, _ = client
    r = c.get("/static/app.js")
    assert r.status_code == 200
    assert b"function acceptSuggestion(" in r.data


def test_app_js_defines_reject_suggestion(client):
    """JS must define rejectSuggestion for dismissing LLM suggestions."""
    c, _ = client
    r = c.get("/static/app.js")
    assert r.status_code == 200
    assert b"function rejectSuggestion(" in r.data


def test_app_js_defines_settings_modal(client):
    """JS must handle settings modal."""
    c, _ = client
    r = c.get("/static/app.js")
    assert r.status_code == 200
    assert b"settingsModal" in r.data


def test_app_js_has_suggestion_badge_maker(client):
    """JS must have _makeSuggestionBadge for rendering suggested name with accept/reject."""
    c, _ = client
    r = c.get("/static/app.js")
    assert r.status_code == 200
    assert b"_makeSuggestionBadge" in r.data


def test_css_has_suggestion_badge_styles(client):
    """CSS must define styles for suggestion badge."""
    c, _ = client
    r = c.get("/static/style.css")
    assert r.status_code == 200
    assert b"suggestion-badge" in r.data


def test_css_has_suggest_progress_styles(client):
    """CSS must define styles for progress bar."""
    c, _ = client
    r = c.get("/static/style.css")
    assert r.status_code == 200
    assert b"suggest-progress" in r.data


def test_css_has_settings_form_styles(client):
    """CSS must define styles for settings form."""
    c, _ = client
    r = c.get("/static/style.css")
    assert r.status_code == 200
    assert b"settings-form" in r.data


def test_rename_handlers_remove_suggestion_badge(client):
    """Both rename paths (modal + lightbox) must remove .suggestion-badge after rename."""
    c, _ = client
    r = c.get("/static/app.js")
    assert r.status_code == 200
    # Lightbox rename
    assert b"if (badge) badge.remove()" in r.data
    # Modal rename sets suggestedName to empty
    assert b'suggestedName = ""' in r.data
