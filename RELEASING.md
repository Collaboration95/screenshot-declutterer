# Release / UAT Checklist — Screenshot Declutterer

Manual acceptance gate, run **by a human**, before every major merge to `main`.
Modeled on how big projects do it:

- **Django** — `RELEASING.rst`: a formal step-by-step release process that must be walked top to bottom
- **WordPress** — release "test drives": a public click-through test plan listing every feature and its expected behavior
- **Kubernetes / Rust** — release process docs with hard quality gates before tagging

The point: automated tests prove *the code works*; this checklist proves *a human can use it*.
Both must pass before a release.

---

## 0. What's being released

Fill this in before starting (record for the PR description / changelog):

| Item | Value |
|------|-------|
| Feature line | _e.g. Phases 1B/1C/3/4 — memory, LLM rename, auto-categorization, dark mode, pruning_ |
| Branch(es) to merge | _e.g. `phase4` → `main`_ |
| Open PRs involved | _e.g. #67_ |
| New endpoints | _list any added since last release_ |
| New env vars / settings | _list any added since last release_ |
| Version bump | _e.g. 0.3.0 → 0.4.0_ |

---

## 1. Pre-flight snapshot

Run these first and eyeball the output. Nothing should be dirty, red, or unexpected.

```bash
git status                       # clean tree (or only intended files)
git log --oneline main..HEAD     # exactly the commits you intend to ship
git diff main --stat | tail -3   # scale of the change
```

**Record the results here** (so the release is auditable later):

```
Branch: __________   Commits ahead of main: ____   Version: ____
```

---

## 2. Automated gates

```bash
make check          # ruff lint + pyright + pytest (all 250 tests)
```

Also run, if the tooling is installed:

```bash
uv run pip-audit    # dependency vulnerabilities
```

| Gate | Pass? |
|------|-------|
| `make lint` (Ruff) | ☐ |
| `make typecheck` (Pyright) | ☐ |
| `make test` (pytest) | ☐ |
| `pip-audit` | ☐ |

> ⚠️ If any gate fails, fix it now. Do not proceed to UAT with red gates.

---

## 3. UAT environment setup (safe — your real Desktop is untouched)

The app supports `SS_DCL_DESKTOP` to override the scanned directory.
**Always UAT against a scratch folder, never `~/Desktop`.**

```bash
# 1. Scratch dir with realistic test screenshots
mkdir -p /tmp/ssdcl-uat
cd /tmp/ssdcl-uat
/Users/speedpowermac/Documents/projects/CODE_MAIN/personal/ss-dcl/.venv/bin/python - <<'EOF'
from PIL import Image, ImageDraw
import os

def make(name, bg, text):
    img = Image.new("RGB", (1280, 800), bg)
    d = ImageDraw.Draw(img)
    d.rectangle([40, 40, 1240, 200], fill=(255, 255, 255))
    d.text((60, 90), text, fill=(0, 0, 0))
    img.save(name)

make("Screenshot-uat-1.png",  (200, 220, 240), "Salary slip January 2026")
make("Screenshot-uat-2.png",  (240, 220, 200), "Flight booking confirmation")
make("Screenshot-uat-3.png",  (220, 240, 200), "Meeting notes Q3 planning")
make("Screenshot-uat-4.png",  (200, 240, 220), "Random noise image here")
make("Screenshot-uat-5.png",  (240, 200, 220), "Bank statement monthly")
make("Screenshot-uat-6.jpg",  (200, 200, 200), "Screenshot jpg format test")
make("Screenshot-uat-7.bmp",  (210, 210, 240), "Screenshot bmp format test")
print("created", len(os.listdir(".")), "test files")
EOF

# 2. Back up real app state (UAT writes to ~/.ss-dcl regardless of SS_DCL_DESKTOP)
mkdir -p /tmp/ssdcl-uat-backup
cp -n ~/.ss-dcl/*.json /tmp/ssdcl-uat-backup/ 2>/dev/null || echo "(no prior state — fresh start, fine)"

# 3. Start the app against the scratch dir
cd /Users/speedpowermac/Documents/projects/CODE_MAIN/personal/ss-dcl
SS_DCL_DESKTOP=/tmp/ssdcl-uat .venv/bin/python -m src.ss_dcl.app
# Browser opens at http://localhost:5002 (or the printed port)
```

