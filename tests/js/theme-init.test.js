// Unit tests for the flash-free theme bootstrap (Phase 1).
// Run: node --test tests/js/
// No browser required - static/theme-init.js exports via module.exports.

"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");

const MODULE_PATH = require.resolve("../../static/theme-init.js");
const SsDclTheme = require("../../static/theme-init.js");

// -- stubs ------------------------------------------------------------------

// Minimal <html> element stub that records data-theme like the real DOM.
function makeDocumentElement() {
  const attrs = new Map();
  return {
    setAttribute(name, value) {
      attrs.set(name, String(value));
    },
    removeAttribute(name) {
      attrs.delete(name);
    },
    getAttribute(name) {
      return attrs.has(name) ? attrs.get(name) : null;
    },
    hasAttribute(name) {
      return attrs.has(name);
    },
  };
}

// Window-like object with a stubbed document, localStorage and matchMedia.
function makeWindow(options) {
  const opts = options || {};
  const store = new Map();
  if (opts.stored !== undefined && opts.stored !== null) {
    store.set(SsDclTheme.THEME_STORAGE_KEY, String(opts.stored));
  }
  const win = {
    document: { documentElement: makeDocumentElement() },
    localStorage: {
      getItem(key) {
        if (opts.throwOnStorage) throw new Error("localStorage is blocked");
        return store.has(key) ? store.get(key) : null;
      },
      setItem(key, value) {
        if (opts.throwOnStorage) throw new Error("localStorage is blocked");
        store.set(key, String(value));
      },
    },
    _store: store,
  };
  if (!opts.noMatchMedia) {
    win.matchMedia = function () {
      return { matches: !!opts.prefersDark, addEventListener() {} };
    };
  }
  return win;
}

function storedMode(win) {
  return win._store.has(SsDclTheme.THEME_STORAGE_KEY)
    ? win._store.get(SsDclTheme.THEME_STORAGE_KEY)
    : null;
}

// -- module surface ---------------------------------------------------------

test("exports the storage key, modes and the full helper surface", () => {
  assert.equal(SsDclTheme.THEME_STORAGE_KEY, "ss-dcl-theme");
  assert.deepEqual(SsDclTheme.MODES, ["auto", "light", "dark"]);
  assert.deepEqual(SsDclTheme.NEXT_THEME, { auto: "dark", dark: "light", light: "auto" });
  assert.equal(SsDclTheme.DARK_QUERY, "(prefers-color-scheme: dark)");
  assert.equal(SsDclTheme.FALLBACK_MODE, "auto");
  const surface = [
    "isMode",
    "normalizeMode",
    "systemPrefersDark",
    "resolveTheme",
    "effectiveTheme",
    "nextTheme",
    "themeLabel",
    "readMode",
    "writeMode",
    "applyTheme",
    "cycleTheme",
    "boot",
  ];
  for (const name of surface) {
    assert.equal(typeof SsDclTheme[name], "function", name + " should be a function");
  }
});

// -- isMode / normalizeMode -------------------------------------------------

test("isMode accepts only the three known modes", () => {
  assert.equal(SsDclTheme.isMode("auto"), true);
  assert.equal(SsDclTheme.isMode("light"), true);
  assert.equal(SsDclTheme.isMode("dark"), true);
  for (const bad of ["", "AUTO", "sunset", null, undefined, 0]) {
    assert.equal(SsDclTheme.isMode(bad), false, "isMode(" + String(bad) + ")");
  }
});

test("normalizeMode falls back to auto for unknown input", () => {
  assert.equal(SsDclTheme.normalizeMode("dark"), "dark");
  assert.equal(SsDclTheme.normalizeMode("nonsense"), "auto");
  assert.equal(SsDclTheme.normalizeMode(null), "auto");
  assert.equal(SsDclTheme.normalizeMode(undefined), "auto");
  assert.equal(SsDclTheme.normalizeMode("Light"), "auto");
});

// -- nextTheme --------------------------------------------------------------

test("nextTheme cycles auto -> dark -> light -> auto", () => {
  assert.equal(SsDclTheme.nextTheme("auto"), "dark");
  assert.equal(SsDclTheme.nextTheme("dark"), "light");
  assert.equal(SsDclTheme.nextTheme("light"), "auto");
});

