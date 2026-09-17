const decisions = new Map();
const undoStack = [];
const selectedCards = new Set();
let totalCards = 0;
let currentSort = "date_desc";
let currentFileKeys = new Set();
let trackedFoldersWorkingCopy = [];
let trackedFolderInfo = [];

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
const lightboxPrev = document.getElementById("lightbox-prev");
const lightboxNext = document.getElementById("lightbox-next");
const lightboxPosition = document.getElementById("lightbox-position");
const lightboxRenameBtn = document.getElementById("lightbox-rename-btn");

const toastRegion = document.getElementById("toast-region");
const feedbackBanner = document.getElementById("feedback-banner");
const feedbackBannerTitle = document.getElementById("feedback-banner-title");
const feedbackBannerMessage = document.getElementById("feedback-banner-message");
const feedbackBannerDetails = document.getElementById("feedback-banner-details");
const feedbackBannerList = document.getElementById("feedback-banner-list");
const feedbackBannerClose = document.getElementById("feedback-banner-close");

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
const settingsCloseBtn = document.getElementById("settings-close-btn");
const settingsSaveStatus = document.getElementById("settings-save-status");
const settingsLLMStatus = document.getElementById("settings-llm-status");
const settingsLLMStatusText = document.getElementById("settings-llm-status-text");
const settingsLLMAction = document.getElementById("settings-llm-action");
const trackedFoldersList = document.getElementById("tracked-folders-list");
const addFolderBtn    = document.getElementById("add-folder-btn");
const trackedFoldersError = document.getElementById("tracked-folders-error");

const llmServerBtn    = document.getElementById("llm-server-btn");
const llmStatusLabel  = document.getElementById("llm-status-label");
const llmMenu         = document.getElementById("llm-menu");
const llmMenuAction   = document.getElementById("llm-menu-action");
const llmMenuStatus   = document.getElementById("llm-menu-status");
const llmMenuDesc     = document.getElementById("llm-menu-desc");

const sortSummary        = document.getElementById("sort-summary");
const progressMeter      = document.getElementById("progress-meter");
const progressMeterFill  = document.getElementById("progress-meter-fill");
const allSortedMsg = document.getElementById("all-sorted-msg");
const scanErrorMsg = document.getElementById("scan-error-msg");
const scanErrorDetail = document.getElementById("scan-error-detail");
const refreshButtons = [
  document.getElementById("refresh-btn"),
  document.getElementById("refresh-sorted-btn"),
  document.getElementById("retry-scan-btn"),
].filter(Boolean);
const suggestProgressFailure = document.getElementById("suggest-progress-failure");
const suggestProgressBar = suggestProgress ? suggestProgress.querySelector('[role="progressbar"]') : null;

const kanban         = document.getElementById("kanban");
const columnSwitcher = document.getElementById("column-switcher");
const compactCountKeep     = document.getElementById("compact-count-keep");
const compactCountUnsorted = document.getElementById("compact-count-unsorted");
const compactCountTrash    = document.getElementById("compact-count-trash");

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
// static/theme-init.js resolved and applied the stored mode before the first
// paint, so this file only owns the interaction and the accessible label. The
// storage key is owned by the bootstrap, so app.js references it instead of
// declaring a second copy that could drift.
const THEME_KEY = SsDclTheme.THEME_STORAGE_KEY;
const themeChoices = [...document.querySelectorAll("[data-theme-choice]")];
const themeColorMeta = document.getElementById("theme-color-meta");

function getSavedTheme() {
  return SsDclTheme.readMode(window);
}

function applyTheme(mode) {
  return SsDclTheme.applyTheme(mode, window);
}

function _updateThemeLabel() {
  const mode = getSavedTheme();
  themeChoices.forEach(choice => {
    const selected = choice.dataset.themeChoice === mode;
    choice.setAttribute("aria-checked", String(selected));
    choice.classList.toggle("is-selected", selected);
  });
  if (themeColorMeta) {
    themeColorMeta.content = SsDclTheme.effectiveTheme(mode, window) === "dark" ? "#171815" : "#F7F6E8";
  }
}

function cycleTheme() {
  const next = SsDclTheme.cycleTheme(window);
  _updateThemeLabel();
  return next;
}

themeChoices.forEach(choice => {
  choice.addEventListener("click", () => {
    selectTheme(choice.dataset.themeChoice);
  });
  choice.addEventListener("keydown", event => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const index = themeChoices.indexOf(choice);
    const delta = event.key === "ArrowRight" ? 1 : -1;
    const next = themeChoices[(index + delta + themeChoices.length) % themeChoices.length];
    next.focus();
    selectTheme(next.dataset.themeChoice);
  });
});

function selectTheme(mode) {
  // Keep the ownership contract visible here: theme-init.js owns the key and
  // persistence implementation; app.js only selects one of its known modes.
  void THEME_KEY;
  SsDclTheme.writeMode(mode, window);
  applyTheme(mode);
  _updateThemeLabel();
  announce(`Theme set to ${mode === "auto" ? "System" : mode === "dark" ? "Dark" : "Light"}.`, { type: "success", timeout: 3000 });
}

// With "auto" selected the board has to follow the OS live.
if (typeof window.matchMedia === "function") {
  window.matchMedia(SsDclTheme.DARK_QUERY).addEventListener("change", () => {
    if (getSavedTheme() === "auto") {
      applyTheme("auto");
      _updateThemeLabel();
    }
  });
}

// The bootstrap already painted the right theme; this only syncs the label.
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

// ── Transient announcements ─────────────────────────────────────────────────
// #sort-summary owns the stable progress statement, so #status-msg only ever
// carries a short-lived notice: it clears itself instead of overwriting the
// summary indefinitely (PLAN 6.2).
let _statusTimer = null;
let _toastId = 0;

function _toastType(options) {
  const opts = options || {};
  return opts.error ? "error" : (opts.type || "info");
}

function showToast(message, options) {
  if (!toastRegion || !message) return;
  const opts = options || {};
  const toast = document.createElement("div");
  const type = _toastType(opts);
  toast.className = `toast toast-${type}`;
  toast.dataset.toastId = String(++_toastId);
  toast.setAttribute("role", type === "error" ? "alert" : "status");

  const iconEl = document.createElement("span");
  iconEl.className = "toast-icon";
  iconEl.setAttribute("aria-hidden", "true");
  iconEl.textContent = type === "success" ? "✓" : type === "error" ? "!" : type === "warning" ? "!" : "i";
  const copy = document.createElement("span");
  copy.className = "toast-copy";
  copy.textContent = message;
  const close = document.createElement("button");
  close.type = "button";
  close.className = "toast-dismiss";
  close.setAttribute("aria-label", "Dismiss notification");
  close.textContent = "×";
  close.addEventListener("click", () => toast.remove());
  toast.append(iconEl, copy, close);
  toastRegion.appendChild(toast);

  const timeout = opts.timeout === undefined ? (type === "error" ? 0 : 6500) : opts.timeout;
  if (timeout > 0) {
    let timer = setTimeout(() => toast.remove(), timeout);
    const pause = () => { clearTimeout(timer); };
    const resume = () => { timer = setTimeout(() => toast.remove(), timeout); };
    toast.addEventListener("mouseenter", pause);
    toast.addEventListener("focusin", pause);
    toast.addEventListener("mouseleave", resume);
    toast.addEventListener("focusout", resume);
  }
  return toast;
}

function showFeedbackBanner(title, message, options) {
  if (!feedbackBanner) return;
  const opts = options || {};
  feedbackBanner.className = `feedback-banner feedback-${opts.type || (opts.error ? "error" : "warning")}`;
  feedbackBannerTitle.textContent = title || "Something needs your attention";
  feedbackBannerMessage.textContent = message || "";
  feedbackBannerList.textContent = "";
  const details = opts.details || [];
  feedbackBannerDetails.hidden = details.length === 0;
  details.forEach(detail => {
    const item = document.createElement("li");
    item.textContent = detail;
    feedbackBannerList.appendChild(item);
  });
  feedbackBanner.hidden = false;
  if (feedbackBannerClose) feedbackBannerClose.focus({ preventScroll: true });
}

