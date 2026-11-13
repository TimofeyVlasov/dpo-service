"""Разметка курса нейросетью.

Порядок: нейросеть предлагает -> код проверяет и чистит -> методист решает.
Сама нейросеть в разметку курса ничего не пишет.
"""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Course, MarkupSuggestion
from app.schemas.course import CoursePatch, RangeIn, RangeOut
from app.schemas.markup import SuggestionOut
from app.services import catalog
from app.services.dictionary_stub import DICTIONARY
from app.services.llm import get_llm

# нейросеть называет уровни словами, числа ставит код
LEVELS = {"начальный": 0, "базовый": 40, "уверенный": 70, "экспертный": 90}


class SuggestionNotFound(Exception):
    pass


class SuggestionStateError(Exception):
    """Предложение уже обработано (принято или отклонено)."""


class BadAnswer(Exception):
    """Нейросеть ответила, но из ответа нельзя собрать разметку."""


def to_out(s: MarkupSuggestion) -> SuggestionOut:
    return SuggestionOut(
        id=s.id,
        course_id=s.course_id,
        status=s.status,
        ranges=[RangeOut(**r) for r in s.ranges],
        created_at=s.created_at,
    )


def build_prompt(course: Course) -> tuple[str, str]:
    """Возвращает (правила для нейросети, данные курса)."""
    skills = "\n".join(f"- {code}" for code in DICTIONARY)
    system = (
        "Ты помощник методиста. По описанию курса определи, каким навыкам он учит "
        "и с какого уровня на какой.\n"
        f"Используй только эти коды навыков:\n{skills}\n"
        f"Уровни обозначай только словами: {', '.join(LEVELS)}.\n"
        "Начальный: человек ничего не знает; базовый: знает основы; "
        "уверенный: работает самостоятельно; экспертный: глубокое знание.\n"
        "Уровень «from» это уровень на входе в курс, «to» уровень после курса, "
        "«to» всегда выше «from».\n"
        "Если курс не относится ни к одному навыку, верни пустой список.\n"
        'Ответь только JSON без пояснений: {"skills": [{"skill": "КОД", '
        '"from": "уровень", "to": "уровень"}]}'
    )
    user = (
        f"Название: {course.title}\n"
        f"Описание: {(course.description or '')[:2000]}\n"
        f"Уровень по версии площадки: {course.level_label or 'не указан'}"
    )
    return system, user


def parse_answer(text: str) -> list[dict]:
    """Достаёт из ответа нейросети JSON и оставляет только пригодные навыки.
    Плохие пункты молча отбрасываются; если не осталось ничего, это BadAnswer."""
    start, end = text.find("{"), text.rfind("}")  # нейросеть иногда оборачивает JSON в текст или ```
    if start == -1 or end <= start:
        raise BadAnswer("в ответе нет JSON")
    try:
        items = json.loads(text[start : end + 1])["skills"]
    except (ValueError, KeyError, TypeError):
        raise BadAnswer("ответ не в ожидаемом формате")
    if not isinstance(items, list):
        raise BadAnswer("skills должен быть списком")

    result: dict[str, dict] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        code = str(item.get("skill", "")).strip().upper()
        low = LEVELS.get(str(item.get("from", "")).strip().lower())
        high = LEVELS.get(str(item.get("to", "")).strip().lower())
        if code not in DICTIONARY or low is None or high is None:
            continue  # код не из справочника или неизвестная метка
        if low >= high or code in result:
            continue  # диапазон неверный или навык уже есть
        result[code] = {"skill": code, "from_level": low, "to_level": high}

    if not result:
        raise BadAnswer("нейросеть не предложила ни одного подходящего навыка")
    return list(result.values())


def suggest(db: Session, course_id: int) -> MarkupSuggestion:
    """Спрашивает нейросеть и сохраняет предложение (статус pending)."""
    course = catalog.get_course(db, course_id)
    system, user = build_prompt(course)
    answer = get_llm().complete(user, system, temperature=0.1, max_tokens=500)
    ranges = parse_answer(answer)
    suggestion = MarkupSuggestion(
        course_id=course.id, status="pending", ranges=ranges, raw_answer=answer
    )
    db.add(suggestion)
    db.commit()
    db.refresh(suggestion)
    return suggestion


def list_suggestions(db: Session, course_id: int) -> list[MarkupSuggestion]:
    catalog.get_course(db, course_id)  # нет курса -> CourseNotFound
    return list(
        db.scalars(
            select(MarkupSuggestion)
            .where(MarkupSuggestion.course_id == course_id)
            .order_by(MarkupSuggestion.id.desc())
        )
    )


def get_suggestion(db: Session, suggestion_id: int) -> MarkupSuggestion:
    suggestion = db.get(MarkupSuggestion, suggestion_id)
    if suggestion is None:
        raise SuggestionNotFound(suggestion_id)
    return suggestion


def _require_pending(s: MarkupSuggestion) -> None:
    if s.status != "pending":
        raise SuggestionStateError("предложение уже обработано")


def accept(
    db: Session, suggestion_id: int, override: list[RangeIn] | None = None
) -> MarkupSuggestion:
    """Записывает разметку в курс (предложенную или исправленную методистом).
    Статус курса не меняем: публикует методист отдельным действием."""
    suggestion = get_suggestion(db, suggestion_id)
    _require_pending(suggestion)
    ranges = override if override is not None else [RangeIn(**r) for r in suggestion.ranges]
    catalog.update_course(db, suggestion.course_id, CoursePatch(ranges=ranges))
    suggestion.status = "accepted"
    db.commit()
    db.refresh(suggestion)
    return suggestion


def reject(db: Session, suggestion_id: int) -> MarkupSuggestion:
    suggestion = get_suggestion(db, suggestion_id)
    _require_pending(suggestion)
    suggestion.status = "rejected"
    db.commit()
    db.refresh(suggestion)
    return suggestion