test("nextTheme normalizes unknown input before cycling", () => {
  assert.equal(SsDclTheme.nextTheme("bogus"), "dark");
  assert.equal(SsDclTheme.nextTheme(undefined), "dark");
});

// -- resolveTheme / effectiveTheme -----------------------------------------

test("resolveTheme: auto follows the system preference", () => {
  assert.equal(SsDclTheme.resolveTheme("auto", true), "dark");
  assert.equal(SsDclTheme.resolveTheme("auto", false), "light");
});

test("resolveTheme: an explicit choice beats the system preference", () => {
  assert.equal(SsDclTheme.resolveTheme("light", true), "light");
  assert.equal(SsDclTheme.resolveTheme("dark", false), "dark");
});

test("resolveTheme: unknown modes degrade to auto behaviour", () => {
  assert.equal(SsDclTheme.resolveTheme("sunset", true), "dark");
  assert.equal(SsDclTheme.resolveTheme(null, false), "light");
});

test("effectiveTheme reads matchMedia from the supplied window", () => {
  assert.equal(SsDclTheme.effectiveTheme("auto", makeWindow({ prefersDark: true })), "dark");
  assert.equal(SsDclTheme.effectiveTheme("auto", makeWindow({ prefersDark: false })), "light");
  assert.equal(SsDclTheme.effectiveTheme("light", makeWindow({ prefersDark: true })), "light");
});

test("systemPrefersDark is false when matchMedia is missing or throws", () => {
  assert.equal(SsDclTheme.systemPrefersDark(makeWindow({ noMatchMedia: true })), false);
  assert.equal(SsDclTheme.systemPrefersDark(null), false);
  const throwing = {
    document: {},
    matchMedia() {
      throw new Error("matchMedia is blocked");
    },
  };
  assert.equal(SsDclTheme.systemPrefersDark(throwing), false);
});

// -- themeLabel -------------------------------------------------------------

test("themeLabel names the mode and resolves auto for the reader", () => {
  assert.equal(SsDclTheme.themeLabel("light", true), "Theme: light");
  assert.equal(SsDclTheme.themeLabel("dark", false), "Theme: dark");
  assert.equal(SsDclTheme.themeLabel("auto", true), "Theme: auto (dark)");
  assert.equal(SsDclTheme.themeLabel("auto", false), "Theme: auto (light)");
  assert.equal(SsDclTheme.themeLabel("garbage", true), "Theme: auto (dark)");
});

// -- readMode / writeMode ---------------------------------------------------

test("readMode returns auto with no window, no storage or an empty store", () => {
  assert.equal(SsDclTheme.readMode(null), "auto");
  assert.equal(SsDclTheme.readMode({}), "auto");
  assert.equal(SsDclTheme.readMode(makeWindow()), "auto");
});

test("readMode rejects a corrupted stored value", () => {
  assert.equal(SsDclTheme.readMode(makeWindow({ stored: "sunset" })), "auto");
  assert.equal(SsDclTheme.readMode(makeWindow({ stored: "DARK" })), "auto");
  assert.equal(SsDclTheme.readMode(makeWindow({ stored: "dark" })), "dark");
  assert.equal(SsDclTheme.readMode(makeWindow({ stored: "light" })), "light");
});

test("writeMode round-trips through localStorage", () => {
  const win = makeWindow();
  assert.equal(SsDclTheme.writeMode("dark", win), true);
  assert.equal(storedMode(win), "dark");
  assert.equal(SsDclTheme.readMode(win), "dark");
  assert.equal(SsDclTheme.writeMode("light", win), true);
  assert.equal(SsDclTheme.readMode(win), "light");
});

test("writeMode normalizes before storing", () => {
  const win = makeWindow();
  assert.equal(SsDclTheme.writeMode("nonsense", win), true);
  assert.equal(storedMode(win), "auto");
});

test("readMode and writeMode never throw when storage is blocked", () => {
  const win = makeWindow({ stored: "dark", throwOnStorage: true });
  assert.equal(SsDclTheme.readMode(win), "auto");
  assert.equal(SsDclTheme.writeMode("dark", win), false);
});