**Sanity check:** the three columns show 7 cards, each with a thumbnail.
`Unsorted = 7`, `Keep = 0`, `Trash = 0`. If not, stop — the scan is broken.

---

## 4. Manual UAT scenarios

Check each box **only** after observing the exact expected result.
Use the generated test files — never real screenshots.

### 4A. Core regression (features that must not have broken)

- [ ] **S1 — Scan & multi-format.** All 7 files appear (PNG ×5, JPG ×1, BMP ×1) in the Unsorted column.
- [ ] **S2 — Drag-and-drop.** Drag a card to Keep; it moves, counts update (`Keep` → 1). Drag another to Trash; counts update. Drag both back to Unsorted; counts return to 7/0/0.
- [ ] **S3 — Card action buttons.** On an Unsorted card: `← Keep` and `Trash →` move the card. `Preview` opens the lightbox.
- [ ] **S4 — Lightbox.** Double-click a card → full-size overlay. `Esc` and backdrop click close it. Arrow keys navigate between cards in the lightbox.
- [ ] **S5 — Inline lightbox rename.** Click the filename bar in the lightbox, edit, press Enter. Filename updates on the card, in the column, and on disk (`ls /tmp/ssdcl-uat`). Extension is preserved.
- [ ] **S6 — Rename modal.** `Rename` button → modal → new name → confirm. Card + disk + thumbnail all update. A duplicate name shows an error (409) and nothing breaks.
- [ ] **S7 — Undo.** `Cmd+Z` after a move returns the card to its previous column. Undo button in header works too. Undo survives a page reload (sessionStorage).
- [ ] **S8 — Sort.** Sort dropdown (name, date, size, and reversed variants) reorders cards correctly; a rename is reflected in name-sort order.
- [ ] **S9 — Trash + confirm.** `Done` with 1–2 cards in Trash → confirm modal shows correct count → confirm → files leave the scratch dir and appear in **macOS Trash** (recoverable). Partial-failure case: `mv` one test file out of `/tmp/ssdcl-uat` mid-session, try to trash it → graceful 207 partial-failure message, no crash.
- [ ] **S10 — Empty state.** Empty the scratch dir, reload → "No screenshots found on your Desktop."
- [ ] **S11 — Port flexibility.** Kill the server, run with `SS_DCL_PORT=5999` → app serves on 5999. Run with `SS_DCL_PORT=0` → auto-picks a free port (5002 if free).
- [ ] **S12 — Session persistence.** Move cards, reload the page → columns and counts restored from `state.json`.

### 4B. Memory store — Phase 1B/1C (NEW)

