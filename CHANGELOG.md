# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Multi-select + batch triage — click cards to select (blue ring + checkmark), floating batch bar moves the whole selection to Keep/Trash, dragging a selected card moves all selected; undo stays per-card (#69)
- Reveal in Finder — `POST /api/reveal` runs `open -R` on macOS (fire-and-forget, path-traversal guarded); Finder button on card actions and in the lightbox (#71)
- Empty-column drop hints — faint dashed "Drop here to keep/trash" placeholders inside empty side columns, dark-mode aware (#72)
- Photos-style batch drag ghost — dragging a selected card fans the selection's thumbnails out on the cursor (composite canvas + `setDragImage`, capped at 6 tiles with a `+N` badge), visual only (#74)

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
