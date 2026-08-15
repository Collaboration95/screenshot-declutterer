# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.6.0] - 2026-08-14

### Added

- LiteRT-LM on-device LLM provider — runs a local vision-language model for screenshot rename suggestions, replacing the cloud Ollama backend entirely; model selected in Settings (default `gemma4-e2b`) (#78)
- Managed LiteRT server lifecycle — `/api/llm/start` spawns `litert-lm serve` as a detached subprocess with PID ownership tracking, `/api/llm/stop` kills only owned servers, `/api/llm/health` liveness probe (#78)
- LiteRT evaluation tooling — screenshot-rename and OCR-to-filename prompts plus an evaluation framework and FE-018 benchmark in `tools/` (#78)
- Structured logging — import-time config, rotating app log file (`~/.ss-dcl/app.log`, 1MB × 3), request correlation IDs (`X-Request-ID`) and per-request access lines (#85)
- `GET /api/health` — liveness probe returning version, desktop scanability, and memory record count; 503 when Desktop is unavailable (#86)
- Security hardening headers — `Referrer-Policy` and `Permissions-Policy` (#96)
- Python 3.12/3.13 added to the CI matrix; platform-independent steps moved to a Linux job (#89, #90)
- `ruff format --check` gate in CI alongside lint (#87)
- pytest coverage gate in CI — `--cov-fail-under=85` (#88)
- JS unit tests — node:test coverage for `batchFanLayout`, `pathName`, `computeCounts`, `chunked` (A-14 / #92)
- Performance benchmarks — `@pytest.mark.perf` for scan/thumbnail/suggest paths (A-16 / #94)
- LiteRT HTTP contract tests against an in-process stub server (A-17 / #95)

### Changed

- Python package is now pip-installable — proper `[build-system]` and import layout, no more `src.`-prefixed imports (#97)
- `app.py` monolith split into focused modules — `server.py`, `llm.py`, `settings.py`, `thumbs.py`, `logging_config.py`, `categorize.py` (#98)
- `get_screenshots()` hoists the state read out of the per-file loop and indexes memory records — O(F×D×R) category scoring eliminated (#79)
- Thumbnail generation no longer blocks request threads on the 2-worker executor (#80)
- Suggest pipeline now runs with bounded backend parallelism and larger chunks instead of fully serial (`chunkSize=1`) (#81)
- Pyright scope widened to include `tests/` and `tools/` (#91)
- `test_routes_memory.py` (1474 lines) split into records/suggest/prune/persistence test files (#93)
- Dead code removed from `MemoryStore` (`get_unprocessed`/`remove`/`get_status`/`count`) (#99)
- Duplicated rename/state/thumbnail logic across `/api/rename` and `/api/accept-suggestion` consolidated (#101)

### Removed

- Ollama provider — LiteRT-LM is now the only LLM backend; `GET /api/ollama/health` replaced by `/api/llm/health` (breaking) (#78)

### Fixed

- `/api/done` no longer wipes state decisions for files that failed to trash — 207 partial-failure now preserves the surviving decisions (#82)
- Negative `prune_max_age_days` rejected server-side (validated 1–730) — no more mass memory pruning from a bad setting (#83)
- Card thumbnail `alt` text no longer double-escaped (#84)
- AGENTS.md tooling config synced to pyproject.toml (py310) (#100)

## [0.5.0] - 2026-08-11

### Added

- Multi-select + batch triage — click cards to select (blue ring + checkmark), floating batch bar moves the whole selection to Keep/Trash, dragging a selected card moves all selected; undo stays per-card (#69)
- Reveal in Finder — `POST /api/reveal` runs `open -R` on macOS (fire-and-forget, path-traversal guarded); Finder button on card actions and in the lightbox (#71)
- Empty-column drop hints — faint dashed "Drop here to keep/trash" placeholders inside empty side columns, dark-mode aware (#72)
- Photos-style batch drag ghost — dragging a selected card fans the selection's thumbnails out on the cursor (composite canvas + `setDragImage`, capped at 6 tiles with a `+N` badge), visual only (#74)
- GitHub Actions CI pipeline — ruff + pyright + pytest + pip-audit on push/PR, matrix over Python 3.10/3.11 on macOS runners (#75)

### Changed

- Python 3.10+ is now required so the supported dependency set can receive current security fixes.

### Removed

- Keyboard-driven triage (FE-007) removed from the backlog indefinitely

### Fixed

- Batch selection now survives drag-and-drop and batch Keep/Trash — the moved cards stay selected until the user explicitly deselects (Escape / ✕ / re-sort / Done) (#76)

## [0.4.0] - 2026-08-05

### Added

- Memory store wired into the app — screenshots get a fingerprint + `memory_status` tracked across sessions; cards expose fingerprint/memory-status data attributes (#64, #65)
- LLM-powered smart rename (Phase 3) — per-card `✨ Suggest` and batch `✨ Suggest All` with progress bar + cancel, suggestion badges with accept/reject/edit; `/api/suggest-names`, `/api/accept-suggestion`, `/api/reject-suggestion` (#66)
- Auto-categorization — keyword-based category hints (green keep / red trash) computed from your past decisions (#67)
- Dark mode — ☀/☾ toggle cycling auto/dark/light, persisted in localStorage, follows system preference (#67)
- Settings UI — LLM provider/model, auto-suggest, prune-max-age; persisted to `~/.ss-dcl/settings.json` with type validation (#67)
- Memory pruning — stale memory records garbage-collected after a configurable age (default 90 days) (#67)
- `GET /api/ollama/health` — liveness probe used by the Ollama circuit breaker (#68)
- LLM evaluation tooling — screenshot-rename and OCR-to-filename prompts plus an evaluation framework (`tools/`)
- Release/UAT process documented in `RELEASING.md`

### Changed

- Ollama suggest retries are now classified — connection-refused, DNS failures, and HTTP 4xx fail fast (no futile retries); only transient errors (timeouts, resets, 429, 5xx) are retried (#68)
- "Suggest All" performs a pre-flight Ollama health check and aborts before any per-file calls when the server is unreachable, instead of grinding through every file (#68)

### Fixed

- LLM suggestion flow: original file extension preserved (#1), clear error surfaced when Ollama is unreachable (#6), robust name sanitization (#7), accept-suggestion input validated (#4), stale suggestion badges removed after edits (#3)
- Non-functional MLX provider option removed from settings (#5)

## [0.3.0] - 2026-06-02

### Added

- Persistent file memory store (`src/ss_dcl/memory.py`) — tracks screenshot identity across sessions using metadata fingerprints (`"{name}|{size}"`) instead of content hashing, requiring zero file I/O (#63)
- `MemoryStore` class with CRUD operations, status lifecycle tracking (`new → suggested → renamed/ignored/trashed`), and atomic JSON persistence
- `FileRecord` dataclass with extensible `meta` field for future LLM categorization and clustering features
- `compute_fingerprint()` — stable identity from filename + file size (already available via `stat()`)
- `atomic_write()` — shared utility for crash-safe file writes (imported by app.py)
- `prune_stale()` — maintenance method to garbage-collect orphaned memory entries
- Design document at `docs/design-llm-rename-prerequisites.md` outlining the full 4-phase LLM integration plan
- 60 new unit tests for the memory store covering CRUD, status transitions, persistence, edge cases, and corruption recovery

## [0.2.0] - 2026-06-02

### Added

- Inline rename bar in lightbox — click filename below the preview image to edit, with iOS-style text selection up to the file extension (#62)
- Card tooltip overlay — hover over any card to see the filename overlaid on the bottom edge (#62)
- Design document for FE-010 at `docs/design-fe010-inline-rename.md`

### Fixed

- Rename bar no longer shrinks to half width when clicking to edit — bar width is pinned before swapping to input (#62)
- Double-fire of rename API call on Enter key (blur race condition) — guarded with disabled/hidden/lightbox state check (#62)
- Blur handler no longer triggers rename when lightbox is closed while editing (#62)
- Card thumbnail `img.src` now updates after rename in both lightbox and rename modal paths — was returning 404 for old filename (#62)
- Screen readers now announce rename errors via `role="alert"` on the error element (#62)
- Lightbox content no longer overflows when error message is visible (#62)

## [0.1.0] - 2026-05-28

### Added

- Flask backend serving a single-page Kanban UI at `/`
- Three-column layout: Keep, Unsorted, Trash
- Drag-and-drop card sorting via HTML5 Drag and Drop API
- Thumbnail generation (400x300) with Pillow, cached at `~/.cache/ss-dcl/thumbs/`
- State persistence via `~/.ss-dcl/state.json`
- Trash files via macOS native Trash API (`send2trash`)
- Sort screenshots by name, date, or size (ascending/descending)
- Undo last move action
- Lightbox preview (double-click or Preview button)
- Rename modal with extension-aware text selection
- Full-size image serving with 1h cache headers
- Auto-open browser on startup
- Port 5002 with auto-fallback via `_find_free_port()`
- Multi-format support: PNG, JPG, JPEG, TIFF, BMP
- Path traversal defense on all filename-accepting routes
- Pre-commit hooks: Ruff (lint+format), Pyright, pytest
- 79 tests covering all routes, sorting, edge cases, and frontend structure
