# AGENTS.md

AI agent context file for the Screenshot Declutterer repository.

## Project Summary

Local macOS web tool that scans `~/Desktop` for `Screenshot*.*` files (PNG, JPG, JPEG, TIFF, BMP), presents them in a Kanban-style drag-and-drop interface (Keep / Unsorted / Trash), and trashes selected files via the native macOS Trash API. Supports renaming files directly from the UI. Everything runs locally — no data leaves the machine.

## Architecture

Single-file backend + single-file frontend. Zero build steps.

```
src/ss_dcl/app.py        Flask backend (all routes, scanning, thumbnails, state, trash, rename, port detection)
src/ss_dcl/memory.py    Persistent file memory store (fingerprint-keyed identity, status tracking, atomic persistence)
static/app.js            Frontend JS (Kanban, drag-and-drop, undo, lightbox, rename modal, confirm modal)
static/style.css         All CSS (Kanban layout, cards, lightbox, rename modal, confirm modal)
templates/index.html     SPA shell — three-column layout + lightbox + rename modal + confirm modal
tests/conftest.py        Shared pytest fixtures and helpers
tests/test_routes_*.py   Route-specific test files (index, screenshots, image, thumb, state, done, rename, memory split into records/suggest/prune/persistence)
tests/test_memory.py     Memory store unit tests (fingerprint, CRUD, persistence, status transitions, edge cases)
tests/test_port_flexibility.py  Port auto-detection tests
tests/test_edge_cases.py Edge case tests
tests/test_frontend.py   Frontend integration tests
tests/test_logging.py    Logging config + request correlation tests
tests/test_litert_stub.py     LiteRT HTTP contract tests against an in-process stub server
tests/test_litert_integration.py  Opt-in real-LiteRT tests (SS_DCL_LITERT_URL)
tests/test_performance.py     Perf benchmarks, @pytest.mark.perf (scan/thumbs/suggest)
```

## Design Decisions

- **Flask over heavier frameworks** — single-user local tool, no need for async/ORMs
- **Vanilla JS, no React/Vue** — UI is simple enough (395 lines); a framework would add a build step for no benefit
- **No build step** — static files served directly by Flask; no transpilation, bundling, or minification
- **Port 5002 with auto-fallback** — avoids conflict with macOS AirPlay Receiver on port 5000; `_find_free_port()` auto-increments if occupied; override via `SS_DCL_PORT` env var
- **send2trash** — files go to native macOS Trash (recoverable), never permanently deleted
- **State as JSON file** (`~/.ss-dcl/state.json`) — no database needed; single-user tool with no concurrent access
- **Thumbnail caching** — generated on-demand with Pillow, cached at `~/.cache/ss-dcl/thumbs/<WxH>/` (size-keyed), staleness checked via `st_mtime`
- **Thumbnail fallback** — if Pillow fails to generate, falls back to serving the full image
- **No auth/CORS/CSRF** — localhost-only tool, single user

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Serve SPA |
| GET | `/api/screenshots?sort=<mode>` | List screenshots with fingerprint, memory_status, suggested_name, suggested_category enrichment (sort: name, name_desc, date, date_desc) |
| GET | `/api/image/<filename>` | Serve full-size image (cache: 1h) |
| GET | `/api/thumb/<filename>` | Serve thumbnail 800x600 max (cache: 24h), falls back to full image |
| GET | `/api/state` | Get persisted decisions `{decisions: {filename: "keep"|"trash"}}` |
| PUT | `/api/state` | Save decisions state |
| POST | `/api/done` | Trash files — body `{filenames: [...]}`. Updates memory with `trashed` status. Returns 207 on partial failure with per-file errors |
| POST | `/api/rename` | Rename a file — body `{old_name, new_name}`. Updates state, thumbnail, memory, and clears suggested_category hint. Returns 409 on conflict |
| POST | `/api/reveal` | Reveal a file in Finder (macOS) — body `{filename}`. Runs `open -R` fire-and-forget; path-traversal guarded. Returns 400 off-macOS, 404 if missing |
| GET | `/api/memory` | Get all persisted memory records `{files: {fingerprint: {status, suggested_name, last_updated}}}` |
| POST | `/api/suggest-names` | Generate AI filename suggestions — body `{fingerprints: [...]}`. Returns `{suggestions: {fp: name}, failures: [fp]}`. LiteRT provider only; uses `gemma4-e2b` by default |
| GET | `/api/llm/health` | LiteRT reachability probe (`/v1/models`). Returns `{ok, provider, error}`; 503 when down |
| GET | `/api/health` | Liveness probe `{ok, version, desktop_scanable, memory_records}`; 503 when Desktop unavailable |
| POST | `/api/llm/start` | Spawn the LiteRT server as a detached subprocess. Resolves `LITERT_SERVE_CMD` via PATH → `~/litert-lm/.venv/bin/litert-lm` fallback, logs to `~/.ss-dcl/litert.log`, records ownership in `LITERT_PIDFILE`, polls `/v1/models` until ready (30s). 502 if spawn/ready fails |
| POST | `/api/llm/stop` | Kill only the PID recorded in `LITERT_PIDFILE` (ownership rule — never a server the user started). 409 when no pidfile, 403 for a foreign PID |
| POST | `/api/accept-suggestion` | Accept suggestion & rename file — body `{fingerprint}`. Handles name conflicts (appends `-2`) |
| POST | `/api/reject-suggestion` | Dismiss suggestion — body `{fingerprint}`. Marks memory status as `"ignored"` |
| GET | `/api/settings` | Get config `{llm_provider, llm_model, auto_suggest, prune_max_age_days}` |
| PUT | `/api/settings` | Save config — body `{llm_provider?, llm_model?, auto_suggest?, prune_max_age_days?}` |

