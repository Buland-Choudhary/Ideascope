# Scene-code runtime contract (v1 — FROZEN)

**Status:** Frozen in Phase 1 (docs/PLAN.md §6.2, §11). Every few-shot example,
the validator, and the client renderer depend on this exact surface. Changing it
after Phase 4 means regenerating every few-shot, so changes require a version
bump (v2) and a deliberate migration — not an incidental edit.

This is the API that **LLM-generated scene code targets** and that the
hand-written engine runtime provides. Keeping it small is both a correctness
lever (less for the model to get wrong) and a security lever (less surface to
abuse — see docs/PLAN.md §7).

---

## 1. What a scene is

A scene is the value of `beat.scene.code` in the lesson spec: a string of
JavaScript, evaluated as an **ES module** inside the sandboxed `<iframe>`
(docs/PLAN.md §7). It must have a **default export** that is a factory function:

```js
export default function createScene(ctx) {
  // ...set up drawing using ctx...
  return controller; // a SceneController (see §4)
}
```

- **Default export only.** There is no `entryPoint` field — the runtime always
  calls the module's default export. A scene with no default export is a
  render failure.
- **No imports.** Scenes must not `import` anything (no network; the CSP blocks
  it anyway — §7). The engine (p5, KaTeX) is injected via `ctx`, never imported.
- **No global side effects** beyond drawing into the surface `ctx` provides.
  No `fetch`, `eval`, `document.cookie`, `window.parent`/`window.top`, timers
  that outlive `destroy()`, etc. (statically rejected before execution — §7).

---

## 2. The `ctx` object (runtime → scene)

`createScene(ctx)` receives a `SceneContext`:

| Field | Type | Notes |
|---|---|---|
| `ctx.engine` | `"canvas" \| "svg"` | Which surface is provided. |
| `ctx.p5` | p5 instance | **canvas engine only.** Instance-mode p5; the canvas is already created at `width × height` and attached. Draw with `ctx.p5.*` (also passed to `setup`/`draw` for convenience). |
| `ctx.svg` | `SVGSVGElement` | **svg engine only.** An `<svg>` element, sized and attached. Append namespaced children to it. |
| `ctx.gsap` | GSAP module | **both engines.** The full GSAP 3 API (`gsap.to()`, `.from()`, `.timeline()`, eases) for tweening a transition instead of hand-rolled easing math — see §2.1. |
| `ctx.width` | number | Stage width in CSS px. |
| `ctx.height` | number | Stage height in CSS px. |
| `ctx.params` | `Record<string, number \| string \| boolean>` | Current manipulable values, keyed by each manipulable's `param`. |
| `ctx.reducedMotion` | boolean | When true, render the final/settled state without continuous motion (docs/PLAN.md §6.4). |
| `ctx.ready` | `() => void` | Call **once** when the first representative frame is on screen (see §5). |

### 2.1 `ctx.gsap` — additive, non-breaking (added post-freeze)

Added without a contract version bump: it's a pure addition (a new optional
`ctx` field), doesn't change any existing field's meaning, and every prior
scene continues to work untouched. GSAP (~70 KB minified, MIT-equivalent free
license) is loaded once per session — like p5, via a dynamic `import()` so it
doesn't inflate the initial bundle (`frontend/src/engines/sceneRuntime.ts`,
`app/validation/runtime.py`) — and is available in **every** scene regardless
of engine, since it's a tweening/timeline library, not a rendering surface.

- **SVG**: SVG attributes aren't directly tweenable by name without a plugin,
  so tween a plain JS object and write the eased value onto the DOM in
  `onUpdate`: `gsap.to(state, { r: 40, duration: 0.3, onUpdate: () => el.setAttribute("r", state.r) })`.
- **Canvas**: same pattern — tween a plain JS object, read the eased value in
  `draw`.
- **`ctx.reducedMotion`**: skip `ctx.gsap` tweens entirely and set the end
  value directly; don't animate into the settled state.

