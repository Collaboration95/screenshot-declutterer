const decisions = new Map();
const undoStack = [];
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

const settingsModal   = document.getElementById("settings-modal");
const settingsProvider = document.getElementById("settings-provider");
const settingsModel   = document.getElementById("settings-model");
const settingsAuto    = document.getElementById("settings-auto");
const settingsCancel  = document.getElementById("settings-cancel");
const settingsSave    = document.getElementById("settings-save");

const renameModal   = document.getElementById("rename-modal");
const renameInput   = document.getElementById("rename-input");
const renameCancel  = document.getElementById("rename-cancel");
const renameConfirm = document.getElementById("rename-confirm");
const renameError   = document.getElementById("rename-error");
let renameTarget = null;

const columns = [colTrash, colUnsorted, colKeep];

// ── Sanitise filenames for safe DOM insertion ────────────────────────────────
function sanitise(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// ── Settings state (loaded on init) ────────────────────────────────────────────
let llmSettings = { llm_provider: "ollama", llm_model: "gemma4:e2b", auto_suggest: false };

function loadSettings() {
  return fetch("/api/settings")
    .then(r => r.json())
    .then(s => { llmSettings = s; })
    .catch(() => {});
}

// ── Bootstrap ────────────────────────────────────────────────────────────────
function init() {
  loadSettings().then(() => {
    fetch("/api/state")
      .then(r => r.json())
      .then(state => loadScreenshots(state.decisions || {}))
      .catch(() => loadScreenshots({}));
  });
}

function loadScreenshots(savedDecisions) {
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
        target.appendChild(makeCard(f.name, col, f.fingerprint, f.memory_status, f.suggested_name));
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
function makeCard(filename, column, fingerprint, memoryStatus, suggestedName) {
  const card = document.createElement("article");
  card.className = "card";
  card.setAttribute("role", "listitem");
  card.setAttribute("aria-label", filename);
  card.dataset.filename = filename;
  card.dataset.fingerprint = fingerprint || "";
  card.dataset.memoryStatus = memoryStatus || "";
  card.dataset.suggestedName = suggestedName || "";
  card.draggable = true;
  card.tabIndex = 0;

  const img = document.createElement("img");
  img.src = `/api/thumb/${encodeURIComponent(filename)}`;
  img.alt = sanitise(filename);
  img.loading = "lazy";
  img.decoding = "async";

  const actions = document.createElement("div");
  actions.className = "card-actions";

  card.appendChild(img);

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

  const renameBtn = makeActionBtn("Rename", "btn-rename", () => openRenameModal(card));
  const previewBtn = makeActionBtn("Preview", "btn-preview", () => openLightbox(card));

  if (column === "unsorted") {
    const keepBtn = makeActionBtn("\u2190 Keep", "btn-keep", () => moveCard(card, "keep"));
    const trashBtn = makeActionBtn("Trash \u2192", "btn-trash", () => moveCard(card, "trash"));
    actions.appendChild(keepBtn);
    actions.appendChild(previewBtn);
    actions.appendChild(renameBtn);
    actions.appendChild(trashBtn);

    // Show "✨ AI Suggest" for unprocessed files
    if (card.dataset.memoryStatus === "new") {
      const suggestBtn = makeActionBtn("✨ Suggest", "btn-suggest", () => suggestSingle(card));
      // Insert after rename, before trash
      const trashRef = actions.querySelector(".btn-trash");
      if (trashRef) actions.insertBefore(suggestBtn, trashRef);
    }
  } else {
    const undoBtn = makeActionBtn("\u21A9 Undo", "btn-undo", () => moveCard(card, "unsorted"));
    actions.appendChild(previewBtn);
    actions.appendChild(renameBtn);
    actions.appendChild(undoBtn);
  }
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
    card.classList.add("dragging");
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", card.dataset.filename);
  });

  card.addEventListener("dragend", () => {
    card.classList.remove("dragging");
    draggedCard = null;
    columns.forEach(c => c.classList.remove("drag-over"));
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
    moveCard(draggedCard, targetColumn);
  });
});

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
  lightboxImg.alt = sanitise(card.dataset.filename);
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
  lightboxImg.alt = sanitise(nextName);
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

