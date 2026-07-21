/**
 * Builds the sandboxed-iframe document that runs one scene.
 *
 * This is the host side of the frozen scene contract (docs/SCENE_CONTRACT.md).
 * The returned HTML is used as an `<iframe sandbox="allow-scripts">` srcdoc
 * (docs/PLAN.md §7): no same-origin access, a strict CSP that blocks all network,
 * and `postMessage` as the only channel. The runtime owns all engine
 * bootstrapping (p5 instance + draw loop, or the `<svg>` root) and calls the
 * scene's `export default createScene(ctx)` factory.
 */

import p5Source from "p5/lib/p5.min.js?raw";

import type { Engine, ParamValue } from "../types/lesson";

export interface SceneDocumentOptions {
  engine: Engine;
  code: string;
  params: Record<string, ParamValue>;
  reducedMotion: boolean;
}

/** Message types on the host↔iframe bridge. */
export const READY = "ideascope:ready";
export const ERROR = "ideascope:error";
export const UPDATE_PARAM = "ideascope:updateParam";

// The runtime script that executes inside the iframe. Reads the embedded config
// and scene code, wires the contract, and reports status over postMessage.
const RUNTIME = `
const post = (msg) => parent.postMessage(msg, "*");
let controller = null;
let readyFired = false;
const fireReady = () => { if (!readyFired) { readyFired = true; post({ type: "${READY}" }); } };
const fail = (message) => post({ type: "${ERROR}", message: String(message) });

const cfg = JSON.parse(document.getElementById("ideascope-cfg").textContent);
const params = cfg.params || {};
const stage = document.getElementById("stage");
const width = window.innerWidth || 640;
const height = window.innerHeight || 400;

const ctx = {
  engine: cfg.engine,
  width: width,
  height: height,
  params: params,
  reducedMotion: !!cfg.reducedMotion,
  ready: fireReady,
};

window.addEventListener("message", (ev) => {
  const m = ev.data;
  if (!m || typeof m !== "object") return;
  if (m.type === "${UPDATE_PARAM}" && controller && typeof controller.onParamChange === "function") {
    params[m.param] = m.value;
    try { controller.onParamChange(m.param, m.value); }
    catch (e) { fail("onParamChange: " + (e && e.message)); }
  }
});

async function boot() {
  let mod;
  try {
    const blob = new Blob([window.__SCENE_CODE__], { type: "text/javascript" });
    const url = URL.createObjectURL(blob);
    mod = await import(url);
    URL.revokeObjectURL(url);
  } catch (e) { fail("scene import failed: " + (e && e.message)); return; }

  const createScene = mod && mod.default;
  if (typeof createScene !== "function") { fail("scene has no default-exported function"); return; }

  try {
    if (cfg.engine === "canvas") {
      if (!window.p5) { fail("p5 not available"); return; }
      const sketch = (p) => {
        p.setup = () => {
          p.createCanvas(width, height);
          ctx.p5 = p;
          controller = createScene(ctx);
          if (controller && typeof controller.setup === "function") controller.setup(p);
        };
        p.draw = () => {
          if (controller && typeof controller.draw === "function") controller.draw(p);
        };
      };
      new window.p5(sketch, stage);
    } else {
      const NS = "http://www.w3.org/2000/svg";
      const svg = document.createElementNS(NS, "svg");
      svg.setAttribute("width", String(width));
      svg.setAttribute("height", String(height));
      svg.setAttribute("viewBox", "0 0 " + width + " " + height);
      stage.appendChild(svg);
      ctx.svg = svg;
      controller = createScene(ctx);
      if (controller && typeof controller.render === "function") controller.render();
    }
  } catch (e) { fail("scene setup failed: " + (e && e.message)); return; }

  // Safety net (docs/SCENE_CONTRACT.md §5): if the scene never calls ctx.ready(),
  // treat it as ready after a timeout so preview/validation can't hang.
  setTimeout(fireReady, 3000);
}

boot();
`;

/**
 * Neutralize a literal `</` (e.g. `</script>`) inside an embedded string so it
 * can't terminate the host `<script>` tag early. `<\/` decodes back to `</`.
 */
function escapeForScript(s: string): string {
  return s.replace(/<\//g, "<\\/");
}

export function buildSceneDocument(opts: SceneDocumentOptions): string {
  const cfg = JSON.stringify({
    engine: opts.engine,
    params: opts.params,
    reducedMotion: opts.reducedMotion,
  });
  const sceneCodeLiteral = JSON.stringify(opts.code);
  const p5Tag = opts.engine === "canvas" ? `<script>${p5Source}</script>` : "";

  const csp =
    "default-src 'none'; script-src 'unsafe-inline' blob:; style-src 'unsafe-inline'; img-src data:;";

  return `<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="${csp}">
<style>html,body{margin:0;padding:0;height:100%;overflow:hidden;background:#fff}#stage{width:100vw;height:100vh}</style>
${p5Tag}
</head>
<body>
<div id="stage"></div>
<script type="application/json" id="ideascope-cfg">${escapeForScript(cfg)}</script>
<script>window.__SCENE_CODE__ = ${escapeForScript(sceneCodeLiteral)};</script>
<script type="module">${RUNTIME}</script>
</body>
</html>`;
}
