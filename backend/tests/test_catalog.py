import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base, get_db
from app.main import app as fastapi_app
from app.models import Course
from app.schemas.course import CourseIn
from app.services.importer import import_courses

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "courses.json"


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def client(engine):
    def override_get_db():
        with Session(engine) as session:
            yield session

    fastapi_app.dependency_overrides[get_db] = override_get_db
    yield TestClient(fastapi_app)
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def loaded(client):
    """Каталог из примера загружен, все курсы в статусе draft."""
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    assert client.post("/admin/courses/import", json=sample).status_code == 200
    return sample


def first_id(client, **params) -> int:
    return client.get("/admin/courses", params=params).json()["items"][0]["id"]


def parse(data) -> list[CourseIn]:
    return TypeAdapter(list[CourseIn]).validate_python(data)


# ---------- список ----------


def test_list_returns_all_with_total(client, loaded):
    data = client.get("/admin/courses").json()
    assert data["total"] == len(loaded)
    assert len(data["items"]) == len(loaded)
    assert all(i["status"] == "draft" and i["skills_count"] >= 1 for i in data["items"])


def test_list_pagination(client, loaded):
    page = client.get("/admin/courses", params={"limit": 2, "offset": 1}).json()
    assert page["total"] == len(loaded)
    assert len(page["items"]) == 2
    assert page["limit"] == 2 and page["offset"] == 1


def test_list_filter_by_status(client, loaded):
    course_id = first_id(client)
    client.post(f"/admin/courses/{course_id}/publish")
    published = client.get("/admin/courses", params={"status": "published"}).json()
    assert [i["id"] for i in published["items"]] == [course_id]
    drafts = client.get("/admin/courses", params={"status": "draft"}).json()
    assert drafts["total"] == len(loaded) - 1


def test_list_search_by_title(client, loaded):
    title = loaded[0]["title"]
    word = title.split()[0]
    found = client.get("/admin/courses", params={"q": word}).json()
    assert any(i["title"] == title for i in found["items"])
    # регистр латиницы не важен (кириллицу без учёта регистра ищет только PostgreSQL,
    # а в тестах стоит SQLite, поэтому здесь проверяем на латинице)
    latin = client.get("/admin/courses", params={"q": "PYTHON"}).json()
    assert latin["total"] >= 1
    nothing = client.get("/admin/courses", params={"q": "zzz-нет-такого"}).json()
    assert nothing["total"] == 0 and nothing["items"] == []


def test_list_rejects_bad_params(client, loaded):
    assert client.get("/admin/courses", params={"status": "oops"}).status_code == 422
    assert client.get("/admin/courses", params={"limit": 0}).status_code == 422
    assert client.get("/admin/courses", params={"offset": -1}).status_code == 422


# ---------- карточка ----------


def test_get_course_has_ranges(client, loaded):
    course_id = first_id(client)
    card = client.get(f"/admin/courses/{course_id}").json()
    assert card["id"] == course_id
    assert card["ranges"]
    assert {"skill", "from_level", "to_level"} <= set(card["ranges"][0])


def test_get_missing_course_is_404(client, loaded):
    assert client.get("/admin/courses/99999").status_code == 404


# ---------- правка ----------


def test_patch_changes_only_given_fields(client, loaded):
    course_id = first_id(client)
    before = client.get(f"/admin/courses/{course_id}").json()
    response = client.patch(
        f"/admin/courses/{course_id}", json={"title": "Новое название", "price": 0}
    )
    assert response.status_code == 200
    after = response.json()
    assert after["title"] == "Новое название"
    assert after["price"] == 0
    assert after["provider"] == before["provider"]
    assert after["ranges"] == before["ranges"]
    assert after["status"] == before["status"]


def test_patch_replaces_ranges(client, loaded):
    course_id = first_id(client)
    new = [{"skill": "PYTHON", "from_level": 10, "to_level": 60}]
    card = client.patch(f"/admin/courses/{course_id}", json={"ranges": new}).json()
    assert card["ranges"] == new


def test_patch_can_clear_nullable_field(client, loaded):
    course_id = first_id(client)
    card = client.patch(f"/admin/courses/{course_id}", json={"rating": None}).json()
    assert card["rating"] is None