function hideFeedbackBanner() {
  if (feedbackBanner) feedbackBanner.hidden = true;
}

if (feedbackBannerClose) feedbackBannerClose.addEventListener("click", hideFeedbackBanner);

function announce(message, options) {
  const opts = options || {};
  if (_statusTimer) clearTimeout(_statusTimer);
  _statusTimer = null;
  statusMsg.textContent = message || "";
  statusMsg.classList.toggle("is-error", !!opts.error);
  if (!message) return;
  showToast(message, opts);
  if (opts.persistent) showFeedbackBanner(opts.title, message, opts);
  if (opts.timeout !== 0) {
    _statusTimer = setTimeout(() => {
      statusMsg.textContent = "";
      statusMsg.classList.remove("is-error");
      _statusTimer = null;
    }, opts.timeout || 8000);
  }
}

// ── Managed LiteRT server status pill ───────────────────────────────────────
// The state lives on the control itself (class + label + accessible name) so
// the server condition is never communicated by button text alone.
let llmServerState = "stopped";

const LLM_STATE_COPY = {
  ready: { label: "AI ready", hint: "Local AI server is running — click to stop it" },
  stopped: { label: "AI stopped", hint: "Local AI server is stopped — click to start it" },
  starting: { label: "AI starting", hint: "Local AI server is starting or stopping…" },
  error: { label: "AI offline", hint: "Local AI server is unreachable — click to try starting it" },
};

function _setLLMStatus(state, labelOverride) {
  llmServerState = state;
  const copy = LLM_STATE_COPY[state] || LLM_STATE_COPY.stopped;
  llmServerBtn.hidden = false;
  llmServerBtn.classList.remove("is-ready", "is-stopped", "is-starting", "is-error");
  llmServerBtn.classList.add(`is-${state}`);
  if (llmStatusLabel) llmStatusLabel.textContent = labelOverride || copy.label;
  llmServerBtn.disabled = state === "starting";
  llmServerBtn.setAttribute("aria-label", copy.hint);
  llmServerBtn.dataset.tooltip = copy.hint;
  llmServerBtn.setAttribute("aria-expanded", String(!llmMenu.hidden));
  if (llmMenuStatus) llmMenuStatus.textContent = copy.label.replace(/^AI /, "");
  if (llmMenuDesc) llmMenuDesc.textContent = state === "error"
    ? "The local AI server is unavailable. Start it to enable filename suggestions."
    : "AI suggestions run on this Mac and never upload your screenshots.";
  if (llmMenuAction) {
    llmMenuAction.querySelector(".menu-item-label").textContent = state === "ready" ? "Stop local AI" : "Start local AI";
    llmMenuAction.disabled = state === "starting";
  }
  if (settingsLLMStatus) {
    settingsLLMStatus.className = `settings-llm-status status-${state}`;
    settingsLLMStatusText.textContent = copy.hint;
  }
}

// Label follows the last health verdict.
function refreshLLMServerButton() {
  llmServerBtn.hidden = false;
  llmServerBtn.disabled = true;
  fetch("/api/llm/health")
    .then(r => r.json())
    .then(h => _setLLMStatus(h.ok ? "ready" : (h.error ? "error" : "stopped")))
    .catch(() => _setLLMStatus("error"));
}

function performLLMControl() {
  const stopping = llmServerState === "ready";
  _setLLMStatus("starting", stopping ? "AI stopping…" : "AI starting…");
  fetch(stopping ? "/api/llm/stop" : "/api/llm/start", { method: "POST" })
    .then(r => r.json())
    .then(data => {
      announce(data.message || data.error || "Server control failed.", { error: !data.ok });
      refreshLLMServerButton();
    })
    .catch(() => {
      announce("Couldn't reach the server controller.", { error: true });
      refreshLLMServerButton();
    });
}

function toggleLLMMenu() {
  if (!llmMenu) return;
  const opening = llmMenu.hidden;
  closeCardOverflow();
  llmMenu.hidden = !opening;
  llmServerBtn.setAttribute("aria-expanded", String(opening));
  if (opening) {
    const action = llmMenu.querySelector("[role=menuitem]");
    if (action) action.focus();
  }
}

llmServerBtn.addEventListener("click", toggleLLMMenu);
if (llmMenuAction) {
  llmMenuAction.addEventListener("click", () => {
    llmMenu.hidden = true;
    llmServerBtn.setAttribute("aria-expanded", "false");
    performLLMControl();
  });
}
if (settingsLLMAction) settingsLLMAction.addEventListener("click", performLLMControl);
document.addEventListener("click", event => {
  if (!llmMenu || llmMenu.hidden) return;
  if (llmMenu.contains(event.target) || llmServerBtn.contains(event.target)) return;
  llmMenu.hidden = true;
  llmServerBtn.setAttribute("aria-expanded", "false");
});

function fileKey(source, filename) {
  return SsDcl.decisionKey(source || "Desktop", filename);
}
function fileKeyForFile(file) {
  return SsDcl.fileKey(file);
}
function loadSettings() {
  return fetch("/api/settings")
    .then(r => r.json())
    .then(s => {
      llmSettings = s;
      // Tracked folders: working copy semantics
      trackedFolderInfo = s.tracked_folder_info || [];
      // If server provides tracked_folders, use that as working copy base
      // Working copy is set when modal opens, but keep info for display
    })
    .catch(() => {});
}

// ── Tracked folders UI helpers ─────────────────────────────────────
function renderTrackedFolders() {
  if (!trackedFoldersList) return;
  trackedFoldersList.innerHTML = "";
  // Desktop default row
  const desktopRow = document.createElement("div");
  desktopRow.className = "tracked-folder-row tracked-default-row";
  const desktopPath = document.createElement("span");
  desktopPath.className = "tracked-folder-path";
  desktopPath.textContent = "Desktop (default)";
  desktopPath.title = "Your Desktop — always scanned";
  desktopRow.appendChild(desktopPath);
  trackedFoldersList.appendChild(desktopRow);
  // Working copy rows
  trackedFoldersWorkingCopy.forEach((path, idx) => {
    const row = document.createElement("div");
    row.className = "tracked-folder-row";
    // Check if missing
    const info = trackedFolderInfo.find(i => i.path === path);
    const exists = info ? info.exists : true;
    if (!exists) row.classList.add("missing");
    const pathSpan = document.createElement("span");
    pathSpan.className = "tracked-folder-path";
    pathSpan.textContent = exists ? path : `${path}  ⚠ no longer exists`;
    pathSpan.title = path;
    const removeBtn = document.createElement("button");
    removeBtn.className = "tracked-folder-remove";
    removeBtn.textContent = "✕";
    removeBtn.title = "Remove";
    removeBtn.setAttribute("aria-label", `Remove ${path}`);
    removeBtn.addEventListener("click", () => {
      trackedFoldersWorkingCopy.splice(idx, 1);
      trackedFoldersError.textContent = "";
      renderTrackedFolders();
      updateSettingsDirty();
    });
    row.appendChild(pathSpan);
    row.appendChild(removeBtn);
    trackedFoldersList.appendChild(row);
  });
}

function showTrackedError(msg) {
  if (trackedFoldersError) trackedFoldersError.textContent = msg || "";
}

