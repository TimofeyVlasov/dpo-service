import pytest

from app.services import llm


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
def fake_llm():
    fake = FakeLLM()
    llm.set_llm(fake)
    yield fake
    llm.set_llm(None)