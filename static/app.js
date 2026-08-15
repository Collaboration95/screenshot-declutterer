const decisions = new Map();
const undoStack = [];
const selectedCards = new Set();
let totalCards = 0;
let currentSort = "date_desc";

try {
  const saved = sessionStorage.getItem("undoStack");
  if (saved) undoStack.push(...JSON.parse(saved));
} catch (_) {}

const cardsUnsorted = document.getElementById("cards-unsorted");
const cardsTrash    = document.getElementById("cards-trash");
const cardsKeep     = document.getElementById("cards-keep");

const colUnsorted = document.getElementById("col-unsorted");
const colTrash    = document.getElementById("col-trash");
const colKeep     = document.getElementById("col-keep");

const countUnsorted = document.getElementById("count-unsorted");
const countTrash    = document.getElementById("count-trash");
const countKeep     = document.getElementById("count-keep");

const undoBtn        = document.getElementById("undo-btn");
const doneBtn        = document.getElementById("done-btn");
const suggestAllBtn  = document.getElementById("suggest-all-btn");
const settingsBtn    = document.getElementById("settings-btn");
const statusMsg      = document.getElementById("status-msg");
const emptyMsg       = document.getElementById("empty-msg");
const loadingMsg     = document.getElementById("loading-msg");
const sortSelect     = document.getElementById("sort-select");
const suggestProgress   = document.getElementById("suggest-progress");
const suggestProgressFill = document.getElementById("suggest-progress-fill");
const suggestProgressText = document.getElementById("suggest-progress-text");
const suggestCancelBtn  = document.getElementById("suggest-cancel-btn");

const lightbox    = document.getElementById("lightbox");
const lightboxImg = document.getElementById("lightbox-img");
const lightboxFilename = document.getElementById("lightbox-filename");
const lightboxRenameInput = document.getElementById("lightbox-rename-input");
const lightboxRenameError = document.getElementById("lightbox-rename-error");
const lightboxBar = document.querySelector(".lightbox-bar");
const cardTooltip = document.getElementById("card-tooltip");

const confirmModal = document.getElementById("confirm-modal");
const modalTitle   = document.getElementById("modal-title");
const modalCancel  = document.getElementById("modal-cancel");
const modalConfirm = document.getElementById("modal-confirm");

const settingsMenu   = document.getElementById("settings-menu");
const settingsProvider = document.getElementById("settings-provider");
const settingsModel   = document.getElementById("settings-model");
const settingsAuto    = document.getElementById("settings-auto");
const settingsCancel  = document.getElementById("settings-cancel");
const settingsSave    = document.getElementById("settings-save");

const llmServerBtn    = document.getElementById("llm-server-btn");

const renameModal   = document.getElementById("rename-modal");
const renameInput   = document.getElementById("rename-input");
const renameCancel  = document.getElementById("rename-cancel");
const renameConfirm = document.getElementById("rename-confirm");
const renameError   = document.getElementById("rename-error");
let renameTarget = null;

const batchBar      = document.getElementById("batch-bar");
const batchCount    = document.getElementById("batch-count");
const batchKeepBtn  = document.getElementById("batch-keep-btn");
const batchTrashBtn = document.getElementById("batch-trash-btn");
const batchClearBtn = document.getElementById("batch-clear-btn");

const columns = [colTrash, colUnsorted, colKeep];

// ── Theme management ─────────────────────────────────────────────────────────
const THEME_KEY = "ss-dcl-theme";

function applyTheme(mode) {
  if (mode === "dark") {
    document.documentElement.setAttribute("data-theme", "dark");
  } else if (mode === "light") {
    document.documentElement.removeAttribute("data-theme");
  } else {
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    if (prefersDark) {
      document.documentElement.setAttribute("data-theme", "dark");
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
  }
}

function getSavedTheme() {
  try { return localStorage.getItem(THEME_KEY) || "auto"; } catch (_) { return "auto"; }
}

function saveTheme(mode) {
  try { localStorage.setItem(THEME_KEY, mode); } catch (_) {}
}

function cycleTheme() {
  const current = getSavedTheme();
  const next = { auto: "dark", dark: "light", light: "auto" }[current] || "auto";
  saveTheme(next);
  applyTheme(next);
  _updateThemeLabel();
}

function _updateThemeLabel() {
  const btn = document.getElementById("theme-toggle");
  if (!btn) return;
  const mode = getSavedTheme();
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const effective = mode === "auto" ? (prefersDark ? "dark" : "light") : mode;
  btn.setAttribute("aria-label", "Theme: " + mode + (mode === "auto" ? " (" + effective + ")" : "") + " — click to cycle");
}

applyTheme(getSavedTheme());
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  if (getSavedTheme() === "auto") applyTheme("auto");
});

document.getElementById("theme-toggle").addEventListener("click", () => {
  cycleTheme();
  _updateThemeLabel();
});
_updateThemeLabel();

// ── Settings state (loaded on init) ────────────────────────────────────────────
let llmSettings = { llm_provider: "litert", llm_model: "gemma4-e2b", auto_suggest: false, prune_max_age_days: 90 };

// LiteRT is the only provider.
const LLM_PROVIDER_LABELS = { litert: "LiteRT-LM" };
const LLM_PROVIDER_MODELS = { litert: "gemma4-e2b" };

// Fallback offline copy when the health response carries no error message.
function providerErrorCopy() {
  const label = LLM_PROVIDER_LABELS[llmSettings.llm_provider] || "LiteRT-LM";
  return `${label} is not running — use the Start button and try again.`;
}

// ── Managed LiteRT server (start/stop button) ───────────────────────────────
// Label follows the last health verdict.
function refreshLLMServerButton() {
  llmServerBtn.hidden = false;
  llmServerBtn.disabled = true;
  fetch("/api/llm/health")
    .then(r => r.json())
    .then(h => {
      llmServerBtn.textContent = h.ok ? "■ Stop LLM" : "▶ Start LLM";
      llmServerBtn.disabled = false;
    })
    .catch(() => {
      llmServerBtn.textContent = "▶ Start LLM";
      llmServerBtn.disabled = false;
    });
}

