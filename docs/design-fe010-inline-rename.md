# FE-010: Inline Filename Display & Lightbox Rename

**Status:** in-progress
**Branch:** `feat/inline-rename-lightbox`

## Problem

Screenshots are displayed as thumbnail-only cards with no visible filename. The only way to see a filename is through the Rename button's modal (which requires clicking an action, not browsing). There is no way to view or edit the filename while viewing the full-size image in the lightbox.

## Goals

1. **Hover tooltip on cards** — show filename when hovering over a screenshot card
2. **Lightbox rename bar** — semi-transparent bar at the bottom of the lightbox showing the filename, editable inline (iOS app-group naming style, but at the bottom)
3. **Seamless state sync** — rename from lightbox updates card, state, and thumbnail just like the existing modal rename

## Non-Goals

- Bulk rename (that's FE-005)
- Changing the existing Rename button/modal on cards (keep it as a fallback)
- Adding metadata beyond filename (file size, date, dimensions — that's FE-008 territory)

## Current Architecture (What Exists)

### Backend (`src/ss_dcl/app.py`)
- `POST /api/rename` — already handles rename with full validation (path traversal, conflict 409, file-not-found 404), thumbnail migration, and state migration. **No backend changes needed.**

### Frontend (`static/app.js`)
- **Cards** (`makeCard()`) — `<article class="card">` containing `<img>` + `<div class="card-actions">`. No visible filename text. Filename stored in `data-filename` attribute.
- **Rename modal** — separate modal dialog triggered by card action button. Pre-fills input, selects up-to-extension, POSTs to `/api/rename`.
- **Lightbox** — full-screen overlay with backdrop blur, shows `<img>` only. Has arrow-key navigation and close button. **No filename display or rename capability.**
- **State** — `decisions` Map + `saveState()` (debounced 300ms). Renames migrate the key in the map.

### Key Files to Modify
| File | Change |
|------|--------|
| `templates/index.html` | Add lightbox rename bar HTML |
| `static/style.css` | Add card tooltip styles + lightbox rename bar styles |
| `static/app.js` | Add tooltip logic, lightbox rename bar logic, inline rename handler |
| `tests/test_frontend.py` | Add tests for new frontend behavior |

### Files NOT Modified
| File | Reason |
|------|--------|
| `src/ss_dcl/app.py` | Existing `/api/rename` endpoint is sufficient |
| `tests/test_routes_rename.py` | Backend rename tests already comprehensive |

---

## Design

### 1. Card Hover Tooltip

**Behavior:**
- On hover, display the filename in a tooltip overlaid at the bottom of the card
- Tooltip appears with a brief fade-in (~150ms)
- Tooltip is semi-transparent dark background with white text
- On mouse leave, tooltip fades out

**HTML changes:** None — tooltip is created dynamically per-card via JS, or we use a single shared tooltip element positioned via JS (preferred to avoid N tooltip DOM nodes for N cards).

**Approach: Single shared tooltip element**
- Add one `<div id="card-tooltip" class="card-tooltip">` to `index.html` (inside `#app` container)
- On `mouseenter` of a card: position the tooltip at the card's bottom edge, set text to `card.dataset.filename`, show it
- On `mouseleave`: hide it
- Use `requestAnimationFrame` for positioning to avoid layout thrash

**CSS:**
```
.card-tooltip {
    position: fixed;
    z-index: 50;
    background: rgba(0, 0, 0, 0.75);
    backdrop-filter: blur(8px);
    color: #fff;
    padding: 6px 12px;
    border-radius: 8px;
    font-size: 0.8rem;
    font-family: -apple-system, SF Mono, Menlo, monospace;
    max-width: 200px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    pointer-events: none;
    opacity: 0;
    transition: opacity 150ms ease;
}
.card-tooltip.visible { opacity: 1; }
```

**JS:**
- In `makeCard()`, add `mouseenter`/`mouseleave` listeners
- Position tooltip using `card.getBoundingClientRect()` — center it below the card
- Long filenames get truncated with ellipsis (CSS `text-overflow: ellipsis`)

### 2. Lightbox Rename Bar

**Behavior:**
- When lightbox opens, a semi-transparent bar appears at the bottom of the viewport
- Bar contains the filename displayed as editable text (like iOS app group naming)
- Clicking the filename text transforms it into an `<input>` field
- Press Enter or blur to confirm rename; Escape to cancel
- Visual feedback: subtle highlight/glow when editing, success flash on confirm
- Bar does NOT block the image — it overlays the bottom portion
- Arrow-key navigation still works while rename bar is in display mode (not editing)
- Close lightbox works as before

**HTML (added to `#lightbox`):**
```html
<div id="lightbox" class="lightbox" hidden role="dialog" aria-label="Image preview">
  <div class="lightbox-backdrop"></div>
  <img class="lightbox-img" id="lightbox-img" src="" alt="" decoding="async" />
  <button class="lightbox-close" id="lightbox-close" aria-label="Close">&times;</button>
  <!-- NEW: rename bar -->
  <div class="lightbox-bar">
    <span class="lightbox-filename" id="lightbox-filename"></span>
    <input class="lightbox-rename-input" id="lightbox-rename-input" type="text"
           autocomplete="off" spellcheck="false" hidden />
  </div>
</div>
```

**CSS:**
```
.lightbox-bar {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 16px 24px;
    background: rgba(0, 0, 0, 0.55);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border-radius: 14px 14px 0 0;
    z-index: 2;
}

.lightbox-filename {
    color: rgba(255, 255, 255, 0.9);
    font-size: 1rem;
    font-family: -apple-system, SF Mono, Menlo, monospace;
    padding: 6px 16px;
    border-radius: 8px;
    cursor: text;
    transition: background 200ms ease;
    max-width: 60vw;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.lightbox-filename:hover {
    background: rgba(255, 255, 255, 0.15);
}

.lightbox-rename-input {
    font-size: 1rem;
    font-family: -apple-system, SF Mono, Menlo, Consolas, monospace;
    background: rgba(255, 255, 255, 0.2);
    backdrop-filter: blur(8px);
    color: #fff;
    border: 2px solid rgba(0, 122, 255, 0.8);
    border-radius: 8px;
    padding: 6px 16px;
    outline: none;
    max-width: 60vw;
    text-align: center;
}

.lightbox-rename-input::placeholder {
    color: rgba(255, 255, 255, 0.4);
}
```

**JS — interaction flow:**

```
openLightbox(card):
  ...existing logic...
  Set #lightbox-filename.textContent = card.dataset.filename
  Reset rename input (hidden, cleared)

Click on #lightbox-filename:
  - Hide the <span>, show the <input>
  - Pre-fill input with current filename
  - Select text up to extension (same logic as existing modal)
  - Focus the input

Enter key on #lightbox-rename-input:
  - Validate client-side (non-empty, no path separators, different from current)
  - POST /api/rename with { old_name, new_name }
  - On success:
    - Update card dataset.filename, img alt
    - Update #lightbox-filename text
    - Update decisions map, save state
    - Flash success indicator (brief green glow or similar)
    - Hide input, show span
  - On error: show error state (red border), keep input focused

Escape key on #lightbox-rename-input:
  - Cancel editing, hide input, show span (unchanged)

Blur on #lightbox-rename-input:
  - Same as Enter (confirm if changed, cancel if unchanged)

lightboxNavigate():
  After changing image, also update #lightbox-filename text
```

### 3. State Sync

The inline rename reuses the existing `POST /api/rename` endpoint. After a successful rename:

| What | How |
|------|-----|
| Card `data-filename` | `card.dataset.filename = newName` |
| Card `img.alt` | `img.alt = sanitise(newName)` |
| Card tooltip | Updated automatically (reads from `dataset.filename` on next hover) |
| Lightbox filename display | `lightboxFilename.textContent = newName` |
| `decisions` Map | Delete old key, set new key with same value |
| Thumbnail `src` | Bust cache: `img.src = /api/thumb/${newName}?t=${Date.now()}` |
| Lightbox `src` | Bust cache: `lightboxImg.src = /api/image/${newName}?t=${Date.now()}` |
| State file | `saveState()` (debounced) writes to `/api/state` |
| Backend state file | Already updated by `/api/rename` handler |
| `lightbox.dataset.currentFilename` | Update to `newName` for navigation |

### 4. Interaction Between Lightbox Rename and Card Rename Modal

Both use the same API. Potential conflict if user opens rename modal while lightbox is open — but this is unlikely since lightbox covers the cards. No special handling needed. If somehow both are open, the second rename will either succeed (different files) or get a 409 conflict (same file, different new names).

### 5. Error Handling in Lightbox Rename

| Scenario | UI Response |
|----------|-------------|
| Empty filename | Red border on input, keep focused |
| Same as current | Cancel editing (no-op) |
| Path separators | Red border, error shake animation |
| 409 Conflict | Show brief error message below input |
| 404 File not found | Close lightbox, reload screenshots (file was moved externally) |
| Network error | Show "Network error" below input, keep input focused |

### 6. Accessibility

- `#lightbox-filename` has `role="button"` and `tabindex="0"` for keyboard accessibility
- `aria-label` on the filename span: "Click to rename"
- When editing, the input gets `aria-label="Rename filename"`
- Screen readers announce rename success/failure

---

## Edge Cases

1. **Very long filenames** — tooltip and lightbox bar both use `text-overflow: ellipsis`; input field allows full editing with scroll
2. **Filenames with special characters** — `sanitise()` already handles HTML escaping; API validates path traversal
3. **Rename while navigating** — if user starts typing in rename input, arrow keys should NOT navigate (check if input is focused before handling arrow key navigation)
4. **Rename followed by navigation** — after renaming, navigating to next/prev card should use the new filename for the image source
5. **Multiple rapid renames** — confirm button/input disables during API call (same pattern as existing modal)
6. **External file deletion between lightbox open and rename** — API returns 404, close lightbox and reload
7. **Lightbox bar overlapping image content** — bar is semi-transparent with backdrop blur so image is still partially visible beneath it

---

## Implementation Plan

| Step | File(s) | Description |
|------|---------|-------------|
| 1 | `templates/index.html` | Add shared tooltip `<div>` inside `#app`, add lightbox bar HTML inside `#lightbox` |
| 2 | `static/style.css` | Add `.card-tooltip`, `.lightbox-bar`, `.lightbox-filename`, `.lightbox-rename-input` styles |
| 3 | `static/app.js` | Add tooltip show/hide/position logic in `makeCard()` |
| 4 | `static/app.js` | Add lightbox bar population in `openLightbox()` and `_lightboxNavigate()` |
| 5 | `static/app.js` | Add inline rename handler (click-to-edit, Enter/Escape/blur, API call, state sync) |
| 6 | `static/app.js` | Guard arrow-key navigation when rename input is focused |
| 7 | `tests/test_frontend.py` | Add tests for tooltip display, lightbox rename bar, inline rename flow |
| 8 | Manual QA | Verify hover tooltip, lightbox rename, state persistence, error states |

---

## Testing Strategy

### Frontend Tests (`tests/test_frontend.py`)
- Tooltip appears on card hover (check DOM for tooltip visibility)
- Lightbox opens with correct filename in bar
- Click filename shows input, pre-fills value, selects up-to-extension
- Enter confirms rename, updates card and lightbox
- Escape cancels rename
- Arrow keys blocked during editing
- Error handling (empty, conflict)

### Existing Tests (Unchanged)
- All `tests/test_routes_rename.py` tests pass unchanged (no backend changes)
- All `tests/test_frontend.py` existing tests pass

---

## Files Changed Summary

| File | Lines Added (est.) | Lines Changed (est.) |
|------|--------------------|-----------------------|
| `templates/index.html` | +10 | ~2 |
| `static/style.css` | +80 | 0 |
| `static/app.js` | +120 | ~15 (lightbox open, navigate) |
| `tests/test_frontend.py` | +40 | 0 |
| **Total** | **~250** | **~17** |
