import type { Duration, Lesson } from "../types/lesson";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface GenerateLessonRequest {
  topic: string;
  duration?: Duration;
}

/**
 * Request a generated lesson (docs/PLAN.md §5.1). Phase 3 is a synchronous POST;
 * Phase 6 replaces this with the just-in-time SSE flow (return an id, then stream
 * beats). In mock mode the backend returns a complete, playable fixture.
 */
export async function generateLesson(req: GenerateLessonRequest): Promise<Lesson> {
  const response = await fetch(`${API_BASE_URL}/api/lessons`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic: req.topic, duration: req.duration ?? "medium" }),
  });
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // keep the default detail
    }
    throw new Error(detail);
  }
  return (await response.json()) as Lesson;
}