llmServerBtn.addEventListener("click", () => {
  const starting = llmServerBtn.textContent.includes("Start");
  llmServerBtn.disabled = true;
  fetch(starting ? "/api/llm/start" : "/api/llm/stop", { method: "POST" })
    .then(r => r.json())
    .then(data => {
      statusMsg.textContent = data.message || data.error || "Server control failed.";
      refreshLLMServerButton();
    })
    .catch(() => {
      statusMsg.textContent = "Couldn't reach the server controller.";
      refreshLLMServerButton();
    });
});

function loadSettings() {
  return fetch("/api/settings")
    .then(r => r.json())
    .then(s => { llmSettings = s; })
    .catch(() => {});
}

// ── Bootstrap ────────────────────────────────────────────────────────────────
function init() {
  loadSettings().then(() => {
    refreshLLMServerButton();
    fetch("/api/state")
      .then(r => r.json())
      .then(state => loadScreenshots(state.decisions || {}))
      .catch(() => loadScreenshots({}));
  });
}

function loadScreenshots(savedDecisions) {
  clearSelection();
  fetch(`/api/screenshots?sort=${encodeURIComponent(currentSort)}`)
    .then(r => r.json())
    .then(files => {
      loadingMsg.hidden = true;
      if (files.length === 0) {
        emptyMsg.hidden = false;
        return;
      }
      totalCards = files.length;
      const existing = new Set(files.map(f => f.name));

      for (const [name, col] of Object.entries(savedDecisions)) {
        if (existing.has(name) && (col === "keep" || col === "trash")) {
          decisions.set(name, col);
        }
      }
      for (const name of Array.from(decisions.keys())) {
        if (!existing.has(name)) decisions.delete(name);
      }

      files.forEach(f => {
        const col = decisions.has(f.name) ? decisions.get(f.name) : "unsorted";
        const target = col === "trash" ? cardsTrash
                     : col === "keep"  ? cardsKeep
                     : cardsUnsorted;
        target.appendChild(makeCard(f.name, col, f.fingerprint, f.memory_status, f.suggested_name, f.suggested_category));
      });
      updateCounts();
      saveState();

      // Auto-suggest if enabled
      if (llmSettings.auto_suggest) {
        const newFps = files
          .filter(f => f.memory_status === "new")
          .map(f => f.fingerprint);
        if (newFps.length > 0) suggestBatch(newFps);
      }
    })
    .catch(() => {
      loadingMsg.hidden = true;
      statusMsg.textContent = "Failed to load screenshots.";
    });
}

init();

// ── Sort ─────────────────────────────────────────────────────────────────────
sortSelect.addEventListener("change", () => {
  currentSort = sortSelect.value;
  undoStack.length = 0;
  clearSelection();
  document.querySelectorAll(".card").forEach(c => c.remove());
  loadScreenshots(Object.fromEntries(decisions));
});

// ── Persist state ────────────────────────────────────────────────────────────
let _saveTimer = null;
function saveState() {
  if (_saveTimer) clearTimeout(_saveTimer);
  _saveTimer = setTimeout(() => {
    const obj = {};
    for (const [k, v] of decisions) obj[k] = v;
    fetch("/api/state", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decisions: obj }),
    }).catch(() => {
      statusMsg.textContent = "Warning: failed to save state.";
    });
    _saveTimer = null;
  }, 300);
}

// ── Card factory ─────────────────────────────────────────────────────────────
function makeCard(filename, column, fingerprint, memoryStatus, suggestedName, suggestedCategory) {
  const card = document.createElement("article");
  card.className = "card";
  card.setAttribute("role", "listitem");
  card.setAttribute("aria-label", filename);
  card.dataset.filename = filename;
  card.dataset.fingerprint = fingerprint || "";
  card.dataset.memoryStatus = memoryStatus || "";
  card.dataset.suggestedName = suggestedName || "";
  if (suggestedCategory) {
    card.dataset.suggestedCategory = suggestedCategory;
  }
  card.draggable = true;
  card.tabIndex = 0;

  const img = document.createElement("img");
  img.src = `/api/thumb/${encodeURIComponent(filename)}`;
  img.alt = filename;
  img.loading = "lazy";
  img.decoding = "async";

  const actions = document.createElement("div");
  actions.className = "card-actions";

  card.appendChild(img);

  // Category hint visual (4C)
  if (suggestedCategory === "keep" || suggestedCategory === "trash") {
    card.classList.add("category-hint-" + suggestedCategory);
  }

  // Suggestion badge (always visible when status is "suggested")
  if (memoryStatus === "suggested" && suggestedName) {
    card.appendChild(_makeSuggestionBadge(card));
  }

  card.appendChild(actions);

  setCardActions(card, column);
  attachDrag(card);
  attachPreview(card);
  attachKeyboard(card);
  attachTooltip(card);
  attachSelect(card);

  return card;
}

function _makeSuggestionBadge(card) {
  const badge = document.createElement("div");
  badge.className = "suggestion-badge";

  const nameSpan = document.createElement("span");
  nameSpan.className = "suggestion-badge-name";
  nameSpan.textContent = card.dataset.suggestedName;
  nameSpan.title = card.dataset.suggestedName;

  const actionsDiv = document.createElement("div");
  actionsDiv.className = "suggestion-badge-actions";

  const acceptBtn = document.createElement("button");
  acceptBtn.className = "suggestion-badge-btn accept";
  acceptBtn.textContent = "✓";
  acceptBtn.title = "Accept & rename";
  acceptBtn.addEventListener("click", e => { e.stopPropagation(); acceptSuggestion(card); });

  const rejectBtn = document.createElement("button");
  rejectBtn.className = "suggestion-badge-btn reject";
  rejectBtn.textContent = "✕";
  rejectBtn.title = "Dismiss suggestion";
  rejectBtn.addEventListener("click", e => { e.stopPropagation(); rejectSuggestion(card); });

  const editBtn = document.createElement("button");
  editBtn.className = "suggestion-badge-btn edit";
  editBtn.textContent = "✎";
  editBtn.title = "Edit & rename";
  editBtn.addEventListener("click", e => { e.stopPropagation(); editSuggestion(card); });

  actionsDiv.appendChild(acceptBtn);
  actionsDiv.appendChild(rejectBtn);
  actionsDiv.appendChild(editBtn);
  badge.appendChild(nameSpan);
  badge.appendChild(actionsDiv);

  return badge;
}

