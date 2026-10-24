from dataclasses import dataclass
# инструмент подключил для того, чтобы превратить классы в контейнеры данных

@dataclass(frozen=True)
class Weights:
    """Веса формулы. Это стартовые значения, их потом настраивают по проверке качества."""

    coverage: float = 65 # ГЛАВНЫЙ КРИТЕРИЙ РЕЛЕВАНТНОСТИ: сколько баллов из 100 дает покрытие пробелов
    fit: float = 15 # сколько баллов за соответствие курса уровню
    free: float = 10 # сколько баллов за то, что курс бесплатный
    rating: float = 10 # сколько баллов за рейтинг курса
    tolerance: int = 10 # курс слишком сложный, если уровень < начало - tolerance
    too_hard_multiplier: float = 0.3 # если курс слишком сложный, штрафуем его, умножая итоговый балл на 0.3
    min_gap: int = 5  # если до целевого уровня меньше 5 баллов - то не пробел


@dataclass(frozen=True)
class Gap:
    """Один пробел по навыку"""

    level: int # уровень человека по навыку
    target: int # цель (целевой уровень по навыку)
    gap: int # разрыв (сколько не хватает до цели)
    urgency: float # срочность (вес пробела в общей куче пробелов)


@dataclass(frozen=True)
class Range:
    """Диапазон курса по одному навыку"""

    skill: str # код навыка
    from_level: int # с какого уровня начинается курс
    to_level: int #до какого уровня курс доводит


@dataclass
class CourseData:
    """Информация о курсе для расчетов"""

    id: str # идентификатор курса (например "А")
    ranges: list[Range] # список диапазонов курса по каждому навыку
    price: float = 0 # цена, если 0 - бесплатный
    rating: float | None = None #рейтинг курса
    duration_h: float | None = None # длительность курса в часах


@dataclass
class Pick:
    """Выбранный курс в результате"""

    course: CourseData # сам курс
    score: float # балл релевантности на момент выбора
    contribution: float #вклад относительно ИСХОДНЫХ пробелов (для карточки)


def compute_gaps(
    levels: dict[str, int],
    targets: dict[str, int],
    importance: dict[str, int],
    min_gap: int = 5,
) -> dict[str, Gap]:
    """Пробелы и срочность: разрыв = цель - уровень, потребность = разрыв * важность."""
    raw: dict[str, tuple[int, int, int, int]] = {}
    for skill, level in levels.items():
        target = targets.get(skill, 0)
        gap = target - level
        if gap >= min_gap:
            raw[skill] = (level, target, gap, gap * importance.get(skill, 2))
    total = sum(item[3] for item in raw.values())
    return {
        skill: Gap(level, target, gap, need / total)
        for skill, (level, target, gap, need) in raw.items()
    }


def closable_share(level: int, target: int, from_level: int, to_level: int) -> float:
    """Какую долю разрыва по ОДНОМУ навыку закроет курс (доля закрытия)."""
    gap = target - level
    if gap <= 0:
        return 0.0
    closable = min(to_level, target) - max(level, from_level)
    return max(0, closable) / gap


def coverage(course: CourseData, gaps: dict[str, Gap]) -> float:
    """Покрытие курса: сумма (доля закрытия * срочность) по навыкам курса."""
    total = 0.0
    for r in course.ranges:
        gap = gaps.get(r.skill)
        if gap is not None:
            total += gap.urgency * closable_share(
                gap.level, gap.target, r.from_level, r.to_level
            )
    return total


def is_too_hard(course: CourseData, gaps: dict[str, Gap], tolerance: int = 10) -> bool:
    """Слишком сложный хотя бы по одному навыку из пробелов."""
    return any(
        gaps[r.skill].level < r.from_level - tolerance
        for r in course.ranges
        if r.skill in gaps
    )


def relevance(course: CourseData, gaps: dict[str, Gap], w: Weights = Weights()) -> float:
    """Балл релевантности 0..100 (нужен только для сортировки)."""
    hard = is_too_hard(course, gaps, w.tolerance)
    score = (
        w.coverage * coverage(course, gaps)
        + (0 if hard else w.fit)
        + (w.free if course.price == 0 else 0)
        + w.rating * (course.rating or 0) / 5
    )
    if hard:
        score *= w.too_hard_multiplier
    return min(100.0, score)


def contribution(
    course: CourseData,
    current_levels: dict[str, int],
    original: dict[str, Gap],
) -> float:
    """Вклад курса относительно исходных пробелов (его показываем на карточке)."""
    total = 0.0
    for r in course.ranges:
        gap = original.get(r.skill)
        if gap is None:
            continue
        current = current_levels.get(r.skill, gap.level)
        closable = max(0, min(r.to_level, gap.target) - max(current, r.from_level))
        total += gap.urgency * closable / gap.gap
    return total


def pick_set(
    courses: list[CourseData],
    levels: dict[str, int],
    targets: dict[str, int],
    importance: dict[str, int],
    w: Weights = Weights(),
    max_courses: int = 3,
    hours_limit: float | None = None,
) -> list[Pick]:
    """Жадный подбор набора: берём лучший курс, «засчитываем» его и пересчитываем пробелы."""
    current = dict(levels)
    original = compute_gaps(levels, targets, importance, w.min_gap)
    gaps = dict(original)
    chosen: list[Pick] = []
    used: set[str] = set()
    hours = 0.0

    while gaps and len(chosen) < max_courses:
        best: tuple[float, CourseData] | None = None
        for course in courses:
            if course.id in used:
                continue
            if hours_limit is not None and hours + (course.duration_h or 0) > hours_limit:
                continue
            score = relevance(course, gaps, w)
            if score > 0 and (best is None or score > best[0]):
                best = (score, course)
        if best is None:
            break
        score, course = best
        chosen.append(Pick(course, score, contribution(course, current, original)))
        used.add(course.id)
        hours += course.duration_h or 0
        for r in course.ranges:
            if r.skill in current and r.skill in targets:
                current[r.skill] = max(current[r.skill], min(r.to_level, targets[r.skill]))
        gaps = compute_gaps(current, targets, importance, w.min_gap)
    return chosen