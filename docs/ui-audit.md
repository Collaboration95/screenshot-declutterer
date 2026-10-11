# UI audit — Screenshot Declutterer

Audit only. No source, test, or doc other than this file was changed.
Audited at commit `b80bc47` (main) on 2026-10-11.

## 0. How this was verified

| Tag | Meaning |
| --- | --- |
| **[code]** | Confirmed by reading `templates/index.html`, `static/app.js`, `static/style.css`, `src/ss_dcl/app.py`, or `git log`. |
| **[live]** | Confirmed in the running app against the isolated demo fixture (`SS_DCL_DESKTOP`/`SS_DCL_HOME` under `.cache/ui-audit/`, `LITERT_BASE_URL=http://127.0.0.1:1`, port 5311), driven with Chrome DevTools: computed styles, `getBoundingClientRect`, `elementFromPoint`, real clicks, screenshots. |
| **[synthetic]** | The state cannot occur with the fixture, so it was forced in-page (cleanup group, scan error, empty board, suggest-progress panel, settings-dirty warning). The rendering is real; only the trigger is simulated. |

Viewports: 1440x900 (light and dark), 1280x800 (light), 1024x768 (light and dark), 800x700 (light).
Screenshots are in `.cache/ui-audit/shots/` (gitignored, local only) and are cited as `shots/NN-...png`.
The fixture exposes no Spotlight "cleanup" data, so the cleanup group was only seen [synthetic].
Real drag-and-drop (HTML5 DnD) cannot be driven through DevTools, so DnD is assessed [code] only.

Not verifiable here: the real folder picker (`/api/pick-folder` shells out to `osascript`), a running LiteRT server (start/stop success path), and a real Done/trash run (send2trash).

### Severity legend

| Severity | Meaning |
| --- | --- |
| blocker | A core workflow cannot be completed. |
| high | Visible defect on a primary surface, or a shipped feature that a mouse user cannot reach. |
| medium | Real defect or inconsistency with a workaround, or a clear design-language gap. |
| low | Polish, hygiene, or latent edge case. |

### Summary

41 issues: **0 blocker, 5 high, 22 medium, 14 low.**

Main themes:

1. **Stray `\u` escapes in HTML (confirmed and extended).** Three literals in `templates/index.html` render as text (`Loading\u2026`, `Name (A\u2013Z)`, `Name (Z\u2013A)`). The JS escape at `app.js:2465` is valid. No mojibake, no `&amp;` double escapes, and no stray entities were found anywhere else. One more stale-text bug was found: the offline message tells the user to "use the Start button above", and no such button exists.
2. **Features that exist but are not reachable by mouse.** Cards with a pending name suggestion lose Keep/Trash/Preview/More behind the suggestion badge. The "N similar" and "Identical" buttons sit under the hover action bar and cannot be clicked. The per-card "Suggest name" action is shown for the wrong status (inverted condition after the Phase 2 rebuild).
3. **Two generations of CSS are stacked.** Lines 1-3220 are the first pass, lines 3371-4402 override it. About 39 classes in the CSS have no DOM. Button and modal styling come from both layers, and the result is 14+ button families and four different modal shells.
4. **Persistent error state.** Errors announced with `timeout: 0` stay in the app bar and as toasts after the problem is fixed. The same message is rendered up to four times.
5. **No touch or swipe path yet.** There are no pointer/touch handlers and no `hover: none` rule. At 1024px and below only one column is visible, so drag-and-drop between columns is impossible.

---

## 1. Feature visibility matrix

Columns: **BE** = backend support; **JS** = handler present; **DOM** = element exists (template or created in JS); **Mouse** = visible/reachable without hidden state; **Kbd** = keyboard path; **Compact** = <=1024px (one column at a time).
"Hover-gated" means the control only appears while the card is hovered or focus is inside it (`style.css:4051-4062`).

