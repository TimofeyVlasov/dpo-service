from pydantic import BaseModel, Field
class SkillLevel(BaseModel): # один навык человека, класс описывает 1 такую запись
    """Уровень человека по одному навыку (из профиля аккредитации)"""
    
    skill: str # код навыка, например PYTHON
    level: int = Field(ge=0, le=100) # уровень по навыку
    target: int = Field(ge=0, le=100) # целевой уровень по навыку (цель)

class Profile(BaseModel): # весь профиль человека
    """Профиль человека: направление и уровни по пройденным навыкам"""

    user_id: str # идентификатор человека, кто он
    direction: str # направление человека, например BACKEND
    skills: list[SkillLevel] # список навыков человека

class Preferences(BaseModel): # ответы на анкету перед выбором
    """Предпочтение человека для подбора (анкета)"""

    max_price: float | None = Field(default=None, ge=0) # none = любой бюджет, 0 = только бесплатные
    languages: list[str] = [] # пусто = любой язык
    hours_per_week: int | None = Field(default=None, gt=0)
