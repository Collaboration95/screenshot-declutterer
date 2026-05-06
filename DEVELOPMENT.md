# Development

## Prerequisites

- macOS
- Python 3.9+
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
