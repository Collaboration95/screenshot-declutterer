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


def test_index_settings_provider_options(client):
    """Provider dropdown offers litert only; the dead MLX/Ollama stubs are gone."""
    c, _ = client
    html = c.get("/").data.decode()
    assert 'value="ollama"' not in html
    assert 'value="litert"' in html
    assert "LiteRT-LM" in html
    assert "coming soon" not in html.lower()


def test_index_settings_model_placeholder_is_litert_default(client):
    """Static placeholder matches the default litert model id (dash form)."""
    c, _ = client
    html = c.get("/").data.decode()
    assert 'placeholder="gemma4-e2b"' in html


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


def test_app_js_uses_generalized_health_endpoint(client):
    """Suggest pre-flight must hit /api/llm/health; no legacy alias remains."""
    c, _ = client
    r = c.get("/static/app.js")
    assert r.status_code == 200
    assert b'fetch("/api/llm/health")' in r.data
    assert b"/api/ollama/health" not in r.data


def test_app_js_assigns_raw_alt_text(client):
    """Alt text must be the raw filename — no HTML escaping (issue #84)."""
    c, _ = client
    r = c.get("/static/app.js")
    assert r.status_code == 200
    assert b"img.alt = filename;" in r.data
    assert b"lightboxImg.alt = card.dataset.filename;" in r.data
    assert b"lightboxImg.alt = nextName;" in r.data


def test_app_js_no_longer_uses_sanitise(client):
    """The HTML-escape helper must be gone — all insertion is property/textContent."""
    c, _ = client
    r = c.get("/static/app.js")
    assert r.status_code == 200
    assert b"sanitise" not in r.data
    assert b"alt = sanitise" not in r.data


def test_index_has_llm_server_button(client):
    """Header hosts the managed LiteRT start/stop button (hidden until litert)."""
    c, _ = client
    html = c.get("/").data.decode()
    assert 'id="llm-server-btn"' in html
    assert 'aria-label="Manage the LiteRT server"' in html


def test_app_js_binds_llm_server_button(client):
    """JS must declare llmServerBtn, else init() dies before loadScreenshots."""
    c, _ = client
    r = c.get("/static/app.js")
    assert r.status_code == 200
    assert b"const llmServerBtn" in r.data
    assert b'getElementById("llm-server-btn")' in r.data


def test_app_js_defines_server_control(client):
    """JS wires the start/stop button to /api/llm/start and /api/llm/stop."""
    c, _ = client
    r = c.get("/static/app.js")
    assert r.status_code == 200
    assert b"refreshLLMServerButton" in r.data
    assert b'"/api/llm/start"' in r.data
    assert b'"/api/llm/stop"' in r.data


def test_app_js_refreshes_server_button_on_init_and_save(client):
    """Server button state must be recomputed on boot and after saving settings."""
    c, _ = client
    r = c.get("/static/app.js")
    assert r.status_code == 200
    assert b"refreshLLMServerButton();" in r.data
    assert b"loadSettings().then(() => {\n    refreshLLMServerButton();" in r.data
    assert b"closeSettingsModal();\n        refreshLLMServerButton();" in r.data


def test_css_has_llm_server_button_style(client):
    c, _ = client
    r = c.get("/static/style.css")
    assert r.status_code == 200
    assert b".header-llm-btn" in r.data


def test_app_js_has_per_provider_error_copy(client):
    """Provider-aware offline copy for the suggest error paths."""
    c, _ = client
    r = c.get("/static/app.js")
    assert r.status_code == 200
    assert b"providerErrorCopy" in r.data
    assert b"LLM_PROVIDER_MODELS" in r.data


def test_app_js_syncs_model_id_on_provider_change(client):
    """Switching providers in the settings modal fixes the default model id."""
    c, _ = client
    r = c.get("/static/app.js")
    assert r.status_code == 200
    assert b'settingsProvider.addEventListener("change"' in r.data
    assert b"LLM_PROVIDER_MODELS[settingsProvider.value]" in r.data


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


def test_index_has_suggest_cancel_button(client):
    """Progress bar must have a cancel button."""
    c, _ = client
    html = c.get("/").data.decode()
    assert 'id="suggest-cancel-btn"' in html


def test_app_js_has_cancel_logic(client):
    """JS must define _suggestCancelled flag for cancel support."""
    c, _ = client
    r = c.get("/static/app.js")
    assert r.status_code == 200
    assert b"_suggestCancelled" in r.data


def test_rename_handlers_remove_suggestion_badge(client):
    """Both rename paths (modal + lightbox) must remove .suggestion-badge after rename."""
    c, _ = client
    r = c.get("/static/app.js")
    assert r.status_code == 200
    # Lightbox rename
    assert b"if (badge) badge.remove()" in r.data
    # Modal rename sets suggestedName to empty
    assert b'suggestedName = ""' in r.data


# ── Phase 4B: Dark mode ─────────────────────────────────────────────────────


def test_index_has_theme_toggle(client):
    """#theme-toggle button exists in HTML."""
    c, _ = client
    html = c.get("/").data.decode()
    assert 'id="theme-toggle"' in html