| # | Feature | BE | JS | DOM | Mouse | Kbd | Compact | Gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Move Keep / Trash / back to Unsorted (buttons) | `PUT /api/state` | `moveCard` app.js:1127 | `setCardActions` app.js:1076 | Hover-gated. **Blocked** on suggestion cards (UI-006) and partly under the similarity buttons (UI-007) | Card focus: Left=Keep, Right=Trash (Unsorted); Left/Right=Unsorted (Keep/Trash) app.js:1862-1870. Undocumented | Yes, via switcher | UI-006, UI-011 |
| 2 | Drag and drop | same | `attachDrag` app.js:1173, column handlers app.js:1201 | `draggable` cards, three columns | Yes | None (arrows are the keyboard alternative) | **Impossible**: only one column is displayed | UI-014 |
| 3 | Select card (click / Space / Enter / check circle) | n/a | `toggleSelect` app.js:1255 | `.card-select` created app.js:875 | Click anywhere on card; the check circle is nearly invisible (white at 20% on the thumbnail, tick only on hover) | Enter/Space on focused card | Yes | UI-034 |
| 4 | Batch bar (Keep / Trash / Clear) | n/a | `updateBatchBar` app.js:1324 | `#batch-bar` index.html:155 | Appears bottom-center when 1+ selected | Esc clears; buttons are tabbable | Yes | No Unsorted/Suggest/Select-all (UI-013) |
| 5 | Undo | n/a | `performUndo` app.js:2295 | `#undo-btn` | Visible, disabled when empty | Cmd/Ctrl+Z (also fires inside text inputs, UI-018) | Yes | One entry per card (UI-013); stuck state (UI-017) |
| 6 | Done / confirm trash | `POST /api/done` (207 on partial) | `doneBtn` app.js:2440, `modalConfirm` app.js:2456 | `#done-btn`, `#confirm-modal` | Visible; label becomes "Clean up N" | Focus trap, Esc | Yes | aria-label mismatch (UI-035), copy (UI-036) |
| 7 | Rename (modal) | `POST /api/rename` | `openRenameModal` app.js:2369 | `#rename-modal`; trigger `.btn-rename` inside the "..." menu | Two clicks, hover-gated | Enter / Esc | Yes | UI-011, UI-027, UI-031 |
| 8 | Rename (lightbox inline) | same | `_startLightboxRename` app.js:1698 | `#lightbox-rename-btn`, click on filename | Yes, inside lightbox | Enter / Esc | Yes | UI-025 |
| 9 | Preview / lightbox with prev/next | `GET /api/image` | `openLightbox` app.js:1550, `_lightboxNavigate` app.js:1576 | `#lightbox` | Icon-only eye button (hover-gated) or double-click | Left/Right/Esc | Yes | No triage actions (UI-015) |
| 10 | Reveal in Finder | `POST /api/reveal` | `revealInFinder` app.js:1612 | `.btn-reveal` in "..." menu; `#lightbox-reveal-btn` | Two clicks / inside lightbox | Tab | Yes | Label differs ("Reveal in Finder" vs "Finder"), UI-032 |
| 11 | Suggest name (single card) | `POST /api/suggest-names` | `suggestSingle` app.js:1901 | `.btn-suggest` app.js:1104 | Only in "..." menu, and only for cards that are **not** `new` | Tab | Yes | **Inverted** (UI-008); never on Keep/Trash cards |
| 12 | Suggest All | same | `suggestAllBtn` app.js:2130 | `#suggest-all-btn` index.html:316 (inside Settings, outside the form) | Settings -> pink strip at the bottom | Tab | Yes | UI-010 |
| 13 | Suggestion badge: accept / dismiss / edit | `/api/accept-suggestion`, `/api/reject-suggestion` | `acceptSuggestion` 2058, `rejectSuggestion` 2082, `editSuggestion` 2111 | `_makeSuggestionBadge` app.js:944 | Always visible (not hover-gated) | Tab | Yes | Accessible names are the glyphs (UI-035); covers the action bar (UI-006) |
| 14 | Auto-suggest on scan | `settings.auto_suggest` | `loadScreenshots` app.js:553 | `#settings-auto` | Settings only | Tab | Yes | UI-010 |
| 15 | Suggest progress and cancel | n/a | `updateSuggestProgress` 1908, `suggestCancelBtn` 2125 | `#suggest-progress` | Floating panel while running | Tab | Yes | Covers the board header (UI-024) |
| 16 | LLM health / start / stop | `/api/llm/health`, `/start`, `/stop` | `refreshLLMStatus` 331, `performLLMControl` 339 | `#settings-llm-status`, `#settings-llm-action` | Settings only. No header indicator since commit 80f9915 | Tab | Yes | UI-003, UI-010 |
| 17 | Settings: provider / model / prune | `/api/settings` | app.js:2146-2287 | `#settings-menu` | Gear icon -> panel | Focus trap, Esc blocked while dirty | Full-height sheet | UI-019, UI-020 |
| 18 | Theme (System / Light / Dark) | n/a | `selectTheme` app.js:182 | `#theme-toggle` radio group | Settings only | Arrow keys | Yes | `cycleTheme` is dead (UI-038) |
| 19 | Tracked folders: add / remove | `POST /api/pick-folder`, settings | app.js:376-459 | `#add-folder-btn`, `#tracked-folders-list` | Settings, below the fold | Tab | Yes | UI-020 |
| 20 | Cleanup review: group, Dismiss, Select all, Queue N for Trash, Show next 5, Review selection | Spotlight usage (`usage.py`) | app.js:574-708 | `#cleanup-*` index.html:96-113 | Visible only when eligible cards exist; Dismiss cannot be undone | Tab | Yes | UI-016 |
| 21 | Similarity: "Identical" / "N similar" buttons | `similarity.py` (`matches`) | `syncSimilarBadges` app.js:1282 | Created in JS | **Not clickable by mouse** (UI-007) | Tab + Enter works | Same | UI-007 |
| 22 | Category hints ("Likely keep/trash" + left border) | `categorize.py` | `_applyCategoryHint` app.js:801 | Created in JS | Always visible | n/a | Yes | None |
| 23 | Sort | `?sort=` | `sortSelect` app.js:736 | `#sort-select` | Visible (labels broken, UI-002) | Native select | Yes | UI-002 |
| 24 | Scan again / Try again | `GET /api/screenshots` | `refreshScreenshots` app.js:475, buttons app.js:710 | `#refresh-btn`, `#refresh-sorted-btn`, `#retry-scan-btn` | Only in empty / all-sorted / error states | Tab | Yes | **No persistent rescan** (UI-009) |
| 25 | Source tag (`in: <folder>`) | `source` field | `makeCard` app.js:906 | `.source-tag` | Visible | n/a | Yes | Card aria-label leaks full path (UI-035) |
| 26 | Compact column switcher | n/a | `setCompactColumn` app.js:719 | `#column-switcher` | Only <=1024px | Buttons with `aria-pressed` | Yes | UI-014, UI-026 |
| 27 | Keyboard shortcuts | n/a | app.js:1850-1898 | none | No visible reference anywhere | n/a | n/a | UI-011 |
| 28 | Status / toast / banner | n/a | `announce` app.js:292 | `#status-msg`, `#toast-region`, `#feedback-banner` | Visible | n/a | Yes | UI-022, UI-023 |
| 29 | Memory records, health probe | `GET /api/memory`, `GET /api/health` | not used | none | Backend-only by design (prune days is the only memory UI) | n/a | n/a | Informational |

---

## 2. Issues

Format: **ID / severity / category** - location - evidence - suggested fix.

### Stray text

**UI-001 / high / stray-text** - `templates/index.html:30`
`<span ... id="sort-summary">Loading\u2026</span>` is plain HTML, so the six literal characters `\u2026` render on screen instead of an ellipsis. [live] visible at first paint and for the whole initial scan (`shots/22-1440-light-loading.png` shows `Loading\u2026`). [code] it is replaced by JS only after the first `updateCounts()`, so it also shows if the scan hangs.
Fix: write `…` or `&hellip;`.

**UI-002 / high / stray-text** - `templates/index.html:43-44`
`<option>Name (A\u2013Z)</option>` and `Name (Z\u2013A)`. [live] the accessibility tree lists the options as `"Name (A\u2013Z)"` and `"Name (Z\u2013A)"`. This is the primary sort control and the text is permanently wrong.
Fix: use `–` or `&ndash;`.

