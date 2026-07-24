import { useCallback, useMemo, useState } from "react";

import type { Beat, ParamValue, PlayableLesson } from "../types/lesson";

export function defaultParams(beat: Beat): Record<string, ParamValue> {
  return Object.fromEntries(beat.manipulables.map((m) => [m.param, m.default]));
}

export interface PlayerState {
  index: number;
  total: number;
  /** Undefined while this beat hasn't arrived yet (still generating, Phase 6). */
  beat: Beat | undefined;
  params: Record<string, ParamValue>;
  canPrev: boolean;
  canNext: boolean;
  isLast: boolean;
  next: () => void;
  prev: () => void;
  setParam: (param: string, value: ParamValue) => void;
}

/**
 * The click-to-advance state machine (docs/PLAN.md §6.3). A linear cursor over
 * the beats plus the current beat's manipulable values. Navigating resets the
 * params to the target beat's defaults (Phase 2 does not persist per-beat
 * manipulable state across navigation — an acceptable MVP simplification).
 *
 * `total` is the outline's declared beat count, not `beats.length` — while a
 * lesson is generating just-in-time (Phase 6), the learner can navigate past
 * the last beat that's arrived so far; `beat` is `undefined` until it shows
 * up, and the player renders a "still preparing" placeholder for that case.
 */
export function usePlayerState(lesson: PlayableLesson): PlayerState {
  const [index, setIndex] = useState(0);
  const total = lesson.outline.targetBeatCount;
  const beat = lesson.beats[index];
  const [params, setParams] = useState<Record<string, ParamValue>>(() =>
    beat ? defaultParams(beat) : {},
  );
  // Tracks whose defaults `params` currently holds, so a beat change — via
  // navigation, or a not-yet-arrived beat streaming in while the learner is
  // already sitting on that index — can be detected and reset synchronously,
  // during render (React's documented pattern for this exact case). Doing it
  // in an effect instead would paint one frame of the *previous* beat's
  // params against the *new* beat's manipulables first — e.g. a slider whose
  // param key doesn't exist in the stale values, rendering value={undefined}
  // (NaN in the DOM) for that frame.
  const [paramsOwner, setParamsOwner] = useState(beat?.id);
  if (paramsOwner !== beat?.id) {
    setParamsOwner(beat?.id);
    setParams(beat ? defaultParams(beat) : {});
  }

  const goto = useCallback(
    (nextIndex: number) => {
      setIndex(Math.max(0, Math.min(total - 1, nextIndex)));
    },
    [total],
  );

  const next = useCallback(() => goto(index + 1), [goto, index]);
  const prev = useCallback(() => goto(index - 1), [goto, index]);

  const setParam = useCallback((param: string, value: ParamValue) => {
    setParams((prevParams) => ({ ...prevParams, [param]: value }));
  }, []);

  return useMemo(
    () => ({
      index,
      total,
      beat,
      params,
      canPrev: index > 0,
      canNext: index < total - 1,
      isLast: index === total - 1,
      next,
      prev,
      setParam,
    }),
    [index, total, beat, params, next, prev, setParam],
  );
}
