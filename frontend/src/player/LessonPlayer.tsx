import { useEffect } from "react";

import { SceneRenderer } from "../engines/SceneRenderer";
import type { Lesson } from "../types/lesson";
import { ManipulableControls } from "./ManipulableControls";
import { usePlayerState } from "./usePlayerState";

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA" || target.isContentEditable;
}

interface LessonPlayerProps {
  lesson: Lesson;
  onExit?: () => void;
}

export function LessonPlayer({ lesson, onExit }: LessonPlayerProps) {
  const player = usePlayerState(lesson);

  // Keyboard advance (docs/PLAN.md §6.4). Space / → advance, ← back — but not
  // while the learner is interacting with a manipulable control.
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (isTypingTarget(e.target)) return;
      if (e.key === "ArrowRight" || e.key === " ") {
        e.preventDefault();
        player.next();
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        player.prev();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [player]);

  return (
    <section className="mx-auto flex max-w-3xl flex-col gap-4 p-6">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{lesson.outline.title}</h1>
          <p className="text-sm text-gray-500">
            Beat {player.index + 1} of {player.total}
          </p>
        </div>
        {onExit && (
          <button
            type="button"
            onClick={onExit}
            className="text-sm text-gray-500 underline hover:text-gray-800"
          >
            ← All lessons
          </button>
        )}
      </header>

      <SceneRenderer beat={player.beat} params={player.params} />

      <ManipulableControls
        manipulables={player.beat.manipulables}
        values={player.params}
        onChange={player.setParam}
      />

      <p className="text-lg leading-relaxed text-gray-800" role="status" aria-live="polite">
        {player.beat.narration.text}
      </p>

      <nav className="flex items-center justify-between border-t border-gray-100 pt-4">
        <button
          type="button"
          onClick={player.prev}
          disabled={!player.canPrev}
          className="rounded-md px-4 py-2 text-sm font-medium text-gray-700 enabled:hover:bg-gray-100 disabled:opacity-40"
        >
          ← Back
        </button>
        <span className="text-xs text-gray-400">Use ← → or Space to navigate</span>
        <button
          type="button"
          onClick={player.next}
          disabled={!player.canNext}
          className="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white enabled:hover:bg-gray-700 disabled:opacity-40"
        >
          {player.isLast ? "Done" : "Next →"}
        </button>
      </nav>
    </section>
  );
}
