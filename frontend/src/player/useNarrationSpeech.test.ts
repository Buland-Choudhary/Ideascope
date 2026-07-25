import { act, renderHook } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

import { FakeSpeechSynthesis, installFakeSpeechSynthesis } from "../test-support/fakeSpeechSynthesis";
import { useNarrationSpeech } from "./useNarrationSpeech";

let fake: FakeSpeechSynthesis;

// No afterEach(vi.unstubAllGlobals) here deliberately: a hook mounted by an
// earlier test can still run its unmount cleanup (stop()) after that test
// ends, and if globals were already unstubbed by then, stop() would throw on
// a `supported` flag that's now stale. Each test's beforeEach reinstalls a
// fresh fake anyway, which is all the isolation these tests need.
beforeEach(() => {
  fake = installFakeSpeechSynthesis(vi);
});

test("starts disabled and reports the API as supported", () => {
  const { result } = renderHook(() => useNarrationSpeech());
  expect(result.current.enabled).toBe(false);
  expect(result.current.supported).toBe(true);
});

test("speak is a no-op while disabled", () => {
  const { result } = renderHook(() => useNarrationSpeech());
  act(() => result.current.speak("hello"));
  expect(fake.spoken).toEqual([]);
});

test("toggling on then speaking calls speechSynthesis.speak with the text", () => {
  const { result } = renderHook(() => useNarrationSpeech());
  act(() => result.current.toggle());
  expect(result.current.enabled).toBe(true);

  act(() => result.current.speak("A sine wave repeats forever."));
  expect(fake.spoken).toEqual(["A sine wave repeats forever."]);
});

test("speak cancels any speech already in progress first", () => {
  const { result } = renderHook(() => useNarrationSpeech());
  act(() => result.current.toggle());
  act(() => result.current.speak("first"));
  act(() => result.current.speak("second"));
  expect(fake.cancelCount).toBeGreaterThanOrEqual(2); // once per speak() call
  expect(fake.spoken).toEqual(["first", "second"]);
});

test("toggling off cancels in-progress speech", () => {
  const { result } = renderHook(() => useNarrationSpeech());
  act(() => result.current.toggle());
  act(() => result.current.speak("hello"));
  const cancelsBefore = fake.cancelCount;

  act(() => result.current.toggle());
  expect(result.current.enabled).toBe(false);
  expect(fake.cancelCount).toBeGreaterThan(cancelsBefore);
});

test("unmounting cancels any in-progress speech", () => {
  const { result, unmount } = renderHook(() => useNarrationSpeech());
  act(() => result.current.toggle());
  act(() => result.current.speak("hello"));
  const cancelsBefore = fake.cancelCount;

  unmount();
  expect(fake.cancelCount).toBeGreaterThan(cancelsBefore);
});

test("reports unsupported when the browser has no speechSynthesis", () => {
  vi.unstubAllGlobals(); // jsdom has no speechSynthesis by default — this is the un-stubbed state

  const { result } = renderHook(() => useNarrationSpeech());
  expect(result.current.supported).toBe(false);

  act(() => result.current.toggle());
  act(() => result.current.speak("hello")); // must not throw
  expect(result.current.enabled).toBe(true); // toggle itself still works, just silently
});
