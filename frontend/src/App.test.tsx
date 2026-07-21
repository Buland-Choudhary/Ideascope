import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "./App";
import { FIXTURES } from "./fixtures";

afterEach(() => {
  vi.restoreAllMocks();
});

test("shows the topic form and example lessons", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: "Ideascope" })).toBeInTheDocument();
  expect(screen.getByLabelText(/What do you want to understand/)).toBeInTheDocument();
  for (const lesson of FIXTURES) {
    expect(screen.getByText(lesson.outline.title)).toBeInTheDocument();
  }
});

test("opens an example lesson in the player and returns to the landing", async () => {
  const user = userEvent.setup();
  render(<App />);

  const first = FIXTURES[0];
  await user.click(screen.getByText(first.outline.title));

  expect(screen.getByText(/Beat 1 of/)).toBeInTheDocument();
  expect(screen.getByText(first.beats[0].narration.text)).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: /All lessons/ }));
  expect(screen.getByRole("heading", { name: "Or try an example", level: 2 })).toBeInTheDocument();
});

test("generating a lesson plays the returned lesson", async () => {
  const user = userEvent.setup();
  const lesson = FIXTURES[0];
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(lesson), { status: 200 })),
  );

  render(<App />);
  await user.type(screen.getByLabelText(/What do you want to understand/), "anything");
  await user.click(screen.getByRole("button", { name: /Generate/ }));

  await waitFor(() => expect(screen.getByText(/Beat 1 of/)).toBeInTheDocument());
});

test("shows an error when generation fails", async () => {
  const user = userEvent.setup();
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ detail: "No API key configured" }), { status: 503 })),
  );

  render(<App />);
  await user.type(screen.getByLabelText(/What do you want to understand/), "entropy");
  await user.click(screen.getByRole("button", { name: /Generate/ }));

  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("No API key configured"));
});
