# Phase 0 — UI inventory and deterministic capture

Phase 0 of [`PLAN.md`](../PLAN.md) freezes what the current interface actually is before any
styling work starts: the DOM and state inventory below, a deterministic non-personal demo
fixture, the canonical viewports, and light/dark baseline images captured from that fixture.

Every capture runs against fixture data on a closed LLM port. No real Desktop file is read or
displayed, no real runtime state directory is touched, and no capture needs a language model.

## 1. Isolation: how a capture avoids real data

| Variable | Effect | Default when unset |
| --- | --- | --- |
| `SS_DCL_DESKTOP` | scan root (`ss_dcl.app.DESKTOP`, `ss_dcl.settings._DEFAULT_DESKTOP`) | `~/Desktop` |
| `SS_DCL_HOME` | runtime root for state, memory, settings, logs, thumbnails (`ss_dcl.paths`) | `$HOME` |
| `LITERT_BASE_URL` | LLM endpoint | `http://localhost:9379` |
| `SS_DCL_PORT` | port the app binds (auto-increments when taken) | `5002` |
| `SS_DCL_LOG_FILE` | rotating log file | `<runtime root>/.ss-dcl/app.log` |

`SS_DCL_HOME` is what makes the documentation flow safe. Everything the app writes on its own
behalf is derived from it in `src/ss_dcl/paths.py`:

```
<SS_DCL_HOME>/.ss-dcl/state.json      decisions
<SS_DCL_HOME>/.ss-dcl/memory.json     per-file status, suggestions, keywords
<SS_DCL_HOME>/.ss-dcl/settings.json   provider, prune age, tracked folders
<SS_DCL_HOME>/.ss-dcl/app.log         app log (SS_DCL_LOG_FILE overrides)
<SS_DCL_HOME>/.ss-dcl/litert.{pid,log}
<SS_DCL_HOME>/.cache/ss-dcl/thumbs/   thumbnail cache
```

Pointing that at a throwaway directory therefore leaves `~/.ss-dcl` and `~/.cache/ss-dcl`
untouched. Pair it with `SS_DCL_DESKTOP` or the app still scans the real `~/Desktop`: both are
required. The fixture tooling sets both, and points `LITERT_BASE_URL` at `http://127.0.0.1:1` (a
closed port) so the LLM-offline states reproduce without a server.

## 2. Current DOM inventory

The shell and every overlay live in `templates/index.html`; cards are built at runtime by
`makeCard()` in `static/app.js`.

### Application shell

| Surface | Elements |
| --- | --- |
| Product title | `<h1>Screenshot Declutterer</h1>` |
| LLM server control | `#llm-server-btn` (`hidden` until the first health verdict, then `▶ Start LLM` / `■ Stop LLM`) |
| Operational status | `#status-msg` (`role="status"`, `aria-live="polite"`) |
| Sort control | `#sort-select` (`date_desc`, `date`, `name`, `name_desc`) |
| Undo | `#undo-btn` (disabled until a move) |
| Done | `#done-btn` (disabled until something is in Trash) |
| Settings | `#settings-btn` (⚙) |

### Board

| Column | Containers |
| --- | --- |
| Keep | `#col-keep[data-column=keep]`, `#cards-keep`, `#count-keep` |
| Unsorted | `#col-unsorted[data-column=unsorted]`, `#cards-unsorted`, `#count-unsorted`, `#loading-msg`, `#empty-msg` |
| Trash | `#col-trash[data-column=trash]`, `#cards-trash`, `#count-trash` |

### Screenshot card (runtime)

```
article.card[role=listitem][draggable=true][tabindex=0]
  dataset: filename, source, fingerprint, memoryStatus, suggestedName, suggestedCategory
  img                       /api/thumb/<name>?source=<source>, loading=lazy, decoding=async
  span.source-tag           only when source != "Desktop"; text "in: <folder name>"
  div.suggestion-badge      only when memoryStatus == "suggested" and suggestedName is set
    span.suggestion-badge-name
    div.suggestion-badge-actions > button.suggestion-badge-btn.{accept,reject,edit}
  div.card-actions          .card-actions-triage when the card is in Unsorted
    .btn-keep .btn-trash .btn-suggest .btn-rename .btn-preview .btn-reveal .btn-undo
```

State classes on the card: `.selected`, `.category-hint-keep`, `.category-hint-trash`,
`.dragging`; the column under a drag gets `.drag-over`.

### Overlays and system surfaces

