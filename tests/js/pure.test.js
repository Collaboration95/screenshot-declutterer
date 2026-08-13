// Unit tests for the pure frontend logic (issue #92).
// Run: node --test tests/js/
// No DOM required — ss_dcl_pure.js exports via module.exports.

"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");

const SsDcl = require("../../static/ss_dcl_pure.js");

// ── batchFanLayout ──────────────────────────────────────────────────────────

test("batchFanLayout: middle tile is centered and straight", () => {
  const layout = SsDcl.batchFanLayout(5);
  assert.equal(layout.length, 5);
  const mid = layout[2];
  assert.equal(mid.dx, 0);
  assert.equal(mid.dy, 0);
  assert.equal(mid.rot, 0);
});

test("batchFanLayout: layout is symmetric around the middle", () => {
  const layout = SsDcl.batchFanLayout(5);
  assert.deepEqual(layout[0].dx, -layout[4].dx);
  assert.deepEqual(layout[0].rot, -layout[4].rot);
  assert.deepEqual(layout[1].dx, -layout[3].dx);
  assert.deepEqual(layout[1].rot, -layout[3].rot);
});

test("batchFanLayout: outer tiles tilt more and rise higher", () => {
  const layout = SsDcl.batchFanLayout(5);
  assert.ok(Math.abs(layout[0].rot) > Math.abs(layout[1].rot));
  assert.ok(Math.abs(layout[0].dy) > Math.abs(layout[1].dy));
});

test("batchFanLayout: even tile count has no dead center", () => {
  const layout = SsDcl.batchFanLayout(4);
  assert.equal(layout.length, 4);
  // No tile sits exactly on the middle (mid = 1.5 → dx is never 0)
  assert.ok(layout.every(t => t.dx !== 0));
});

test("batchFanLayout: single tile is centered", () => {
  const layout = SsDcl.batchFanLayout(1);
  assert.deepEqual(layout, [{ dx: 0, dy: 0, rot: 0 }]);
});

// ── Path_name ───────────────────────────────────────────────────────────────

test("Path_name: strips POSIX directories", () => {
  assert.equal(SsDcl.Path_name("/tmp/x/Screenshot 1.png"), "Screenshot 1.png");
});

test("Path_name: strips Windows directories", () => {
  assert.equal(SsDcl.Path_name("C:\\Users\\me\\Screenshot 1.png"), "Screenshot 1.png");
});

test("Path_name: plain filename passes through", () => {
  assert.equal(SsDcl.Path_name("Screenshot 1.png"), "Screenshot 1.png");
});

// ── computeCounts ───────────────────────────────────────────────────────────

test("computeCounts: splits decisions into keep/trash/unsorted", () => {
  const decisions = new Map([
    ["a.png", "keep"],
    ["b.png", "trash"],
    ["c.png", "keep"],
  ]);
  assert.deepEqual(SsDcl.computeCounts(decisions, 5), {
    keep: 2,
    trash: 1,
    unsorted: 2,
    total: 5,
  });
});

test("computeCounts: empty decisions are all unsorted", () => {
  assert.deepEqual(SsDcl.computeCounts(new Map(), 3), {
    keep: 0,
    trash: 0,
    unsorted: 3,
    total: 3,
  });
});

test("computeCounts: unknown values count as unsorted", () => {
  const decisions = new Map([["a.png", "keep"], ["b.png", "maybe"]]);
  const counts = SsDcl.computeCounts(decisions, 4);
  assert.equal(counts.keep, 1);
  assert.equal(counts.unsorted, 3);
});

// ── chunked ─────────────────────────────────────────────────────────────────

test("chunked: splits into contiguous chunks of chunkSize", () => {
  const items = [1, 2, 3, 4, 5, 6, 7];
  assert.deepEqual(SsDcl.chunked(items, 3), [[1, 2, 3], [4, 5, 6], [7]]);
});

test("chunked: exact multiple yields equal chunks", () => {
  assert.deepEqual(SsDcl.chunked([1, 2, 3, 4], 2), [[1, 2], [3, 4]]);
});

test("chunked: empty input yields no chunks", () => {
  assert.deepEqual(SsDcl.chunked([], 5), []);
});

test("chunked: single chunk when smaller than chunkSize", () => {
  assert.deepEqual(SsDcl.chunked([1, 2], 5), [[1, 2]]);
});
