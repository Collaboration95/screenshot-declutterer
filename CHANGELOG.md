# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