**UI-003 / medium / stray-text** - `src/ss_dcl/app.py:855`, `static/app.js:215`
"LiteRT server is not running - use the Start button above and try again." There is no Start button, and certainly not "above". The only control is "Start local AI" inside Settings. [live] this sentence appears three times at once in the offline state (app bar line, banner, toast: `shots/23-1440-light-llm-offline.png`). The backend string wins because `suggestBatch` prefers `h.error` (app.js:2032).
Fix: say "Open Settings and choose Start local AI" (or better, give the banner a "Start local AI" action, see UI-010).

**UI-004 / low / stray-text** - `tests/`, git history
The escapes are long-standing and were never caught. [code] `git log -S`: the sort-option escapes date from `3cbc21e` (2026-05-05) and `Loading\u2026` from `d163cc3` (2026-09-16). At `4f33e7b` the template also carried `\u2014` in two `data-tooltip` values and in an sr-only span, plus `Loading screenshots\u2026`; those disappeared only because the surrounding markup was later rewritten (`80f9915`, the board-state panels), not because anyone fixed the pattern. No test asserts that the served template is free of literal `\u`: a search of `tests/` and `tools/` for `u2026|u2013|Loading` finds nothing relevant.
Fix: add one test that fails on `\\u[0-9a-f]{4}` in `templates/index.html`.

**UI-005 / low / inconsistent-style** - `static/app.js:242,250,398,402,958-970`, `templates/index.html:176,199,248,316`
Icons are a mix of the local SVG set (app.js:765) and text glyphs: ✓ ✕ ✎ in the suggestion badge, ✕ and ⚠ in tracked folders, × for close buttons, and an emoji ✨ (`&#10024;`) on Suggest All. The comment at app.js:762 says the design deliberately avoids "emoji glyph carrying meaning". [live] glyph widths and weights differ between the badge buttons and the SVG icon buttons (`shots/04-...`, `shots/02-...`). No mojibake was found: every non-ASCII character in the template, JS, CSS, and Python strings is intentional UTF-8.
Fix: move to the SVG icon helper and drop the emoji.

### Missing or unreachable controls

**UI-006 / high / missing-control** - `static/style.css:4040-4086` (duplicate rules at 1275 and 3816), `static/app.js:925-932`
On a card with a pending suggestion, the suggestion badge (`z-index: 6`) is laid over the hover action bar, and `.card:has(.suggestion-badge:hover) .card-actions` hides the bar while the badge is hovered. [live] at 1440x900: badge y=373-430, Keep/Trash y=360-388 (only the top ~12px is outside the badge), Preview/More y=394-422 (fully covered). `elementFromPoint` at the Preview and More centers returns `.suggestion-badge`. At 1024px the badge (y=424-481) fully covers Keep/Trash (y=438-466). Keyboard focus shows the same overlap (`shots/24-1440-light-card-focus.png`: no visible Keep/Trash). Result: a mouse user cannot reach Keep, Trash, Preview, or the "..." menu (Rename, Reveal) on any suggested card. They can still drag the card or use arrow keys.
Fix: lay the badge out in normal flow (below the meta, above the overlay) and keep the action bar in its own non-overlapping row, or stop hiding the action bar on badge hover.

**UI-007 / high / missing-control** - `static/style.css:4040-4062`, `static/app.js:1282-1322`
The similarity buttons ("Identical", "N similar") live in `.card-meta`, which is entirely inside the hover action bar's footprint. [live] all 8 similarity buttons in the fixture overlap the action bar region at 1440x900. With the card hovered, `elementFromPoint` at the "1 similar" button center returns `.btn-keep`. A real click on a "3 similar" button (DevTools click moves the pointer, so hover is active) only toggled that one card's selection (1 selected, expected 4) and never ran the similarity handler. The feature added in `fc2c716` is therefore not usable with a mouse.
Fix: same layout change as UI-006: reserve a non-overlapping row for badges or move the action bar to a toolbar that does not cover the meta strip.

**UI-008 / high / missing-control** - `static/app.js:1114`
`const overflow = isNew ? [renameBtn, revealBtn] : [suggestBtn, renameBtn, revealBtn];` The comment above says "Unprocessed files get the one-click AI action", but the condition is inverted. [live] a `new` card's "..." menu holds only Rename and Reveal in Finder; the card has no `.btn-suggest`. [code] git history: before Phase 2 (`d163cc3`) the Suggest button was added `if (card.dataset.memoryStatus === "new")`. Keep and Trash cards never get Suggest. The only way to name a `new` card is Suggest All in Settings or auto-suggest.
Fix: show Suggest name when `isNew` (and, optionally, as a re-suggest for other statuses and in Keep/Trash).

**UI-009 / medium / missing-control** - `static/app.js:710`, `templates/index.html:126,132,138`
There is no persistent Scan/Refresh control. `refreshScreenshots` is bound only to the "Scan again" / "Try again" buttons in the empty, all-sorted, and error panels, and to Settings Save. [code] there is also no `visibilitychange`, focus, or polling refresh. New screenshots taken while the page is open need a manual reload unless the board happens to be empty or fully sorted.
Fix: add a Rescan icon button next to Sort (or a visibility-change rescan) and keep the panel buttons as secondary entry points.

**UI-010 / medium / missing-control** - `templates/index.html:262-289, 316`, `static/app.js:2129-2141, 2032`
All local-AI controls (Start/Stop server, Auto-suggest, Suggest All) live in Settings. Suggest All sits outside the scrolling form as a full-width pink strip with an emoji, formatted as a `.menu-item` left over from the removed header menu (commit `80f9915`). The offline error surfaces (status line, banner, toast) offer no action, so a user who hits "Local AI is offline" has to find Settings -> Local AI -> "Start local AI" on their own. [live] `shots/02-1440-light-settings.png`, `shots/23-...`.
Fix: put "Suggest names" next to Sort/Done (or in the batch bar), and give the offline banner a "Start local AI" action.

