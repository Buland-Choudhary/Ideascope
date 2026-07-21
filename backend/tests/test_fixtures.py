from app.fixtures import load_all_fixtures
from app.models import Engine, ManipulableType

# Freeze the expected fixture set so an accidental deletion fails the suite.
EXPECTED_FIXTURES = {"sine_wave", "water_cycle"}


def test_all_fixtures_load_and_validate() -> None:
    fixtures = load_all_fixtures()
    assert set(fixtures) == EXPECTED_FIXTURES


def test_fixtures_cover_both_engines() -> None:
    fixtures = load_all_fixtures()
    engines = {beat.engine for lesson in fixtures.values() for beat in lesson.beats}
    assert engines == {Engine.CANVAS, Engine.SVG}


def test_fixtures_include_a_manipulable() -> None:
    fixtures = load_all_fixtures()
    types = {
        m.type for lesson in fixtures.values() for beat in lesson.beats for m in beat.manipulables
    }
    # Phase-1 exit criterion: at least one manipulable across the fixtures.
    assert ManipulableType.SLIDER in types


def test_every_scene_uses_default_export() -> None:
    fixtures = load_all_fixtures()
    for lesson in fixtures.values():
        for beat in lesson.beats:
            assert "export default" in beat.scene.code, f"{lesson.id}/{beat.id}"