// ── Card action buttons ──────────────────────────────────────────────────────
function setCardActions(card, column) {
  const actions = card.querySelector(".card-actions");
  actions.innerHTML = "";
  actions.classList.toggle("card-actions-triage", column === "unsorted");

  const renameBtn = makeActionBtn("Rename", "btn-rename", () => openRenameModal(card));
  const previewBtn = makeActionBtn("Preview", "btn-preview", () => openLightbox(card));
  const revealBtn = makeActionBtn("Finder", "btn-reveal", () => revealInFinder(card.dataset.filename));

  if (column === "unsorted") {
    const keepBtn = makeActionBtn("\u2190 Keep", "btn-keep", () => moveCard(card, "keep"));
    const trashBtn = makeActionBtn("Trash \u2192", "btn-trash", () => moveCard(card, "trash"));

    // Keep the triage controls in three predictable rows so the overlay is
    // easy to scan: file actions, optional suggestion, then the decision.
    actions.appendChild(makeActionRow(renameBtn, revealBtn, previewBtn));

    // Show "✨ AI Suggest" for unprocessed files
    if (card.dataset.memoryStatus === "new") {
      const suggestBtn = makeActionBtn("✨ Suggest", "btn-suggest", () => suggestSingle(card));
      actions.appendChild(makeActionRow(suggestBtn));
    }

    actions.appendChild(makeActionRow(keepBtn, trashBtn));
  } else {
    const undoBtn = makeActionBtn("\u21A9 Undo", "btn-undo", () => moveCard(card, "unsorted"));
    actions.appendChild(previewBtn);
    actions.appendChild(renameBtn);
    actions.appendChild(revealBtn);
    actions.appendChild(undoBtn);
  }
}

function makeActionRow(...buttons) {
  const row = document.createElement("div");
  row.className = "card-action-row";
  buttons.forEach(button => row.appendChild(button));
  return row;
}

function makeActionBtn(label, cls, onClick) {
  const btn = document.createElement("button");
  btn.className = `action-btn ${cls}`;
  btn.textContent = label;
  btn.addEventListener("click", e => {
    e.stopPropagation();
    onClick();
  });
  return btn;
}

// ── Move card between columns ────────────────────────────────────────────────
function moveCard(card, toColumn) {
  const filename = card.dataset.filename;
  const fromColumn = getCardColumn(card);

  if (fromColumn === toColumn) return;

  if (toColumn === "unsorted") {
    decisions.delete(filename);
  } else {
    decisions.set(filename, toColumn);
  }

  undoStack.push({ filename, from: fromColumn, to: toColumn });
  _persistUndoStack();

  const target = toColumn === "trash" ? cardsTrash
               : toColumn === "keep"  ? cardsKeep
               : cardsUnsorted;

  target.prepend(card);

  setCardActions(card, toColumn);
  updateCounts();
  saveState();
}

function getCardColumn(card) {
  if (cardsTrash.contains(card)) return "trash";
  if (cardsKeep.contains(card)) return "keep";
  return "unsorted";
}

// ── HTML5 Drag & Drop ───────────────────────────────────────────────────────
let draggedCard = null;

function attachDrag(card) {
  card.addEventListener("dragstart", e => {
    draggedCard = card;
    _lastDragStart = Date.now();
    card.classList.add("dragging");
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", card.dataset.filename);
    // Dragging a selected card: attach a Photos-style fanned stack of the
    // whole selection to the cursor (visual only — the drop still batchMoves).
    _clearGhostCanvas();
    if (selectedCards.has(card) && selectedCards.size > 1) {
      const ghost = buildBatchDragGhost([...selectedCards], selectedCards.size);
      if (ghost) {
        _ghostCanvas = ghost.canvas;
        e.dataTransfer.setDragImage(ghost.canvas, ghost.offsetX, ghost.offsetY);
      }
    }
  });

  card.addEventListener("dragend", () => {
    card.classList.remove("dragging");
    draggedCard = null;
    columns.forEach(c => c.classList.remove("drag-over"));
    _clearGhostCanvas();
  });
}

columns.forEach(col => {
  col.addEventListener("dragover", e => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    col.classList.add("drag-over");
  });

  col.addEventListener("dragleave", e => {
    if (!col.contains(e.relatedTarget)) {
      col.classList.remove("drag-over");
    }
  });

  col.addEventListener("drop", e => {
    e.preventDefault();
    col.classList.remove("drag-over");
    if (!draggedCard) return;

    const targetColumn = col.dataset.column;
    // Dragging a selected card moves the whole selection.
    if (selectedCards.has(draggedCard)) {
      batchMove(targetColumn);
    } else {
      moveCard(draggedCard, targetColumn);
    }
  });
});

// ── Multi-select batch triage ─────────────────────────────────────────────
// Click a card to toggle its selected state; Keep/Trash buttons (or dragging
// a selected card) act on the whole selection at once. Each card is moved via
// moveCard(), so every move still lands on the existing multi-level undo stack.
let _lastDragStart = 0;

function attachSelect(card) {
  card.addEventListener("click", () => {
    if (Date.now() - _lastDragStart < 350) return;
    toggleSelect(card);
  });
}

function toggleSelect(card) {
  if (selectedCards.has(card)) {
    selectedCards.delete(card);
    card.classList.remove("selected");
  } else {
    selectedCards.add(card);
    card.classList.add("selected");
  }
  updateBatchBar();
}

function clearSelection() {
  selectedCards.forEach(card => card.classList.remove("selected"));
  selectedCards.clear();
  updateBatchBar();
}

function updateBatchBar() {
  const n = selectedCards.size;
  batchCount.textContent = n ? `${n} selected` : "0 selected";
  batchKeepBtn.disabled = n === 0;
  batchTrashBtn.disabled = n === 0;
  batchBar.hidden = n === 0;
}

function batchMove(toColumn) {
  const cards = [...selectedCards].filter(card => document.contains(card));
  cards.forEach(card => moveCard(card, toColumn));
  // Keep the selection after the move: dropping (or clicking Keep/Trash)
  // should NOT deselect the batch — the user can keep re-dragging/re-
  // triaging the same set. Deselection is explicit: Escape, the ✕ Clear
  // button, re-sort, or Done (#76). moveCard() moves the same DOM node,
  // so selectedCards stays valid.
}

