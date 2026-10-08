"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const { CleanupBatches } = require("../../static/ss_dcl_pure.js");
const seventeen = Array.from({ length: 17 }, (_, i) => `shot-${i}`);

test("17 suggestions advance explicitly through 5, 5, 5, 2", () => {
  const batches = new CleanupBatches();
  batches.reconcile(seventeen, seventeen);
  const reviewed = [];
  for (const count of [5, 5, 5, 2]) {
    const view = batches.view(seventeen);
    assert.equal(view.shown.length, count);
    reviewed.push(...view.shown);
    batches.advance(seventeen);
  }
  assert.deepEqual(reviewed, seventeen);
  assert.equal(batches.view(seventeen).waiting.length, 0);
});

test("Keep/queue vacate slots; undo restores them without taking waiting cards", () => {
  const batches = new CleanupBatches();
  batches.reconcile(seventeen, seventeen);
  const decided = seventeen.slice(5);
  assert.deepEqual(batches.reconcile(decided, seventeen), { shown: [], waiting: decided });
  assert.deepEqual(batches.view(seventeen).shown, seventeen.slice(0, 5));
});

test("next batch defers unresolved cards; earlier-batch undo stays ordinary", () => {
  const batches = new CleanupBatches();
  batches.reconcile(seventeen, seventeen);
  batches.advance(seventeen.slice(1)); // First card kept; four unresolved.
  assert.deepEqual(batches.view(seventeen), {
    shown: seventeen.slice(5, 10),
    waiting: seventeen.slice(10),
  });
  assert.equal(batches.deferred.has(seventeen[0]), true);
});

test("rescan and sort preserve membership and remove stale slots without filling", () => {
  const batches = new CleanupBatches();
  batches.reconcile(seventeen, seventeen);
  const reversed = [...seventeen].reverse().filter(key => key !== "shot-2");
  const view = batches.reconcile(reversed, reversed);
  assert.deepEqual(view.shown, ["shot-4", "shot-3", "shot-1", "shot-0"]);
  batches.advance(reversed);
  assert.deepEqual(batches.view(reversed).shown, reversed.slice(0, 5));
});

test("rename preserves batch membership and prior-batch deferral", () => {
  const batches = new CleanupBatches();
  batches.reconcile(seventeen, seventeen);
  batches.rename("shot-0", "renamed-0");
  const renamed = ["renamed-0", ...seventeen.slice(1)];
  assert.deepEqual(batches.reconcile(renamed, renamed).shown, renamed.slice(0, 5));
  batches.advance(renamed);
  batches.rename("renamed-0", "renamed-again");
  assert.equal(batches.deferred.has("renamed-again"), true);
  assert.equal(batches.deferred.has("renamed-0"), false);
});

test("new candidates on refresh wait for an explicit advance", () => {
  const batches = new CleanupBatches();
  batches.reconcile([], []);
  assert.deepEqual(batches.reconcile(seventeen, seventeen), { shown: [], waiting: seventeen });
  batches.advance(seventeen);
  assert.deepEqual(batches.view(seventeen).shown, seventeen.slice(0, 5));
});
