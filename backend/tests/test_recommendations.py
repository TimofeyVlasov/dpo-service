import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter
from pytest import approx
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base, get_db
from app.main import app as fastapi_app
from app.models import Course, Recommendation
from app.schemas.course import CourseIn
from app.schemas.profile import Preferences, Profile, SkillLevel
from app.services.importer import import_courses
from app.services.profile_stub import get_profile
from app.services.recommender import recommend

from functools import partial

import httpx

from app.services import profile_client

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "courses.json"


def sample_courses() -> list[CourseIn]:
    data = json.loads(SAMPLE.read_text(encoding="utf-8"))
    return TypeAdapter(list[CourseIn]).validate_python(data)


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db(engine):
    """База с импортированными и опубликованными курсами."""
    with Session(engine) as session:
        import_courses(session, sample_courses())
        session.execute(update(Course).values(status="published"))
        session.commit()
        yield session


def external_ids(rec: Recommendation) -> list[str]:
    return [item.course.external_id for item in rec.items]


def test_weak_profile_gets_expected_set(db):
    prefs = Preferences(max_price=5000, languages=["ru"], hours_per_week=8)
    rec = recommend(db, get_profile("demo-weak"), prefs)
    assert external_ids(rec) == ["ex-001", "ex-004", "ex-006"]
    assert [i.label for i in rec.items] == ["best", "extra", "extra"]
    assert rec.total_contribution == approx(0.773, abs=1e-3)


def test_free_only_budget_excludes_paid_courses(db):
    rec = recommend(db, get_profile("demo-weak"), Preferences(max_price=0))
    assert rec.items
    assert all(item.course.price == 0 for item in rec.items)


def test_language_filter(db):
    rec = recommend(db, get_profile("demo-weak"), Preferences(languages=["en"]))
    assert all(item.course.language == "en" for item in rec.items)


def test_single_gap_gives_one_course(db):
    rec = recommend(db, get_profile("demo-sql"), Preferences())
    assert external_ids(rec) == ["ex-006"]
    assert rec.total_contribution == approx(0.857, abs=1e-3)


def test_no_gaps_gives_empty_recommendation(db):
    rec = recommend(db, get_profile("demo-strong"), Preferences())
    assert rec.items == []
    assert rec.total_contribution == 0


def test_unknown_skill_is_ignored(db):
    profile = Profile(
        user_id="x", direction="BACKEND",
        skills=[SkillLevel(skill="UNKNOWN", level=10, target=70)],
    )
    assert recommend(db, profile, Preferences()).items == []


def test_unpublished_courses_are_not_used(engine):
    with Session(engine) as session:
        import_courses(session, sample_courses())   # курсы остались черновиками
        rec = recommend(session, get_profile("demo-weak"), Preferences())
        assert rec.items == []


def test_recommendation_is_saved_with_snapshot(db):
    rec = recommend(db, get_profile("demo-weak"), Preferences())
    saved = db.scalar(select(Recommendation).where(Recommendation.id == rec.id))
    assert saved.user_id == "demo-weak"
    assert saved.mode == "gaps"
    assert saved.profile_snapshot["skills"][0]["skill"] == "PYTHON"
    assert db.scalar(select(func.count()).select_from(Recommendation)) == 1


@pytest.fixture
def client(engine):
    def override_get_db():
        with Session(engine) as session:
            yield session

    fastapi_app.dependency_overrides[get_db] = override_get_db
    yield TestClient(fastapi_app)
    fastapi_app.dependency_overrides.clear()


def load_catalog(client) -> None:
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    assert client.post("/admin/courses/import", json=sample).status_code == 200
    drafts = client.get("/admin/courses", params={"status": "draft", "limit": 200}).json()
    assert drafts["total"] == len(sample)
    for item in drafts["items"]:
        assert client.post(f"/admin/courses/{item['id']}/publish").status_code == 200


