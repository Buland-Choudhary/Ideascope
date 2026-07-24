"""In-memory generation state (docs/PLAN.md §5.3): the per-lesson store the
SSE stream endpoint and the background generation worker share.
"""

from app.state.store import LessonEvent, LessonState, LessonStore, get_lesson_store

__all__ = ["LessonEvent", "LessonState", "LessonStore", "get_lesson_store"]
