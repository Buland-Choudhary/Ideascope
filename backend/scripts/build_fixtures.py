"""Build the hand-authored fixture lessons into validated JSON.

The scene-code strings are authored here as readable Python triple-quoted
strings (avoids hand-escaping JS inside JSON), constructed through the Pydantic
models (so invalid content fails at build time), and written to
``app/fixtures/*.json`` — those JSON files are the runtime artifact consumed by
mock generation mode (docs/PLAN.md §1) and the Phase-2 static player.

Run:  cd backend && uv run python scripts/build_fixtures.py

The scene code targets the frozen contract in docs/SCENE_CONTRACT.md.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.models import (
    Beat,
    Engine,
    Lesson,
    LessonParams,
    Manipulable,
    ManipulableType,
    Narration,
    Outline,
    Primitive,
    Scene,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "app" / "fixtures"


# --- Sine wave (canvas / plot, with slider manipulables) -------------------

SINE_INTRO = """\
export default function createScene(ctx) {
  let firstFrame = true;
  return {
    setup(p) {
      p.frameRate(ctx.reducedMotion ? 1 : 30);
    },
    draw(p) {
      const w = ctx.width, h = ctx.height;
      p.background(255);
      p.stroke(220); p.strokeWeight(1);
      p.line(0, h / 2, w, h / 2);
      const amp = h * 0.3;
      const k = (2 * Math.PI * 1.5) / w;
      const phase = ctx.reducedMotion ? 0 : p.frameCount * 0.05;
      p.noFill(); p.stroke(30, 120, 220); p.strokeWeight(3);
      p.beginShape();
      for (let x = 0; x <= w; x += 2) {
        p.vertex(x, h / 2 - amp * Math.sin(k * x + phase));
      }
      p.endShape();
      if (firstFrame) { firstFrame = false; ctx.ready(); }
    },
  };
}
"""

SINE_AMPLITUDE = """\
export default function createScene(ctx) {
  let amplitude = Number(ctx.params.amplitude ?? 40);
  let firstFrame = true;
  return {
    setup(p) {
      p.frameRate(ctx.reducedMotion ? 1 : 30);
    },
    draw(p) {
      const w = ctx.width, h = ctx.height;
      p.background(255);
      p.stroke(220); p.strokeWeight(1);
      p.line(0, h / 2, w, h / 2);
      const k = (2 * Math.PI * 1.5) / w;
      const phase = ctx.reducedMotion ? 0 : p.frameCount * 0.05;
      p.noFill(); p.stroke(30, 120, 220); p.strokeWeight(3);
      p.beginShape();
      for (let x = 0; x <= w; x += 2) {
        p.vertex(x, h / 2 - amplitude * Math.sin(k * x + phase));
      }
      p.endShape();
      if (firstFrame) { firstFrame = false; ctx.ready(); }
    },
    onParamChange(param, value) {
      if (param === "amplitude") amplitude = Number(value);
    },
  };
}
"""

SINE_FREQUENCY = """\
export default function createScene(ctx) {
  let frequency = Number(ctx.params.frequency ?? 1.5);
  let firstFrame = true;
  return {
    setup(p) {
      p.frameRate(ctx.reducedMotion ? 1 : 30);
    },
    draw(p) {
      const w = ctx.width, h = ctx.height;
      p.background(255);
      p.stroke(220); p.strokeWeight(1);
      p.line(0, h / 2, w, h / 2);
      const amp = h * 0.3;
      const k = (2 * Math.PI * frequency) / w;
      const phase = ctx.reducedMotion ? 0 : p.frameCount * 0.05;
      p.noFill(); p.stroke(30, 120, 220); p.strokeWeight(3);
      p.beginShape();
      for (let x = 0; x <= w; x += 2) {
        p.vertex(x, h / 2 - amp * Math.sin(k * x + phase));
      }
      p.endShape();
      if (firstFrame) { firstFrame = false; ctx.ready(); }
    },
    onParamChange(param, value) {
      if (param === "frequency") frequency = Number(value);
    },
  };
}
"""

sine_wave = Lesson(
    id="fixture-sine-wave",
    topic="How a sine wave works",
    params=LessonParams(),  # duration defaults to medium; fixture is short
    outline=Outline(
        title="How a sine wave works",
        summary=(
            "A sine wave is smooth, repeating up-and-down motion. This lesson "
            "builds intuition for its two knobs: amplitude (height) and "
            "frequency (how many cycles fit across)."
        ),
        target_beat_count=3,
    ),
    beats=[
        Beat(
            id="sine-0",
            index=0,
            intent="Introduce a sine wave as smooth, repeating up-and-down motion.",
            primitive=Primitive.PLOT,
            engine=Engine.CANVAS,
            narration=Narration(
                text=(
                    "A sine wave is the smoothest way something can go up and down "
                    "and repeat forever. Watch it roll across the screen."
                )
            ),
            scene=Scene(code=SINE_INTRO),
        ),
        Beat(
            id="sine-1",
            index=1,
            intent="Show that amplitude controls the height of the wave.",
            primitive=Primitive.PLOT,
            engine=Engine.CANVAS,
            narration=Narration(
                text=(
                    "Amplitude is how tall the wave is. Drag the slider and the "
                    "peaks grow or shrink — but the timing stays the same."
                )
            ),
            scene=Scene(code=SINE_AMPLITUDE),
            manipulables=[
                Manipulable(
                    id="amp",
                    label="Amplitude",
                    type=ManipulableType.SLIDER,
                    param="amplitude",
                    default=40,
                    min=5,
                    max=120,
                    step=1,
                )
            ],
        ),
        Beat(
            id="sine-2",
            index=2,
            intent="Show that frequency controls how many cycles fit across the screen.",
            primitive=Primitive.PLOT,
            engine=Engine.CANVAS,
            narration=Narration(
                text=(
                    "Frequency is how many full cycles fit across. Turn it up and "
                    "the wave bunches together; turn it down and it stretches out."
                )
            ),
            scene=Scene(code=SINE_FREQUENCY),
            manipulables=[
                Manipulable(
                    id="freq",
                    label="Frequency",
                    type=ManipulableType.SLIDER,
                    param="frequency",
                    default=1.5,
                    min=0.5,
                    max=5,
                    step=0.1,
                )
            ],
        ),
    ],
)


# --- Water cycle (svg / process_flow, with stepper + toggle) ---------------

WATER_MAKE = """\
  const NS = "http://www.w3.org/2000/svg";
  const make = (tag, attrs) => {
    const el = document.createElementNS(NS, tag);
    for (const k in attrs) el.setAttribute(k, String(attrs[k]));
    return el;
  };
  const cx = ctx.width / 2, cy = ctx.height / 2;
  const r = Math.min(ctx.width, ctx.height) * 0.12;
  const pts = [
    [cx, cy - r * 2.2],
    [cx + r * 2.4, cy + r * 1.6],
    [cx - r * 2.4, cy + r * 1.6],
  ];
  const labels = ["Evaporation", "Condensation", "Precipitation"];
