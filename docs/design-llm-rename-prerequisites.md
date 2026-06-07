# LLM-Powered Smart Rename — Prerequisite Architecture Plan

**Related backlog:** FE-011 (Auto-categorization), FE-005 (Bulk rename)
**Date:** 2026-06-02
**Status:** planning

---

## 1. Problem Statement

We want to integrate a local LLM (Gemma via Ollama or MLX) to generate plausible names
for screenshots. Before we can build the LLM feature itself, we need foundational
infrastructure that the current codebase lacks:

1. **No file identity** — the app tracks files by filename only. If a screenshot is
   renamed, there's no way to know "this is the same file I already analyzed."
2. **No persistent memory** — `state.json` only stores ephemeral keep/trash decisions
   for the current session. Once files are trashed or the session ends, all knowledge
   is lost.
3. **No processing history** — there is no record of which files the LLM has already
   seen, what names it suggested, or what the user decided.

Without these, the LLM would re-analyze every file on every launch — wasting time,
compute, and annoying the user with repeated suggestions for files they already handled.

---

## 2. Current State of the Codebase

```
~/.ss-dcl/
  state.json              ← session decisions only: {decisions: {filename: "keep"|"trash"}}

~/.cache/ss-dcl/
  thumbs/                 ← thumbnail cache (keyed by filename, checked via mtime)

src/ss_dcl/
  app.py                  ← monolith: routes, scanning, thumbnails, state, rename, trash
  __init__.py

static/
  app.js                  ← frontend Kanban, drag-and-drop, rename, lightbox
  style.css

templates/
  index.html              ← SPA shell
```

