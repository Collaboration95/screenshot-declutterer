# Development

## Prerequisites

- macOS
- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Setup

```bash
git clone https://github.com/Collaboration95/screenshot-declutterer.git
cd screenshot-declutterer
make dev
```

## Make Targets

| Target | Description |
|--------|-------------|
| `make install` | Install runtime dependencies |
| `make dev` | Install dev dependencies |
| `make run` | Start the app |
| `make test` | Run tests |
| `make lint` | Lint with Ruff |
| `make typecheck` | Type-check with Pyright |
| `make check` | Run all checks (lint + typecheck + tests) |

Run `make` or `make help` to see all available targets.

## Tech Stack

- **Backend:** Python / Flask
- **Frontend:** Vanilla HTML, CSS, JavaScript (no build step)
- **Linting:** Ruff + Pyright
- **Testing:** pytest

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Serve SPA |
| GET | `/api/screenshots?sort=<mode>` | List screenshots (sort: name, name_desc, date, date_desc, size, size_desc) |
| GET | `/api/image/<filename>` | Serve full-size image (cache: 1h) |
| GET | `/api/thumb/<filename>` | Serve thumbnail (cache: 24h), falls back to full image |
| GET | `/api/state` | Get persisted decisions |
| PUT | `/api/state` | Save decisions state |
| POST | `/api/rename` | Rename a file — body `{old_name, new_name}` |
| POST | `/api/done` | Trash files — body `{filenames: [...]}`. Returns 207 on partial failure |
