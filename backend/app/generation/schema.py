"""Plan-stage output schema — what the plan call returns (docs/PLAN.md §5.2).

The plan stage produces the whole-lesson outline: per-beat intent, primitive,
engine, narration, and manipulables — but **no scene code** (that's the per-beat
stage, Phase 4). These are separate from the runtime ``Lesson`` models because
the plan is a distinct, smaller shape the LLM emits via structured outputs; the
service layer assembles a full ``Lesson`` from a ``LessonPlan``.
"""

from pydantic import BaseModel, Field

from app.models import Engine, Manipulable, Palette, Primitive


class BeatPlan(BaseModel):
    intent: str = Field(description="The pedagogical goal of this beat (internal, not shown).")
    narration: str = Field(description="Learner-facing narration text for this beat.")
    primitive: Primitive = Field(description="Which animation primitive best fits this beat.")
    engine: Engine = Field(
        description="'canvas' for plots/simulations, 'svg' for diagrams/timelines."
    )
    manipulables: list[Manipulable] = Field(
        default_factory=list,
        description="Optional interactive controls (slider/stepper/toggle/select).",
    )


class LessonPlan(BaseModel):
    title: str = Field(description="A concise lesson title.")
    summary: str = Field(description="A one- or two-sentence summary of the whole lesson.")
    palette: Palette = Field(
        description="One color scheme for the whole lesson, fit to the topic's mood."
    )
    beats: list[BeatPlan] = Field(description="The ordered beats that make up the lesson.")


class BeatCode(BaseModel):
    """Per-beat scene-generation output (docs/PLAN.md §5.2, Phase 4)."""

    code: str = Field(
        description=(
            "Complete ES module source for this beat's scene, written against "
            "the frozen scene contract (a single `export default` factory)."
        )
    )
