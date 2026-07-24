"""Structured-output schema for the vision self-critique (docs/PLAN.md §5.2)."""

from pydantic import BaseModel, Field


class Critique(BaseModel):
    passed: bool = Field(
        description="Whether the rendered scene achieves the stated intent, judged visually."
    )
    feedback: str = Field(
        description=(
            "If not passed: concrete, actionable feedback on what's wrong and how to fix the "
            "scene code. If passed: brief confirmation of what the scene shows."
        )
    )