All filename-accepting routes validate against path traversal: bare name check (`filename == Path(filename).name`) + resolved path must be within `~/Desktop`.

## Frontend Architecture

All in `static/app.js`:

- **Global state**: `decisions` (Map), `undoStack` (Array), `selectedCards` (Set), `totalCards`, `currentSort`
- **Entry**: `init()` → loads saved state → `loadScreenshots()` → creates cards via `makeCard()`
- **Core logic**: `moveCard(card, column)` updates decisions map, undo stack, DOM, and persists state
- **Drag-and-drop**: Native HTML5 Drag and Drop API. Cards `draggable="true"`. Columns are drop targets with visual feedback via CSS classes (`dragging`, `drag-over`). Dragging a selected card attaches a Photos-style fanned stack of the whole selection to the cursor (`buildBatchDragGhost()` — composite canvas + `setDragImage`); visual only, drop still batch-moves
- **Kanban layout**: Three columns — Keep (22% width), Unsorted (CSS Grid, flex:1), Trash (22% width)
- **Undo**: `performUndo()` pops from stack, reverses the move
- **Lightbox**: Double-click or Preview button → full-size overlay. Escape or backdrop click closes
- **Confirm modal**: Done button → modal with trash count → POST `/api/done`
- **Rename modal**: Rename button → modal with text input → POST `/api/rename`. Updates card dataset filename, state, thumbnail, and clears category hint
- **Theme toggle**: ☀/☾ button cycles auto/dark/light; persisted in localStorage; follows system preference in auto mode
- **Category hints**: Colored left border (green=keep, red=trash) when auto-categorization has sufficient signal; cleared on accept/reject/rename

## Runtime Paths

| Constant | Value |
|----------|-------|
| DESKTOP | `~/Desktop` |
| SCREENSHOT_GLOB | `Screenshot*.*` (filtered by SUPPORTED_IMAGE_EXTENSION) |
| THUMB_DIR | `~/.cache/ss-dcl/thumbs/<WxH>/` (keyed by current THUMB_SIZE) |
| STATE_FILE | `~/.ss-dcl/state.json` |
| MEMORY_FILE | `~/.ss-dcl/memory.json` |
| SETTINGS_FILE | `~/.ss-dcl/settings.json` |
| APP_LOG_FILE | `~/.ss-dcl/app.log` (env `SS_DCL_LOG_FILE`; rotating, 1MB × 3) |
| THUMB_SIZE | `(800, 600)` |
| LITERT_BASE_URL | `http://localhost:9379` (env `LITERT_BASE_URL`) |
| LITERT_SERVE_CMD | `litert-lm serve` (env `LITERT_SERVE_CMD`; PATH → venv fallback) |
| LITERT_PIDFILE | `~/.ss-dcl/litert.pid` |
| LITERT_LOG_FILE | `~/.ss-dcl/litert.log` |

