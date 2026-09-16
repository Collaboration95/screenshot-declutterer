"""Phase 1 design-token foundation and flash-free theme bootstrap.

These tests lock the contract PLAN.md Phase 1 establishes for the frontend:

* the stored theme is resolved and written to <html> before the stylesheet is
  applied, without an inline script (the CSP keeps script-src at 'self');
* every colour in a shared component rule comes from a token, never a literal;
* the two dark palettes (explicit choice + system preference) stay identical so
  "auto" resolves correctly even with JavaScript disabled;
* text and UI token pairs clear their WCAG contrast thresholds in both modes;
* reduced-motion and forced-colors fallbacks exist for the shared controls.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

STYLE_CSS = (REPO_ROOT / "static" / "style.css").read_text(encoding="utf-8")
THEME_JS = (REPO_ROOT / "static" / "theme-init.js").read_text(encoding="utf-8")
APP_JS = (REPO_ROOT / "static" / "app.js").read_text(encoding="utf-8")
INDEX_HTML = (REPO_ROOT / "templates" / "index.html").read_text(encoding="utf-8")

# The shared base layer is the boundary: everything above it declares tokens,
# everything below it must consume them.
_BASE_AT = STYLE_CSS.index("box-sizing: border-box")
_TOKEN_END = STYLE_CSS.rindex("/*", 0, _BASE_AT)
TOKEN_CSS = STYLE_CSS[:_TOKEN_END]
COMPONENT_CSS = STYLE_CSS[_TOKEN_END:]

_DECLARATION = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;]+);")
_DEFINITION = re.compile(r"(--[a-z0-9-]+)\s*:")
_USAGE = re.compile(r"var\(\s*(--[a-z0-9-]+)")
_COLOR_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\s*\(")

REQUIRED_TOKENS = (
    # Scales: type, weight, space, radius, border, motion, control, elevation.
    "--font-sans",
    "--font-mono",
    "--type-body",
    "--type-body-line",
    "--weight-regular",
    "--weight-semibold",
    "--space-1",
    "--space-4",
    "--space-9",
    "--radius-control",
    "--radius-dialog",
    "--radius-pill",
    "--border-width",
    "--border-width-emphasis",
    "--duration-fast",
    "--duration-base",
    "--duration-slow",
    "--ease-standard",
    "--ease-emphasized",
    "--control-height",
    "--control-hit-target",
    "--elevation-1",
    "--elevation-2",
    "--elevation-3",
    # Semantic surfaces and ink.
    "--surface-canvas",
    "--surface-shell",
    "--surface-raised",
    "--surface-muted",
    "--surface-sunken",
    "--surface-control",
    "--ink-primary",
    "--ink-secondary",
    "--ink-muted",
    "--ink-disabled",
    "--ink-on-solid",
    "--border-subtle",
    "--border-strong",
    "--border-control",
    # Roles: actions, states, focus, overlays.
    "--action-primary",
    "--action-keep",
    "--action-trash",
    "--action-warning",
    "--action-neutral",
    "--on-action",
    "--accent-keep-ink",
    "--accent-trash-ink",
    "--accent-ai-strong",
    "--status-error-ink",
    "--status-warning-ink",
    "--focus-ring-color",
    "--control-bg",
    "--control-text",
    "--control-disabled-bg",
    "--selection-ring",
    "--overlay-scrim",
    "--overlay-ink",
    "--tooltip-surface",
)


def _rule_block(selector: str) -> str:
    """Return the declaration text of the first rule matching ``selector``."""
    start = STYLE_CSS.index(selector)
    open_brace = STYLE_CSS.index("{", start)
    depth = 0
    for index in range(open_brace, len(STYLE_CSS)):
        char = STYLE_CSS[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return STYLE_CSS[open_brace + 1 : index]
    raise AssertionError(f"unbalanced braces after {selector!r}")


def _declarations(block: str) -> dict[str, str]:
    return {match.group(1): match.group(2).strip() for match in _DECLARATION.finditer(block)}


def _meaningful_lines(block: str) -> list[str]:
    return [line.strip() for line in block.splitlines() if line.strip()]


def _strip_comments(source: str) -> str:
    """Drop /* */ blocks and full-line // comments so text checks see code."""
    without_blocks = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return "\n".join(
        line for line in without_blocks.splitlines() if not line.lstrip().startswith("//")
    )


