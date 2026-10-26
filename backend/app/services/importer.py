from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Course, CourseCompetency
from app.schemas.course import CourseIn, ImportResult


def import_courses(db: Session, items: list[CourseIn]) -> ImportResult:
    """Создаёт новые курсы (статус draft) и обновляет уже известные по external_id."""
    created = 0
    updated = 0
    for item in items:
        course = db.scalar(select(Course).where(Course.external_id == item.external_id))
        if course is None:
            course = Course(external_id=item.external_id, status="draft")
            db.add(course)
            created += 1
        else:
            updated += 1

        course.title = item.title
        course.url = str(item.url)
        course.provider = item.provider
        course.description = item.description
        course.price = item.price
        course.duration_h = item.duration_h
        course.language = item.language
        course.rating = item.rating
        course.level_label = item.level_label
        course.direction = item.direction

        # старую разметку убираем и записываем заново
        course.competencies.clear()
        db.flush()
        course.competencies.extend(
            CourseCompetency(
                skill_code=r.skill, from_level=r.from_level, to_level=r.to_level
            )
            for r in item.ranges
        )
    db.commit()
    return ImportResult(created=created, updated=updated)