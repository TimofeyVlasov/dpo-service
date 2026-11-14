import pytest

from app.core.config import settings
from app.services import llm, rationale
from app.services.llm import GigaChatClient
from app.services.matching import CourseData, Gap, Pick, Range

pytestmark = pytest.mark.live


@pytest.mark.skipif(not settings.gigachat_credentials, reason="нет GIGACHAT_CREDENTIALS в .env")
def test_real_gigachat_explains_pick():
    llm.set_llm(GigaChatClient(settings))  # вместо заглушки; после теста её уберёт conftest
    gaps = {"SQL": Gap(level=10, target=70, gap=60, urgency=1.0)}
    titles = {"1": "SQL углублённый"}
    picks = [Pick(CourseData(id="1", ranges=[Range("SQL", 40, 80)]), score=60, contribution=0.5)]

    texts = rationale.explain(picks, titles, gaps)
    facts = rationale.collect_facts(picks, titles, gaps)

    print(texts[0])
    assert texts[0] != rationale.template_text(facts[0]), "вернулась шаблонная фраза"