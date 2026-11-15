# Development

## Prerequisites

- macOS
- Python 3.14 (selected by `.python-version`; also the only version tested in CI)
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Setup

```bash
git clone https://github.com/Collaboration95/screenshot-declutterer.git
cd screenshot-declutterer
make dev
```

`uv sync` selects Python 3.14 from `.python-version` and recreates an older
project virtualenv when needed. Run `uv run python --version` to confirm.
The package requires Python 3.14 or newer; older versions are no longer supported.

## CI and contributions

Create a feature branch and open a pull request targeting `main`. CI runs on
PR creation, reopening, and updates to the PR branch. Pushes alone and PRs to
other branches do not trigger this workflow.

The single macOS `Checks` job reads `.python-version` and runs Ruff lint and
formatting, Pyright, pytest with the 85% coverage gate, JavaScript unit tests,
and `pip-audit`. There is no multi-version compatibility matrix.
Local pre-commit Ruff, Pyright, and pytest hooks use the same locked `uv`
environment as CI.

GitHub branch protection requires a PR and a passing `Checks` job before a
change can enter `main`. Direct pushes are blocked for administrators too;
force pushes and deletion of `main` are also blocked. Review approvals are
not required, so a solo contributor can merge a passing PR.

The protection lives in repository settings, separately from
`.github/workflows/ci.yml`. Keep its required check name (`Checks`) aligned
with the workflow's job name when changing CI.
The checked-in configuration is `.github/main-branch-protection.json`.
Repository administrators can apply it with the authenticated GitHub CLI:

```bash
gh api --method PUT repos/Collaboration95/screenshot-declutterer/branches/main/protection \
  --input .github/main-branch-protection.json
```

The required check is bound to the GitHub Actions app, and the PR branch must
be up to date with `main` before merging. When this policy is first enabled,
older open PRs must incorporate the CI change so they can produce `Checks`.

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
| GET | `/api/screenshots?sort=<mode>` | List screenshots (sort: name, name_desc, date, date_desc) |
| GET | `/api/image/<filename>` | Serve full-size image (cache: 1h) |
| GET | `/api/thumb/<filename>` | Serve thumbnail (cache: 24h), falls back to full image |
| GET | `/api/state` | Get persisted decisions |
| PUT | `/api/state` | Save decisions state |
| POST | `/api/rename` | Rename a file — body `{old_name, new_name}` |
| POST | `/api/done` | Trash files — body `{filenames: [...]}`. Returns 207 on partial failure |
