// ── State ─────────────────────────────────────────────────────────────────────
// decisions: Map<filename, 'keep' | 'trash'>
const decisions = new Map();
const undoStack = []; // { filename, from, to }

// ── DOM refs ─────────────────────────────────────────────────────────────────
const cardsUnsorted = document.getElementById("cards-unsorted");
const cardsTrash    = document.getElementById("cards-trash");
const cardsKeep     = document.getElementById("cards-keep");

const colUnsorted = document.getElementById("col-unsorted");
const colTrash    = document.getElementById("col-trash");
const colKeep     = document.getElementById("col-keep");

const countUnsorted = document.getElementById("count-unsorted");
const countTrash    = document.getElementById("count-trash");
const countKeep     = document.getElementById("count-keep");

const undoBtn   = document.getElementById("undo-btn");
const doneBtn   = document.getElementById("done-btn");
const statusMsg = document.getElementById("status-msg");
const emptyMsg  = document.getElementById("empty-msg");

const lightbox    = document.getElementById("lightbox");
const lightboxImg = document.getElementById("lightbox-img");

const confirmModal = document.getElementById("confirm-modal");
const modalTitle   = document.getElementById("modal-title");
const modalCancel  = document.getElementById("modal-cancel");
const modalConfirm = document.getElementById("modal-confirm");

const columns = [colTrash, colUnsorted, colKeep];

// ── Bootstrap ────────────────────────────────────────────────────────────────
fetch("/api/screenshots")
  .then(r => r.json())
  .then(filenames => {
    if (filenames.length === 0) {
      emptyMsg.hidden = false;
      return;
    }
    filenames.forEach(f => cardsUnsorted.appendChild(makeCard(f, "unsorted")));
    updateCounts();
  })
  .catch(() => {
    statusMsg.textContent = "Failed to load screenshots.";
  });

// ── Card factory ─────────────────────────────────────────────────────────────
function makeCard(filename, column) {
  const card = document.createElement("article");
  card.className = "card";
  card.dataset.filename = filename;
  card.draggable = true;
  card.tabIndex = 0;

  const img = document.createElement("img");
  img.src = `/api/image/${encodeURIComponent(filename)}`;
  img.alt = filename;
  img.loading = "lazy";

  const actions = document.createElement("div");
  actions.className = "card-actions";

  card.appendChild(img);
  card.appendChild(actions);

  setCardActions(card, column);
  attachDrag(card);
  attachPreview(card);
  attachKeyboard(card);

  return card;
}

// ── Card action buttons ──────────────────────────────────────────────────────
function setCardActions(card, column) {
  const actions = card.querySelector(".card-actions");
  actions.innerHTML = "";

  if (column === "unsorted") {
    const keepBtn = makeActionBtn("\u2190 Keep", "btn-keep", () => moveCard(card, "keep"));
    const previewBtn = makeActionBtn("Preview", "btn-preview", () => openLightbox(card));
    const trashBtn = makeActionBtn("Trash \u2192", "btn-trash", () => moveCard(card, "trash"));
    actions.appendChild(keepBtn);
    actions.appendChild(previewBtn);
    actions.appendChild(trashBtn);
  } else {
    const previewBtn = makeActionBtn("Preview", "btn-preview", () => openLightbox(card));
    const undoBtn = makeActionBtn("\u21A9 Undo", "btn-undo", () => moveCard(card, "unsorted"));
    actions.appendChild(previewBtn);
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

  // Update decisions map
  if (toColumn === "unsorted") {
    decisions.delete(filename);
  } else {
    decisions.set(filename, toColumn);
  }

  // Push undo
  undoStack.push({ filename, from: fromColumn, to: toColumn });

  // Move DOM
  const target = toColumn === "trash" ? cardsTrash
               : toColumn === "keep"  ? cardsKeep
               : cardsUnsorted;

  if (toColumn === "unsorted") {
    target.prepend(card);
  } else {
    target.prepend(card);
  }

  setCardActions(card, toColumn);
  updateCounts();
}

function getCardColumn(card) {
  if (cardsTrash.contains(card)) return "trash";
  if (cardsKeep.contains(card)) return "keep";
  return "unsorted";
}

// ── HTML5 Drag & Drop ────────────────────────────────────────────────────────
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

// Column drop zones
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
  const filename = card.dataset.filename;
  lightboxImg.src = `/api/image/${encodeURIComponent(filename)}`;
  lightboxImg.alt = filename;
  lightbox.hidden = false;
}

function closeLightbox() {
  lightbox.hidden = true;
  lightboxImg.src = "";
}

document.getElementById("lightbox-close").addEventListener("click", closeLightbox);
document.querySelector(".lightbox-backdrop").addEventListener("click", closeLightbox);

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
  // Esc closes lightbox
  if (e.key === "Escape") {
    if (!lightbox.hidden) { closeLightbox(); return; }
    if (!confirmModal.hidden) { closeModal(); return; }
  }

  // Cmd/Ctrl+Z = undo
  if ((e.metaKey || e.ctrlKey) && e.key === "z") {
    e.preventDefault();
    performUndo();
  }
});

// ── Undo ─────────────────────────────────────────────────────────────────────
undoBtn.addEventListener("click", () => performUndo());
function performUndo() {
  if (undoStack.length === 0) return;
  const action = undoStack.pop();
  const card = document.querySelector(`[data-filename="${CSS.escape(action.filename)}"]`);
  if (!card) return;

  // Move back without pushing to undo stack
  const fromColumn = action.from;
  const filename = action.filename;

  if (fromColumn === "unsorted") {
    decisions.delete(filename);
  } else {
    decisions.set(filename, fromColumn);
  }

  const target = fromColumn === "trash" ? cardsTrash
               : fromColumn === "keep"  ? cardsKeep
               : cardsUnsorted;
  target.prepend(card);

  setCardActions(card, fromColumn);
  updateCounts();
}

// ── Counts & status ──────────────────────────────────────────────────────────
function updateCounts() {
  const nUnsorted = cardsUnsorted.querySelectorAll(".card").length;
  const nTrash    = cardsTrash.querySelectorAll(".card").length;
  const nKeep     = cardsKeep.querySelectorAll(".card").length;
  const total     = nUnsorted + nTrash + nKeep;

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

      const failed = new Set((data.errors || []).map(e => e.split(":")[0].trim()));
      toTrash.forEach(filename => {
        if (!failed.has(filename)) {
          const card = cardsTrash.querySelector(`[data-filename="${CSS.escape(filename)}"]`);
          if (card) card.remove();
          decisions.delete(filename);
        }
      });

      // Clear undo stack for trashed files
      undoStack.length = 0;

      updateCounts();

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