batchKeepBtn.addEventListener("click", () => batchMove("keep"));
batchTrashBtn.addEventListener("click", () => batchMove("trash"));
batchClearBtn.addEventListener("click", clearSelection);

// ── Batch drag ghost (Photos-style) ─────────────────────────────────────────
// When a drag starts on a selected card, fan the selected thumbnails out on
// the cursor like the macOS Photos app. HTML5 DnD only supports ONE drag
// image (setDragImage), so we composite the whole fanned stack onto a single
// canvas. Purely visual — drop/undo/batch logic is untouched.
// Fan geometry lives in ss_dcl_pure.js (SsDcl.batchFanLayout) — unit-tested.
const MAX_GHOST_TILES = 6;
const GHOST_TILE_W = SsDcl.GHOST_TILE_W;
const GHOST_TILE_H = SsDcl.GHOST_TILE_H;

function ghostRoundedRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.arcTo(x + w, y, x + w, y + r, r);
  ctx.lineTo(x + w, y + h - r);
  ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
  ctx.lineTo(x + r, y + h);
  ctx.arcTo(x, y + h, x, y + h - r, r);
  ctx.lineTo(x, y + r);
  ctx.arcTo(x, y, x + r, y, r);
  ctx.closePath();
}

// Composite the selected thumbnails into one fanned-stack canvas. Returns
// { canvas, offsetX, offsetY } for setDragImage, or null to keep the native
// ghost (e.g. no thumbnails decoded yet). cards = selected card elements in
// DOM order; total = number of cards in the selection (may exceed tiles).
let _ghostCanvas = null; // composite canvas currently attached for drag image

function _clearGhostCanvas() {
  if (_ghostCanvas) {
    _ghostCanvas.remove();
    _ghostCanvas = null;
  }
}

function buildBatchDragGhost(cards, total) {
  // Every card has an <img>; decoding state doesn't matter — drawImage on an
  // undecoded image simply paints nothing for that slot (graceful degrade).
  const drawable = cards.filter(card => card.querySelector("img"));
  if (drawable.length === 0) return null; // nothing usable — native ghost is fine
  const tileCount = Math.min(drawable.length, MAX_GHOST_TILES);
  const layout = SsDcl.batchFanLayout(tileCount);

  // Canvas size: fan extent + rotation slack, so rotated corners never clip.
  const maxRot = Math.max(...layout.map(t => Math.abs(t.rot))) * (Math.PI / 180);
  const dxMax = Math.max(...layout.map(t => Math.abs(t.dx)));
  const dyMax = Math.max(...layout.map(t => Math.abs(t.dy)));
  const extW = GHOST_TILE_W / 2 + (GHOST_TILE_H / 2) * Math.sin(maxRot);
  const extH = GHOST_TILE_H / 2 + (GHOST_TILE_W / 2) * Math.sin(maxRot);
  const half = Math.ceil(Math.max(dxMax + extW, dyMax + extH) + 8);
  const size = half * 2;
  const dpr = Math.min(window.devicePixelRatio || 1, 3);
  const canvas = document.createElement("canvas");
  canvas.width = Math.ceil(size * dpr);
  canvas.height = Math.ceil(size * dpr);
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.scale(dpr, dpr);
  ctx.translate(half, half); // fan center = drag hotspot later

  // Draw most-tilted tiles first so the straight-on "front" card is on top.
  const order = [...layout.keys()].sort(
    (a, b) => Math.abs(layout[b].rot) - Math.abs(layout[a].rot)
  );
  for (const i of order) {
    const img = drawable[i].querySelector("img");
    const t = layout[i];
    ctx.save();
    ctx.translate(t.dx, t.dy);
    ctx.rotate((t.rot * Math.PI) / 180);
    ghostRoundedRect(ctx, -GHOST_TILE_W / 2, -GHOST_TILE_H / 2, GHOST_TILE_W, GHOST_TILE_H, 8);
    ctx.fillStyle = "#fff";
    ctx.fill();
    ctx.save();
    ctx.clip();
    ctx.drawImage(img, -GHOST_TILE_W / 2, -GHOST_TILE_H / 2, GHOST_TILE_W, GHOST_TILE_H);
    ctx.restore();
    ghostRoundedRect(ctx, -GHOST_TILE_W / 2, -GHOST_TILE_H / 2, GHOST_TILE_W, GHOST_TILE_H, 8);
    ctx.strokeStyle = "rgba(30, 30, 30, 0.25)";
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.restore();
  }

  // Count badge: "+N" when the selection exceeds the rendered tiles (or some
  // thumbnails weren't decoded yet).
  if (total > tileCount) {
    const label = "+" + (total - tileCount);
    ctx.font = "600 16px -apple-system, system-ui, sans-serif";
    const tw = ctx.measureText(label).width;
    const bw = tw + 18;
    const bh = 24;
    const bx = -GHOST_TILE_W / 2 + 10;
    const by = GHOST_TILE_H / 2 - 26;
    ghostRoundedRect(ctx, bx, by, bw, bh, bh / 2);
    ctx.fillStyle = "rgba(255, 255, 255, 0.96)";
    ctx.fill();
    ctx.fillStyle = "#1c1c1e";
    ctx.textBaseline = "middle";
    ctx.fillText(label, bx + 10, by + bh / 2 + 0.5);
  }

  // Chrome only rasterizes a drag image if the canvas has already been
  // PAINTED — an unpainted canvas makes setDragImage fall back to the
  // browser's blank icon (that little "globe") instead of the stack. So
  // attach the canvas to the document offscreen (invisible but rendered)
  // and force layout BEFORE setDragImage; _clearGhostCanvas() removes it
  // again on dragend.
  canvas.style.cssText =
    "position:fixed;top:0;left:0;width:" + size + "px;height:" + size + "px;" +
    "opacity:0.002;pointer-events:none;";
  document.body.appendChild(canvas);
  canvas.getBoundingClientRect(); // force layout → rasterize the bitmap now
  try {
    ctx.getImageData(0, 0, 1, 1); // defensive: synchronously commit the bitmap
  } catch (_) {/* non-2d / tainted — ignore */}

  // Hotspot = center of the front card (canvas center in CSS pixels).
  return { canvas, offsetX: half, offsetY: half };
}