def test_app_js_has_theme_cycle(client):
    """JS must define cycleTheme or THEME_KEY for theme management."""
    c, _ = client
    r = c.get("/static/app.js")
    assert r.status_code == 200
    assert b"THEME_KEY" in r.data
    assert b"function cycleTheme(" in r.data


def test_css_has_dark_variables(client):
    """CSS must have [data-theme="dark"] block with --bg-body."""
    c, _ = client
    r = c.get("/static/style.css")
    assert r.status_code == 200
    assert b'[data-theme="dark"]' in r.data
    assert b"--bg-body" in r.data


def test_css_has_light_variables(client):
    """CSS must have :root block with CSS custom properties."""
    c, _ = client
    r = c.get("/static/style.css")
    assert r.status_code == 200
    assert b":root {" in r.data
    assert b"--bg-body" in r.data


# ── Phase 4C/4D: Frontend hints + failure count ──────────────────────────────


def test_css_has_category_hint_styles(client):
    """CSS must define .category-hint-keep/-trash rules."""
    c, _ = client
    r = c.get("/static/style.css")
    assert r.status_code == 200
    assert b"category-hint-keep" in r.data
    assert b"category-hint-trash" in r.data


def test_app_js_shows_failure_count(client):
    """JS must reference failures.length for showing failure count."""
    c, _ = client
    r = c.get("/static/app.js")
    assert r.status_code == 200
    assert b"failedCount" in r.data
    assert b"failures" in r.data


# ── Sprint: multi-select, reveal in Finder, drop hints ─────────────────────


def test_index_has_batch_bar(client):
    """Multi-select batch bar exists in HTML."""
    c, _ = client
    html = c.get("/").data.decode()
    assert 'id="batch-bar"' in html
    assert 'id="batch-count"' in html
    assert 'id="batch-keep-btn"' in html
    assert 'id="batch-trash-btn"' in html
    assert 'id="batch-clear-btn"' in html


def test_app_js_defines_batch_selection(client):
    """JS must define selection state and batch-move helpers."""
    c, _ = client
    r = c.get("/static/app.js")
    assert r.status_code == 200
    assert b"selectedCards" in r.data
    assert b"function toggleSelect(" in r.data
    assert b"function clearSelection(" in r.data
    assert b"function batchMove(" in r.data
    assert b"function updateBatchBar(" in r.data


def test_batch_move_preserves_selection():
    """batchMove must NOT clear the selection — dropping a multi-drag (or
    clicking batch Keep/Trash) keeps the set selected; deselection is only
    explicit (Escape / ✕ Clear / re-sort / Done), per issue #76."""
    import re

    with open("static/app.js", encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"function batchMove\(toColumn\) \{.*?\n\}", src, re.S)
    assert m is not None, "batchMove not found in app.js"
    body = m.group(0)
    assert "clearSelection" not in body
    # still moves every selected card, filtering out stale nodes
    assert "cards.forEach(card => moveCard(card, toColumn))" in body
    assert "document.contains(card)" in body


def test_app_js_defines_batch_drag_ghost(client):
    """Photos-style composite drag ghost must exist and attach via setDragImage."""
    c, _ = client
    r = c.get("/static/app.js")
    assert r.status_code == 200
    assert b"MAX_GHOST_TILES" in r.data
    assert b"function batchFanLayout(" in r.data
    assert b"function buildBatchDragGhost(" in r.data
    assert b"setDragImage" in r.data
    # ghost must only kick in when dragging a *selected* card
    assert b"selectedCards.has(card)" in r.data
    assert b"selectedCards.size > 1" in r.data


def test_batch_fan_layout_is_symmetric_and_centered():
    """batchFanLayout exposes pure geometry: middle tile center, symmetric."""
    import re

    with open("static/app.js", encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"function batchFanLayout\(tileCount\) \{.*?\n\}", src, re.S)
    assert m is not None
    body = m.group(0)
    # stagger scales with tile size (so the fan stays legible when resized),
    # rotation symmetric around mid
    assert "tileCount - 1" in body and "GHOST_TILE_H * 0.042" in body
    assert "(i - mid) * 7" in body


def test_app_js_defines_reveal_in_finder(client):
    """JS must define revealInFinder hitting /api/reveal."""
    c, _ = client
    r = c.get("/static/app.js")
    assert r.status_code == 200
    assert b"function revealInFinder(" in r.data
    assert b"/api/reveal" in r.data


def test_index_has_lightbox_reveal_button(client):
    """Lightbox bar must include a reveal-in-Finder button."""
    c, _ = client
    html = c.get("/").data.decode()
    assert 'id="lightbox-reveal-btn"' in html


def test_css_has_batch_bar_and_selection_styles(client):
    """CSS must style the batch bar and .card.selected."""
    c, _ = client
    r = c.get("/static/style.css")
    assert r.status_code == 200
    assert b"batch-bar" in r.data
    assert b"card.selected" in r.data


def test_css_has_empty_column_hints(client):
    """CSS must render dashed drop hints in empty side columns."""
    c, _ = client
    r = c.get("/static/style.css")
    assert r.status_code == 200
    assert b"column-cards:empty" in r.data
    assert b"Drop here to keep" in r.data
    assert b"Drop here to trash" in r.data
