import pytest

from app.core.config import settings
from app.models import Course
from app.services import markup
from app.services.llm import GigaChatClient

pytestmark = pytest.mark.live


@pytest.mark.skipif(not settings.gigachat_credentials, reason="нет GIGACHAT_CREDENTIALS в .env")
def test_real_gigachat_marks_sql_course():
    course = Course(
        title="SQL углублённый",
        description="Подзапросы, индексы, транзакции, проектирование таблиц.",
        level_label="intermediate",
    )
    skill_codes = {"SQL"}
    system, user = markup.build_prompt(course, skill_codes)
    answer = GigaChatClient(settings).complete(user, system, temperature=0.1, max_tokens=500)
    ranges = markup.parse_answer(answer, skill_codes)
    assert any(r["skill"] == "SQL" for r in ranges), answer
