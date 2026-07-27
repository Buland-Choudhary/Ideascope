import type { Beat, Duration, LessonUsage, ModelOption, Outline } from "../types/lesson";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface GenerateLessonRequest {
  topic: string;
  duration?: Duration;
  /** Optional per-lesson model override (docs/PLAN.md §14) — omit to use the
   * server's configured defaults. */
  model?: string;
}

async function parseErrorDetail(response: Response): Promise<string> {
  let detail = `Request failed (${response.status})`;
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") detail = body.detail;
  } catch {
    // keep the default detail
  }
  return detail;
}

/**
 * POST /api/lessons (docs/PLAN.md §5.1): kicks off plan + per-beat generation
 * in the background and returns immediately with the lesson id. Call
 * `streamLesson` with the returned id to receive the outline and each beat as
 * they're generated and validated.
 */
export async function createLesson(req: GenerateLessonRequest): Promise<string> {
  const response = await fetch(`${API_BASE_URL}/api/lessons`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      topic: req.topic,
      duration: req.duration ?? "medium",
      model: req.model,
    }),
  });
  if (!response.ok) throw new Error(await parseErrorDetail(response));
  const body = (await response.json()) as { lessonId: string };
  return body.lessonId;
}

/** GET /api/models: the models a learner can pick for a lesson, with the
 * $/MTok pricing used to estimate cost (docs/PLAN.md §14). */
export async function fetchModels(): Promise<ModelOption[]> {
  const response = await fetch(`${API_BASE_URL}/api/models`);
  if (!response.ok) throw new Error(await parseErrorDetail(response));
  return (await response.json()) as ModelOption[];
}

export interface LessonStreamHandlers {
  onOutline: (outline: Outline) => void;
  onBeat: (beat: Beat) => void;
  onBeatFailed?: (index: number, error: string) => void;
  onComplete: (usage: LessonUsage | null) => void;
  onFailed: (error: string) => void;
}

/**
 * Subscribes to GET /api/lessons/{id}/stream (SSE, docs/PLAN.md §5.1).
 * Returns an unsubscribe function — call it on unmount. `lesson_complete` and
 * `lesson_failed` are terminal: the handlers close the connection themselves
 * rather than relying on `EventSource`'s default auto-reconnect, which would
 * otherwise keep retrying against a stream that's already finished.
 */
export function streamLesson(lessonId: string, handlers: LessonStreamHandlers): () => void {
  const source = new EventSource(`${API_BASE_URL}/api/lessons/${lessonId}/stream`);

  source.addEventListener("outline_ready", (e) => {
    const data = JSON.parse((e as MessageEvent).data) as { outline: Outline };
    handlers.onOutline(data.outline);
  });
  source.addEventListener("beat_ready", (e) => {
    const data = JSON.parse((e as MessageEvent).data) as { beat: Beat };
    handlers.onBeat(data.beat);
  });
  source.addEventListener("beat_failed", (e) => {
    const data = JSON.parse((e as MessageEvent).data) as { index: number; error: string };
    handlers.onBeatFailed?.(data.index, data.error);
  });
  source.addEventListener("lesson_complete", (e) => {
    // `usage` is only present once at least one real Anthropic call has been
    // made (docs/PLAN.md's cost-transparency note) — absent in mock mode.
    const data = JSON.parse((e as MessageEvent).data) as { usage?: LessonUsage };
    handlers.onComplete(data.usage ?? null);
    source.close();
  });
  source.addEventListener("lesson_failed", (e) => {
    const data = JSON.parse((e as MessageEvent).data) as { error: string };
    handlers.onFailed(data.error);
    source.close();
  });

  return () => source.close();
}
