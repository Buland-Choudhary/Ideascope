import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

import { getFixture } from "../fixtures";
import { FakeSpeechSynthesis, installFakeSpeechSynthesis } from "../test-support/fakeSpeechSynthesis";
import type { Lesson } from "../types/lesson";
import { LessonPlayer } from "./LessonPlayer";

const lesson = getFixture("fixture-sine-wave") as Lesson;

let fake: FakeSpeechSynthesis;

beforeEach(() => {
  fake = installFakeSpeechSynthesis(vi);
});

test("narration text is always visible, and speech is off by default", () => {
  render(<LessonPlayer lesson={lesson} />);
  expect(screen.getByText(lesson.beats[0].narration.text)).toBeInTheDocument();
  expect(fake.spoken).toEqual([]);
  expect(screen.getByRole("button", { name: /Narration off/ })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
});

test("toggling narration on speaks the current beat, off cancels it", async () => {
  const user = userEvent.setup();
  render(<LessonPlayer lesson={lesson} />);

  await user.click(screen.getByRole("button", { name: /Narration off/ }));
  expect(fake.spoken).toEqual([lesson.beats[0].narration.text]);
  expect(screen.getByRole("button", { name: /Narration on/ })).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  const cancelsBefore = fake.cancelCount;
  await user.click(screen.getByRole("button", { name: /Narration on/ }));
  expect(fake.cancelCount).toBeGreaterThan(cancelsBefore);
});

test("navigating to the next beat speaks its narration when enabled", async () => {
  const user = userEvent.setup();
  render(<LessonPlayer lesson={lesson} />);

  await user.click(screen.getByRole("button", { name: /Narration off/ })); // turn on
  fake.spoken = []; // clear the speak from mounting on beat 0

  await user.click(screen.getByRole("button", { name: /Next/ }));
  expect(fake.spoken).toEqual([lesson.beats[1].narration.text]);
});

test("narration text stays visible while speech is off", async () => {
  const user = userEvent.setup();
  render(<LessonPlayer lesson={lesson} />);

  await user.click(screen.getByRole("button", { name: /Next/ }));
  expect(screen.getByText(lesson.beats[1].narration.text)).toBeInTheDocument();
  expect(fake.spoken).toEqual([]); // never enabled
});

test("the toggle disables itself when speechSynthesis isn't supported", () => {
  vi.unstubAllGlobals();
  render(<LessonPlayer lesson={lesson} />);
  expect(screen.getByRole("button", { name: /Narration off/ })).toBeDisabled();
});

test("Done is enabled on the last beat and exits the lesson", async () => {
  const user = userEvent.setup();
  const onExit = vi.fn();
  render(<LessonPlayer lesson={lesson} onExit={onExit} />);

  for (let i = 0; i < lesson.beats.length - 1; i++) {
    await user.click(screen.getByRole("button", { name: /Next/ }));
  }

  const doneButton = screen.getByRole("button", { name: "Done" });
  expect(doneButton).toBeEnabled();
  await user.click(doneButton);
  expect(onExit).toHaveBeenCalledTimes(1);
});

test("Done is disabled on the last beat when there's no exit handler", async () => {
  const user = userEvent.setup();
  render(<LessonPlayer lesson={lesson} />);

  for (let i = 0; i < lesson.beats.length - 1; i++) {
    await user.click(screen.getByRole("button", { name: /Next/ }));
  }

  expect(screen.getByRole("button", { name: "Done" })).toBeDisabled();
});