if (addFolderBtn) {
  addFolderBtn.addEventListener("click", () => {
    showTrackedError("");
    addFolderBtn.disabled = true;
    addFolderBtn.textContent = "Opening…";
    fetch("/api/pick-folder", { method: "POST" })
      .then(r => r.json().then(j => ({ status: r.status, body: j })))
      .then(({ status, body }) => {
        addFolderBtn.disabled = false;
        addFolderBtn.textContent = "+ Add folder";
        if (status !== 200) {
          showTrackedError(body.error || "Folder picker failed");
          return;
        }
        if (body.path === null || body.path === undefined) {
          // Cancel — no-op
          return;
        }
        const newPath = body.path;
        if (trackedFoldersWorkingCopy.includes(newPath)) {
          showTrackedError("That folder is already tracked");
          return;
        }
        // Client-side cap check before server validation
        if (trackedFoldersWorkingCopy.length >= 10) {
          showTrackedError("Too many tracked folders: maximum is 10");
          return;
        }
        trackedFoldersWorkingCopy.push(newPath);
        renderTrackedFolders();
        updateSettingsDirty();
      })
      .catch(() => {
        addFolderBtn.disabled = false;
        addFolderBtn.textContent = "+ Add folder";
        showTrackedError("Folder picker failed — please try again");
      });
  });
}

// ── Bootstrap ────────────────────────────────────────────────────────────────
function setBoardState(state, detail) {
  [loadingMsg, emptyMsg, allSortedMsg, scanErrorMsg].forEach(node => {
    if (node) node.hidden = true;
  });
  if (state === "loading" && loadingMsg) loadingMsg.hidden = false;
  if (state === "empty" && emptyMsg) emptyMsg.hidden = false;
  if (state === "sorted" && allSortedMsg) allSortedMsg.hidden = false;
  if (state === "error" && scanErrorMsg) {
    scanErrorMsg.hidden = false;
    if (scanErrorDetail) scanErrorDetail.textContent = detail || "Check that Desktop is available, then try again.";
  }
}

function refreshScreenshots() {
  document.querySelectorAll(".card").forEach(card => card.remove());
  totalCards = 0;
  currentFileKeys = new Set();
  setBoardState("loading");
  fetch("/api/state")
    .then(r => r.json())
    .then(state => loadScreenshots(state.decisions || {}))
    .catch(() => loadScreenshots({}));
}

function init() {
  loadSettings().then(() => {
    refreshLLMServerButton();
    refreshScreenshots();
  });
}

function loadScreenshots(savedDecisions) {
  clearSelection();
  setBoardState("loading");
  fetch(`/api/screenshots?sort=${encodeURIComponent(currentSort)}`)
    .then(r => r.json().then(body => ({ ok: r.ok, body })))
    .then(({ ok, body: files }) => {
      if (!ok || !Array.isArray(files)) {
        const detail = files && (files.error || files.message);
        throw new Error(detail || "The screenshot scan failed.");
      }
      if (files.length === 0) {
        totalCards = 0;
        currentFileKeys = new Set();
        setBoardState("empty");
        updateCounts();
        return;
      }
      totalCards = files.length;
      currentFileKeys = new Set(files.map(f => SsDcl.fileKey(f)));

      // Preserve all persisted decisions (including untracked folders) — only project active set into board
      for (const [key, col] of Object.entries(savedDecisions)) {
        if (col === "keep" || col === "trash") {
          decisions.set(key, col);
        } else {
          decisions.delete(key);
        }
      }
      // Do NOT delete untracked decisions — they remain in Map for re-add restoration
      // Clean invalid values only
      for (const [k, v] of Array.from(decisions.entries())) {
        if (v !== "keep" && v !== "trash" && !currentFileKeys.has(k)) {
          // For non-active keys with invalid values, keep but they are not counted
        }
      }

      files.forEach(f => {
        const key = SsDcl.fileKey(f);
        const col = decisions.has(key) ? decisions.get(key) : "unsorted";
        const target = col === "trash" ? cardsTrash
                     : col === "keep"  ? cardsKeep
                     : cardsUnsorted;
        target.appendChild(makeCard(f.name, f.source, col, f.fingerprint, f.memory_status, f.suggested_name, f.suggested_category));
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
    .catch(error => {
      totalCards = 0;
      currentFileKeys = new Set();
      setBoardState("error", error.message);
      updateCounts();
      announce(error.message || "Failed to load screenshots.", {
        error: true,
        persistent: true,
        title: "Scan failed",
        timeout: 0,
      });
    });
}

refreshButtons.forEach(button => button.addEventListener("click", refreshScreenshots));

init();

// ── Compact column switcher (<=1024px) ───────────────────────────────────────
// Below the compact breakpoint the board shows one column at a time so every
// primary action stays reachable without horizontal scrolling; this control
// chooses which column is on screen (PLAN 6.4). The pressed state lives on the
// group so assistive tech reads the switcher as a single selection.
function setCompactColumn(target) {
  if (!kanban || !columnSwitcher) return;
  kanban.dataset.compactColumn = target;
  columnSwitcher.querySelectorAll(".compact-switcher-item").forEach(btn => {
    btn.setAttribute("aria-pressed", String(btn.dataset.columnTarget === target));
  });
}

if (columnSwitcher) {
  columnSwitcher.addEventListener("click", e => {
    const btn = e.target.closest(".compact-switcher-item");
    if (btn) setCompactColumn(btn.dataset.columnTarget);
  });
}


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
      announce("Warning: failed to save state.", { error: true });
    });
    _saveTimer = null;
  }, 300);
}

// ── Local icon set ───────────────────────────────────────────────────────────
// Small stroke icons drawn from path data in this file: no font, no CDN, no
// emoji glyph carrying meaning on its own (PLAN 6.2/6.4).
const ICON_PATHS = {
  keep: "M5 12.5 9.5 17 19 7",
  trash: "M6 7h12M9.5 7V5h5v2M7.5 7l.9 12h7.2l.9-12M10.5 10.5v6M13.5 10.5v6",
  preview: "M2.7 12S6.2 6.2 12 6.2 21.3 12 21.3 12 17.8 17.8 12 17.8 2.7 12 2.7 12Z M12 14.9a2.9 2.9 0 1 0 0-5.8 2.9 2.9 0 0 0 0 5.8Z",
  rename: "M4.5 19.5h15M6.3 16.2 16 6.5a2 2 0 0 1 2.8 2.8l-9.7 9.7-3.6.8.8-3.6Z",
  reveal: "M4 7.2A1.7 1.7 0 0 1 5.7 5.5h3.6l1.8 1.9h7.2A1.7 1.7 0 0 1 20 9.1v8.2a1.7 1.7 0 0 1-1.7 1.7H5.7A1.7 1.7 0 0 1 4 17.3V7.2Z",
  suggest: "M11 4.5 12.4 8.6 16.5 10 12.4 11.4 11 15.5 9.6 11.4 5.5 10 9.6 8.6 11 4.5ZM17.5 14.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8.8-2.2Z",
  undo: "M8 5 4 9l4 4M4 9h10.5a5.5 5.5 0 0 1 0 11H10",
  more: "M7 12h.01M12 12h.01M17 12h.01",
  check: "M5 12.5 9.5 17 19 7",
};

const SVG_NS = "http://www.w3.org/2000/svg";

function icon(name, size) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", "icon");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", String(size || 16));
  svg.setAttribute("height", String(size || 16));
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", ICON_PATHS[name] || "");
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", "currentColor");
  path.setAttribute("stroke-width", "1.9");
  path.setAttribute("stroke-linecap", "round");
  path.setAttribute("stroke-linejoin", "round");
  svg.appendChild(path);
  return svg;
}

// ── Category hint (4C) ───────────────────────────────────────────────────────
// The learned category is announced in words as well as colour: a labelled
// micro-badge plus the supplemental left border (PLAN 6.4).
function _applyCategoryHint(card, category) {
  card.classList.remove("category-hint-keep", "category-hint-trash");
  const previous = card.querySelector(".card-badge");
  if (previous) previous.remove();
  delete card.dataset.suggestedCategory;
  if (category !== "keep" && category !== "trash") return;
  card.dataset.suggestedCategory = category;
  card.classList.add(`category-hint-${category}`);
  const badge = document.createElement("span");
  badge.className = `card-badge badge badge-${category}`;
  badge.textContent = category === "keep" ? "Likely keep" : "Likely trash";
  badge.title =
    category === "keep"
      ? "Your past decisions suggest keeping this screenshot"
      : "Your past decisions suggest trashing this screenshot";
  const meta = card.querySelector(".card-meta");
  if (meta) meta.appendChild(badge);
}