**UI-011 / medium / missing-control** - `static/app.js:1850-1898`, `static/style.css:4051-4062`
Discoverability: shortcuts (Left/Right move, Enter/Space select, Esc clear, Cmd/Ctrl+Z undo, double-click preview) are documented nowhere in the UI. Card actions are hover-or-focus-only (`opacity: 0; pointer-events: none` until hover), and there is no `@media (hover: none)` fallback. [code] `grep` finds no `hover: none`, `pointer: coarse`, `touchstart`, or `pointerdown`. Rename and Reveal need two clicks through the "..." menu.
Fix: add a keyboard-shortcut hint (tooltip or "?" popover) and an always-visible action row for coarse pointers.

**UI-012 / medium / a11y** - `static/app.js:985-1074`
The card overflow is `role="menu"`, and the comment says it "closes on selection, Escape, or an outside click". [live] pressing Escape with the menu open leaves it open (focus stays on the trigger). [code] there is no Escape handler for it (`closeCardOverflow` is only called from outside-click, trigger, item-click, and `setCardActions`), and no arrow-key navigation, which `role="menu"` requires.
Fix: add Escape (return focus to the trigger) and Up/Down roving focus, or drop `role="menu"`.

**UI-013 / medium / missing-control** - `templates/index.html:155-160`, `static/app.js:1333-1345, 1141`
The batch bar can only move to Keep or Trash. There is no "Unsorted" for cards selected in Keep/Trash, no "Suggest names" for the selection, and no "Select all". Undo is one entry per card (`moveCard` pushes per call), so undoing a 10-card batch needs 10 clicks. `docs/ui-inventory-phase0.md:103` says selection "supports click, shift-range, and Photos-style batch drag", but [code] there is no shift handling for selection (the only `shiftKey` use is the focus trap at app.js:1529).
Fix: add "Unsorted" and "Select all in column", make a batch a single undo entry, correct the doc.

**UI-014 / medium / layout** - `static/style.css:3545-3590, 4249+`, `static/app.js:719-732`
At <=1024px exactly one column has `display: flex`. [live] at 1024 `colKeep` and `colUnsorted` are `display: none` while Trash is shown. Cards stay `draggable`, but there is no drop target on screen, and the switcher buttons are not drop targets. There are no pointer or touch handlers, so a touch device has no gesture to move a card. This is where the swipe gesture belongs (see section 6).
Fix: do not rely on DnD below the breakpoint; add the swipe gesture or make the switcher tabs drop targets.

**UI-015 / low / missing-control** - `templates/index.html:180-200`, `static/app.js:1561`
The lightbox offers only previous/next, rename, Finder, and close. A user previewing a screenshot cannot Keep or Trash it, or accept a suggestion, without closing. Navigation uses `document.querySelectorAll(".card")`, which is DOM order (Keep, then cleanup group, then Unsorted, then Trash) and includes cards in columns that are hidden at compact widths, so "5 of 20" jumps between columns.
Fix: add Keep/Trash/Unsorted to the lightbox bar and restrict navigation to the current column.

**UI-016 / low / state** - `templates/index.html:99`, `static/app.js:697-702`
"Dismiss" hides the cleanup group for the page session with no way to bring it back (no "Show cleanup suggestions" control); `cleanupDismissed` resets only on a full reload. [code]
Fix: leave a small "Show cleanup suggestions" link where the group was.

**UI-017 / low / state** - `static/app.js:2304-2307`
When the card for an undo entry no longer exists (e.g. a restored `sessionStorage` entry for a file that disappeared), `performUndo` pushes the entry back and returns. The Undo button stays enabled and does nothing, forever. [code] (`undoStack` is restored from `sessionStorage` at app.js:10-13.)
Fix: drop unresolvable entries and continue to the next.

**UI-018 / low / a11y** - `static/app.js:1894-1897`
The global Cmd/Ctrl+Z handler calls `preventDefault()` and performs the board undo even when focus is in the rename input, lightbox rename input, or Settings fields, so text undo is hijacked. [code]
Fix: ignore the shortcut when `e.target` is an input, textarea, or select.

### Layout and state

**UI-019 / medium / layout** - `static/style.css:4400-4402`, `static/app.js:2210`
`.toast-region` has `z-index: 1200`, above the settings sheet (`z-index: 600`) and the modal overlay (`1100`). [live] at 800x700 and 1440 the "Settings have unsaved changes - save or close them from the panel" warning toast is drawn over the Close and Save buttons it tells the user to press (`shots/18-800-light-settings-dirty-escape.png`). Warning toasts last 6.5s or until dismissed.
Fix: dock toasts above the dialog footer (or move them to the top) while a dialog is open, or show the dirty warning inline in the footer.

**UI-020 / medium / layout** - `static/style.css:1612, 2533-2536`, `static/app.js:2186-2192`
The settings form scrolls (scrollHeight 935 vs clientHeight 571 at 1440x900) and Suggest All plus the footer take the rest of the panel, so Tracked folders, "+ Add folder", and Memory are below the fold with no visible scroll cue (`shots/02-...`). The form's `scrollTop` is not reset when the dialog reopens, so it opened mid-scroll at 800px (`shots/16-800-light-settings.png`, Appearance is cut off). The gap between the form and the Suggest All strip is dead space (28px at 800px).
Fix: reset `scrollTop` on open, move Suggest All into the form, add a section nav or collapsible sections.

**UI-021 / medium / layout** - `static/style.css:942, 3466`
`#status-msg` is in the flow of the app bar. [live] when it carries text the app bar grows from 60px to 72px and the whole board shifts down 12px (compare `shots/01-...` with `shots/20-...` and `shots/24-...`), then shifts back when the text clears.
Fix: reserve the line or move transient messages to the toast region only.

**UI-022 / medium / state** - `static/app.js:292-308`
`announce(..., { timeout: 0 })` never clears `#status-msg` and the error toast (timeout 0) never auto-dismisses. [live] after a forced scan error followed by a successful (empty) rescan, "Desktop is not readable" remained in the app bar and an error toast stayed on screen (`shots/21-1440-light-empty.png`). The offline message stayed in the app bar after the banner and toast were closed (`shots/24-...`).
Fix: clear `#status-msg` and matching toasts when the condition resolves (or on the next successful scan/health check).