// ── Preview / Lightbox ───────────────────────────────────────────────────────
function attachPreview(card) {
  card.addEventListener("dblclick", e => {
    e.preventDefault();
    openLightbox(card);
  });
}

function openLightbox(card) {
  lightbox.dataset.currentFilename = card.dataset.filename;
  lightboxImg.src = `/api/image/${encodeURIComponent(card.dataset.filename)}`;
  lightboxImg.alt = card.dataset.filename;
  _updateLightboxBar(card.dataset.filename);
  lightbox.hidden = false;
}

function _lightboxNavigate(direction) {
  const allCards = [...document.querySelectorAll(".card")];
  const current = lightbox.dataset.currentFilename;
  const idx = allCards.findIndex(c => c.dataset.filename === current);
  if (idx < 0) return;
  const next = idx + direction;
  if (next < 0 || next >= allCards.length) return;
  const nextCard = allCards[next];
  const nextName = nextCard.dataset.filename;
  lightbox.dataset.currentFilename = nextName;
  lightboxImg.src = `/api/image/${encodeURIComponent(nextName)}`;
  lightboxImg.alt = nextName;
  _updateLightboxBar(nextName);
}

function closeLightbox() {
  lightbox.hidden = true;
  lightboxImg.src = "";
  lightboxRenameInput.hidden = true;
  lightboxRenameInput.classList.remove("error");
  lightboxRenameError.textContent = "";
  lightboxFilename.hidden = false;
}

document.getElementById("lightbox-close").addEventListener("click", closeLightbox);
document.querySelector(".lightbox-backdrop").addEventListener("click", closeLightbox);

// ── Reveal in Finder ────────────────────────────────────────────────────────
function revealInFinder(filename) {
  if (!filename) return;
  fetch("/api/reveal", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename }),
  })
    .then(r => r.json())
    .then(data => {
      statusMsg.textContent = data.ok
        ? "Revealed in Finder."
        : (data.error || "Could not reveal in Finder.");
    })
    .catch(() => {
      statusMsg.textContent = "Network error — could not reveal in Finder.";
    });
}

document.getElementById("lightbox-reveal-btn").addEventListener("click", () => {
  revealInFinder(lightbox.dataset.currentFilename);
});

// ── Card tooltip ───────────────────────────────────────────────────────────
function attachTooltip(card) {
  card.addEventListener("mouseenter", () => {
    cardTooltip.textContent = card.dataset.filename;
    cardTooltip.classList.add("visible");
    requestAnimationFrame(() => {
      const rect = card.getBoundingClientRect();
      const tooltipRect = cardTooltip.getBoundingClientRect();
      let left = rect.left + rect.width / 2 - tooltipRect.width / 2;
      // Anchor above the card image, not the card's bottom edge, so the
      // tooltip never overlaps the suggestion badge below the image.
      const img = card.querySelector("img");
      const anchor = img ? img.getBoundingClientRect() : rect;
      let top = anchor.bottom - tooltipRect.height - 10;
      if (left < 4) left = 4;
      if (left + tooltipRect.width > window.innerWidth - 4) {
        left = window.innerWidth - tooltipRect.width - 4;
      }
      if (top < rect.top + 4) {
        top = rect.top + 4;
      }
      cardTooltip.style.left = left + "px";
      cardTooltip.style.top = top + "px";
    });
  });
  card.addEventListener("mouseleave", () => {
    cardTooltip.classList.remove("visible");
  });
}

// ── Lightbox rename bar ────────────────────────────────────────────────────
function _updateLightboxBar(filename) {
  lightboxFilename.textContent = filename;
  lightboxRenameInput.value = filename;
  lightboxRenameInput.hidden = true;
  lightboxFilename.hidden = false;
  lightboxRenameError.textContent = "";
  lightboxRenameInput.classList.remove("error");
  lightboxBar.style.minWidth = "";
}

lightboxFilename.addEventListener("click", () => _startLightboxRename());
lightboxFilename.addEventListener("keydown", e => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); _startLightboxRename(); }
});

function _startLightboxRename() {
  const filename = lightbox.dataset.currentFilename;
  const bar = document.querySelector(".lightbox-bar");
  bar.style.minWidth = bar.offsetWidth + "px";
  lightboxFilename.hidden = true;
  lightboxRenameInput.hidden = false;
  lightboxRenameInput.value = filename;
  lightboxRenameInput.classList.remove("error");
  lightboxRenameError.textContent = "";
  lightboxRenameInput.focus();
  const dotIdx = filename.lastIndexOf(".");
  if (dotIdx > 0) {
    lightboxRenameInput.setSelectionRange(0, dotIdx);
  } else {
    lightboxRenameInput.select();
  }
}

lightboxRenameInput.addEventListener("keydown", e => {
  if (e.key === "Enter") { e.preventDefault(); _confirmLightboxRename(); }
  if (e.key === "Escape") { e.stopPropagation(); _cancelLightboxRename(); }
});

lightboxRenameInput.addEventListener("blur", () => {
  if (!lightboxRenameInput.hidden) _confirmLightboxRename();
});

function _cancelLightboxRename() {
  lightboxRenameInput.hidden = true;
  lightboxRenameInput.classList.remove("error");
  lightboxRenameError.textContent = "";
  lightboxFilename.hidden = false;
  lightboxBar.style.minWidth = "";
}

function applyRenameToCard(card, oldName, newName) {
  // Shared post-rename DOM/state dance (issue #101): used by the lightbox
  // rename, the rename modal, and acceptSuggestion.
  const col = getCardColumn(card);
  if (col === "unsorted") {
    decisions.delete(oldName);
  } else {
    decisions.delete(oldName);
    decisions.set(newName, col);
  }
  card.dataset.filename = newName;
  // A rename always transitions status to "renamed".
  // fingerprint stays unchanged — it's the stable identity key
  // (original macOS name + size), not a derived filename attribute.
  card.dataset.memoryStatus = "renamed";
  card.dataset.suggestedName = "";
  const badge = card.querySelector(".suggestion-badge");
  if (badge) badge.remove();
  // Clear category hint
  card.classList.remove("category-hint-keep", "category-hint-trash");
  delete card.dataset.suggestedCategory;
  const cardImg = card.querySelector("img");
  cardImg.alt = newName;
  cardImg.src = `/api/thumb/${encodeURIComponent(newName)}?t=${Date.now()}`;
  setCardActions(card, col);
  updateCounts();
  saveState();
}

