import test from "node:test";
import assert from "node:assert/strict";
import { createIdleSnapshotScheduler } from "./snapshotScheduler.js";

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

test("debounces rapid updates into one dispatch", async () => {
  const calls: number[] = [];
  const scheduler = createIdleSnapshotScheduler(20, async (documentId) => {
    calls.push(documentId);
  });

  scheduler.onUpdate(42);
  scheduler.onUpdate(42);
  scheduler.onUpdate(42);

  await sleep(60);
  scheduler.dispose();

  assert.equal(calls.length, 1);
  assert.equal(calls[0], 42);
});

test("queues another dispatch when updates happen during in-flight dispatch", async () => {
  const calls: number[] = [];
  const scheduler = createIdleSnapshotScheduler(10, async (documentId) => {
    calls.push(documentId);
    await sleep(30);
  });

  scheduler.onUpdate(7);
  await sleep(15); // first dispatch started
  scheduler.onUpdate(7); // should queue second idle window

  await sleep(90);
  scheduler.dispose();

  assert.equal(calls.length, 2);
  assert.deepEqual(calls, [7, 7]);
});

test("purge cancels queued idle dispatch for a document", async () => {
  const calls: number[] = [];
  const scheduler = createIdleSnapshotScheduler(30, async (documentId) => {
    calls.push(documentId);
  });

  scheduler.onUpdate(99);
  scheduler.purge(99);

  await sleep(70);
  scheduler.dispose();

  assert.equal(calls.length, 0);
});