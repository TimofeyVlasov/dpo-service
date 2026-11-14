"""Пояснения к подбору.

Нейросеть только пересказывает то, что посчитал код: какие курсы выбраны и
сколько пробелов они закрывают. Выбирать курсы и считать числа она не может.
Любой сбой нейросети заменяется шаблонной фразой, подбор от этого не страдает.
"""

import json
import logging
import re
from dataclasses import dataclass

from app.services.dictionary_stub import DICTIONARY
from app.services.llm import LLMUnavailable, get_llm
from app.services.matching import Gap, Pick

log = logging.getLogger(__name__)

MAX_TEXT = 400  # длиннее одно пояснение быть не может


@dataclass
class Facts:
    """Что известно о выбранном курсе: название, вклад и шаги по навыкам."""

    title: str
    contribution: float  # доля 0..1
    steps: list[dict]  # по навыкам: skill, now, target, from, to


def collect_facts(
    picks: list[Pick], titles: dict[str, str], gaps: dict[str, Gap]
) -> list[Facts]:
    """Для каждого выбранного курса собирает факты: какие пробелы он касается."""
    result = []
    for p in picks:
        steps = [
            {
                "skill": r.skill,
                "now": gaps[r.skill].level,
                "target": gaps[r.skill].target,
                "from": r.from_level,
                "to": r.to_level,
            }
            for r in p.course.ranges
            if r.skill in gaps
        ]
        result.append(Facts(titles.get(p.course.id, "курс"), p.contribution, steps))
    return result


def template_text(f: Facts) -> str:
    """Запасное пояснение без нейросети: собирается из тех же цифр."""
    text = f"Закрывает около {round(f.contribution * 100)}% ваших пробелов."
    if f.steps:
        parts = ", ".join(
            f"{s['skill']} (сейчас {s['now']}, цель {s['target']}, "
            f"курс ведёт с {s['from']} до {s['to']})"
            for s in f.steps
        )
        text += f" Навыки: {parts}."
    return text


def build_prompt(facts: list[Facts]) -> tuple[str, str]:
    """Возвращает (правила для нейросети, факты по курсам)."""
    system = (
        "Ты помощник, который объясняет сотруднику, почему ему рекомендованы курсы. "
        "Для каждого курса напиши одно или два коротких предложения по-русски: "
        "какой пробел он закрывает и чем это полезно.\n"
        "Используй только факты из запроса. Не придумывай навыки, цифры и свойства курса, "
        "не упоминай навыки, которых нет в описании этого курса.\n"
        'Ответь только JSON без пояснений: {"items": [{"n": 1, "text": "..."}]}, '
        "где n это номер курса из запроса."
    )
    lines = []
    for n, f in enumerate(facts, start=1):
        lines.append(
            f"Курс {n}: «{f.title}». Закрывает около {round(f.contribution * 100)}% пробелов."
        )
        for s in f.steps:
            lines.append(
                f"  - {s['skill']}: у человека сейчас {s['now']}, нужно {s['target']}; "
                f"курс ведёт с {s['from']} до {s['to']}"
            )
    return system, "\n".join(lines)


def mentions_foreign_skill(text: str, f: Facts) -> bool:
    """В тексте упомянут навык из справочника, которого у этого курса нет."""
    own = {s["skill"] for s in f.steps}
    return any(
        code not in own and re.search(rf"\b{re.escape(code)}\b", text, re.IGNORECASE)
        for code in DICTIONARY
    )


def parse_answer(text: str, facts: list[Facts]) -> dict[int, str]:
    """Достаёт пояснения из ответа. Негодные пункты просто пропускаются:
    для них потом возьмётся шаблон. Ничего не бросает."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        items = json.loads(text[start : end + 1])["items"]
    except (ValueError, KeyError, TypeError):
        return {}
    if not isinstance(items, list):
        return {}

    result: dict[int, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        n, body = item.get("n"), item.get("text")
        if not isinstance(n, int) or isinstance(n, bool):
            continue
        if not 1 <= n <= len(facts) or n in result:
            continue
        if not isinstance(body, str) or not body.strip():
            continue
        body = body.strip()[:MAX_TEXT]
        if mentions_foreign_skill(body, facts[n - 1]):
            continue
        result[n] = body
    return result


def explain(
    picks: list[Pick], titles: dict[str, str], gaps: dict[str, Gap]
) -> list[str]:
    """Один текст на каждый выбранный курс, в том же порядке, что и picks."""
    if not picks:
        return []
    facts = collect_facts(picks, titles, gaps)
    fallback = [template_text(f) for f in facts]

    system, user = build_prompt(facts)
    try:
        answer = get_llm().complete(user, system, temperature=0.3, max_tokens=800)
    except LLMUnavailable as error:
        log.warning("пояснения: нейросеть недоступна (%s), взяты шаблоны", error)
        return fallback

    texts = parse_answer(answer, facts)
    return [texts.get(n, fallback[n - 1]) for n in range(1, len(facts) + 1)]