import { useEffect, useRef, useState } from "react";

import { createLesson, streamLesson } from "./api/lessons";
import { FIXTURES } from "./fixtures";
import { LessonPlayer } from "./player/LessonPlayer";
import type { Duration, GenerationStatus, Lesson, PlayableLesson } from "./types/lesson";

/**
 * Just-in-time generation shell (docs/PLAN.md §5.1, Phase 6): the topic form
 * kicks off backend generation and gets a lesson id back immediately, then
 * subscribes to the SSE stream for the outline and each beat as they're
 * generated and validated — the player renders beat 1 as soon as it arrives
 * rather than waiting for the whole lesson (mock mode replays a complete
 * fixture through the same event sequence, so this is one code path either
 * way). The fixture picker below still opens a fixture directly, with no
 * network round trip, since it's already a complete lesson.
 */
export function App() {
  const [fixture, setFixture] = useState<Lesson | null>(null);
  const [lessonId, setLessonId] = useState<string | null>(null);
  const live = useLiveLesson(lessonId);

  function reset() {
    setFixture(null);
    setLessonId(null);
  }

  if (fixture) {
    return <LessonPlayer lesson={fixture} onExit={reset} />;
  }

  if (lessonId) {
    if (live.lesson) {
      return (
        <LessonPlayer lesson={live.lesson} generationStatus={live.status} onExit={reset} />
      );
    }
    if (live.status === "failed") {
      return <GenerationFailed error={live.error} onBack={reset} />;
    }
    return <PreparingOutline onCancel={reset} />;
  }

  return <Landing onFixture={setFixture} onLessonId={setLessonId} />;
}

interface LiveLessonState {
  lesson: PlayableLesson | null;
  status: GenerationStatus;
  error: string | null;
}

/** Subscribes to the SSE stream for `lessonId`, building up a PlayableLesson. */
function useLiveLesson(lessonId: string | null): LiveLessonState {
  const [state, setState] = useState<LiveLessonState>({
    lesson: null,
    status: "generating",
    error: null,
  });

  useEffect(() => {
    if (!lessonId) return;
    setState({ lesson: null, status: "generating", error: null });

    return streamLesson(lessonId, {
      onOutline: (outline) => {
        setState((prev) => ({
          ...prev,
          lesson: { id: lessonId, outline, beats: prev.lesson?.beats ?? [] },
        }));
      },
      onBeat: (beat) => {
        setState((prev) => {
          if (!prev.lesson) return prev;
          const beats = [...prev.lesson.beats];
          beats[beat.index] = beat;
          return { ...prev, lesson: { ...prev.lesson, beats } };
        });
      },
      onComplete: () => setState((prev) => ({ ...prev, status: "complete" })),
      onFailed: (error) => setState((prev) => ({ ...prev, status: "failed", error })),
    });
  }, [lessonId]);

  return state;
}

function PreparingOutline({ onCancel }: { onCancel: () => void }) {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center gap-4 p-8 text-center">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-gray-300 border-t-gray-600" />
      <p className="text-gray-600" role="status" aria-live="polite">
        Planning your lesson…
      </p>
      <button type="button" onClick={onCancel} className="text-sm text-gray-500 underline">
        Cancel
      </button>
    </main>
  );
}

function GenerationFailed({ error, onBack }: { error: string | null; onBack: () => void }) {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center gap-4 p-8 text-center">
      <p className="text-red-600" role="alert">
        {error ?? "Something went wrong generating this lesson."}
      </p>
      <button type="button" onClick={onBack} className="text-sm text-gray-500 underline">
        ← Try again
      </button>
    </main>
  );
}

function Landing({
  onFixture,
  onLessonId,
}: {
  onFixture: (lesson: Lesson) => void;
  onLessonId: (lessonId: string) => void;
}) {
  const [topic, setTopic] = useState("");
  const [duration, setDuration] = useState<Duration>("medium");
  const [status, setStatus] = useState<"idle" | "generating" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  // A ref guard, not just the disabled attribute: several submit events fired
  // in the same tick (a fast double/triple-click, or Enter mashed on the
  // button) can all reach this handler before React re-renders the DOM with
  // the button disabled, since that round-trips through a state update.
  const submittingRef = useRef(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!topic.trim() || submittingRef.current) return;
    submittingRef.current = true;
    setStatus("generating");
    setError(null);
    try {
      const lessonId = await createLesson({ topic: topic.trim(), duration });
      onLessonId(lessonId);
    } catch (err) {
      setStatus("error");
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      submittingRef.current = false;
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-8 p-8">
      <header>
        <h1 className="text-4xl font-bold tracking-tight">Ideascope</h1>
        <p className="mt-1 text-lg text-gray-600">See any idea, one click at a time.</p>
      </header>

      <form onSubmit={onSubmit} className="flex flex-col gap-3">
        <label htmlFor="topic" className="text-sm font-medium text-gray-700">
          What do you want to understand?
        </label>
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            id="topic"
            type="text"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="e.g. how a sine wave works"
            maxLength={300}
            disabled={status === "generating"}
            className="min-w-0 flex-1 rounded-lg border border-gray-300 px-3 py-2 focus:border-gray-500 focus:outline-none focus:ring-2 focus:ring-gray-400"
          />
          <div className="flex gap-2">
            <select
              aria-label="Duration"
              value={duration}
              onChange={(e) => setDuration(e.target.value as Duration)}
              disabled={status === "generating"}
              className="rounded-lg border border-gray-300 px-2 py-2 text-sm"
            >
              <option value="short">Short</option>
              <option value="medium">Medium</option>
              <option value="long">Long</option>
            </select>
            <button
              type="submit"
              disabled={status === "generating" || !topic.trim()}
              className="flex-1 rounded-lg bg-gray-900 px-4 py-2 font-medium text-white enabled:hover:bg-gray-700 disabled:opacity-40 sm:flex-none"
            >
              {status === "generating" ? "Generating…" : "Generate"}
            </button>
          </div>
        </div>
        {status === "error" && error && (
          <p className="text-sm text-red-600" role="alert">
            {error}
          </p>
        )}
      </form>

      <div className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400">
          Or try an example
        </h2>
        {FIXTURES.map((fixture) => (
          <button
            key={fixture.id}
            type="button"
            onClick={() => onFixture(fixture)}
            className="rounded-lg border border-gray-200 p-4 text-left transition hover:border-gray-400 hover:bg-gray-50"
          >
            <span className="block font-medium text-gray-900">{fixture.outline.title}</span>
            <span className="mt-1 block text-sm text-gray-500">{fixture.outline.summary}</span>
          </button>
        ))}
      </div>
    </main>
  );
}