"""

WATER_INTRO = f"""\
export default function createScene(ctx) {{
  const svg = ctx.svg;
{WATER_MAKE}
  for (let i = 0; i < 3; i++) {{
    const a = pts[i], b = pts[(i + 1) % 3];
    svg.appendChild(make("line", {{ x1: a[0], y1: a[1], x2: b[0], y2: b[1], stroke: "#bbb", "stroke-width": 2 }}));
  }}
  for (let i = 0; i < 3; i++) {{
    svg.appendChild(make("circle", {{ cx: pts[i][0], cy: pts[i][1], r, fill: "#dbeafe", stroke: "#3b82f6", "stroke-width": 2 }}));
    const t = make("text", {{ x: pts[i][0], y: pts[i][1] + 4, "text-anchor": "middle", "font-size": 13, fill: "#1e3a8a" }});
    t.textContent = labels[i];
    svg.appendChild(t);
  }}
  ctx.ready();
  return {{}};
}}
"""

WATER_STAGE = f"""\
export default function createScene(ctx) {{
  const svg = ctx.svg;
{WATER_MAKE}
  for (let i = 0; i < 3; i++) {{
    const a = pts[i], b = pts[(i + 1) % 3];
    svg.appendChild(make("line", {{ x1: a[0], y1: a[1], x2: b[0], y2: b[1], stroke: "#bbb", "stroke-width": 2 }}));
  }}
  const circles = [];
  for (let i = 0; i < 3; i++) {{
    const c = make("circle", {{ cx: pts[i][0], cy: pts[i][1], r, fill: "#eee", stroke: "#3b82f6", "stroke-width": 2 }});
    circles.push(c);
    svg.appendChild(c);
    const t = make("text", {{ x: pts[i][0], y: pts[i][1] + 4, "text-anchor": "middle", "font-size": 13, fill: "#1e3a8a" }});
    t.textContent = labels[i];
    svg.appendChild(t);
  }}
  let stage = Number(ctx.params.stage ?? 0);
  const highlight = () => circles.forEach((c, i) => c.setAttribute("fill", i === stage ? "#3b82f6" : "#eee"));
  highlight();
  ctx.ready();
  return {{
    onParamChange(param, value) {{
      if (param === "stage") {{ stage = Number(value); highlight(); }}
    }},
  }};
}}
"""

WATER_LABELS = f"""\
export default function createScene(ctx) {{
  const svg = ctx.svg;
{WATER_MAKE}
  const texts = [];
  for (let i = 0; i < 3; i++) {{
    svg.appendChild(make("circle", {{ cx: pts[i][0], cy: pts[i][1], r, fill: "#dbeafe", stroke: "#3b82f6", "stroke-width": 2 }}));
    const t = make("text", {{ x: pts[i][0], y: pts[i][1] + 4, "text-anchor": "middle", "font-size": 13, fill: "#1e3a8a" }});
    t.textContent = labels[i];
    texts.push(t);
    svg.appendChild(t);
  }}
  let show = Boolean(ctx.params.showLabels ?? true);
  const apply = () => texts.forEach((t) => t.setAttribute("visibility", show ? "visible" : "hidden"));
  apply();
  ctx.ready();
  return {{
    onParamChange(param, value) {{
      if (param === "showLabels") {{ show = Boolean(value); apply(); }}
    }},
  }};
}}
"""

water_cycle = Lesson(
    id="fixture-water-cycle",
    topic="The water cycle",
    params=LessonParams(),
    outline=Outline(
        title="The water cycle",
        summary=(
            "Water moves in a never-ending loop: it rises as vapor, gathers into "
            "clouds, and falls back as rain. This lesson walks the three stages "
            "and lets you step through them."
        ),
        target_beat_count=3,
    ),
    beats=[
        Beat(
            id="water-0",
            index=0,
            intent="Show the three stages of the water cycle as a connected loop.",
            primitive=Primitive.PROCESS_FLOW,
            engine=Engine.SVG,
            narration=Narration(
                text=(
                    "The water cycle is a loop with three stages that feed into each "
                    "other: evaporation, condensation, and precipitation."
                )
            ),
            scene=Scene(code=WATER_INTRO),
        ),
        Beat(
            id="water-1",
            index=1,
            intent="Let the learner step through and highlight each stage in turn.",
            primitive=Primitive.PROCESS_FLOW,
            engine=Engine.SVG,
            narration=Narration(
                text=(
                    "Step through the cycle one stage at a time. Each highlighted "
                    "stage hands off to the next, then the loop begins again."
                )
            ),
            scene=Scene(code=WATER_STAGE),
            manipulables=[
                Manipulable(
                    id="stage",
                    label="Stage",
                    type=ManipulableType.STEPPER,
                    param="stage",
                    default=0,
                    min=0,
                    max=2,
                    step=1,
                )
            ],
        ),
        Beat(
            id="water-2",
            index=2,
            intent="Let the learner toggle the stage labels to self-test recall.",
            primitive=Primitive.PROCESS_FLOW,
            engine=Engine.SVG,
            narration=Narration(
                text=(
                    "Turn the labels off and see if you can name each stage from its "
                    "position in the loop, then turn them back on to check."
                )
            ),
            scene=Scene(code=WATER_LABELS),
            manipulables=[
                Manipulable(
                    id="labels",
                    label="Show labels",
                    type=ManipulableType.TOGGLE,
                    param="showLabels",
                    default=True,
                )
            ],
        ),
    ],
)


FIXTURES: dict[str, Lesson] = {
    "sine_wave": sine_wave,
    "water_cycle": water_cycle,
}


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    for name, lesson in FIXTURES.items():
        path = FIXTURES_DIR / f"{name}.json"
        payload = lesson.model_dump(by_alias=True, mode="json")
        path.write_text(json.dumps(payload, indent=2) + "\n")
        print(f"wrote {path.relative_to(FIXTURES_DIR.parent.parent)}")


if __name__ == "__main__":
    main()
