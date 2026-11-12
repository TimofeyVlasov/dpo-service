import json
import time

import httpx
import pytest

from app.core.config import Settings
from app.services import llm
from app.services.llm import GigaChatClient, LLMUnavailable


def make_cfg(**changes) -> Settings:
    data = {"gigachat_credentials": "test-key", "gigachat_scope": "GIGACHAT_API_PERS"}
    data.update(changes)
    return Settings(**data)


class MockGiga:
    """Изображает сервер GigaChat: считает запросы и отдаёт заготовленные ответы."""

    def __init__(self, token_lifetime_s=1800, chat_statuses=None, chat_text="ответ"):
        self.oauth_calls = []
        self.chat_calls = []
        self.token_lifetime_s = token_lifetime_s
        self.chat_statuses = list(chat_statuses or [])
        self.chat_text = chat_text
        self.issued = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth"):
            self.oauth_calls.append(request)
            self.issued += 1
            expires_ms = int((time.time() + self.token_lifetime_s) * 1000)
            return httpx.Response(
                200, json={"access_token": f"tok-{self.issued}", "expires_at": expires_ms}
            )
        self.chat_calls.append(request)
        status = self.chat_statuses.pop(0) if self.chat_statuses else 200
        if status != 200:
            return httpx.Response(status, json={"message": "error"})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": self.chat_text}}]},
        )


def client_with(handler, **cfg) -> GigaChatClient:
    return GigaChatClient(make_cfg(**cfg), transport=httpx.MockTransport(handler))


def test_complete_returns_model_text():
    mock = MockGiga(chat_text="Привет!")
    assert client_with(mock).complete("Скажи привет") == "Привет!"


def test_request_has_expected_shape():
    mock = MockGiga()
    client_with(mock).complete("вопрос", system="инструкция", temperature=0.1, max_tokens=50)

    oauth = mock.oauth_calls[0]
    assert oauth.headers["Authorization"] == "Basic test-key"
    assert "RqUID" in oauth.headers
    assert b"scope=GIGACHAT_API_PERS" in oauth.content

    chat = mock.chat_calls[0]
    assert chat.headers["Authorization"] == "Bearer tok-1"
    body = json.loads(chat.content)
    assert body["model"] == "GigaChat"
    assert body["messages"] == [
        {"role": "system", "content": "инструкция"},
        {"role": "user", "content": "вопрос"},
    ]
    assert body["temperature"] == 0.1 and body["max_tokens"] == 50


def test_token_is_cached_between_calls():
    mock = MockGiga()
    client = client_with(mock)
    client.complete("a")
    client.complete("b")
    assert len(mock.oauth_calls) == 1
    assert len(mock.chat_calls) == 2


def test_expired_token_is_refreshed():
    mock = MockGiga(token_lifetime_s=0)  # токен «живёт» 0 секунд
    client = client_with(mock)
    client.complete("a")
    client.complete("b")
    assert len(mock.oauth_calls) == 2


def test_401_triggers_one_retry_with_new_token():
    mock = MockGiga(chat_statuses=[401, 200])
    assert client_with(mock).complete("a") == "ответ"
    assert len(mock.oauth_calls) == 2
    assert mock.chat_calls[1].headers["Authorization"] == "Bearer tok-2"


def test_repeated_401_is_error():
    mock = MockGiga(chat_statuses=[401, 401])
    with pytest.raises(LLMUnavailable):
        client_with(mock).complete("a")


def test_server_error_is_llm_unavailable():
    with pytest.raises(LLMUnavailable):
        client_with(MockGiga(chat_statuses=[500])).complete("a")


def test_missing_credentials_is_llm_unavailable():
    mock = MockGiga()
    with pytest.raises(LLMUnavailable, match="GIGACHAT_CREDENTIALS"):
        client_with(mock, gigachat_credentials="").complete("a")
    assert not mock.oauth_calls and not mock.chat_calls


def test_network_failure_is_llm_unavailable():
    def broken(request):
        raise httpx.ConnectError("нет сети")

    with pytest.raises(LLMUnavailable):
        client_with(broken).complete("a")


def test_unexpected_answer_format_is_llm_unavailable():
    def weird(request):
        if request.url.path.endswith("/oauth"):
            return httpx.Response(
                200, json={"access_token": "t", "expires_at": int((time.time() + 1800) * 1000)}
            )
        return httpx.Response(200, json={"oops": 1})

    with pytest.raises(LLMUnavailable):
        client_with(weird).complete("a")


def test_tests_never_get_real_client(fake_llm):
    assert llm.get_llm() is fake_llm


def test_fake_returns_queued_answers_and_records_calls(fake_llm):
    fake_llm.answers = ["первый", RuntimeError("упал")]
    assert llm.get_llm().complete("q1") == "первый"
    with pytest.raises(RuntimeError):
        llm.get_llm().complete("q2")
    assert [c["user"] for c in fake_llm.calls] == ["q1", "q2"]