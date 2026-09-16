# Screenshot Declutterer UI Revamp Plan

**Status:** Proposed<br>
**Research date:** 2026-09-16<br>
**Reference direction:** [Wispr Flow](https://wisprflow.ai/)<br>
**Delivery model:** Incremental, zero-build frontend redesign

## 1. Executive Summary

Revamp Screenshot Declutterer so it feels calm, editorial, warm, and native to macOS while
preserving the fast Keep / Unsorted / Trash workflow and the project's local-first character.
The visual direction should borrow Wispr Flow's design principles—soft neutrals, strong type
contrast, restrained color, generous spacing, gentle curves, and quiet motion—without copying
Wispr's logo, illustrations, marketing copy, or proprietary product identity.

The result should feel like a focused desktop utility rather than a generic Kanban board:

- the screenshot board remains the primary surface;
- the current functionality and backend API remain intact;
- cards become calmer and easier to scan;
- settings, dropdowns, confirmations, rename flows, progress UI, lightbox, and empty/error states
  share one coherent component system;
- light, dark, and system themes are complete and equally intentional;
- README screenshots are regenerated from deterministic, non-personal demo data;
- the app remains vanilla HTML, CSS, and JavaScript with no build step.

This is a visual and interaction-system project, not a feature-expansion project. New product
features such as duplicates, watch folders, and cleanup statistics should remain outside this
scope unless they are separately approved.

## 2. Goals

1. Give the application a distinctive, demo-ready visual identity inspired by Wispr Flow's
   current design language.
2. Make the Keep / Trash decision visually dominant and reduce competition from secondary
   actions.
3. Establish reusable semantic tokens and component patterns instead of accumulating one-off
   CSS rules.
4. Bring every overlay and state to the same level of polish as the main board.
5. Make light and dark themes deliberate variants of one system, not independent color swaps.
6. Preserve accessibility, keyboard operation, privacy, local-only operation, and the current
   zero-build architecture.
7. Produce new README media that represents the redesigned product accurately and safely.

## 3. Non-Goals

- Do not reproduce Wispr Flow pixel-for-pixel or use its protected brand assets.
- Do not add React, Vue, Tailwind, a bundler, or a frontend package manager.
- Do not change Flask route contracts or the memory/LLM architecture solely for presentation.
- Do not convert the app into a marketing site; the editorial influence should support utility.
- Do not hide or remove advanced functionality. Reorganize it and reduce its visual priority.
- Do not use personal screenshots in documentation or visual regression fixtures.

## 4. Research Findings

### 4.1 Sources reviewed

- [Wispr Flow home page](https://wisprflow.ai/) for the current palette, typography, navigation,
  spacing, buttons, surface treatment, and motion character.
- [Wispr Rebrand: Designing the future of voice](https://wisprflow.ai/rebrand) for the design
  intent behind the current system.
- [Wispr Flow media kit](https://wisprflow.ai/media-kit) for official logo and product-visual
  usage boundaries.
- [Designing a natural and useful voice interface](https://wisprflow.ai/post/designing-a-natural-and-useful-voice-interface)
  for the product principle that sophistication should remove friction rather than add visible
  complexity.
- [Wispr Flow desktop navigation documentation](https://docs.wisprflow.ai/articles/5096240724-navigating-the-wispr-flow-app-desktop-ios-and-android)
  for the structure of its desktop Hub, settings hierarchy, search, menus, and contextual actions.
- The current Screenshot Declutterer templates, styles, frontend behavior, test expectations,
  screenshots, and existing Phase 4 design notes in this repository.

### 4.2 Observed Wispr Flow visual system

The following values were verified from the current public site on 2026-09-16 and should be
treated as reference measurements, not values that must be copied exactly:

| Element | Observed reference |
|---|---|
| Main light background | warm cream, `rgb(255, 255, 235)` |
| Primary ink | near-black, `rgb(26, 26, 26)` |
| Deep accent | dark green, `rgb(3, 79, 70)` |
| Soft accent | pale lilac, `rgb(240, 215, 255)` |
| Body type | Figtree / modern humanist sans |
| Editorial type | EB Garamond / high-character serif |
| Primary CTA | pale lilac fill, dark 2px outline, 8px radius |
| Common geometry | soft 7–12px controls plus larger pill-shaped elements |
| Shadow strategy | minimal; separation comes from borders, tone, and spacing |

Wispr's own rebrand write-up emphasizes soft neutrals, restrained green accents, an editorial
serif paired with Figtree, gentle curves, generous whitespace, clear hierarchy, and slow,
subtle microinteractions. It explicitly frames the target as purposeful editorial design rather
than a dense SaaS dashboard. Those principles transfer well to Screenshot Declutterer, but the
product UI must remain denser and more operational than the marketing site.

### 4.3 Translation principles for this app

| Wispr principle | Screenshot Declutterer translation |
|---|---|
| Warm, quiet canvas | Warm neutral app background with softly differentiated columns |
| Editorial type contrast | Serif only for the product title, empty-state headline, and major modal titles; sans everywhere operational |
| Restraint | Keep and Trash are the only persistent high-emphasis actions |
| Soft geometry | Rounded shell, cards, panels, controls, and thumbnails from one radius scale |
| Color that breathes | Lilac for intelligent/local-AI actions, green for Keep/safe-positive, coral for Trash/destructive |
| Minimal shadow | Fine borders and tonal layering first; shadows reserved for raised overlays and dragged cards |
| Quiet motion | Short fades, small lifts, and card transitions; never constant decorative animation |
| Native-feeling workflow | Maintain keyboard shortcuts, predictable menus, and macOS-like focus/selection behavior |

### 4.4 Brand boundary

The implementation may use the reference's broad visual ideas and open-source typefaces, but it
must not use Wispr's logo, voice-wave mark, illustrations, screenshots, animations, branded copy,
or exact page compositions. Screenshot Declutterer should retain its own name and product story.
The visual goal is “same level of taste and family of principles,” not impersonation.

## 5. Current UI Inventory and Problems to Solve

### 5.1 Existing architecture

- `templates/index.html` contains the complete application shell and all overlays.
- `static/style.css` contains themes and every component style in one file.
- `static/app.js` owns card rendering, sorting, selection, drag-and-drop, lightbox, rename,
  suggestions, settings, theme behavior, progress, confirmation, and undo.
- `static/ss_dcl_pure.js` contains pure helpers used by the browser and JavaScript tests.
- `tests/test_frontend.py` checks DOM IDs, CSS markers, and JavaScript behavior by source content.
- `docs/assets/screenshot-sorted.png` and `docs/assets/screenshot-confirm.png` are the README media.

The redesign can remain frontend-only except for optional deterministic demo/screenshot tooling.

### 5.2 Surfaces that must be redesigned together

1. App background and top application bar.
2. Product identity/title and local-privacy indicator.
3. LLM server status/control.
4. Sort control and other dropdown/select fields.
5. Undo, Done, settings, and theme controls.
6. Keep, Unsorted, and Trash columns and their headers/counts.
7. Screenshot cards in both full and compact column layouts.
8. Hover, selected, focused, dragging, suggested, category-hint, and disabled card states.
9. Card action overlay and secondary-action hierarchy.
10. Suggestion badge with accept, dismiss, and edit actions.
11. Multi-select batch action bar.
12. Suggestion progress surface and cancellation state.
13. Filename tooltip and generic tooltips.
14. Full-image lightbox and inline lightbox rename.
15. Trash confirmation dialog.
16. Rename dialog and validation/error states.
17. Settings panel, form rows, toggles, tracked folders, and destructive/advanced settings.
18. Loading, empty, scan error, LLM offline, partial failure, and completion feedback.

### 5.3 Current experience issues

- The board reads as a conventional three-column Kanban instead of a focused macOS utility.
- The white/gray/blue palette is functional but generic and does not communicate a product
  personality.
- Card hover reveals up to six actions at similar emphasis, which competes with the central
  Keep/Trash decision.
- Side columns use narrow cards whose visual treatment feels disconnected from unsorted cards.
- The header mixes operational status, server control, sort, undo, completion, and settings in a
  single dense row without grouping.
- Native selects, inputs, button families, settings, and dialogs do not yet share a complete
  form/control specification.
- The theme system is a strong base, but token names are component-specific and cannot yet scale
  cleanly to richer surfaces or interaction states.
- Theme selection cycles through modes without clearly showing which mode is active.
- Overlays do not yet define one focus-management, dismissal, width, spacing, and button-order
  contract.
- Empty and loading states are primarily text and do not help the interface feel intentional.
- Documentation screenshots contain blurred personal-looking material and no dark-theme view.

## 6. Target Experience

### 6.1 Overall composition

At the primary 1440×900 desktop viewport, place the application inside a warm, softly padded
canvas instead of running every column edge-to-edge against the browser window.

- Use a compact floating app bar with the identity/status group on the left and workflow controls
  on the right.
- Put the sorting board inside a rounded, bordered workspace shell.
- Keep the three-column mental model, but reduce the feeling of three equal database columns:
  Unsorted is the active gallery, while Keep and Trash are quieter decision trays.
- Use spacing and tone—not heavy separators—to distinguish regions.
- Preserve a minimum usable viewport of approximately 1024×700 for a desktop browser window.
- Below the desktop threshold, switch to a deliberate compact layout rather than squeezing the
  three columns until controls overlap. The recommended compact treatment is a segmented
  Keep/Unsorted/Trash view with counts, while drag-and-drop remains available on larger screens.

### 6.2 Application bar

Left group:

- A simple project-owned mark or monogram may be designed later; do not copy Wispr's waveform.
- Product name in a restrained display serif.
- A small “On-device” status pill with a green status dot and tooltip explaining that screenshots
  remain local.
- LLM state becomes a compact status menu (`Ready`, `Stopped`, `Starting`, `Error`) rather than a
  large start/stop button in the product identity group.

Center/summary behavior:

- Replace transient center text with a stable progress statement such as `12 of 48 sorted` and a
  thin progress meter.
- Announcements and errors should appear as short-lived toasts or inline banners with an ARIA live
  region, not overwrite the core summary indefinitely.

Right group:

- Sort remains a native `<select>` for accessibility, styled as a quiet outlined control.
- Undo is an icon-plus-label secondary button while space allows.
- Done becomes contextual copy such as `Clean up 3` when trash contains items and remains visually
  quiet when disabled.
- Settings uses a real icon from a small locally shipped icon set or a platform-safe text label;
  do not rely on an emoji glyph.

### 6.3 Board and columns

- Workspace shell: one rounded outer border, subtle inner tonal regions, no heavy global shadow.
- Column headers: sentence case or small caps with clearer hierarchy; count badges use one neutral
  pattern plus semantic accent when nonzero.
- Unsorted: warm neutral gallery with responsive cards and a clear empty state.
- Keep: pale green-tinted tray using low-saturation color.
- Trash: pale coral-tinted tray; use red only for the destructive action and active count.
- Empty trays: compact illustrated/icon state is optional, but text and drop target must remain
  clear without decoration. Any illustration must be project-owned or generated, never copied.
- Drag-over: combine a tonal wash, inset outline, and text change; do not depend on color alone.

### 6.4 Screenshot cards

Card anatomy for Unsorted:

1. Thumbnail in a consistent aspect-ratio frame.
2. Bottom metadata strip with truncated filename and optional source label.
3. Optional semantic badge for AI suggestion or learned category.
4. Persistent selection affordance at top-left.
5. Primary Keep/Trash actions shown on hover/focus in a compact bottom bar.
6. Preview and an overflow menu for Rename, Reveal in Finder, and Suggest.

Card behavior:

- Hover adds a small lift and border emphasis, not a dark full-card scrim.
- Keyboard focus mirrors hover and exposes the same controls.
- Selection uses a high-contrast ring plus checked control and does not rely on blue alone.
- Suggested names render as a calm inline row with named buttons/tooltips rather than isolated
  colored glyphs.
- Category hints become a labeled micro-badge (`Likely keep` / `Likely trash`) or accessible icon
  and text; the border color may remain supplemental.
- Keep/Trash compact cards retain filename access and overflow actions instead of becoming image-
  only tiles.
- Drag ghosts keep the existing Photos-style stack but adopt the new radius, border, and count
  badge tokens.

### 6.5 Dropdowns, menus, and form controls

Use one control family across the sort field, provider field, settings inputs, tracked folders,
and future menus:

- 40px default control height; 36px compact variant where needed.
- 10px control radius, 1px semantic border, and strong `:focus-visible` ring.
- Native `<select>` behavior retained. Do not replace it with a custom listbox unless there is a
  tested keyboard/accessibility need that native controls cannot meet.
- Labels remain visible above controls; placeholders never replace labels.
- Help text sits below the relevant control and errors occupy the same reserved area to prevent
  layout jumps.
- Toggle rows use a proper checkbox/switch input with text label and optional description.
- Menus use 8px internal padding, 36px items, leading icon slot, shortcut slot, hover/active
  states, separators between action groups, and destructive red only for destructive actions.
- Menus close on Escape, outside click, or selection and restore focus to their trigger.

### 6.6 Settings redesign

Convert the current small dropdown into a roomy anchored panel on large screens and a centered or
full-height dialog on compact screens.

Recommended grouping:

- **Appearance:** segmented `System / Light / Dark` control.
- **Local AI:** provider, model, server status/control, auto-suggest, and Suggest All.
- **Sources:** Desktop plus tracked folders and Add folder.
- **Memory:** prune age with a concise explanation; visually mark it as advanced.

Panel requirements:

- 420–480px desktop width with a maximum viewport-safe height and internal scrolling.
- Sticky title row and footer actions when content scrolls.
- Clear section headings, descriptions, and dividers.
- Save is primary; Close/Cancel is secondary. Disable Save until values change.
- Show saving, saved, and validation states without closing unexpectedly.
- The LLM state must not be communicated only by button text.

### 6.7 Dialog system

Trash confirmation and rename should use one dialog foundation, preferably native `<dialog>` with
a documented fallback only if supported-browser constraints require it.

Shared contract:

- semantic title, optional description, content, and footer slots;
- `aria-labelledby`, `aria-describedby`, and modal behavior;
- focus enters at the least destructive useful control and returns to the trigger on close;
- Escape closes non-destructive dialogs;
- clicking the backdrop closes rename/settings only if doing so cannot lose unsaved edits;
- 16–20px radius, fine border, restrained shadow, and a soft backdrop blur where supported;
- one entry/exit transition disabled under `prefers-reduced-motion`;
- predictable button order across every dialog.

Trash confirmation:

- Include count, action summary, and the recoverable macOS Trash reassurance.
- Use warm coral for the destructive button instead of maximum-saturation red.
- Keep `Cancel` focused by default.

Rename dialog:

- Show the current thumbnail or compact file icon only if it does not increase load time.
- Visually separate the editable stem from the preserved extension.
- Validate inline and keep the dialog open on server errors.

### 6.8 Lightbox

- Use a near-black neutral rather than a pure black backdrop.
- Place filename, source, rename, Finder, navigation, and close actions in a floating glass-like
  toolbar that remains legible in both themes.
- Provide previous/next controls visually as well as through the current arrow-key behavior.
- Ensure controls do not cover important image content at smaller window heights.
- Inline rename should use the same field/button styles as the rename dialog.

### 6.9 Batch bar, progress, tooltips, and feedback

Batch bar:

- Present as a centered floating command bar with selection count, Keep, Trash, and Clear.
- Use a subtle entrance animation and reserve enough bottom space so it never covers cards.
- Expose keyboard shortcuts where applicable.

Suggestion progress:

- Present as a compact activity panel or inline banner near the app bar.
- Include processed/total count, current state, failure count, and Cancel.
- Ensure completion removes the progress surface after an accessible announcement.

Tooltips:

- Standardize delay, max width, padding, radius, typography, placement, and Escape dismissal.
- Never make a tooltip the only source of essential information.

Feedback:

- Add a reusable toast region for success, warning, error, and informational messages.
- Toasts pause on hover/focus, have a dismiss action when persistent, and remain screen-reader
  accessible.
- Partial trash failures should use a persistent error summary with per-file detail rather than a
  fleeting status line.

### 6.10 Empty, loading, and error states

Define intentional states for:

- first scan/loading;
- no screenshots found;
- all screenshots sorted;
- tracked folder missing;
- scan failed;
- LLM unavailable;
- suggestion partially failed;
- image/thumbnail failed;
- Desktop unavailable.

Each state should include a short title, one-sentence explanation, and only the relevant action.
Avoid large decorative illustrations unless a project-owned visual direction is explicitly chosen.

## 7. Design System Specification

### 7.1 Typography

Recommended stack:

- UI/body: locally bundled **Figtree** with system sans fallbacks.
- Editorial display: locally bundled **EB Garamond** for the app name and a few high-level titles.
- Filenames/technical values: existing SF Mono / Menlo / Consolas stack.

Both recommended families are available under open font licenses, but the implementation must
include their license files. Fonts should be self-hosted as WOFF2 files so the local-first app does
not contact Google Fonts or another CDN. If the extra assets are undesirable, use the macOS system
font for UI and Georgia as the display fallback; do not block the redesign on font loading.

Suggested scale:

| Token | Size / line height | Use |
|---|---|---|
| `--type-display-sm` | 24 / 28 | App name, empty-state title |
| `--type-title` | 18 / 24 | Dialog and panel titles |
| `--type-body` | 14 / 20 | General UI copy |
| `--type-label` | 12 / 16 | Field labels, column labels |
| `--type-caption` | 11 / 16 | Metadata, source tags, shortcuts |

Use sentence case for controls and headings. Reserve all-caps for very short eyebrow labels only.

### 7.2 Color tokens

Replace component-specific variables such as `--bg-card` and `--text-progress` with semantic
layers. The following palette is a proposed Screenshot Declutterer interpretation and must be
contrast-tested before finalization.

#### Light theme proposal

| Token | Proposed value | Purpose |
|---|---|---|
| `--surface-canvas` | `#F7F6E8` | Warm page canvas |
| `--surface-shell` | `#FBFAF2` | Main workspace |
| `--surface-raised` | `#FFFDF8` | Cards, menus, dialogs |
| `--surface-muted` | `#EFEEE2` | Quiet controls/side trays |
| `--ink-primary` | `#1A1A18` | Primary content |
| `--ink-secondary` | `#626158` | Supporting text |
| `--ink-muted` | `#858378` | Metadata/disabled text |
| `--border-subtle` | `#DEDCCE` | General boundaries |
| `--accent-ai` | `#E7D2F4` | Suggestions and local AI |
| `--accent-ai-strong` | `#76508D` | AI text/focus detail |
| `--accent-keep` | `#2F6A5D` | Keep and positive state |
| `--accent-keep-soft` | `#E0EEE8` | Keep tray/background |
| `--accent-trash` | `#C95844` | Trash/destructive state |
| `--accent-trash-soft` | `#F5E3DD` | Trash tray/background |
| `--focus-ring` | `#6E4E80` | Keyboard focus |

#### Dark theme proposal

| Token | Proposed value | Purpose |
|---|---|---|
| `--surface-canvas` | `#171815` | Page canvas |
| `--surface-shell` | `#1D1F1B` | Main workspace |
| `--surface-raised` | `#252721` | Cards, menus, dialogs |
| `--surface-muted` | `#20221E` | Quiet controls/side trays |
| `--ink-primary` | `#F4F2E7` | Primary content |
| `--ink-secondary` | `#C4C1B5` | Supporting text |
| `--ink-muted` | `#918F86` | Metadata/disabled text |
| `--border-subtle` | `#3A3C35` | General boundaries |
| `--accent-ai` | `#493C50` | Suggestions and local AI |
| `--accent-ai-strong` | `#D5B4E8` | AI text/focus detail |
| `--accent-keep` | `#8BC5B4` | Keep and positive state |
| `--accent-keep-soft` | `#213A33` | Keep tray/background |
| `--accent-trash` | `#EF8D78` | Trash/destructive state |
| `--accent-trash-soft` | `#422B27` | Trash tray/background |
| `--focus-ring` | `#D5B4E8` | Keyboard focus |

Add semantic aliases for hover, pressed, selected, disabled, overlay, scrim, and on-accent text.
Do not encode meaning into raw palette names in component CSS.

### 7.3 Spacing, radii, borders, and elevation

- Spacing scale: 4, 6, 8, 12, 16, 20, 24, 32, 40.
- Radius scale: 8px controls, 12px small cards, 16px panels/cards, 20px dialogs/workspace,
  full-pill for badges and segmented controls.
- Border: 1px default; 2px only for selected/focused emphasis.
- Elevation:
  - level 0: canvas and columns, no shadow;
  - level 1: cards, border plus extremely soft shadow;
  - level 2: menus/batch bar, contained shadow;
  - level 3: dialogs/lightbox toolbar, strongest but still diffused shadow.

### 7.4 Motion

- Hover/focus feedback: 120–160ms.
- Panels, menus, and toasts: 160–200ms.
- Dialogs and card moves: 180–240ms.
- Use opacity and small transforms; avoid animating layout dimensions where possible.
- Card sorting should visibly preserve object continuity between columns.
- Disable nonessential transitions and all decorative movement under
  `prefers-reduced-motion: reduce`.
- Never delay an operation to make an animation visible.

## 8. Theme Architecture

Keep the existing `auto`, `light`, and `dark` behavior but make it explicit and flash-free.

1. Rename CSS variables to the semantic system described above.
2. Set `color-scheme: light` / `dark` so native selects and scrollbars match the theme.
3. Move the initial theme read into `static/theme-init.js`, loaded synchronously in `<head>` from
   the same origin. This avoids a light-theme flash while respecting the current CSP prohibition
   on inline scripts.
4. Keep `data-theme="light|dark"` for explicit modes and a persisted preference value of
   `auto|light|dark`.
5. In auto mode, listen to `prefers-color-scheme` changes and update immediately.
6. Replace the cycling moon/sun button with a labeled three-option segmented control in Settings.
   A compact toolbar button may remain as a shortcut if its current state is visible in the
   tooltip/accessible name.
7. Test every overlay, disabled state, thumbnail failure, and native form control in both themes.
8. Update `<meta name="theme-color">` dynamically if it improves the browser chrome without
   affecting the local app experience.

## 9. Accessibility Requirements

- Maintain complete keyboard operation for cards, sorting, selection, undo, lightbox navigation,
  menus, and dialogs.
- Use `:focus-visible` consistently and never remove focus outlines without a replacement.
- Ensure interactive targets are at least 36×36px, aiming for 44×44px on primary actions.
- Meet WCAG 2.2 AA contrast for text, controls, focus indicators, and semantic states.
- Do not use color alone for Keep/Trash, category hints, selection, progress, or errors.
- Use native controls where they offer better platform and assistive-technology behavior.
- Add `aria-modal`, labelled/described dialogs, focus containment, and focus restoration.
- Make tooltip content supplementary and expose equivalent accessible names.
- Announce scan results, sort completion, suggestion progress, undo, rename, and trash outcomes
  through appropriately polite/assertive live regions.
- Preserve meaningful image alt text. Do not add the filename twice when visible adjacent text
  already provides the accessible name.
- Test 200% zoom and a compact desktop window without clipped actions or unreachable content.
- Respect reduced motion, increased contrast where feasible, and forced-colors mode.

## 10. Implementation Phases

Each phase should finish in a working state and be independently reviewable. Prefer small commits
or PRs using the repository's conventional commit format.

### Phase 0 — Baseline and deterministic fixtures

**Purpose:** Freeze expected behavior and create safe visual test data before changing styles.

Tasks:

- Record the current DOM/state inventory listed in Section 5.
- Add a deterministic demo fixture generator under `tools/` that creates representative,
  non-personal screenshot images and filenames in a temporary folder.
- Include states for unsorted, kept, trashed, suggested name, category hint, multi-select, LLM
  offline, and tracked-folder source.
- Define canonical screenshot viewports: 1440×900 primary, 1280×800 secondary, 1024×768 compact.
- Document the manual screenshot flow using `SS_DCL_DESKTOP` and an isolated temporary HOME/state
  directory.
- Capture baseline light and dark images for comparison, but do not replace README media yet.

Files:

- `tools/` new deterministic fixture/capture helper(s)
- `tests/test_frontend.py` or focused new UI-structure tests
- optional `docs/assets/ui-baseline/` if baseline images are intentionally checked in

Acceptance criteria:

- No real Desktop files are read or displayed during documentation capture.
- Existing tests remain green.
- Every required UI state can be reproduced without a running LLM.

### Phase 1 — Foundations: type, tokens, theme bootstrap, controls

**Purpose:** Build the design system before reshaping individual surfaces.

Tasks:

- Add locally hosted font files and license notices, or lock in the approved system-font fallback.
- Replace current component-specific theme variables with semantic tokens.
- Add spacing, type, radius, border, elevation, duration, and easing tokens.
- Add `color-scheme` and `static/theme-init.js` for flash-free theme initialization.
- Build shared base styles for buttons, icon buttons, badges, inputs, selects, checkboxes/switches,
  segmented controls, menus, and focus states.
- Define light/dark states for hover, pressed, selected, disabled, error, warning, and success.
- Add reduced-motion and forced-colors rules.

Files:

- `static/style.css`
- `static/theme-init.js` (new)
- `templates/index.html`
- `static/fonts/*` and license files if fonts are bundled
- `tests/test_frontend.py`

Acceptance criteria:

- No unapproved hardcoded UI colors remain outside the token declarations.
- Theme choice is applied before the body paints.
- Native controls render legibly in both modes.
- Keyboard focus is obvious on every interactive element.

### Phase 2 — App shell, workspace, columns, and cards

**Purpose:** Deliver the visible facelift while preserving the sorting model.

Tasks:

- Redesign the application bar and progress summary.
- Add the local/on-device status treatment and reorganize LLM state.
- Wrap the board in the new workspace shell.
- Restyle column proportions, headers, counts, trays, drop targets, and scroll areas.
- Rebuild card anatomy with metadata, primary actions, preview, overflow, suggestion row, source
  tag, and accessible category hint.
- Adapt compact Keep/Trash cards to the same component family.
- Update selected, focus, drag, drag-over, disabled, image-error, and suggested states.
- Update the fanned batch drag ghost to match new tokens.
- Add the compact window layout without altering desktop behavior.

Files:

- `templates/index.html`
- `static/style.css`
- `static/app.js`
- `static/ss_dcl_pure.js` only if new pure helpers are useful
- `tests/test_frontend.py`
- `tests/js/pure.test.js`

Acceptance criteria:

- Keep, Trash, drag-and-drop, multi-select, undo, suggestions, preview, rename, and Finder reveal
  retain current behavior.
- Primary actions are visually clearer than secondary actions.
- Hover and keyboard focus expose equivalent controls.
- At 1024×768, all primary actions remain reachable without horizontal page scrolling.

### Phase 3 — Menus, settings, dialogs, lightbox, and feedback

**Purpose:** Give every transient surface the same polish as the board.

Tasks:

- Implement the shared menu/popover contract.
- Reorganize Settings into Appearance, Local AI, Sources, and Memory sections.
- Replace the theme cycle with explicit System/Light/Dark selection.
- Implement shared dialog structure for Trash confirmation and Rename.
- Add focus containment/restoration and consistent Escape/backdrop behavior.
- Redesign the lightbox toolbar and visible previous/next navigation.
- Redesign the batch bar and suggestion progress surface.
- Standardize tooltips.
- Add reusable toast/banner feedback and migrate appropriate `statusMsg` messages.
- Create intentional loading, empty, offline, partial-failure, and all-sorted states.

Files:

- `templates/index.html`
- `static/style.css`
- `static/app.js`
- `tests/test_frontend.py`
- `tests/js/pure.test.js`

Acceptance criteria:

- Every overlay has correct focus entry, focus containment, Escape behavior, and focus restoration.
- Settings does not overflow at 1024×768 or 200% zoom.
- Errors remain visible until resolved/dismissed and are announced accessibly.
- No menu or dialog relies on hover to function.

### Phase 4 — Motion, responsive refinement, and resilience

**Purpose:** Add controlled polish and stabilize uncommon states.

Tasks:

- Add card-move continuity, menu/dialog transitions, toast motion, and subtle hover feedback.
- Verify and tune `prefers-reduced-motion` behavior.
- Test extreme filenames, 0/1/1000+ cards, long folder paths, missing thumbnails, failed images,
  delayed API responses, and partial trash failures.
- Validate window resizing while a menu/dialog/lightbox is open.
- Ensure fixed/floating UI does not overlap scrollbars, cards, or macOS browser chrome.
- Measure performance before and after; avoid blur/filter effects on large scrolling card grids if
  they cause frame drops.

Files:

- `static/style.css`
- `static/app.js`
- relevant frontend/performance tests

Acceptance criteria:

- No decorative animation runs in reduced-motion mode.
- Card scrolling and drag interactions remain smooth with the performance fixture.
- No layout shifts occur when errors, suggestions, or progress appear.

### Phase 5 — Verification and README media

**Purpose:** Prove the redesign and update public-facing documentation only after the UI is final.

Tasks:

- Run Ruff, Pyright, pytest, JavaScript tests, and relevant performance tests.
- Perform manual keyboard-only checks for the complete sorting flow.
- Check light/dark/system themes at all canonical viewports.
- Check contrast with an automated tool and manually inspect focus/semantic states.
- Capture fresh deterministic screenshots at 1440×900:
  - main board, light mode;
  - main board, dark mode;
  - trash confirmation or settings detail, whichever best demonstrates the system.
- Use GitHub's `<picture>` element with `prefers-color-scheme` sources for the main README hero so
  readers see an appropriate theme.
- Replace the outdated feature/roadmap text that still describes shipped AI rename work as planned.
- Update cache-busting query strings for changed static assets.

Files:

- `README.md`
- `docs/assets/screenshot-sorted-light.png` (new)
- `docs/assets/screenshot-sorted-dark.png` (new)
- `docs/assets/screenshot-confirm.png` or a renamed detail screenshot
- `templates/index.html` asset versions

Acceptance criteria:

- README screenshots contain no personal data and match the shipped UI.
- Both themes are represented without duplicating an excessively tall documentation section.
- README feature and roadmap claims match version 0.6.x behavior.
- Full test suite and required quality gates pass.

## 11. File-Level Change Map

| File | Expected change |
|---|---|
| `templates/index.html` | Reorganize app bar, card/overlay hooks, settings sections, dialogs, toast region, and theme bootstrap include |
| `static/style.css` | Replace ad hoc styles with semantic tokens and redesigned component/state system |
| `static/app.js` | Render new card anatomy; menu/dialog/toast behavior; explicit theme selection; focus management |
| `static/theme-init.js` | New early theme initialization script |
| `static/ss_dcl_pure.js` | Optional pure state/format helpers for testability |
| `static/fonts/*` | Optional locally hosted Figtree/EB Garamond WOFF2 files plus licenses |
| `tests/test_frontend.py` | Update brittle source assertions and add structural/accessibility contracts |
| `tests/js/pure.test.js` | Test any extracted theme/menu/card state helpers |
| `tools/*` | Deterministic demo data and documentation screenshot tooling |
| `docs/assets/*` | New light/dark README screenshots |
| `README.md` | New responsive screenshots and accurate feature/roadmap copy |

No backend route change is expected. If screenshot tooling needs a demo-data switch, prefer the
existing `SS_DCL_DESKTOP` environment override and isolated runtime paths over a production demo
endpoint.

## 12. Test and QA Matrix

### 12.1 Automated regression

- Existing Flask route suite remains unchanged and green.
- Update frontend source assertions to test durable contracts rather than exact row/gap CSS.
- Add DOM-contract tests for dialog labels/descriptions, live regions, menu triggers, and explicit
  theme controls.
- Add JavaScript unit coverage for theme resolution, progress copy, contextual Done labels, and
  any new state-to-class mapping.
- Keep CSP tests green; all scripts, fonts, and icons must be local/self-hosted.

### 12.2 Interaction matrix

| Flow | Mouse | Keyboard | Screen reader semantics |
|---|---:|---:|---:|
| Sort one card | Required | Required | Announced |
| Multi-select and batch move | Required | Required | Count announced |
| Drag one/many cards | Required | Alternate required | Drop result announced |
| Undo | Required | Cmd/Ctrl+Z | Result announced |
| Preview and navigate | Required | Enter/arrows/Escape | Dialog labelled |
| Rename | Required | Required | Error associated with field |
| Suggest/accept/reject | Required | Required | Progress/result announced |
| Settings and theme | Required | Required | Current selection exposed |
| Confirm trash | Required | Required | Safe default focus |

### 12.3 Visual matrix

- Themes: light, dark, auto-light, auto-dark.
- Viewports: 1440×900, 1280×800, 1024×768; optional 800px-wide resilience check.
- Zoom: 100%, 200%.
- States: loading, populated, all sorted, empty, selected, dragging, suggested, LLM offline,
  settings open, rename open/error, confirm open, progress active, toast/error, lightbox.
- Data stress: long filenames, long paths, many cards, missing image, multiple sources.

## 13. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| The redesign becomes a Wispr clone | Use only transferable principles; preserve product identity and unique workflow |
| Editorial styling reduces information density | Confine display type and large spacing to high-level surfaces; keep operational content compact |
| Warm palette lowers contrast | Contrast-test every semantic pair before locking tokens |
| Custom controls harm accessibility | Retain native selects/inputs and use progressive enhancement |
| Blur and shadows hurt grid performance | Prefer borders/solid tone; performance-test large batches before keeping effects |
| Settings redesign expands scope | Reorganize existing fields only; no new backend settings in this workstream |
| Frontend tests are brittle | Replace exact source-string checks with durable DOM/behavior assertions where practical |
| README captures leak personal data | Use deterministic generated fixtures and isolated runtime directories |
| Theme flash persists | Load a same-origin theme initializer in `<head>` before stylesheet-dependent rendering |

## 14. Definition of Done

The revamp is complete when:

- the board, cards, settings, selects, menus, dialogs, tooltips, progress, batch bar, lightbox, and
  empty/error states visibly belong to one system;
- light, dark, and system themes are complete, flash-free, and persist correctly;
- all current behaviors and API contracts remain functional;
- core flows work by mouse and keyboard, with appropriate announcements and focus management;
- text and control contrast meets WCAG 2.2 AA;
- the app remains local-first, zero-build, and free of remote runtime assets;
- the full automated test suite and project quality gates pass;
- the README uses fresh deterministic light/dark screenshots and accurately describes current
  functionality;
- final visual QA has been performed at every canonical viewport and state in Section 12.

## 15. Recommended Delivery Order

Implement in five focused review units:

1. deterministic fixtures + semantic tokens + theme bootstrap;
2. app shell + board + cards;
3. settings + menus + dialogs + lightbox;
4. feedback states + motion + accessibility/responsive hardening;
5. README screenshots + documentation cleanup + final QA.

Do not update the README screenshots early. They should be the final artifact after interaction,
theme, and responsive QA have stabilized.