**UI-023 / medium / a11y** - `static/app.js:292-308, 268-284`
One condition can be rendered up to four times: `#status-msg`, banner title/message, toast, and the board error panel (`shots/20-...`). Each is a live region (`role=status` / `alert`, `aria-live=polite`), so screen readers announce it repeatedly. `showFeedbackBanner` also calls `feedbackBannerClose.focus()`, moving focus away from the user's task on any persistent message, including background auto-suggest failures.
Fix: choose one surface per severity (toast for transient, banner for blocking) and do not move focus unless the banner is the result of a user action.

**UI-024 / medium / layout** - `static/style.css:2930, 2988, 4387-4389`
The feedback banner and the suggest-progress panel are `position: fixed; top: ...` and cover the column titles and the top row of cards. [live] banner hides the "UNSORTED" header (`shots/20-...`, `shots/23-...`); the progress panel covers header and first card row (`shots/28-1440-light-progress-batch-toast.png`).
Fix: dock both below the app bar in the layout flow, or anchor them to the bottom-left.

**UI-025 / medium / layout** - `static/style.css:1986, 2049`
`.lightbox-content` has `overflow: hidden` and `max-height: 90vh`. [live] at 1440x900 the bar is 98px tall at y=787-885 but its parent ends at y=855, so the bottom padding is cut off. In rename mode the bar grows to 162px, overlaps the image, and crops the top of the screenshot (the window title is gone in `shots/09-1440-light-lightbox-rename.png`).
Fix: size the image from the remaining height after the bar, or move the bar outside the clipped container.

**UI-026 / medium / layout** - `static/style.css:4249+`
At <=1024px the Keep/Trash trays render one full-width card per row. [live] 974x768 card in a 527px-high scroll container (`shots/27-1024-dark-trash-column.png`); `object-fit: cover` crops the left edge, and the filename and actions are below the fold.
Fix: use the same multi-column grid as Unsorted (or a compact list row) in the Keep and Trash tabs.

**UI-027 / low / layout** - `static/style.css:2112-2128`
`.modal` is `max-width: 380px`, narrower than a typical filename (37+ chars in mono). [live] `shots/11-1440-light-rename-modal.png`: the input is scrolled so the first character is cut ("creenshot ...").
Fix: widen the rename modal (about 520px) or use a multi-line/auto-size field.

**UI-028 / low / state** - `static/style.css:1427-1446`, `static/app.js:1642-1680`
The card filename tooltip is `max-width: 220px; white-space: nowrap; text-overflow: ellipsis`, so it truncates the same filename it exists to reveal ("Screenshot 2026-03-02 at 1..."). [live] `shots/12-1440-dark-board.png`. It also gets stuck: when cards are removed while hovered (rescan, error), `mouseleave` never fires and the tooltip stays on screen (`shots/20-...`, `shots/21-...`).
Fix: allow wrapping or a wider max-width; hide it on `refreshScreenshots`.

**UI-029 / low / layout** - `static/style.css:2222-2256, 3207+`
`[data-tooltip]::after` always opens downward. [live] the tooltip for the bottom-docked batch bar is 83x62px (text wraps) and is clipped by the viewport edge (`shots/25-1440-light-batch-tooltip.png`). The "Settings" tooltip also stays visible after the dialog closes because focus returns to the trigger with `:focus-visible` (`shots/04-...`, `shots/28-...`). The tooltip on the "..." button is cropped by the neighboring card (`shots/06-...`).
Fix: flip upward near the viewport bottom and suppress after programmatic focus restore.

**UI-030 / low / inconsistent-style** - `static/style.css:1719, 2585`, `templates/index.html:267-283`
[live] in Settings, field labels (Provider, Model, Auto-suggest on scan, Prune memory after) are uppercase bold at about the same weight as the section headings (Appearance, Local AI), so hierarchy is flat. The auto-suggest checkbox is a 36px square (rule at line 1719 says 18px; the later rule at 2585 wins). Provider is a select with one option. "Start local AI" wraps onto two lines at 1440 (`shots/02-...`).
Fix: lighter, sentence-case field labels; use a styled switch (the unused `.switch` CSS already exists).

### Inconsistent style (design language)

**UI-031 / medium / inconsistent-style** - `static/style.css:2181-2191, 1416-1424`
`.modal-confirm` is hard-wired to the destructive Trash red (`--action-trash`), and the rule is last in the cascade on purpose (comment at 2181). [live] computed background `rgb(180, 71, 47)` on `#modal-confirm` (correct), `#rename-confirm` (Rename) and the enabled `#settings-save` (Save). `.rename-confirm-btn` (primary purple) is overridden. A routine Rename or Save looks as dangerous as moving files to the Trash.
Fix: split `.modal-confirm` into `.btn-primary` (Rename, Save) and `.btn-danger` (Move to Trash).

**UI-032 / medium / inconsistent-style** - see section 3
Over 14 button families with different font size (11 / 12 / 14px), weight (400 / 600), radius (4 / 7 / 8 / 999px), border treatment, and height. [live] computed styles are tabulated in section 3. Same action, different treatment: "Reveal in Finder" (card menu) vs "Finder" (lightbox, `index.html:192`); Preview = eye icon (card) vs "Preview" label (cleanup card); Cancel = full-width outline (`.suggest-cancel-btn`) vs filled grey (`.modal-cancel`); "Scan again" is `.state-action` while "Dismiss" and "Show next 5" are `.cleanup-quiet`.
Fix: consolidate to the set proposed in section 3.

**UI-033 / medium / inconsistent-style** - `templates/index.html:180-322`, `static/app.js:1538, 1605-1606, 2227-2231, 2387-2389, 2453-2454`
Four different overlay shells:

