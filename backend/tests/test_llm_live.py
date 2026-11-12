import pytest

from app.core.config import settings
from app.services.llm import GigaChatClient

pytestmark = pytest.mark.live


@pytest.mark.skipif(not settings.gigachat_credentials, reason="нет GIGACHAT_CREDENTIALS в .env")
def test_real_gigachat_answers():
    # клиент создаём напрямую, мимо подмены, так что запрос уходит по-настоящему
    answer = GigaChatClient(settings).complete("Ответь одним словом: привет", max_tokens=20)
    assert answer.strip()