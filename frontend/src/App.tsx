import { useState } from "react";

import { FIXTURES, getFixture } from "./fixtures";
import { LessonPlayer } from "./player/LessonPlayer";

/**
 * Phase-2 shell: a picker over the hand-authored fixture lessons, plus the
 * lesson player. The real topic-input form and generation flow arrive in
 * Phase 6 (docs/PLAN.md §11); this proves the player + engine runtimes in
 * isolation against fixtures.
 */
export function App() {
  const [activeId, setActiveId] = useState<string | null>(null);
  const active = activeId ? getFixture(activeId) : undefined;

  if (active) {
    return <LessonPlayer lesson={active} onExit={() => setActiveId(null)} />;
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-6 p-8">
      <header>
        <h1 className="text-4xl font-bold tracking-tight">Ideascope</h1>
        <p className="mt-1 text-lg text-gray-600">See any idea, one click at a time.</p>
      </header>

      <div className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400">
          Example lessons
        </h2>
        {FIXTURES.map((lesson) => (
          <button
            key={lesson.id}
            type="button"
            onClick={() => setActiveId(lesson.id)}
            className="rounded-lg border border-gray-200 p-4 text-left transition hover:border-gray-400 hover:bg-gray-50"
          >
            <span className="block font-medium text-gray-900">{lesson.outline.title}</span>
            <span className="mt-1 block text-sm text-gray-500">{lesson.outline.summary}</span>
          </button>
        ))}
      </div>
    </main>
  );
}
