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
from app.services import rationale
from app.services.llm import LLMUnavailable
from app.services.matching import CourseData, Gap, Pick, Range

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "courses.json"

GAPS = {"SQL": Gap(level=10, target=70, gap=60, urgency=1.0)}
TITLES = {"1": "SQL с нуля", "2": "SQL углублённый"}


def make_pick(course_id: str, contribution: float) -> Pick:
    course = CourseData(id=course_id, ranges=[Range("SQL", 0, 40)])
    return Pick(course, score=50, contribution=contribution)


PICKS = [make_pick("1", 0.4), make_pick("2", 0.3)]
ONE = PICKS[:1]


def answer(*texts) -> str:
    items = [{"n": i, "text": t} for i, t in enumerate(texts, start=1)]
    return json.dumps({"items": items}, ensure_ascii=False)


def templates(picks=PICKS) -> list[str]:
    facts = rationale.collect_facts(picks, TITLES, GAPS)
    return [rationale.template_text(f) for f in facts]


# ---------- функция explain ----------


def test_prompt_contains_facts(fake_llm):
    rationale.explain(PICKS, TITLES, GAPS)
    call = fake_llm.calls[0]
    assert "SQL с нуля" in call["user"] and "SQL углублённый" in call["user"]
    assert "40%" in call["user"] and "10" in call["user"]
    assert "JSON" in call["system"]


def test_llm_text_is_used(fake_llm):
    fake_llm.answers = [answer("Закроет базу по SQL.", "Подтянет запросы.")]
    assert rationale.explain(PICKS, TITLES, GAPS) == [
        "Закроет базу по SQL.",
        "Подтянет запросы.",
    ]


def test_one_request_for_all_courses(fake_llm):
    fake_llm.answers = [answer("Раз.", "Два.")]
    rationale.explain(PICKS, TITLES, GAPS)
    assert len(fake_llm.calls) == 1


def test_answer_in_fence_is_parsed(fake_llm):
    fake_llm.answers = [f"Вот:\n```json\n{answer('Раз.', 'Два.')}\n```"]
    assert rationale.explain(PICKS, TITLES, GAPS) == ["Раз.", "Два."]


def test_course_missing_in_answer_gets_template(fake_llm):
    fake_llm.answers = [answer("Только первое.")]
    texts = rationale.explain(PICKS, TITLES, GAPS)
    assert texts[0] == "Только первое."
    assert texts[1] == templates()[1]


def test_llm_unavailable_gives_templates(fake_llm):
    fake_llm.answers = [LLMUnavailable("нет сети")]
    assert rationale.explain(PICKS, TITLES, GAPS) == templates()


@pytest.mark.parametrize("bad", ["не знаю", '{"items": 5}', '{"other": 1}'])
def test_unusable_answer_gives_templates(fake_llm, bad):
    fake_llm.answers = [bad]
    assert rationale.explain(PICKS, TITLES, GAPS) == templates()


@pytest.mark.parametrize(
    "item",
    [
        {"n": 1, "text": "   "},  # пустой текст
        {"n": 5, "text": "Текст"},  # такого курса в наборе нет
        {"n": 1, "text": 123},  # текст не строка
        {"n": "a", "text": "Текст"},  # номер не число
    ],
)
def test_bad_items_get_templates(fake_llm, item):
    fake_llm.answers = [json.dumps({"items": [item]}, ensure_ascii=False)]
    assert rationale.explain(ONE, TITLES, GAPS) == templates(ONE)


def test_text_with_foreign_skill_is_replaced(fake_llm):
    fake_llm.answers = [answer("Научит работать с Docker.", "Хороший курс по SQL.")]
    texts = rationale.explain(PICKS, TITLES, GAPS)
    assert texts[0] == templates()[0]  # Docker у этого курса нет
    assert texts[1] == "Хороший курс по SQL."


def test_no_picks_means_no_request(fake_llm):
    assert rationale.explain([], {}, {}) == []
    assert fake_llm.calls == []


def test_template_mentions_share_and_skill():
    text = templates(ONE)[0]
    assert "40%" in text and "SQL" in text


# ---------- через настоящий /recommendations ----------


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


def load_catalog(client) -> None:
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    assert client.post("/admin/courses/import", json=sample).status_code == 200
    drafts = client.get("/admin/courses", params={"status": "draft", "limit": 200}).json()
    for item in drafts["items"]:
        assert client.post(f"/admin/courses/{item['id']}/publish").status_code == 200


BODY = {
    "user_id": "demo-weak",
    "preferences": {"max_price": 5000, "languages": ["ru"], "hours_per_week": 8},
}


def test_endpoint_returns_llm_rationale(client, fake_llm):
    load_catalog(client)
    fake_llm.answers = [answer("Первое.", "Второе.", "Третье.")]
    data = client.post("/recommendations", json=BODY).json()
    assert [c["rationale"] for c in data["courses"]] == ["Первое.", "Второе.", "Третье."]
    assert len(fake_llm.calls) == 1  # один запрос на весь набор


def test_endpoint_works_when_llm_is_down(client, fake_llm):
    load_catalog(client)
    fake_llm.answers = [LLMUnavailable("нет сети")]
    response = client.post("/recommendations", json=BODY)
    assert response.status_code == 200
    courses = response.json()["courses"]
    assert len(courses) == 3
    assert all(c["rationale"].startswith("Закрывает около") for c in courses)