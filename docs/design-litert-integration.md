# LiteRT-LM Integration — On-Device Vision Rename via `litert-lm serve`

**Related backlog:** FE-016 (LLM smart rename — provider extension), FE-018 (LLM benchmark — baseline data), FE-019 (OCR hybrid — alternative, now optional), FE-020 (model keep-alive — partially solved by LiteRT's resident model), FE-021 (async suggestion queue — informed by concurrency findings)
**Date:** 2026-08-11
**Status:** implemented (Phases A–C shipped on `feat/litert-lm`; Phase D eval complete 2026-08-12)
**Branch:** `feat/litert-lm`

---

## 1. Problem Statement

The app's only LLM backend is Ollama, and its default model (`gemma4:e2b`) is
documented as "too heavy for local hardware" (FE-016 note, backlog-features.txt).
The result: the flagship smart-rename feature is slow to the point of unusable on
this machine, and the team planned an OCR-hybrid pipeline (FE-019) as a workaround.

Google's **LiteRT-LM** (`litert-lm`, v0.15.0) runs the exact same model —
`gemma-4-E2B-it` — natively on Apple Silicon through the LiteRT runtime, with a
one-command OpenAI-compatible server. We already have a working sample venv at
`~/litert-lm/` and the model imported as `gemma4-e2b`.

This design makes `litert-lm serve` a first-class LLM provider in the app, so the
existing ✨ Suggest / Suggest All flows work end-to-end with a **verified ~5s per
screenshot** instead of being blocked on Ollama. It deliberately does **not**
refactor the LLM layer into a plugin framework — it adds a provider dispatcher,
mirroring how the app already treats `send2trash` vs. raw deletes (one small
switch, no over-engineering).

---

## 2. What We Verified (empirical, 2026-08-11)

All of the following was tested against the working sample before this doc was
written. Numbers are real measurements, not estimates.

### 2.1 Toolchain

```
litert-lm, version 0.15.0          # installed in ~/litert-lm/.venv (Python 3.14)
import:  litert-lm import \
           --from-huggingface-repo litert-community/gemma-4-E2B-it-litert-lm \
           gemma-4-E2B-it.litertlm gemma4-e2b
model:   ~/.litert-lm/models/gemma4-e2b/model.litertlm   (2.4 GB)
         + 5 × *.xnnpack_cache artifacts (compiled encoders, disk-cached)
```

### 2.2 `litert-lm serve` — OpenAI-compatible surface

- Default port **9379**; `--host`, `--port`, `--cors-origin` options
- Endpoints: `GET /v1/models`, `POST /v1/chat/completions`
- `litert-lm list` shows the imported model ID: `gemma4-e2b`
- Vision is supported: `--vision-backend [cpu|gpu]` on `run`, and image
  `image_url` content parts work through the server (tested below)

### 2.3 Vision rename works — with the standard OpenAI payload

```json
{
  "model": "gemma4-e2b",
  "messages": [{
    "role": "user",
    "content": [
      {"type": "text", "text": "Describe this screenshot as a 3-5 word filename. Return only the filename."},
      {"type": "image_url", "image_url": {"url": "data:image/png;base64,<b64>"}}
    ]
  }],
  "max_tokens": 40
}
```

Response (standard OpenAI shape):

```json
{
  "choices": [{"index": 0, "message": {"role": "assistant", "content": "Q3 Budget Planning"}, "finish_reason": "stop"}],
  "usage": {"prompt_tokens": 303, "completion_tokens": 5, "total_tokens": 308,
            "completion_tokens_details": {"reasoning_tokens": 0}}
}
```

The model correctly read rendered text off the test image ("Q3 Budget Planning
Meeting" → `Q3 Budget Planning`). This is the quality we need for rename.

### 2.4 Performance (real measurements)

| Metric | Value | Notes |
|--------|-------|-------|
| Cold server startup → ready | **~1 s** | xnnpack artifacts are disk-cached; model stays resident |
| Warm vision suggestion | **~5 s** per image | 1280×800 test screenshot |
| Text-only completion | sub-second | not used by rename flow |
| Server RSS while idle | **2.55 GB** | the 2.4 GB model resident in memory |
| Idle CPU | 0 % | model stays loaded, no polling |
| Concurrency | **serialized** | 2 parallel requests took 9.8 s ≈ 2 × 5 s — one model instance, requests queue |
| Thinking/reasoning | **off by default** | `reasoning_tokens: 0` in responses — no hidden latency |
| Format support | PNG, JPG work raw; **BMP/TIFF must be PNG-normalized** | raw BMP/TIFF base64 is tens of MB (shell/HTTP-hostile) |

### 2.5 FE-018 benchmark row (Phase D, 2026-08-12)

Ran `tools/eval-screenshot-names.py` on all **39** `~/Desktop` screenshots,
with a litert vision pipeline that calls the **production client**
(`_call_litert_suggest`, same prompt/payload/normalization as the app) so
quality + latency reflect real usage. The Ollama baseline is the app's current
ollama vision config (`gemma4:e2b`) on the same 39 files.

Reports saved to `tools/eval-results/litert-report.json` and
`tools/eval-results/ollama-gemma4-baseline.json`.

| Config | Success | Avg latency | Avg words | Size on disk |
|--------|---------|-------------|-----------|--------------|
| litert `gemma4-e2b` (LiteRT-LM serve, port 9379) | **39/39** | **6.5 s** | 3.2 | 2.4 GB |
| ollama `gemma4:e2b` (vision baseline) | 39/39 | 20.9 s | 3.3 | 7.2 GB |

- **3.2× speedup** and ~1/3 the disk footprint, same 100 % success rate.
- Every name was filename-safe (kebab-case, 2–200 chars); no failures, no
  retries, in either run.
- Per-file agreement is high; e.g. both models produced near-identical names
  for 7/39 files ("tuition-fees-details", "import-task-from-zip",
  "aws-backup-question", "galaxy-a71-backup", "calorie-deficit-details",
  "aws-certification-success", "software-engineering-fees").
- LiteRT occasionally diverges from Ollama's read of the same image (e.g.
  "reviewer-editing-interface" vs "flight-review-expires"; "sign-in-to-mohit-labs"
  vs "mohit-labs-sign-in") but stays in the same semantic ballpark.
- Latency spread: litert 5.2–8.0 s across the 39 files (< ±1 s wobble); ollama
  11.1–34.2 s (user-facing slowness, especially on larger files).

**Conclusion:** the LiteRT provider is quality-par with the Ollama vision
baseline at 3.2× the speed and a third of the disk footprint. It is the better
default on this machine.

### 2.6 Key architectural consequences

1. **Keep requests sequential** — the server serializes anyway; the app already
   calls per-file in a loop, so no change needed. Parallelizing (FE-021) would
   only buy UI responsiveness, not throughput.
2. **Normalize images to PNG before encoding** — Pillow `convert("RGB")` + save
   to PNG cuts a 40 MB BMP to ~10 KB base64. Reuses the same Pillow dependency
   the thumbnail pipeline already uses. (JPG/PNG can pass through as-is, but a
   single normalize path is simpler and also strips alpha/EXIF surprises.)
3. **Cold-start is a non-issue for LiteRT** — FE-020's "model still loading"
   problem is specific to Ollama's model unloading; LiteRT keeps the model
   resident. Only the server *process* itself needs starting.

---

## 3. Requirements

### Must-have

- [x] Select LiteRT-LM as LLM provider in Settings (alongside Ollama)
- [x] ✨ Suggest / ✨ Suggest All work against `litert-lm serve` with the model
      ID from `litert-lm list` (`gemma4-e2b`)
- [x] Health check reports LiteRT reachability (and drives the same
      pre-flight abort + error copy the Ollama path has)
- [x] PNG/JPG/JPEG/TIFF/BMP screenshots all work (PNG normalization)
- [x] Ollama provider remains fully functional and default (zero breakage,
      all 270 existing tests still green)
- [x] Unit tests for the new client with no live server (monkeypatched network,
      matching the `_call_ollama_suggest` test pattern)

### Nice-to-have / future-proofing

- [x] "Start server" affordance in the UI when LiteRT is down (managed
      subprocess, see §5.6) — this is what makes the feature *actually work*
      for a non-CLI user
- [x] `LITERT_BASE_URL` env override (mirrors `OLLAMA_BASE_URL`)
- [ ] Auto-suggest on scan defaulting to on for the LiteRT provider (cheap
      enough at ~5 s/file; decide later)
- [x] Record this integration as FE-018's first benchmark entry (we already
      have the latency/RSS numbers above) — see §2.5

