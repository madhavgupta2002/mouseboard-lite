import test from "node:test";
import assert from "node:assert/strict";
import {Motion, textEdit} from "../web/motion.mjs";

function sweep(start, end, steps = 60) {
  const motion = new Motion();
  let x = 0, y = 0;
  for (let i = 0; i <= steps; i++) {
    const angles = start.map((value, axis) => value + (end[axis] - value) * i / steps);
    const delta = motion.update(...angles, i / 60);
    x += delta[0]; y += delta[1];
  }
  return [x, y];
}

test("screen-up right turn moves horizontally, not vertically", () => {
  const [x, y] = sweep([0, 0, 0], [-20, 0, 0]);
  assert.ok(x > 200);
  assert.ok(Math.abs(y) < 0.01);
});

test("lifting the phone moves upward, not horizontally", () => {
  const [x, y] = sweep([0, 0, 0], [0, 20, 0]);
  assert.ok(y < -200);
  assert.ok(Math.abs(x) < 0.01);
});

test("both axes work together", () => {
  const [x, y] = sweep([0, 0, 0], [-20, 15, 0]);
  assert.ok(x > 150 && y < -150);
});

test("stationary noise stays still", () => {
  const motion = new Motion();
  let distance = 0;
  motion.update(0, 0, 0, 0);
  for (let i = 1; i < 1000; i++)
    distance += Math.hypot(...motion.update(i % 2 ? 0.02 : -0.02, 0, 0, i / 60));
  assert.equal(distance, 0);
});

test("heading wrap from 359 to 0 does not jump", () => {
  const motion = new Motion();
  motion.update(359.9, 0, 0, 0);
  const [x, y] = motion.update(0.1, 0, 0, 1 / 60);
  assert.ok(Math.abs(x) < 4 && Math.abs(y) < 0.01);
});

test("equivalent Euler representations do not move the cursor", () => {
  const motion = new Motion();
  motion.update(0, 0, 0, 0);
  assert.ok(Math.hypot(...motion.update(180, 180, 180, 1 / 60)) < 0.01);
});

test("recenter, a stale sample, and a huge sensor jump emit no movement", () => {
  const motion = new Motion();
  motion.update(0, 0, 0, 0);
  assert.deepEqual(motion.update(90, 0, 0, 1 / 60), [0, 0]);
  assert.deepEqual(motion.update(91, 0, 0, 2), [0, 0]);
  motion.reset();
  assert.deepEqual(motion.update(140, 20, 0, 3), [0, 0]);
});

test("missing sensor values are ignored", () => {
  const motion = new Motion();
  assert.deepEqual(motion.update(null, 0, 0, 1), [0, 0]);
  assert.deepEqual(motion.update(NaN, 0, 0, 1), [0, 0]);
});

test("keyboard diff supports ordinary typing, deletion, and autocorrect", () => {
  assert.deepEqual(textEdit("he", "hey"), {type: "text", remove: 0, text: "y"});
  assert.deepEqual(textEdit("hey", "he"), {type: "text", remove: 1, text: ""});
  assert.deepEqual(textEdit("teh", "the "), {type: "text", remove: 2, text: "he "});
});