| Surface | Shell | Title element | Dismiss paths | Footer |
| --- | --- | --- | --- | --- |
| Confirm | centered `.modal`, blurred scrim | `<p class="modal-title">` | Esc, Cancel; backdrop deliberately **not** (app.js:2453) | Cancel / Move to Trash (red) |
| Rename | same `.modal` | `<p class="modal-title">` | Esc, Cancel, backdrop | Cancel / Rename (red) |
| Settings | anchored popover on desktop, full-height sheet on compact, **no scrim**, own sticky header and footer | `<p class="settings-menu-title">` + `<h2>` sections | x button, Close, outside click, Esc (blocked when dirty) | Close / Save (red) |
| Lightbox | full-bleed dark layer with its own dark button style | sr-only `<span>` | x, backdrop, Esc | none |

Close affordances differ (x in settings and lightbox, none in modals), titles are `<p>` not headings, and the confirm modal has no filename list or item count beyond the title.
Fix: one modal shell (section 3).

**UI-034 / medium / a11y** - `static/style.css:4087-4170, 3934-3960`
Contrast. [live] measured on `shots/05-...`: the Preview (eye) icon is `#fbfbfb` on a `#b1b0ac` button, about 2.1:1 (WCAG 1.4.11 asks for 3:1 for UI components). The "..." button uses the same translucent style. The unselected `.card-select` circle is a 20% white fill with a 40% white border and the tick is `opacity: 0` until hover (`style.css:3960-3966`), so on light thumbnails there is no visible selection affordance (`shots/01-...`, `shots/05-...`). Button text is 11px at weight 600 in `.action-btn`, `.state-action`, `.tracked-add-btn`, `.text-btn`, `.suggest-cancel-btn`, and the lightbox buttons.
Fix: opaque (or darker scrim) icon buttons; a visible resting state for the select circle; minimum 12px button text.

**UI-035 / medium / a11y** - `templates/index.html:53, 190`, `static/app.js:839, 957-972, 1306`
Accessible-name problems. [live] a11y tree: Done is named "Move screenshots to trash" while its visible label is "Clean up 3" (label-in-name, WCAG 2.5.3). The suggestion buttons are named "✓", "✕", "✎" (the descriptions "Accept & rename" etc. are only `title`). `#lightbox-filename` is `role="button"` with `aria-label="Click to rename"`, which replaces the filename as its name. Tracked-folder card `aria-label` is `"<file> (<absolute path>)"`, e.g. `.../ss-dcl/.cache/ui-audit/Reference/Screenshots`. Similarity buttons have names of 200+ characters. Keep/Trash/Preview buttons are named just "Keep"/"Trash" with no filename. Column `<section role="list">` contains a header and a wrapper div between the list and its `listitem`s.
Fix: aria-labels that contain the visible text; use the folder basename in card labels; real `aria-label`s on badge buttons.

**UI-036 / low / inconsistent-style** - copy
The same action is called "Done" (disabled state), "Clean up N" (label), "Move screenshots to Trash" (tooltip), "Move to Trash" (confirm), "Queue N for Trash" (cleanup), and "Trash" (card/batch). Only the last moves a card, and only "Done"/"Move to Trash" actually trashes files.
Fix: one verb pair, e.g. "Trash" (queue) and "Empty queue / Move N to Trash" (commit).

### Dead code, docs, hygiene

**UI-037 / medium / dead-code** - `static/style.css`
Two generations of CSS are stacked (first pass lines 1-3220, second pass from the "App shell and application bar" block at line 3371, plus a "Phase 3" block at 4381). [code] 99 selector blocks are defined 2+ times (`.column` 4x; `.kanban`, `.modal-overlay`, `.toast-region`, `.lightbox-bar-top`, `.card.selected` 3x). 10 `!important`s. 39 classes have no matching DOM or JS (dynamic names such as `badge-keep/trash`, `toast-*`, `status-*`, `feedback-*` were excluded):
`badge-ai badge-disabled badge-warning btn-accept btn-danger btn-reject btn-suggest-edit btn-warning card-action-row card-actions-triage field-error field-help field-label header-center header-left header-right header-settings-btn header-theme-btn icon-btn-sm input-error input-mono menu-item-primary menu-item-shortcut menu-separator menu-suggest-all-btn popover-desc popover-eyebrow popover-heading popover-status popover-title segmented segmented-item settings-field-help settings-field-row switch switch-track theme-choice-group theme-icon-dark theme-icon-light`.
Notably `.btn.btn-keep`, `.btn.btn-trash`, `.btn.btn-danger`, and `.btn.btn-warning` exist only as dead definitions; the live Keep/Trash buttons are `.action-btn.btn-keep` / `.batch-btn`. Conversely, `.activity-panel`, `.appbar-status`, `.lightbox-prev`, `.lightbox-next`, `.settings-section-advanced`, `.cleanup-source`, `.batch-bar` are used in markup with no rule (harmless hooks).
Fix: delete dead rules, merge the two generations, then re-baseline screenshots.

**UI-038 / low / dead-code** - `static/app.js:161, 359, 820, 1615-1617`, `tests/test_frontend.py:518`, `tests/test_theme_foundation.py:270`
Unused JS: `cycleTheme()` (superseded by the radio group; pinned by two tests), `fileKeyForFile()`, `_clearCategoryHint()`, `void THEME_KEY`, and the unused `payload` variable in `revealInFinder`. [code] (counted references: 1 each.)
Fix: remove along with the tests that pin them.

**UI-039 / low / dead-code** - `templates/index.html:11,12,324,325`
Cache-busting strings `theme-init.js?v=1`, `style.css?v=7`, `ss_dcl_pure.js?v=5`, `app.js?v=6` were last bumped in `d163cc3` (2026-09-16) while the files changed again in `80f9915`, `50fa683`, `fc2c716`, `8ccc9ab`. [code] This is harmless today because `SEND_FILE_MAX_AGE_DEFAULT = 0` (`app.py:77`), but the numbers no longer mean anything, and `docs/ui-inventory-phase0.md:92` lists `v=5/4/4`.
Fix: drop the query strings (max-age is 0) or derive them from the file mtime.

**UI-040 / medium / dead-code** - `docs/ui-inventory-phase0.md`, `AGENTS.md`
Docs that no longer match the DOM:

