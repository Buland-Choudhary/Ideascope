import { useCallback, useEffect, useMemo, useState } from "react";

export interface NarrationSpeech {
  /** Whether the learner has turned narration read-aloud on. */
  enabled: boolean;
  /** False if the browser has no `SpeechSynthesis` API — the toggle disables itself. */
  supported: boolean;
  toggle: () => void;
  /** Speaks `text` if enabled; a no-op otherwise. Cancels any speech in progress first. */
  speak: (text: string) => void;
  stop: () => void;
}

/**
 * Wraps the browser's native `SpeechSynthesis` API (docs/PLAN.md §1 — "free,
 * zero added latency/cost," the MVP's whole TTS story). Narration *text* is
 * always rendered regardless of this toggle (docs/PLAN.md §6.1); this only
 * controls whether it's also read aloud, and degrades silently — never
 * throwing — when the API isn't available.
 */
export function useNarrationSpeech(): NarrationSpeech {
  const [enabled, setEnabled] = useState(false);
  const supported = typeof window !== "undefined" && "speechSynthesis" in window;

  const stop = useCallback(() => {
    if (supported) window.speechSynthesis.cancel();
  }, [supported]);

  const speak = useCallback(
    (text: string) => {
      if (!supported || !enabled) return;
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
    },
    [supported, enabled],
  );

  const toggle = useCallback(() => {
    setEnabled((prev) => {
      const next = !prev;
      if (!next) stop();
      return next;
    });
  }, [stop]);

  // Never leave an utterance talking after the player using this hook unmounts.
  useEffect(() => stop, [stop]);

  return useMemo(
    () => ({ enabled, supported, toggle, speak, stop }),
    [enabled, supported, toggle, speak, stop],
  );
}
