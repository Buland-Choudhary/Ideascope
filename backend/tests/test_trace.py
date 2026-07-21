"""The trace logger must actually emit by default (docs/PLAN.md §5.5) — not
just when a script attaches its own handler. See app/observability/trace.py.
"""

import json
import logging

from _pytest.logging import LogCaptureFixture

from app.observability import log_generation_event


def test_trace_logger_has_a_default_handler_and_info_level() -> None:
    logger = logging.getLogger("ideascope.trace")
    assert logger.level == logging.INFO
    assert len(logger.handlers) >= 1


def test_log_generation_event_emits_valid_json(caplog: LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="ideascope.trace"):
        log_generation_event("beat", "ok", lesson_id="l1", beat_index=0, input_tokens=10)

    assert len(caplog.records) == 1
    record = json.loads(caplog.records[0].message)
    assert record == {
        "stage": "beat",
        "outcome": "ok",
        "lesson_id": "l1",
        "beat_index": 0,
        "input_tokens": 10,
    }
