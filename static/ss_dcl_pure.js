// Pure frontend logic, extracted from app.js so it can be unit-tested with
// node:test (issue #92). No DOM access — safe to load in Node via
// module.exports and in the browser via the SsDcl global (loaded before
// app.js in index.html).

"use strict";

(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  if (root) {
    root.SsDcl = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  // Fan geometry constants (4:3 tiles, matching the thumbnail ratio).
  const GHOST_TILE_W = 252;
  const GHOST_TILE_H = 189;

  // Deterministic fan layout: tiles tilt away from the middle card, which
  // stays straight-on as the "front" of the stack. Horizontal/vertical
  // stagger scales with tile size so the fan stays legible at any tile size.
  function batchFanLayout(tileCount) {
    const layout = [];
    const mid = (tileCount - 1) / 2;
    for (let i = 0; i < tileCount; i++) {
      layout.push({
        dx: Math.round((i - mid) * (GHOST_TILE_W * 0.112)) || 0, // ≈28px @ 252px tiles
        dy: Math.round(Math.abs(i - mid) * -(GHOST_TILE_H * 0.042)) || 0, // ≈ -8px
        rot: Math.round((i - mid) * 7) || 0,
      });
    }
    return layout;
  }

  // Strip any path component — filenames must not smuggle separators.
  function Path_name(filename) {
    return filename.split("/").pop().split("\\").pop();
  }

  // Column counts derived from the decisions map + total card count.
  // decisions: Map<filename, "keep"|"trash"> (any other value counts as
  // unsorted). Keys may be "source|name" for tracked folders or bare for Desktop.
  function computeCounts(decisions, totalCards) {
    let keep = 0;
    let trash = 0;
    for (const v of decisions.values()) {
      if (v === "keep") keep++;
      else if (v === "trash") trash++;
    }
    const unsorted = totalCards - keep - trash;
    return { keep, trash, unsorted, total: totalCards };
  }

  // Split items into contiguous chunks of at most chunkSize.
  function chunked(items, chunkSize) {
    const chunks = [];
    for (let i = 0; i < items.length; i += chunkSize) {
      chunks.push(items.slice(i, i + chunkSize));
    }
    return chunks;
  }

  // ── Tracking folders helpers ──────────────────────────────────────
  const DEFAULT_SOURCE = "Desktop";
  function _enc(s) {
    return s.replace(/\|/g, "%7C");
  }
  function _dec(s) {
    return s.replace(/%7C/g, "|");
  }
  function decisionKey(source, name) {
    if (!source || source === DEFAULT_SOURCE) {
      if (name.includes("|")) return _enc(name);
      return name;
    }
    return `${_enc(source)}|${_enc(name)}`;
  }
  function parseDecisionKey(key) {
    if (key.startsWith(`${DEFAULT_SOURCE}|`)) {
      return { source: DEFAULT_SOURCE, name: _dec(key.slice(DEFAULT_SOURCE.length + 1)) };
    }
    if (key.indexOf("|") === -1) {
      if (key.indexOf("%7C") !== -1) {
        return { source: DEFAULT_SOURCE, name: _dec(key) };
      }
      return { source: DEFAULT_SOURCE, name: key };
    }
    const idx = key.indexOf("|");
    const sourceEnc = key.slice(0, idx);
    const nameEnc = key.slice(idx + 1);
    const source = _dec(sourceEnc);
    const name = _dec(nameEnc);
    if (!source) return { source: DEFAULT_SOURCE, name: _dec(key) };
    if (source !== DEFAULT_SOURCE && !source.startsWith("/")) {
      return { source: DEFAULT_SOURCE, name: _dec(key) };
    }
    return { source, name };
  }
  function fileKey(file) {
    return decisionKey(file.source || DEFAULT_SOURCE, file.name);
  }
  function sourceQuery(source) {
    if (!source || source === DEFAULT_SOURCE) return "";
    return `?source=${encodeURIComponent(source)}`;
  }
  function sourceQueryParam(source) {
    if (!source || source === DEFAULT_SOURCE) return "";
    return `&source=${encodeURIComponent(source)}`;
  }
  function cardSelector(source, filename) {
    // Use CSS.escape for filename, but here we return a string to be used with querySelector
    // Caller should escape.
    return { source, filename };
  }

  return {
    GHOST_TILE_W,
    GHOST_TILE_H,
    batchFanLayout,
    Path_name,
    computeCounts,
    chunked,
    DEFAULT_SOURCE,
    decisionKey,
    parseDecisionKey,
    fileKey,
    sourceQuery,
    sourceQueryParam,
    cardSelector,
  };
});
