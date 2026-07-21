import type { Lesson } from "../types/lesson";
import sineWave from "./sine_wave.json";
import waterCycle from "./water_cycle.json";

/**
 * Hand-authored fixture lessons, emitted by `backend/scripts/build_fixtures.py`
 * and re-validated there against the Pydantic schema. The `as Lesson` casts are
 * safe because the JSON is schema-validated at build time; TS can't narrow the
 * imported literal's string fields to the spec's unions on its own.
 */
export const FIXTURES: Lesson[] = [sineWave as Lesson, waterCycle as Lesson];

export function getFixture(id: string): Lesson | undefined {
  return FIXTURES.find((lesson) => lesson.id === id);
}
