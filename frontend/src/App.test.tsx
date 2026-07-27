import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";
import { FIXTURES } from "./fixtures";
import { FakeEventSource } from "./test-support/fakeEventSource";

beforeEach(() => {
  FakeEventSource.reset();
  vi.stubGlobal("EventSource", FakeEventSource);
});

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

test("generating a lesson streams the outline then each beat as it arrives", async () => {
  const user = userEvent.setup();
  const lesson = FIXTURES[0];
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ lessonId: "lesson-abc" }), { status: 202 })),
  );

  render(<App />);
  await user.type(screen.getByLabelText(/What do you want to understand/), "anything");
  await user.click(screen.getByRole("button", { name: /Generate/ }));

  await waitFor(() => expect(screen.getByText(/Planning your lesson/)).toBeInTheDocument());

  const source = FakeEventSource.latest();
  expect(source.url).toContain("/api/lessons/lesson-abc/stream");

  act(() => source.emit("outline_ready", { outline: lesson.outline }));
  await waitFor(() => expect(screen.getByText(lesson.outline.title)).toBeInTheDocument());
  // Beat 1 hasn't arrived yet — the player shows the "preparing" placeholder.
  expect(screen.getByText(/Still preparing this part/)).toBeInTheDocument();

  act(() => source.emit("beat_ready", { index: 0, beat: lesson.beats[0] }));
  await waitFor(() =>
    expect(screen.getByText(lesson.beats[0].narration.text)).toBeInTheDocument(),
  );

  for (let i = 1; i < lesson.beats.length; i++) {
    act(() => source.emit("beat_ready", { index: i, beat: lesson.beats[i] }));
  }
  act(() => source.emit("lesson_complete", { lessonId: "lesson-abc" }));
  expect(source.closed).toBe(true);
});

test("model picker appears once fetched, and the chosen model is sent to POST /api/lessons", async () => {
  const user = userEvent.setup();
  const models = [
    { id: "claude-opus-4-8", inputPricePerMtok: 5, outputPricePerMtok: 25 },
    { id: "claude-haiku-4-5", inputPricePerMtok: 1, outputPricePerMtok: 5 },
  ];
  const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async (url) => {
    if (url.includes("/api/models")) return new Response(JSON.stringify(models), { status: 200 });
    return new Response(JSON.stringify({ lessonId: "lesson-abc" }), { status: 202 });
  });
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);
  await waitFor(() => expect(screen.getByLabelText("Model")).toBeInTheDocument());

  await user.type(screen.getByLabelText(/What do you want to understand/), "anything");
  await user.selectOptions(screen.getByLabelText("Model"), "claude-haiku-4-5");
  await user.click(screen.getByRole("button", { name: /Generate/ }));

  await waitFor(() => expect(screen.getByText(/Planning your lesson/)).toBeInTheDocument());
  const postCall = fetchMock.mock.calls.find(([url]) => url.includes("/api/lessons"));
  expect(postCall).toBeDefined();
  const [, init] = postCall!;
  const body = JSON.parse(init!.body as string);
  expect(body.model).toBe("claude-haiku-4-5");
});

test("omitting a model choice sends no override (server uses its default)", async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async (url) => {
    if (url.includes("/api/models")) return new Response(JSON.stringify([]), { status: 200 });
    return new Response(JSON.stringify({ lessonId: "lesson-abc" }), { status: 202 });
  });
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);
  await user.type(screen.getByLabelText(/What do you want to understand/), "anything");
  await user.click(screen.getByRole("button", { name: /Generate/ }));

  await waitFor(() => expect(screen.getByText(/Planning your lesson/)).toBeInTheDocument());
  const postCall = fetchMock.mock.calls.find(([url]) => url.includes("/api/lessons"));
  const [, init] = postCall!;
  const body = JSON.parse(init!.body as string);
  expect(body.model).toBeUndefined();
});

test("shows the token/cost badge once lesson_complete carries a usage report", async () => {
  const user = userEvent.setup();
  const lesson = FIXTURES[0];
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ lessonId: "lesson-abc" }), { status: 202 })),
  );

  render(<App />);
  await user.type(screen.getByLabelText(/What do you want to understand/), "anything");
  await user.click(screen.getByRole("button", { name: /Generate/ }));
  await waitFor(() => expect(screen.getByText(/Planning your lesson/)).toBeInTheDocument());

  const source = FakeEventSource.latest();
  act(() => source.emit("outline_ready", { outline: lesson.outline }));
  for (let i = 0; i < lesson.beats.length; i++) {
    act(() => source.emit("beat_ready", { index: i, beat: lesson.beats[i] }));
  }
  await waitFor(() =>
    expect(screen.getByText(lesson.beats[0].narration.text)).toBeInTheDocument(),
  );

  act(() =>
    source.emit("lesson_complete", {
      lessonId: "lesson-abc",
      usage: { inputTokens: 500, outputTokens: 300, costUsd: 0.0089, breakdown: [] },
    }),
  );

  await waitFor(() => expect(screen.getByText(/\$0\.0089/)).toBeInTheDocument());
});

test("rapid-fire clicks on Generate only submit once", async () => {
  const user = userEvent.setup();
  // The Landing form also fetches GET /api/models on mount (for the model
  // picker) — a URL-aware mock keeps that call out of the count this test
  // actually cares about: how many times POST /api/lessons fired.
  const fetchMock = vi.fn(async (url: string) => {
    if (url.includes("/api/models")) return new Response(JSON.stringify([]), { status: 200 });
    return new Response(JSON.stringify({ lessonId: "lesson-abc" }), { status: 202 });
  });
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);
  await user.type(screen.getByLabelText(/What do you want to understand/), "anything");

  // Several submit events in the same tick — a real fast double/triple-click
  // or Enter-mashing produces at least this. The button disabling via a state
  // update round-trip isn't fast enough to block these; a synchronous ref
  // guard in the submit handler is (see App.tsx's submittingRef).
  const button = screen.getByRole("button", { name: /Generate/ });
  act(() => {
    for (let i = 0; i < 5; i++) button.click();
  });

  await waitFor(() => expect(screen.getByText(/Planning your lesson/)).toBeInTheDocument());
  const postCalls = fetchMock.mock.calls.filter(([url]) => url.includes("/api/lessons"));
  expect(postCalls).toHaveLength(1);
});

test("shows an error when lesson creation is rejected", async () => {
  const user = userEvent.setup();
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(JSON.stringify({ detail: "No API key configured" }), { status: 503 }),
    ),
  );

  render(<App />);
  await user.type(screen.getByLabelText(/What do you want to understand/), "entropy");
  await user.click(screen.getByRole("button", { name: /Generate/ }));

  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("No API key configured"));
});

test("shows an error when the lesson fails mid-generation", async () => {
  const user = userEvent.setup();
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ lessonId: "lesson-xyz" }), { status: 202 })),
  );

  render(<App />);
  await user.type(screen.getByLabelText(/What do you want to understand/), "entropy");
  await user.click(screen.getByRole("button", { name: /Generate/ }));
  await waitFor(() => expect(FakeEventSource.instances.length).toBe(1));

  act(() => FakeEventSource.latest().emit("lesson_failed", { error: "No Anthropic API key" }));

  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("No Anthropic API key"));
});