// ── Card tooltip ───────────────────────────────────────────────────────────
function attachTooltip(card) {
  card.addEventListener("mouseenter", () => {
    cardTooltip.textContent = card.dataset.filename;
    cardTooltip.classList.add("visible");
    requestAnimationFrame(() => {
      const rect = card.getBoundingClientRect();
      const tooltipRect = cardTooltip.getBoundingClientRect();
      let left = rect.left + rect.width / 2 - tooltipRect.width / 2;
      let top = rect.bottom - tooltipRect.height - 10;
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
  if (newName !== Path_name(newName)) {
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
        const cardImg = card.querySelector("img");
        cardImg.alt = newName;
        cardImg.src = `/api/thumb/${encodeURIComponent(newName)}?t=${Date.now()}`;
        setCardActions(card, col);
        updateCounts();
        saveState();
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
    if (!settingsModal.hidden) { closeSettingsModal(); return; }
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
  suggestAllBtn.disabled = true;
  suggestProgress.hidden = false;
  suggestProgressFill.style.width = "0%";
  suggestProgressText.textContent = `0 / ${fingerprints.length}`;

  const chunkSize = 1;
  let completed = 0;
  let firstError = null;

  function processChunk(startIdx) {
    if (_suggestCancelled) {
      suggestProgressText.textContent = `Cancelled (${completed} processed)`;
      setTimeout(() => { suggestProgress.hidden = true; suggestAllBtn.disabled = false; }, 1500);
      return;
    }
    if (startIdx >= fingerprints.length) {
      suggestProgressFill.style.width = "100%";
      if (completed === 0 && firstError) {
        suggestProgressText.textContent = firstError;
        statusMsg.textContent = firstError;
        setTimeout(() => { suggestProgress.hidden = true; suggestAllBtn.disabled = false; }, 4000);
      } else if (completed === 0) {
        suggestProgressText.textContent = "No suggestions generated. Is Ollama running?";
        setTimeout(() => { suggestProgress.hidden = true; suggestAllBtn.disabled = false; }, 3000);
      } else {
        suggestProgressText.textContent = `Done! ${completed} processed`;
        if (firstError) {
          statusMsg.textContent = firstError;
        }
        setTimeout(() => { suggestProgress.hidden = true; suggestAllBtn.disabled = false; }, 1500);
      }
      return;
    }

    const chunk = fingerprints.slice(startIdx, startIdx + chunkSize);

    fetch("/api/suggest-names", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fingerprints: chunk }),
    })
      .then(r => r.json())
      .then(data => {
        // Check for backend-level error (e.g. unsupported provider)
        if (data.error) {
          if (!firstError) firstError = data.error;
        }
        const suggestions = data.suggestions || {};
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
        const nextIdx = startIdx + chunkSize;
        const pct = Math.round((Math.min(nextIdx, fingerprints.length) / fingerprints.length) * 100);
        suggestProgressFill.style.width = pct + "%";
        suggestProgressText.textContent = `${Math.min(nextIdx, fingerprints.length)} / ${fingerprints.length}`;
        processChunk(nextIdx);
      })
      .catch(() => {
        if (!firstError) firstError = "Couldn't reach Ollama — is it running?";
        const nextIdx = startIdx + chunkSize;
        processChunk(nextIdx);
      });
  }

  processChunk(0);
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
      const col = getCardColumn(card);
      if (col === "unsorted") {
        decisions.delete(oldName);
      } else {
        decisions.delete(oldName);
        decisions.set(newName, col);
      }
      card.dataset.filename = newName;
      card.dataset.memoryStatus = "renamed";
      card.dataset.suggestedName = "";
      const cardImg = card.querySelector("img");
      cardImg.alt = newName;
      cardImg.src = `/api/thumb/${encodeURIComponent(newName)}?t=${Date.now()}`;
      // Remove badge
      const badge = card.querySelector(".suggestion-badge");
      if (badge) badge.remove();
      setCardActions(card, col);
      updateCounts();
      saveState();
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

// ── Suggest All button ───────────────────────────────────────────────────────
suggestAllBtn.addEventListener("click", () => {
  const newFps = [...document.querySelectorAll(".card")]
    .filter(c => c.dataset.memoryStatus === "new")
    .map(c => c.dataset.fingerprint)
    .filter(Boolean);
  if (newFps.length === 0) {
    statusMsg.textContent = "No new screenshots to suggest names for.";
    return;
  }
  suggestBatch(newFps);
});

// ── Settings modal ────────────────────────────────────────────────────────────
settingsBtn.addEventListener("click", () => {
  // Load current settings into form
  settingsProvider.value = llmSettings.llm_provider || "ollama";
  settingsModel.value = llmSettings.llm_model || "gemma4:e2b";
  settingsAuto.checked = llmSettings.auto_suggest || false;
  settingsModal.hidden = false;
});

function closeSettingsModal() {
  settingsModal.hidden = true;
}

settingsCancel.addEventListener("click", closeSettingsModal);
settingsModal.addEventListener("click", e => {
  if (e.target === settingsModal) closeSettingsModal();
});

settingsSave.addEventListener("click", () => {
  const newSettings = {
    llm_provider: settingsProvider.value,
    llm_model: settingsModel.value.trim() || "gemma4:e2b",
    auto_suggest: settingsAuto.checked,
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
        closeSettingsModal();
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
  let nKeep = 0, nTrash = 0;
  for (const v of decisions.values()) {
    if (v === "keep") nKeep++;
    else nTrash++;
  }
  const nUnsorted = totalCards - nKeep - nTrash;
  const total     = totalCards;

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
  if (newName !== Path_name(newName)) {
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
      const col = getCardColumn(renameTarget);
      if (col === "unsorted") {
        decisions.delete(oldName);
      } else {
        decisions.delete(oldName);
        decisions.set(newName, col);
      }
      renameTarget.dataset.filename = newName;
      // A rename always transitions status to "renamed".
      // fingerprint stays unchanged — it's the stable identity key
      // (original macOS name + size), not a derived filename attribute.
      renameTarget.dataset.memoryStatus = "renamed";
      renameTarget.dataset.suggestedName = "";
      const badge = renameTarget.querySelector(".suggestion-badge");
      if (badge) badge.remove();
      const cardImg = renameTarget.querySelector("img");
      cardImg.alt = newName;
      cardImg.src = `/api/thumb/${encodeURIComponent(newName)}?t=${Date.now()}`;
      setCardActions(renameTarget, col);
      updateCounts();
      saveState();
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

function Path_name(filename) {
  return filename.split("/").pop().split("\\").pop();
}

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
