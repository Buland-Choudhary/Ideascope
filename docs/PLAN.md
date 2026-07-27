# Ideascope — Implementation Plan

**Status:** Draft v2 — planning complete, implementation not yet started. (v2 is a full revision pass: adopts API-native structured outputs and prompt caching, pins concrete model roles and pricing, and closes engineering gaps — scene runtime contract, screenshot timing, Playwright resource limits, SSE keepalives, observability, accessibility. See §18 for the change list.)
**Companion doc:** [`../README.md`](../README.md) has the project charter (why, principles, locked decisions D1–D12). This document turns that charter into an executable, ordered plan. Nothing here should contradict the README; if it ever does, the README is the source of truth for *what*, this doc is the source of truth for *how and in what order*.

This plan resolves every "open decision" the README flagged and adds the engineering detail needed to build without re-litigating architecture mid-implementation. Where the README left something ambiguous, this doc makes a concrete call — the goal is zero surprises once coding starts, not maximum flexibility.

---

## Table of contents

1. [New decisions this plan locks in](#1-new-decisions-this-plan-locks-in)
2. [System architecture](#2-system-architecture)
3. [The lesson spec — data contract](#3-the-lesson-spec--data-contract)
4. [Animation primitive vocabulary](#4-animation-primitive-vocabulary)
5. [Backend design](#5-backend-design)
6. [Frontend design](#6-frontend-design)
7. [Security & safety](#7-security--safety)
8. [Repository layout](#8-repository-layout)
9. [Tech stack summary](#9-tech-stack-summary)
10. [MVP boundary](#10-mvp-boundary)
11. [Roadmap — phased milestones](#11-roadmap--phased-milestones)
12. [Testing strategy](#12-testing-strategy)
13. [Deployment & CI/CD](#13-deployment--cicd)
14. [Cost & latency budget](#14-cost--latency-budget)
15. [Risk register](#15-risk-register)
16. [Demo-readiness checklist](#16-demo-readiness-checklist)
17. [Open questions to revisit](#17-open-questions-to-revisit)
18. [Revision history](#18-revision-history)

---

## 1. New decisions this plan locks in

The README listed three open items. Resolutions:

| Open item | Resolution |
|---|---|
| **Name availability** | `ideascope.io` is taken by an unrelated startup-idea-validation tool (small, different niche — low confusion risk, but rules out that exact domain). GitHub is fine (`Buland-Choudhary/Ideascope`, already this repo). **Decision:** use `ideascope.dev` or `getideascope.com` (or similar) for the deployed URL if a custom domain is bought later; the platform subdomain (e.g. `ideascope.vercel.app`) is sufficient for MVP/demo and costs nothing. Revisit only if a custom domain is desired before the internship application round. |
| **Deployment + open-source plan** | See [§13](#13-deployment--cicd). Frontend on Vercel, backend on Fly.io/Render, Docker for the backend, GitHub Actions for CI. Repo stays public from day one (it's a portfolio piece); **MIT license**, added once the repo has real content (end of Phase 0), so recruiters can freely browse and clone. |
| **MVP boundary + roadmap** | See [§10](#10-mvp-boundary) and [§11](#11-roadmap--phased-milestones). |

Additional decisions this plan makes that the README left implicit:

- **State/session persistence for MVP:** in-memory, single-process (a Python dict keyed by `lessonId`, TTL-evicted). No database for MVP — consistent with D9 (ephemeral). A DB only enters the picture in Phase 2 for shareable links.
- **Delivery transport for just-in-time beats:** Server-Sent Events (SSE), not WebSockets. Data only flows server→client after the initial request (manipulable interactions are handled entirely client-side against already-delivered code), so a one-directional stream is simpler and sufficient.
- **TTS for MVP:** the browser's native `SpeechSynthesis` API, not a backend TTS call. It's free, has zero added latency/cost, and satisfies D5 (toggleable narration) completely. A paid, higher-quality TTS backend (e.g. ElevenLabs) is a Phase-2 upgrade behind the same narration-toggle interface, not a rebuild.
- **Code execution sandbox:** *all* generated scene code — not just the "escape hatch" — runs inside a sandboxed `<iframe sandbox="allow-scripts">` (no `allow-same-origin`), talking to the host app over `postMessage`. This is stricter than D4's letter ("sandboxed escape hatch") but is the right call given D1 (any topic) makes the app a public arbitrary-code-generation surface. See [§7](#7-security--safety).
- **Engine count for MVP:** two engines, not four. **p5.js/canvas** (primary, general-purpose) and **SVG+DOM+KaTeX** (text/math/diagram-heavy beats). GSAP/Framer Motion and the free-form escape hatch are Phase-2 additions — D4 already calls this phasing out explicitly ("MVP leans on one primary engine plus SVG; other engines... come later"), this plan just makes the cut line concrete.
- **Structured outputs, not validate-and-retry:** the plan-stage call uses the Anthropic API's native structured outputs (`output_config.format` with a JSON schema — in the Python SDK, `client.messages.parse()` against the Pydantic lesson-spec models directly). The API guarantees schema-valid JSON, so retries are reserved for *semantic* problems (bad pedagogy, wrong beat count), not JSON shape. This deletes a whole class of parsing/retry code the v1 plan assumed.
- **Prompt caching is designed in, not bolted on:** every per-beat generation call shares a large stable prefix (pedagogy system prompt + primitive few-shot examples) with only the beat-specific intent varying at the end. With a `cache_control` breakpoint after the stable prefix, all N beat calls after the first read that prefix from cache at ~0.1× input price. This only works if the prompt layout is stable-first/volatile-last from day one — retrofitting it means restructuring every prompt, so it's locked now. (Corollary: no timestamps, request IDs, or per-lesson content in the system prompt.)
- **Model roles (concrete, revisit with Phase-3 cost data):** `claude-opus-4-8` for the plan call and vision self-critique (correctness-critical, low volume per lesson); `claude-opus-4-8` for per-beat scene generation initially, with `claude-sonnet-5` as the measured fallback if per-lesson cost runs high (near-Opus on coding tasks at a lower price point); `claude-haiku-4-5` for auto-fix regeneration (it's repairing a known error against a known message, not doing creative generation). Model IDs and pricing verified against current API docs — see §14.
- **Mock generation mode:** the backend ships a `MOCK_GENERATION=1` mode that serves the Phase-1 fixture lessons through the real API/SSE surface instead of calling Anthropic. Frontend development, E2E tests, and demos of the player itself cost $0 and run offline. Cheap to build in Phase 3 (the fixtures already exist from Phase 1), expensive to want later.

---

## 2. System architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Browser (React SPA)                                              │
│                                                                     │
│  ┌────────────┐   ┌───────────────────┐   ┌──────────────────┐   │
│  │ Topic form │──▶│ Lesson Player      │──▶│ Scene Renderer    │   │
│  │ (params)   │   │ (beat state        │   │ (per-beat sandboxed│   │
│  └────────────┘   │  machine, click-   │   │  <iframe>: p5.js   │   │
│                    │  to-advance,       │   │  engine or SVG/    │   │
│                    │  manipulables,     │   │  KaTeX engine)     │   │
│                    │  narration toggle) │   └──────────────────┘   │
│                    └─────────┬──────────┘                          │
└──────────────────────────────┼─────────────────────────────────────┘
                                │  HTTPS (REST + SSE)
┌───────────────────────────────▼─────────────────────────────────────┐
│  Backend (FastAPI, single service)                                   │
│                                                                       │
│  POST /api/lessons ─────▶ Plan stage (Claude) ─▶ Outline              │
│                               │                                       │
│                               ▼                                       │
│                    In-memory LessonState store (dict, TTL)            │
│                               │                                       │
│  GET /api/lessons/{id}/stream (SSE) ◀── Beat generation workers       │
│                               │             (async, sequential/JIT)   │
│                               ▼                                       │
│                    Per-beat pipeline:                                 │
│                    1. Generate scene code (Claude)                    │
│                    2. Render/execute check (headless Chromium,        │
│                       Playwright) + auto-fix retry (Claude)           │
│                    3. Vision self-critique (Claude vision) vs. intent │
│                    4. Pass → mark ready · Fail after retries →        │
│                       degrade to safe text/KaTeX fallback beat        │
└───────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
                      Anthropic API (Claude: text + vision)
```

**Why this shape:**
- The plan/generate/validate split maps directly to D7 + D8 — it's not a new idea, just the README's pipeline drawn out with concrete transport (SSE) and storage (in-memory dict) choices.
- Validation reuses the same headless-Chromium instance for both the render/auto-fix check and the screenshot the vision critique needs — one browser automation dependency (Playwright), not two.
- The sandboxed iframe is the single execution boundary for LLM-generated code on both the validation server (Playwright drives a real browser there too) and the learner's browser, so "what the validator checked" and "what the learner sees" are the same code path — no separate/divergent renderer to keep in sync.

---

## 3. The lesson spec — data contract

This is the contract between backend generation and frontend rendering. Backend defines it as Pydantic models; frontend mirrors it as TypeScript types (kept in sync by hand for MVP — a shared schema/codegen step is a nice-to-have, not worth the tooling overhead at this scale).

```jsonc
Lesson {
  id: string                     // uuid, session-scoped
  topic: string                  // as typed by the learner
  params: {
    duration: "short" | "medium" | "long",   // required (has a default: "medium")
    difficulty?: "beginner" | "intermediate" | "advanced",
    priorKnowledge?: string,      // free text, optional
    tone?: "playful" | "formal" | "neutral",
    language?: string             // reserved, not used pre-Phase-2
  },
  outline: {
    title: string,
    summary: string,
    targetBeatCount: number       // resolved from duration preset (3–5 / 6–9 / 10–14)
  },
  beats: Beat[]
}

Beat {
  id: string,
  index: number,
  intent: string,                 // pedagogical goal for this beat; internal/debug, not shown to learner
  narration: {
    text: string,                 // always present (D5)
    // no audioUrl for MVP — browser SpeechSynthesis reads `text` directly client-side
  },
  engine: "canvas" | "svg",       // MVP set; + "motion" | "sandbox" in Phase 2
  manipulables?: Manipulable[],
  scene: {
    code: string,                 // engine-specific source, validated & sandboxed
    // (entryPoint dropped when the scene contract was frozen in Phase 1 — every
    //  scene uses a fixed `export default`; see docs/SCENE_CONTRACT.md)
  },
  status: "pending" | "generating" | "validating" | "ready" | "failed" | "degraded",
  validation?: {
    renderOk: boolean,
    autoFixAttempts: number,
    critique?: { pass: boolean, feedback: string, attempt: number }
  }
}

Manipulable {
  id: string,
  label: string,
  type: "slider" | "stepper" | "toggle" | "select",
  param: string,                  // key the scene code reads from its params object
  min?: number, max?: number, step?: number,   // for slider/stepper
  options?: string[],             // for select
  default: number | string | boolean
}
```

**Notes:**
- `intent` exists so the vision self-critique has something concrete to grade against ("does this render achieve *this* pedagogical goal?"), and it doubles as a great debug/dev-mode overlay.
- `status: "degraded"` is the graceful-failure path from §5.3 — a beat that never passed validation still ships as a plain text+KaTeX summary rather than broken or missing content. Correctness-first (README principle 4) means the fallback must never be a blank beat.
- Duration → beat-count mapping is a plan-stage responsibility (the LLM decides exact count within the band based on topic complexity), not a hard client-side constant.

---

## 4. Animation primitive vocabulary

D3/D4's design implication calls for "a vetted vocabulary of reusable animation primitives" — this is the concrete starter list the plan-stage prompt selects from per beat, and the per-beat generation prompt is templated per primitive (few-shot examples per primitive, kept in the backend prompt library). Each primitive is engine-agnostic in concept but has a preferred engine:

| Primitive | Use for | Preferred engine |
|---|---|---|
| Timeline / sequence | ordered steps, history, processes over time | SVG |
| Plot / graph | functions, data trends, distributions | canvas |
| Geometric transform | rotation, scaling, projection, proofs | canvas |
| Process / flow diagram | pipelines, algorithms, state transitions | SVG |
| Comparison | side-by-side contrast, before/after | SVG |
| Part-to-whole | composition, hierarchies, ratios | SVG |
| Simulation | physics, agent-based, iterative systems | canvas |

This table lives in the backend prompt library (Phase 3–4), not just this doc — the plan-stage prompt is instructed to tag each beat with one primitive, which then picks both the engine and the few-shot template for the per-beat call. Growing this vocabulary (new primitives, better few-shots) is the highest-leverage ongoing quality work post-MVP, more so than adding engines.

---

## 5. Backend design

### 5.1 API surface (MVP)

| Method & path | Purpose |
|---|---|
| `POST /api/lessons` | Body: `{ topic, duration, difficulty?, priorKnowledge?, tone? }`. Kicks off plan stage + beat-1 generation async; returns `{ lessonId }` immediately (202-style). |
| `GET /api/lessons/{id}/stream` | SSE stream. Events: `outline_ready`, `beat_ready` (index + full beat payload), `beat_failed`, `lesson_complete`. |
| `GET /api/lessons/{id}` | Full current known state — used for SSE-reconnect and debugging. |
| `GET /api/lessons/{id}/beats/{index}` | Single beat detail (fallback if a client missed an SSE event). |
| `POST /api/lessons/{id}/beats/{index}/regenerate` | Learner-triggered regenerate (D7 — optional gate). Cheap to include once the pipeline exists; ships in MVP. |

No `/api/tts` endpoint in MVP (browser `SpeechSynthesis` handles it client-side — see §1).

### 5.2 Generation pipeline

1. **Plan call** (`claude-opus-4-8`, structured outputs): topic + params + pedagogy-principles system prompt → whole-lesson outline. The response is schema-enforced by the API (`client.messages.parse()` against the Pydantic outline models), so it cannot be malformed JSON. One retry is reserved for *semantic* failures the schema can't express (beat count outside the duration band, empty intents) — appended as feedback, then give up and surface a lesson-level error.
2. **Per-beat call** (`claude-opus-4-8`, text): outline beat (`intent`, primitive tag, engine) + primitive-specific few-shot template → scene code string. Prompt layout is cache-optimized (§1): stable system prompt + few-shots first with a `cache_control` breakpoint, beat-specific content last — beat calls 2..N read the shared prefix from cache.
3. **Render/auto-fix check** (Playwright, headless Chromium): load the sandboxed iframe runtime with the generated code; catch JS execution errors and console errors within a timeout (e.g. 5s). On failure, feed the error text + broken code to `claude-haiku-4-5` for a repair attempt (max 2 auto-fix attempts total) — repair is constrained, well-specified work that doesn't need the big model.
4. **Vision self-critique** (`claude-opus-4-8`, vision): screenshot the rendered beat at 2–3 points (initial "settled" state, and after simulating a manipulable/interaction if present) → Claude compares against `intent` + narration text → `{ pass, feedback }` (also a structured output). On fail, regenerate scene code once more with the critique feedback appended (max 1 critique-triggered retry). **Screenshot timing:** the runtime bridge's `ready` signal marks when the scene has reached its initial settled state — the validator screenshots on `ready`, not on page-load, so continuously-animating scenes are captured at a deliberate, representative frame. This makes "emit `ready` at a representative state" part of the scene-code contract (§6.2), enforced by the few-shot examples.
5. **Graceful degradation:** if a beat still fails after all retries, replace it with an auto-generated plain-text+KaTeX fallback beat (narration text is always present regardless, so this is a real fallback, not an empty state) and mark `status: "degraded"`. The lesson always completes; the learner is never blocked by a single bad beat.

Beats after #1 generate **sequentially in the background** for MVP (not fully parallel) — this bounds concurrent Anthropic API spend per lesson and matches D8's "just-in-time" framing. Parallel generation of beats 2+ (once beat 1 is delivered) is a Phase-2 optimization once cost/latency data from real usage justifies it.

**Browser resources:** validation runs against a single long-lived Chromium instance (fresh browser *context* per check, not fresh browser), guarded by an asyncio semaphore (e.g. max 2–3 concurrent render checks). Headless Chromium is the backend's dominant memory consumer — this cap is what makes the single-instance deployment (§13) viable, and it's also a natural backpressure mechanism under load.

### 5.3 State management

`LessonState` lives in an in-memory dict (`lessonId -> LessonState`) inside the single backend process, TTL-evicted (e.g. 2 hours). This is an explicit MVP scaling limitation: it only works behind a single backend instance (no horizontal scaling, state lost on restart/deploy). Documented, accepted trade-off given D9 (ephemeral persistence) — a Redis-backed store is the drop-in fix if/when multi-instance deployment is needed (Phase 2, only if traffic warrants it).

### 5.4 Rate limiting & cost guardrails

- IP-based token bucket (e.g. `slowapi`) capping lessons/hour per IP.
- Topic string length cap (e.g. 300 chars) and basic empty/gibberish rejection before it reaches the plan call.
- Hard timeout + max-retry ceiling per beat (bounds worst-case Anthropic spend per lesson — see §14 for the actual budget numbers).
- Global concurrency cap on render-check work via the Playwright semaphore (§5.2) — the API accepts new lessons but beats queue behind the semaphore rather than exhausting memory.

### 5.5 Observability — the generation trace log

Quality iteration on prompts is the core ongoing work of this project (§4), and it's impossible without data. Every generation attempt logs a structured record server-side: lesson ID, topic, beat index, primitive tag, engine, model used, attempt number, outcome (`ok` / `render_fail` / `critique_fail` / `degraded`), the error text or critique feedback on failure, token usage, and wall-clock latency. Plain JSONL to disk/stdout is fine for MVP (picked up by the host's log drain) — no observability stack needed. This is what turns "beat 4 of the entropy lesson looked wrong" into "the *simulation* primitive fails critique 40% of the time; fix its few-shots." Also the raw data for the §14 cost model. Note: topic strings are user input — keep log retention short and don't log anything else user-identifying beyond the rate-limit IP.

---

## 6. Frontend design

### 6.1 Component architecture

- **Topic form** — topic input + optional params (duration required with a default, others collapsed behind "more options"). Topic-only submit must be one click (README principle 5).
- **Lesson Player** — owns the click-to-advance state machine: `currentBeatIndex`, per-beat `ready|generating|failed` status (from the SSE stream), forward/back navigation, narration toggle state. Advancing past the last *ready* beat while later beats are still generating shows a lightweight "still preparing the next part" state rather than blocking — the format is self-paced, so slow generation degrades to "wait a beat," never to a broken click.
- **Manipulable controls** — renders slider/stepper/toggle/select per the beat's `manipulables[]`, feeds value changes into the active scene's runtime bridge (client-side only, no backend round-trip).
- **Narration** — text always rendered; toggle drives whether `SpeechSynthesis.speak()` fires alongside it.
- **Scene Renderer** — mounts the per-beat sandboxed `<iframe>`, loads the matching engine runtime (p5.js or SVG/KaTeX bundle) plus the beat's `scene.code`, and bridges `postMessage` for: init params/manipulable values in, ready/error/advance-hint signals out.

### 6.2 Engine runtime bridge (postMessage protocol)

Host → iframe: `{ type: "init", params, manipulables }`, `{ type: "updateParam", id, value }`.
Iframe → host: `{ type: "ready" }`, `{ type: "error", message }`.

Kept intentionally minimal for MVP — no "advance hint" or scene-driven pacing signals yet (self-paced means the *learner* clicks, the scene never auto-advances, so the protocol doesn't need a completion event beyond `ready`).

**The scene-code contract (Phase-1 deliverable, frozen before any prompts are written):** the exact API surface that generated code targets — the shape every few-shot example, the validator, and the client renderer all depend on. Sketch (finalized in Phase 1):

```js
// What a generated scene module must export, per engine:
export function setup(stage, params) { ... }        // stage: engine-provided handle (p5 instance / SVG root); params: current manipulable values
export function onParamChange(name, value) { ... }  // optional; called on manipulable interaction
// The engine runtime wraps these: it owns the p5/SVG boilerplate, calls setup(),
// emits `ready` after the first settled frame, and routes updateParam → onParamChange.
```

Generated code never touches `postMessage`, the DOM outside its stage, or engine bootstrapping — the hand-written runtime owns all of that. Keeping the generated surface this small is both a correctness lever (less for the LLM to get wrong) and a security lever (less API to abuse). Changing this contract after Phase 4 means regenerating every few-shot, so it gets a deliberate design pass, not an incidental one.

### 6.3 State machine (informal)

`idle → submitting → outline_ready → (per beat: pending → generating → ready|degraded) → beat[0] shown → learner clicks next → beat[1] shown (or "preparing…" if not ready yet) → ... → lesson_complete`

Back navigation is always allowed to any already-ready beat (no regeneration). This is a simple linear array with a cursor, not a general graph — no need for anything heavier for MVP.

### 6.4 Accessibility (MVP-scoped, concrete)

Not a Phase-9 afterthought — three items are cheap now and expensive later:

- **Keyboard advance:** `Space`/`→` advance, `←` goes back, focus never trapped inside the scene iframe. Click-to-advance is the product; keyboard-to-advance is the same product for keyboard users.
- **`prefers-reduced-motion`:** the engine runtimes expose this to scenes as a param, and the few-shot examples demonstrate honoring it (settle to the final state without continuous animation). An animation-heavy learning app that ignores this setting excludes exactly the users it claims to serve.
- **Narration text as the accessible channel:** narration text lives in the DOM (not inside the canvas), in an `aria-live="polite"` region on beat change — screen readers get the full lesson content even though the animation itself is visual.

---

## 7. Security & safety

Given D1 (any topic) + D2 (LLM writes live code), the app is effectively a public arbitrary-code-generation-and-execution surface. This needs explicit defenses, not just "the vision critique will catch it":

- **Execution sandbox:** every scene runs in an `<iframe sandbox="allow-scripts">` with **no** `allow-same-origin` — the iframe cannot read cookies, localStorage, or the parent DOM, and has no origin to make same-origin requests from. Communication is `postMessage` only.
- **Network isolation:** a strict CSP on the iframe document (`default-src 'none'; script-src 'self' ...`) prevents generated code from making network calls at all — scenes are pure rendering, no fetch needed by design.
- **Static denylist before execution:** generated code is scanned (simple regex/AST check) for `fetch`, `XMLHttpRequest`, `import(`, `eval(`, `document.cookie`, `window.parent`, `window.top` before it's ever run, both at validation time and defensively again client-side. Reject/regenerate on match rather than execute.
- **Execution timeout / watchdog:** both validation-time (Playwright) and learner-side (iframe) enforce a render timeout; a scene that hangs (bad loop) is killed and treated as a render failure → auto-fix path.
- **Prompt-injection resistance:** the topic field is untrusted user text fed into a system-prompted call. System prompts are structured so topic content is clearly delimited as data, not instructions; output is always schema-validated (Pydantic) regardless of what the model was told, so a successful injection can at most produce an off-topic *but still schema-valid and sandboxed* lesson — it cannot escalate to code execution outside the sandbox or leak the system prompt into a rendered beat undetected (schema has no field for arbitrary prose outside `narration`/`intent`).
- **Secrets:** Anthropic API key lives server-side only (env var / platform secret store), never shipped to the client. All Anthropic calls are backend-initiated.

---

## 8. Repository layout

Target layout once Phase 0–3 scaffolding lands (not created yet — this plan intentionally ships docs-only first):

```
Ideascope/
├── README.md
├── LICENSE                    # MIT, added end of Phase 0
├── docs/
│   ├── PLAN.md                 # this file
│   └── SCENE_CONTRACT.md       # frozen scene-code runtime contract (Phase 1)
├── frontend/                   # React + TS + Vite (Phase 2+)
│   ├── src/
│   │   ├── components/         # TopicForm, LessonPlayer, ManipulableControls, ...
│   │   ├── engines/             # canvas runtime, svg/katex runtime, postMessage bridge
│   │   ├── state/               # lesson player state machine
│   │   └── types/                # TS mirror of the lesson spec
│   └── ...
├── backend/                    # FastAPI (Phase 3+)
│   ├── app/
│   │   ├── api/                 # route handlers
│   │   ├── generation/           # plan stage, per-beat stage, prompt templates + few-shots
│   │   ├── validation/            # render/auto-fix, vision critique
│   │   ├── models/                 # Pydantic lesson spec
│   │   ├── fixtures/                 # hand-authored fixture lessons (Phase 1) + loader
│   │   └── state/                   # in-memory LessonState store
│   ├── scripts/                    # build_fixtures.py (authors fixtures → JSON)
│   └── ...
└── .github/workflows/          # CI (Phase 0/10)
```

---

## 9. Tech stack summary

| Layer | Choice | Notes |
|---|---|---|
| Frontend framework | React + TypeScript + Vite | matches D4 ("React shell is hand-written") |
| UI chrome styling | Tailwind CSS | fast, keeps custom CSS to the animation engines themselves |
| Canvas engine | p5.js | mature, simple imperative API well-suited to LLM code generation |
| SVG/text engine | native SVG + DOM + KaTeX | KaTeX for math rendering inside beats |
| Motion library (Phase 2) | GSAP or Framer Motion | deferred — not in MVP |
| Backend framework | FastAPI (Python) | confirmed per README's working assumption |
| Validation schemas | Pydantic (backend), hand-mirrored TS types (frontend) | |
| Headless render/screenshot | Playwright (Chromium) | shared by render-check and vision-critique screenshot steps |
| LLM | Claude via Anthropic API (text + vision) | per D10; model roles in §1, pricing in §14 |
| LLM output shaping | API structured outputs (`client.messages.parse()` / `output_config.format`) | schema-enforced JSON, no parse-retry code |
| TTS (MVP) | Browser `SpeechSynthesis` | free, zero backend latency; upgrade path in Phase 2 |
| Streaming transport | Server-Sent Events | one-directional server→client is sufficient |
| Session state (MVP) | In-process dict, TTL-evicted | no DB per D9 |
| Frontend hosting | Vercel | |
| Backend hosting | Fly.io or Render (containerized) | |
| CI | GitHub Actions | lint + typecheck + test on PR |
| License | MIT | added end of Phase 0 |

---

## 10. MVP boundary

**In scope for MVP (the demoable, resume-ready v1):**

- Topic + duration required inputs; difficulty/prior-knowledge/tone optional, collapsed by default.
- Two-stage generation pipeline (plan → per-beat), sequential background generation, SSE delivery.
- Two engines: p5.js/canvas + SVG+DOM+KaTeX.
- Full validation pipeline: render/auto-fix → vision self-critique → bounded retries → graceful text/KaTeX degradation (never a blank/broken beat).
- Basic manipulables: slider, stepper, toggle, select, reactive client-side.
- Narration: always-present text + browser-TTS toggle.
- Click-to-advance player with back navigation and "still preparing" states.
- Learner-triggered per-beat regenerate.
- Rate limiting, topic length caps, execution sandbox, prompt-injection-hardened prompts.
- Deployed (Vercel + Fly.io/Render), public repo, MIT license, polished README + short demo GIF/video.

**Explicitly out of scope for MVP (Phase 2+, see §11):**

- GSAP/Framer Motion engine and the free-form sandboxed escape-hatch engine.
- Shareable links / any persistence beyond the in-memory session.
- Paid/higher-quality TTS backend.
- Learning-outcome evaluation (D12 stretch — post-lesson quiz/adaptivity).
- Multi-language narration/text.
- Curated public gallery of pre-generated example lessons.
- Parallel (vs. sequential) background beat generation.
- Analytics/telemetry.

---

## 11. Roadmap — phased milestones

Phased by deliverable, not calendar — but rough pacing assumes a solo, part-time, semester-length effort. Each phase lists its exit criteria; don't start the next phase until the current one's criteria are met, since later phases assume earlier contracts (especially the lesson spec) are stable.

- **Phase 0 — Foundations. ✅ DONE.** Repo scaffolding, base CI (lint/typecheck/test/build for both apps), MIT license. Frontend (React/Vite/Tailwind) and backend (FastAPI) both build and pass all checks; hello-world loop verified end-to-end in a real browser. *(Deferred, non-blocking: actual Vercel/Fly.io deploy + Anthropic key provisioning — needs account credentials; deploy configs are in place.)*
- **Phase 1 — Lesson spec + scene contract. ✅ DONE.** Pydantic models (`backend/app/models/lesson.py`) with cross-field validation + camelCase wire format; hand-mirrored TS types (`frontend/src/types/lesson.ts`); the scene-code runtime contract **frozen** in `docs/SCENE_CONTRACT.md`; two hand-authored fixtures (sine wave / canvas + water cycle / svg) covering both engines and slider/stepper/toggle manipulables, built via `scripts/build_fixtures.py`. *Exit met: fixtures validate against the schema (tests), all 6 scene modules verified as valid ES-module JS via `node --check`, scene code written against the frozen contract.*
- **Phase 2 — Static player shell. ✅ DONE.** Lesson Player + click-to-advance state machine (`usePlayerState`), both engine runtimes via the sandboxed-iframe `postMessage` bridge implementing the frozen contract (`engines/sceneRuntime.ts`, `SceneRenderer.tsx`; p5 inlined for canvas, native SVG for the other), manipulable controls (slider/stepper/toggle/select), keyboard nav, `aria-live` narration, and the §7 denylist scan — all against the Phase-1 fixtures, no backend. *Exit met: verified in a real browser (Playwright/Chromium) — both fixtures play end-to-end, canvas + SVG scenes render, click-to-advance + keyboard nav + manipulables all work; 17 unit tests + a 12-check E2E pass. (Known optimization deferred to Phase 9: p5's ~1 MB inlines into the bundle; lazy-load it per canvas scene.)*
- **Phase 3 — Backend skeleton + plan call. ✅ DONE.** `POST /api/lessons` (synchronous for now; SSE in Phase 6), plan-stage call via structured outputs + cache-optimized prompt + semantic beat-band retry (`app/generation/`), mock generation mode (§1) serving fixtures, the generation trace log (§5.5), topic length cap (§5.4), and a light frontend topic-form integration. *Exit met: mock end-to-end verified in a real browser (topic form → backend → player renders); plan logic unit-tested with a fake Anthropic client. **Live Claude call spot-checked against 10 varied real topics** (`scripts/spot_check_plan.py`) — technical (sine wave, binary search, neural nets/backprop), science (water cycle, photosynthesis, entropy), civics, economics, philosophy: **10/10 succeeded, 10/10 in-band on the first pass**, no retries needed, sensible primitive/engine tagging throughout. Per-call latency 10–28s (non-streaming; the long/14-beat lesson was the outlier) — a data point for the Phase 6 JIT/streaming design, not a blocker here.*
- **Phase 4 — Per-beat generation. ✅ DONE.** Per-beat Claude calls via structured outputs, one few-shot per primitive (all 7) bundled into a single fully-static, cache-optimized system prompt (stronger than originally planned — every beat call across every lesson shares the cache prefix, not just within one lesson). Two pre-render checks (contract compliance, §7 denylist) each with a feedback-guided retry; a transient-error classifier (`app/generation/retry.py`) retries genuine API blips (5xx/429/connection errors) without burning the quality-retry budget on a bug. Real mode now returns a fully generated (not yet execution-validated) lesson. *Exit met, in full:* a third live spot-check (`scripts/spot_check_beats.py`, 5 fresh topics, after two prior attempts hit transient Anthropic-side `529 Overloaded` — see below) succeeded completely: **23/23 generated beats valid JavaScript** across all 7 primitives and both engines ($1.25). Beyond that, a real end-to-end browser check (topic "how tides work," never previously seen) generated a full lesson live through the actual running app and played all 5 beats with **zero render errors** — screenshot-verified, an SVG tide-curve scene with high/low markers and time labels, matching the pedagogy prompt's intent. This is the first phase where a real topic a user types produces a genuinely playable animation. Along the way, fixed a real gap the live runs surfaced: the generation trace log (§5.5) had no default logging handler and silently dropped every record under plain uvicorn — fixed in `app/observability/trace.py`, unit-tested. 36 tests pass, ruff + mypy clean. Total live-verification spend across Phase 3+4: **~$1.94** (10 plan-only spot-check topics + two failed + one successful 5-topic beat spot-check + one full real-mode browser generation), zero wasted on code bugs — the only "waste" was retries into a transient Anthropic-side capacity issue, not anything in this codebase.
- **Phase 5 — Validation pipeline. ✅ DONE.** Full render/auto-fix/critique/degrade pipeline (`app/validation/`): a Python port of the sandboxed-iframe scene runtime (`runtime.py`, deliberately *without* the frontend's 3s ready-fallback — a hang must fail, not silently pass); a single long-lived headless-Chromium instance with a `threading.Semaphore` concurrency cap (`browser.py`, using the pre-installed binary directly, no `playwright install`); the render/auto-fix check (`render_check.py`, catches thrown errors, console errors, and hangs, screenshots on success, simulates one manipulable interaction); auto-fix repair on `claude-haiku-4-5` (`auto_fix.py`); vision self-critique on `claude-opus-4-8` (`critique.py`, screenshots sent as image content blocks, structured `Critique{passed, feedback}` output); a deterministic, non-LLM text fallback (`fallback.py`, safe against injection via `.textContent`, never `.innerHTML`); and the `validate_beat` orchestrator (`pipeline.py`) tying it together with bounded regeneration (critique feedback fed back into `generate_beat_scene` via a new `extra_feedback` param) and graceful degradation to `BeatStatus.DEGRADED` when retries are exhausted. Wired into `generate_lesson` so every real-mode beat is now render-checked and critiqued before being returned. *Exit met: 58 tests pass (ruff/mypy/pytest clean) — new unit tests for auto-fix and critique against a fake client, orchestration tests for every pipeline branch (happy path, auto-fix recovery, critique-triggered regeneration, the critique-call-itself-failed carve-out, and both degradation paths), plus real-headless-Chromium tests for render-check (good/missing-export/thrown-error/hang/manipulable-interaction) and the fallback scene (including an adversarial `<script>` payload) — all free, no Anthropic cost. **Live-verified against the real API**: a full 5-beat "how a rainbow forms" lesson generated, rendered, and passed vision critique end-to-end with zero degraded beats; two real critique-triggered regenerations fired and succeeded exactly as designed (fail → feedback → regenerate → re-render → pass) across two different lessons. Live run stopped when the Anthropic account ran out of credit (a real, correctly-classified-as-non-retryable 400) — spend up to that point: ~17.4K input / ~30.2K output tokens on `claude-opus-4-8` (auto-fix/haiku never triggered — every observed failure was a critique-quality fail, not a render fail), **~$0.84**.*
- **Phase 6 — JIT delivery. ✅ DONE.** `POST /api/lessons` now returns `{lessonId}` immediately (202) and kicks off generation on a background thread; `GET /api/lessons/{id}/stream` (SSE) emits `outline_ready`, `beat_ready`, `beat_failed`, `lesson_complete`/`lesson_failed` as they happen, with a 15s keepalive and full replay-from-0 on reconnect; `GET /api/lessons/{id}` and `/beats/{index}` cover reconnect/debug and the single-beat fallback. State lives in an in-memory, TTL-evicted `LessonState`/`LessonStore` (`app/state/`) — a background thread writes an append-only event log, the async endpoint polls it, matching docs/PLAN.md §5.3's accepted single-process MVP trade-off. `generate_and_validate_beat` was extracted out of `generate_lesson` so the batch path (Phase 3-5) and the new streaming orchestrator (`app/generation/orchestrator.py`) share it; a beat-level bug now always degrades to the deterministic text fallback rather than leaving a gap, so beat indices stay contiguous even on an unexpected failure. Mock mode replays a complete fixture through the exact same event sequence real generation produces, so the JIT/SSE surface is exercised for $0. On the frontend, `usePlayerState` now tracks `outline.targetBeatCount` as the real total (independent of how many beats have arrived) and renders a non-blocking "still preparing this part" placeholder for any index beyond what's streamed in yet; `createLesson`/`streamLesson` (native `EventSource`) replace the old synchronous POST. *Exit met: 72 backend tests (16 new) and 20 frontend tests (both suites' full ruff/mypy/eslint/tsc pass), then a real end-to-end check against live `uvicorn`+`vite` dev servers (mock mode, $0) — an actual browser `EventSource` connection to FastAPI's real `StreamingResponse` (not TestClient), submitting a topic, watching the outline arrive, the first beat render inside the real sandboxed iframe (screenshot-verified), and navigating through to the last beat. That live run caught a real bug unit tests missed: resetting a beat's manipulable params in a `useEffect` painted one frame of the *previous* beat's values against the *new* beat's controls — a slider whose param key didn't exist in the stale values rendered `value={undefined}` (NaN in the DOM). Fixed by switching to React's "adjust state during render" pattern (`usePlayerState.ts`), which resets synchronously before paint; re-verified live, confirmed clean (screenshot: beat 3/3, frequency slider correctly at 1.5, no NaN). Two console warnings observed during the live run (a favicon 404, and a `Permissions policy violation: accelerometer` from p5.js's device-orientation probing inside the sandboxed iframe) were confirmed pre-existing — reproducible on the plain Phase-2 fixture path with no JIT generation involved — so left as-is, not a Phase 6 regression.*
- **Phase 7 — Manipulables end-to-end. 🟡 IN PROGRESS.** Most of the wiring already existed from earlier phases (the plan prompt's MANIPULABLES rule, per-primitive few-shots all demonstrating `onParamChange`, and the frontend's manipulable controls/postMessage bridge from Phase 2) — what was missing was verification that a generated manipulable actually, visibly does the right thing, not just that the static frame looks right. Closed the scope cut flagged in `render_check.py`'s own Phase-5 docstring: the interaction screenshot it already captured (after simulating one manipulable change) is now fed to the vision critique alongside the base screenshot, with which param changed to what value, so a beat only passes if the interaction produces a correct, visible change (`app/validation/critique.py`, `pipeline.py`). 75 tests pass (3 new), ruff/mypy clean, zero API cost. *Exit not yet met: the plan calls for live-verifying at least 2 real generated lessons with working manipulables end-to-end, which needs real API access — the Anthropic account is still out of credit (confirmed via a direct probe call, same `Your credit balance is too low` error as the Phase 5 close-out). Deferred until credits are available; nothing else is blocking it.*
- **Phase 8 — Narration. ✅ DONE.** `useNarrationSpeech` (`frontend/src/player/useNarrationSpeech.ts`) wraps the browser's native `SpeechSynthesis` API per docs/PLAN.md §1 — no backend TTS call, zero added cost/latency. A toggle button in the player header (default off) drives whether `speak()` fires; narration text itself is rendered unconditionally regardless of toggle state (already true since Phase 2, unchanged here). Speaking a new beat cancels any utterance in progress first, so navigating quickly never overlaps two beats' narration; unmounting the player (or the API being unavailable) cancels/no-ops cleanly rather than leaving something talking or throwing. *Exit met: 32 frontend tests pass (12 new — a fake `SpeechSynthesis` global for the hook's own unit tests plus a `LessonPlayer` integration suite covering default-off, toggle-on speaks the current beat, toggle-off cancels and stays silent on navigation, narration text always visible, and graceful disablement when unsupported), zero API cost. **Live-verified against real `uvicorn`+`vite` dev servers and real headless Chromium** — confirmed real Chromium implements `SpeechSynthesis` even headless, instrumented `speechSynthesis.speak` in the actual running app, and confirmed: toggle starts off, toggling on speaks beat 1's exact narration text, navigating to beat 2 speaks its narration, toggling off leaves the narration text visible while silencing further navigation. Screenshot-verified.*
- **Phase 9 — Polish & hardening. ✅ DONE.** The §7 checklist's execution sandbox, network isolation, denylist, timeouts, and secrets handling were already in place from earlier phases; this phase added the one missing §5.4 item and closed real gaps live testing surfaced. **Rate limiting**: an IP-based cap (`slowapi`, default 20 lessons/hour, `app/rate_limit.py`) on `POST /api/lessons`, returning 429 past the limit. **Junk-topic hardening**: fixed a real bug where `min_length=1` was checked *before* stripping, so a whitespace-only topic passed validation and only became empty later — now stripped and re-validated in one `field_validator`; gibberish topics still produce a schema-valid lesson by construction (structured outputs). **Accessibility**: added a visible focus ring to the one input that had suppressed its default outline; added a missing `role="status" aria-live="polite"` to the "planning your lesson" state; verified via real keyboard tab-through in real Chromium that every landing-page control has a visible focus indicator. **Responsive**: found and fixed a real horizontal-overflow bug at a 375px viewport — the topic-form row's `flex` children had no shrink budget (classic `min-width: auto` flexbox trap); now stacks vertically below `sm:`, verified overflow-free live. **Adversarial testing**: live-scripted (not just imagined) junk topics, a 5000-char topic (client-truncates to 300, server rejects longer), and rapid-fire clicking — which caught a **real double-submission bug**: firing several clicks in one JS tick outpaces React's disable-the-button re-render, so all of them reached the submit handler (5 clicks → 5 POSTs). Fixed with a synchronous `useRef` guard in the submit handler, independent of any render round-trip; verified live (5 clicks → 1 POST) and covered by a regression test that fails without the fix. **Also closed a Phase-2-deferred performance item**: p5 (~1 MB) now loads via a dynamic `import()` instead of a static one, so it lands in its own cacheable chunk instead of bloating every learner's initial download regardless of whether their lesson ever uses a canvas scene — main bundle dropped from 1,286 KB to 222 KB; live-verified an SVG-only lesson never fetches the p5 chunk at all, a canvas lesson fetches it exactly once across the whole session (cached for subsequent beats), and canvas scenes still render correctly. *Exit met: 79 backend + 33 frontend tests pass (14 new), zero API cost — all of the above verified against real headless Chromium and real dev servers in mock mode, not just unit tests.*
- **Phase 10 — Deployment & demo readiness. 🟡 STARTED EARLY.** Decided to deploy incrementally rather than wait for full feature completeness, so progress is checkable from any device after each change. `backend/Dockerfile` was fixed along the way (was a stale Phase-0 stub missing `anthropic`/`slowapi`/`playwright` deps entirely — would not have booted) and rebuilt on `uv sync`, verified locally (561MB image, boots clean, `/api/health` + `POST /api/lessons` both work in a container). `render.yaml` (backend) and `frontend/netlify.toml` (frontend) target Render + Netlify's free tiers, chosen after comparing current terms across Render, Fly.io, Railway, Netlify Functions, Cloud Run, and Oracle Cloud.
  **Known, deliberate deviation — validation pipeline skipped in the deployed real-mode path.** `IDEASCOPE_SKIP_VALIDATION=true` (new setting, `app/config.py`; bypassed in `app/generation/service.py`'s `generate_and_validate_beat`, tested in `tests/test_service.py`) makes real generation skip render-check/auto-fix/vision-critique (docs/PLAN.md §5.2 steps 3-5) entirely and ship each beat's generated code straight through. Chosen to avoid both the Chromium hosting requirement (keeps the deployed backend on Render's free 512MB tier even in real mode) and the vision-critique Anthropic spend, given the $5 total credit budget. **This is a real, acknowledged trade-off against README principle 4 ("correctness first... a wrong-but-pretty animation is a failure") and the §15 risk register's top entry** — there is no longer a server-side gate catching a beat that renders but is pedagogically wrong, and no auto-fix repair for one that errors outright (the client-side sandboxed-iframe error handling in `engines/SceneRenderer.tsx` still catches genuine crashes and shows a "couldn't render this scene" fallback instead of a blank beat, so failures are visible/graceful, just not caught or repaired before a real visitor sees them). The validation pipeline's code is untouched and fully tested — this is a one-line config flip to turn back on, not a redesign. Revisit before treating this deployment as demo/recruiter-ready; until then, catching bad beats means periodically generating a few real lessons and looking at them, not an automated gate. `IDEASCOPE_LESSONS_RATE_LIMIT` was also tightened to `5/hour` on the deployed instance (from the app default `20/hour`) specifically because of the small credit budget. *Exit: §16 checklist fully green — not yet met; accounts/actual deploy still pending, and the validation trade-off above should be revisited before checking that box for good.*
  **Post-deploy iteration (real app, real users, real bug reports).** Deployed and live on Render + Netlify; work continues against the live app rather than waiting for a "phase" to formally close. This round: (1) **fixed a real reported bug** — the "Done" button on a lesson's last beat was both disabled (`canNext` is false on the last index, and the button's `disabled` was wired to it) and, even if it hadn't been, wired to `next()`, a no-op at the last index. Now calls `onExit` and is enabled whenever one is provided (`LessonPlayer.tsx`); regression-tested, live-verified (click Done on beat 3/3 → lands back on the topic form). (2) **Added GSAP** (`ctx.gsap`, ~70 KB minified, free/MIT-equivalent license) to the scene contract as a purely additive, non-breaking extension (§2.1 of `docs/SCENE_CONTRACT.md` — no version bump needed) — a tweening/timeline library available in *both* engines via the same lazy-dynamic-import pattern as p5, so generated scenes can use real easing (`"back.out"`, `"elastic.out"`, etc.) instead of hand-rolled sine/frame-counter interpolation. The `process_flow` few-shot was rewritten to demonstrate the pattern (an eased "pop" on the active stage instead of an instant color snap); the contract-rules prose now documents when/how to use it, including respecting `ctx.reducedMotion`. Live-verified in a real browser: a real GSAP tween visibly animated inside the sandboxed iframe (screenshots differ before/after), both engines confirmed via the backend's Python-ported runtime too. **Found and fixed a second, pre-existing bug along the way**: `ctx.katex` was documented in the contract and promised in the beat-generation prompt but was *never actually implemented* in either runtime — any beat reaching for it would have crashed (gracefully, via the client-side sandboxed-iframe error fallback, but still a beat that should have worked). Removed from the active prompt and contract until it can be done properly (KaTeX needs its fonts embedded as `data:` URIs under the sandboxed CSP, which is real additional work, not a one-liner). (3) **Cost lever**: with `skip_validation` already removing the critique/auto-fix spend, the remaining per-lesson cost is dominated by per-beat generation calls (one per beat, long code output). Switched the default `beat_model` from `claude-opus-4-8` to `claude-sonnet-5` (~40% cheaper on output tokens, still a strong coding model) — `app/config.py` default plus explicit `IDEASCOPE_BEAT_MODEL` in `render.yaml` for the deployed instance; revert via `IDEASCOPE_BEAT_MODEL=claude-opus-4-8` to trade cost back for quality if generation quality suffers noticeably. *92 backend + 35 frontend tests pass (13 new), zero Anthropic cost — all of the above verified against real headless Chromium, not just unit tests.*
  **Post-deploy iteration round 2 (latency, cost transparency, lightweight review, visual polish).** Four issues raised directly against the live deployed app. (1) **Latency**: beats used to generate strictly one at a time (each a ~15-25s Anthropic call), so a 6-beat lesson could take 90-150s. Fixed via bounded-concurrency generation (`app/generation/orchestrator.py`, new `beat_generation_concurrency` setting, default 3) — safe only when `skip_validation=true`, since a beat is then just one independent Anthropic call; concurrency is forced back to 1 — a plain sequential loop, deliberately *not* wrapped in a `ThreadPoolExecutor` at all — whenever the Playwright-based validation pipeline is active, because Playwright's sync API requires every call to originate from one consistent thread across the shared browser singleton's whole lifetime. Two separate greenlet thread-affinity crashes were hit and fixed getting this right: real concurrency broke it first, then — more subtly — even a `max_workers=1` `ThreadPoolExecutor` broke it a second time, because each `ThreadPoolExecutor()` spins up a *new* worker thread per lesson, so two lessons generated back-to-back would each hand Playwright a different thread. Beats can now finish out of order: `LessonState.add_beat` keeps its list sorted by index, `GET .../beats/{index}` looks up by the beat's own `index` field instead of list position, and `Lesson.check_beat_indices` was relaxed from "list is exactly 0..N-1 in order" to "indices are unique and in range" (full contiguity is still enforced once every beat has arrived, by the pigeonhole principle) — a real bug this parallelization would otherwise have shipped into `GET /api/lessons/{id}` (a beat-index-out-of-list-order lesson failing to validate) was caught by a new test before merge, not after. (2) **Lightweight code review**, replacing the heavy validation this deployment already runs without: `app/validation/code_review.py` asks `claude-haiku-4-5` to read each beat's generated source (no rendering, no Chromium needed) and flag a real, specific problem — missing `ctx.ready()`, an ignored manipulable, hardcoded pixel sizes, an obvious JS bug — or confirm it plausibly meets the stated intent; a beat that fails gets one feedback-guided regeneration retry, the same shape as the full pipeline's critique loop (`app/validation/pipeline.py`) just without ever executing anything. (3) **Model picker + cost transparency**: `POST /api/lessons` accepts an optional `model` field (validated against a 3-model allowlist in `app/config.py`; `GET /api/models` exposes the list with live `$/MTok` pricing from `app/observability/pricing.py`) that overrides `plan_model`/`beat_model` for that lesson only. Every real Anthropic call — plan, beat, code-review, and (when the full pipeline runs) auto-fix/critique — now reports its token usage via an `on_usage` callback threaded down to `LessonState.record_usage`, aggregated per (stage, model) into a `LessonUsage` surfaced on the `lesson_complete`/`lesson_failed` SSE events and `GET /api/lessons/{id}`; the frontend shows a `$X.XXXX · N tokens` badge (hover for the per-stage breakdown) once generation completes, plus a model dropdown on the topic form. (4) **Visual quality**: the beat-generation system prompt's entire visual-design guidance used to be one sentence ("keep it clear... correctness matters more than polish") — replaced with a concrete design system (fixed indigo `#4f46e5`/amber `#f59e0b` palette, soft off-white `#f8fafc` background, drop shadows via `p.drawingContext.shadowBlur`/svg `feDropShadow`, rounded corners, an explicit `system-ui` font stack, generous margins) and all 7 per-primitive few-shots in `app/generation/beat_prompts.py` rewritten to demonstrate it. Verified by actually rendering all 7 examples through the real p5/GSAP runtime (not the app's iframe bridge, but the same libraries and `ctx` contract) and screenshotting the output — confirmed shadows, palette, rounding, and typography all render correctly, not just that `node --check` accepts the syntax. *105 backend + 42 frontend tests pass (19 new — concurrency, out-of-order beat handling, the relaxed index validator, code-review pass/regenerate paths, usage aggregation/thread-safety, the model-override API surface, and the frontend model picker/cost badge), ruff/mypy/eslint/tsc all clean.* **Live-verified against the real Anthropic API, not just mock mode**: one real "how photosynthesis works" lesson (5 beats, `claude-haiku-4-5` override, `skip_validation=true` — the deployed configuration) exercised all four changes at once. The trace log confirms beats 1 and 2 started generating before beat 0 finished (concurrency working); beat 1 failed its code review (`critique_fail`), was regenerated, and passed its re-review (`ok`) — the review loop catching and fixing a real generation defect live, not in a test; every plan/beat/review call used the requested `claude-haiku-4-5` override; and the final lesson's reported usage matched the trace log exactly: **1 plan + 6 beat + 6 code-review calls (one beat regenerated), 18,579 input / 15,316 output tokens, $0.0952 total** — all 5 beats shipped `ready` with `critiquePass: true`.
- **Phase 11 — Stretch (time-permitting).** Prioritize by resume value for an ML internship narrative: learning-outcome eval (D12) and a third engine are the highest-value adds; shareable links and a curated gallery are next; multi-language and paid TTS last.

---

## 12. Testing strategy

- **Unit tests:** Pydantic schema validation (backend), primitive template rendering, state-machine transitions (frontend).
- **Component/snapshot tests:** manipulable controls, player navigation states.
- **E2E tests (Playwright):** full topic-submit → play-through flow against the fixture lessons (Phase 2) and, later, against a small fixed set of real topics run in CI on a schedule (not every PR, to bound Anthropic spend) as a **generation-quality regression suite** — the same ~10 topics used as manual spot-checks in Phases 3–5, automated once the pipeline stabilizes.
- **Security tests:** attempt the denylisted APIs (`fetch`, `eval`, etc.) from inside a test scene and confirm the sandbox blocks them; basic prompt-injection attempts in the topic field confirm schema validation still holds.

---

## 13. Deployment & CI/CD

- **Frontend:** Vercel, auto-deploy from `main` (or the working branch during development), preview deployments per PR.
- **Backend:** Dockerized FastAPI, deployed to Fly.io or Render. Single instance for MVP (consistent with the in-memory state decision in §5.3). **The image includes headless Chromium for Playwright** — use the official Playwright Python base image; expect ~1.5 GB image and size the instance at **≥1 GB RAM** (Chromium is the dominant consumer; the §5.2 semaphore keeps it bounded). This rules out the smallest free-tier instances — budget for one small paid instance.
- **CORS:** backend allowlists exactly the Vercel production domain + preview-deployment pattern; no wildcard origin (the API is unauthenticated, so CORS + rate limiting are the only abuse dampeners).
- **SSE keepalives:** the stream endpoint emits a comment/heartbeat event every ~15s so proxies and the hosting platform's idle-timeout don't silently kill long-lived connections while the learner reads; the client treats a dropped stream as reconnect-then-`GET /api/lessons/{id}` (already in §5.1).
- **CI (GitHub Actions):** on every PR — lint + typecheck (frontend), lint + type-check via `mypy`/`ruff` (backend), unit tests both sides. The generation-quality regression suite (§12) runs on a schedule (e.g. nightly), not per-PR, since it costs real Anthropic API spend.
- **Secrets:** Anthropic API key stored in the hosting platform's secret manager, injected as an env var to the backend only — never present in any frontend build or client bundle.
- **Open source:** repo public from the start; MIT license added end of Phase 0; a short CONTRIBUTING note can be added later if external interest materializes (not a priority — this is a portfolio piece, not seeking contributors).

---

## 14. Cost & latency budget

Envelope to sanity-check before build; the §5.5 trace log replaces these estimates with measured numbers once Phase 3–5 are live.

**Current pricing** (per million tokens, from Anthropic docs as of mid-2026 — re-verify at Phase 3):

| Model | Role here | Input | Output |
|---|---|---|---|
| `claude-opus-4-8` | plan, per-beat scene gen, vision critique | $5 | $25 |
| `claude-sonnet-5` | cost fallback for scene gen if needed | $3 ($2 intro through Aug 2026) | $15 ($10 intro) |
| `claude-haiku-4-5` | auto-fix repair | $1 | $5 |

Prompt caching: cache reads ≈ 0.1× input price, writes ≈ 1.25× — with the stable-prefix prompt layout (§1), all but the first per-beat call read the shared system prompt + few-shots from cache.

**Order-of-magnitude per-lesson estimate** (medium preset, ~7 beats, everything passing first try): 1 plan call (~2K in / ~2K out) + 7 beat calls (~5K in each, mostly cache-read after the first / ~1.5K out each) + 7 vision critiques (~2K in each incl. screenshot / ~0.3K out each). Output dominates: roughly 15K output tokens ≈ **$0.40 on Opus 4.8**, with cached input adding little. With realistic retry rates, budget **~$0.50–1.50 per lesson**; the retry ceilings (§5.4) cap the worst case at roughly 2–3× the clean-run cost. Entirely sustainable for a demo/portfolio app at tens of lessons/day; the rate limiter is what protects against someone scripting hundreds.

- **Latency target:** outline + beat 1 ready within a few seconds of submit (this is the number that matters for demo feel — everything after beat 1 happens while the learner is reading/interacting, so it's hidden by the self-paced format per D8/D9's design intent). The plan call streams; beat-1 generation starts as soon as the outline's first beat is parseable.
- **Mitigation levers if measured costs run high, in order:** tighten retry ceilings (cheapest); move per-beat scene generation from Opus to `claude-sonnet-5` (§1 already provisions this); shrink the few-shot library per primitive (hurts quality — last resort).

---

## 15. Risk register

| Risk (from README) | Mitigation in this plan |
|---|---|
| Animation correctness & quality is make-or-break | §5.2 full validation pipeline + §3 graceful degradation — a lesson can never ship a broken or blank beat |
| Latency & API cost | §5.2 sequential JIT generation, §14 budget guardrails, §1 SSE so beat 1 latency is what's felt |
| Scope creep from D3 + D4 | §10 explicitly cuts engines/escape-hatch/richer manipulables to Phase 2+ |
| Adjacency to prior work (Auto Data Analyst) | Not an engineering risk — a positioning note for the eventual write-up/demo script, not addressed by this plan |
| Big players circling (Google Learn About) | Same — positioning, not architecture |
| Param sprawl (D6) | §6.1 topic-only is one click; optional params collapsed by default |
| **New: arbitrary code execution surface (D1+D2)** | §7 sandbox/CSP/denylist/timeout defenses |
| **New: single-instance in-memory state is a scaling ceiling** | Explicitly accepted for MVP (§5.3); documented Redis swap path if ever needed |
| **New: headless Chromium memory pressure on a small instance** | §5.2 single browser + semaphore; §13 sizes the instance for it |
| **New: prompt/few-shot drift breaks the scene contract** | §6.2 freezes the contract in Phase 1, before any prompt is written; §5.5 trace log catches quality regressions per primitive |

---

## 16. Demo-readiness checklist

Everything below should be true before calling MVP "done" for recruiter-facing use:

- [ ] Topic-only submission works great with zero configuration, on a wide range of topic types (technical, non-technical, abstract, concrete).
- [ ] No broken/blank beats observed across a manual test set of ≥15 varied topics.
- [ ] First beat renders within a few seconds of submit.
- [ ] Narration toggle, manipulables, and back-navigation all work.
- [ ] App survives adversarial input (empty topic, huge topic, prompt-injection attempts, rapid repeated submits) without crashing or leaking errors to the UI.
- [ ] Deployed at a stable public URL, backend and frontend both green in CI.
- [ ] README + this plan are current with whatever actually got built (update both if reality diverges).
- [ ] Short demo GIF/video captured for the resume/portfolio link.

---

## 17. Open questions to revisit

Nothing blocking — these are fine to leave open until they matter:

- Whether to buy a custom domain before the internship application round (§1) — pure polish, not functional.
- Whether Phase 11 stretch work should prioritize the learning-outcome eval or a third rendering engine — decide based on how Phase 0–10 actually goes and which is more impressive to demo live.
- Whether the generation-quality regression suite's fixed topic set needs to grow — revisit once Phase 5 is live and real failure patterns are visible.
- Whether per-beat scene generation stays on `claude-opus-4-8` or moves to `claude-sonnet-5` — decide from measured quality + cost in the §5.5 trace log, not up front.

---

## 18. Revision history

**v2 (2026-07-19)** — full revision pass before implementation. Changes from v1:

- *API modernization:* plan-stage JSON now uses the Anthropic API's native structured outputs (schema-enforced; parse-retry code deleted from the design); prompt caching designed into the per-beat prompt layout from day one; concrete model roles pinned (`claude-opus-4-8` / `claude-sonnet-5` fallback / `claude-haiku-4-5` for repairs) with current pricing in §14.
- *New engineering commitments:* scene-code runtime contract is now a frozen Phase-1 deliverable (§6.2); screenshot timing defined via the `ready` signal (§5.2); single-browser + semaphore policy for Playwright (§5.2); generation trace log (§5.5); mock generation mode (§1, Phase 3); SSE keepalives, CORS policy, and Chromium-aware instance sizing (§13); concrete MVP accessibility scope (§6.4).
- *Cost model:* replaced the qualitative envelope with an order-of-magnitude per-lesson estimate (~$0.50–1.50) from current pricing.
- *Risk register:* added Chromium memory pressure and scene-contract drift.

**v1 (2026-07-19)** — initial plan.