| Surface | Elements |
| --- | --- |
| Batch bar | `#batch-bar[hidden]`, `#batch-count`, `#batch-keep-btn`, `#batch-trash-btn`, `#batch-clear-btn` |
| Filename tooltip | `#card-tooltip[aria-hidden]` |
| Lightbox | `#lightbox[hidden]`, `.lightbox-backdrop`, `#lightbox-img`, `#lightbox-filename`, `#lightbox-reveal-btn`, `#lightbox-rename-input`, `#lightbox-rename-error`, `#lightbox-close` |
| Trash confirmation | `#confirm-modal[hidden]`, `#modal-title`, `#modal-cancel`, `#modal-confirm` |
| Rename dialog | `#rename-modal[hidden]`, `#rename-title`, `#rename-input`, `#rename-error`, `#rename-cancel`, `#rename-confirm` |
| Suggestion progress | `#suggest-progress[hidden]`, `#suggest-progress-fill`, `#suggest-progress-text`, `#suggest-cancel-btn` |
| Settings panel | `#settings-menu[hidden]`, `#settings-provider`, `#settings-model`, `#settings-auto`, `#settings-prune-age`, `#theme-toggle`, `#tracked-folders-list`, `#add-folder-btn`, `#tracked-folders-error`, `#suggest-all-btn`, `#settings-cancel`, `#settings-save` |

Static assets are cache-busted with query strings in `templates/index.html`
(`style.css?v=5`, `ss_dcl_pure.js?v=4`, `app.js?v=4`); Phase 5 owns bumping them.

## 3. State inventory

| State | Representation |
| --- | --- |
| Theme | `data-theme="dark"` present or absent on `<html>`; mode in `localStorage["ss-dcl-theme"]` (`auto` \| `dark` \| `light`); `auto` follows `prefers-color-scheme`; the toggle lives inside the settings panel and cycles auto → dark → light |
| Column membership | `decision_key(source, name)` → `"keep"` \| `"trash"` in `state.json`; no entry means Unsorted. Desktop keys are bare filenames, tracked folders use `<absolute path>\|<name>` |
| Memory status | `new`, `suggested`, `renamed`, `ignored`, `trashed` (`src/ss_dcl/memory.py`) |
| Suggestion badge | `memoryStatus == "suggested"` with a `suggestedName` |
| Category hint | `suggestedCategory` recomputed per scan from accepted-history keywords; `keep`/`trash` only |
| Selection | `.selected` cards + visible `#batch-bar`; supports click, shift-range, and Photos-style batch drag |
| Drag and drop | `.dragging` on the card(s), `.drag-over` on the hovered column |
| Sort | `name`, `name_desc`, `date`, `date_desc` (default `date_desc` on initial load) |
| LLM server | hidden → disabled probe → `▶ Start LLM` (offline) / `■ Stop LLM` (running) |
| Loading / empty | `#loading-msg` visible while scanning, `#empty-msg` when no source yields files |
| Progress | `#suggest-progress` with fill width and `n of m` text; cancellable |
| Feedback | `#status-msg` copy, plus `207` partial-failure counts after Done |

## 4. Canonical viewports

| Viewport | Role |
| --- | --- |
| 1440×900 | primary (default for every documented state) |
| 1280×800 | secondary |
| 1024×768 | compact |

Captures use device pixel ratio 2, so the PNGs are 2880×1800 and friends.

## 5. Required states and how the fixture reproduces them

| Required state | Fixture evidence |
| --- | --- |
| unsorted | 13 cards with no decision entry |
| kept | 4 cards decided `keep` |
| trashed | 3 cards decided `trash` |
| suggested name | 2 cards with memory status `suggested` and a `suggested_name` |
| category hint | 12 keyword-carrying cards (7 lean `keep`, 5 lean `trash`) recomputed by `/api/screenshots` |
| multi-select | 13 unsorted cards, any two of which can be selected |
| LLM offline | every run uses `LITERT_BASE_URL=http://127.0.0.1:1` |
| tracked-folder source | 3 cards whose source is the workspace's `Reference/Screenshots` |

## 6. Deterministic demo fixture

`tools/demo_fixtures.py` renders 20 mock window images procedurally from a fixed seed
(`DEMO_SEED = 20260916`), assigns fixed filenames and mtimes, and writes the matching state,
memory, and settings files. Regenerating the same root produces byte-identical output.

```
<root>
  desktop/                          scanning root (source "Desktop")
  Reference/Screenshots/            one tracked-folder source
  home/.ss-dcl/state.json           keep/trash decisions
  home/.ss-dcl/memory.json          per-file status, suggestions, keywords
  home/.ss-dcl/settings.json        provider, prune age, tracked folders
  manifest.json                     slot → file, expected state, and coverage counts
```