- [ ] **S13 — Fingerprint + status.** After first load, `~/.ss-dcl/memory.json` contains one record per screenshot with a `fingerprint` (`name|size`) and `status: "new"`.
- [ ] **S14 — Status persistence.** Rename a file via the UI → `memory.json` status becomes `"renamed"` for that fingerprint (fingerprint itself unchanged). Reload → the card no longer offers "✨ Suggest" (it's not `new` anymore).
- [ ] **S15 — Trash updates memory.** Trash a file via Done → its memory record becomes `"trashed"`.

### 4C. LLM suggest — Phase 3 (NEW)

> Requires Ollama (`ollama serve`). If you don't have a model installed, do **S18 only**
> (the error path) and mark S16–S17 as N/A — that is still a valid UAT result for this release.

- [ ] **S16 — Per-card Suggest.** On a fresh `new` card click `✨ Suggest`. A badge appears on the card showing the suggested kebab-case name (with ✓ accept / ✕ reject / ✎ edit buttons).
- [ ] **S17 — Suggest All.** Click `✨ Suggest All` with several `new` cards → progress bar fills, "N / M" counter updates, all cards get badges. **Cancel button** stops the batch cleanly mid-run (no stuck UI, button re-enables).
- [ ] **S18 — Ollama down (error path).** Stop Ollama, click `✨ Suggest All` → no crash; a clear message like "Couldn't reach Ollama — is it running?" or "No suggestions generated…" appears, and the app remains fully usable.
- [ ] **S19 — Accept.** ✓ on a badge → the file is renamed on disk to the suggested name, badge disappears, card updates (thumbnail + filename), `memory.json` → `renamed`. The state decision for the card is carried across the rename (a card in Keep stays in Keep under the new name).
- [ ] **S20 — Accept conflict.** Manually create a file with the same name as a suggestion on disk → accept → app appends `-2` (`name-2.png`) instead of overwriting. Nothing is lost.
- [ ] **S21 — Reject.** ✕ on a badge → badge gone, card stays put, `memory.json` → `ignored`, and the card no longer offers Suggest.
- [ ] **S22 — Edit.** ✎ on a badge → rename modal pre-filled with the suggested name, text selected up to the extension. Confirm → renamed (status `renamed`).

### 4D. Auto-categorization — Phase 4 (NEW)

- [ ] **S23 — Category hints.** After suggesting names for 2+ cards that share a keyword (e.g. both containing "salary"), then trashing one and keeping the other → the kept card shows a **green left border**, the trashed card a **red left border** (`category-hint-keep` / `category-hint-trash` CSS classes).
- [ ] **S24 — Hint clears.** Accept, reject, or rename a hinted card → border disappears immediately (no stale hint).

### 4E. Dark mode — Phase 4 (NEW)

- [ ] **S25 — Theme toggle.** ☀/☾ button cycles auto → dark → light. UI (cards, columns, modals, lightbox) renders correctly in each — no unreadable text or white-on-white.
- [ ] **S26 — Persistence.** Reload → theme is remembered (localStorage). In `auto` mode, toggling macOS dark mode in System Settings switches the app live (or within a page interaction).

### 4F. Settings & pruning — Phase 4 (NEW)

- [ ] **S27 — Settings round-trip.** ⚙ → change model name + prune age (e.g. `30`) → Save → reopen settings → values persisted (`~/.ss-dcl/settings.json`). Reload page → still there.
- [ ] **S28 — Settings validation.** Enter a non-numeric prune age → rejected (no crash, sane fallback to 90). Negative / zero → fallback to 90.
- [ ] **S29 — Pruning.** With prune age set low (e.g. `1`) and a `memory.json` entry whose `last_updated` is > 1 day old for a file that no longer exists on disk → on next app start, that entry is garbage-collected (log line `Pruned N stale memory entries`).

---

## 5. Cleanup (restore your real environment)

```bash
# Remove test screenshots from Trash (they're just copies, but tidy up)
# Delete scratch dir + backups
rm -rf /tmp/ssdcl-uat /tmp/ssdcl-uat-backup

# Restore real app state (or leave as-is if you didn't care about pollution)
cp /tmp/ssdcl-uat-backup/*.json ~/.ss-dcl/ 2>/dev/null || echo "no backup to restore"
```

> The only leak from a scratch-dir UAT is `~/.ss-dcl/*.json` — memory entries, state decisions,
> and settings for the test files. Restoring the backup resets it completely.

---

## 6. Release choreography (after UAT passes)

1. [ ] Update `CHANGELOG.md` — new `## [x.y.z] - YYYY-MM-DD` section, `### Added` / `### Fixed`, linking PR numbers. (Currently stale at 0.3.0 while Phases 1B/1C/3/4 sit unrecorded.)
2. [ ] Bump the version in `pyproject.toml`.
3. [ ] Commit the changelog + version bump on the feature branch.
4. [ ] Merge to `main` (squash or merge — keep history readable).
5. [ ] Tag: `git tag v0.4.0 && git push origin v0.4.0` (annotated, message = changelog summary).
6. [ ] Clean up merged branches (`git branch -d`, `git push origin --delete`) — target the ~15 stale branches.
7. [ ] Mark `backlog-features.txt` items done (FE-016/FE-017/FE-011/FE-013/FE-014 as applicable).
8. [ ] Re-run `make check` on `main` post-merge as the final sanity pass.

---

## 7. Sign-off

| Gate | Status |
|------|--------|
| Automated gates (section 2) | ☐ PASS ☐ FAIL |
| Manual UAT (section 4) | ☐ PASS ☐ FAIL — failed scenarios: ________ |
| Changelog + version | ☐ done |
| Tag + push | ☐ done |

**Decision:** ☐ RELEASE v____  ☐ HOLD — reasons: ________________________________

---

## Quick reference

- Run app: `.venv/bin/python -m src.ss_dcl.app` (from repo root) — or `make run`
- Safe UAT: `SS_DCL_DESKTOP=/tmp/ssdcl-uat .venv/bin/python -m src.ss_dcl.app`
- Tests: `make check` · State: `~/.ss-dcl/state.json` · Memory: `~/.ss-dcl/memory.json` · Settings: `~/.ss-dcl/settings.json`
