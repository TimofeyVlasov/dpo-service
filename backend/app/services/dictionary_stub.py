"""ВРЕМЕННАЯ замена справочника компетенций: цели и важность навыков."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SkillInfo:
    direction: str # направление
    target: int # цель по умолчанию для навыка
    importance: int # 1, 2 или 3


DICTIONARY: dict[str, SkillInfo] = {
    "PYTHON": SkillInfo("BACKEND", target=70, importance=3),
    "SQL": SkillInfo("BACKEND", target=70, importance=3),
    "ASYNC": SkillInfo("BACKEND", target=60, importance=2),
    "DOCKER": SkillInfo("BACKEND", target=60, importance=2),
    "GIT": SkillInfo("BACKEND", target=60, importance=1),
}