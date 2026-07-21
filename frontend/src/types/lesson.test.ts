import { expect, test } from "vitest";

import type { Beat, Lesson } from "./lesson";

// Compile-time check that the mirrored types are internally consistent and
// ergonomic to construct. `tsc` enforces the shape; the runtime asserts keep
// vitest happy and guard against accidental structural drift.

const sampleBeat: Beat = {
  id: "b0",
  index: 0,
  intent: "Introduce the concept.",
  primitive: "plot",
  engine: "canvas",
  narration: { text: "A short narration." },
  scene: { code: "export default () => ({})" },
  manipulables: [
    { id: "amp", label: "Amplitude", type: "slider", param: "amplitude", default: 40, min: 5, max: 120, step: 1 },
    { id: "stg", label: "Stage", type: "stepper", param: "stage", default: 0, min: 0, max: 2, step: 1 },
    { id: "lbl", label: "Show labels", type: "toggle", param: "showLabels", default: true },
  ],
  status: "ready",
};

const sampleLesson: Lesson = {
  id: "sample",
  topic: "Sample topic",
  params: { duration: "short" },
  outline: { title: "Sample", summary: "A sample lesson.", targetBeatCount: 1 },
  beats: [sampleBeat],
};

test("a typed lesson literal has the expected shape", () => {
  expect(sampleLesson.beats).toHaveLength(1);
  expect(sampleLesson.beats[0].engine).toBe("canvas");
  expect(sampleLesson.beats[0].manipulables.map((m) => m.type)).toEqual([
    "slider",
    "stepper",
    "toggle",
  ]);
});
