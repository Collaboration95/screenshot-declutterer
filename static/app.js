// decisions: Map<filename, 'keep' | 'trash'>
const decisions = new Map();

const grid      = document.getElementById("screenshot-grid");
const doneBtn   = document.getElementById("done-btn");
const statusMsg = document.getElementById("status-msg");
const emptyMsg  = document.getElementById("empty-msg");

// ── Bootstrap ─────────────────────────────────────────────────────────────────
fetch("/api/screenshots")
  .then(r => r.json())
  .then(filenames => {
    if (filenames.length === 0) {
      emptyMsg.hidden = false;
      return;
    }
    filenames.forEach(filename => grid.appendChild(makeCard(filename)));
    updateStatus();
  })
  .catch(() => {
    statusMsg.textContent = "Failed to load screenshots.";
  });

// ── Card factory ──────────────────────────────────────────────────────────────
function makeCard(filename) {
  const card = document.createElement("article");
  card.className = "card unsorted";
  card.dataset.filename = filename;

  const img = document.createElement("img");
  img.src = `/api/image/${encodeURIComponent(filename)}`;
  img.alt = filename;
  img.loading = "lazy";

  const overlay = document.createElement("div");
  overlay.className = "card-overlay";
  overlay.innerHTML =
    '<span class="hint hint-keep">← Keep</span>' +
    '<span class="hint hint-trash">Trash →</span>';

  card.appendChild(img);
  card.appendChild(overlay);

  attachDrag(card);
  return card;
}

// ── Drag interaction ──────────────────────────────────────────────────────────
// Works via both HTML5 drag events (mouse) and pointer events (trackpad / touch).
function attachDrag(card) {
  let startX = null;

  // ── Pointer-based drag (trackpad / touch) ─────────────────────────────────
  card.addEventListener("pointerdown", e => {
    startX = e.clientX;
    card.setPointerCapture(e.pointerId);
    card.style.transition = "none";
  });

  card.addEventListener("pointermove", e => {
    if (startX === null) return;
    const delta = e.clientX - startX;
    card.style.transform = `translateX(${delta}px)`;
    card.style.opacity = 1 - Math.min(Math.abs(delta) / 300, 0.4);
  });

  card.addEventListener("pointerup", e => {
    if (startX === null) return;
    const delta = e.clientX - startX;
    finalizeDrag(card, delta);
    startX = null;
  });

  card.addEventListener("pointercancel", () => {
    snapBack(card);
    startX = null;
  });
}

// ── Drag outcome ──────────────────────────────────────────────────────────────
const THRESHOLD = 80; // px

function finalizeDrag(card, delta) {
  card.style.transition = "transform 0.2s ease, opacity 0.2s ease";

  if (delta > THRESHOLD) {
    markCard(card, "trash");
  } else if (delta < -THRESHOLD) {
    markCard(card, "keep");
  } else {
    snapBack(card);
  }
}

function snapBack(card) {
  card.style.transition = "transform 0.2s ease, opacity 0.2s ease";
  card.style.transform  = "";
  card.style.opacity    = "";
}

function markCard(card, decision) {
  const filename = card.dataset.filename;

  // Reset visual state
  card.classList.remove("keep", "trash", "unsorted");
  card.style.transform = "";
  card.style.opacity   = "";

  // Apply new state
  card.classList.add(decision);
  decisions.set(filename, decision);

  // Update / replace stamp
  const existing = card.querySelector(".stamp");
  if (existing) existing.remove();

  const stamp = document.createElement("span");
  stamp.className = `stamp stamp-${decision}`;
  stamp.textContent = decision === "keep" ? "Keep" : "Trash";
  card.appendChild(stamp);

  updateStatus();
  checkAutoComplete();
}

// ── Status line ───────────────────────────────────────────────────────────────
function updateStatus() {
  const total   = grid.querySelectorAll(".card").length;
  const sorted  = decisions.size;
  const trashed = [...decisions.values()].filter(v => v === "trash").length;

  if (sorted === 0) {
    statusMsg.textContent = `${total} screenshot${total !== 1 ? "s" : ""} — drag to sort`;
  } else {
    statusMsg.textContent = `${sorted}/${total} sorted · ${trashed} to trash`;
  }

  doneBtn.disabled = trashed === 0;
}

// ── Auto-complete when every card is sorted ───────────────────────────────────
function checkAutoComplete() {
  const unsorted = grid.querySelectorAll(".unsorted").length;
  const trashed  = [...decisions.values()].filter(v => v === "trash").length;
  if (unsorted === 0 && trashed > 0) {
    handleDone();
  }
}

// ── Done button ───────────────────────────────────────────────────────────────
doneBtn.addEventListener("click", handleDone);

function handleDone() {
  const toTrash = [...decisions.entries()]
    .filter(([, v]) => v === "trash")
    .map(([filename]) => filename);

  if (toTrash.length === 0) return;

  const confirmed = window.confirm(
    `Move ${toTrash.length} screenshot${toTrash.length !== 1 ? "s" : ""} to Trash?\n\nThis cannot be undone from here.`
  );
  if (!confirmed) return;

  doneBtn.disabled = true;
  statusMsg.textContent = "Moving to Trash…";

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

      // Remove successfully trashed cards from the DOM
      const failed = new Set((data.errors || []).map(e => e.split(":")[0].trim()));
      toTrash.forEach(filename => {
        if (!failed.has(filename)) {
          const card = grid.querySelector(`[data-filename="${CSS.escape(filename)}"]`);
          if (card) card.remove();
          decisions.delete(filename);
        }
      });

      updateStatus();

      if (grid.querySelectorAll(".card").length === 0) {
        emptyMsg.hidden = false;
        statusMsg.textContent = "All done!";
        doneBtn.disabled = true;
      }
    })
    .catch(() => {
      alert("Network error — please try again.");
      doneBtn.disabled = false;
      updateStatus();
    });
}
