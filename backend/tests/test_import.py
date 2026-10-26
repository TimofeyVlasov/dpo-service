import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (чтобы таблицы попали в Base.metadata)
from app.core.database import Base, get_db
from app.main import app as fastapi_app
from app.models import Course, CourseCompetency
from app.schemas.course import CourseIn
from app.services.importer import import_courses

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "courses.json"


def load_sample() -> list[dict]:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def parse_sample() -> list[CourseIn]:
    return TypeAdapter(list[CourseIn]).validate_python(load_sample())


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    return engine


def valid_course(**changes) -> dict:
    data = {
        "external_id": "t-1",
        "title": "Тестовый курс",
        "url": "https://example.com/t-1",
        "provider": "Тестовая платформа",
        "ranges": [{"skill": "SQL", "from_level": 0, "to_level": 50}],
    }
    data.update(changes)
    return data


def test_sample_file_is_valid():
    items = parse_sample()
    assert len(items) >= 10
    assert len({i.external_id for i in items}) == len(items)


def test_import_creates_draft_courses_with_ranges(engine):
    items = parse_sample()
    with Session(engine) as db:
        result = import_courses(db, items)
        assert result.created == len(items)
        assert result.updated == 0
        assert db.scalar(select(func.count()).select_from(Course)) == len(items)
        assert all(c.status == "draft" for c in db.scalars(select(Course)))
        first = db.scalar(select(Course).where(Course.external_id == "ex-001"))
        assert {c.skill_code for c in first.competencies} == {"PYTHON", "SQL"}


def test_reimport_updates_instead_of_duplicating(engine):
    items = parse_sample()
    with Session(engine) as db:
        import_courses(db, items)
        again = import_courses(db, items)
        assert again.created == 0
        assert again.updated == len(items)
        assert db.scalar(select(func.count()).select_from(Course)) == len(items)
        assert db.scalar(select(func.count()).select_from(CourseCompetency)) == sum(
            len(i.ranges) for i in items
        )


def test_reimport_changes_price_and_ranges(engine):
    with Session(engine) as db:
        import_courses(db, [CourseIn.model_validate(valid_course(price=100))])
        changed = valid_course(
            price=0, ranges=[{"skill": "SQL", "from_level": 10, "to_level": 70}]
        )
        import_courses(db, [CourseIn.model_validate(changed)])
        course = db.scalar(select(Course).where(Course.external_id == "t-1"))
        assert course.price == 0
        assert len(course.competencies) == 1
        assert course.competencies[0].from_level == 10
        assert course.competencies[0].to_level == 70


def test_reimport_keeps_published_status(engine):
    item = CourseIn.model_validate(valid_course())
    with Session(engine) as db:
        import_courses(db, [item])
        course = db.scalar(select(Course).where(Course.external_id == "t-1"))
        course.status = "published"
        db.commit()
        import_courses(db, [item])
        db.refresh(course)
        assert course.status == "published"


def test_wrong_range_is_rejected():
    bad = valid_course(ranges=[{"skill": "SQL", "from_level": 60, "to_level": 40}])
    with pytest.raises(ValidationError):
        CourseIn.model_validate(bad)


def test_negative_price_is_rejected():
    with pytest.raises(ValidationError):
        CourseIn.model_validate(valid_course(price=-1))


def test_duplicate_skill_is_rejected():
    ranges = [
        {"skill": "SQL", "from_level": 0, "to_level": 30},
        {"skill": "SQL", "from_level": 30, "to_level": 60},
    ]
    with pytest.raises(ValidationError):
        CourseIn.model_validate(valid_course(ranges=ranges))


@pytest.fixture
def client(engine):
    def override_get_db():
        with Session(engine) as session:
            yield session

    fastapi_app.dependency_overrides[get_db] = override_get_db
    yield TestClient(fastapi_app)
    fastapi_app.dependency_overrides.clear()


def test_import_endpoint_accepts_sample(client):
    response = client.post("/admin/courses/import", json=load_sample())
    assert response.status_code == 200
    assert response.json() == {"created": len(load_sample()), "updated": 0}


def test_import_endpoint_rejects_bad_data(client):
    bad = [valid_course(price=-5)]
    response = client.post("/admin/courses/import", json=bad)
    assert response.status_code == 422