import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "./App";

afterEach(() => {
  vi.restoreAllMocks();
});

test("renders the title and tagline", () => {
  vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
  render(<App />);
  expect(screen.getByRole("heading", { name: "Ideascope" })).toBeInTheDocument();
  expect(screen.getByText("See any idea, one click at a time.")).toBeInTheDocument();
});

test("shows backend version when the health check succeeds", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ version: "0.0.1" }), { status: 200 })),
  );
  render(<App />);
  await waitFor(() =>
    expect(screen.getByText("Backend online (v0.0.1)")).toBeInTheDocument(),
  );
});

test("shows an error state when the health check fails", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      throw new Error("network down");
    }),
  );
  render(<App />);
  await waitFor(() =>
    expect(screen.getByText("Backend unreachable")).toBeInTheDocument(),
  );
});
