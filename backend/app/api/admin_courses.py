# Здесь описана группа адресов по теме КАТАЛОГ КУРСОВ

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.course import (
    CourseDetail,
    CourseIn,
    CourseList,
    CoursePatch,
    CourseStatus,
    ImportResult,
)
from app.services import catalog
from app.services.importer import import_courses

router = APIRouter(prefix="/admin/courses", tags=["admin: courses"])


# ручка импорта
@router.post("/import", response_model=ImportResult)
def import_courses_endpoint(items: list[CourseIn], db: Session = Depends(get_db)):
    """Принимает список курсов в JSON, проверяет его и записывает в каталог."""
    return import_courses(db, items)


# ручка списка
@router.get("", response_model=CourseList)
def list_courses(
    status: CourseStatus | None = None,
    direction: str | None = None,
    q: str | None = Query(default=None, description="поиск по названию"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Список курсов с фильтрами и постраничностью."""
    return catalog.list_courses(db, status, direction, q, limit, offset)


# ручка карточки
@router.get("/{course_id}", response_model=CourseDetail)
def get_course(course_id: int, db: Session = Depends(get_db)):
    """Карточка курса с разметкой по навыкам."""
    return _run(lambda: catalog.to_detail(catalog.get_course(db, course_id)))


# ручка правки
@router.patch("/{course_id}", response_model=CourseDetail)
def patch_course(course_id: int, patch: CoursePatch, db: Session = Depends(get_db)):
    """Правка полей курса и/или его разметки (присланные поля заменяются)."""
    return _run(lambda: catalog.to_detail(catalog.update_course(db, course_id, patch)))


@router.post("/{course_id}/publish", response_model=CourseDetail)
def publish_course(course_id: int, db: Session = Depends(get_db)):
    """Опубликовать курс: он начинает участвовать в подборе."""
    return _change(db, course_id, "published")


@router.post("/{course_id}/archive", response_model=CourseDetail)
def archive_course(course_id: int, db: Session = Depends(get_db)):
    """Убрать курс из подбора (в старых рекомендациях он сохраняется)."""
    return _change(db, course_id, "archived")


@router.post("/{course_id}/restore", response_model=CourseDetail)
def restore_course(course_id: int, db: Session = Depends(get_db)):
    """Вернуть курс из архива в черновик, на повторную проверку."""
    return _change(db, course_id, "draft")


def _change(db: Session, course_id: int, status: str) -> CourseDetail:
    return _run(lambda: catalog.to_detail(catalog.change_status(db, course_id, status)))


def _run(action):
    """Переводит ошибки сервиса в понятные ответы API: 404 и 409."""
    try:
        return action()
    except catalog.CourseNotFound:
        raise HTTPException(status_code=404, detail="курс не найден")
    except catalog.CatalogRuleError as error:
        raise HTTPException(status_code=409, detail=str(error))