# FE-038 independent verification

**Result: PASS**, with the evidence timing and perceptual-match limits below. Verification was performed by **gpt-6-luna**. No implementation changes were made and no commit was created.

## Commands and results

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest` | **567 passed, 5 deselected**; **88.05% branch coverage**. Ran with local socket access for the port-flexibility tests. This full run preceded the final malformed-cache validation change. |
| `SS_DCL_PORT=5338 .venv/bin/python -m pytest --no-cov tests/test_similarity.py::test_malformed_persisted_signals_recompute -q` | **4 passed** after the latest cache validation change, including a 32-character non-hex byte hash. |
| `SS_DCL_PORT=5338 .venv/bin/python -m pytest --no-cov -m perf` | **3 passed**, 569 deselected. |
| `node --test "tests/js/**/*.test.js"` | **62 passed**. |
| `.venv/bin/ruff check . && .venv/bin/ruff format --check .` | Passed; 52 files already formatted. |
| `.venv/bin/pyright --pythonpath .venv/bin/python` | **0 errors, 0 warnings, 0 informations**. |
| `git diff --check` | Passed. |

The full suite was run twice during verification with the same 567-pass, 88.05% result. It excludes the opt-in tests shown as deselected; performance tests were run separately. The focused malformed-cache test covers the final cache-validation change without rerunning the whole suite.

## Browser verification

The latest synthetic similarity Chrome harness passed **26 checks** on Chrome 154. It covered 1440px and 320px layouts in light and dark themes, keyboard badge activation, JPEG/re-encode and resize candidates, direct-peer-only selection, selection of peers from an ordinary card in cleanup review, cleanup-checkbox uncheck/recheck while preserving the rest of the selection, batch actions, drag, undo, rename, refresh, Done, and disappeared files.

Evidence is local at `/tmp/fe038-similarity-ui-selection/verification.json`; its four generated captures are in that same directory. The final cleanup-batch Chrome regression also passed all checks, including viewport/control fit, keyboard access, 5 → 5 → 5 → 2 sequencing, selection, undo, deferral, rename, and disappearance. Its evidence is at `/tmp/fe038-cleanup-batches-ui-selection/verification.json`. Both harnesses wrote captures to `/tmp`; committed screenshots were not overwritten.

The implementer's refreshed private browser run passed with 20 copied screenshots,
including explicit JPEG/re-encode and resize assertions. Its report is at
`.cache/similarity-personal-report/verification.json`; personal captures remain
gitignored. This run finished after the verifier inspected the earlier report.
No personal screenshots were copied into this report or published. The latest
synthetic captures from Luna's run were copied into the public evidence directory.

The implementer's final full suite passed **568 tests, 5 deselected**, with
**88.05% coverage**, after the cache-validation change; final performance tests
passed **3 tests**. `uv run --no-sync pyright` passed, and
`uv run --no-sync pip-audit` found no known vulnerabilities in dependencies (the
local, unpublished application package itself cannot be audited against PyPI).

## Read-only implementation review

No concrete bug was found in the reviewed matching, cache, source lookup, rename, or selection flows.

- Exact matches use original byte size and BLAKE2b-128. Perceptual signals are cached against size, mtime, ctime, device, and inode, and are committed only if the stat tuple stays unchanged during computation. Cached digests validate as 16-byte hex values; cached contrast must be finite.
- Name fallback preserves an existing record only for the same source and unchanged byte size. The legacy bare-name fallback for Desktop rejects records tagged to a tracked source. A renamed record’s stable fingerprint is returned; a size change creates a new record identity.
- Similarity results are symmetric direct neighbors; the UI does not expand through a peer’s peers. Rename updates peer references in the current board. Active board selection toggles cleanup cards individually; with no active board selection, cleanup toggles continue to update independent cleanup-review choices.

## Measured limits

The synthetic adversarial fixtures measured JPEG re-encode at dHash distance 6 and proportional resize at 8; both remained candidates. A luminance-identical recolor had dHash distance 0 but RGB mean absolute error 41.33/255, so the 12/255 global gate rejected it. A localized recolor had global error 2.67/255 and worst 4×4-region error 39.17/255, so the 30/255 regional gate rejected it. Blank and low-contrast fixtures were rejected by the contrast gate.

Fine text changes can still pass: one changed-text fixture scored dHash distance 8 with RGB MAE 0.78/255. These signals identify review candidates and do not prove semantic or pixel identity. Crops, scrolling, overlays, and subtle content changes remain known limits; see [design notes](design-fe038-similar-screenshots.md).

## Remaining blockers

Luna also independently verified the final inclusive aspect-boundary correction:
**21 focused similarity/route/adversarial tests passed**, and **144 ordered
dimension pairs** agreed with an exact `Fraction` oracle. Integer cross products
accept exactly 3% in both directions and reject values above it, avoiding float
rounding at the boundary. The implementation's rule and thresholds are otherwise
unchanged.

No software-check blocker remains. Both the independent synthetic verification
and the implementer's refreshed personal-copy checks are complete.