function _confirmLightboxRename() {
  if (lightboxRenameInput.disabled || lightboxRenameInput.hidden || lightbox.hidden) return;
  const oldName = lightbox.dataset.currentFilename;
  const newName = lightboxRenameInput.value.trim();

  if (!newName) {
    lightboxRenameInput.classList.add("error");
    lightboxRenameError.textContent = "Filename cannot be empty.";
    lightboxRenameInput.focus();
    return;
  }
  if (newName === oldName) {
    _cancelLightboxRename();
    return;
  }
  if (newName !== SsDcl.Path_name(newName)) {
    lightboxRenameInput.classList.add("error");
    lightboxRenameError.textContent = "Filename must not contain path separators.";
    lightboxRenameInput.focus();
    return;
  }

  lightboxRenameInput.disabled = true;
  lightboxRenameError.textContent = "";

  fetch("/api/rename", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ old_name: oldName, new_name: newName }),
  })
    .then(r => r.json())
    .then(data => {
      lightboxRenameInput.disabled = false;
      if (!data.ok) {
        lightboxRenameInput.classList.add("error");
        lightboxRenameError.textContent = data.error || "Rename failed.";
        lightboxRenameInput.focus();
        return;
      }
      const card = document.querySelector(`[data-filename="${CSS.escape(oldName)}"]`);
      if (card) {
        applyRenameToCard(card, oldName, newName);
      }
      lightbox.dataset.currentFilename = newName;
      lightboxImg.src = `/api/image/${encodeURIComponent(newName)}?t=${Date.now()}`;
      lightboxImg.alt = newName;
      _updateLightboxBar(newName);
    })
    .catch(() => {
      lightboxRenameInput.disabled = false;
      lightboxRenameInput.classList.add("error");
      lightboxRenameError.textContent = "Network error — please try again.";
      lightboxRenameInput.focus();
    });
}

// ── Keyboard shortcuts ───────────────────────────────────────────────────────
function attachKeyboard(card) {
  card.addEventListener("keydown", e => {
    const col = getCardColumn(card);
    if (col === "unsorted") {
      if (e.key === "ArrowLeft") { e.preventDefault(); moveCard(card, "keep"); }
      if (e.key === "ArrowRight") { e.preventDefault(); moveCard(card, "trash"); }
    } else {
      if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
        e.preventDefault();
        moveCard(card, "unsorted");
      }
    }
  });
}

document.addEventListener("keydown", e => {
  if (!lightbox.hidden) {
    if (document.activeElement === lightboxRenameInput) {
      return;
    }
    if (e.key === "ArrowLeft") { e.preventDefault(); _lightboxNavigate(-1); return; }
    if (e.key === "ArrowRight") { e.preventDefault(); _lightboxNavigate(1); return; }
  }
  if (e.key === "Escape") {
    if (!lightbox.hidden && !lightboxRenameInput.hidden) {
      _cancelLightboxRename();
      return;
    }
    if (!lightbox.hidden) { closeLightbox(); return; }
    if (!confirmModal.hidden) { closeModal(); return; }
    if (!renameModal.hidden) { closeRenameModal(); return; }
    if (!settingsMenu.hidden) { closeSettingsMenu(); return; }
    if (selectedCards.size > 0) { clearSelection(); return; }
  }

  if ((e.metaKey || e.ctrlKey) && e.key === "z") {
    e.preventDefault();
    performUndo();
  }
});

// ── AI Suggest (single card) ──────────────────────────────────────────────────
function suggestSingle(card) {
  const fp = card.dataset.fingerprint;
  if (!fp) return;
  suggestBatch([fp]);
}

// ── AI Suggest (batch) ──────────────────────────────────────────────────────
function suggestBatch(fingerprints) {
  if (fingerprints.length === 0) return;

  _suggestCancelled = false;

  // Chunk requests (issue #81): the backend parallelizes LLM calls per
  // chunk, so a larger chunk cuts round trips without serializing anything.
  // Chunking logic lives in ss_dcl_pure.js (SsDcl.chunked) — unit-tested.
  const chunkSize = 5;
  const chunks = SsDcl.chunked(fingerprints, chunkSize);
  let completed = 0;
  let firstError = null;
  let failedCount = 0;

  function abortBatch(message) {
    suggestProgressFill.style.width = "100%";
    suggestProgressText.textContent = message;
    statusMsg.textContent = message;
    setTimeout(() => { suggestProgress.hidden = true; suggestAllBtn.disabled = false; }, 4000);
  }

  function processChunk(chunkIdx) {
    if (_suggestCancelled) {
      suggestProgressText.textContent = `Cancelled (${completed} processed)`;
      setTimeout(() => { suggestProgress.hidden = true; suggestAllBtn.disabled = false; }, 1500);
      return;
    }
    if (chunkIdx >= chunks.length) {
      suggestProgressFill.style.width = "100%";
      if (completed === 0 && firstError) {
        suggestProgressText.textContent = firstError;
        statusMsg.textContent = firstError;
        setTimeout(() => { suggestProgress.hidden = true; suggestAllBtn.disabled = false; }, 4000);
      } else if (completed === 0) {
        suggestProgressText.textContent = providerErrorCopy();
        setTimeout(() => { suggestProgress.hidden = true; suggestAllBtn.disabled = false; }, 3000);
      } else {
        if (failedCount > 0) {
          suggestProgressText.textContent = `Done! ${completed} processed — ${failedCount} file${failedCount > 1 ? "s" : ""} failed`;
        } else {
          suggestProgressText.textContent = `Done! ${completed} processed`;
        }
        if (firstError) {
          statusMsg.textContent = firstError;
        }
        setTimeout(() => { suggestProgress.hidden = true; suggestAllBtn.disabled = false; }, 2500);
      }
      return;
    }

    const chunk = chunks[chunkIdx];

    fetch("/api/suggest-names", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fingerprints: chunk }),
    })
      .then(r => r.json())
      .then(data => {
        // Backend-level error is fatal: abort the rest of the batch.
        if (data.error) {
          if (!firstError) firstError = data.error;
          abortBatch(data.error);
          return;
        }
        const suggestions = data.suggestions || {};
        failedCount += (data.failures || []).length;
        for (const [fp, suggestedName] of Object.entries(suggestions)) {
          const card = document.querySelector(`[data-fingerprint="${CSS.escape(fp)}"]`);
          if (card) {
            card.dataset.memoryStatus = "suggested";
            card.dataset.suggestedName = suggestedName;
            const oldBadge = card.querySelector(".suggestion-badge");
            if (oldBadge) oldBadge.remove();
            const badge = _makeSuggestionBadge(card);
            const actions = card.querySelector(".card-actions");
            card.insertBefore(badge, actions);
            setCardActions(card, getCardColumn(card));
          }
          completed++;
        }
        const nextIdx = chunkIdx + 1;
        const pct = Math.round((Math.min((nextIdx) * chunkSize, fingerprints.length) / fingerprints.length) * 100);
        suggestProgressFill.style.width = pct + "%";
        suggestProgressText.textContent = `${Math.min(nextIdx * chunkSize, fingerprints.length)} / ${fingerprints.length}`;
        processChunk(nextIdx);
      })
      .catch(() => {
        if (!firstError) firstError = providerErrorCopy();
        const nextIdx = chunkIdx + 1;
        processChunk(nextIdx);
      });
  }

  // Pre-flight circuit breaker: bail out before any per-file calls if
  // LiteRT is down (avoids 3 futile retries per file on connection refused).
  fetch("/api/llm/health")
    .then(r => r.json())
    .then(h => {
      if (!h.ok) {
        statusMsg.textContent = h.error || providerErrorCopy();
        suggestAllBtn.disabled = false;
        suggestProgress.hidden = true;
        suggestProgressFill.style.width = "0%";
        suggestProgressText.textContent = "0 / " + fingerprints.length;
        return;
      }
      suggestAllBtn.disabled = true;
      suggestProgress.hidden = false;
      suggestProgressFill.style.width = "0%";
      suggestProgressText.textContent = `0 / ${fingerprints.length}`;
      processChunk(0);
    })
    .catch(() => {
      statusMsg.textContent = providerErrorCopy();
      suggestAllBtn.disabled = false;
      suggestProgress.hidden = true;
    });
}

