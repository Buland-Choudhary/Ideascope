# Ideascope

**See any idea, one click at a time.**

Ideascope is an AI web app that turns any **topic** (plus optional parameters like **duration**) into a **self-paced, animation-heavy, interactive micro-lesson**. The lesson plays live in the browser and advances **one beat at a time on the user's click**. The goal is to make small, hard-to-grasp concepts genuinely *click* — through motion and interaction rather than walls of text.

> This is the main description for the project. It's a distilled synthesis of the living Project Charter (currently v0.6). When a decision changes in the charter, mirror it here.

The full step-by-step build plan lives in [`docs/PLAN.md`](docs/PLAN.md) — start there before writing code.

## Repository layout

```
Ideascope/
├── docs/PLAN.md        # the phased implementation plan (source of truth for how/when)
├── frontend/           # React + TypeScript + Vite lesson player (see frontend/README.md)
├── backend/            # FastAPI generation service (see backend/README.md)
└── .github/workflows/  # CI: lint, typecheck, test, build on every PR
```

## Quickstart (local dev)

Two terminals — backend and frontend:

```bash
# terminal 1 — backend (http://localhost:8000)
cd backend && uv sync && uv run uvicorn app.main:app --reload

# terminal 2 — frontend (http://localhost:5173)
cd frontend && npm install && npm run dev
```

The frontend calls the backend's `/api/health` on load and shows the connection
status. Per-app details, checks, and configuration are in
[`frontend/README.md`](frontend/README.md) and [`backend/README.md`](backend/README.md).

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

The **build plan (`docs/PLAN.md`) is drafted** (v2), resolving the remaining open decisions below. Progress:

