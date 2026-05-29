# AGENTS.md

AI agent context file for the Screenshot Declutterer repository.

## Project Summary

Local macOS web tool that scans `~/Desktop` for `Screenshot*.png` files, presents them in a Kanban-style drag-and-drop interface (Keep / Unsorted / Trash), and trashes selected files via the native macOS Trash API. Everything runs locally — no data leaves the machine.

## Architecture

Single-file backend + single-file frontend. Zero build steps.

```
src/ss_dcl/app.py        Flask backend (all routes, scanning, thumbnails, state, trash)
static/app.js            Frontend JS (Kanban, drag-and-drop, undo, lightbox, modal)
static/style.css         All CSS (Kanban layout, cards, lightbox, modal)
templates/index.html     SPA shell — three-column layout + lightbox + confirm modal
tests/conftest.py        Shared pytest fixtures and helpers
tests/test_routes_*.py   Route-specific test files
tests/test_edge_cases.py Edge case tests
tests/test_frontend.py   Frontend integration tests
```

## Design Decisions

- **Flask over heavier frameworks** — single-user local tool, no need for async/ORMs
- **Vanilla JS, no React/Vue** — UI is simple enough (395 lines); a framework would add a build step for no benefit
- **No build step** — static files served directly by Flask; no transpilation, bundling, or minification
- **Port 5002** — avoids conflict with macOS AirPlay Receiver on port 5000
- **send2trash** — files go to native macOS Trash (recoverable), never permanently deleted
- **State as JSON file** (`~/.ss-dcl/state.json`) — no database needed; single-user tool with no concurrent access
- **Thumbnail caching** — generated on-demand with Pillow, cached at `~/.cache/ss-dcl/thumbs/`, staleness checked via `st_mtime`
- **Thumbnail fallback** — if Pillow fails to generate, falls back to serving the full image
- **No auth/CORS/CSRF** — localhost-only tool, single user

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Serve SPA |
| GET | `/api/screenshots?sort=<mode>` | List screenshots (sort: name, name_desc, date, date_desc, size, size_desc) |
| GET | `/api/image/<filename>` | Serve full-size image (cache: 1h) |
| GET | `/api/thumb/<filename>` | Serve thumbnail 400x300 max (cache: 24h), falls back to full image |
| GET | `/api/state` | Get persisted decisions `{decisions: {filename: "keep"|"trash"}}` |
| PUT | `/api/state` | Save decisions state |
| POST | `/api/done` | Trash files — body `{filenames: [...]}`. Returns 207 on partial failure with per-file errors |

All filename-accepting routes validate against path traversal: bare name check (`filename == Path(filename).name`) + resolved path must be within `~/Desktop`.

## Frontend Architecture

All in `static/app.js` (~395 lines):

- **Global state**: `decisions` (Map), `undoStack` (Array), `totalCards`, `currentSort`
- **Entry**: `init()` → loads saved state → `loadScreenshots()` → creates cards via `makeCard()`
- **Core logic**: `moveCard(card, column)` updates decisions map, undo stack, DOM, and persists state
- **Drag-and-drop**: Native HTML5 Drag and Drop API. Cards `draggable="true"`. Columns are drop targets with visual feedback via CSS classes (`dragging`, `drag-over`)
- **Kanban layout**: Three columns — Keep (22% width), Unsorted (CSS Grid, flex:1), Trash (22% width)
- **Undo**: `performUndo()` pops from stack, reverses the move
- **Lightbox**: Double-click or Preview button → full-size overlay. Escape or backdrop click closes
- **Confirm modal**: Done button → modal with trash count → POST `/api/done`

## Runtime Paths

| Constant | Value |
|----------|-------|
| DESKTOP | `~/Desktop` |
| SCREENSHOT_GLOB | `Screenshot*.png` |
| THUMB_DIR | `~/.cache/ss-dcl/thumbs/` |
| STATE_FILE | `~/.ss-dcl/state.json` |
| THUMB_SIZE | `(400, 300)` |

## Dependencies

**Runtime:** Flask >= 3.0, Pillow >= 10.0, send2trash >= 1.8
**Dev:** pytest >= 8.0, Ruff >= 0.11, Pyright >= 1.1, pre-commit >= 4.0, pytest-cov >= 5.0, pip-audit >= 0.5

## Testing

- Framework: pytest with Flask test client
- Fixture: `client(tmp_path, monkeypatch)` — temp dir as fake Desktop, patches `DESKTOP`, `THUMB_DIR`, `STATE_FILE`
- `send2trash` always mocked to avoid actually trashing files
- Helper `_make_png()` creates valid minimal PNGs in-memory
- ~61 tests across focused test files covering all routes, sorting, path traversal, state round-trip, partial failures, edge cases

## Tooling Config

- **Ruff**: target py39, line-length 100, rules: E, F, W, I, UP, B, SIM, RUF
- **Pyright**: pythonVersion 3.9, typeCheckingMode basic
- **pytest**: testpaths `["tests"]`, pythonpath `["src", "."]`
- **Pre-commit**: Ruff (lint+format), Pyright, pytest

## Key Gotchas

- **macOS-only** — relies on `Screenshot*.png` naming convention, `send2trash`, and `~/Desktop` path
- **Path traversal defense** — two-layer check: bare filename + resolved path within Desktop
- **207 Multi-Status** — `/api/done` returns 207 when some files succeed and some fail
- **Auto-open browser** — daemon thread opens browser after 1s delay; skipped during Werkzeug reloader
- **Non-recursive scan** — only top-level `~/Desktop` files, not subdirectories
- **Lazy loading** — card images use `loading="lazy"` and `decoding="async"`
