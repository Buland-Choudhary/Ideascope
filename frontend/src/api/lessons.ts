import type { Beat, Duration, Outline } from "../types/lesson";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface GenerateLessonRequest {
  topic: string;
  duration?: Duration;
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
    body: JSON.stringify({ topic: req.topic, duration: req.duration ?? "medium" }),
  });
  if (!response.ok) throw new Error(await parseErrorDetail(response));
  const body = (await response.json()) as { lessonId: string };
  return body.lessonId;
}

export interface LessonStreamHandlers {
  onOutline: (outline: Outline) => void;
  onBeat: (beat: Beat) => void;
  onBeatFailed?: (index: number, error: string) => void;
  onComplete: () => void;
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
  source.addEventListener("lesson_complete", () => {
    handlers.onComplete();
    source.close();
  });
  source.addEventListener("lesson_failed", (e) => {
    const data = JSON.parse((e as MessageEvent).data) as { error: string };
    handlers.onFailed(data.error);
    source.close();
  });

  return () => source.close();
}