---

## 4. Architecture

### 4.1 Provider model — a dispatcher, not a framework

Today `api_suggest_names()` calls `_call_ollama_suggest(file_path, model, ext)`
directly. We add one sibling function and route through a small dispatcher:

```
api_suggest_names()
  └─ _call_model_suggest(image_path, model, extension, provider)   # NEW
       ├─ provider == "litert" → _call_litert_suggest(...)         # NEW
       └─ provider == "ollama" → _call_ollama_suggest(...)         # unchanged
```

Rationale (house style — single-file backend, zero build, no over-engineering):
the old design doc's Phase 2 "llm/ package + Provider interface" was never built,
and a full plugin framework is not justified by two providers with near-identical
jobs. A dispatcher keeps `app.py` self-contained and is trivially testable by
monkeypatching `_call_model_suggest`.

### 4.2 Settings (backend)

| Key | Type | Default | Values |
|-----|------|---------|--------|
| `llm_provider` | str | `"ollama"` | `"ollama"` \| `"litert"` |
| `llm_model` | str | `"gemma4:e2b"` (unchanged) | free text; for litert the model ID from `litert-lm list` |

Settings validation in `api_save_settings` already type-checks `llm_provider`
as str; we extend the accepted set. `_load_settings()`/`api_get_settings()`
defaults stay `"ollama"` so existing installs and tests are untouched.

