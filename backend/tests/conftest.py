import pytest

from app.services import llm
from app.core.config import settings

from functools import partial

import httpx

from app.services import dictionary_client


class FakeLLM:
    """Подставной вместо GigaChat. В сеть не ходит.

    answers: очередь ответов; элемент-исключение будет выброшено.
    calls: что у нас спрашивали (для проверок в тестах).
    """

    def __init__(self):
        self.answers: list = []
        self.calls: list[dict] = []

    def complete(self, user, system="", *, temperature=0.2, max_tokens=1000):
        self.calls.append({"user": user, "system": system})
        if not self.answers:
            return "Заглушка: в тестах нейросеть не вызывается."
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture(autouse=True)
def use_demo_profiles_by_default(monkeypatch):
    monkeypatch.setattr(settings, "accreditation_base_url", None)

@pytest.fixture(autouse=True)
def fake_llm():
    fake = FakeLLM()
    llm.set_llm(fake)
    yield fake
    llm.set_llm(None)

@pytest.fixture
def use_remote_dictionary(monkeypatch, use_demo_profiles_by_default):
    original_fetch = dictionary_client.fetch_dictionary

    def setup(handler):
        monkeypatch.setattr(
            settings,
            "accreditation_base_url",
            "http://accreditation.test",
        )
        monkeypatch.setattr(
            dictionary_client,
            "fetch_dictionary",
            partial(original_fetch, transport=httpx.MockTransport(handler)),
        )

    return setup