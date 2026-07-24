"""Graceful degradation (docs/PLAN.md §5.2 step 5): when a beat exhausts every
retry, replace its scene with a plain, reliably-rendering text display rather
than showing something broken or blank.

Deliberately **not** another LLM call: a degraded beat is the last line of
defense, and asking an LLM to generate the fallback would let the fallback
itself fail. This is a fixed Python template — "auto-generated" by code, not
by a model — guaranteed to satisfy the scene contract every time.
"""

import json
import textwrap

_LINE_HEIGHT = 34
_MAX_CHARS_PER_LINE = 42


def build_fallback_scene(text: str) -> str:
    """An SVG-engine scene that displays ``text`` centered and word-wrapped."""
    lines = textwrap.wrap(text, width=_MAX_CHARS_PER_LINE) or [text]
    lines_json = json.dumps(lines)
    return f"""\
export default function createScene(ctx) {{
  const NS = "http://www.w3.org/2000/svg";
  const lines = {lines_json};
  const lineHeight = {_LINE_HEIGHT};
  const startY = ctx.height / 2 - ((lines.length - 1) * lineHeight) / 2;
  const t = document.createElementNS(NS, "text");
  t.setAttribute("x", ctx.width / 2);
  t.setAttribute("y", startY);
  t.setAttribute("text-anchor", "middle");
  t.setAttribute("font-size", "20");
  t.setAttribute("font-family", "system-ui, sans-serif");
  t.setAttribute("fill", "#1f2937");
  lines.forEach((line, i) => {{
    const tspan = document.createElementNS(NS, "tspan");
    tspan.setAttribute("x", ctx.width / 2);
    tspan.setAttribute("dy", i === 0 ? 0 : lineHeight);
    tspan.textContent = line;
    t.appendChild(tspan);
  }});
  ctx.svg.appendChild(t);
  ctx.ready();
  return {{}};
}}
"""
