# Screenshot Declutterer

> A local-first macOS workspace for reviewing, renaming, and cleaning up screenshots.

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![macOS only](https://img.shields.io/badge/platform-macOS-lightgrey)

<p align="center">
  <img src="docs/assets/screenshot-sorted.png" alt="Screenshot Declutterer sorting board" width="820" />
</p>

Screenshot Declutterer opens a local webpage and scans top-level screenshot files
on your Desktop, plus any folders you add in Settings. Review them as draggable
cards across **Keep**, **Unsorted**, and **Trash**. You can preview, rename,
multi-select, and batch-triage files before confirming cleanup.

When cleanup is confirmed, selected files move to the native macOS Trash, where
they remain recoverable. The app and its optional AI naming flow run locally;
screenshots are never uploaded to a cloud service.

The README screenshots use the repository's deterministic, non-personal demo
fixture. See the [full UI baseline](docs/assets/ui-baseline/README.md) for the
complete capture matrix.

## Features

- **Kanban triage** — drag cards between Keep, Unsorted, and Trash, or use the
  focused-card actions and keyboard shortcuts
- **Multi-select and batch actions** — select several cards and move the whole
  selection to Keep or Trash; selected cards can also be dragged as a group
- **Multiple sources** — Desktop is always included; add up to ten tracked
  folders from the native macOS folder picker, with source tags on cards
- **Optional local AI naming** — LiteRT-LM uses an on-device vision model to
  suggest safe filenames; accept, dismiss, or edit suggestions
- **Learned category hints** — past decisions produce subtle “Likely keep” or
  “Likely trash” suggestions without moving files automatically
- **Direct renaming** — rename from a card, a lightbox preview, or an AI
  suggestion; file extensions are preserved when appropriate
- **Full-size preview** — double-click a card or use Preview to open the
  lightbox, then browse with previous/next controls
- **Safe cleanup** — confirmation is required before files move to macOS Trash;
  partial failures are reported individually and do not erase successful state
- **Undo** — multi-level undo persists across a browser reload for the current
  session
- **Reveal in Finder** — open the selected screenshot's location directly in
  Finder on macOS
- **Responsive themes** — System, Light, and Dark modes, plus a compact
  one-column switcher for smaller windows
- **Local-first runtime** — Pillow thumbnails are cached locally, decisions and
  memory are small JSON files, and there is no build step or account
- **Multi-format scanning** — PNG, JPG, JPEG, TIFF, and BMP files matching
  `Screenshot*.*`

<p align="center">
  <img src="docs/assets/screenshot-confirm.png" alt="Screenshot Declutterer trash confirmation" width="820" />
</p>

## Optional local AI naming

The AI feature is shipped and uses **LiteRT-LM**, not a cloud API. The default
model ID is `gemma4-e2b`. The core sorting workflow works normally when the
local AI server is unavailable.

To enable suggestions:

1. Install LiteRT-LM and import a compatible vision model with the ID
   `gemma4-e2b`.
2. Start the server with `litert-lm serve`, or use **Start local AI** from the
   AI status pill in the app. The default server URL is
   `http://localhost:9379`.
3. Use **Suggest All** in Settings for new screenshots. The app shows progress
   and cancellation controls, then lets you accept, dismiss, or edit each
   result.

The Settings panel also supports a custom model ID and optional
**Auto-suggest on scan**. AI replies are normalized to safe filenames while
preserving the source image extension. If LiteRT-LM is stopped or unreachable,
the app shows an offline status and leaves the rest of the workflow available.

## Quick Start

```bash
git clone https://github.com/Collaboration95/screenshot-declutterer.git
cd screenshot-declutterer
make install
make run
```

Your browser opens automatically at `http://localhost:<port>` (default 5002,
auto-incremented if occupied).

For development dependencies and checks:

```bash
make dev
make check
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SS_DCL_PORT` | `5002` (auto) | Override the server port. Set `0` to auto-detect. |
| `SS_DCL_DESKTOP` | `~/Desktop` | Directory to scan for Desktop screenshots. |
| `SS_DCL_HOME` | current home | Relocate app state, logs, and caches for an isolated runtime. |
| `THUMB_SIZE` | `800x600` | Thumbnail dimensions in `WxH` format. |
| `LITERT_BASE_URL` | `http://localhost:9379` | URL of the local LiteRT-LM server. |
| `LITERT_SERVE_CMD` | `litert-lm serve` | Command used by the in-app Start local AI action. |
| `FLASK_DEBUG` | `0` | Enable Flask debug mode (`1` to enable). |

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Arrow Left` | Move a focused Unsorted card to Keep; return a sorted card to Unsorted |
| `Arrow Right` | Move a focused Unsorted card to Trash; return a sorted card to Unsorted |
| `Enter` / `Space` | Toggle selection for the focused card |
| `Cmd/Ctrl + Z` | Undo the last move |
| `Esc` | Close a preview or modal, or clear the current selection |
| `Double-click` | Open a full-size preview |
| `←` / `→` in preview | Browse between screenshots |

## How It Works

1. **Scans** Desktop and configured tracked folders for top-level files matching
   `Screenshot*.*` with supported image extensions.
2. **Identifies** files with lightweight source-aware fingerprints and persists
   processing history in a local memory store.
3. **Serves** locally generated thumbnails through Flask; Pillow caches them by
   thumbnail size and refreshes stale files.
4. **Sorts** with a vanilla JavaScript drag-and-drop interface, multi-select,
   keyboard controls, and persisted Keep/Trash decisions.
5. **Suggests names** only when requested or enabled, by sending image data to
   the local LiteRT-LM server on the same Mac.
6. **Cleans up** through `send2trash`, which uses the native macOS Trash API
   instead of permanently deleting files.

## Local Data

By default, the app writes only local state:

- `~/.ss-dcl/state.json` — Keep/Trash decisions
- `~/.ss-dcl/memory.json` — fingerprinted file history, suggestions, and status
- `~/.ss-dcl/settings.json` — AI, theme, tracked-folder, and pruning settings
- `~/.ss-dcl/app.log` — rotating application log
- `~/.cache/ss-dcl/thumbs/<WxH>/` — generated thumbnail cache

The managed LiteRT-LM process writes its PID and log under `~/.ss-dcl/` as
well. Set `SS_DCL_HOME` to move this entire runtime tree to a throwaway
directory for demos or tests.

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for the project layout, make targets, and
test commands. The project uses Flask, vanilla HTML/CSS/JavaScript, Pillow,
`send2trash`, Ruff, Pyright, and pytest with no frontend build step.

See [backlog-features.txt](backlog-features.txt) for proposed features and
future ideas, and [CHANGELOG.md](CHANGELOG.md) for shipped changes.

## License

MIT — see [LICENSE](LICENSE).
