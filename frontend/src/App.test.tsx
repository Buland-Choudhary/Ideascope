import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";

import { App } from "./App";
import { FIXTURES } from "./fixtures";

test("lists the fixture lessons", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: "Ideascope" })).toBeInTheDocument();
  for (const lesson of FIXTURES) {
    expect(screen.getByText(lesson.outline.title)).toBeInTheDocument();
  }
});

test("opens a lesson in the player and can return to the list", async () => {
  const user = userEvent.setup();
  render(<App />);

  const first = FIXTURES[0];
  await user.click(screen.getByText(first.outline.title));

  // Player header shows beat position.
  expect(screen.getByText(/Beat 1 of/)).toBeInTheDocument();
  // Narration of the first beat is present.
  expect(screen.getByText(first.beats[0].narration.text)).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: /All lessons/ }));
  expect(
    screen.getByRole("heading", { name: "Example lessons", level: 2 }),
  ).toBeInTheDocument();
});
