import { useEffect } from "react";

import { SceneRenderer } from "../engines/SceneRenderer";
import type { GenerationStatus, LessonUsage, PlayableLesson } from "../types/lesson";
import { ManipulableControls } from "./ManipulableControls";
import { useNarrationSpeech } from "./useNarrationSpeech";
import { usePlayerState } from "./usePlayerState";

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA" || target.isContentEditable;
}

interface LessonPlayerProps {
  lesson: PlayableLesson;
  /** Defaults to "complete" — fixture lessons are already fully generated. */
  generationStatus?: GenerationStatus;
  /** Real token usage/cost for this lesson's generation (docs/PLAN.md's cost-
   * transparency note) — absent for fixtures and mock-mode lessons, which
   * never made a real Anthropic call. */
  usage?: LessonUsage | null;
  onExit?: () => void;
}

export function LessonPlayer({
  lesson,
  generationStatus = "complete",
  usage,
  onExit,
}: LessonPlayerProps) {
  const player = usePlayerState(lesson);
  const narration = useNarrationSpeech();

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

  // Reads the current beat aloud when narration is on — on the beat changing
  // (navigation, or one streaming in) and when the learner toggles it on
  // (docs/PLAN.md §6.1: "toggle drives whether SpeechSynthesis.speak() fires
  // alongside" the always-visible narration text).
  useEffect(() => {
    if (player.beat) narration.speak(player.beat.narration.text);
  }, [player.beat, narration]);

  return (
    <section className="mx-auto flex max-w-3xl flex-col gap-4 p-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-baseline sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold tracking-tight break-words">{lesson.outline.title}</h1>
          <p className="text-sm text-gray-500">
            Beat {player.index + 1} of {player.total}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3 sm:gap-4">
          {generationStatus === "complete" && usage && <UsageBadge usage={usage} />}
          <button
            type="button"
            onClick={narration.toggle}
            disabled={!narration.supported}
            aria-pressed={narration.enabled}
            title={narration.supported ? undefined : "Narration isn't supported in this browser"}
            className="rounded-md border border-gray-200 px-3 py-1.5 text-sm text-gray-600 enabled:hover:bg-gray-100 disabled:opacity-40"
          >
            {narration.enabled ? "🔊 Narration on" : "🔇 Narration off"}
          </button>
          {onExit && (
            <button
              type="button"
              onClick={onExit}
              className="text-sm text-gray-500 underline hover:text-gray-800"
            >
              ← All lessons
            </button>
          )}
        </div>
      </header>

      {player.beat ? (
        <>
          <SceneRenderer beat={player.beat} params={player.params} palette={lesson.palette} />

          <ManipulableControls
            manipulables={player.beat.manipulables}
            values={player.params}
            onChange={player.setParam}
          />

          <p className="text-lg leading-relaxed text-gray-800" role="status" aria-live="polite">
            {player.beat.narration.text}
          </p>
        </>
      ) : (
        <PreparingBeat status={generationStatus} />
      )}

      <nav className="flex items-center justify-between border-t border-gray-100 pt-4">
        <button
          type="button"
          onClick={player.prev}
          disabled={!player.canPrev}
          className="rounded-md px-4 py-2 text-sm font-medium text-gray-700 enabled:hover:bg-gray-100 disabled:opacity-40"
        >
          ← Back
        </button>
        <span className="hidden text-xs text-gray-400 sm:inline">Use ← → or Space to navigate</span>
        <button
          type="button"
          onClick={player.isLast ? onExit : player.next}
          disabled={player.isLast ? !onExit : !player.canNext}
          className="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white enabled:hover:bg-gray-700 disabled:opacity-40"
        >
          {player.isLast ? "Done" : "Next →"}
        </button>
      </nav>
    </section>
  );
}

function formatCost(usd: number): string {
  // Beat-level costs are typically a fraction of a cent — 2 decimal places
  // would round most lessons to "$0.00", which reads as "this was free"
  // rather than "this cost basically nothing." 4 places keeps it honest.
  return `$${usd.toFixed(4)}`;
}

/**
 * Real token usage/cost for this lesson's generation (docs/PLAN.md's cost-
 * transparency note), shown once generation completes. The title tooltip
 * breaks it down per pipeline stage/model — plan, beat, and (when the
 * lightweight code review or full validation pipeline ran) review/critique
 * calls all cost real tokens, not just the beat calls a learner might assume.
 */
function UsageBadge({ usage }: { usage: LessonUsage }) {
  const totalTokens = usage.inputTokens + usage.outputTokens;
  const tooltip = usage.breakdown
    .map(
      (b) =>
        `${b.stage} (${b.model}): ${b.calls} call${b.calls === 1 ? "" : "s"}, ` +
        `${b.inputTokens.toLocaleString()} in / ${b.outputTokens.toLocaleString()} out, ` +
        formatCost(b.costUsd),
    )
    .join("\n");

  return (
    <span
      className="rounded-md border border-gray-200 px-3 py-1.5 text-sm text-gray-600"
      title={tooltip}
    >
      💰 {formatCost(usage.costUsd)} · {totalTokens.toLocaleString()} tokens
    </span>
  );
}

/**
 * Shown for a beat index the learner has reached before it's arrived
 * (docs/PLAN.md §6.1: "the format is self-paced, so slow generation degrades
 * to 'wait a beat,' never to a broken click"). Deliberately not blocking —
 * the nav buttons above stay usable so the learner can step back and re-read
 * while this beat finishes generating in the background.
 */
function PreparingBeat({ status }: { status: GenerationStatus }) {
  return (
    <div
      className="flex min-h-[16rem] flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-gray-300 bg-gray-50 text-gray-500"
      role="status"
      aria-live="polite"
    >
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-gray-300 border-t-gray-600" />
      <p className="text-sm">
        {status === "failed"
          ? "This part couldn't be generated."
          : "Still preparing this part — hang tight…"}
      </p>
    </div>
  );
}
