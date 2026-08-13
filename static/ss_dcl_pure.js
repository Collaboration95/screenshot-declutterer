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
  // unsorted).
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

  return {
    GHOST_TILE_W,
    GHOST_TILE_H,
    batchFanLayout,
    Path_name,
    computeCounts,
    chunked,
  };
});
