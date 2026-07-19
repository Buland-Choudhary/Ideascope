# Ideascope

**See any idea, one click at a time.**

Ideascope is an AI web app that turns any **topic** (plus optional parameters like **duration**) into a **self-paced, animation-heavy, interactive micro-lesson**. The lesson plays live in the browser and advances **one beat at a time on the user's click**. The goal is to make small, hard-to-grasp concepts genuinely *click* — through motion and interaction rather than walls of text.

> This is the main description for the project. It's a distilled synthesis of the living Project Charter (currently v0.6). When a decision changes in the charter, mirror it here.

The full step-by-step build plan lives in [`docs/PLAN.md`](docs/PLAN.md) — start there before writing code.

---

## What it is — and what it isn't

**It is** a generator of short, interactive, animated explainers that render live in the browser. The learner controls the pace, and the animation *illustrates the idea* itself.

**It is NOT** an explainer-*video* generator (no MP4, no timeline export), a chat tutor, a static slide deck, or decorative animation for its own sake.

## Why this project

Ideascope is a **portfolio flagship** aimed at landing a Summer-2027 ML internship. That framing drives the requirements:

- **Semester-long scope** — polished, deployed, and demoable, not a weekend AI wrapper.
- **Impressive and clearly non-generic.**
- **Demoable on any topic a recruiter types**, live, with **no external dataset** required.

## Core principles (non-negotiables)

1. **Interactive, live in the browser — never an exported video.**
2. **Self-paced.** Advances on the user's click. No autoplay timeline, no scroll-driven playback.
3. **Animation illustrates the concept** — Manim-quality *intent*, delivered interactively.
4. **Correctness first.** A wrong-but-pretty animation is a failure.
5. **Topic-only must be great.** Optional parameters are progressive enhancement, never required.
6. **Grounded in learning science.** Lessons follow multimedia-learning principles (segmenting, signaling, coherence, spatial contiguity), not just aesthetics.

## Positioning — the pocket we're claiming

Ideascope sits in a barely-built niche: **AI-generated, self-paced, click-to-advance, concept-illustrating animation rendered live in the browser** — essentially "AI-generated explorable explanations."

| Neighbor | What they do | Why we're different |
|---|---|---|
| AI explainer-video makers (Synthesia, Animaker) | prompt → narrated MP4 | passive video, decorative visuals |
| AI Manim generators (TheoremExplainAgent, Manimator) | prompt → concept animation | still linear video, watch-only |
| AI tutors (Google Learn About, LearnLM) | conversational + quizzes | chat, not *generated* animation |
| AI interactive courseware (research prototypes) | generate interactive HTML lessons | teacher-authoring, pre-product |

## Locked design decisions (core spec D1–D12, complete)

| # | Decision | Resolution |
|---|---|---|
| D1 | Topic domain | **General** — any topic |
| D2 | Animation generation | **LLM writes live code** |
| D3 | Interactivity | **Both** — click-to-advance *and* manipulables (sliders/steppers) |
| D4 | Runtime | **Multi-engine stage hosted in React** (p5.js/canvas default; SVG+DOM+KaTeX; GSAP/Framer Motion; sandboxed escape hatch). React shell is hand-written. |
| D5 | Narration | **Optional toggle** — text always present; TTS on/off; silent mode shows text |
| D6 | Input params | **Rich optional set**, strong defaults; topic-only works great |
| D7 | Validation | **Layered** — render/auto-fix → vision self-critique vs. intent (core gate) → learner "regenerate" (optional, not a gate) |
| D8 | Generation | **Two-stage pipeline** — plan whole outline → separate per-beat scene calls |
| D9 | Persistence | **Ephemeral** — generate & go; shareable links are an easy future add |
| D10 | Model | **Claude** for planning, scene code, and vision self-critique (Anthropic API) |
| D11 | Duration | **Short / medium / long presets** → target beat bands (~3–5 / 6–9 / 10–14) |
| D12 | Pedagogy | **Baked in (core)** — learning-outcome eval is an optional stretch |

### Design implications

- **Any topic + generated code means correctness is the central challenge.** D7 is the primary defense.
- Generated code targets a **vetted vocabulary of reusable animation primitives**: timeline, plot/graph, geometric transform, process/flow, comparison, part-to-whole, simulation.
- **Pedagogy is encoded in the generation prompts and pattern library** (Mayer's multimedia-learning principles). Self-paced click-to-advance already satisfies *segmenting*.
- **Multi-engine, manipulables, and eval are phased.** The MVP leans on one primary engine plus SVG; other engines, the escape hatch, richer manipulables, and the eval come later.

## System shape

**Frontend (React — the shell):** the lesson player — beat sequence, click-to-advance state machine, manipulable controls, narration toggle, layout, and the multi-engine scene renderer.

**Lesson spec (the contract):** structured JSON — an ordered list of **beats**. Each beat = `{ intent, narration text, optional manipulables (param + range + default), scene (engine + code) }`. Duration preset maps to target beat count.

**Scene renderer (multi-engine):** dispatches each scene to p5.js/canvas, SVG+DOM+KaTeX, or a motion library; manipulable values flow in as reactive params; a sandboxed escape hatch handles free-form code.

**Backend (FastAPI) — Claude-powered generation pipeline:**

1. **Plan call** — topic + params + pedagogy rules → whole-lesson outline (beats with intent, narration, engine, manipulables).
2. **Per-beat calls** (separate, parallel / just-in-time) — each generates one beat's scene code.
3. **Validate per beat** — execute/render check + auto-fix → Claude vision self-critique vs. intent → bounded retries.
4. **Just-in-time delivery** — outline + beat 1 first; later beats generated and validated in the background while the learner progresses.

Plus a **TTS service** for narration audio on demand.

**Initial optional params (D6):** difficulty/expertise level, assumed prior knowledge, visual style/tone, and (later) language. Only **topic + duration** are required.

## Working assumptions (correct if wrong)

- Backend framework: **FastAPI** (confirmed direction; not yet formally locked).
- Audience: technical self-learners and evaluating recruiters, but must handle non-technical topics gracefully.

## Current status & next step

The **core spec (D1–D12) is complete**, and the project is named **Ideascope** (chosen over "Primer" and "Unfurl," both already used by close AI-learning competitors).

The **build plan (`docs/PLAN.md`) is now drafted**, resolving the remaining open decisions below. It is the next thing to review before implementation starts.

Remaining open decisions (resolved in the plan, revisit if circumstances change):

- **Name availability** — `ideascope.io` is taken (unrelated startup-idea-validation tool); a `.dev`/`.app`/`getideascope.com`-style domain is recommended instead. GitHub namespace is fine under the personal account.
- **Deployment + open-source plan** — see `docs/PLAN.md` §13.
- **MVP boundary + roadmap** — see `docs/PLAN.md` §10–11.

## Key risks / watch-items

- **Animation correctness & quality is make-or-break** — D7 is the main defense.
- **Latency & API cost** — vision-critique plus per-beat calls add both; mitigated by just-in-time/background generation and the self-paced format.
- **Scope creep from D3 + D4** — phase the manipulables and multi-engine work.
- **Adjacency to prior work** (the Auto Data Analyst loop) — the animation/pedagogy layer must be the clearly-new hard part.
- **Big players circling** (Google Learn About / Learn Your Way) — frame as "I can build what they invest in."
- **Param sprawl (D6)** — keep the topic-only path frictionless.