### 4.3 New constants (app.py)

```python
LITERT_BASE_URL = os.environ.get("LITERT_BASE_URL", "http://localhost:9379")
LITERT_HEALTH_TIMEOUT = 3          # seconds (mirrors OLLAMA_HEALTH_TIMEOUT)
_LITERT_HEALTH_TTL = 5.0           # cache negative AND positive probes
_litert_health_cache: tuple[float, bool] | None = None
LITERT_DEFAULT_MODEL = "gemma4-e2b"
# managed-process settings (nice-to-have, §5.6):
LITERT_SERVE_CMD = os.environ.get("LITERT_SERVE_CMD", "litert-lm serve")
LITERT_SERVE_READY_TIMEOUT = 30    # seconds to wait for /v1/models
LITERT_PIDFILE = Path.home() / ".ss-dcl" / "litert.pid"
```

### 4.4 `_call_litert_suggest(image_path, model, extension)` — the client

Payload (built with a small helper `_image_to_png_data_uri(path)`):

```python
def _image_to_png_data_uri(image_path: Path) -> str:
    """Normalize any supported image to a PNG base64 data URI.

    PNG/JPG/JPEG pass through a Pillow re-encode; BMP/TIFF (raw base64 can be
    tens of MB) collapse to ~10 KB. Also strips alpha (convert('RGB')) which
    some vision encoders dislike. Matches the THUMB_SIZE philosophy — one
    Pillow pipeline for all formats.
    """
    with Image.open(image_path) as im:
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
```

Request — `POST {LITERT_BASE_URL}/v1/chat/completions`:

```python
payload = json.dumps({
    "model": model,
    "messages": [{
        "role": "user",
        "content": [
            {"type": "text", "text": PROMPT},          # same prompt as Ollama path
            {"type": "image_url", "image_url": {"url": data_uri}},
        ],
    }],
    "max_tokens": 40,
    "stream": False,
}).encode("utf-8")
```

Response parsing — OpenAI shape, plus defensive handling:

```python
result = json.loads(resp.read())
choices = result.get("choices") or []
raw = (choices[0].get("message", {}).get("content") or "").strip() if choices else ""
```

