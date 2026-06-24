# Phase 4 — Polish & Production Readiness

**Branch:** `phase4`
**Base:** `add-llm`
**Date:** 2026-06-24
**Status:** planning

---

## 1. Overview

Phase 4 hardens the application for daily use. Four workstreams in priority order:

| # | Workstream | Effort | Risk |
|---|-----------|--------|------|
| **4A** | Memory pruning / GC | S (~30 lines) | Low |
| **4B** | Dark mode | M (~150 lines) | Low |
| **4C** | Auto-categorization (FE-011) | L (~200 lines) | Medium |
| **4D** | LLM retry / error recovery | S (~40 lines) | Low |

Each produces a working, testable, deployable state. None depends on the others.

---

## 2. Workstream 4A — Memory Pruning / GC

### 2.1 Problem

`memory.json` grows unbounded. Every screenshot ever seen by the app gets a permanent record — including files long since trashed, renamed, or deleted. Over months of use this file accumulates hundreds of orphaned entries. There's no cleanup mechanism.

`MemoryStore.prune_stale()` already exists and works correctly (tested in `test_memory.py`), but nothing calls it.

### 2.2 Design

**Trigger:** On every `GET /api/screenshots` scan, after building the file list, call `prune_stale()` with the set of active fingerprints. This keeps memory.json proportional to the number of screenshots currently on Desktop (+ a 90-day grace window for recently trashed/renamed files).

**Configurable:** Max age is configurable via settings. Default 90 days.

**Logging:** Log how many records were pruned so the user can observe GC activity in the console (not in the UI — it's invisible maintenance).

### 2.3 Implementation Plan

#### 2.3.1 Backend — `app.py`

```python
# In get_screenshots(), after the scan loop completes and before the sort/return:

# ── Memory pruning ──────────────────────────────────────────
# After every scan, prune orphaned entries older than the
# configured max_age_days (default 90).  Active fingerprints
# are those belonging to files still on disk right now.
if any_new or True:  # prune on every scan, not just when new files appear
    settings = _load_settings()
    max_age = settings.get("prune_max_age_days", 90)
    active_fps = {f["fingerprint"] for f in files}
    pruned = memory.prune_stale(active_fps, max_age_days=max_age)
    if pruned > 0:
        logger.info("Pruned %d stale memory entries (max age: %d days)", pruned, max_age)
        memory.save()
```

**Note:** `prune_stale()` uses `rec.last_updated` to determine age. This is updated on every mutation (`update_suggestion`, `accept_suggestion`, `reject_suggestion`, `record_rename`, `mark_trashed`). Entries that were created but never touched (status stays `"new"` and file was deleted) will use `first_seen` via the `last_updated` fallback (which equals `first_seen` at creation time). This is correct behavior.

#### 2.3.2 Settings extension

Add `prune_max_age_days` to the settings file and API. Default `90`, accept any positive integer. The settings modal doesn't need a UI for this (it's an advanced config — power users can edit `settings.json` directly, or we add it to the settings modal as an optional field).

```python
# In api_save_settings():
type_checks = {
    "llm_provider": str,
    "llm_model": str,
    "auto_suggest": bool,
    "prune_max_age_days": int,          # NEW
}
for key in ("llm_provider", "llm_model", "auto_suggest", "prune_max_age_days"):
    ...

# In api_get_settings():
return jsonify({
    "llm_provider": s.get("llm_provider", "ollama"),
    "llm_model": s.get("llm_model", DEFAULT_LLM_MODEL),
    "auto_suggest": s.get("auto_suggest", False),
    "prune_max_age_days": s.get("prune_max_age_days", 90),   # NEW
})
```

#### 2.3.3 Settings Modal — add prune age field

```html
<div class="settings-field">
  <label for="settings-prune-age">Prune memory after (days)</label>
  <input id="settings-prune-age" type="number" min="1" max="730"
         class="rename-input" />
</div>
```

JS: wire `#settings-prune-age` to `llmSettings.prune_max_age_days`.

#### 2.3.4 Tests

| Test | What it verifies |
|------|-----------------|
| `test_scan_triggers_prune_stale` | After scanning, orphaned entries beyond max age are removed from memory.json |
| `test_prune_respects_settings_age` | Changing `prune_max_age_days` in settings affects what gets pruned |
| `test_prune_keeps_active_entries` | Files still on disk are never pruned regardless of age |
| `test_prune_keeps_recent_inactive` | Files trashed 5 days ago are kept when max_age=90 |
| `test_settings_prune_age_roundtrip` | Save → load preserves prune_max_age_days |
| `test_settings_prune_age_type_validation` | Non-integer values rejected |

