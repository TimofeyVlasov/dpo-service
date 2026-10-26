from pydantic import BaseModel, Field, HttpUrl, model_validator


class RangeIn(BaseModel):
    """Диапазон курса по одному навыку."""

    skill: str = Field(pattern=r"^[A-Z0-9_]{2,50}$")
    from_level: int = Field(ge=0, le=100)
    to_level: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def check_range(self):
        if self.from_level >= self.to_level:
            raise ValueError("from_level должно быть меньше to_level")
        return self


class CourseIn(BaseModel):
    """Курс в том виде, в каком он приходит из файла или от API платформы."""

    external_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    url: HttpUrl
    provider: str = Field(min_length=1, max_length=100)
    description: str = ""
    price: float = Field(default=0, ge=0)
    duration_h: float | None = Field(default=None, gt=0)
    language: str = Field(default="ru", min_length=2, max_length=10)
    rating: float | None = Field(default=None, ge=0, le=5)
    level_label: str | None = Field(default=None, max_length=30)
    direction: str | None = Field(default=None, pattern=r"^[A-Z0-9_]{2,50}$")
    ranges: list[RangeIn] = Field(min_length=1)

    @model_validator(mode="after")
    def check_unique_skills(self):
        skills = [r.skill for r in self.ranges]
        if len(skills) != len(set(skills)):
            raise ValueError("навыки в ranges не должны повторяться")
        return self


class ImportResult(BaseModel):
    created: int
    updated: int