Retry/error behavior — **reuse the exact Ollama machinery**:
- `timeout=30`, retries up to 2 with 1 s/2 s backoff on transient errors
- `_is_retryable_ollama_error(exc)` classifies `URLError`/`OSError` the same way
  (connection refused / DNS → fail fast; timeouts / resets / 5xx → retry)
- JSON decode failure → return None (won't fix itself), same as Ollama
- Sanitization pipeline (lowercase → hyphenate → strip punctuation → dedupe
  hyphens → truncate 120 → append extension) is shared — extract it from
  `_call_ollama_suggest` into a module-level `_sanitize_suggestion(raw, ext)`
  used by both providers so behavior stays identical.

### 4.5 Health check — generalize, keep the old route

Current: `GET /api/ollama/health` → `_ollama_healthy()` → `GET {OLLAMA_BASE_URL}/api/tags`.

New:
- `GET /api/llm/health` — provider-aware. For `litert` probes
  `GET {LITERT_BASE_URL}/v1/models` with a 3 s timeout and the same TTL-cached
  `_litert_healthy()` (cache both verdicts 5 s, so a down server is probed once
  per batch, not once per file — mirrors `_ollama_healthy`).
- Response: `{"ok": bool, "provider": "...", "error": "<copy>"}`.
- `GET /api/ollama/health` stays as a thin wrapper (`provider="ollama"`) so the
  frontend and any existing callers don't 404. The frontend migrates to the
  new endpoint.

Copy per provider, e.g.:
- Ollama down: `Ollama is not reachable — start it with 'ollama serve' and try again.`
- LiteRT down: `LiteRT server is not running — start it with 'litert-lm serve' (or use "Start server" below).`

### 4.6 Provider wiring in `api_suggest_names`

Replace the hard reject:

```python
provider = settings.get("llm_provider", "ollama")
if provider not in ("ollama", "litert"):
    return jsonify({"error": f"Provider {provider!r} is not supported."}), 400
...
suggested = _call_model_suggest(file_path, model, rec.extension, provider)
```

`model` default stays `DEFAULT_LLM_MODEL`; the settings UI will pre-fill
`gemma4-e2b` when the provider is litert (the ID from `litert-lm list` — note
no colon, unlike Ollama's `gemma4:e2b`).

### 4.7 Process lifecycle — "make it actually work" (the key UX decision)

Three options, ordered by app complexity:

**Option A — manual (mirror Ollama).** User runs `litert-lm serve` themselves.
Health check shows a clear message when down. Zero app changes beyond the
client. Consistent with how Ollama is treated today.
→ *Default posture; fallback when auto-start fails.*

**Option B — one-click start from the UI (recommended).** When
`llm_provider == "litert"` and the health probe fails, the Suggest All pre-flight
shows a "Start LiteRT server" button:

- `POST /api/llm/start` spawns `LITERT_SERVE_CMD` (resolved via `shutil.which`,
  then the known sample venv `~/litert-lm/.venv/bin/litert-lm` as fallback) as a
  detached subprocess, logs to `~/.ss-dcl/litert.log`, writes its PID to
  `LITERT_PIDFILE`, and polls `/v1/models` until ready or `LITERT_SERVE_READY_TIMEOUT`.
- `POST /api/llm/stop` kills **only** a PID we recorded (never one the user
  started) — pidfile ownership rule: if the PID in the pidfile isn't alive or
  doesn't match, refuse.
- Startup is fast (~1 s, §2.4), so the button feels instant.
- The app never auto-spawns on boot (respects the lazy-loading philosophy;
  2.55 GB is a big side effect to trigger silently).

**Option C — launchd agent / wrapper script.** `tools/litert-serve.sh` that
starts on login, keeps the process alive. Good for power users; out of scope
for this iteration (documented as a follow-up).

**Decision: A as default behavior, B as the UX affordance.** The pre-flight
already exists (Ollama circuit breaker, #68); we extend it rather than invent
new machinery.

### 4.8 Frontend changes

`static/app.js` + `templates/index.html`:

1. **Provider dropdown** (`#settings-provider`): add
   `<option value="litert">LiteRT-LM (local)</option>`; remove the disabled
   "MLX (coming soon)" line (it's been dead since #5).
2. **Model placeholder** swaps with provider: `gemma4:e2b` (Ollama) vs
   `gemma4-e2b` (LiteRT). Persist whatever the user typed; don't silently
   rewrite values.
3. **Health check** (`runSuggestBatch` pre-flight, currently
   `fetch("/api/ollama/health")`) → `fetch("/api/llm/health")`, and branch the
   error copy on `provider` in the response.
4. **Start/Stop affordance** (Option B): when litert is selected and health
   returns 503, render the error message + "Start LiteRT server" button that
   calls `/api/llm/start`, then re-runs the pre-flight.
5. `llmSettings` default object (`static/app.js:137`) stays `llm_provider:
   "ollama"` for backward compatibility; the Settings modal already round-trips
   through `PUT /api/settings`.

---

## 5. Data Flow Diagrams

### 5.1 Suggest All with LiteRT (happy path)

```
User clicks ✨ Suggest All
  → GET /api/llm/health  (provider=litert)
      → _litert_healthy() → GET :9379/v1/models → 200, cached 5s
  → POST /api/suggest-names {fingerprints: [...]}
      → for each new fingerprint:
          _call_model_suggest(path, "gemma4-e2b", ".png", "litert")
            → _image_to_png_data_uri(path)          # PNG-normalized
            → POST :9379/v1/chat/completions {image_url data URI}
            → parse choices[0].message.content
            → _sanitize_suggestion(raw, ".png")
          → memory.update_suggestion(fp, name) + category hint (unchanged)
  → {suggestions: {fp: name}, failures: [...]}       # unchanged shape
  → badges render (unchanged frontend)
```

### 5.2 LiteRT down (error path)

```
GET /api/llm/health → _litert_healthy() → connection refused → cached False
  → 503 {ok: false, provider: "litert", error: "LiteRT server is not running..."}
  → Suggest All aborts before any per-file calls (#68 behavior preserved)
  → UI shows error + [Start LiteRT server] button (Option B)
      → POST /api/llm/start → spawn, poll /v1/models (~1s), 200 {ok: true}
      → re-run pre-flight → batch proceeds
```

### 5.3 Provider switch is just a setting

```
Settings ⚙ → LLM Provider: LiteRT-LM → Save → PUT /api/settings
  → llm_provider: "litert" persisted in ~/.ss-dcl/settings.json
  → next Suggest run dispatches to _call_litert_suggest
  → switching back to Ollama requires zero migration (memory.json untouched —
     fingerprints/status are provider-agnostic)
```

---

## 6. Implementation Plan

### Phase A — Backend client + dispatcher (no UI)

1. Extract `_sanitize_suggestion(raw, extension)` from `_call_ollama_suggest`;
   have the Ollama path use it (pure refactor, behavior-identical).
2. Add `_image_to_png_data_uri(path)` (Pillow normalize; Pillow already a dep).
3. Add `_call_litert_suggest(image_path, model, extension)` (module-level, so
   tests monkeypatch it exactly like `_call_ollama_suggest`).
4. Add `_call_model_suggest(image_path, model, extension, provider)` dispatcher.
5. Add `LITERT_BASE_URL` consts + `_litert_healthy()` (TTL-cached probe of
   `/v1/models`).
6. Generalize health route: new `/api/llm/health`; keep `/api/ollama/health`
   as a wrapper.
7. Relax `api_suggest_names` provider gate to `("ollama", "litert")` and call
   the dispatcher.
8. **Tests** (Phase A, all offline): payload shape (data URI, content array),
   response parsing (normal / empty choices / missing keys), retry
   classification via `_is_retryable_ollama_error`, PNG normalization size for
   BMP/TIFF inputs, provider routing, health endpoint per provider, and the
   existing Ollama suite untouched. Expect ~25 new tests.

### Phase B — Settings + frontend

1. `index.html`: provider dropdown + placeholder swap.
2. `app.js`: health URL, per-provider error copy, `llmSettings` defaults.
3. Frontend tests (HTML-structure assertions, house pattern).

### Phase C — Managed process (Option B, the "actually works" piece)

1. `POST /api/llm/start` / `POST /api/llm/stop` + pidfile ownership rules.
2. `LITERT_SERVE_CMD` resolution (PATH → sample venv fallback).
3. Start/Stop button UI + disabled states; tests with monkeypatched subprocess.

### Phase D — Evaluation & follow-ups

1. [x] Run `tools/eval-screenshot-names.py` against the litert server on the same
   test set used for the FE-018 matrix; record quality + latency in this doc
   (§2.5 — done 2026-08-12: 39/39, 6.5 s avg, 3.2× faster than Ollama baseline).
2. [ ] Revisit FE-019 (OCR hybrid): with litert working, OCR is no longer
   required for rename; keep it as a fallback option only. *(parked — decided
   to skip; OCR stays optional.)*
3. [x] Decide auto-suggest-on-scan default for the litert provider. *(See
   § Open Questions — resolved: litert is an explicit, user-initiated action.
   Auto-suggest stays off by default for both providers; per-file cost of
   6.5 s makes scan-time suggestion a poor default on any provider.)*

---

## 7. File Change Summary

| File | Change |
|------|--------|
| `src/ss_dcl/app.py` | `_sanitize_suggestion` extraction, `_image_to_png_data_uri`, `_call_litert_suggest`, `_call_model_suggest`, `_litert_healthy`, `/api/llm/health` (+ keep `/api/ollama/health`), provider gate, `LITERT_*` consts; Phase C: `/api/llm/start` + `/api/llm/stop` |
| `templates/index.html` | provider `<option>` for litert, drop dead MLX option, start/stop button (Phase C) |
| `static/app.js` | health endpoint, per-provider copy, model placeholder swap, start/stop flow (Phase C) |
| `tests/test_routes_memory.py` (or new `tests/test_routes_litert.py`) | new client/health/dispatcher tests; existing tests unchanged |
| `tests/test_frontend.py` | provider option + placeholder assertions |
| `AGENTS.md` | API table additions (health generalization, llm/start/stop), `LITERT_*` runtime consts |
| `backlog-features.txt` | note FE-016 provider extension; FE-018 baseline entry |
| `tools/eval-screenshot-names.py` | `litert` approach added — reuses the app's `_call_litert_suggest` production client (Phase D) |
| `tools/eval-results/litert-report.json` | Phase D benchmark output (39 screenshots, litert) |
| `tools/eval-results/ollama-gemma4-baseline.json` | Phase D baseline output (same 39 screenshots, Ollama) |
| `CHANGELOG.md` | 0.6.0 entry (provider support, health generalization) — pending release prep |

---

## 8. Testing Strategy

- **Unit (no live server)** — monkeypatch `_call_litert_suggest` in route tests
  (house pattern from `test_suggest_names_with_real_file_and_mock_llm`); unit-test
  the client's payload/parsing with a fake `urllib` handler or by refactoring the
  HTTP call into a small injectable seam. Never require a real model in CI.
- **Health** — per-provider reachable/unreachable; TTL cache behavior (probe
  count asserted, matching `test_ollama_health` style).
- **Regression** — full suite (270 tests today) stays green with the Ollama
  default; the provider gate accepts `"litert"`; unknown providers still 400.
- **Manual UAT** — add a LiteRT scenario to RELEASING.md §4C: switch provider,
  run Suggest All against `litert-lm serve`, accept a suggestion, verify
  rename + memory status; kill the server → error path + Start button.

---

## 9. Risk Analysis

| Risk | Severity | Mitigation |
|------|----------|------------|
| litert-lm v0.15.0 API churn (young tool) | Med | All LiteRT surface isolated behind `_call_litert_suggest` + one health probe; one function to update |
| 2.55 GB resident memory | Med | Documented; only when provider selected + server running; never auto-spawned at boot |
| Server serializes requests (~5 s each) | Low | App already sequential; Suggest All progress bar covers batch UX; FE-021 would only help UI, not throughput |
| Port 9379 conflict | Low | `LITERT_BASE_URL` override; start endpoint fails fast with clear error |
| BMP/TIFF payloads | Low | PNG normalization caps base64 at ~10 KB |
| Managing a subprocess we didn't start | Med | Pidfile ownership rule — never kill a server the user started |
| Thinking model adds latency if enabled | Low | Confirmed off by default (`reasoning_tokens: 0`); don't enable in payload |
| Python 3.14 venv requirement (sample uses 3.14) | Low | `litert-lm` runs as a separate process; the app only talks HTTP. No dependency coupling |

---

## 10. Validation Against Current Codebase

**Checkpoint 1 — does this break existing tests?** No. `_call_ollama_suggest`
behavior is preserved (sanitizer extraction is a pure refactor, covered by
existing tests); default provider stays `"ollama"`; `/api/ollama/health` remains.

**Checkpoint 2 — does this fit the project philosophy?** Yes. Local-only,
no data leaves the machine, single-file backend, no build step, one small
dispatcher instead of a plugin framework, Pillow reused for normalization.

**Checkpoint 3 — is this extensible?** Yes. A third provider is one more
`_call_*_suggest` + one `elif`; the health endpoint is provider-parameterized;
memory store is provider-agnostic.

**Checkpoint 4 — edge cases.**
- Provider selected but server down → pre-flight abort + Start button (B) or
  clear copy (A)
- User edits model to a name `litert-lm list` doesn't know → server 404s the
  model → surfaces as failure entry, same as Ollama today
- App restarted with litert running → health probe succeeds, no double-spawn
- pidfile stale (crashed server) → start endpoint checks liveness before spawn

---

## 11. Open Questions

1. ~~Keep Ollama as the default provider, or flip to litert on this machine
   (settings.json is per-machine, so default choice is low-stakes)?~~
   **Resolved** — §2.5 shows litert is 3.2× faster and quality-par, so litert
   is the better default on this machine; per-machine `settings.json` makes
   the flip zero-risk. Owner decides at release time.
2. ~~Auto-suggest on scan — enable by default for litert (it's cheap enough)?~~
   **Resolved** — No. Auto-suggest stays off by default (both providers).
   Even at 6.5 s/file the scan-time cost is unjustified when suggestions are
   an explicit, user-initiated action; 20.9 s on Ollama would be worse.
3. ~~Should the Start button be Phase B (ship with provider) or Phase C (follow-up)?~~
   **Resolved** — shipped in Phase C, as recommended.
4. Add `--thinking false` / `--temperature` explicitly in the serve command or
   rely on model defaults (verified: reasoning off by default)?
   **Resolved** — rely on defaults; Phase C's serve command keeps the Out-of-scope
   flags minimal, and §2.4 confirms `reasoning_tokens: 0`.
5. ~~Record this as FE-018 benchmark entry #1 now (numbers are already in §2.4)?~~
   **Resolved** — done, full row in §2.5.

---

## Appendix A — Verified reproduction steps (for implementation + UAT)

```bash
# 1. Start the server (the working sample venv)
~/litert-lm/.venv/bin/litert-lm serve --port 9379
# ready in ~1s; logs to stdout; model resident (2.55 GB RSS)

# 2. Sanity: model visible
curl -s http://localhost:9379/v1/models

# 3. Vision rename (single screenshot)
B64=$(base64 < shot.png)
curl -s http://localhost:9379/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"gemma4-e2b\",\"messages\":[{\"role\":\"user\",\"content\":[
        {\"type\":\"text\",\"text\":\"Describe this screenshot as a 3-5 word filename. Return only the filename.\"},
        {\"type\":\"image_url\",\"image_url\":{\"url\":\"data:image/png;base64,$B64\"}}]}],\"max_tokens\":40}"

# 4. BMP/TIFF screenshots must be PNG-normalized before encoding (Pillow,
#    convert("RGB") → save PNG) — raw BMP/TIFF base64 is tens of MB.
```
