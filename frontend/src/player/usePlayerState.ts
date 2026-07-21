import { useCallback, useMemo, useState } from "react";

import type { Beat, Lesson, ParamValue } from "../types/lesson";

export function defaultParams(beat: Beat): Record<string, ParamValue> {
  return Object.fromEntries(beat.manipulables.map((m) => [m.param, m.default]));
}

export interface PlayerState {
  index: number;
  total: number;
  beat: Beat;
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
 */
export function usePlayerState(lesson: Lesson): PlayerState {
  const [index, setIndex] = useState(0);
  const beat = lesson.beats[index];
  const [params, setParams] = useState<Record<string, ParamValue>>(() => defaultParams(beat));

  const total = lesson.beats.length;

  const goto = useCallback(
    (nextIndex: number) => {
      const clamped = Math.max(0, Math.min(total - 1, nextIndex));
      setIndex(clamped);
      setParams(defaultParams(lesson.beats[clamped]));
    },
    [lesson, total],
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
