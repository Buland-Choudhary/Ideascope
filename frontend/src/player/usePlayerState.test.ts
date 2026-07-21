import { act, renderHook } from "@testing-library/react";
import { expect, test } from "vitest";

import { getFixture } from "../fixtures";
import type { Lesson } from "../types/lesson";
import { usePlayerState } from "./usePlayerState";

const lesson = getFixture("fixture-sine-wave") as Lesson;

test("starts at the first beat with default params", () => {
  const { result } = renderHook(() => usePlayerState(lesson));
  expect(result.current.index).toBe(0);
  expect(result.current.canPrev).toBe(false);
  expect(result.current.canNext).toBe(true);
  // Beat 0 has no manipulables.
  expect(result.current.params).toEqual({});
});

test("advances and clamps at the end", () => {
  const { result } = renderHook(() => usePlayerState(lesson));
  act(() => result.current.next());
  expect(result.current.index).toBe(1);
  // Beat 1 (amplitude slider) resets to its default.
  expect(result.current.params).toEqual({ amplitude: 40 });

  act(() => result.current.next());
  act(() => result.current.next()); // beyond the end — clamps
  expect(result.current.index).toBe(2);
  expect(result.current.isLast).toBe(true);
  expect(result.current.canNext).toBe(false);
});

test("setParam updates the current beat's value", () => {
  const { result } = renderHook(() => usePlayerState(lesson));
  act(() => result.current.next()); // beat 1
  act(() => result.current.setParam("amplitude", 90));
  expect(result.current.params.amplitude).toBe(90);
});

test("navigating back resets params to defaults", () => {
  const { result } = renderHook(() => usePlayerState(lesson));
  act(() => result.current.next());
  act(() => result.current.setParam("amplitude", 90));
  act(() => result.current.prev());
  act(() => result.current.next());
  expect(result.current.params.amplitude).toBe(40);
});
