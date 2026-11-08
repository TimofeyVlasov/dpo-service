"""Управление каталогом: список, карточка, правка, смена статуса.

Статусы курса:  draft (черновик) -> published (виден в подборе) -> archived (скрыт).
Из архива курс можно вернуть только в черновик, чтобы его проверили заново.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Course, CourseCompetency
from app.schemas.course import (
    CourseDetail,
    CourseList,
    CourseListItem,
    CoursePatch,
    RangeOut,
)

# из какого статуса в какие можно перейти
TRANSITIONS: dict[str, set[str]] = {
    "draft": {"published", "archived"},
    "published": {"archived"},
    "archived": {"draft"},
}


class CourseNotFound(Exception):
    pass


class CatalogRuleError(Exception):
    """Нарушено правило каталога (например, нельзя опубликовать курс без разметки)."""


# Превращает курс из базы в готовую карточку CourseDetail для ответа методисту вместе с разметкой по навыкам.
def to_detail(course: Course) -> CourseDetail:
    ranges = sorted(course.competencies, key=lambda c: c.skill_code)
    return CourseDetail(
        id=course.id,
        external_id=course.external_id,
        title=course.title,
        url=course.url,
        provider=course.provider,
        description=course.description,
        price=course.price,
        duration_h=course.duration_h,
        language=course.language,
        rating=course.rating,
        level_label=course.level_label,
        direction=course.direction,
        status=course.status,
        ranges=[
            RangeOut(skill=r.skill_code, from_level=r.from_level, to_level=r.to_level)
            for r in ranges
        ],
    )


# Отдаёт список курсов с фильтрами (статус, направление, поиск по названию) и порцией (limit, offset), плюс общее число подходящих (total).
def list_courses(
    db: Session,
    status: str | None = None,
    direction: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> CourseList:
    conditions = []
    if status:
        conditions.append(Course.status == status)
    if direction:
        conditions.append(Course.direction == direction)
    if q:
        conditions.append(Course.title.ilike(f"%{q}%"))

    total = db.scalar(select(func.count()).select_from(Course).where(*conditions)) or 0

    skills_count = (
        select(func.count())
        .where(CourseCompetency.course_id == Course.id)
        .correlate(Course)
        .scalar_subquery()
    )
    rows = db.execute(
        select(Course, skills_count)
        .where(*conditions)
        .order_by(Course.id)
        .limit(limit)
        .offset(offset)
    ).all()

    items = [
        CourseListItem(
            id=c.id,
            external_id=c.external_id,
            title=c.title,
            provider=c.provider,
            direction=c.direction,
            level_label=c.level_label,
            price=c.price,
            status=c.status,
            skills_count=n,
        )
        for c, n in rows
    ]
    return CourseList(items=items, total=total, limit=limit, offset=offset)


# Находит курс по номеру; если его нет, бросает ошибку «не найден». Её используют остальные функции.
def get_course(db: Session, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise CourseNotFound(course_id)
    return course


# Меняет только присланные поля курса, а присланную разметку заменяет целиком. Статус не трогает.
def update_course(db: Session, course_id: int, patch: CoursePatch) -> Course:
    """Меняет только присланные поля. Статус при правке не трогаем:
    правит методист, он и есть проверяющий."""
    course = get_course(db, course_id)
    data = patch.model_dump(exclude_unset=True, exclude={"ranges"})
    if "url" in data:
        data["url"] = str(data["url"])
    for name, value in data.items():
        setattr(course, name, value)

    if patch.ranges is not None:
        course.competencies.clear()
        db.flush()
        course.competencies.extend(
            CourseCompetency(
                skill_code=r.skill, from_level=r.from_level, to_level=r.to_level
            )
            for r in patch.ranges
        )
    db.commit()
    db.refresh(course)
    return course


# Меняет статус курса, если переход разрешён таблицей TRANSITIONS и (для публикации) у курса есть разметка; иначе бросает ошибку правила.
def change_status(db: Session, course_id: int, new_status: str) -> Course:
    course = get_course(db, course_id)
    if new_status not in TRANSITIONS[course.status]:
        raise CatalogRuleError(
            f"нельзя перевести курс из «{course.status}» в «{new_status}»"
        )
    if new_status == "published" and not course.competencies:
        raise CatalogRuleError("нельзя опубликовать курс без разметки по навыкам")
    course.status = new_status
    db.commit()
    db.refresh(course)
    return course