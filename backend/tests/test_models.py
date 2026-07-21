import pytest
from pydantic import ValidationError

from app.models import (
    Beat,
    Engine,
    Lesson,
    LessonParams,
    Manipulable,
    ManipulableType,
    Narration,
    Outline,
    Primitive,
    Scene,
)


def _beat(index: int, *, manipulables: list[Manipulable] | None = None) -> Beat:
    return Beat(
        id=f"b{index}",
        index=index,
        intent="x",
        primitive=Primitive.PLOT,
        engine=Engine.CANVAS,
        narration=Narration(text="n"),
        scene=Scene(code="export default () => ({})"),
        manipulables=manipulables or [],
    )


def test_slider_requires_min_max() -> None:
    with pytest.raises(ValidationError, match="requires 'min' and 'max'"):
        Manipulable(id="a", label="A", type=ManipulableType.SLIDER, param="a", default=1)


def test_slider_min_less_than_max() -> None:
    with pytest.raises(ValidationError, match="'min' must be less than 'max'"):
        Manipulable(
            id="a", label="A", type=ManipulableType.SLIDER, param="a", default=1, min=5, max=5
        )


def test_select_requires_options_and_valid_default() -> None:
    with pytest.raises(ValidationError, match="one of 'options'"):
        Manipulable(
            id="a",
            label="A",
            type=ManipulableType.SELECT,
            param="a",
            default="z",
            options=["x", "y"],
        )


def test_toggle_default_must_be_bool() -> None:
    with pytest.raises(ValidationError, match="toggle 'default' must be a boolean"):
        Manipulable(id="a", label="A", type=ManipulableType.TOGGLE, param="a", default=1)


def test_valid_toggle_keeps_bool_default() -> None:
    m = Manipulable(id="a", label="A", type=ManipulableType.TOGGLE, param="a", default=True)
    assert m.default is True


def test_duplicate_manipulable_params_rejected() -> None:
    dup = [
        Manipulable(
            id="a", label="A", type=ManipulableType.SLIDER, param="p", default=1, min=0, max=2
        ),
        Manipulable(
            id="b", label="B", type=ManipulableType.SLIDER, param="p", default=1, min=0, max=2
        ),
    ]
    with pytest.raises(ValidationError, match="unique within a beat"):
        _beat(0, manipulables=dup)


def test_beat_indices_must_be_contiguous() -> None:
    with pytest.raises(ValidationError, match="contiguous from 0"):
        Lesson(
            id="l",
            topic="t",
            params=LessonParams(),
            outline=Outline(title="t", summary="s", target_beat_count=2),
            beats=[_beat(0), _beat(2)],
        )


def test_camelcase_wire_format() -> None:
    params = LessonParams(prior_knowledge="algebra")
    dumped = params.model_dump(by_alias=True)
    assert "priorKnowledge" in dumped
    assert "prior_knowledge" not in dumped