**Note on `ctx.katex`:** an earlier draft of this contract and the beat-
generation prompt documented `ctx.katex` (math rendering) as available. It was
never actually implemented in either runtime — KaTeX needs its web fonts
available to render correctly, and the sandboxed iframe's CSP blocks all
network/font loading, so it would need every font file embedded as a `data:`
URI, which wasn't done. Any beat that reached for it would have crashed
(gracefully — the client-side sandboxed-iframe error handling catches it and
shows a "couldn't render this scene" fallback rather than a blank beat — but
still a beat that should have worked). Removed from the active prompt
(`app/generation/beat_prompts.py`) until it's implemented properly; not
currently part of the contract.

---

## 3. Manipulable values

`ctx.params[param]` holds the current value for each manipulable declared on the
beat, keyed by its `param` string. Types follow the manipulable type: `slider`/
`stepper` → number, `toggle` → boolean, `select` → string. When the learner
changes a control, the runtime calls `controller.onParamChange(param, value)`
(§4) — the scene never reads DOM events directly.

---

## 4. The `SceneController` (scene → runtime)

`createScene` returns a controller object. All methods are optional except where
an engine needs one to render anything.

| Method | Engine | Purpose |
|---|---|---|
| `setup(p)` | canvas | One-time setup; `p` is the p5 instance. Optional. |
| `draw(p)` | canvas | Called every animation frame by the runtime's p5 draw loop. This is where a canvas scene renders. |
| `render()` | svg | Optional convenience; svg scenes typically build their DOM inside `createScene` and mutate it in `onParamChange`. |
| `onParamChange(param, value)` | both | Called when a manipulable changes. `param` matches the manipulable's `param` key. |
| `destroy()` | both | Cleanup: stop any `requestAnimationFrame` loops, remove listeners. The runtime calls this before unmounting a beat. |

The runtime owns all engine bootstrapping (creating the p5 instance and its
draw loop, creating the `<svg>` root, wiring `postMessage`). Generated code
never touches `postMessage`, the DOM outside its surface, or engine setup.

---

## 5. The `ready` signal (screenshot timing)

The vision-critique validator screenshots the scene when `ctx.ready()` fires,
**not** on page load (docs/PLAN.md §5.2). This lets continuously-animating scenes
be captured at a deliberate, representative frame instead of a blank first paint.

Rules for the scene:

- Call `ctx.ready()` **exactly once**, when the first frame that represents the
  concept is drawn.
- **Static scenes** (most SVG): call it at the end of `createScene`, after the
  DOM is built.
- **Animated scenes** (most canvas): call it at the end of the **first** `draw`
  (guard with a flag), so the screenshot lands on a real frame.

The runtime enforces a timeout: if `ready` is never called, the scene is treated
as ready after a few seconds so a buggy scene can't hang validation forever.
That safety net is a runtime detail — generated code must still call `ready`.

---

## 6. Canvas scene skeleton

```js
export default function createScene(ctx) {
  const { params } = ctx;
  let amplitude = params.amplitude ?? 40;
  let firstFrame = true;

  return {
    setup(p) {
      p.frameRate(ctx.reducedMotion ? 1 : 30);
    },
    draw(p) {
      p.background(255);
      // ...draw using `amplitude` and (unless reducedMotion) p.frameCount...
      if (firstFrame) {
        firstFrame = false;
        ctx.ready();
      }
    },
    onParamChange(param, value) {
      if (param === "amplitude") amplitude = Number(value);
    },
  };
}
```

## 7. SVG scene skeleton

```js
export default function createScene(ctx) {
  const { svg, width, height, params } = ctx;
  const NS = "http://www.w3.org/2000/svg";

  const make = (tag, attrs) => {
    const el = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
    return el;
  };

  // ...build elements, append to `svg`...
  ctx.ready();

  return {
    onParamChange(param, value) {
      // ...update attributes in place...
    },
  };
}
```

---

## 8. Versioning

This document is **v1**. The lesson spec does not (yet) record a contract
version on each scene, because at MVP there is exactly one live contract. If a
v2 is ever needed, add a `scene.contractVersion` field and gate the runtime on
it, rather than silently changing v1 semantics.