APP_JS_CODE = _strip_comments(APP_JS)


LIGHT_PALETTE = _declarations(_rule_block(":root {"))
DARK_EXPLICIT_BLOCK = _rule_block('[data-theme="dark"] {')
DARK_MEDIA_BLOCK = _rule_block(':root:not([data-theme="light"]) {')
DARK_PALETTE = {**LIGHT_PALETTE, **_declarations(DARK_EXPLICIT_BLOCK)}

PALETTES = {"light": LIGHT_PALETTE, "dark": DARK_PALETTE}


def _resolve(token: str, palette: dict[str, str]) -> str:
    """Follow var() aliases until a literal hex colour is reached."""
    seen: set[str] = set()
    name = token
    while True:
        assert name not in seen, f"cyclic token definition at {name}"
        seen.add(name)
        raw = palette.get(name, LIGHT_PALETTE.get(name))
        assert raw is not None, f"undefined token {name}"
        alias = re.fullmatch(r"var\(\s*(--[a-z0-9-]+)\s*\)", raw)
        if alias is None:
            assert raw.startswith("#"), f"{name} should resolve to hex, got {raw!r}"
            return raw
        name = alias.group(1)


def _relative_luminance(color: str) -> float:
    raw = color.lstrip("#")
    channels = [int(raw[index : index + 2], 16) / 255 for index in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(foreground: str, background: str) -> float:
    first = _relative_luminance(foreground)
    second = _relative_luminance(background)
    high, low = max(first, second), min(first, second)
    return (high + 0.05) / (low + 0.05)


_SURFACES = (
    "--surface-canvas",
    "--surface-shell",
    "--surface-raised",
    "--surface-muted",
    "--surface-control",
)

# Body copy and labels: WCAG AA for normal text.
TEXT_PAIRS: list[tuple[str, str]] = (
    [("--ink-primary", surface) for surface in (*_SURFACES, "--surface-sunken")]
    + [("--ink-secondary", surface) for surface in _SURFACES]
    + [
        ("--ink-muted", "--surface-raised"),
        ("--ink-muted", "--surface-shell"),
        ("--ink-muted", "--surface-canvas"),
        ("--ink-muted", "--surface-muted"),
    ]
    + [
        ("--ink-on-solid", solid)
        for solid in (
            "--action-primary",
            "--accent-keep-fill",
            "--accent-trash-fill",
            "--status-warning-fill",
        )
    ]
    + [
        ("--accent-ai-strong", "--surface-raised"),
        ("--accent-ai-strong", "--accent-ai-soft"),
        ("--accent-keep-ink", "--surface-raised"),
        ("--accent-keep-ink", "--accent-keep-soft"),
        ("--accent-trash-ink", "--surface-raised"),
        ("--accent-trash-ink", "--accent-trash-soft"),
        ("--status-warning-ink", "--surface-raised"),
        ("--status-warning-ink", "--status-warning-soft"),
    ]
)

# Non-text UI: WCAG 1.4.11 pushes borders, rings and solid fills to 3:1.
# Decorative tokens (--border-strong, the --*-border accents) are excluded on
# purpose: they are ornamental hairlines, not the only cue for a control.
UI_PAIRS: list[tuple[str, str]] = (
    [("--focus-ring-color", surface) for surface in _SURFACES]
    + [
        ("--border-control", surface)
        for surface in (
            "--surface-raised",
            "--surface-muted",
            "--surface-control",
            "--surface-canvas",
            "--surface-shell",
        )
    ]
    + [
        (fill, "--surface-raised")
        for fill in ("--accent-keep-fill", "--accent-trash-fill", "--status-warning-fill")
    ]
)


# -- theme bootstrap --------------------------------------------------------


def test_theme_bootstrap_runs_in_head_before_the_stylesheet():
    """The stored theme must land on <html> before the first paint."""
    head_end = INDEX_HTML.index("</head>")
    theme_at = INDEX_HTML.index("theme-init.js")
    css_at = INDEX_HTML.index("style.css")
    app_at = INDEX_HTML.index("app.js")
    assert theme_at < head_end, "theme-init.js must sit inside <head>"
    assert theme_at < css_at < app_at, "order must be theme-init, style.css, app.js"


def test_no_inline_script_keeps_the_csp_intact():
    for body in re.findall(r"<script\b[^>]*>(.*?)</script>", INDEX_HTML, re.DOTALL):
        assert body.strip() == "", "the theme bootstrap must not use an inline script"


def test_theme_bootstrap_is_served_with_the_page(client):
    c, _ = client
    page = c.get("/").data.decode()
    assert "/static/theme-init.js" in page
    served = c.get("/static/theme-init.js")
    assert served.status_code == 200
    assert b"ss-dcl-theme" in served.data


def test_app_js_reuses_the_shared_theme_module():
    """One storage key, one resolver - app.js must not fork the logic."""
    assert "SsDclTheme.THEME_STORAGE_KEY" in APP_JS
    assert '"ss-dcl-theme"' not in APP_JS
    assert "localStorage" not in APP_JS_CODE
    assert "SsDclTheme.cycleTheme" in APP_JS


def test_theme_module_never_writes_markup():
    assert "innerHTML" not in THEME_JS
    assert "document.write" not in THEME_JS


# -- tokens -----------------------------------------------------------------


@pytest.mark.parametrize("token", REQUIRED_TOKENS)
def test_required_design_token_is_declared(token: str) -> None:
    assert token in LIGHT_PALETTE, f"{token} is missing from the light palette"


@pytest.mark.parametrize("token", ("--surface-canvas", "--ink-primary", "--focus-ring-color"))
def test_dark_palette_restates_the_core_tokens(token: str) -> None:
    assert token in _declarations(DARK_EXPLICIT_BLOCK)
    assert token in _declarations(DARK_MEDIA_BLOCK)


def test_component_layer_follows_the_token_layer():
    assert "Base" in COMPONENT_CSS[:120]
    assert COMPONENT_CSS.index(".btn") > 0


def test_every_used_token_is_defined():
    defined = set(_DEFINITION.findall(STYLE_CSS))
    used = set(_USAGE.findall(STYLE_CSS))
    assert not used - defined, f"undefined tokens: {sorted(used - defined)}"


def test_declared_color_scheme_matches_each_palette():
    assert "color-scheme: light" in _rule_block(":root {")
    assert "color-scheme: dark" in DARK_EXPLICIT_BLOCK
    assert "color-scheme: dark" in DARK_MEDIA_BLOCK


def test_explicit_light_wins_over_a_dark_system_preference():
    """The media-query copy has to exclude data-theme=light or it leaks."""
    media_at = STYLE_CSS.index("@media (prefers-color-scheme: dark)")
    assert ':root:not([data-theme="light"])' in STYLE_CSS[media_at:]


def test_the_two_dark_palettes_stay_identical():
    """CSS has no mixins, so the duplicated palette must not drift."""
    assert _meaningful_lines(DARK_EXPLICIT_BLOCK) == _meaningful_lines(DARK_MEDIA_BLOCK)


def test_component_rules_have_no_colour_literals():
    """Everything below the token layer must go through var()."""
    literals = sorted(set(_COLOR_LITERAL.findall(COMPONENT_CSS)))
    assert literals == [], f"hardcoded colours outside the token layer: {literals}"


def test_no_external_stylesheets_scripts_or_font_imports():
    """Local-only means no CDN, no @import and no remote font fetch."""
    assert "@import" not in STYLE_CSS
    assert "url(" not in STYLE_CSS
    assert "http://" not in STYLE_CSS and "https://" not in STYLE_CSS
    assert "http://" not in INDEX_HTML and "https://" not in INDEX_HTML
    assert "//cdn" not in INDEX_HTML


def test_font_stack_is_local_system_fonts():
    """PLAN section 7.1 approves system fonts over self-hosted webfonts."""
    assert "-apple-system" in LIGHT_PALETTE["--font-sans"]
    assert "var(--font-sans)" in COMPONENT_CSS


# -- accessibility fallbacks ------------------------------------------------


def test_reduced_motion_disables_transitions_and_animation():
    block = _rule_block("@media (prefers-reduced-motion: reduce)")
    assert "animation-duration: 0.01ms !important" in block
    assert "transition-duration: 0.01ms !important" in block
    assert "scroll-behavior: auto !important" in block


def test_forced_colors_keeps_boundaries_and_focus_visible():
    block = _rule_block("@media (forced-colors: active)")
    assert "CanvasText" in block, "surfaces need a system-colour boundary"
    assert "ButtonText" in block, "buttons need a system-colour boundary"
    assert "Highlight" in block, "selection and focus need a system colour"
    assert "GrayText" in block, "a missing state needs a non-colour cue"
    assert ":focus-visible" in block
    assert ".column.drag-over" in block, "the drop target needs a non-colour cue"


def test_shared_controls_define_a_visible_focus_state():
    focus = _rule_block(":focus-visible {")
    assert "outline" in focus
    assert "var(--focus-ring-color)" in focus
    assert "outline-offset" in focus
    assert ".switch input:focus-visible + .switch-track" in STYLE_CSS


# -- contrast ---------------------------------------------------------------


@pytest.mark.parametrize("palette_name", ["light", "dark"])
def test_text_tokens_meet_wcag_aa(palette_name: str) -> None:
    palette = PALETTES[palette_name]
    failures = []
    for foreground, background in TEXT_PAIRS:
        ratio = _contrast(_resolve(foreground, palette), _resolve(background, palette))
        if ratio < 4.5:
            failures.append(f"{foreground} on {background} = {ratio:.2f}")
    assert not failures, f"{palette_name} text contrast below 4.5: {failures}"


@pytest.mark.parametrize("palette_name", ["light", "dark"])
def test_ui_tokens_meet_wcag_non_text_contrast(palette_name: str) -> None:
    palette = PALETTES[palette_name]
    failures = []
    for foreground, background in UI_PAIRS:
        ratio = _contrast(_resolve(foreground, palette), _resolve(background, palette))
        if ratio < 3.0:
            failures.append(f"{foreground} on {background} = {ratio:.2f}")
    assert not failures, f"{palette_name} UI contrast below 3.0: {failures}"


@pytest.mark.parametrize("palette_name", ["light", "dark"])
def test_muted_ink_on_sunken_surface_is_a_documented_exception(palette_name: str) -> None:
    """--ink-muted on --surface-sunken sits just under AA on purpose.

    --surface-sunken is only a hover wash for .batch-clear and .modal-cancel,
    plus the tracked-folders list background; muted ink never lands on it. If
    this now clears 4.5 the token moved, so fold the pair into TEXT_PAIRS and
    delete this test.
    """
    ratio = _contrast(
        _resolve("--ink-muted", PALETTES[palette_name]),
        _resolve("--surface-sunken", PALETTES[palette_name]),
    )
    assert ratio >= 4.0, f"muted ink on the sunken surface regressed to {ratio:.2f}"
    if palette_name == "light":
        assert ratio < 4.5, "the documented exception is no longer needed"