### 2.4 Edge Cases

- **Empty Desktop** → `active_fps` is empty → all entries older than max_age are pruned. Correct — no files means no need to remember anything old.
- **Very first scan (memory.json doesn't exist)** → `prune_stale` with empty store returns 0. Harmless.
- **User sets `prune_max_age_days=1`** → trashed files disappear from memory after 1 day. If the file is restored from Trash after 2 days, it appears as "new" and gets re-analyzed. Acceptable — the user explicitly chose aggressive pruning.
- **User sets `prune_max_age_days=730`** → effectively disables pruning. Memory grows unbounded. Acceptable — power user choice.

---

## 3. Workstream 4B — Dark Mode

### 3.1 Problem

The app is bright white (#fff, #f5f5f7). Using it at night is harsh. macOS supports system-wide dark mode preferences; the app should respect them.

### 3.2 Design

**Approach:** CSS custom properties (variables) with a `[data-theme="dark"]` selector on `<html>`. A small JS module reads `prefers-color-scheme` and sets the attribute on load, then listens for changes. A manual toggle (sun/moon icon in header) overrides the system preference and persists the choice to `localStorage`.

**Scope:** Full app — not just Phase 3 elements. The CSS is only ~450 lines; a full pass is manageable and avoids the jarring experience of partially-themed UI.

**No backend changes.** This is purely CSS + a few lines of JS.

### 3.3 Implementation Plan

#### 3.3.1 CSS Architecture

Define all colors as custom properties on `:root` (light) and `[data-theme="dark"]` (dark), then reference them everywhere:

```css
/* ── Theme variables ─────────────────────────────────────── */

:root {
  --bg-body:       #f5f5f7;
  --bg-header:     #fff;
  --bg-column:     #fafafa;
  --bg-unsorted:   #f5f5f7;
  --bg-card:       #fff;
  --bg-modal:      #fff;
  --bg-modal-overlay: rgba(0, 0, 0, 0.45);
  --bg-progress:   #f0e6ff;
  --bg-badge:      #f3e8ff;
  --bg-btn-cancel: #f0f0f0;
  --bg-btn-cancel-hover: #e4e4e4;
  --bg-settings-btn: #f0f0f0;
  --bg-settings-btn-hover: #e0e0e0;
  --bg-cancel-suggest: #fff;
  --bg-cancel-suggest-hover: #f0e6ff;

  --text-primary:  #1a1a1a;
  --text-secondary: #666;
  --text-muted:    #888;
  --text-header:   inherit;
  --text-badge:    #6b21a8;
  --text-progress: #6b21a8;

  --border-col:    #e5e5e5;
  --border-header: #e0e0e0;
  --border-badge:  #e0d0f0;
  --border-progress: #e0d0f0;

  --shadow-card:   0 1px 6px rgba(0,0,0,.08);
  --shadow-card-hover: 0 3px 12px rgba(0,0,0,.14);
  --shadow-header: 0 1px 4px rgba(0,0,0,.06);

  --count-bg:      #eee;
  --count-text:    #666;
  --count-trash-bg: #fff0f0;
  --count-trash-text: #ff3b30;
  --count-keep-bg: #f0fff4;
  --count-keep-text: #34c759;

  --column-title:  #888;
  --column-trash-title: #ff3b30;
  --column-keep-title:  #34c759;

  --lightbox-bar-bg: rgba(0, 0, 0, 0.55);
  --lightbox-filename: rgba(255, 255, 255, 0.9);
  --lightbox-filename-hover: rgba(255, 255, 255, 0.15);
  --lightbox-rename-bg: rgba(255, 255, 255, 0.2);
  --lightbox-close-bg: rgba(255, 255, 255, 0.15);
  --lightbox-close-hover: rgba(255, 255, 255, 0.3);
  --lightbox-backdrop: rgba(0, 0, 0, 0.8);
}

[data-theme="dark"] {
  --bg-body:       #1c1c1e;
  --bg-header:     #2c2c2e;
  --bg-column:     #242426;
  --bg-unsorted:   #1c1c1e;
  --bg-card:       #2c2c2e;
  --bg-modal:      #2c2c2e;
  --bg-modal-overlay: rgba(0, 0, 0, 0.7);
  --bg-progress:   #2d1f3a;
  --bg-badge:      #2d1f3a;
  --bg-btn-cancel: #3a3a3c;
  --bg-btn-cancel-hover: #48484a;
  --bg-settings-btn: #3a3a3c;
  --bg-settings-btn-hover: #48484a;
  --bg-cancel-suggest: #3a3a3c;
  --bg-cancel-suggest-hover: #2d1f3a;

  --text-primary:  #f5f5f7;
  --text-secondary: #aeaeb2;
  --text-muted:    #8e8e93;
  --text-header:   #f5f5f7;
  --text-badge:    #d4a0f0;
  --text-progress: #d4a0f0;

  --border-col:    #38383a;
  --border-header: #38383a;
  --border-badge:  #4a305a;
  --border-progress: #4a305a;

  --shadow-card:   0 1px 6px rgba(0,0,0,.3);
  --shadow-card-hover: 0 3px 12px rgba(0,0,0,.5);
  --shadow-header: 0 1px 4px rgba(0,0,0,.3);

  --count-bg:      #3a3a3c;
  --count-text:    #aeaeb2;
  --count-trash-bg: #3d1c1c;
  --count-trash-text: #ff6961;
  --count-keep-bg: #1c3d24;
  --count-keep-text: #32d74b;

  --column-title:  #8e8e93;
  --column-trash-title: #ff6961;
  --column-keep-title:  #32d74b;

  --lightbox-bar-bg: rgba(44, 44, 46, 0.85);
  --lightbox-filename: rgba(245, 245, 247, 0.9);
  --lightbox-filename-hover: rgba(245, 245, 247, 0.15);
  --lightbox-rename-bg: rgba(245, 245, 247, 0.15);
  --lightbox-close-bg: rgba(245, 245, 247, 0.15);
  --lightbox-close-hover: rgba(245, 245, 247, 0.3);
  --lightbox-backdrop: rgba(0, 0, 0, 0.9);
}
```

Then replace every hardcoded color in `style.css` with `var(--xxx)`. For example:

```css
/* Before */
body { background: #f5f5f7; color: #1a1a1a; }

/* After */
body { background: var(--bg-body); color: var(--text-primary); }
```

All `#xxxxxx` colors in the stylesheet get replaced with their variable counterpart. This is a mechanical find-replace across ~50 declarations.

#### 3.3.2 Theme toggle — HTML

Add a button in the header, between the settings gear and the sort select:

```html
<button id="theme-toggle" class="header-theme-btn" aria-label="Toggle dark mode">
  <span class="theme-icon-light">☀</span>
  <span class="theme-icon-dark">☾</span>
</button>
```

```css
.header-theme-btn {
  padding: 8px 10px;
  border: none;
  border-radius: 8px;
  background: var(--bg-settings-btn);
  color: var(--text-primary);
  font-size: 1rem;
  cursor: pointer;
  transition: background 0.15s;
}
.header-theme-btn:hover { background: var(--bg-settings-btn-hover); }

/* Show/hide icons based on theme */
[data-theme="dark"] .theme-icon-light { display: none; }
[data-theme="dark"] .theme-icon-dark  { display: inline; }
:root .theme-icon-dark  { display: none; }
:root .theme-icon-light { display: inline; }
```

#### 3.3.3 Theme JS module

```javascript
// ── Theme management ─────────────────────────────────────────
const THEME_KEY = "ss-dcl-theme";

function applyTheme(mode) {
  if (mode === "dark") {
    document.documentElement.setAttribute("data-theme", "dark");
  } else if (mode === "light") {
    document.documentElement.removeAttribute("data-theme");
  } else {
    // "auto" — follow system
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.toggleAttribute("data-theme", prefersDark);
  }
}

function getSavedTheme() {
  try { return localStorage.getItem(THEME_KEY) || "auto"; } catch (_) { return "auto"; }
}

function saveTheme(mode) {
  try { localStorage.setItem(THEME_KEY, mode); } catch (_) {}
}

function cycleTheme() {
  const current = getSavedTheme();
  const next = { auto: "dark", dark: "light", light: "auto" }[current] || "auto";
  saveTheme(next);
  applyTheme(next);
}

// On load
applyTheme(getSavedTheme());

// Listen for system changes (only matters when mode is "auto")
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  if (getSavedTheme() === "auto") applyTheme("auto");
});

// Wire the toggle button
document.getElementById("theme-toggle").addEventListener("click", cycleTheme);
```

**Behavior:**
- Default: `"auto"` — follows system preference, no `localStorage` entry
- Click once: `"dark"` — forces dark, saved to `localStorage`
- Click again: `"light"` — forces light, saved to `localStorage`
- Click again: `"auto"` — back to system, saved to `localStorage`
- System preference change: only takes effect when mode is `"auto"`

#### 3.3.4 Tests

| Test | What it verifies |
|------|-----------------|
| `test_index_has_theme_toggle` | `#theme-toggle` button exists in HTML |
| `test_app_js_has_theme_cycle` | `function cycleTheme` or `THEME_KEY` appears in JS |
| `test_css_has_dark_variables` | `[data-theme="dark"]` block exists in CSS with `--bg-body` |
| `test_css_has_light_variables` | `:root` block exists with CSS custom properties |

### 3.4 Edge Cases

- **`localStorage` unavailable** (private browsing, old browser) → `try/catch` around all `localStorage` calls. Falls back to `"auto"` in memory, which follows system preference. The toggle button still works for the session.
- **System preference changes mid-session** → `matchMedia` listener re-applies when mode is `"auto"`. When mode is `"dark"` or `"light"` (manual override), system changes are ignored.
- **Browser doesn't support `prefers-color-scheme`** → `matchMedia(...).matches` returns `false` → light theme. Graceful degradation.
- **CSS variable not defined** → Browser uses initial/inherited value. Fallback colors are the light theme (defined in `:root`), so missing dark variables just show light colors in dark mode. Not ideal but not broken.

---

## 4. Workstream 4C — Auto-Categorization (FE-011)

### 4.1 Problem

Users manually sort every screenshot into Keep/Trash. Many screenshots follow patterns (e.g., "all code editor screenshots → Keep, all meme screenshots → Trash"). The app could learn these patterns and suggest a column, reducing manual work.

### 4.2 Design

**Approach: Heuristic-based, not ML.** A full ML pipeline (training, feature extraction, model serving) is overkill for a local single-user tool. Instead, use lightweight heuristics that improve with use:

1. **Filename patterns** — if the user always trashes files matching `Screenshot * at *.?? PM.png` (evening screenshots) but keeps `Screenshot * at *.?? AM.png` (morning work), learn that.
2. **Content-based via LLM** — we already have LLM integration. After the LLM generates a name like `"customer-onboarding-thread.png"`, we can ask a second, tiny question: *"Does this screenshot look like work or personal?"* and use the answer as a categorization hint.
3. **User history** — for any fingerprint that's been categorized before (Keep/Trash), reuse the decision if the same file reappears.

Actually, **let me simplify.** The most practical auto-categorization for this app is:

**Heuristic A: Content keywords from LLM suggestion.** After the LLM suggests a name, extract keywords and check against user's historical patterns. If the suggested name contains words from previously-kept files → suggest Keep. If from previously-trashed → suggest Trash.

**Heuristic B: Time-of-day.** Screenshots taken during work hours (9-5) might be work-related → suggest Keep. Evening/weekend → unsure.

**Heuristic C: App source (future).** If we add OCR or window-title extraction, we could know which app produced the screenshot. Code editor → Keep, social media → Trash. This requires macOS accessibility APIs and is out of scope for now.

**Recommendation: Start with Heuristic A only** — it's zero additional work since we already have LLM suggestions. The `memory.meta` field stores the keywords.

### 4.3 Revised Design (Heuristic A Only)

Flow:

```
1. LLM generates suggested name: "customer-onboarding-discussion.png"
2. Extract keywords: ["customer", "onboarding", "discussion"]
3. Check user's history:
   - Files user KEPT that share these keywords → keep_score += 1 per match
   - Files user TRASHED that share these keywords → trash_score += 1 per match
4. If keep_score > trash_score → suggest "Keep" (show green hint on card)
   If trash_score > keep_score → suggest "Trash" (show red hint on card)
   If equal or no history → neutral (no hint)
5. Store keywords in memory.meta for future reference
```

**Keyword extraction from LLM output:**

```python
def extract_keywords(suggested_name: str) -> list[str]:
    """Extract stemmed keywords from a kebab-case filename."""
    # "customer-onboarding-discussion.png" → ["customer", "onboarding", "discussion"]
    stem = Path(suggested_name).stem
    return [w.lower() for w in stem.split("-") if len(w) > 2]
```

**Categorization logic:**

```python
def suggest_category(
    keywords: list[str],
    memory: MemoryStore,
) -> Optional[str]:
    """Return 'keep', 'trash', or None based on historical patterns."""
    keep_score = 0
    trash_score = 0

    for rec in memory.all_records():
        if rec.status in ("renamed", "trashed"):
            rec_keywords = rec.meta.get("keywords", [])
            overlap = set(keywords) & set(rec_keywords)
            if rec.status == "renamed":   # user accepted → kept
                keep_score += len(overlap)
            elif rec.status == "trashed":
                trash_score += len(overlap)

    if keep_score > trash_score:
        return "keep"
    elif trash_score > keep_score:
        return "trash"
    return None  # neutral
```

### 4.4 Integration Points

#### 4.4.1 Backend — `app.py`

After `api_suggest_names` updates the suggestion, run categorization:

```python
# In api_suggest_names, after memory.update_suggestion():
keywords = extract_keywords(suggested)
category = suggest_category(keywords, memory)
if category:
    rec = memory.lookup(fp)
    rec.meta["keywords"] = keywords
    rec.meta["suggested_category"] = category
```

Add `suggested_category` to `GET /api/screenshots` response:

```python
files.append({
    ...
    "suggested_category": existing.meta.get("suggested_category") if existing else None,
})
```

#### 4.4.2 Frontend — `app.js`

When a card has `suggested_category === "keep"`, show a subtle green left-border or a small "✨ Keep?" badge below the suggestion badge. When `"trash"`, red. When `null`, nothing.

```javascript
// In makeCard(), after building the card:
if (suggestedCategory === "keep") {
  card.style.borderLeft = "3px solid #34c759";
} else if (suggestedCategory === "trash") {
  card.style.borderLeft = "3px solid #ff3b30";
}
```

Or, more consistently: add a small colored dot in the suggestion badge area.

```javascript
// In _makeSuggestionBadge(), after the name span:
if (card.dataset.suggestedCategory === "keep") {
  const hint = document.createElement("span");
  hint.className = "suggestion-category-hint keep";
  hint.textContent = "✨ Keep?";
  badge.appendChild(hint);
}
```

### 4.5 Tests

| Test | What it verifies |
|------|-----------------|
| `test_extract_keywords_from_suggested_name` | `"foo-bar-baz.png"` → `["foo", "bar", "baz"]` |
| `test_extract_keywords_filters_short_words` | `"a-b-cat.png"` → `["cat"]` |
| `test_suggest_category_no_history_returns_none` | Empty memory → `None` |
| `test_suggest_category_keep_when_keywords_match_kept` | Previously kept files with matching keywords → `"keep"` |
| `test_suggest_category_trash_when_keywords_match_trashed` | Previously trashed files with matching keywords → `"trash"` |
| `test_suggest_category_tie_returns_none` | Equal keep/trash scores → `None` |
| `test_suggest_names_stores_keywords_in_meta` | After LLM suggest, `rec.meta.keywords` is populated |
| `test_screenshots_includes_suggested_category` | Response includes `suggested_category` field |
| `test_frontend_card_shows_category_hint` | JS has code for category-based visual hints |

### 4.6 Edge Cases

- **No LLM suggestions yet** → No keywords, no categorization. Neutral. Works.
- **All history is trashed (user is aggressive)** → Everything gets categorized as "trash". The user might want to reset. Future feature: "reset learning data" button.
- **Keywords overlap with both keep and trash** → Score-based tie-breaking. Higher overlap wins.
- **Single-word suggestions** (e.g., `"screenshot.png"`) → Only one keyword, weak signal. Most won't match history → neutral. Acceptable.
- **memory.meta grows** → Each record stores a `keywords` list. For 500 files with ~3 keywords each, that's ~500 × 3 × 10 bytes ≈ 15 KB. Negligible.
- **Privacy** → Keywords are stored locally in `memory.json`. They're just word fragments from filenames. No user data leaves the machine.

---

## 5. Workstream 4D — LLM Retry / Error Recovery

### 5.1 Problem

`_call_ollama_suggest` has a single 30s timeout with no retry. Ollama can be slow to load the model on first request (cold start: 10-30s), or the model might be temporarily busy with another request. One failure and the file is skipped forever (status stays `"new"` but `api_suggest_names` won't retry because it only processes `"new"` files — but it doesn't change status on failure, so it *will* retry on the next scan... unless the user doesn't trigger another suggest).

Actually, looking at the code again: `api_suggest_names` skips files whose status is not `"new"`. On LLM failure, the status stays `"new"` — so the file *will* be retried next time. The real issue is: **the user gets a silent failure with no feedback during the current batch**, and has to manually re-trigger "Suggest All".

### 5.2 Design

**Retry logic:** Retry failed Ollama calls up to 2 times with exponential backoff (1s, 3s). Only mark as permanently failed after 3 attempts.

**Timeout:** Increase initial timeout to 60s (model cold-start can exceed 30s on first request). Subsequent requests in the same batch reuse the loaded model and are faster.

**Status for failed files:** Introduce a transient status `"retry"` in the frontend (not persisted — it's session-only) so the user sees "3 files failed — try again?".

Actually, simpler approach: **Keep status as `"new"` on failure** (already the case), but **track failures in the batch response** and show them in the UI. The progress bar already has `firstError` tracking. Enhance it:

```python
# In api_suggest_names, return failures alongside suggestions:
return jsonify({
    "suggestions": {...},
    "failures": ["fp1", "fp2"],   # fingerprints that failed
    "error": None,                 # or a global error message
})
```

And in the JS:

```javascript
if (data.failures && data.failures.length > 0) {
  // Show "3 files couldn't be processed — try again?"
  statusMsg.textContent = `${data.failures.length} files couldn't be processed. Try again?`;
}
```

### 5.3 Implementation Plan

#### 5.3.1 Backend — retry in `_call_ollama_suggest`

```python
def _call_ollama_suggest(
    image_path: Path,
    model: str,
    extension: str = ".png",
    max_retries: int = 2,
) -> Optional[str]:
    ...
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read())
                raw = result.get("message", {}).get("content", "").strip()
                break  # success → exit retry loop
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            if attempt < max_retries:
                wait = (2 ** attempt)  # 1s, 2s
                logger.warning(
                    "Ollama attempt %d/%d failed for %s, retrying in %ds: %s",
                    attempt + 1, max_retries + 1, image_path.name, wait, exc,
                )
                time.sleep(wait)
            else:
                logger.warning(
                    "Ollama suggest failed after %d attempts for %s: %s",
                    max_retries + 1, image_path.name, exc,
                )
                return None
    ...
```

#### 5.3.2 Backend — return failures

```python
# In api_suggest_names:
failures: list[str] = []

for fp in fingerprints:
    ...
    suggested = _call_ollama_suggest(file_path, model, rec.extension)
    if suggested:
        ...
    else:
        failures.append(fp)

return jsonify({
    "suggestions": suggestions,
    "failures": failures,
})
```

#### 5.3.3 Frontend — show failure count

In `suggestBatch`, after the batch completes, check `failures`:

```javascript
// After all chunks processed:
if (failures.length > 0) {
    statusMsg.textContent =
        `${failures.length} file${failures.length > 1 ? "s" : ""} couldn't be processed. Try again?`;
}
```

#### 5.3.4 Tests

| Test | What it verifies |
|------|-----------------|
| `test_suggest_names_returns_failures_list` | Failures appear in response when LLM returns None |
| `test_suggest_names_empty_failures_on_success` | `failures: []` when all succeed |
| `test_call_ollama_suggest_retries_on_failure` | Retries up to max_retries times before giving up |
| `test_call_ollama_suggest_succeeds_on_retry` | Second attempt succeeds → returns suggestion |
| `test_frontend_shows_failure_count` | JS code references `failures.length` or similar |

### 5.4 Edge Cases

- **All files fail** → progress bar shows "0 processed", status message shows failure count.
- **Partial failure** → some get badges, some don't. Status message shows count. User can re-trigger "Suggest All" (failed files are still `"new"`).
- **Ollama crashes mid-batch** → Each file is tried independently. First failure triggers retries. Subsequent files also retry. The batch continues with remaining files.
- **Network timeout vs model-not-found** → `URLError` covers both. The retry loop is the same. If model isn't pulled at all, all retries fail quickly → all files appear in `failures`.

---

## 6. File Change Summary

### 4A — Memory Pruning

| File | Action | Lines (est.) |
|------|--------|-------------|
| `src/ss_dcl/app.py` | Modify `get_screenshots()` + settings endpoints | +15, ~3 changed |
| `static/app.js` | Add prune age to settings modal | +5 |
| `templates/index.html` | Add prune age input to settings | +5 |
| `tests/test_routes_memory.py` | 5 new pruning tests | +80 |

### 4B — Dark Mode

| File | Action | Lines (est.) |
|------|--------|-------------|
| `static/style.css` | Replace colors with `var(--xxx)`, add `:root` + `[data-theme]` blocks | ~+120, ~50 changed |
| `static/app.js` | Theme management module | +30 |
| `templates/index.html` | Theme toggle button | +5 |
| `tests/test_frontend.py` | 3 new theme tests | +30 |

### 4C — Auto-Categorization

| File | Action | Lines (est.) |
|------|--------|-------------|
| `src/ss_dcl/app.py` | `extract_keywords()`, `suggest_category()`, wire into suggest-names | +50 |
| `src/ss_dcl/memory.py` | No changes (uses existing `meta` field) | 0 |
| `static/app.js` | Category hint in badge, `suggestedCategory` dataset | +20 |
| `tests/test_routes_memory.py` | 6 new categorization tests | +100 |

### 4D — LLM Retry

| File | Action | Lines (est.) |
|------|--------|-------------|
| `src/ss_dcl/app.py` | Retry loop in `_call_ollama_suggest`, failures in response | +25, ~5 changed |
| `static/app.js` | Show failure count in status | +10 |
| `tests/test_routes_memory.py` | 4 new retry tests | +70 |

### Totals

| Workstream | Est. Lines |
|-----------|-----------|
| 4A — Pruning | ~105 |
| 4B — Dark mode | ~235 |
| 4C — Auto-categorization | ~170 |
| 4D — LLM retry | ~110 |
| **Total** | **~620** |

---

## 7. Validation Against Current Codebase

### Checkpoint 1: Does this break existing tests?
- **4A**: `get_screenshots` gains a `prune_stale` call. Existing tests use temp dirs with freshly-created files → no stale entries to prune → `prune_stale` returns 0. No test breakage.
- **4B**: CSS variable changes are purely visual. Existing frontend tests check for IDs and class names in source, not color values. No test breakage.
- **4C**: `suggested_category` added to API response (additive field). Existing tests don't assert on its absence. `meta.keywords` added to existing records. No test breakage.
- **4D**: `_call_ollama_suggest` signature unchanged (added keyword-only `max_retries`). Existing mocks ignore extra kwargs. Response adds `failures` field — existing tests for unknown fingerprints return `{"suggestions": {}, "failures": []}`. The empty dict test `{"suggestions": {}}` will need updating. **One test needs adjustment.**

### Checkpoint 2: Does this fit the project philosophy?
- ✅ No build step
- ✅ No new runtime dependencies
- ✅ Single-user, localhost-only
- ✅ JSON file storage (settings.json extended)
- ✅ Atomic writes where needed
- ✅ Vanilla JS, no frameworks
- ✅ Zero additional I/O (pruning uses in-memory data)

### Checkpoint 3: Is this extensible?
- CSS variables make future theming trivial (add `[data-theme="high-contrast"]`)
- `memory.meta` dict already supports arbitrary data — categorization is just the first use
- Retry logic is parameterized (`max_retries`) — easy to make configurable
- Pruning age is already in settings — can add UI for it later

---

## 8. Dependency Graph

```
4A (pruning) ── independent ── can be implemented first
    │
4B (dark mode) ── independent ── purely CSS/JS, no backend
    │
4C (auto-categorization) ── depends on Phase 3 (LLM suggestions exist)
    │
4D (retry) ── depends on Phase 3 (_call_ollama_suggest exists)
```

All four can be done in any order. Recommended order: 4A → 4B → 4D → 4C (simplest first, builds confidence).

---

## 9. Risk Analysis

| Risk | Mitigation |
|------|-----------|
| Pruning too aggressive | Default 90 days is conservative. Configurable. Log every prune. |
| Dark mode colors look bad | Use macOS system colors as reference. Test manually on real machine. |
| Auto-categorization suggests wrong column | It's a *suggestion* (subtle hint), not an automatic move. User still has final say. |
| Retry loop hangs on persistent failure | Max 3 attempts × 60s timeout = 3 min max per file. Acceptable for local tool. |
| CSS variable refactor introduces visual regressions | Mechanical find-replace. Visual diff by running the app before/after. |
| `failures` field changes API contract | Old frontend ignores unknown fields. New frontend checks for it. Backward compatible. |
