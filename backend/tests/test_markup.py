import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base, get_db
from app.main import app as fastapi_app
from app.services.llm import LLMUnavailable

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "courses.json"

GOOD = json.dumps(
    {
        "skills": [
            {"skill": "PYTHON", "from": "начальный", "to": "базовый"},
            {"skill": "SQL", "from": "базовый", "to": "уверенный"},
        ]
    },
    ensure_ascii=False,
)
EXPECTED = [
    {"skill": "PYTHON", "from_level": 0, "to_level": 40},
    {"skill": "SQL", "from_level": 40, "to_level": 70},
]


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
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    assert client.post("/admin/courses/import", json=sample).status_code == 200
    return sample


def first_id(client) -> int:
    return client.get("/admin/courses").json()["items"][0]["id"]


def suggest(client, course_id):
    return client.post(f"/admin/courses/{course_id}/suggest-markup")


def ranges_of(client, course_id):
    return client.get(f"/admin/courses/{course_id}").json()["ranges"]


# ---------- получение предложения ----------


def test_suggest_creates_pending_suggestion(client, loaded, fake_llm):
    fake_llm.answers = [GOOD]
    course_id = first_id(client)
    response = suggest(client, course_id)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "pending"
    assert data["course_id"] == course_id
    assert data["ranges"] == EXPECTED
    title = client.get(f"/admin/courses/{course_id}").json()["title"]
    assert title in fake_llm.calls[0]["user"]   # название курса ушло нейросети
    assert "PYTHON" in fake_llm.calls[0]["system"]  # список навыков тоже


def test_answer_wrapped_in_text_and_fence_is_parsed(client, loaded, fake_llm):
    fake_llm.answers = [f"Вот разметка:\n```json\n{GOOD}\n```\nГотово."]
    assert suggest(client, first_id(client)).json()["ranges"] == EXPECTED


def test_bad_items_are_dropped_and_good_kept(client, loaded, fake_llm):
    messy = json.dumps(
        {
            "skills": [
                {"skill": "python", "from": "Начальный", "to": "Базовый"},  # регистр исправит код
                {"skill": "COBOL", "from": "начальный", "to": "базовый"},  # нет в справочнике
                {"skill": "SQL", "from": "супер", "to": "базовый"},  # неизвестная метка
                {"skill": "GIT", "from": "уверенный", "to": "базовый"},  # from выше to
                {"skill": "PYTHON", "from": "базовый", "to": "экспертный"},  # дубль навыка
            ]
        },
        ensure_ascii=False,
    )
    fake_llm.answers = [messy]
    ranges = suggest(client, first_id(client)).json()["ranges"]
    assert ranges == [{"skill": "PYTHON", "from_level": 0, "to_level": 40}]


@pytest.mark.parametrize(
    "answer", ["не знаю", '{"skills": []}', '{"skills": 5}', '{"other": 1}']
)
def test_unusable_answer_is_502_and_nothing_saved(client, loaded, fake_llm, answer):
    fake_llm.answers = [answer]
    course_id = first_id(client)
    assert suggest(client, course_id).status_code == 502
    assert client.get(f"/admin/courses/{course_id}/suggestions").json() == []


def test_llm_unavailable_is_503(client, loaded, fake_llm):
    fake_llm.answers = [LLMUnavailable("нет сети")]
    assert suggest(client, first_id(client)).status_code == 503


def test_suggest_for_missing_course_is_404(client, fake_llm):
    assert suggest(client, 99999).status_code == 404
    assert fake_llm.calls == []  # нейросеть для несуществующего курса не трогаем


# ---------- решение методиста ----------


def test_accept_writes_ranges_to_course(client, loaded, fake_llm):
    fake_llm.answers = [GOOD]
    course_id = first_id(client)
    suggestion_id = suggest(client, course_id).json()["id"]
    response = client.post(f"/admin/suggestions/{suggestion_id}/accept")
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    card = client.get(f"/admin/courses/{course_id}").json()
    assert card["ranges"] == EXPECTED
    assert card["status"] == "draft"  # принятие не публикует курс


def test_accept_with_edited_ranges_uses_methodist_version(client, loaded, fake_llm):
    fake_llm.answers = [GOOD]
    course_id = first_id(client)
    suggestion_id = suggest(client, course_id).json()["id"]
    edited = [{"skill": "SQL", "from_level": 10, "to_level": 55}]
    response = client.post(
        f"/admin/suggestions/{suggestion_id}/accept", json={"ranges": edited}
    )
    assert response.status_code == 200
    assert ranges_of(client, course_id) == edited


def test_reject_keeps_course_unchanged(client, loaded, fake_llm):
    fake_llm.answers = [GOOD]
    course_id = first_id(client)
    before = ranges_of(client, course_id)
    suggestion_id = suggest(client, course_id).json()["id"]
    response = client.post(f"/admin/suggestions/{suggestion_id}/reject")
    assert response.json()["status"] == "rejected"
    assert ranges_of(client, course_id) == before


def test_decided_suggestion_cannot_be_decided_again(client, loaded, fake_llm):
    fake_llm.answers = [GOOD, GOOD]
    course_id = first_id(client)
    first = suggest(client, course_id).json()["id"]
    second = suggest(client, course_id).json()["id"]
    client.post(f"/admin/suggestions/{first}/accept")
    assert client.post(f"/admin/suggestions/{first}/accept").status_code == 409
    assert client.post(f"/admin/suggestions/{first}/reject").status_code == 409
    client.post(f"/admin/suggestions/{second}/reject")
    assert client.post(f"/admin/suggestions/{second}/accept").status_code == 409


def test_missing_suggestion_is_404(client, loaded):
    assert client.post("/admin/suggestions/99999/accept").status_code == 404
    assert client.post("/admin/suggestions/99999/reject").status_code == 404


def test_accept_rejects_bad_edited_ranges(client, loaded, fake_llm):
    fake_llm.answers = [GOOD]
    course_id = first_id(client)
    suggestion_id = suggest(client, course_id).json()["id"]
    url = f"/admin/suggestions/{suggestion_id}/accept"
    bad = [{"skill": "SQL", "from_level": 50, "to_level": 50}]
    assert client.post(url, json={"ranges": bad}).status_code == 422
    assert client.post(url, json={"ranges": []}).status_code == 422
    listing = client.get(f"/admin/courses/{course_id}/suggestions").json()
    assert listing[0]["status"] == "pending"  # предложение осталось нетронутым


# ---------- список ----------


def test_list_suggestions_newest_first(client, loaded, fake_llm):
    fake_llm.answers = [GOOD, GOOD]
    course_id = first_id(client)
    a = suggest(client, course_id).json()["id"]
    b = suggest(client, course_id).json()["id"]
    listing = client.get(f"/admin/courses/{course_id}/suggestions").json()
    assert [i["id"] for i in listing] == [b, a]
    assert client.get("/admin/courses/99999/suggestions").status_code == 404