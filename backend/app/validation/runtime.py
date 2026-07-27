"""Builds the HTML documents the validator loads in a real browser.

This is a Python port of ``frontend/src/engines/sceneRuntime.ts`` — the same
sandboxed-iframe contract (docs/SCENE_CONTRACT.md), the same CSP, the same
postMessage bridge — so "what the validator checked" and "what the learner
sees" are the same execution boundary (docs/PLAN.md §2). Keep this in sync
with the frontend module when either changes; the two exist independently
because the frontend and backend are separately deployed services with no
shared build step (same rationale as the duplicated denylist — see
app/generation/beat.py).

**One deliberate divergence:** the frontend runtime has a 3-second safety net
that fires `ctx.ready()` even if the scene never calls it, so a buggy scene
doesn't leave a learner staring at "Preparing scene…" forever. The validator
omits that fallback — if a scene never signals ready or throws within the
validation timeout, that hang *is* the failure signal we want to catch and
route to auto-fix. Being lenient here would let broken scenes silently pass.
"""

import json
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent / "vendor"
_P5_SOURCE = (_VENDOR_DIR / "p5.min.js").read_text()
_GSAP_SOURCE = (_VENDOR_DIR / "gsap.min.js").read_text()

READY = "ideascope:ready"
ERROR = "ideascope:error"
UPDATE_PARAM = "ideascope:updateParam"

# Same shape as frontend/src/engines/sceneRuntime.ts's RUNTIME, minus the
# ready-fallback timer (see module docstring).
_SCENE_RUNTIME_JS = f"""
const post = (msg) => parent.postMessage(msg, "*");
let controller = null;
let readyFired = false;
const fireReady = () => {{ if (!readyFired) {{ readyFired = true; post({{ type: "{READY}" }}); }} }};
const fail = (message) => post({{ type: "{ERROR}", message: String(message) }});

const cfg = JSON.parse(document.getElementById("ideascope-cfg").textContent);
const params = cfg.params || {{}};
const stage = document.getElementById("stage");
const width = window.innerWidth || 640;
const height = window.innerHeight || 400;

const ctx = {{
  engine: cfg.engine,
  width: width,
  height: height,
  params: params,
  reducedMotion: !!cfg.reducedMotion,
  ready: fireReady,
  gsap: window.gsap,
}};

window.addEventListener("message", (ev) => {{
  const m = ev.data;
  if (!m || typeof m !== "object") return;
  if (m.type === "{UPDATE_PARAM}" && controller && typeof controller.onParamChange === "function") {{
    params[m.param] = m.value;
    try {{ controller.onParamChange(m.param, m.value); }}
    catch (e) {{ fail("onParamChange: " + (e && e.message)); }}
  }}
}});

async function boot() {{
  let mod;
  try {{
    const blob = new Blob([window.__SCENE_CODE__], {{ type: "text/javascript" }});
    const url = URL.createObjectURL(blob);
    mod = await import(url);
    URL.revokeObjectURL(url);
  }} catch (e) {{ fail("scene import failed: " + (e && e.message)); return; }}

  const createScene = mod && mod.default;
  if (typeof createScene !== "function") {{ fail("scene has no default-exported function"); return; }}

  try {{
    if (cfg.engine === "canvas") {{
      if (!window.p5) {{ fail("p5 not available"); return; }}
      const sketch = (p) => {{
        p.setup = () => {{
          p.createCanvas(width, height);
          ctx.p5 = p;
          controller = createScene(ctx);
          if (controller && typeof controller.setup === "function") controller.setup(p);
        }};
        p.draw = () => {{
          if (controller && typeof controller.draw === "function") controller.draw(p);
        }};
      }};
      new window.p5(sketch, stage);
    }} else {{
      const NS = "http://www.w3.org/2000/svg";
      const svg = document.createElementNS(NS, "svg");
      svg.setAttribute("width", String(width));
      svg.setAttribute("height", String(height));
      svg.setAttribute("viewBox", "0 0 " + width + " " + height);
      stage.appendChild(svg);
      ctx.svg = svg;
      controller = createScene(ctx);
      if (controller && typeof controller.render === "function") controller.render();
    }}
  }} catch (e) {{ fail("scene setup failed: " + (e && e.message)); return; }}
}}

boot();
"""


def _escape_for_script(s: str) -> str:
    """Neutralize a literal ``</`` so it can't terminate the host <script> tag."""
    return s.replace("</", "<\\/")


def _escape_for_html_attr(s: str) -> str:
    return s.replace("&", "&amp;").replace('"', "&quot;")


def build_scene_srcdoc(
    *, engine: str, code: str, params: dict[str, object], reduced_motion: bool = False
) -> str:
    """The sandboxed document — identical shape to the frontend's srcdoc."""
    cfg = json.dumps({"engine": engine, "params": params, "reducedMotion": reduced_motion})
    scene_code_literal = json.dumps(code)
    p5_tag = f"<script>{_P5_SOURCE}</script>" if engine == "canvas" else ""
    gsap_tag = f"<script>{_GSAP_SOURCE}</script>"
    csp = (
        "default-src 'none'; script-src 'unsafe-inline' blob:; "
        "style-src 'unsafe-inline'; img-src data:;"
    )
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{csp}">
<style>html,body{{margin:0;padding:0;height:100%;overflow:hidden;background:#fff}}#stage{{width:100vw;height:100vh}}</style>
{p5_tag}
{gsap_tag}
</head>
<body>
<div id="stage"></div>
<script type="application/json" id="ideascope-cfg">{_escape_for_script(cfg)}</script>
<script>window.__SCENE_CODE__ = {_escape_for_script(scene_code_literal)};</script>
<script type="module">{_SCENE_RUNTIME_JS}</script>
</body>
</html>"""


def build_harness_html(srcdoc: str) -> str:
    """The outer page: hosts the sandboxed iframe, records the last status
    message, and exposes a helper to simulate a manipulable interaction.
    """
    escaped = _escape_for_html_attr(srcdoc)
    return f"""<!doctype html>
<html>
<body style="margin:0">
<iframe id="scene" sandbox="allow-scripts" style="width:800px;height:500px;border:0" srcdoc="{escaped}"></iframe>
<script>
window.__ideascope_status__ = null;
window.addEventListener("message", (ev) => {{
  const m = ev.data;
  if (m && typeof m === "object" && (m.type === "{READY}" || m.type === "{ERROR}")) {{
    window.__ideascope_status__ = m;
  }}
}});
window.__ideascope_update_param__ = (param, value) => {{
  window.__ideascope_status__ = null;
  document.getElementById("scene").contentWindow.postMessage(
    {{ type: "{UPDATE_PARAM}", param: param, value: value }}, "*"
  );
}};
</script>
</body>
</html>"""