```sh
uv run python tools/demo_fixtures.py --root .cache/ui-baseline-fixtures --force   # generate
uv run python tools/demo_fixtures.py --root .cache/ui-baseline-fixtures --verify   # check
uv run python tools/demo_fixtures.py --json --force                                # manifest
```

The manifest is the contract for everything downstream: `env` holds the exact environment to
export, and each entry in `files` carries the fingerprint, expected `status`,
`expected_category`, and Kanban `column` so a capture can assert what it should see.

## 7. Automated capture

`tools/capture_ui_baseline.py` drives a headless Chrome over the DevTools protocol, so it needs
no extra Python dependency beyond the project's own. It generates the fixture, serves the app on
the fixture's advertised port (5311), and writes one PNG per matrix entry.

```sh
uv run python tools/capture_ui_baseline.py --list                        # print the matrix
uv run python tools/capture_ui_baseline.py --out docs/assets/ui-baseline --force
uv run python tools/capture_ui_baseline.py --url http://127.0.0.1:5002   # existing server
uv run python tools/capture_ui_baseline.py --states board,settings --themes dark
```

The full matrix is 18 images: seven states (`board`, `hover`, `multi-select`, `lightbox`,
`confirm`, `rename`, `settings`) × two themes at 1440×900, plus `board` at 1280×800 and
1024×768 in both themes. Output lands in [`docs/assets/ui-baseline/`](assets/ui-baseline/)
together with a generated `README.md` index. Chrome is discovered from `SS_DCL_CHROME`, the
standard install locations, or `PATH`; without it the command exits 2 with a message and the
manual flow below still works.

The capture tool is a contributor convenience: nothing in CI renders Chrome. Capture is
byte-identical across runs on one machine, so the baseline can be re-derived and diffed rather
than trusted.

## 8. Manual screenshot flow

The same fixture works without Chrome automation, for example to inspect a state by hand or to
capture on a machine where the headless tool cannot run:

```sh
# 1. Generate the fixture (idempotent with --force).
uv run python tools/demo_fixtures.py --root .cache/ui-baseline-fixtures --force

# 2. Point the app at the fixture, never at your real Desktop or state.
export SS_DCL_DESKTOP="$PWD/.cache/ui-baseline-fixtures/desktop"
export SS_DCL_HOME="$PWD/.cache/ui-baseline-fixtures/home"
export LITERT_BASE_URL=http://127.0.0.1:1
export SS_DCL_PORT=5311

# 3. Run the app and open the printed URL.
uv run python -m ss_dcl.app
```

Then set the browser to the canonical viewport (for example 1440×900 with device pixel ratio 2)
and use the fixture data to reach each required state:

| State | How to reach it |
| --- | --- |
| board | load `/` — unsorted, kept, trashed, a suggestion badge, category hints, and the tracked-folder tag are already present |
| hover | hover an Unsorted card to reveal the action overlay |
| multi-select | click two or three Unsorted cards (the batch bar appears) |
| lightbox | double-click a card, or use Preview |
| confirm | click Done with cards in Trash |
| rename | click Rename on a card in Trash |
| settings | click ⚙ — the tracked folder is listed with the theme toggle |
| LLM offline | nothing to do: `▶ Start LLM` is the state, because the LLM URL is a closed port |
| dark theme | open ⚙ and cycle the theme toggle, or set `localStorage["ss-dcl-theme"] = "dark"` |

Unset the two variables (or close the shell) when finished; the fixture directory lives under
`.cache/`, which is gitignored.

## 9. What Phase 0 deliberately leaves alone

- `docs/assets/screenshot-sorted.png` and `docs/assets/screenshot-confirm.png` stay as they are;
  README media is Phase 5 work.
- No application CSS, markup, or JavaScript behaviour changes: the baseline must show the
  interface being revamped, not an improved one.
- No new runtime dependency. Both tools are plain Python scripts under `tools/`.

## 10. Tests that lock this down

- `tests/test_demo_fixtures.py` generates the fixture into a temporary directory, drives it
  through the Flask test client (list, sources, suggestions, hints, health, thumbnails, state
  round-trip), asserts byte-identical regeneration, and asserts the real `~/Desktop` and
  `~/.ss-dcl` are untouched by a full capture pass.
- `tests/test_frontend.py::test_phase0_inventory_surface_ids_exist` asserts every element id
  listed above is still present in the served shell, so this inventory cannot drift silently.