- **Phase 0 (Foundations) — done.** Repo scaffolded with a building React/Vite frontend and FastAPI backend, CI (lint + typecheck + test + build for both), MIT license. Hello-world loop verified end-to-end in a real browser.
- **Phase 1 (Lesson spec + scene contract) — done.** Pydantic lesson-spec models + hand-mirrored TS types, the scene-code runtime contract frozen in [`docs/SCENE_CONTRACT.md`](docs/SCENE_CONTRACT.md), and two hand-authored fixture lessons (canvas + SVG) that validate against the schema.
- **Phase 2 (Static player shell) — done.** The lesson player, click-to-advance state machine, and both engine runtimes (sandboxed-iframe scene renderer implementing the contract) run the fixtures end-to-end in the browser — click-to-advance, keyboard nav, and manipulables all work. No backend generation yet.
- **Phase 3 (Backend skeleton + plan call) — done.** `POST /api/lessons`, the Claude plan-stage call (structured outputs), mock generation mode, and the generation trace log. Both flows verified end-to-end: mock (topic form → backend → player) in a real browser, and the **live Claude plan call spot-checked against 10 varied real topics — 10/10 succeeded, all in-band on the first pass**. See [`backend/README.md`](backend/README.md) for API key setup.
- **Phase 4 (Per-beat scene-code generation) — done.** Per-beat Claude calls targeting the frozen scene contract, one few-shot per animation primitive, contract/denylist retries, and a transient-API-error retry path. Fully verified live: a 5-topic spot-check produced **23/23 syntactically valid generated scenes** across all 7 primitives, and a real end-to-end browser run generated and played a genuinely new topic ("how tides work") with all 5 beats rendering error-free — the first phase where a real user-typed topic produces a working animation. See `docs/PLAN.md` §11 for the full account, including a real observability bug the live runs surfaced and fixed (the generation trace log had no default handler).
- **Phase 5 (Validation pipeline) — done.** Every real-mode beat is now render-checked in a real sandboxed headless-Chromium instance, auto-fixed on `claude-haiku-4-5` if it fails to render, vision-critiqued on `claude-opus-4-8` (a screenshot judged against the beat's intent), regenerated once with the critique feedback if it doesn't pass, and gracefully degraded to a deterministic (non-LLM) text fallback if it still fails — so no broken beat can reach a learner. 58 tests pass (22 new), all free (fake-client or real-browser-only, no API cost). **Live-verified against the real API**: a full 5-beat lesson generated, rendered, and passed critique end-to-end with zero degraded beats, and two real critique-triggered regenerations fired and succeeded exactly as designed. See `docs/PLAN.md` §11 for the full account.
- **Phase 6 (JIT delivery) — done.** `POST /api/lessons` now returns instantly with a lesson id and generates in the background; the frontend subscribes to a Server-Sent Events stream and renders the outline, then each beat, as they arrive — no more waiting for the whole lesson before seeing anything. Navigating to a beat that hasn't streamed in yet shows a non-blocking "still preparing this part" placeholder instead of an error. 72 backend + 20 frontend tests pass, all free (mock mode replays a fixture through the identical event sequence real generation uses). **Verified live against real `uvicorn`+`vite` dev servers** — a real browser `EventSource` connection, submitting a topic, watching the outline and first beat render inside the actual sandboxed iframe, navigating to the end. That live run caught and fixed a real bug unit tests missed (a one-frame NaN flash on a manipulable slider when switching beats — see `docs/PLAN.md` §11 for the full account).

- **Phase 7 (Manipulables end-to-end) — in progress.** Most of the wiring already existed from earlier phases; what closed this round was the validation pipeline's vision critique now also grading the "after interaction" screenshot (already captured since Phase 5, but not yet fed to Claude) — so a beat only passes if its manipulable visibly and correctly changes something, not just if the static frame looks right. 75 tests pass (3 new), zero API cost. **Blocked on live verification**: the plan's exit criterion needs 2+ real generated lessons confirmed working end-to-end, and the Anthropic account is still out of credit (confirmed directly — same billing error as Phase 5's close-out). Everything else for this phase is done; resumes as soon as credits are available.
- **Phase 8 (Narration) — done.** A narration toggle (off by default) drives the browser's native `SpeechSynthesis` API — no backend TTS call, so this is free — while narration text stays visible regardless of toggle state. Switching beats cancels any speech in progress first, so navigating quickly never overlaps two beats' narration. 32 frontend tests pass (12 new), zero API cost. **Live-verified against real `uvicorn`+`vite` dev servers and real headless Chromium**: confirmed Chromium's `SpeechSynthesis` works headless, then confirmed in the actual running app that the toggle starts off, turning it on speaks the exact current-beat narration, navigating speaks the next beat, and turning it off silences further navigation while the text stays on screen.
- **Phase 9 (Polish & hardening) — done.** Added the one missing security-checklist item (IP-based rate limiting on lesson creation, `slowapi`) and fixed real bugs live testing found: a whitespace-only topic used to slip past validation and start generating for an empty string; a horizontal-overflow layout bug on narrow phones (a classic flexbox min-width trap); and — the standout catch — rapid-fire clicking the Generate button could fire multiple simultaneous lesson requests, because disabling the button relies on a React re-render that doesn't win a race against several clicks in the same instant. Fixed with a synchronous guard, verified live (5 clicks → 1 request, was 5). Also closed a Phase-2-deferred performance item: p5 (~1 MB) now loads on demand instead of bloating every learner's download, cutting the main bundle from 1,286 KB to 222 KB — verified live that SVG-only lessons never fetch it at all and canvas lessons fetch it exactly once, cached. 79 backend + 33 frontend tests pass (14 new), zero API cost — everything above verified against real headless Chromium, not just imagined.
- **Phase 10 (Deployment) — live.** Deployed incrementally instead of waiting for full feature completeness — backend on Render's free tier, frontend on Netlify (`render.yaml` / `frontend/netlify.toml`). **Deliberate trade-off:** the deployed backend runs real generation with `IDEASCOPE_SKIP_VALIDATION=true` — beats ship straight from Claude with no render-check/auto-fix/vision-critique, to avoid both the Chromium hosting requirement and the critique API spend given a small credit budget. This knowingly trades away part of README principle 4 ("correctness first") for now; the client still catches genuine render crashes gracefully (no blank beats), just without server-side repair or a pedagogy gate. Full detail and the exact revert path in `docs/PLAN.md`'s Phase 10 entry — revisit before calling this recruiter-ready.
- **Post-deploy iteration — done.** Working against the live app now. Fixed a real reported bug: the "Done" button on a lesson's last beat was disabled and did nothing even when it wasn't — now it actually ends the lesson. Added GSAP (`ctx.gsap`, ~70 KB) to the scene contract as a non-breaking extension available in both engines, so generated scenes get real eased animation (`"back.out"`, `"elastic.out"`, etc.) instead of hand-rolled sine-wave interpolation — live-verified a real tween animating inside the sandboxed iframe. Found and fixed a second pre-existing bug along the way: `ctx.katex` was promised in the prompt and contract but never actually implemented in either runtime, so any beat reaching for math rendering would have crashed — removed until it's done properly (needs embedded fonts under the sandboxed CSP). Switched the default beat-generation model from `claude-opus-4-8` to `claude-sonnet-5` (~40% cheaper — beat calls, not the plan call, dominate per-lesson spend) given the small credit budget and no auto-fix/critique safety net while validation is skipped. 92 backend + 35 frontend tests pass (13 new), zero API cost — verified against real headless Chromium throughout.
- **Post-deploy iteration round 2 — done.** Four issues raised against the live app. (1) **Latency**: beats now generate several at a time (`beat_generation_concurrency`, default 3) instead of strictly one after another — cuts wall-clock lesson time by roughly that factor at zero extra cost, since it's the same API calls just no longer serialized. Automatically falls back to one-at-a-time whenever the full Playwright validation pipeline is active, since Playwright's sync API requires every call to come from one consistent thread — real concurrency, and separately even a careless single-worker `ThreadPoolExecutor`, both broke that and were caught and fixed. (2) **Lightweight code review**: a cheap text-only review (`claude-haiku-4-5`) reads each beat's generated source and flags obviously wrong or broken code — missing `ctx.ready()`, an ignored manipulable, hardcoded pixel sizes — with one feedback-guided regeneration retry, standing in for the heavy render/critique pipeline this deployment already runs without. (3) **Model picker + cost transparency**: a dropdown lets a learner pick which model generates a lesson (validated server-side against a 3-model allowlist), and every real Anthropic call's token usage is now tracked and shown as a `$X.XXXX · N tokens` badge (hover for a per-stage breakdown) once generation completes. (4) **Visual quality**: the beat-generation prompt's visual guidance used to be one throwaway sentence; replaced with a concrete design system (fixed indigo/amber palette, soft shadows, rounded corners, a real font stack, generous margins) and every few-shot example rewritten to demonstrate it — verified by actually rendering all 7 through the real p5/GSAP runtime and screenshotting the result, not just checking the JS parses. 105 backend + 42 frontend tests pass (19 new), ruff/mypy/eslint/tsc clean. **Live-verified against the real Anthropic API**: one real lesson exercised all four changes together — beats completed out of order (concurrency confirmed working), one beat failed its code review and was correctly regenerated then passed on re-review (review loop confirmed working), the model override applied to every plan/beat/review call, and the on-screen cost report exactly matched the server trace log: 18,579 input / 15,316 output tokens across 13 real API calls, **$0.0952**.
- **Post-deploy iteration round 3 — done.** Three requested changes. (1) **Per-lesson color palette**: lessons used to render against one fixed indigo/amber palette regardless of topic; the plan stage now picks a `Palette` fit to the topic's mood, carried through as a new host-injected `ctx.palette` scene-runtime field (same pattern as `ctx.gsap`) rather than baked into generated code — so the model never risks mistyping a hex color and the beat prompt stays cache-friendly across lessons. (2) **Wider model picker**: added Claude Fable 5 and Claude Opus 5 to the allowlist — deliberately still excluding Opus 4.7/4.6 and Sonnet 4.6, which aren't confirmed to support the structured outputs every generation call here depends on. The cost-conscious defaults (`skip_validation=true`, `claude-sonnet-5` beat model) are unchanged. (3) **Mobile fixes**: the topic form's button row and the player header could overflow narrow viewports (worse once the model picker's labels got longer) — both now wrap gracefully below the `sm:` breakpoint. 115 backend + 42 frontend tests pass (10 new), ruff/mypy/eslint/tsc clean. **Live-verified against the real Anthropic API and real dev servers**: three plan-only calls for different-mood topics came back distinctly on-theme (rainforest → greens, jet engine → amber/sky-blue, deep space → near-black/cool-blue); a full real 8-beat lesson ("a coral reef ecosystem") rendered its LLM-chosen ocean palette correctly through the real sandboxed runtime, screenshot-confirmed; the expanded model list was confirmed via a real `GET /api/models` call; the mobile layout showed no horizontal overflow at a real 375×812 viewport. Total spend this round: **~$0.61**.

Next up is finishing Phase 7's live verification once Anthropic credits are available, plus revisiting the skipped-validation trade-off before calling the deployment recruiter-ready.

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
