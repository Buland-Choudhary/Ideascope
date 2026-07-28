"""Sanity checks on the beat-generation prompt library (docs/PLAN.md §5.2):
every per-primitive few-shot is itself syntactically valid JavaScript, since
it's shown to the model as the pattern to match — a broken example would
actively teach bad code. Uses `node --check`, the same technique
`scripts/build_fixtures.py` and the spot-check scripts use for generated code.
"""

import subprocess
import tempfile
from pathlib import Path

import pytest

from app.generation.beat_prompts import _FEWSHOTS, BEAT_SYSTEM_PROMPT
from app.models import Primitive


def _extract_js(example: str) -> str:
    start = example.index("```js") + len("```js")
    end = example.index("```", start)
    return example[start:end]


@pytest.mark.parametrize("primitive", list(Primitive))
def test_fewshot_is_valid_javascript(primitive: Primitive) -> None:
    js = _extract_js(_FEWSHOTS[primitive])
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False) as tmp:
        tmp.write(js)
        path = Path(tmp.name)
    try:
        result = subprocess.run(
            ["node", "--check", str(path)], capture_output=True, text=True, timeout=10
        )
        assert result.returncode == 0, result.stderr
    finally:
        path.unlink(missing_ok=True)


def test_every_primitive_has_a_fewshot() -> None:
    assert set(_FEWSHOTS.keys()) == set(Primitive)


def test_system_prompt_no_longer_promises_katex() -> None:
    # ctx.katex was documented and promised in the prompt but never actually
    # wired into either runtime (frontend/src/engines/sceneRuntime.ts or
    # app/validation/runtime.py) — any beat that reached for it would crash.
    # Removed until it's properly implemented (KaTeX needs its fonts embedded
    # as data URIs to render correctly under the sandboxed CSP, which is a
    # separate, larger piece of work). See docs/SCENE_CONTRACT.md §2.
    assert "katex" not in BEAT_SYSTEM_PROMPT.lower()


def test_system_prompt_documents_gsap() -> None:
    assert "ctx.gsap" in BEAT_SYSTEM_PROMPT


def test_system_prompt_documents_palette() -> None:
    assert "ctx.palette" in BEAT_SYSTEM_PROMPT


@pytest.mark.parametrize("primitive", list(Primitive))
def test_fewshot_uses_ctx_palette_not_hardcoded_colors(primitive: Primitive) -> None:
    js = _extract_js(_FEWSHOTS[primitive])
    assert "ctx.palette" in js
    # Every hardcoded hex/rgb color in the pre-palette design system should
    # have been replaced by a ctx.palette.* reference — except the shadow
    # filter's flood-color tint, which is deliberately not a palette color
    # (see the design-system rule in _CONTRACT_RULES).
    assert "#f8fafc" not in js
    assert "#4f46e5" not in js
    assert "#f59e0b" not in js
    assert "#334155" not in js
    assert "#cbd5e1" not in js
    assert "#e2e8f0" not in js
    assert "rgba(79,70,229" not in js