def test_endpoint_returns_recommendation(client):
    load_catalog(client)
    body = {
        "user_id": "demo-weak",
        "preferences": {"max_price": 5000, "languages": ["ru"], "hours_per_week": 8},
    }
    response = client.post("/recommendations", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == "demo-weak"
    assert data["mode"] == "gaps"
    assert data["total_contribution"] == approx(0.773, abs=1e-3)
    assert [c["title"] for c in data["courses"]] == [
        "Основы Python и SQL", "Docker для разработчика", "SQL углублённый",
    ]
    first = data["courses"][0]
    assert first["rank"] == 1
    assert first["label"] == "best"
    assert first["contribution"] == approx(0.341, abs=1e-3)


def test_endpoint_unknown_user_returns_404(client):
    response = client.post("/recommendations", json={"user_id": "nobody"})
    assert response.status_code == 404

REMOTE_USER = "10000000-0000-4000-8000-000000000001"


def remote_profile_body(level: int) -> dict:
    return {
        "userId": REMOTE_USER,
        "area": "Backend",
        "competencies": [
            {"skill": "SQL", "direction": "BACKEND", "rating": level, "target": 70}
        ],
    }


@pytest.fixture
def use_remote_profile(monkeypatch, use_demo_profiles_by_default):
    original_fetch = profile_client.fetch_profile

    def setup(handler):
        monkeypatch.setattr(
            profile_client.settings,
            "accreditation_base_url",
            "http://accreditation.test",
        )
        monkeypatch.setattr(
            profile_client,
            "fetch_profile",
            partial(original_fetch, transport=httpx.MockTransport(handler)),
        )

    return setup


@pytest.mark.parametrize(
    "level, wrapped, expected_count",
    [(35, False, 1), (35, True, 1), (70, False, 0)],
)
def test_endpoint_uses_remote_level(
    client, engine, use_remote_profile, level, wrapped, expected_count
):
    load_catalog(client)
    requests = []
    payload = remote_profile_body(level)
    if wrapped:
        payload = {"status": "success", "data": payload}

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        return httpx.Response(200, json=payload)

    use_remote_profile(handler)
    response = client.post("/recommendations", json={"user_id": REMOTE_USER})

    assert response.status_code == 200
    data = response.json()
    assert len(data["courses"]) == expected_count
    assert requests == [("GET", f"/dpo/{REMOTE_USER}/latest")]

    with Session(engine) as session:
        saved = session.get(Recommendation, data["recommendation_id"])
        assert saved is not None
        assert saved.profile_snapshot == {
            "user_id": REMOTE_USER,
            "direction": "BACKEND",
            "skills": [{"skill": "SQL", "level": level, "target": 70}],
        }


@pytest.mark.parametrize(
    "remote_status, expected_status",
    [(204, 404), (404, 404), (500, 503)],
)
def test_endpoint_handles_remote_status(
    client, use_remote_profile, remote_status, expected_status
):
    use_remote_profile(lambda request: httpx.Response(remote_status))

    response = client.post("/recommendations", json={"user_id": REMOTE_USER})

    assert response.status_code == expected_status


def test_endpoint_handles_profile_timeout(client, use_remote_profile):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("сервис не ответил", request=request)

    use_remote_profile(handler)

    response = client.post("/recommendations", json={"user_id": REMOTE_USER})

    assert response.status_code == 503


def test_endpoint_rejects_invalid_profile(client, use_remote_profile):
    use_remote_profile(
        lambda request: httpx.Response(200, json=remote_profile_body(120))
    )

    response = client.post("/recommendations", json={"user_id": REMOTE_USER})

    assert response.status_code == 502


def test_endpoint_rejects_profile_of_other_user(client, use_remote_profile):
    payload = remote_profile_body(35)
    payload["userId"] = "10000000-0000-4000-8000-000000000002"
    use_remote_profile(lambda request: httpx.Response(200, json=payload))

    response = client.post("/recommendations", json={"user_id": REMOTE_USER})

    assert response.status_code == 502