### Key characteristics:
- Single-file backend, single-file frontend, zero build steps
- State is **filename-keyed** and **session-scoped**
- No content hashing anywhere
- No abstraction layers (no separate modules for state, scanning, etc.)
- Atomic writes for state file (good — we'll reuse this pattern)
- `conftest.py` patches `DESKTOP`, `THUMB_DIR`, `STATE_FILE` for tests

---

## 3. Requirements

### Must-have
| ID | Requirement | Why |
|----|------------|-----|
| R1 | Metadata-based file identity (fingerprint) | Files get renamed; need stable identity without reading file contents |
| R2 | Persistent memory store (survives restarts) | Remember what we've processed across sessions |
| R3 | Processing status per file | Know which files are new / suggested / renamed / ignored |
| R4 | LLM suggestion history | Store what the LLM suggested and what the user chose |
| R5 | Idempotent scanning | Re-scanning the same files doesn't re-trigger processing |
| R6 | Backward compatible | Existing state.json, rename, trash flows still work |
| R7 | Testable | Memory store has its own unit tests, isolated from Flask |
| R8 | Atomic writes | Memory file can't be corrupted by crashes (reuse existing pattern) |

### Nice-to-have / Future-proofing
| ID | Requirement | Why |
|----|------------|-----|
| R9 | Extensible metadata per file | FE-011 (auto-categorize), FE-012 (clustering) need per-file metadata |
| R10 | Swappable storage backend | May want SQLite later for query performance at scale |
| R11 | Fingerprint migration | If identity scheme changes, provide migration path |
| R12 | Memory pruning / GC | Don't let memory grow unbounded over months/years |

---

## 4. File Identity: Metadata Fingerprints (Not Hashing)

### Why not content hashing?

SHA-256 / xxHash / BLAKE3 all solve a problem we don't have. We don't need
cryptographic uniqueness or adversarial collision resistance. We need to answer
one question: *"Have I seen this file before?"*

Content hashing:
- Reads every byte of every file → I/O cost even for unchanged files
- Needs a library dependency (xxhash) or is slow (stdlib hashlib)
- Solves for adversarial dedup, which is irrelevant for a local single-user tool

### Why metadata fingerprints work here

macOS screenshot filenames encode a **second-precision timestamp**:

```
Screenshot 2024-01-01 at 12.00.00 PM.png
Screenshot 2024-01-01 at 12.00.01 PM.png    ← auto-increments seconds
Screenshot 2024-01-01 at 12.00.00 PM 2.png  ← appends (2) for same-second
```

macOS guarantees these names are unique. Combined with file **size** (bytes),
the tuple `(original_name, size)` is a practically collision-free identity
for a single-user desktop tool.

**Real-world validation** — on your actual Desktop with 65 screenshots:
- 0 duplicate filenames (macOS guarantees this)
- 0 duplicate (name, size) pairs
- 0 I/O cost — we already `stat()` every file during scan

### The fingerprint

```python
def compute_fingerprint(name: str, size: int) -> str:
    """Stable identity string from file metadata. Zero file I/O."""
    return f"{name}|{size}"
```

This produces keys like:
```
"Screenshot 2024-01-01 at 12.00.00 PM.png|2072765"
"Screenshot 2024-01-01 at 12.00.01 PM.png|62118"
```

### What happens on rename?

When a file is renamed (via our app), we update the memory entry's
`last_known_name` but the **fingerprint never changes** — it's locked to
the original macOS name + size. The file stays tracked.

If renamed externally (outside our app), the old fingerprint is orphaned
and the file appears "new" under whatever name it has. This is correct —
if the user manually renamed a file, we treat it as a new context.

### What about mtime?

We intentionally **exclude mtime** from the fingerprint because:
- `cp` / `mv` / restore-from-trash all change mtime
- Download sync tools (Dropbox, iCloud) can change mtime
- Size + original name is already sufficient
- We store mtime as metadata for sorting/display, not identity

---

## 5. Architecture

### 5.1 New File Layout

```
src/ss_dcl/
  __init__.py
  app.py                  ← modified (integrate memory, add routes)
  memory.py               ← NEW: MemoryStore class + fingerprinting

~/.ss-dcl/
  state.json              ← unchanged (session keep/trash decisions)
  memory.json             ← NEW: persistent file history (fingerprint-keyed)
```

### 5.2 Memory Store Schema

```json
{
  "version": 1,
  "files": {
    "Screenshot 2024-01-01 at 12.00.00 PM.png|2072765": {
      "original_name": "Screenshot 2024-01-01 at 12.00.00 PM.png",
      "last_known_name": "quarterly-report.png",
      "size": 2072765,
      "extension": ".png",
      "status": "renamed",
      "suggested_name": "quarterly report.png",
      "user_name": "quarterly-report.png",
      "first_seen": "2024-01-01T12:00:00",
      "last_updated": "2024-01-01T12:05:00",
      "meta": {}
    }
  }
}
```

The key is `"{original_name}|{size}"` — human-readable, stable, zero I/O.

### 5.3 Status Lifecycle

```
                 ┌─────────────────── scan discovers file ──┐
                 │  compute_fingerprint(name, size)          │
                 │  lookup in memory                          │
                 │                                            │
            found? │                           not found ──┐ │
            ┌──┘   │                                         │ │
            │      ▼                                         │ │
     ┌─────────────┐    ┌──────┐                             │ │
     │ use existing │    │ new  │  (first time we've seen    │ │
     │ status       │    └──┬───┘   this fingerprint)        │ │
     └─────────────┘       │                                 │ │
                            │                                │ │
                     LLM analyzes image                     │ │
                            │                                │ │
                            ▼                                │ │
                     ┌───────────┐                           │ │
                     │ suggested │  (LLM proposed a name)    │ │
                     └──┬───┬────┘                           │ │
                        │   │                                │ │
                user accepts  user ignores                   │ │
                        │   │                                │ │
                        ▼   ▼                                │ │
                ┌─────────┐ ┌─────────┐                     │ │
                │ renamed │ │ ignored │  (user chose to     │ │
                └─────────┘ └─────────┘   keep original     │ │
                                              or skipped)   │ │
                                                            │ │
                                                    file reappears
                                                    (same fingerprint)
                                                            │ │
                                                            ▼ ▼
                                                     NO re-trigger ┘
                                                     (status exists)
```

### 5.4 MemoryStore API

```python
# memory.py

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

def compute_fingerprint(name: str, size: int) -> str:
    """Stable identity from metadata. Zero file I/O."""
    return f"{name}|{size}"


@dataclass
class FileRecord:
    fingerprint: str
    original_name: str
    last_known_name: str
    size: int
    extension: str
    status: str              # "new" | "suggested" | "renamed" | "ignored" | "trashed"
    suggested_name: Optional[str] = None
    user_name: Optional[str] = None
    first_seen: str = ""     # ISO 8601
    last_updated: str = ""   # ISO 8601
    meta: dict = field(default_factory=dict)


class MemoryStore:
    """Persistent, fingerprint-keyed file memory."""

    def __init__(self, path: Path):
        self._path = path
        self._files: dict[str, FileRecord] = {}

    # ── Loading / Saving ──
    def load(self) -> None: ...
    def save(self) -> None:          # uses _atomic_write

    # ── Queries ──
    def lookup(self, fingerprint: str) -> Optional[FileRecord]: ...
    def lookup_by_name(self, filename: str) -> Optional[FileRecord]: ...
    def get_status(self, fingerprint: str) -> str: ...
    def get_unprocessed(self, active_fingerprints: set[str]) -> list[FileRecord]: ...

    # ── Mutations ──
    def record_file(self, name: str, size: int) -> FileRecord: ...
    def update_suggestion(self, fp: str, suggested_name: str) -> None: ...
    def accept_suggestion(self, fp: str, user_name: str) -> None: ...
    def reject_suggestion(self, fp: str) -> None: ...
    def record_rename(self, fp: str, new_name: str) -> None: ...
    def remove(self, fp: str) -> None: ...

    # ── Maintenance ──
    def prune_stale(self, active_fps: set[str], max_age_days: int = 90) -> int: ...
```

### 5.5 Integration Points with app.py

```
┌─────────────────────────────────────────────────────────────┐
│ app.py Integration Points                                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  get_screenshots()                                          │
│  ├── Existing: glob files, build {name, size, mtime}       │
│  └── NEW:      compute fingerprint(name, size)             │
│                check memory: is this fingerprint known?     │
│                include {fingerprint, memory_status} in resp │
│                record new fingerprints into memory          │
│                                                             │
│  api_rename()  (POST /api/rename)                          │
│  ├── Existing: validate, rename file, move thumb,          │
│  │             update state.json                            │
│  └── NEW:      update memory: last_known_name, status      │
│                                                             │
│  api_done()    (POST /api/done)                             │
│  ├── Existing: trash files, clean state, clean thumbs      │
│  └── NEW:      update memory: status → "trashed"           │
│                                                             │
│  NEW: api_memory() (GET /api/memory)                       │
│  └── Returns memory status for all current screenshots     │
│      (used by frontend to show "already processed" badges) │
│                                                             │
│  NEW: api_suggest_names() (POST /api/suggest-names) [stub] │
│  └── Accepts list of fingerprints, returns {}              │
│      (will be wired to LLM in Phase 2)                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 5.6 Updated API Response Shapes

**GET /api/screenshots** — enriched with fingerprint + memory status:

```json
[
  {
    "name": "Screenshot 2024-01-01 at 12.00.00 PM.png",
    "size": 2072765,
    "mtime": 1704110400.0,
    "fingerprint": "Screenshot 2024-01-01 at 12.00.00 PM.png|2072765",
    "memory_status": "new"
  }
]
```

`memory_status` values: `"new"` | `"suggested"` | `"renamed"` | `"ignored"` | `"trashed"` | `null`

### 5.7 Data Flow Diagrams

#### Scan Flow (with memory)

```
  User opens app
       │
       ▼
  ┌─────────────────────────┐
  │ GET /api/state           │  (load session decisions)
  └───────────┬─────────────┘
              │
              ▼
  ┌──────────────────────────────────────────────────────┐
  │ GET /api/screenshots?sort=date_desc                  │
  │                                                       │
  │  For each Screenshot*.* on Desktop:                   │
  │    1. stat() → size, mtime          ← already done   │
  │    2. fp = f"{name}|{size}"         ← string concat  │
  │    3. memory.lookup(fp)                               │
  │       ├─ found   → use existing status                │
  │       └─ not found → memory.record_file(name, size)   │
  │                    → status = "new"                    │
  │    4. Build response {name, size, mtime,               │
  │       fingerprint, memory_status}                      │
  │                                                       │
  │  memory.save()                                        │
  └───────────┬──────────────────────────────────────────┘
              │
              ▼
  ┌──────────────────────────────────────┐
  │ Frontend receives files              │
  │                                      │
  │  For each card:                      │
  │    if memory_status == "suggested"   │
  │      → show suggestion badge         │
  │    if memory_status == "new"         │
  │      → mark as "AI name pending"     │
  │    if memory_status in               │
  │       ("renamed","ignored")          │
  │      → no action needed              │
  └──────────────────────────────────────┘
```

Note: **Step 2 is a string concatenation.** Zero file I/O. Zero hashing.
We already `stat()` every file in the existing code, so size is free.

#### Rename Flow (with memory update)

```
  User renames file (modal or lightbox)
       │
       ▼
  POST /api/rename {old_name, new_name}
       │
       ▼
  ┌──────────────────────────────────┐
  │ app.api_rename()                 │
  │                                  │
  │  1. validate paths (existing)    │
  │  2. rename file on disk          │
  │  3. move thumbnail               │
  │  4. update state.json decisions  │
  │  5. [NEW] compute fingerprint    │
  │  6. [NEW] memory.record_rename(  │
  │       fp, new_name)              │
  │  7. [NEW] memory.save()          │
  └──────────────────────────────────┘
```

#### LLM Suggest Flow (Phase 2 — stub in Phase 1)

```
  User clicks "Suggest Names" (or auto-trigger)
       │
       ▼
  POST /api/suggest-names {fingerprints: [...]}
       │
       ▼
  ┌────────────────────────────────────────────┐
  │ Filter: only fps with                      │
  │   memory_status == "new"                   │
  │                                            │
  │ For each unprocessed fingerprint:          │
  │   ┌────────────────────────────────────┐   │
  │   │ Send image to LLM                  │   │
  │   │ "Describe this screenshot          │   │
  │   │  in 3-5 words as a                 │   │
  │   │  filename-friendly name"           │   │
  │   └──────────┬─────────────────────────┘   │
  │              │                              │
  │              ▼                              │
  │   memory.update_suggestion(                 │
  │     fp, suggested_name)                     │
  │                                            │
  │ memory.save()                               │
  │ return {fingerprint: suggested_name, ...}  │
  └────────────────────────────────────────────┘
```

### 5.8 Relationship: state.json vs memory.json

```
  state.json                         memory.json
  ┌──────────────────────────┐       ┌──────────────────────────────┐
  │ Session-scoped            │       │ Permanent                    │
  │                           │       │                              │
  │ Keyed by FILENAME         │       │ Keyed by FINGERPRINT         │
  │                           │       │  ("Screenshot ... .png|size")│
  │ Values:                   │       │                              │
  │   "keep" | "trash"        │       │ Values:                      │
  │                           │       │   full FileRecord (see 5.2)  │
  │ Lifecycle:                │       │                              │
  │   Written on every        │       │ Lifecycle:                   │
  │   card move               │       │   Written on scan, rename,   │
  │                           │       │   suggest, trash, accept     │
  │ Cleaned:                  │       │                              │
  │   entries removed on      │       │ Cleaned:                     │
  │   trash/done              │       │   prune_stale() removes      │
  │                           │       │   entries > 90 days old      │
  │                           │       │   (configurable)             │
  │                           │       │                              │
  │ Used by: frontend         │       │ Used by: backend (memory     │
  │ card positioning           │       │   store), frontend (badges)  │
  └──────────────────────────┘       └──────────────────────────────┘

  They coexist. state.json is the "what column is this card in?" answer.
  memory.json is the "have I processed this file before?" answer.
```

---

## 6. Phase-by-Phase Implementation Plan

### Phase 1: Memory Store Foundation
**Goal:** Fingerprint-based identity + persistent memory, no LLM yet.

#### Phase 1A — Create `src/ss_dcl/memory.py`

| Component | Description |
|-----------|-------------|
| `compute_fingerprint()` | String concat `"{name}\|{size}"` — zero I/O |
| `FileRecord` dataclass | Typed representation of a memory entry |
| `MemoryStore` class | Load/save/lookup/record/update |
| `_atomic_write()` | Moved from `app.py` to here (shared utility) |

**Tests:** `tests/test_memory.py` (~25 tests)
- Fingerprint computation (various names, sizes, edge cases)
- MemoryStore CRUD (record, lookup, update, remove)
- Persistence (save → load → verify round-trip)
- Atomic write safety (corruption resistance)
- Status transitions (new → suggested → renamed/ignored)
- Prune stale entries
- lookup_by_name scans values (since key is fingerprint, not name)

#### Phase 1B — Integrate MemoryStore into `app.py`

| Change | Details |
|--------|---------|
| Import `MemoryStore`, `compute_fingerprint` | New imports at top |
| Initialize memory store | In `_init_dirs()`, create `MemoryStore(MEMORY_FILE).load()` |
| New constant `MEMORY_FILE` | `Path.home() / ".ss-dcl" / "memory.json"` |
| Move `_atomic_write` to `memory.py` | `app.py` imports from memory |
| Modify `get_screenshots()` | Compute fingerprint per file, check/record in memory, include in response |
| Modify `api_rename()` | After rename, update memory with `record_rename()` |
| Modify `api_done()` | After trash, update memory with `status="trashed"` |
| New: `GET /api/memory` | Return memory status for current files |
| New: `POST /api/suggest-names` (stub) | Accept `{fingerprints:[...]}`, return `{}` — wired later |
| New conftest fixture | Patch `MEMORY_FILE` to tmp_path |

**Tests:** Extend existing test files + new `tests/test_routes_memory.py`
- Screenshots response includes `fingerprint` and `memory_status`
- Rename updates memory
- Done/trash updates memory
- Memory survives across simulated sessions
- Stub suggest-names returns empty

#### Phase 1C — Frontend awareness (minimal)

| Change | Details |
|--------|---------|
| Card data attribute | `card.dataset.fingerprint = file.fingerprint` |
| Card data attribute | `card.dataset.memoryStatus = file.memory_status` |
| Visual badge | Optional: small dot/badge on "new" cards to indicate "AI name available" |

**Tests:** `tests/test_frontend.py` additions
- Card has fingerprint data attribute
- Card has memory status data attribute

---

### Phase 2: LLM Abstraction Layer
**Goal:** Swappable interface for local LLM backends.

#### Step 2.1 — Create `src/ss_dcl/llm/` package

```
src/ss_dcl/llm/
  __init__.py        ← exports get_provider()
  base.py            ← abstract base class
  ollama.py          ← Ollama provider (HTTP API)
  mlx_provider.py    ← MLX provider (Python bindings)
  prompt.py          ← prompt templates for screenshot naming
```

#### Step 2.2 — LLM Provider Interface

```python
# llm/base.py

class LLMProvider(ABC):
    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def suggest_name(self, image_path: Path, context: str = "") -> Suggestion: ...

    @abstractmethod
    def suggest_names_batch(self, images: list[Path]) -> list[Suggestion]: ...


@dataclass
class Suggestion:
    suggested_name: str
    confidence: float       # 0.0-1.0
    raw_response: str       # full LLM output for debugging
```

#### Step 2.3 — Wire into app.py

- `POST /api/suggest-names` now calls the LLM provider
- Background processing (ThreadPoolExecutor, same pattern as thumbnails)
- Results written to memory store

---

### Phase 3: UI Integration
**Goal:** Show suggestions in the Kanban UI.

#### Step 3.1 — Suggestion UI on cards
- "✨ AI Suggest" button on unsorted cards (when status == "new")
- Suggestion badge showing proposed name (when status == "suggested")
- Accept / Reject / Edit buttons for suggestions

#### Step 3.2 — Batch suggestion
- "Suggest All Names" button in header
- Progress indicator during batch processing
- Results appear as cards are processed

#### Step 3.3 — Settings
- LLM provider selection (Ollama / MLX)
- Model name
- Auto-suggest on scan (on/off)

---

### Phase 4: Polish & Advanced Features
**Goal:** Production readiness.

- Memory pruning / garbage collection
- Error recovery for failed LLM calls
- Retry logic
- FE-011 integration (auto-categorize uses memory `meta` field)
- Dark mode support for new UI elements

---

## 7. File Change Summary (Phase 1 Only)

| File | Action | Lines (est.) |
|------|--------|-------------|
| `src/ss_dcl/memory.py` | **NEW** | ~180 |
| `src/ss_dcl/app.py` | Modify | ~50 added, ~10 changed |
| `tests/test_memory.py` | **NEW** | ~220 |
| `tests/test_routes_memory.py` | **NEW** | ~80 |
| `tests/conftest.py` | Modify | ~5 added |
| `static/app.js` | Modify | ~15 added |
| `backlog-features.txt` | Modify | ~5 added |

**Total new code:** ~550 lines (Phase 1)
**Existing code modified:** ~25 lines across 3 files

---

## 8. Risk Analysis

| Risk | Mitigation |
|------|-----------|
| Fingerprint collision (same name + same size) | macOS screenshot naming makes this virtually impossible. If it ever happens, the worst case is a false "already processed" → user can force re-process via UI |
| Fingerprint changes if file is edited | Size changes → new fingerprint → treated as new file. This is correct behavior (edited image = new context for LLM) |
| File renamed externally | Old fingerprint orphaned, file appears "new" under its current name. Correct — user chose to rename outside the app |
| memory.json grows unbounded | `prune_stale()` with configurable max age. Run on app start |
| Concurrent access (unlikely) | Single-user tool, atomic writes. Same safety as state.json |
| Breaking existing tests | New fields in API response are additive. Existing tests check subset |
| Phase 2 LLM provider varies by machine | Abstraction layer + `is_available()` check. Graceful fallback |

---

## 9. Dependency Graph

```
Phase 1A: memory.py (standalone, no Flask dependency)
    │
    ▼
Phase 1B: integrate into app.py (Flask routes)
    │
    ▼
Phase 1C: frontend awareness (JS data attributes)
    │
    ▼
Phase 2A: llm/base.py (abstract interface)
    │
    ├──► Phase 2B: llm/ollama.py
    │
    └──► Phase 2C: llm/mlx_provider.py
              │
              ▼
         Phase 3A: suggestion UI on cards
              │
              ▼
         Phase 3B: batch suggestion + progress
              │
              ▼
         Phase 4: polish, caching, settings
```

Each phase produces a working, testable, deployable state.
No phase depends on a later phase.

---

## 10. Validation Against Current Codebase

### Checkpoint 1: Does this break existing tests?
- `get_screenshots()` returns additional fields (`fingerprint`, `memory_status`)
  but existing tests only check for `name`, `size`, `mtime` — they'll pass unchanged.
- `api_rename()` and `api_done()` gain side effects (memory update) but the
  existing assertions about file state, response codes, and state.json remain valid.
- Conftest patches `DESKTOP`, `THUMB_DIR`, `STATE_FILE` — we add `MEMORY_FILE`
  to the same pattern. No conflict.

### Checkpoint 2: Does this fit the project philosophy?
- ✅ No build step
- ✅ No new runtime dependencies (just string formatting)
- ✅ Single-user, localhost-only
- ✅ JSON file storage (consistent with state.json)
- ✅ Atomic writes (consistent pattern)
- ✅ Zero additional I/O on scan (fingerprint from already-available metadata)

### Checkpoint 3: Is this extensible?
- `FileRecord.meta` dict supports arbitrary future data (categories, clusters, tags)
- `MemoryStore` class can be swapped to SQLite backend without changing callers
- `LLMProvider` abstract class supports any number of backends
- New API endpoints follow existing naming convention (`/api/...`)
- Fingerprint scheme can be versioned (field in memory.json) for future migration

### Checkpoint 4: Edge cases
- **File appears, is processed, then deleted externally:** memory has the fingerprint,
  next scan won't find the file, no re-processing. If file reappears (restored from
  trash with same name + size), fingerprint matches → "already processed."
- **Two files with identical name and size:** Practically impossible with macOS
  screenshot naming. If it happens (edge case), both get the same suggestion —
  harmless. A `meta` field could store mtime for disambiguation in future.
- **File is renamed outside the app:** New name appears as a "new" file. Old
  fingerprint is orphaned and eventually pruned. Correct behavior.
- **File is restored from trash:** macOS may change the name (append " copy") or
  keep it. If name + size match → recognized. If not → treated as new. Both correct.
- **Corrupted memory.json:** Same recovery pattern as state.json — reset to empty.
- **Very large Desktop (200+ screenshots):** Fingerprint computation is O(n) string
  operations. Memory JSON is small (~1KB per file). No performance concern.

---

## 11. Empirical Model Evaluation (2026-06-03)

Hands-on testing of candidate vision models via Ollama on Apple Silicon (16 GB unified memory).

### Test Setup

- **Machine:** Apple Silicon Mac, 16 GB RAM
- **Ollama version:** 0.22.0
- **Prompt:** *"Describe this screenshot in 3-5 words as a filename."*
- **Test images:** Real `~/Desktop` screenshots (1-4 MB PNG files)
- **Method:** Ollama HTTP API (`/api/chat` with base64-encoded images, `stream: false`)

### Results

| Model | Disk Size | GPU RAM | Quality | Verdict |
|-------|-----------|---------|---------|---------|
| **gemma4:e2b** (Q4_K_M) | 6.7 GB | 7.7 GB | ✅ Excellent | **Recommended** |
| **moondream** | 1.7 GB | 1.3 GB | ❌ Broken | Unusable |
| **smolvlm** | — | — | — | Not available on Ollama |
| **minicpm-v** | — | — | — | Pull failed (too large/slow) |

### gemma4:e2b — Sample Outputs

| Screenshot | Original Name | Generated Name |
|------------|--------------|----------------|
| Chat thread screenshot | `Screenshot 2025-11-27 at 11.02.40 PM.png` | "Customer onboarding discussion thread" |
| Messages screenshot | `Screenshot 2025-12-24 at 6.43.58 PM.png` | "Salary delay messages" |
| Video call screenshot | `Screenshot 2025-05-15 at 10.34.00 PM.png` | "Two men video call" |

Output quality is consistently 3-4 words, descriptive, and filename-appropriate.

### moondream — Sample Outputs

| Screenshot | Output |
|------------|--------|
| Chat thread screenshot | *(empty)* |
| Messages screenshot | *(empty)* |
| Messages screenshot | "!!!IMPORTANT!!!" |

Produces either empty responses or incoherent output. Not suitable for this task
despite its small footprint. The model appears to be a proof-of-concept for edge
deployment, not production-quality vision.

### Key Findings

1. **gemma4:e2b at 7.7 GB GPU RAM is the only viable option** on Ollama right now.
   Smaller vision models (moondream) are too weak; mid-range models (smolvlm) aren't
   available via Ollama yet.

2. **7.7 GB on a 16 GB machine is tight but workable** — leaves ~8 GB for OS,
   browser, IDE. Models auto-unload after 5 min of inactivity (configurable via
   `OLLAMA_KEEP_ALIVE` env var).

3. **Memory management strategy for Phase 2:**
   - Set `OLLAMA_KEEP_ALIVE=0` in our integration so the model unloads immediately
     after each inference batch, freeing GPU RAM
   - Or batch all screenshots in one session, then explicitly unload
   - Document the RAM requirement in README so users know the trade-off

4. **Future option — MLX with 4-bit quantization:** The same Gemma 4 E2B model
   via MLX (`mlx-community/gemma-4-e2b-it-4bit`) may use only ~2-3 GB RAM.
   This would be the ideal path if MLX's Python API matures. The `LLMProvider`
   abstraction makes this a drop-in replacement.

5. **Fallback strategy:** If the model is unavailable (Ollama not running, model
   not pulled), the app should degrade gracefully — show a "Suggest Names" button
   that's disabled with a tooltip explaining the requirement.

### Decision

**Use `gemma4:e2b` via Ollama for Phase 2.** Revisit MLX path when it offers
a clear memory advantage without adding fragility.

---

## 12. Alternative Approach: OCR + Text-Only LLM (Hybrid Pipeline)

*Added: 2026-06-03*

### The Idea

Instead of feeding the full image to a vision LLM (which requires a large model
like gemma4:e2b at 7.7 GB), split the work:

1. **OCR via pytesseract** — extract text from the screenshot image
2. **Tiny text-only LLM** — given the extracted text, generate a short filename

This avoids vision models entirely. The OCR handles the "seeing," the LLM handles
the "understanding." Text-only LLMs are dramatically smaller than vision models.

### Why This Works for Screenshots

Most screenshots contain prominent text — code, chat messages, error dialogs,
settings panels, web pages, etc. OCR captures the essence of the content, which
is exactly what you'd use to name the file.

### OCR Component: pytesseract

| Aspect | Detail |
|--------|--------|
| System dep | `tesseract` via Homebrew (`brew install tesseract`) |
| Python dep | `pytesseract` (tiny wrapper, zero models) |
| RAM | 0 MB (no GPU needed) |
| Speed | ~50-200ms per screenshot |
| Quality | Excellent for screenshots (text on clean backgrounds) |
| macOS status | Already installed on this machine (Tesseract 5.5.2) |

**Usage:**

```python
from PIL import Image
import pytesseract

text = pytesseract.image_to_string(Image.open("screenshot.png"))
# → "Select a domain\nAutomotive and Machinery\nSkilled Trades..."
```

### Text-Only LLM Candidates

Since we only process text (not images), models can be much smaller:

| Model | Params | Ollama Size | RAM (loaded) |
|-------|--------|-------------|--------------|
| **SmolLM 360M** | 360M | ~700 MB | ~700 MB |
| **SmolLM 1.7B** | 1.7B | ~3 GB | ~3 GB |
| **Llama 3.2 1B** | 1B | ~1 GB | ~1 GB |
| **Qwen 2.5 1.5B** | 1.5B | ~1.5 GB | ~1.5 GB |
| **Gemma 2 2B** | 2B | ~1.5 GB | ~1.5 GB |
| **Phi-3 Mini 3.8B** | 3.8B | ~2.5 GB | ~2.5 GB |

All of these are trivial compared to gemma4:e2b at 7.7 GB.

### Proposed Pipeline

```
┌──────────────┐    ┌──────────────────┐    ┌─────────────────────┐
│  Screenshot   │───→│  pytesseract OCR  │───→│  Raw extracted text │
│  (image file) │    │  (0 GPU, 50ms)   │    │  e.g. "Select a     │
└──────────────┘    └──────────────────┘    │  domain\nAutomotive  │
                                             │  and Machinery..."  │
                                             └──────────┬──────────┘
                                                        │
                                                        ▼
                                             ┌─────────────────────┐
                                             │  Text-only LLM      │
                                             │  (SmolLM / Qwen /   │
                                             │   Gemma 2)          │
                                             │                     │
                                             │  Prompt:            │
                                             │  "Given this text   │
                                             │  from a screenshot, │
                                             │  suggest a short    │
                                             │  filename (3-5      │
                                             │  words): ..."       │
                                             └──────────┬──────────┘
                                                        │
                                                        ▼
                                             ┌─────────────────────┐
                                             │  "domain-selection" │
                                             │  "facetime-contacts"│
                                             │  "salary-delay-msg" │
                                             └─────────────────────┘
```

### Advantages Over Vision LLM

1. **RAM:** ~1-3 GB instead of 7.7 GB — leaves room for the app, browser, IDE
2. **Speed:** OCR (50ms) + tiny LLM (100ms) ≈ 150ms vs vision LLM ~1-2s
3. **Availability:** Text models are abundant; vision models are fewer and larger
4. **No GPU needed:** Tesseract runs on CPU, tiny LLMs can too
5. **Offline:** Everything runs locally, no network calls

### Drawbacks

1. **Fails on purely visual content:** A screenshot with diagrams, charts, or
   images-without-text won't produce useful OCR output
2. **OCR noise:** Tesseract can misread text, producing garbage LLM input
3. **Two moving parts:** OCR + LLM = two things that can fail independently
4. **Context loss:** The LLM only sees text, not layout, colors, or visual hierarchy

### Recommendation

Use the hybrid pipeline as the **primary approach** for Phase 2, with the
vision LLM as a **fallback** for screenshots where OCR yields too little text.
The `LLMProvider` abstraction supports both paths.

---

### Decision (Revised, 2026-06-03)

**Primary: OCR (pytesseract) + text-only LLM (SmolLM/Qwen/Gemma 2).**

**Fallback: Vision LLM (gemma4:e2b) when OCR produces insufficient text.**

The LLMProvider abstraction in Phase 2 should support both paths transparently.
