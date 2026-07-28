"""The lesson spec — the structured JSON contract for a generated lesson.

Mirrors docs/PLAN.md §3. The frontend keeps a hand-written TypeScript mirror of
these models in ``frontend/src/types/lesson.ts`` (kept in sync by hand for MVP,
per §3). JSON is emitted in ``camelCase`` (via the alias generator) so the wire
format matches the TypeScript types and the §3 spec; Python code uses
``snake_case`` field names.
"""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Base model: snake_case in Python, camelCase on the wire."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# --- Enums -----------------------------------------------------------------


class Duration(StrEnum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class Difficulty(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class Tone(StrEnum):
    PLAYFUL = "playful"
    FORMAL = "formal"
    NEUTRAL = "neutral"


class Engine(StrEnum):
    """MVP engine set (docs/PLAN.md §1). ``motion``/``sandbox`` are Phase 2."""

    CANVAS = "canvas"
    SVG = "svg"


class Primitive(StrEnum):
    """The vetted animation primitive vocabulary (docs/PLAN.md §4)."""

    TIMELINE = "timeline"
    PLOT = "plot"
    GEOMETRIC_TRANSFORM = "geometric_transform"
    PROCESS_FLOW = "process_flow"
    COMPARISON = "comparison"
    PART_TO_WHOLE = "part_to_whole"
    SIMULATION = "simulation"


class ManipulableType(StrEnum):
    SLIDER = "slider"
    STEPPER = "stepper"
    TOGGLE = "toggle"
    SELECT = "select"


class BeatStatus(StrEnum):
    PENDING = "pending"
    GENERATING = "generating"
    VALIDATING = "validating"
    READY = "ready"
    FAILED = "failed"
    DEGRADED = "degraded"


# --- Duration → target beat band (docs/PLAN.md D11) ------------------------

BEAT_BANDS: dict[Duration, tuple[int, int]] = {
    Duration.SHORT: (3, 5),
    Duration.MEDIUM: (6, 9),
    Duration.LONG: (10, 14),
}


# --- Models ----------------------------------------------------------------


class LessonParams(CamelModel):
    duration: Duration = Duration.MEDIUM
    difficulty: Difficulty | None = None
    prior_knowledge: str | None = None
    tone: Tone | None = None
    # Reserved; unused pre-Phase-2 (docs/PLAN.md §3).
    language: str | None = None


class Outline(CamelModel):
    title: str
    summary: str
    target_beat_count: int = Field(ge=1, le=20)


class Manipulable(CamelModel):
    id: str
    label: str
    type: ManipulableType
    # Key the scene code reads from its ``params`` object (docs/SCENE_CONTRACT.md).
    param: str
    default: bool | int | float | str
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: list[str] | None = None

    @model_validator(mode="after")
    def check_shape(self) -> Self:
        if self.type in (ManipulableType.SLIDER, ManipulableType.STEPPER):
            if self.min is None or self.max is None:
                raise ValueError(f"{self.type.value} requires 'min' and 'max'")
            if self.min >= self.max:
                raise ValueError("'min' must be less than 'max'")
            if not isinstance(self.default, (int, float)) or isinstance(self.default, bool):
                raise ValueError(f"{self.type.value} 'default' must be numeric")
        if self.type == ManipulableType.SELECT:
            if not self.options:
                raise ValueError("select requires a non-empty 'options' list")
            if self.default not in self.options:
                raise ValueError("select 'default' must be one of 'options'")
        if self.type == ManipulableType.TOGGLE and not isinstance(self.default, bool):
            raise ValueError("toggle 'default' must be a boolean")
        return self


class Palette(CamelModel):
    """A lesson-wide color scheme, chosen once by the plan stage to fit the
    topic's mood — every beat's generated scene reads these same values
    instead of picking its own, so a lesson reads as one deliberately
    designed thing rather than a patchwork of independently-styled beats.
    All fields are hex color strings (e.g. ``"#4f46e5"``).
    """

    background: str = Field(description="Page/canvas background — a soft near-white or near-black.")
    primary: str = Field(description="Main accent for the focal shape/series.")
    secondary: str = Field(description="Secondary accent for a second series or contrast.")
    text: str = Field(description="Body/label text — strong contrast against background.")
    muted: str = Field(description="Gridlines, tracks, and de-emphasized elements.")


class Narration(CamelModel):
    # Always present (docs/PLAN.md D5); TTS reads this client-side in MVP.
    text: str


class Scene(CamelModel):
    # Engine-specific ES-module source, written against docs/SCENE_CONTRACT.md.
    # (The v1 plan sketched an ``entryPoint`` field; dropped when the contract
    # was frozen — every scene uses a fixed ``export default``. See §3 note.)
    code: str


class BeatValidation(CamelModel):
    render_ok: bool
    auto_fix_attempts: int = 0
    critique_pass: bool | None = None
    critique_feedback: str | None = None


class Beat(CamelModel):
    id: str
    index: int = Field(ge=0)
    # Pedagogical goal; internal/debug, graded against by the vision critique.
    intent: str
    primitive: Primitive
    engine: Engine
    narration: Narration
    scene: Scene
    manipulables: list[Manipulable] = Field(default_factory=list)
    status: BeatStatus = BeatStatus.READY
    validation: BeatValidation | None = None

    @model_validator(mode="after")
    def check_manipulable_params_unique(self) -> Self:
        params = [m.param for m in self.manipulables]
        if len(params) != len(set(params)):
            raise ValueError("manipulable 'param' keys must be unique within a beat")
        return self


def _default_palette() -> Palette:
    # The house palette from before per-lesson palettes existed — kept as the
    # default so hand-authored fixtures (docs/PLAN.md's mock lessons, which
    # predate this field) still validate without editing their JSON.
    return Palette(
        background="#f8fafc",
        primary="#4f46e5",
        secondary="#f59e0b",
        text="#334155",
        muted="#cbd5e1",
    )


class Lesson(CamelModel):
    id: str
    topic: str
    params: LessonParams
    outline: Outline
    palette: Palette = Field(default_factory=_default_palette)
    beats: list[Beat]

    @model_validator(mode="after")
    def check_beat_indices(self) -> Self:
        # Uniqueness + in-range is deliberately checked instead of "list is
        # exactly 0..N-1 in order": concurrent generation (docs/PLAN.md §5.2)
        # can produce a partial, out-of-order snapshot while a lesson is still
        # generating — e.g. just beat 2, sitting alone while 0 and 1 are still
        # in flight — and that's a valid state to fetch (GET .../lessons/{id}
        # is explicitly for "SSE-reconnect and debugging" mid-generation), not
        # a bug. Once every beat has arrived (len == target_beat_count), these
        # two conditions force the indices to be exactly {0, ..., N-1} by the
        # pigeonhole principle, so a separate "complete lesson" contiguity
        # check would be redundant.
        indices = [b.index for b in self.beats]
        if len(indices) != len(set(indices)):
            raise ValueError(f"beat indices must be unique; got {indices}")
        if any(i >= self.outline.target_beat_count for i in indices):
            raise ValueError(
                f"beat indices must be contiguous from 0, within the lesson's "
                f"{self.outline.target_beat_count}-beat target; got {indices}"
            )
        return self


class UsageBreakdownEntry(CamelModel):
    """One (pipeline stage, model) bucket of the cost report below — e.g. "3
    beat calls on claude-sonnet-5 cost $0.02"."""

    stage: str
    model: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


class LessonUsage(CamelModel):
    """Real token usage and estimated dollar cost for one lesson's generation
    (docs/PLAN.md's cost-transparency note) — every actual Anthropic API call
    made while generating it, across the plan, beat, and (when applicable)
    code-review/auto-fix/critique stages. An estimate: pricing is a
    hand-maintained table (``app/observability/pricing.py``), not a live
    invoice lookup.
    """

    input_tokens: int
    output_tokens: int
    cost_usd: float
    breakdown: list[UsageBreakdownEntry] = Field(default_factory=list)
