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