## Logging

- Configured at import time in `ss_dcl/logging_config.py` (console + rotating file handler) — `__main__` has no `basicConfig` anymore
- Every log record carries a `request_id` (12-hex contextvar, also returned as `X-Request-ID` header); access log line per request: `ACCESS <METHOD> <path> -> <status> (<ms>)`
- Named subsystem loggers (app.py never uses `__name__`, which is `__main__` when run directly): `ss_dcl.http` (ACCESS middleware), `ss_dcl.files` (scan/refresh/prune/thumbs), `ss_dcl.llm` (LLM routes + llm.py), `ss_dcl.app` (lifecycle/trash/rename/state), plus `ss_dcl.memory/server/settings/thumbs/categorize`
- werkzeug per-request access lines are suppressed (`_QuietRequestHandler` in app.py — it embeds its own timestamp and duplicates the `ss_dcl.http` ACCESS line); werkzeug errors still log

## Dependencies

**Runtime:** Flask >= 3.0, Pillow >= 10.0, send2trash >= 1.8
**Dev:** pytest >= 8.0, Ruff >= 0.11, Pyright >= 1.1, pre-commit >= 4.0, pytest-cov >= 5.0, pip-audit >= 0.5

## Testing

- Framework: pytest with Flask test client
- Fixture: `client(tmp_path, monkeypatch)` — temp dir as fake Desktop, patches `DESKTOP`, `THUMB_DIR`, `STATE_FILE`
- `send2trash` always mocked to avoid actually trashing files
- Helper `_make_png()` creates valid minimal PNGs in-memory
- ~332 tests across focused test files covering all routes, sorting, path traversal, state round-trip, partial failures, rename, port flexibility, edge cases, LLM suggest/accept/reject flows, pruning, dark mode, auto-categorization, LLM retry, LiteRT HTTP contract (stub server), health endpoint, logging/correlation
- `@pytest.mark.perf` benchmarks (scan/thumbnails/suggest, `uv run pytest -m perf`) and `@pytest.mark.integration` opt-in tests (real LiteRT, `SS_DCL_LITERT_URL=... uv run pytest -m integration`) are deselected by default

## Tooling Config

`pyproject.toml` is the single source of truth for tooling config; the summary below mirrors it (checked at 0.5.0).

- **Ruff**: target py310, line-length 100, rules: E, F, W, I, UP, B, SIM, RUF
- **Pyright**: pythonVersion 3.10, typeCheckingMode basic, include src/tests/tools
- **pytest**: testpaths `["tests"]`, pythonpath `["src"]`, coverage gate `--cov-fail-under=85`
- **Pre-commit**: Ruff (lint+format), Pyright, pytest

## Key Gotchas

- **macOS-only** — relies on `Screenshot*.png` naming convention, `send2trash`, and `~/Desktop` path
- **Multi-format** — scans for PNG, JPG, JPEG, TIFF, BMP files matching `Screenshot*.*`
- **Path traversal defense** — two-layer check: bare filename + resolved path within Desktop
- **207 Multi-Status** — `/api/done` returns 207 when some files succeed and some fail
- **Auto-open browser** — daemon thread opens browser after 1s delay; skipped during Werkzeug reloader
- **Non-recursive scan** — only top-level `~/Desktop` files, not subdirectories
- **Lazy loading** — card images use `loading="lazy"` and `decoding="async"`
- **Rename** — POST `/api/rename` validates both old and new names, checks for conflicts (409), moves thumbnails, updates state file
