from typing import Literal
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


# ---------- управление каталогом: что отдаём и что принимаем ----------

CourseStatus = Literal["draft", "published", "archived"]


class RangeOut(BaseModel):
    """Диапазон курса по навыку в ответе API"""

    skill: str
    from_level: int
    to_level: int

class CourseListItem(BaseModel):
    """Короткая строка курса для списка"""

    id: int
    external_id: str
    title: str
    provider: str
    direction: str | None
    level_label: str | None
    price: float
    status: CourseStatus
    skills_count: int

class CourseList(BaseModel):
    items: list[CourseListItem] # строки этой страницы
    total: int # сколько всего курсов подходит под запрос по всему каталогу, а не на этой странице
    limit: int # сколько строк в странице
    offset: int # сколько строк пропустили с начала

class CourseDetail(BaseModel):
    """Полная карточка курса вместе с разметкой по навыкам"""

    id: int
    external_id: str
    title: str
    url: str
    provider: str
    description: str
    price: float
    duration_h: float | None
    language: str
    rating: float | None
    level_label: str | None
    direction: str | None
    status: CourseStatus
    ranges: list[RangeOut]

# эти поля в базе обязательные: прислать для них null в правке нельзя
PATCH_NOT_NULL = ("title", "url", "provider", "description", "price", "language", "ranges")

class CoursePatch(BaseModel):
    """Частичная правка: меняются только те поля, что пришли в запросе.
    external_id и status здесь менять нельзя (статус меняется отдельными действиями)."""

    title: str | None = Field(default=None, min_length=1, max_length=300)
    url: HttpUrl | None = None
    provider: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    price: float | None = Field(default=None, ge=0)
    duration_h: float | None = Field(default=None, gt=0)
    language: str | None = Field(default=None, min_length=2, max_length=10)
    rating: float | None = Field(default=None, ge=0, le=5)
    level_label: str | None = Field(default=None, max_length=30)
    direction: str | None = Field(default=None, pattern=r"^[A-Z0-9_]{2,50}$")
    ranges: list[RangeIn] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def check(self):
        for name in PATCH_NOT_NULL:
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"поле {name} нельзя обнулить")
        if self.ranges:
            skills = [r.skill for r in self.ranges]
            if len(skills) != len(set(skills)):
                raise ValueError("навыки в ranges не должны повторяться")
        return self