// -- applyTheme -------------------------------------------------------------

test("applyTheme: auto removes the attribute so the media query wins", () => {
  const win = makeWindow({ stored: "dark" });
  const html = win.document.documentElement;
  html.setAttribute("data-theme", "dark");
  assert.equal(SsDclTheme.applyTheme("auto", win), "light");
  assert.equal(html.hasAttribute("data-theme"), false);
});

test("applyTheme: light and dark write the matching attribute", () => {
  const win = makeWindow();
  const html = win.document.documentElement;
  assert.equal(SsDclTheme.applyTheme("light", win), "light");
  assert.equal(html.getAttribute("data-theme"), "light");
  assert.equal(SsDclTheme.applyTheme("dark", win), "dark");
  assert.equal(html.getAttribute("data-theme"), "dark");
});

test("applyTheme: explicit light beats a dark system preference", () => {
  const win = makeWindow({ prefersDark: true });
  assert.equal(SsDclTheme.applyTheme("light", win), "light");
  assert.equal(win.document.documentElement.getAttribute("data-theme"), "light");
});

test("applyTheme returns the resolved theme without a document", () => {
  assert.equal(SsDclTheme.applyTheme("auto", null), "light");
  assert.equal(SsDclTheme.applyTheme("dark", {}), "dark");
});

// -- cycleTheme -------------------------------------------------------------

test("cycleTheme persists the next mode and applies it", () => {
  const win = makeWindow({ prefersDark: true });
  assert.equal(SsDclTheme.cycleTheme(win), "dark");
  assert.equal(storedMode(win), "dark");
  assert.equal(win.document.documentElement.getAttribute("data-theme"), "dark");
  assert.equal(SsDclTheme.cycleTheme(win), "light");
  assert.equal(storedMode(win), "light");
  assert.equal(win.document.documentElement.getAttribute("data-theme"), "light");
  assert.equal(SsDclTheme.cycleTheme(win), "auto");
  assert.equal(storedMode(win), "auto");
  assert.equal(win.document.documentElement.hasAttribute("data-theme"), false);
});

test("cycleTheme survives blocked storage by still applying the attribute", () => {
  const win = makeWindow({ throwOnStorage: true });
  assert.equal(SsDclTheme.cycleTheme(win), "dark");
  assert.equal(win.document.documentElement.getAttribute("data-theme"), "dark");
});

// -- boot -------------------------------------------------------------------

test("boot resolves the stored mode and paints it before returning", () => {
  const win = makeWindow({ stored: "dark" });
  assert.equal(SsDclTheme.boot(win), "dark");
  assert.equal(win.document.documentElement.getAttribute("data-theme"), "dark");
  const autoWin = makeWindow({ stored: "bogus", prefersDark: true });
  assert.equal(SsDclTheme.boot(autoWin), "auto");
  assert.equal(autoWin.document.documentElement.hasAttribute("data-theme"), false);
});

test("requiring the module in a browser-like global applies the theme at once", () => {
  const win = makeWindow({ stored: "dark" });
  const previousWindow = globalThis.window;
  const previousDocument = globalThis.document;
  const previousStorage = globalThis.localStorage;
  globalThis.window = win;
  globalThis.document = win.document;
  globalThis.localStorage = win.localStorage;
  delete require.cache[MODULE_PATH];
  try {
    require(MODULE_PATH);
    assert.equal(win.document.documentElement.getAttribute("data-theme"), "dark");
  } finally {
    delete require.cache[MODULE_PATH];
    if (previousWindow === undefined) delete globalThis.window;
    else globalThis.window = previousWindow;
    if (previousDocument === undefined) delete globalThis.document;
    else globalThis.document = previousDocument;
    if (previousStorage === undefined) delete globalThis.localStorage;
    else globalThis.localStorage = previousStorage;
  }
});

test("requiring the module without a document leaves the DOM untouched", () => {
  delete require.cache[MODULE_PATH];
  try {
    assert.doesNotThrow(() => {
      require(MODULE_PATH);
    });
  } finally {
    delete require.cache[MODULE_PATH];
    require(MODULE_PATH);
  }
});
