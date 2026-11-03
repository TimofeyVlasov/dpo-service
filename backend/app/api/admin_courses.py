# Здесь описана группа адресов по теме КАТАЛОГ КУРСОВ

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import update

from app.models import Course
from app.core.database import get_db
from app.schemas.course import CourseIn, ImportResult
from app.services.importer import import_courses

router = APIRouter(prefix="/admin/courses", tags=["admin: courses"])


@router.post("/import", response_model=ImportResult)
def import_courses_endpoint(items: list[CourseIn], db: Session = Depends(get_db)):
    """Принимает список курсов в JSON, проверяет его и записывает в каталог."""
    return import_courses(db, items)

@router.post("/publish-drafts")
def publish_drafts(db: Session = Depends(get_db)):
    """ВРЕМЕННО, для разработки: публикует все черновики разом.
    Позже публикация будет после проверки разметки методистом."""
    result = db.execute(
        update(Course).where(Course.status == "draft").values(status="published")
    )
    db.commit()
    return {"published": result.rowcount}