- `ui-inventory-phase0.md:52,214` Settings is "(⚙)"; it is an SVG sliders icon.
- `:73` lists `.card-actions-triage`, which exists only in dead CSS.
- `:85` lightbox list omits `#lightbox-prev`, `#lightbox-next`, `#lightbox-position`, `#lightbox-rename-btn`.
- `:98` the theme "toggle... cycles auto -> dark -> light" is now a three-button radio group.
- `:103` "shift-range" selection does not exist.
- `:107` loading/empty omits `#all-sorted-msg`, `#scan-error-msg`; nothing on the cleanup group, similarity buttons, compact switcher, toast region, feedback banner, or the "..." overflow menu.
- `:213` "click Rename on a card in Trash" - Rename is inside the "..." menu.
- `:215` "`▶ Start LLM` is the state" - no such control; it is "Start local AI" in Settings.
- `AGENTS.md` "Theme toggle: ☀/☾ button cycles" (UI is the Settings radio group); "Single-file backend" and the file list omit `sources.py`, `server.py`, `llm.py`, `settings.py`, `thumbs.py`, `categorize.py`, `static/theme-init.js`, `static/ss_dcl_pure.js`; the endpoint table omits `POST /api/pick-folder` and the `source` parameter on image/thumb/reveal/rename; `GET /api/settings` omits `tracked_folders`; "UI is simple enough (395 lines)" while `app.js` is 2,531 lines; "Rename modal: Rename button" (it is in the overflow menu).
`tests/test_frontend.py::test_phase0_inventory_surface_ids_exist` guards ids only, so this prose can drift silently.
Fix: refresh both docs as part of the phase that touches each surface.

**UI-041 / low / state** - `src/ss_dcl/app.py` (`/api/llm/health`), no favicon
[live] Console shows two errors on every load with the LLM offline: `GET /favicon.ico` 404 and `GET /api/llm/health` 503 (the expected "offline" answer is returned as an HTTP error, so it is logged as a failed resource). No CSP violations and no JS exceptions were logged (the CSP `style-src 'self'` is respected: all dynamic styles go through the CSSOM).
Fix: add a favicon (or `<link rel="icon" href="data:,">`) and return 200 with `{ok: false}` for the probe.

---

## 3. Design-language inventory

### 3.1 Current button families ([live] computed styles, light theme, 1440)