function _clearCategoryHint(card) {
  _applyCategoryHint(card, null);
}

// ── Card factory ─────────────────────────────────────────────────────────────
function makeCard(filename, source, column, fingerprint, memoryStatus, suggestedName, suggestedCategory) {
  // Backward compat: if called with old signature (filename, column, ...), shift
  if (typeof source === "string" && (source === "keep" || source === "trash" || source === "unsorted")) {
    suggestedCategory = suggestedName;
    suggestedName = memoryStatus;
    memoryStatus = fingerprint;
    fingerprint = column;
    column = source;
    source = "Desktop";
  }
  source = source || "Desktop";
  const card = document.createElement("article");
  card.className = "card";
  card.setAttribute("role", "listitem");
  card.setAttribute("aria-label", `${filename} (${source})`);
  card.dataset.filename = filename;
  card.dataset.source = source;
  card.dataset.fingerprint = fingerprint || "";
  card.dataset.memoryStatus = memoryStatus || "";
  card.dataset.suggestedName = suggestedName || "";
  if (suggestedCategory) {
    card.dataset.suggestedCategory = suggestedCategory;
  }
  card.draggable = true;
  card.tabIndex = 0;

  const thumbUrl = `/api/thumb/${encodeURIComponent(filename)}${SsDcl.sourceQuery(source)}`;
  const thumb = document.createElement("div");
  thumb.className = "card-thumb";

  const img = document.createElement("img");
  img.src = thumbUrl;
  img.alt = filename;
  img.loading = "lazy";
  img.decoding = "async";
  img.addEventListener("error", () => {
    card.classList.add("image-error");
    img.hidden = true;
    const fallback = thumb.querySelector(".card-image-error") || document.createElement("div");
    fallback.className = "card-image-error";
    fallback.textContent = "Preview unavailable";
    fallback.setAttribute("role", "img");
    fallback.setAttribute("aria-label", `${filename}: preview unavailable`);
    if (!fallback.parentElement) thumb.insertBefore(fallback, select);
  });

  // Persistent selection affordance at the top-left of the thumbnail (PLAN
  // 6.4 #4). It is a real button so assistive tech can find and name it, but it
  // sits outside the tab order: the card itself takes focus, exposes the action
  // bar on :focus-within, and Enter/Space toggles the same selection.
  const select = document.createElement("button");
  select.type = "button";
  select.className = "card-select";
  select.tabIndex = -1;
  select.setAttribute("aria-pressed", "false");
  select.setAttribute("aria-label", `Select ${filename}`);
  select.appendChild(icon("check", 14));

  thumb.appendChild(img);
  thumb.appendChild(select);

  const meta = document.createElement("div");
  meta.className = "card-meta";

  const name = document.createElement("span");
  name.className = "card-name";
  name.textContent = filename;
  name.title = filename;
  meta.appendChild(name);

  // Source tag for tracked folders
  if (source !== "Desktop") {
    const tag = document.createElement("span");
    tag.className = "source-tag";
    const folderName = source.split("/").pop() || source;
    tag.textContent = `in: ${folderName}`;
    tag.title = source;
    meta.appendChild(tag);
  }

  const actions = document.createElement("div");
  actions.className = "card-actions";

  card.appendChild(thumb);
  card.appendChild(meta);

  // Category hint: labelled micro-badge plus the supplemental left border.
  _applyCategoryHint(card, suggestedCategory);

  // Suggestion badge (always visible when status is "suggested")
  if (memoryStatus === "suggested" && suggestedName) {
    card.appendChild(_makeSuggestionBadge(card));
  }

  // The action bar must stay the last child: suggestBatch() inserts badges
  // with insertBefore(badge, .card-actions).
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

// ── Card action bar ─────────────────────────────────────────────────────────
// One bar per card, revealed on hover or keyboard focus (PLAN 6.4 #5/#6). The
// decision (Keep / Trash) is always the primary cluster; preview, an optional
// AI suggest, and the overflow menu that hides Rename / Reveal in Finder are
// secondary. Keep and Trash cards reuse the very same bar, so the side trays
// keep filename access and file actions instead of collapsing to image tiles.
//
// The overflow menu is a plain in-card popover: it is toggled by its own
// trigger, and closes on selection, Escape, or an outside click. Nothing here
// depends on hover to function.
let _openOverflow = null;

function closeCardOverflow() {
  if (!_openOverflow) return;
  const trigger = _openOverflow.parentElement
    ? _openOverflow.parentElement.querySelector(".btn-more")
    : null;
  _openOverflow.hidden = true;
  if (trigger) trigger.setAttribute("aria-expanded", "false");
  _openOverflow = null;
}

function toggleCardOverflow(menu, trigger) {
  if (_openOverflow === menu) {
    closeCardOverflow();
    return;
  }
  closeCardOverflow();
  menu.hidden = false;
  trigger.setAttribute("aria-expanded", "true");
  _openOverflow = menu;
}

document.addEventListener("click", e => {
  if (!_openOverflow) return;
  if (_openOverflow.contains(e.target)) return;
  closeCardOverflow();
});

function makeActionBtn(label, cls, onClick, options) {
  const opts = options || {};
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = `action-btn ${cls}${opts.iconOnly ? " action-btn-icon" : ""}`;
  if (opts.iconName) btn.appendChild(icon(opts.iconName, 15));
  if (opts.iconOnly) {
    // Icon-only controls carry their name in text, never in the glyph alone.
    btn.setAttribute("aria-label", opts.ariaLabel || label);
    btn.dataset.tooltip = opts.tooltip || opts.ariaLabel || label;
  } else {
    const text = document.createElement("span");
    text.className = "action-btn-label";
    text.textContent = label;
    btn.appendChild(text);
  }
  btn.addEventListener("click", e => {
    e.stopPropagation();
    if (btn.closest(".card-overflow")) closeCardOverflow();
    onClick();
  });
  return btn;
}

// Overflow trigger + menu, grouped so the menu can anchor to the action bar.
function makeOverflowMenu(items, contextLabel) {
  const wrap = document.createElement("div");
  wrap.className = "card-overflow-wrap";

  const trigger = makeActionBtn("More", "btn-more", () => {}, {
    iconName: "more",
    iconOnly: true,
    ariaLabel: `More actions for ${contextLabel}`,
    tooltip: "More actions",
  });
  trigger.setAttribute("aria-haspopup", "menu");
  trigger.setAttribute("aria-expanded", "false");

  const menu = document.createElement("div");
  menu.className = "card-overflow menu";
  menu.setAttribute("role", "menu");
  menu.setAttribute("aria-label", `More actions for ${contextLabel}`);
  menu.hidden = true;
  items.forEach(item => {
    item.setAttribute("role", "menuitem");
    menu.appendChild(item);
  });

  trigger.addEventListener("click", () => toggleCardOverflow(menu, trigger));
  wrap.appendChild(trigger);
  wrap.appendChild(menu);
  return wrap;
}

function setCardActions(card, column) {
  closeCardOverflow();
  const actions = card.querySelector(".card-actions");
  actions.textContent = "";

  const primary = document.createElement("div");
  primary.className = "card-action-primary";
  const secondary = document.createElement("div");
  secondary.className = "card-action-secondary";

  const filename = card.dataset.filename;
  const isNew = card.dataset.memoryStatus === "new";

  const previewBtn = makeActionBtn("Preview", "btn-preview", () => openLightbox(card), {
    iconName: "preview",
    iconOnly: true,
    ariaLabel: `Preview ${filename}`,
    tooltip: "Preview",
  });
  const renameBtn = makeActionBtn("Rename", "btn-rename", () => openRenameModal(card), {
    iconName: "rename",
  });
  const revealBtn = makeActionBtn(
    "Reveal in Finder",
    "btn-reveal",
    () => revealInFinder(card.dataset.filename, card.dataset.source),
    { iconName: "reveal" }
  );
  const suggestBtn = makeActionBtn("Suggest name", "btn-suggest", () => suggestSingle(card), {
    iconName: "suggest",
  });

  if (column === "unsorted") {
    primary.appendChild(makeActionBtn("Keep", "btn-keep", () => moveCard(card, "keep"), { iconName: "keep" }));
    primary.appendChild(makeActionBtn("Trash", "btn-trash", () => moveCard(card, "trash"), { iconName: "trash" }));
    secondary.appendChild(previewBtn);
    // Unprocessed files get the one-click AI action; processed ones keep it
    // reachable from the overflow menu.
    const overflow = isNew ? [renameBtn, revealBtn] : [suggestBtn, renameBtn, revealBtn];
    secondary.appendChild(makeOverflowMenu(overflow, filename));
  } else {
    primary.appendChild(makeActionBtn("Unsorted", "btn-undo", () => moveCard(card, "unsorted"), { iconName: "undo" }));
    secondary.appendChild(previewBtn);
    secondary.appendChild(makeOverflowMenu([renameBtn, revealBtn], filename));
  }

  actions.appendChild(primary);
  actions.appendChild(secondary);
}

// ── Move card between columns ────────────────────────────────────────────────
function moveCard(card, toColumn) {
  const filename = card.dataset.filename;
  const source = card.dataset.source || "Desktop";
  const key = fileKey(source, filename);
  const fromColumn = getCardColumn(card);

  if (fromColumn === toColumn) return;

  if (toColumn === "unsorted") {
    decisions.delete(key);
  } else {
    decisions.set(key, toColumn);
  }

  undoStack.push({ filename, source, key, from: fromColumn, to: toColumn });
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

// Selection is never signalled by colour alone: the card gets a high-contrast
// ring plus a checked control, and the select button carries the state for
// assistive tech.
function _syncCardSelection(card) {
  const selected = card.classList.contains("selected");
  const control = card.querySelector(".card-select");
  if (!control) return;
  control.setAttribute("aria-pressed", selected ? "true" : "false");
  control.setAttribute("aria-label", `${selected ? "Deselect" : "Select"} ${card.dataset.filename}`);
}

function toggleSelect(card) {
  if (selectedCards.has(card)) {
    selectedCards.delete(card);
    card.classList.remove("selected");
  } else {
    selectedCards.add(card);
    card.classList.add("selected");
  }
  _syncCardSelection(card);
  updateBatchBar();
}

function clearSelection() {
  selectedCards.forEach(card => {
    card.classList.remove("selected");
    _syncCardSelection(card);
  });
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
const GHOST_TILE_RADIUS = 12;

// The fanned stack is rasterised on a canvas, which cannot inherit CSS, so the
// tile chrome is read from the design tokens instead of repeating the palette
// here. Fallbacks only apply before the stylesheet has resolved.
function ghostToken(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name);
  return (value || "").trim() || fallback;
}

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

  const tileSurface = ghostToken("--surface-raised", "#FFFFFF");
  const tileBorder = ghostToken("--border-strong", "rgba(0, 0, 0, 0.25)");
  const badgeSurface = ghostToken("--surface-raised", "#FFFFFF");
  const badgeInk = ghostToken("--ink-primary", "#1A1A18");

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
    ghostRoundedRect(ctx, -GHOST_TILE_W / 2, -GHOST_TILE_H / 2, GHOST_TILE_W, GHOST_TILE_H, GHOST_TILE_RADIUS);
    ctx.fillStyle = tileSurface;
    ctx.fill();
    ctx.save();
    ctx.clip();
    ctx.drawImage(img, -GHOST_TILE_W / 2, -GHOST_TILE_H / 2, GHOST_TILE_W, GHOST_TILE_H);
    ctx.restore();
    ghostRoundedRect(ctx, -GHOST_TILE_W / 2, -GHOST_TILE_H / 2, GHOST_TILE_W, GHOST_TILE_H, GHOST_TILE_RADIUS);
    ctx.strokeStyle = tileBorder;
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
    ctx.fillStyle = badgeSurface;
    ctx.fill();
    ctx.fillStyle = badgeInk;
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

// ── Shared overlay contract ────────────────────────────────────────────────
// Settings, rename, confirmation, and the lightbox all use the same small
// focus manager. The DOM remains a fallback-friendly div overlay, while the
// aria-modal contract and keyboard loop provide native-dialog behaviour.
let activeOverlay = null;
let overlayReturnFocus = null;

function overlayFocusable(dialog) {
  return [...dialog.querySelectorAll(
    "button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex='-1'])"
  )].filter(node => !node.hidden && node.offsetParent !== null);
}

function openOverlay(dialog, trigger, firstSelector) {
  if (!dialog) return;
  if (activeOverlay && activeOverlay !== dialog) closeOverlay(activeOverlay, { restore: false });
  overlayReturnFocus = trigger || document.activeElement;
  activeOverlay = dialog;
  dialog.hidden = false;
  const first = (firstSelector && dialog.querySelector(firstSelector)) || overlayFocusable(dialog)[0] || dialog;
  requestAnimationFrame(() => first.focus({ preventScroll: true }));
}

function closeOverlay(dialog, options) {
  if (!dialog) return;
  const opts = options || {};
  dialog.hidden = true;
  if (activeOverlay === dialog) activeOverlay = null;
  const returnFocus = overlayReturnFocus;
  overlayReturnFocus = null;
  if (opts.restore !== false && returnFocus && document.contains(returnFocus) && !returnFocus.disabled) {
    requestAnimationFrame(() => returnFocus.focus({ preventScroll: true }));
  }
}

function trapOverlayFocus(dialog, event) {
  if (event.key !== "Tab" || activeOverlay !== dialog) return;
  const focusable = overlayFocusable(dialog);
  if (focusable.length === 0) {
    event.preventDefault();
    dialog.focus();
    return;
  }
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

[confirmModal, renameModal, settingsMenu, lightbox].forEach(dialog => {
  if (dialog) dialog.addEventListener("keydown", event => trapOverlayFocus(dialog, event));
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
  lightbox.dataset.currentSource = card.dataset.source || "Desktop";
  const src = card.dataset.source || "Desktop";
  lightboxImg.src = `/api/image/${encodeURIComponent(card.dataset.filename)}${SsDcl.sourceQuery(src)}`;
  lightboxImg.alt = card.dataset.filename;
  _updateLightboxBar(card.dataset.filename);
  openOverlay(lightbox, card, "#lightbox-close");
  _syncLightboxNavigation();
}

function lightboxCards() {
  return [...document.querySelectorAll(".card")];
}

function _syncLightboxNavigation() {
  const allCards = lightboxCards();
  const current = lightbox.dataset.currentFilename;
  const currentSource = lightbox.dataset.currentSource || "Desktop";
  const idx = allCards.findIndex(c => c.dataset.filename === current && (c.dataset.source || "Desktop") === currentSource);
  const position = idx >= 0 ? idx + 1 : 0;
  if (lightboxPosition) lightboxPosition.textContent = `${position} of ${allCards.length}`;
  if (lightboxPrev) lightboxPrev.disabled = idx <= 0;
  if (lightboxNext) lightboxNext.disabled = idx < 0 || idx >= allCards.length - 1;
}

function _lightboxNavigate(direction) {
  const allCards = lightboxCards();
  const current = lightbox.dataset.currentFilename;
  const currentSource = lightbox.dataset.currentSource || "Desktop";
  const idx = allCards.findIndex(c => c.dataset.filename === current && (c.dataset.source || "Desktop") === currentSource);
  if (idx < 0) return;
  const next = idx + direction;
  if (next < 0 || next >= allCards.length) return;
  const nextCard = allCards[next];
  const nextName = nextCard.dataset.filename;
  const nextSource = nextCard.dataset.source || "Desktop";
  lightbox.dataset.currentFilename = nextName;
  lightbox.dataset.currentSource = nextSource;
  lightboxImg.src = `/api/image/${encodeURIComponent(nextName)}${SsDcl.sourceQuery(nextSource)}`;
  lightboxImg.alt = nextName;
  _updateLightboxBar(nextName);
  _syncLightboxNavigation();
}

function closeLightbox() {
  closeOverlay(lightbox);
  lightboxImg.src = "";
  lightboxRenameInput.hidden = true;
  lightboxRenameInput.classList.remove("error");
  lightboxRenameError.textContent = "";
  lightboxFilename.hidden = false;
  if (lightboxPosition) lightboxPosition.textContent = "";
}

document.getElementById("lightbox-close").addEventListener("click", closeLightbox);
document.querySelector(".lightbox-backdrop").addEventListener("click", closeLightbox);
if (lightboxPrev) lightboxPrev.addEventListener("click", () => _lightboxNavigate(-1));
if (lightboxNext) lightboxNext.addEventListener("click", () => _lightboxNavigate(1));
if (lightboxRenameBtn) lightboxRenameBtn.addEventListener("click", _startLightboxRename);

// ── Reveal in Finder ────────────────────────────────────────────────────────
function revealInFinder(filename, source) {
  if (!filename) return;
  source = source || "Desktop";
  const payload = source === "Desktop" ? { filename } : { source, name: filename };
  // Also send source for Desktop for clarity; server accepts both
  if (source !== "Desktop" && !payload.source) payload.source = source;
  // Prefer {source, name} contract, but keep legacy {filename} for Desktop
  const body = source === "Desktop" ? { filename, source } : { source, name: filename };
  fetch("/api/reveal", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
    .then(r => r.json())
    .then(data => {
      announce(
        data.ok ? "Revealed in Finder." : (data.error || "Could not reveal in Finder."),
        { error: !data.ok },
      );
    })
    .catch(() => {
      announce("Network error — could not reveal in Finder.", { error: true });
    });
}

document.getElementById("lightbox-reveal-btn").addEventListener("click", () => {
  revealInFinder(lightbox.dataset.currentFilename, lightbox.dataset.currentSource);
});

// ── Card tooltip ───────────────────────────────────────────────────────────
function attachTooltip(card) {
  let tooltipTimer = null;
  const show = () => {
    if (tooltipTimer) clearTimeout(tooltipTimer);
    tooltipTimer = setTimeout(() => {
      cardTooltip.textContent = card.dataset.filename;
      cardTooltip.setAttribute("aria-hidden", "false");
      cardTooltip.classList.add("visible");
      requestAnimationFrame(() => {
        const rect = card.getBoundingClientRect();
        const tooltipRect = cardTooltip.getBoundingClientRect();
        let left = rect.left + rect.width / 2 - tooltipRect.width / 2;
        const img = card.querySelector("img");
        const anchor = img ? img.getBoundingClientRect() : rect;
        let top = anchor.bottom - tooltipRect.height - 10;
        if (left < 4) left = 4;
        if (left + tooltipRect.width > window.innerWidth - 4) left = window.innerWidth - tooltipRect.width - 4;
        if (top < rect.top + 4) top = rect.top + 4;
        cardTooltip.style.left = left + "px";
        cardTooltip.style.top = top + "px";
      });
    }, 450);
  };
  const hide = () => {
    if (tooltipTimer) clearTimeout(tooltipTimer);
    tooltipTimer = null;
    cardTooltip.classList.remove("visible");
    cardTooltip.setAttribute("aria-hidden", "true");
  };
  card.addEventListener("mouseenter", show);
  card.addEventListener("focusin", show);
  card.addEventListener("mouseleave", hide);
  card.addEventListener("focusout", event => {
    if (!card.contains(event.relatedTarget)) hide();
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") hide();
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
  const source = card.dataset.source || "Desktop";
  const oldKey = fileKey(source, oldName);
  const newKey = fileKey(source, newName);
  const col = getCardColumn(card);
  if (col === "unsorted") {
    decisions.delete(oldKey);
  } else {
    decisions.delete(oldKey);
    decisions.set(newKey, col);
  }
  // Keep currentFileKeys in sync so counts and subsequent triage stay correct
  if (currentFileKeys.has(oldKey)) {
    currentFileKeys.delete(oldKey);
    currentFileKeys.add(newKey);
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
  const thumbBase = `/api/thumb/${encodeURIComponent(newName)}${SsDcl.sourceQuery(source)}`;
  cardImg.src = thumbBase + (thumbBase.includes("?") ? "&" : "?") + `t=${Date.now()}`;
  // Update source tag title remains same source
  setCardActions(card, col);
  updateCounts();
  saveState();
}

function _confirmLightboxRename() {
  if (lightboxRenameInput.disabled || lightboxRenameInput.hidden || lightbox.hidden) return;
  const oldName = lightbox.dataset.currentFilename;
  const source = lightbox.dataset.currentSource || "Desktop";
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
    body: JSON.stringify({ old_name: oldName, new_name: newName, source }),
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
      const card = document.querySelector(`[data-filename="${CSS.escape(oldName)}"][data-source="${CSS.escape(source)}"]`);
      if (card) {
        applyRenameToCard(card, oldName, newName);
      } else {
        // Fallback for legacy bare
        const fallback = document.querySelector(`[data-filename="${CSS.escape(oldName)}"]`);
        if (fallback) applyRenameToCard(fallback, oldName, newName);
      }
      lightbox.dataset.currentFilename = newName;
      const imgBase = `/api/image/${encodeURIComponent(newName)}${SsDcl.sourceQuery(source)}`;
      lightboxImg.src = imgBase + (imgBase.includes("?") ? "&" : "?") + `t=${Date.now()}`;
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
    // Inner controls own their own keys (Enter on Rename must not also
    // toggle the card's selection).
    if (e.target !== card) return;
    const col = getCardColumn(card);
    // Enter/Space toggle multi-select, mirroring the click on the card.
    if (e.key === "Enter" || e.key === " " || e.key === "Spacebar") {
      e.preventDefault();
      toggleSelect(card);
      return;
    }
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
function updateSuggestProgress(processed, total, failures, state) {
  const safeTotal = Math.max(total || 0, 1);
  const percent = Math.min(100, Math.round((processed / safeTotal) * 100));
  suggestProgressFill.style.width = percent + "%";
  if (suggestProgressBar) {
    suggestProgressBar.setAttribute("aria-valuenow", String(percent));
    suggestProgressBar.setAttribute("aria-valuetext", `${processed} of ${total} processed`);
  }
  suggestProgressText.textContent = state || `${processed} of ${total} processed`;
  if (suggestProgressFailure) {
    suggestProgressFailure.textContent = failures ? `${failures} failed` : "";
  }
}

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
    updateSuggestProgress(completed, fingerprints.length, failedCount, message);
    announce(message, { error: true, persistent: true, title: "Suggestions stopped", timeout: 0 });
    setTimeout(() => { suggestProgress.hidden = true; suggestAllBtn.disabled = false; }, 4000);
  }

  function processChunk(chunkIdx) {
    if (_suggestCancelled) {
      updateSuggestProgress(completed, fingerprints.length, failedCount, `Cancelled after ${completed} processed`);
      announce(`Suggestions cancelled after ${completed} processed.`, { type: "warning" });
      setTimeout(() => { suggestProgress.hidden = true; suggestAllBtn.disabled = false; }, 1500);
      return;
    }
    if (chunkIdx >= chunks.length) {
      updateSuggestProgress(fingerprints.length, fingerprints.length, failedCount);
      if (completed === 0 && firstError) {
        updateSuggestProgress(completed, fingerprints.length, failedCount, firstError);
        announce(firstError, { error: true, persistent: true, title: "Suggestions unavailable", timeout: 0 });
        setTimeout(() => { suggestProgress.hidden = true; suggestAllBtn.disabled = false; }, 4000);
      } else if (completed === 0) {
        updateSuggestProgress(completed, fingerprints.length, failedCount, providerErrorCopy());
        announce(providerErrorCopy(), { error: true, persistent: true, title: "Suggestions unavailable", timeout: 0 });
        setTimeout(() => { suggestProgress.hidden = true; suggestAllBtn.disabled = false; }, 3000);
      } else {
        if (failedCount > 0) {
          const result = `Done. ${completed} processed — ${failedCount} file${failedCount > 1 ? "s" : ""} failed`;
          updateSuggestProgress(completed, fingerprints.length, failedCount, result);
          showFeedbackBanner("Some suggestions failed", result, {
            type: "warning",
            details: [`${failedCount} screenshot${failedCount > 1 ? "s" : ""} could not be named.`],
          });
        } else {
          const result = `Done. ${completed} processed`;
          updateSuggestProgress(completed, fingerprints.length, failedCount, result);
          announce(result, { type: "success" });
        }
        if (firstError) {
          announce(firstError, { error: true, persistent: true, title: "Suggestion warning", timeout: 0 });
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
        }
        completed += chunk.length;
        const nextIdx = chunkIdx + 1;
        updateSuggestProgress(completed, fingerprints.length, failedCount);
        processChunk(nextIdx);
      })
      .catch(() => {
        if (!firstError) firstError = providerErrorCopy();
        failedCount += chunk.length;
        completed += chunk.length;
        updateSuggestProgress(completed, fingerprints.length, failedCount);
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
        _setLLMStatus("error");
        announce(h.error || providerErrorCopy(), {
          error: true,
          persistent: true,
          title: "Local AI is offline",
          timeout: 0,
        });
        suggestAllBtn.disabled = false;
        suggestProgress.hidden = true;
        suggestProgressFill.style.width = "0%";
        updateSuggestProgress(0, fingerprints.length, 0, "Waiting for local AI");
        return;
      }
      suggestAllBtn.disabled = true;
      suggestProgress.hidden = false;
      updateSuggestProgress(0, fingerprints.length, 0);
      processChunk(0);
    })
    .catch(() => {
      _setLLMStatus("error");
      announce(providerErrorCopy(), { error: true, persistent: true, title: "Local AI is offline", timeout: 0 });
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
        announce(data.error || "Failed to accept suggestion.", { error: true, persistent: true, title: "Suggestion not accepted", timeout: 0 });
        return;
      }
      const oldName = card.dataset.filename;
      const newName = data.new_name;
      applyRenameToCard(card, oldName, newName);
      announce(`Renamed to ${newName}.`, { type: "success" });
    })
    .catch(() => announce("Network error — suggestion was not accepted.", { error: true, persistent: true, title: "Suggestion failed", timeout: 0 }));
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
      if (!data.ok) {
        announce(data.error || "Could not dismiss the suggestion.", { error: true });
        return;
      }
      card.dataset.memoryStatus = "ignored";
      card.dataset.suggestedName = "";
      const badge = card.querySelector(".suggestion-badge");
      if (badge) badge.remove();
      // Clear category hint
      card.classList.remove("category-hint-keep", "category-hint-trash");
      delete card.dataset.suggestedCategory;
      setCardActions(card, getCardColumn(card));
      announce("Suggestion dismissed.", { type: "success" });
    })
    .catch(() => announce("Network error — suggestion was not dismissed.", { error: true }));
}

// ── Edit suggestion (open rename modal pre-filled with suggested name) ────────
function editSuggestion(card) {
  renameTarget = card;
  renameInput.value = card.dataset.suggestedName || card.dataset.filename;
  renameError.textContent = "";
  openOverlay(renameModal, card, "#rename-input");
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
    announce("No new screenshots to suggest names for.");
    return;
  }
  closeSettingsMenu();
  suggestBatch(newFps);
});

// ── Settings dropdown ──────────────────────────────────────────────────────────
let settingsSnapshot = "";

function readSettingsForm() {
  return JSON.stringify({
    llm_provider: settingsProvider.value,
    llm_model: settingsModel.value.trim(),
    auto_suggest: settingsAuto.checked,
    prune_max_age_days: document.getElementById("settings-prune-age")?.value || "",
    tracked_folders: trackedFoldersWorkingCopy,
  });
}

function updateSettingsDirty() {
  const dirty = readSettingsForm() !== settingsSnapshot;
  settingsSave.disabled = !dirty;
  settingsMenu.classList.toggle("is-dirty", dirty);
  if (settingsSaveStatus && !dirty) settingsSaveStatus.textContent = "";
  return dirty;
}

function resetSettingsForm() {
  settingsProvider.value = llmSettings.llm_provider || "litert";
  settingsModel.value = llmSettings.llm_model || "gemma4-e2b";
  settingsModel.placeholder = LLM_PROVIDER_MODELS[settingsProvider.value] || "gemma4-e2b";
  settingsAuto.checked = llmSettings.auto_suggest || false;
  const pruneAge = document.getElementById("settings-prune-age");
  if (pruneAge) pruneAge.value = llmSettings.prune_max_age_days || 90;
  trackedFoldersWorkingCopy = [...(llmSettings.tracked_folders || [])];
  trackedFolderInfo = llmSettings.tracked_folder_info || [];
  showTrackedError("");
  renderTrackedFolders();
  settingsSnapshot = readSettingsForm();
  if (settingsSaveStatus) settingsSaveStatus.textContent = "";
  updateSettingsDirty();
}

settingsBtn.addEventListener("click", () => {
  if (!settingsMenu.hidden) { closeSettingsMenu(); return; }
  resetSettingsForm();
  openOverlay(settingsMenu, settingsBtn, ".theme-choice");
});

// When the model field holds a legacy/default id, snap it to the LiteRT form.
settingsProvider.addEventListener("change", () => {
  const def = LLM_PROVIDER_MODELS[settingsProvider.value] || "gemma4-e2b";
  settingsModel.placeholder = def;
  if (settingsModel.value.trim() === "gemma4-e2b" || settingsModel.value.trim() === "gemma4:e2b") {
    settingsModel.value = def;
  }
  updateSettingsDirty();
});

function closeSettingsMenu(options) {
  const opts = options || {};
  if (!opts.discard && updateSettingsDirty()) {
    announce("Settings have unsaved changes — save or close them from the panel.", { type: "warning" });
    return false;
  }
  closeOverlay(settingsMenu);
  return true;
}

settingsCancel.addEventListener("click", () => {
  resetSettingsForm();
  closeSettingsMenu({ discard: true });
});
if (settingsCloseBtn) settingsCloseBtn.addEventListener("click", () => {
  resetSettingsForm();
  closeSettingsMenu({ discard: true });
});
// Clicking outside a dirty panel leaves it open so changes cannot disappear.
document.addEventListener("click", e => {
  if (settingsMenu.hidden) return;
  if (settingsMenu.contains(e.target) || settingsBtn.contains(e.target)) return;
  closeSettingsMenu();
});

[settingsModel, settingsAuto, document.getElementById("settings-prune-age")].filter(Boolean).forEach(control => {
  control.addEventListener("input", updateSettingsDirty);
  control.addEventListener("change", updateSettingsDirty);
});
document.addEventListener("input", event => {
  if (settingsMenu.hidden || !settingsMenu.contains(event.target)) return;
  updateSettingsDirty();
});

settingsSave.addEventListener("click", () => {
  if (settingsSave.disabled) return;
  const pruneVal = parseInt(document.getElementById("settings-prune-age")?.value || "90", 10);
  const newSettings = {
    llm_provider: settingsProvider.value,
    llm_model: settingsModel.value.trim() || "gemma4-e2b",
    auto_suggest: settingsAuto.checked,
    prune_max_age_days: isNaN(pruneVal) || pruneVal < 1 ? 90 : pruneVal,
    tracked_folders: trackedFoldersWorkingCopy,
  };

  settingsSave.disabled = true;
  settingsSave.textContent = "Saving…";
  if (settingsSaveStatus) settingsSaveStatus.textContent = "Saving…";
  fetch("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(newSettings),
  })
    .then(r => r.json().then(j => ({ status: r.status, body: j })))
    .then(({ status, body }) => {
      if (status === 200 && body.ok) {
        llmSettings = { ...newSettings, tracked_folder_info: body.tracked_folder_info || trackedFolderInfo };
        settingsSnapshot = readSettingsForm();
        settingsSave.disabled = true;
        if (settingsSaveStatus) settingsSaveStatus.textContent = "Saved";
        settingsSave.textContent = "Save";
        announce("Settings saved.", { type: "success" });
        closeSettingsMenu();
        refreshLLMServerButton();
        // Reload board to reflect new sources
        refreshScreenshots();
      } else {
        settingsSave.disabled = false;
        settingsSave.textContent = "Save";
        showTrackedError(body.error || "Failed to save settings");
        announce(body.error || "Failed to save settings.", { error: true, type: "error" });
      }
    })
    .catch(() => {
      settingsSave.disabled = false;
      settingsSave.textContent = "Save";
      showTrackedError("Network error — please try again");
      announce("Network error — settings were not saved.", { error: true, type: "error" });
    });
});

// ── Undo ─────────────────────────────────────────────────────────────────────
function _persistUndoStack() {
  try { sessionStorage.setItem("undoStack", JSON.stringify(undoStack)); } catch (_) {}
}

undoBtn.addEventListener("click", () => performUndo());
function performUndo() {
  if (undoStack.length === 0) return;
  const action = undoStack.pop();
  // Source-aware selector: find card by both filename and source
  const selSource = action.source || "Desktop";
  const selector = `[data-filename="${CSS.escape(action.filename)}"][data-source="${CSS.escape(selSource)}"]`;
  let card = document.querySelector(selector);
  // Fallback for legacy undo entries without source
  if (!card) card = document.querySelector(`[data-filename="${CSS.escape(action.filename)}"]`);
  if (!card) {
    undoStack.push(action);
    return;
  }
  _persistUndoStack();
  const key = action.key || fileKey(selSource, action.filename);
  if (action.from === "unsorted") {
    decisions.delete(key);
  } else {
    decisions.set(key, action.from);
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
  // Count only decisions whose keys correspond to currently displayed files
  const filtered = new Map();
  for (const [k, v] of decisions) {
    if (currentFileKeys.has(k)) filtered.set(k, v);
  }
  const { keep: nKeep, trash: nTrash, unsorted: nUnsorted, total } = SsDcl.computeCounts(filtered, totalCards);

  countUnsorted.textContent = nUnsorted;
  countTrash.textContent    = nTrash;
  countKeep.textContent     = nKeep;

  // The compact switcher carries the same tallies as the column headers so the
  // hidden columns stay countable at narrow widths (PLAN 6.4).
  compactCountKeep.textContent     = nKeep;
  compactCountUnsorted.textContent = nUnsorted;
  compactCountTrash.textContent    = nTrash;

  // #sort-summary is the stable progress statement and the meter renders the
  // same figure visually; #status-msg is reserved for transient notices.
  const progress = SsDcl.progressSummary({ keep: nKeep, trash: nTrash, unsorted: nUnsorted, total: total });
  sortSummary.textContent = progress.summary;
  progressMeterFill.style.width = progress.percent + "%";
  progressMeter.setAttribute("aria-valuenow", String(progress.percent));
  progressMeter.setAttribute("aria-valuetext", progress.summary);

  // The primary action names itself once there is something to clean up.
  doneBtn.textContent = SsDcl.doneLabel(nTrash);

  undoBtn.disabled = undoStack.length === 0;
  doneBtn.disabled = nTrash === 0;

  if (totalCards > 0 && nUnsorted === 0) {
    setBoardState("sorted");
  } else if (totalCards > 0) {
    [allSortedMsg, scanErrorMsg].forEach(node => { if (node) node.hidden = true; });
  }
}

// ── Rename modal ──────────────────────────────────────────────────────────────
function openRenameModal(card) {
  renameTarget = card;
  renameInput.value = card.dataset.filename;
  renameError.textContent = "";
  openOverlay(renameModal, card, "#rename-input");
  const dotIdx = card.dataset.filename.lastIndexOf(".");
  renameInput.focus();
  if (dotIdx > 0) {
    renameInput.setSelectionRange(0, dotIdx);
  }
}

function closeRenameModal() {
  closeOverlay(renameModal);
  renameTarget = null;
}

renameCancel.addEventListener("click", closeRenameModal);
renameModal.addEventListener("click", e => {
  if (e.target === renameModal) closeRenameModal();
});

renameConfirm.addEventListener("click", () => {
  if (!renameTarget) return;
  const oldName = renameTarget.dataset.filename;
  const source = renameTarget.dataset.source || "Desktop";
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
    body: JSON.stringify({ old_name: oldName, new_name: newName, source }),
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
  openOverlay(confirmModal, doneBtn, "#modal-cancel");
});

function closeModal() {
  closeOverlay(confirmModal);
}

modalCancel.addEventListener("click", closeModal);
// The destructive confirmation has no backdrop dismissal: an accidental
// click outside should never silently discard an important decision prompt.

modalConfirm.addEventListener("click", () => {
  closeModal();

  const toTrash = [...cardsTrash.querySelectorAll(".card")]
    .map(c => ({ source: c.dataset.source || "Desktop", name: c.dataset.filename }));

  if (toTrash.length === 0) return;

  doneBtn.disabled = true;
  announce("Moving to Trash\u2026");

  fetch("/api/done", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ files: toTrash }),
  })
    .then(r => r.json())
    .then(data => {
      const reportedErrors = data.errors || [];

      // Prefer structured errors_detail if present
      const failedKeys = new Set();
      const details = data.errors_detail || data.failed || [];
      if (details.length > 0) {
        details.forEach(d => {
          if (d.source && d.name) failedKeys.add(fileKey(d.source, d.name));
          else if (d.name) failedKeys.add(d.name);
        });
      } else {
        // Legacy fallback: parse "filename: error" strings
        reportedErrors.forEach(e => {
          const parts = e.split(":");
          const name = parts.length > 1 ? parts[0].trim() : e.trim();
          if (name) failedKeys.add(name);
        });
      }
      toTrash.forEach(({ source, name }) => {
        const key = fileKey(source, name);
        if (!failedKeys.has(key) && !failedKeys.has(name)) {
          const card = cardsTrash.querySelector(`[data-filename="${CSS.escape(name)}"][data-source="${CSS.escape(source)}"]`) || cardsTrash.querySelector(`[data-filename="${CSS.escape(name)}"]`);
          if (card) { card.remove(); totalCards--; if (currentFileKeys) currentFileKeys.delete(key); }
          decisions.delete(key);
          // Also clean legacy bare for Desktop
          if (source === "Desktop") decisions.delete(name);
        }
      });

      if (!data.ok || reportedErrors.length > 0 || details.length > 0) {
        showFeedbackBanner(
          "Some screenshots stayed in Trash",
          "Review the details and try again after resolving the file errors.",
          { type: "error", details: reportedErrors.map(String).concat(details.map(d => d.error || `${d.name || "File"}: could not be moved`)) },
        );
      } else {
        announce(`Moved ${toTrash.length} screenshot${toTrash.length !== 1 ? "s" : ""} to Trash.`, { type: "success" });
      }

      undoStack.length = 0;
      clearSelection();

      updateCounts();
      saveState();

      const remaining = document.querySelectorAll(".card").length;
      if (remaining === 0) {
        setBoardState("empty");
        announce("All done!", { type: "success" });
        doneBtn.disabled = true;
      }
    })
    .catch(() => {
      announce("Network error — screenshots were not moved.", { error: true, persistent: true, title: "Trash operation failed", timeout: 0 });
      doneBtn.disabled = false;
      updateCounts();
    });
});
