import { useState } from "react";

import { generateLesson } from "./api/lessons";
import { FIXTURES } from "./fixtures";
import { LessonPlayer } from "./player/LessonPlayer";
import type { Duration, Lesson } from "./types/lesson";

/**
 * Phase-3 shell: a topic form that generates a lesson via the backend (a
 * complete, playable fixture in mock mode), plus the fixture picker and the
 * lesson player. The just-in-time / streaming generation flow arrives in
 * Phase 6 (docs/PLAN.md §11).
 */
export function App() {
  const [lesson, setLesson] = useState<Lesson | null>(null);

  if (lesson) {
    return <LessonPlayer lesson={lesson} onExit={() => setLesson(null)} />;
  }

  return <Landing onLesson={setLesson} />;
}

function Landing({ onLesson }: { onLesson: (lesson: Lesson) => void }) {
  const [topic, setTopic] = useState("");
  const [duration, setDuration] = useState<Duration>("medium");
  const [status, setStatus] = useState<"idle" | "generating" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!topic.trim()) return;
    setStatus("generating");
    setError(null);
    try {
      const lesson = await generateLesson({ topic: topic.trim(), duration });
      onLesson(lesson);
    } catch (err) {
      setStatus("error");
      setError(err instanceof Error ? err.message : "Something went wrong");
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
        <div className="flex gap-2">
          <input
            id="topic"
            type="text"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="e.g. how a sine wave works"
            maxLength={300}
            disabled={status === "generating"}
            className="flex-1 rounded-lg border border-gray-300 px-3 py-2 focus:border-gray-500 focus:outline-none"
          />
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
            className="rounded-lg bg-gray-900 px-4 py-2 font-medium text-white enabled:hover:bg-gray-700 disabled:opacity-40"
          >
            {status === "generating" ? "Generating…" : "Generate"}
          </button>
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
            onClick={() => onLesson(fixture)}
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
