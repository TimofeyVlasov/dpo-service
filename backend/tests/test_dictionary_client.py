import httpx
import pytest

from app.services.dictionary_client import (
    DictionaryUnavailable,
    InvalidDictionaryResponse,
    fetch_dictionary,
)
from app.services.dictionary_stub import SkillInfo


SQL = {
    "code": "sql",
    "name": "Работа с реляционными БД",
    "direction": "backend",
    "target": 70,
    "importance": 3,
    "is_active": True,
    "skills": [{"code": "JOIN", "name": "Соединения таблиц"}],
}


def fetch_with(handler):
    return fetch_dictionary(
        "http://accreditation.test/",
        5.0,
        transport=httpx.MockTransport(handler),
    )


def test_fetch_dictionary_reads_active_skills():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/profile/getAccType"
        assert request.url.query == b""

        inactive = {**SQL, "code": "GIT", "is_active": False}
        return httpx.Response(200, json=[SQL, inactive])

    assert fetch_with(handler) == {"SQL": SkillInfo("BACKEND", 70, 3)}


@pytest.mark.parametrize(
    "payload",
    [
        {"competencies": [SQL]},
        [{**SQL, "importance": 4}],
        [SQL, {**SQL, "code": "SQL"}],
    ],
)
def test_fetch_dictionary_rejects_invalid_payload(payload):
    with pytest.raises(InvalidDictionaryResponse):
        fetch_with(lambda request: httpx.Response(200, json=payload))


@pytest.mark.parametrize(
    "status_code, expected_error",
    [
        (500, DictionaryUnavailable),
        (404, InvalidDictionaryResponse),
    ],
)
def test_fetch_dictionary_handles_http_errors(status_code, expected_error):
    with pytest.raises(expected_error):
        fetch_with(lambda request: httpx.Response(status_code))


def test_fetch_dictionary_handles_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("сервис не ответил", request=request)

    with pytest.raises(DictionaryUnavailable):
        fetch_with(handler)