from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Course, CourseCompetency
from app.schemas.profile import Preferences
from app.services.matching import CourseData, Range


def load_candidates(
    db: Session, direction: str, skills: set[str], prefs: Preferences
) -> list[CourseData]:
    """«Прокладка»: достаёт подходящие курсы из базы и превращает их в CourseData."""
    stmt = (
        select(Course)
        .where(Course.status == "published", Course.direction == direction)
        .where(
            Course.id.in_(
                select(CourseCompetency.course_id).where(
                    CourseCompetency.skill_code.in_(skills)
                )
            )
        )
        .options(selectinload(Course.competencies))
    )
    if prefs.max_price is not None:
        stmt = stmt.where(Course.price <= prefs.max_price)
    if prefs.languages:
        stmt = stmt.where(Course.language.in_(prefs.languages))

    return [
        CourseData(
            id=str(course.id),
            ranges=[
                Range(c.skill_code, c.from_level, c.to_level)
                for c in course.competencies
            ],
            price=course.price,
            rating=course.rating,
            duration_h=course.duration_h,
        )
        for course in db.scalars(stmt).all()
    ]