def test_patch_rejects_invalid_data(client, loaded):
    course_id = first_id(client)
    url = f"/admin/courses/{course_id}"
    assert client.patch(url, json={"title": None}).status_code == 422
    assert client.patch(url, json={"price": -1}).status_code == 422
    assert client.patch(url, json={"ranges": []}).status_code == 422
    bad_range = [{"skill": "PYTHON", "from_level": 50, "to_level": 50}]
    assert client.patch(url, json={"ranges": bad_range}).status_code == 422
    dup = [
        {"skill": "PYTHON", "from_level": 0, "to_level": 10},
        {"skill": "PYTHON", "from_level": 10, "to_level": 20},
    ]
    assert client.patch(url, json={"ranges": dup}).status_code == 422


def test_patch_missing_course_is_404(client, loaded):
    assert client.patch("/admin/courses/99999", json={"title": "x"}).status_code == 404


# ---------- статусы ----------


def test_publish_archive_restore_cycle(client, loaded):
    course_id = first_id(client)
    base = f"/admin/courses/{course_id}"
    assert client.post(f"{base}/publish").json()["status"] == "published"
    assert client.post(f"{base}/archive").json()["status"] == "archived"
    assert client.post(f"{base}/restore").json()["status"] == "draft"
    assert client.post(f"{base}/publish").json()["status"] == "published"


def test_forbidden_transitions_are_409(client, loaded):
    course_id = first_id(client)
    base = f"/admin/courses/{course_id}"
    assert client.post(f"{base}/restore").status_code == 409  # draft -> draft
    client.post(f"{base}/publish")
    assert client.post(f"{base}/publish").status_code == 409  # published -> published
    assert client.post(f"{base}/restore").status_code == 409  # published -> draft
    client.post(f"{base}/archive")
    assert client.post(f"{base}/publish").status_code == 409  # archived -> published


def test_status_change_of_missing_course_is_404(client, loaded):
    assert client.post("/admin/courses/99999/publish").status_code == 404


def test_cannot_publish_course_without_ranges(client, engine, loaded):
    course_id = first_id(client)
    with Session(engine) as db:
        course = db.get(Course, course_id)
        course.competencies.clear()
        db.commit()
    assert client.post(f"/admin/courses/{course_id}/publish").status_code == 409


def test_temporary_bulk_publish_is_gone(client, loaded):
    assert client.post("/admin/courses/publish-drafts").status_code in (404, 405, 422)


# ---------- повторный импорт ----------


def test_reimport_with_changed_ranges_returns_published_to_draft(engine):
    data = json.loads(SAMPLE.read_text(encoding="utf-8"))
    with Session(engine) as db:
        import_courses(db, parse(data))
        course = db.scalars(select(Course)).first()
        course.status = "published"
        db.commit()

        changed = json.loads(json.dumps(data))
        for item in changed:
            if item["external_id"] == course.external_id:
                rng = item["ranges"][0]
                rng["to_level"] = min(100, rng["to_level"] + 1)
                if rng["to_level"] == rng["from_level"]:
                    rng["from_level"] -= 1
        import_courses(db, parse(changed))
        db.refresh(course)
        assert course.status == "draft"


def test_reimport_with_changed_title_only_keeps_published(engine):
    data = json.loads(SAMPLE.read_text(encoding="utf-8"))
    with Session(engine) as db:
        import_courses(db, parse(data))
        course = db.scalars(select(Course)).first()
        course.status = "published"
        db.commit()

        changed = json.loads(json.dumps(data))
        for item in changed:
            if item["external_id"] == course.external_id:
                item["title"] = item["title"] + " (обновлено)"
        import_courses(db, parse(changed))
        db.refresh(course)
        assert course.status == "published"
        assert course.title.endswith("(обновлено)")


def test_archived_course_stays_archived_after_reimport(engine):
    data = json.loads(SAMPLE.read_text(encoding="utf-8"))
    with Session(engine) as db:
        import_courses(db, parse(data))
        course = db.scalars(select(Course)).first()
        course.status = "archived"
        db.commit()
        import_courses(db, parse(data))
        db.refresh(course)
        assert course.status == "archived"