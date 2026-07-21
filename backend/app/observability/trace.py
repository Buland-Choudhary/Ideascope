"""The generation trace log (docs/PLAN.md §5.5).

Every generation attempt emits one structured JSONL record — the data that turns
"beat 4 looked wrong" into "the simulation primitive fails critique 40% of the
time," and the raw input for the §14 cost model. Plain JSON to a dedicated logger
for MVP (the host's log drain picks it up); no observability stack needed.

Privacy: topic strings are user input. Keep log retention short; do not add other
user-identifying fields here.
"""

import json
import logging
from typing import Any

_logger = logging.getLogger("ideascope.trace")
_logger.setLevel(logging.INFO)
if not _logger.handlers:
    # Without an explicit handler, this logger's INFO records are silently
    # dropped under plain uvicorn (root logger defaults to WARNING and
    # doesn't touch third-party logger names). Attach a plain stdout handler
    # by default so "picked up by the host's log drain" (per the module
    # docstring) is actually true out of the box, not just when a script
    # happens to configure logging itself.
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(_handler)
    _logger.propagate = False


def log_generation_event(stage: str, outcome: str, **fields: Any) -> None:
    """Emit one generation-trace record.

    Args:
        stage: pipeline stage, e.g. "plan", "beat", "auto_fix", "critique".
        outcome: "ok" | "render_fail" | "critique_fail" | "degraded" | "error".
        **fields: additional context (lesson_id, beat_index, primitive, engine,
            model, attempt, latency_ms, input_tokens, output_tokens, error, ...).
    """
    record: dict[str, Any] = {"stage": stage, "outcome": outcome, **fields}
    _logger.info(json.dumps(record, default=str))
