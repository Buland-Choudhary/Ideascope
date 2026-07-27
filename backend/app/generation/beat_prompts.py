"""Per-beat scene-code generation prompt (docs/PLAN.md §5.2, Phase 4).

Layout is cache-optimized like the plan prompt (§1), with one refinement: the
system prompt bundles the contract rules plus **one few-shot example for every
primitive** — not just the primitive of the beat being generated. That makes
the system prompt fully static across every beat call, for every lesson, for
the life of the process: a single ``cache_control`` breakpoint gives a cache
hit on essentially every beat call after the first one this process ever
makes, not just the 2nd..Nth beat of one lesson. The user message (which beat,
which primitive/engine to use *this time*) is the only thing that varies.

Every example here targets the frozen contract in docs/SCENE_CONTRACT.md.
"""

from app.generation.schema import BeatPlan
from app.models import Primitive

_CONTRACT_RULES = """\
You are the scene-code generator for Ideascope. You write ONE beat's animation \
as a small ES module targeting a fixed runtime contract. Follow it exactly:

- Your entire response is the module source. It must have exactly one \
`export default` — a factory function `(ctx) => controller` or \
`function createScene(ctx) { ... return controller; }`. No other exports.
- NO imports. NO `fetch`, `XMLHttpRequest`, `WebSocket`, `eval`, `new Function`, \
`document.cookie`, `localStorage`, `sessionStorage`, `window.parent`, \
`window.top`, or direct `postMessage`. The engine and DOM access you need are \
all provided through `ctx` — never reach outside it.
- `ctx` fields: `ctx.engine` ("canvas"|"svg"), `ctx.p5` (canvas engine: an \
instance-mode p5 object, canvas already created), `ctx.svg` (svg engine: an \
attached `<svg>` element), `ctx.gsap` (both engines: the GSAP animation \
library, for eased tweens and timelines — see below), `ctx.width`/`ctx.height` \
(numbers), `ctx.params` (current manipulable values keyed by their `param` \
name), `ctx.reducedMotion` (boolean — when true, render the settled final \
state, no continuous motion), `ctx.ready()` (call exactly once, when the first \
representative frame is drawn).
- The controller object you return may implement: `setup(p)` (canvas, once), \
`draw(p)` (canvas, every frame — draw here), `render()` (svg, optional), \
`onParamChange(param, value)` (both — react to a manipulable changing), \
`destroy()` (both, optional cleanup).
- Canvas scenes: call `ctx.ready()` at the end of the FIRST `draw` call (guard \
with a flag) so the screenshot lands on a real frame, not a blank one.
- SVG scenes: build your DOM, then call `ctx.ready()` once, at the end of setup.
- Read manipulable values from `ctx.params[paramName]`; update your local state \
in `onParamChange` — never read DOM input elements directly (there are none).
- **`ctx.gsap`** (full GSAP 3 API — `gsap.to()`, `.from()`, `.timeline()`, eases \
like `"power2.out"`, `"elastic.out(1, 0.4)"`, `"back.out"`, etc.) is the \
preferred way to animate a transition — a manipulable change, a value settling \
into place, a sequence of steps appearing — instead of hand-rolling easing math. \
For an SVG scene, tween a plain JS object and write the eased value onto DOM \
attributes/CSS in `onUpdate` (SVG attributes aren't directly tweenable by name \
without a plugin). For a canvas scene, tween a plain JS object and read the \
eased value in `draw`. When `ctx.reducedMotion` is true, skip `ctx.gsap` tweens \
entirely and set the end value directly — don't animate into the settled state.
- Keep it visually clear at a glance: generous spacing, a small readable \
palette, no clutter. Correctness of the depiction matters more than polish.

Below is one worked example per animation primitive. Match the shown patterns \
(ctx usage, ready() timing, onParamChange) but invent the actual visual \
content for whatever topic and intent you're asked to render — never reuse an \
example's specific subject matter unless it happens to match."""