// ── Accept suggestion (rename file to suggested name) ───────────────────────
function acceptSuggestion(card) {
  const fp = card.dataset.fingerprint;
  if (!fp) return;

  fetch("/api/accept-suggestion", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fingerprint: fp }),
  })
    .then(r => r.json())
    .then(data => {
      if (!data.ok) {
        alert(data.error || "Failed to accept suggestion");
        return;
      }
      const oldName = card.dataset.filename;
      const newName = data.new_name;
      applyRenameToCard(card, oldName, newName);
    })
    .catch(() => alert("Network error — please try again."));
}

// ── Reject suggestion (dismiss, mark as ignored) ─────────────────────────────
function rejectSuggestion(card) {
  const fp = card.dataset.fingerprint;
  if (!fp) return;

  fetch("/api/reject-suggestion", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fingerprint: fp }),
  })
    .then(r => r.json())
    .then(data => {
      if (!data.ok) return;
      card.dataset.memoryStatus = "ignored";
      card.dataset.suggestedName = "";
      const badge = card.querySelector(".suggestion-badge");
      if (badge) badge.remove();
      // Clear category hint
      card.classList.remove("category-hint-keep", "category-hint-trash");
      delete card.dataset.suggestedCategory;
      setCardActions(card, getCardColumn(card));
    })
    .catch(() => {});
}

// ── Edit suggestion (open rename modal pre-filled with suggested name) ────────
function editSuggestion(card) {
  renameTarget = card;
  renameInput.value = card.dataset.suggestedName || card.dataset.filename;
  renameError.textContent = "";
  renameModal.hidden = false;
  const dotIdx = renameInput.value.lastIndexOf(".");
  renameInput.focus();
  if (dotIdx > 0) {
    renameInput.setSelectionRange(0, dotIdx);
  }
}

// ── Cancel suggest button ────────────────────────────────────────────────────
let _suggestCancelled = false;
suggestCancelBtn.addEventListener("click", () => {
  _suggestCancelled = true;
});

// ── Suggest All button (inside the settings menu) ─────────────────────────────
suggestAllBtn.addEventListener("click", () => {
  const newFps = [...document.querySelectorAll(".card")]
    .filter(c => c.dataset.memoryStatus === "new")
    .map(c => c.dataset.fingerprint)
    .filter(Boolean);
  if (newFps.length === 0) {
    statusMsg.textContent = "No new screenshots to suggest names for.";
    return;
  }
  closeSettingsMenu();
  suggestBatch(newFps);
});

// ── Settings dropdown ──────────────────────────────────────────────────────────
settingsBtn.addEventListener("click", () => {
  if (!settingsMenu.hidden) { closeSettingsMenu(); return; }
  // Load current settings into form
  settingsProvider.value = llmSettings.llm_provider || "litert";
  settingsModel.value = llmSettings.llm_model || "gemma4-e2b";
  settingsModel.placeholder = LLM_PROVIDER_MODELS[settingsProvider.value] || "gemma4-e2b";
  settingsAuto.checked = llmSettings.auto_suggest || false;
  const pruneAge = document.getElementById("settings-prune-age");
  if (pruneAge) pruneAge.value = llmSettings.prune_max_age_days || 90;
  settingsMenu.hidden = false;
});

// When the model field holds a legacy/default id, snap it to the LiteRT form.
settingsProvider.addEventListener("change", () => {
  const def = LLM_PROVIDER_MODELS[settingsProvider.value] || "gemma4-e2b";
  settingsModel.placeholder = def;
  if (settingsModel.value.trim() === "gemma4-e2b" || settingsModel.value.trim() === "gemma4:e2b") {
    settingsModel.value = def;
  }
});

function closeSettingsMenu() {
  settingsMenu.hidden = true;
}

settingsCancel.addEventListener("click", closeSettingsMenu);
// Dropdown behavior: clicking outside the menu (or the ⚙ button) closes it.
document.addEventListener("click", e => {
  if (settingsMenu.hidden) return;
  if (settingsMenu.contains(e.target) || settingsBtn.contains(e.target)) return;
  closeSettingsMenu();
});