| Family (classes) | Used for | Size / type | Look |
| --- | --- | --- | --- |
| `.btn .btn-primary .btn-sm` | Done / "Clean up N" | 36px, 14px/600, r8 | solid purple |
| `.btn .btn-primary` | Cleanup "Queue N for Trash" | auto, 14px/600, r8 | solid purple (moves to Trash, not red) |
| `.btn .btn-ghost .btn-sm` | Undo | 36px, 14px/600 | transparent |
| `.icon-btn` | Settings gear, Settings x | 36px, r8 | neutral fill |
| `.modal-btn .modal-cancel` | Cancel / Close | 14px/600, r8, no border | neutral fill |
| `.modal-btn .modal-confirm` | Move to Trash, Rename, Save | 14px/600, r8 | **always red** (UI-031) |
| `.batch-btn .batch-keep / .batch-trash / .batch-clear` | Batch bar | 12px/600, r8 | green / red / neutral |
| `.action-btn .btn-keep / .btn-trash / .btn-undo` | Card overlay | 28px, 11px/600, r8 | green / red / grey, white 1px border |
| `.action-btn .btn-preview / .btn-more` (icon-only) | Card overlay | 28px, 11px/600 | translucent white (UI-034) |
| `.action-btn .btn-rename / .btn-reveal / .btn-suggest` | "..." menu items | 11px/600 | menu rows |
| `.suggestion-badge-btn .accept / .reject / .edit` | Suggestion strip | 24px, r4, glyph text | green / amber / purple squares |
| `.similarity-badge` | "N similar" | 26px, 11px/400, r8 | outlined |
| `.cleanup-quiet` | Dismiss, Show next 5, Review selection | 12px/**400**, r8 | outlined cream |
| `.state-action` | Scan again / Try again | 11px/600, r8 | outlined |
| `.tracked-add-btn` | + Add folder | 11px/600 | dashed outline |
| `.text-btn` | Start/Stop local AI | 11px/600, r0 | purple text |
| `.menu-item .menu-item-ai` | Suggest All | 14px/600 | pink strip, emoji |
| `.suggest-cancel-btn` | Cancel suggestions | 11px/600 | full-width outline |
| `.compact-switcher-item` | Keep / Unsorted / Trash tabs | 12px/600 | outlined segmented |
| `.theme-choice` | System / Light / Dark | 12px/600, r7 | segmented radio |
| `.lightbox-nav / -rename-btn / -reveal-btn / -close` | Lightbox | 11px/600, r8 | translucent white on dark |
| `.card-select` | Selection circle | 24px circle | faint (UI-034) |
| `.feedback-dismiss`, `.toast-dismiss`, `.tracked-folder-remove` | Close x | glyph text | bare |

### 3.2 Proposed consolidated set

One `.btn` base (`font: 600 14px`, radius 8, 1px border, 150ms transition, `:focus-visible` ring) and size modifiers.

| Role | Class | Replaces | Rule |
| --- | --- | --- | --- |
| Primary | `.btn-primary` | Done, Queue N, Rename, Save, Suggest | One per surface. Solid brand purple |
| Secondary | `.btn-secondary` | modal-cancel, state-action, cleanup-quiet (Dismiss/Next), tracked-add, suggest-cancel, similarity-badge, lightbox text buttons | Neutral outlined; same height and font as primary |
| Quiet | `.btn-quiet` | text-btn, btn-ghost, Dismiss, "Show cleanup suggestions" | No border until hover |
| Danger | `.btn-danger` | modal-confirm (Move to Trash), batch Trash, card Trash | Red, **only** for trash / destructive; never Rename or Save |
| Positive (tone modifier) | `.btn[data-tone="keep"]` | batch Keep, card Keep | Green tint on Primary or Secondary |
| Icon | `.btn-icon` (36 / 28 / 24px) | icon-btn, btn-preview, btn-more, close x, card-select, dismiss, remove | Always `aria-label`, SVG only, >=3:1 contrast |

Sizes: `md` 36px (appbar, dialogs), `sm` 28px (card bar, batch bar, compact), minimum text 12px. Labels: one name per action everywhere (UI-032, UI-036).

### 3.3 Current modal chrome and proposed shell

Current shells are in UI-033. Proposed single shell `.dialog`:

- Structure: `header` (`<h2 id>` title, optional description, `.btn-icon` close x), `body`, sticky `footer` (Secondary left, Primary or Danger right).
- Scrim: one blurred scrim for every dialog, including Settings (as a right-side sheet variant `.dialog--sheet`) and the lightbox (`.dialog--media`, dark surface, same close button).
- Dismissal: Esc and x always; backdrop click for non-destructive dialogs only; the destructive confirm lists the number of files and keeps backdrop dismissal off. Dirty forms (Settings) ask before closing.
- Focus: the existing `openOverlay` / `closeOverlay` / `trapOverlayFocus` contract (app.js:1488-1540) is already shared and should be the one implementation.
- Feedback: errors inline in the footer (not toasts above the dialog, UI-019).

---

## 4. Proposed phased fix order

| Phase | Scope | Issues |
| --- | --- | --- |
| 1. Stray text | Fix the three `\u` literals, the stale "Start button above" copy, add a guard test | UI-001, 002, 003, 004 |
| 2. Reachability | Rework the card layout so badges and the action bar do not overlap; fix the Suggest condition; persistent Rescan; surface Suggest All / Start AI where the user is; Escape on the overflow menu; make batch undo atomic | UI-006, 007, 008, 009, 010, 012, 013, 017, 018 |
| 3. State and layout | Clear stale status, dedupe messages and live regions, stop focus stealing, stop toasts covering dialogs, reserve the status line, fix lightbox bar, compact Keep/Trash grids, settings scroll and open position, tooltip fixes | UI-019 - 029, 041 |
| 4. Button consolidation | Introduce the six button roles in section 3.2; delete dead CSS (merge the two stylesheet generations); fix contrast and accessible names; unify labels | UI-005, 030, 031, 032, 034, 035, 036, 037, 038 |
| 5. Modal convergence | Migrate confirm, rename, settings, lightbox onto the one shell and one dismissal policy | UI-033, 015, 016, 027 |
| 6. Swipe | Add the gesture (section 5) on top of the consolidated card and `moveCard` | UI-011, 014 |
| 7. Docs and tests | Refresh `ui-inventory-phase0.md` and `AGENTS.md`; update the tests that pin removed code (`cycleTheme`); re-baseline `docs/assets/ui-baseline`; drop the cache-bust query strings | UI-039, 040 |

Run the baseline capture (`tools/capture_ui_baseline.py`) at the end of phases 2, 4, and 5.

---

## 5. Swipe gesture: where it hooks in

Not designed in depth; just the integration points ([code]).

- **Attach point:** `makeCard()` (app.js:825) already ends with `attachDrag`, `attachPreview`, `attachKeyboard`, `attachTooltip`, `attachSelect` (app.js:934-939). A new `attachSwipe(card)` belongs there, built on Pointer Events (`pointerdown/move/up/cancel`) with `touch-action: pan-y` on `.card`.
- **Commit action:** call `moveCard(card, "keep" | "trash")` (app.js:1127). It already handles decisions, undo stack, DOM move, counts, persistence, and focus, so swipe inherits undo and `/api/state` for free. For a selected card, route through `batchMove` as the drop handler does (app.js:1221-1226).
- **Direction mapping needs a decision.** The existing keyboard shortcut is Left = Keep and Right = Trash (app.js:1863-1864), which matches the board geometry (Keep column on the left, Trash on the right). The owner's example (left = trash, right = keep) is the opposite. Pick one and use it in both places and in the visual cue.
- **Conflict with HTML5 DnD:** cards are `draggable="true"` and have a 350ms click-suppression window after dragstart (`_lastDragStart`, app.js:1235-1240). Restrict swipe to `pointerType === "touch"` (or `pen`), or disable `draggable` while a touch swipe is in progress.
- **Compact mode:** below 1024px only one column is visible (UI-014), so swipe is the only way to triage without opening the overlay; the Keep/Trash tabs in the switcher show the counts that should animate.
- **Visual feedback:** reuse the `.dragging` / `.drag-over` vocabulary or add `.swiping-keep` / `.swiping-trash` with the existing tokens (`--action-keep`, `--action-trash`).
- **Special cases:** cleanup cards intentionally have no Trash button (app.js:1110), so swipe-right there should be "queue" or disabled; suggestion cards (UI-006) need the layout fix first; the lightbox could take the same swipe for prev/next (`_lightboxNavigate`, app.js:1576).
- **Prerequisite:** UI-006/007/011 (hover-gated and overlapping controls) should be fixed first, because the gesture needs an always-visible, non-overlapping card surface.

---

## 6. Items checked and found fine

- `getElementById` / `querySelector` ids in `app.js` all exist in the template or are created before use. The 12 template ids with no JS or CSS reference are `aria-labelledby` / `aria-describedby` targets.
- `static/app.js:2465` `"Moving to Trash…"` is inside a JS string, so the escape is correct.
- No double-escaped entities (`&amp;amp;`), mojibake, or stray HTML entities anywhere in the template, JS, CSS `content:` strings, or Python response strings; the em dashes and ellipses in JS/Python strings are literal UTF-8.
- Console: no JS exceptions and no CSP violations (see UI-041 for the two network errors).
- Theme: light, dark, and system modes all render consistently; dark mode reproduced every layout issue above, with no additional contrast failures found in the surfaces sampled.
- Keyboard: focus trap, focus return, and Esc order across the lightbox, confirm, rename, and settings dialogs work as coded.
- Compact switcher, empty/loading/error panels, batch bar placement, and the confirm modal render correctly at 800, 1024, 1280, and 1440 widths apart from the issues listed.