_FEWSHOTS: dict[Primitive, str] = {
    Primitive.PLOT: """\
### Example — primitive: plot (canvas)
Intent: "Show that amplitude controls the height of a wave."
```js
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
```""",
    Primitive.PROCESS_FLOW: """\
### Example — primitive: process_flow (svg)
Intent: "Let the learner step through a 3-stage cycle and see the current stage highlighted."
```js
export default function createScene(ctx) {
  const NS = "http://www.w3.org/2000/svg";
  const make = (tag, attrs) => {
    const el = document.createElementNS(NS, tag);
    for (const k in attrs) el.setAttribute(k, String(attrs[k]));
    return el;
  };
  const cx = ctx.width / 2, cy = ctx.height / 2;
  const r = Math.min(ctx.width, ctx.height) * 0.12;
  const pts = [[cx, cy - r * 2.2], [cx + r * 2.4, cy + r * 1.6], [cx - r * 2.4, cy + r * 1.6]];
  const labels = ["Stage A", "Stage B", "Stage C"];
  for (let i = 0; i < 3; i++) {
    const a = pts[i], b = pts[(i + 1) % 3];
    ctx.svg.appendChild(make("line", { x1: a[0], y1: a[1], x2: b[0], y2: b[1], stroke: "#bbb", "stroke-width": 2 }));
  }
  const circles = [];
  for (let i = 0; i < 3; i++) {
    const c = make("circle", { cx: pts[i][0], cy: pts[i][1], r, fill: "#eee", stroke: "#3b82f6", "stroke-width": 2 });
    circles.push(c);
    ctx.svg.appendChild(c);
    const t = make("text", { x: pts[i][0], y: pts[i][1] + 4, "text-anchor": "middle", "font-size": 13, fill: "#1e3a8a" });
    t.textContent = labels[i];
    ctx.svg.appendChild(t);
  }
  let stage = Number(ctx.params.stage ?? 0);
  const scale = circles.map(() => ({ v: 1 }));
  const setScale = (i, v) => circles[i].setAttribute("r", String(r * v));
  const highlight = () => {
    circles.forEach((c, i) => {
      c.setAttribute("fill", i === stage ? "#3b82f6" : "#eee");
      const target = i === stage ? 1.25 : 1;
      if (ctx.reducedMotion) { setScale(i, target); return; }
      ctx.gsap.to(scale[i], {
        v: target,
        duration: 0.35,
        ease: "back.out(2)",
        onUpdate: () => setScale(i, scale[i].v),
      });
    });
  };
  highlight();
  ctx.ready();
  return {
    onParamChange(param, value) {
      if (param === "stage") { stage = Number(value); highlight(); }
    },
  };
}
```""",
    Primitive.TIMELINE: """\
### Example — primitive: timeline (svg)
Intent: "Show three events in order along a horizontal line."
```js
export default function createScene(ctx) {
  const NS = "http://www.w3.org/2000/svg";
  const make = (tag, attrs) => {
    const el = document.createElementNS(NS, tag);
    for (const k in attrs) el.setAttribute(k, String(attrs[k]));
    return el;
  };
  const y = ctx.height / 2;
  const margin = ctx.width * 0.12;
  ctx.svg.appendChild(make("line", { x1: margin, y1: y, x2: ctx.width - margin, y2: y, stroke: "#bbb", "stroke-width": 2 }));
  const events = ["First", "Second", "Third"];
  events.forEach((label, i) => {
    const x = margin + (i / (events.length - 1)) * (ctx.width - 2 * margin);
    ctx.svg.appendChild(make("circle", { cx: x, cy: y, r: 10, fill: "#3b82f6" }));
    const t = make("text", { x, y: y - 24, "text-anchor": "middle", "font-size": 13, fill: "#1e293b" });
    t.textContent = label;
    ctx.svg.appendChild(t);
  });
  ctx.ready();
  return {};
}
```""",
    Primitive.GEOMETRIC_TRANSFORM: """\
### Example — primitive: geometric_transform (canvas)
Intent: "Show how rotating an angle sweeps a point around a circle."
```js
export default function createScene(ctx) {
  let angleDeg = Number(ctx.params.angle ?? 45);
  let firstFrame = true;
  return {
    setup(p) {
      p.frameRate(ctx.reducedMotion ? 1 : 30);
      p.angleMode(p.DEGREES);
    },
    draw(p) {
      const cx = ctx.width / 2, cy = ctx.height / 2;
      const r = Math.min(ctx.width, ctx.height) * 0.35;
      p.background(255);
      p.stroke(220); p.noFill();
      p.circle(cx, cy, r * 2);
      const x = cx + r * p.cos(-angleDeg);
      const y = cy + r * p.sin(-angleDeg);
      p.stroke(30, 120, 220); p.strokeWeight(2);
      p.line(cx, cy, x, y);
      p.noStroke(); p.fill(30, 120, 220);
      p.circle(x, y, 12);
      if (firstFrame) { firstFrame = false; ctx.ready(); }
    },
    onParamChange(param, value) {
      if (param === "angle") angleDeg = Number(value);
    },
  };
}
```""",
    Primitive.COMPARISON: """\
### Example — primitive: comparison (svg)
Intent: "Compare two quantities side by side as bars."
```js
export default function createScene(ctx) {
  const NS = "http://www.w3.org/2000/svg";
  const make = (tag, attrs) => {
    const el = document.createElementNS(NS, tag);
    for (const k in attrs) el.setAttribute(k, String(attrs[k]));
    return el;
  };
  const baseY = ctx.height * 0.85;
  const maxH = ctx.height * 0.6;
  const barA = make("rect", { x: ctx.width * 0.3, width: 60, fill: "#3b82f6" });
  const barB = make("rect", { x: ctx.width * 0.6, width: 60, fill: "#f59e0b" });
  ctx.svg.appendChild(barA);
  ctx.svg.appendChild(barB);
  const setHeight = (rect, value) => {
    const h = maxH * Math.min(1, Math.max(0, value / 100));
    rect.setAttribute("height", h);
    rect.setAttribute("y", baseY - h);
  };
  let a = Number(ctx.params.valueA ?? 50), b = Number(ctx.params.valueB ?? 50);
  setHeight(barA, a); setHeight(barB, b);
  ctx.ready();
  return {
    onParamChange(param, value) {
      if (param === "valueA") { a = Number(value); setHeight(barA, a); }
      if (param === "valueB") { b = Number(value); setHeight(barB, b); }
    },
  };
}
```""",
    Primitive.PART_TO_WHOLE: """\
### Example — primitive: part_to_whole (svg)
Intent: "Show how a whole splits into two proportional parts."
```js
export default function createScene(ctx) {
  const NS = "http://www.w3.org/2000/svg";
  const make = (tag, attrs) => {
    const el = document.createElementNS(NS, tag);
    for (const k in attrs) el.setAttribute(k, String(attrs[k]));
    return el;
  };
  const barY = ctx.height / 2 - 20, barW = ctx.width * 0.7, barX = (ctx.width - barW) / 2;
  const partA = make("rect", { x: barX, y: barY, height: 40, fill: "#3b82f6" });
  const partB = make("rect", { y: barY, height: 40, fill: "#e5e7eb" });
  ctx.svg.appendChild(partB);
  ctx.svg.appendChild(partA);
  const update = (pct) => {
    const wA = barW * Math.min(1, Math.max(0, pct / 100));
    partA.setAttribute("width", wA);
    partB.setAttribute("x", barX + wA);
    partB.setAttribute("width", barW - wA);
  };
  let pct = Number(ctx.params.share ?? 50);
  update(pct);
  ctx.ready();
  return {
    onParamChange(param, value) {
      if (param === "share") { pct = Number(value); update(pct); }
    },
  };
}
```""",
    Primitive.SIMULATION: """\
### Example — primitive: simulation (canvas)
Intent: "Show a pendulum swinging, with length as a manipulable."
```js
export default function createScene(ctx) {
  let length = Number(ctx.params.length ?? 120);
  let t = 0;
  let firstFrame = true;
  return {
    setup(p) {
      p.frameRate(ctx.reducedMotion ? 1 : 30);
    },
    draw(p) {
      const pivotX = ctx.width / 2, pivotY = ctx.height * 0.15;
      p.background(255);
      const angle = ctx.reducedMotion ? 0 : Math.sin(t) * 0.6;
      if (!ctx.reducedMotion) t += 0.05;
      const bobX = pivotX + length * Math.sin(angle);
      const bobY = pivotY + length * Math.cos(angle);
      p.stroke(150); p.strokeWeight(2);
      p.line(pivotX, pivotY, bobX, bobY);
      p.noStroke(); p.fill(30, 120, 220);
      p.circle(bobX, bobY, 24);
      p.fill(80); p.circle(pivotX, pivotY, 6);
      if (firstFrame) { firstFrame = false; ctx.ready(); }
    },
    onParamChange(param, value) {
      if (param === "length") length = Number(value);
    },
  };
}
```""",
}

BEAT_SYSTEM_PROMPT = _CONTRACT_RULES + "\n\n" + "\n\n".join(_FEWSHOTS.values())


def build_beat_user_message(beat: BeatPlan) -> str:
    """The volatile, per-beat half of the prompt (kept after the cache break)."""
    lines = [
        f"Primitive: {beat.primitive.value}",
        f"Engine: {beat.engine.value}",
        f"Intent: {beat.intent}",
        f"Narration the learner will read alongside this beat: {beat.narration}",
    ]
    if beat.manipulables:
        lines.append("Manipulables (read these from ctx.params):")
        for m in beat.manipulables:
            spec = f"  - {m.param} ({m.type.value})"
            if m.min is not None and m.max is not None:
                spec += f", range {m.min}-{m.max}, default {m.default}"
            elif m.options:
                spec += f", options {m.options}, default {m.default!r}"
            else:
                spec += f", default {m.default!r}"
            lines.append(spec)
    lines.append(
        f"\nWrite the {beat.engine.value}-engine scene code for this beat now. "
        "Respond with the module source only."
    )
    return "\n".join(lines)