settingsSave.addEventListener("click", () => {
  const pruneVal = parseInt(document.getElementById("settings-prune-age")?.value || "90", 10);
  const newSettings = {
    llm_provider: settingsProvider.value,
    llm_model: settingsModel.value.trim() || "gemma4-e2b",
    auto_suggest: settingsAuto.checked,
    prune_max_age_days: isNaN(pruneVal) || pruneVal < 1 ? 90 : pruneVal,
  };

  fetch("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(newSettings),
  })
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        llmSettings = newSettings;
        closeSettingsMenu();
        refreshLLMServerButton();
      }
    })
    .catch(() => {});
});

// ── Undo ─────────────────────────────────────────────────────────────────────
function _persistUndoStack() {
  try { sessionStorage.setItem("undoStack", JSON.stringify(undoStack)); } catch (_) {}
}

undoBtn.addEventListener("click", () => performUndo());
function performUndo() {
  if (undoStack.length === 0) return;
  const action = undoStack.pop();
  const card = document.querySelector(`[data-filename="${CSS.escape(action.filename)}"]`);
  if (!card) {
    undoStack.push(action);
    return;
  }
  _persistUndoStack();

  if (action.from === "unsorted") {
    decisions.delete(action.filename);
  } else {
    decisions.set(action.filename, action.from);
  }

  const target = action.from === "trash" ? cardsTrash
               : action.from === "keep"  ? cardsKeep
               : cardsUnsorted;
  target.prepend(card);

  setCardActions(card, action.from);
  updateCounts();
  saveState();
}

// ── Counts & status ──────────────────────────────────────────────────────────
function updateCounts() {
  const { keep: nKeep, trash: nTrash, unsorted: nUnsorted, total } = SsDcl.computeCounts(decisions, totalCards);

  countUnsorted.textContent = nUnsorted;
  countTrash.textContent    = nTrash;
  countKeep.textContent     = nKeep;

  if (nTrash + nKeep === 0) {
    statusMsg.textContent = `${total} screenshot${total !== 1 ? "s" : ""} \u2014 drag to sort`;
  } else {
    statusMsg.textContent = `${nTrash + nKeep}/${total} sorted \u00B7 ${nTrash} to trash`;
  }

  undoBtn.disabled = undoStack.length === 0;
  doneBtn.disabled = nTrash === 0;
}

// ── Rename modal ──────────────────────────────────────────────────────────────
function openRenameModal(card) {
  renameTarget = card;
  renameInput.value = card.dataset.filename;
  renameError.textContent = "";
  renameModal.hidden = false;
  const dotIdx = card.dataset.filename.lastIndexOf(".");
  renameInput.focus();
  if (dotIdx > 0) {
    renameInput.setSelectionRange(0, dotIdx);
  }
}

function closeRenameModal() {
  renameModal.hidden = true;
  renameTarget = null;
}

renameCancel.addEventListener("click", closeRenameModal);
renameModal.addEventListener("click", e => {
  if (e.target === renameModal) closeRenameModal();
});

renameConfirm.addEventListener("click", () => {
  if (!renameTarget) return;
  const oldName = renameTarget.dataset.filename;
  const newName = renameInput.value.trim();
  if (!newName) {
    renameError.textContent = "Filename cannot be empty.";
    return;
  }
  if (newName === oldName) {
    closeRenameModal();
    return;
  }
  if (newName !== SsDcl.Path_name(newName)) {
    renameError.textContent = "Filename must not contain path separators.";
    return;
  }
  renameError.textContent = "";
  renameConfirm.disabled = true;

  fetch("/api/rename", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ old_name: oldName, new_name: newName }),
  })
    .then(r => r.json())
    .then(data => {
      renameConfirm.disabled = false;
      if (!data.ok) {
        renameError.textContent = data.error || "Rename failed.";
        return;
      }
      applyRenameToCard(renameTarget, oldName, newName);
      closeRenameModal();
    })
    .catch(() => {
      renameConfirm.disabled = false;
      renameError.textContent = "Network error — please try again.";
    });
});

renameInput.addEventListener("keydown", e => {
  if (e.key === "Enter") { e.preventDefault(); renameConfirm.click(); }
  if (e.key === "Escape") closeRenameModal();
});

// Path_name lives in ss_dcl_pure.js (SsDcl.Path_name) — unit-tested.

// ── Done button / modal ──────────────────────────────────────────────────────
doneBtn.addEventListener("click", () => {
  const nTrash = cardsTrash.querySelectorAll(".card").length;
  if (nTrash === 0) return;

  modalTitle.textContent = `Move ${nTrash} screenshot${nTrash !== 1 ? "s" : ""} to Trash?`;
  confirmModal.hidden = false;
});

function closeModal() {
  confirmModal.hidden = true;
}

modalCancel.addEventListener("click", closeModal);
confirmModal.addEventListener("click", e => {
  if (e.target === confirmModal) closeModal();
});

modalConfirm.addEventListener("click", () => {
  closeModal();

  const toTrash = [...cardsTrash.querySelectorAll(".card")]
    .map(c => c.dataset.filename);

  if (toTrash.length === 0) return;

  doneBtn.disabled = true;
  statusMsg.textContent = "Moving to Trash\u2026";

  fetch("/api/done", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filenames: toTrash }),
  })
    .then(r => r.json())
    .then(data => {
      if (!data.ok && data.errors && data.errors.length > 0) {
        alert("Some files could not be moved:\n" + data.errors.join("\n"));
      }

      const failed = new Set();
      (data.errors || []).forEach(e => {
        const parts = e.split(":");
        const name = parts.length > 1 ? parts[0].trim() : e.trim();
        if (name) failed.add(name);
      });
      toTrash.forEach(filename => {
        if (!failed.has(filename)) {
          const card = cardsTrash.querySelector(`[data-filename="${CSS.escape(filename)}"]`);
          if (card) { card.remove(); totalCards--; }
          decisions.delete(filename);
        }
      });

      undoStack.length = 0;
      clearSelection();

      updateCounts();
      saveState();

      const remaining = document.querySelectorAll(".card").length;
      if (remaining === 0) {
        emptyMsg.hidden = false;
        statusMsg.textContent = "All done!";
        doneBtn.disabled = true;
      }
    })
    .catch(() => {
      alert("Network error \u2014 please try again.");
      doneBtn.disabled = false;
      updateCounts();
    });
});
