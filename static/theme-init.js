// Flash-free theme bootstrap and pure theme helpers (Phase 1).
//
// Loaded from <head> *before* style.css so the resolved theme attribute is on
// <html> before the first paint. No inline script is used anywhere — the CSP
// keeps script-src at 'self'. The helpers are exported for node:test through
// module.exports and for app.js through the SsDclTheme global, the same UMD
// pattern as ss_dcl_pure.js.
//
// Attribute contract, kept in sync with static/style.css:
//   auto  -> no data-theme attribute; the prefers-color-scheme media query wins
//   light -> data-theme="light"  (an explicit choice must beat a dark system)
//   dark  -> data-theme="dark"

"use strict";

(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  if (root) {
    root.SsDclTheme = api;
    if (root.document) api.boot(root);
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const THEME_STORAGE_KEY = "ss-dcl-theme";
  const MODES = ["auto", "light", "dark"];
  const NEXT_THEME = { auto: "dark", dark: "light", light: "auto" };
  const DARK_QUERY = "(prefers-color-scheme: dark)";
  const FALLBACK_MODE = "auto";
  const FALLBACK_THEME = "light";

  // Accept a window-like object; fall back to the ambient window when the
  // caller passes nothing (browser) and to null in Node.
  function _win(candidate) {
    if (candidate && candidate.document) return candidate;
    return typeof window !== "undefined" ? window : null;
  }

  function isMode(value) {
    return MODES.indexOf(value) !== -1;
  }

  function normalizeMode(value) {
    return isMode(value) ? value : FALLBACK_MODE;
  }

  // matchMedia can be missing (old engines) or throw (locked-down contexts).
  function systemPrefersDark(win) {
    const w = _win(win);
    if (!w || typeof w.matchMedia !== "function") return false;
    try {
      const query = w.matchMedia(DARK_QUERY);
      return !!(query && query.matches);
    } catch (_) {
      return false;
    }
  }

  // Stored mode plus system preference decide which palette actually paints.
  function resolveTheme(mode, prefersDark) {
    const normalized = normalizeMode(mode);
    if (normalized === FALLBACK_MODE) return prefersDark ? "dark" : FALLBACK_THEME;
    return normalized;
  }

  function effectiveTheme(mode, win) {
    return resolveTheme(mode, systemPrefersDark(win));
  }

  function nextTheme(mode) {
    return NEXT_THEME[normalizeMode(mode)] || FALLBACK_MODE;
  }

  function themeLabel(mode, prefersDark) {
    const normalized = normalizeMode(mode);
    if (normalized === FALLBACK_MODE) {
      return "Theme: auto (" + resolveTheme(FALLBACK_MODE, prefersDark) + ")";
    }
    return "Theme: " + normalized;
  }

  // localStorage throws in Safari private mode; a missing read means "auto".
  function readMode(win) {
    const w = _win(win);
    if (!w || !w.localStorage) return FALLBACK_MODE;
    try {
      const raw = w.localStorage.getItem(THEME_STORAGE_KEY);
      return isMode(raw) ? raw : FALLBACK_MODE;
    } catch (_) {
      return FALLBACK_MODE;
    }
  }

  function writeMode(mode, win) {
    const w = _win(win);
    if (!w || !w.localStorage) return false;
    try {
      w.localStorage.setItem(THEME_STORAGE_KEY, normalizeMode(mode));
      return true;
    } catch (_) {
      return false;
    }
  }

  function applyTheme(mode, win) {
    const w = _win(win);
    const doc = w && w.document;
    const normalized = normalizeMode(mode);
    const resolved = resolveTheme(normalized, systemPrefersDark(w));
    if (!doc || !doc.documentElement) return resolved;
    if (normalized === FALLBACK_MODE) {
      doc.documentElement.removeAttribute("data-theme");
    } else {
      doc.documentElement.setAttribute("data-theme", normalized);
    }
    return resolved;
  }

  function cycleTheme(win) {
    const w = _win(win);
    const next = nextTheme(readMode(w));
    writeMode(next, w);
    applyTheme(next, w);
    return next;
  }

  // Runs at parse time in the browser: store the resolved theme before paint.
  function boot(win) {
    const w = _win(win);
    const mode = readMode(w);
    applyTheme(mode, w);
    return mode;
  }

  return {
    THEME_STORAGE_KEY: THEME_STORAGE_KEY,
    MODES: MODES,
    NEXT_THEME: NEXT_THEME,
    DARK_QUERY: DARK_QUERY,
    FALLBACK_MODE: FALLBACK_MODE,
    isMode: isMode,
    normalizeMode: normalizeMode,
    systemPrefersDark: systemPrefersDark,
    resolveTheme: resolveTheme,
    effectiveTheme: effectiveTheme,
    nextTheme: nextTheme,
    themeLabel: themeLabel,
    readMode: readMode,
    writeMode: writeMode,
    applyTheme: applyTheme,
    cycleTheme: cycleTheme,
    boot: boot,
  };
});
