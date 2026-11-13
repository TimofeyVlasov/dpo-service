from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.course import RangeIn, RangeOut

SuggestionStatus = Literal["pending", "accepted", "rejected"]


class SuggestionOut(BaseModel):
    """Предложение разметки в ответе API."""

    id: int
    course_id: int
    status: SuggestionStatus
    ranges: list[RangeOut]
    created_at: datetime


class AcceptIn(BaseModel):
    """Тело запроса «принять». Без ranges берётся предложение как есть,
    с ranges методист подменяет его своей правкой."""

    ranges: list[RangeIn] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def check_unique_skills(self):
        if self.ranges:
            skills = [r.skill for r in self.ranges]
            if len(skills) != len(set(skills)):
                raise ValueError("навыки в ranges не должны повторяться")
        return self