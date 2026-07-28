/**
 * TypeScript mirror of the backend lesson spec.
 *
 * Hand-kept in sync with `backend/app/models/lesson.py` (docs/PLAN.md §3 accepts
 * manual mirroring for MVP). The wire format is camelCase — matching the JSON the
 * backend emits via its alias generator. Scene `code` strings target the frozen
 * contract in docs/SCENE_CONTRACT.md.
 */

export type Duration = "short" | "medium" | "long";
export type Difficulty = "beginner" | "intermediate" | "advanced";
export type Tone = "playful" | "formal" | "neutral";

/** MVP engine set (docs/PLAN.md §1); "motion" | "sandbox" arrive in Phase 2. */
export type Engine = "canvas" | "svg";

export type Primitive =
  | "timeline"
  | "plot"
  | "geometric_transform"
  | "process_flow"
  | "comparison"
  | "part_to_whole"
  | "simulation";

export type ManipulableType = "slider" | "stepper" | "toggle" | "select";

/** A live manipulable value flowing into a scene via `ctx.params`. */
export type ParamValue = number | string | boolean;

export type BeatStatus =
  | "pending"
  | "generating"
  | "validating"
  | "ready"
  | "failed"
  | "degraded";

export interface LessonParams {
  duration: Duration;
  difficulty?: Difficulty | null;
  priorKnowledge?: string | null;
  tone?: Tone | null;
  /** Reserved; unused pre-Phase-2. */
  language?: string | null;
}

export interface Outline {
  title: string;
  summary: string;
  targetBeatCount: number;
}

export interface Manipulable {
  id: string;
  label: string;
  type: ManipulableType;
  /** Key the scene reads from `ctx.params` (docs/SCENE_CONTRACT.md §3). */
  param: string;
  default: number | string | boolean;
  min?: number | null;
  max?: number | null;
  step?: number | null;
  options?: string[] | null;
}

/** A lesson-wide color scheme, chosen once by the plan stage to fit the
 * topic's mood (docs/SCENE_CONTRACT.md §2.2) — every beat's scene reads these
 * same values via `ctx.palette` instead of picking its own. All fields are
 * hex color strings (e.g. `"#4f46e5"`). */
export interface Palette {
  background: string;
  primary: string;
  secondary: string;
  text: string;
  muted: string;
}

/** The house palette from before per-lesson palettes existed — a fallback for
 * lessons that predate this field (e.g. hand-authored fixtures emitted before
 * it was added) so they keep rendering with their original, matching colors. */
export const DEFAULT_PALETTE: Palette = {
  background: "#f8fafc",
  primary: "#4f46e5",
  secondary: "#f59e0b",
  text: "#334155",
  muted: "#cbd5e1",
};

export interface Narration {
  text: string;
}

export interface Scene {
  code: string;
}

export interface BeatValidation {
  renderOk: boolean;
  autoFixAttempts: number;
  critiquePass?: boolean | null;
  critiqueFeedback?: string | null;
}

export interface Beat {
  id: string;
  index: number;
  intent: string;
  primitive: Primitive;
  engine: Engine;
  narration: Narration;
  scene: Scene;
  manipulables: Manipulable[];
  status: BeatStatus;
  validation?: BeatValidation | null;
}

export interface Lesson {
  id: string;
  topic: string;
  params: LessonParams;
  outline: Outline;
  palette: Palette;
  beats: Beat[];
}

/** Generation lifecycle for a just-in-time lesson (docs/PLAN.md §5.1, Phase 6). */
export type GenerationStatus = "generating" | "complete" | "failed";

/** A model a learner can pick for a lesson's generation, GET /api/models. */
export interface ModelOption {
  id: string;
  inputPricePerMtok: number;
  outputPricePerMtok: number;
}

/** One (pipeline stage, model) bucket of a lesson's token/cost report. */
export interface UsageBreakdownEntry {
  stage: string;
  model: string;
  calls: number;
  inputTokens: number;
  outputTokens: number;
  costUsd: number;
}

/** Real token usage and estimated dollar cost for one lesson's generation
 * (docs/PLAN.md's cost-transparency note) — present once at least one real
 * Anthropic call has happened; absent in mock mode. */
export interface LessonUsage {
  inputTokens: number;
  outputTokens: number;
  costUsd: number;
  breakdown: UsageBreakdownEntry[];
}

/**
 * What the player needs while a lesson is being generated just-in-time: the
 * outline (and its `targetBeatCount`) plus however many beats have arrived so
 * far — which may be fewer than `targetBeatCount` while `beats.length <
 * outline.targetBeatCount` and `status` is still `"generating"`.
 */
export type PlayableLesson = Pick<Lesson, "id" | "outline" | "palette" | "beats">;
