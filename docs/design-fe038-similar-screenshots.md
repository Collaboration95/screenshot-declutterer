# Find similar screenshots (FE-038)

Status: implemented and locally verified, 2026-10-10.

The implementation preserves the proposal's separate byte and visual signals,
direct matches, and explicit user review. Independent GPT-6 Luna measurements
showed dHash collisions for different text and recolored interfaces, so v1 adds
contrast and RGB checks. The submitted proposal ended at the signals table;
the cache schema, API contract, and selection behavior below complete it.

## Signals and cache

Pillow and Python's standard library provide all computations. Exact identity
compares original byte size and a streamed BLAKE2b-128 digest. It does not hash
reencoded pixels. Unreadable images can still have identical bytes, but cannot
produce visual candidates. Pillow's decompression-bomb limits apply.

For visual candidates, EXIF orientation is applied and transparency composited
on white. Grayscale is reduced with Lanczos to 17×16; 256 horizontal comparisons
form dHash. Every condition below must pass:

- Hamming distance at most 10/256.
- `max(aspect_a, aspect_b) / min(aspect_a, aspect_b) - 1 <= 0.03`.
- Both hash populations between 9 and 247 inclusive.
- Both reduced grayscale standard deviations at least 8 on the 0–255 scale.
- Mean absolute RGB error at most 12 across a 16×16 color thumbnail.
- Mean absolute error at most 30 in each of its sixteen 4×4 RGB regions.

These thresholds are conservative candidate filters, not proof of duplication.
Small text changes can vanish at the reduced resolution. Large overlays, crop,
scroll, and theme changes may be missed. Visually unrelated layouts and measured
color collisions are rejected. Exact byte identity takes precedence, so the same
peer is never reported twice.

Each `FileRecord.meta.similarity` holds:

| Field | Content |
| --- | --- |
| `version` | Signal algorithm version; currently 1 |
| `stat` | Size, mtime_ns, ctime_ns, device, inode |
| `signals.byte_hash` | 32 hex characters (128 bits) |
| `signals.dhash` | 64 hex characters (256 bits), or null on decode failure |
| `signals.width`, `height` | Oriented source dimensions |
| `signals.rgb` | 768 thumbnail bytes represented as 1,536 hex characters |
| `signals.contrast` | Reduced grayscale standard deviation |

Unchanged scans and app restarts reuse cached signals. Same-size edits with
restored mtimes are caught by ctime; replacement is caught by inode/device.
Before/after stat checks discard signals if a file changes during hashing.
Missing/unreadable files do not contribute stale matches. Malformed cache entries
are recomputed. Hashes remain in existing local JSON memory and are not sent in
the screenshot API. There are no workers or model processes for similarity and
no background tasks when idle.

Rename retains the original memory fingerprint if byte size remains unchanged;
the next scan revalidates file stats. A file with a changed size gets a new
metadata identity. Renamed files still follow the existing `Screenshot*.*`
scan convention.

## API and interaction

`GET /api/screenshots` adds a `matches` list to each active file:

```json
{"source": "Desktop", "name": "Screenshot copy.png", "kind": "identical", "distance": 0}
```

Near candidates have `kind: "similar"` and their dHash Hamming distance. Names
and source IDs identify live peers even when filenames repeat across folders.
Matches are symmetric and sorted deterministically by kind, distance, source,
and name. Only files in the current scan participate; removed or untracked
sources cannot leave stale peers. A–B and B–C do not imply A–C.

A card can show both **Identical** and **N similar**. Clicking a button replaces
the board selection with that anchor and its direct peers of that type. The
native buttons support keyboard activation. Selection is reversible and makes
no Keep or Trash decisions; existing batch actions and drag own triage and undo.
Done remains the confirmed native Trash operation.

The selection can include cleanup cards without advancing or filling the cleanup
batch. The ordinary batch bar temporarily owns actions; cleanup checkboxes show
the active selection while their independent review choices are retained. Clear
or Escape resumes those choices. Renames update peer references immediately.
Done updates badges after successfully removed cards; Refresh rereads sources
and clears board selection, as before. Selection announcements use the existing
status region without a toast covering batch controls on narrow screens.

## Verification and practical limits

Unit and route tests cover exact/near boundaries, nontransitivity, source
identity, cache reuse/restart/corruption, same-size edits, rename, disappeared
files, read races, and outside-folder symlinks. Luna's adversarial tests include
equal-luminance color collisions, changed regions, blank/low-contrast images,
JPEG reencoding, resize, and the known fine-text ambiguity.

`tools/check_similarity_ui.py` drives real headless Chrome against an isolated
Flask server. It checks keyboard activation, layout at 1440px and 320px in both
themes, cleanup coexistence, source-aware selection, batch queue, drag, undo,
rename, refresh, and fixture-only Done. The fixture Trash adapter unlinks only
disposable test copies. The ordinary route suite mocks native Trash.

An explicitly authorized run with `--copy-from ~/Desktop` duplicates up to 20
personal screenshots into `.cache/similarity-personal-fixtures`. All personal
captures and reports go to `.cache/similarity-personal-report`, both gitignored.
Original images and personal state are untouched. Public evidence uses synthetic
screenshots only. The fixture may combine synthetic and copied screenshots;
transformed and identical copies validate mechanics, not a field error rate.

Matching is pairwise, O(N²), and result size can also be quadratic when all files
are identical. Signal computation is cached, but first scans decode each new
image. The existing 500-file scan budget passes locally; this is not a guarantee
for thousands of full-resolution files. Clustering and semantic search remain
separate work. No automatic deletion, union-find, or embedding model is included.
