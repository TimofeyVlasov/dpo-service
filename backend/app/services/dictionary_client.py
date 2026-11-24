import httpx
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from app.core.config import settings
from app.services.dictionary_stub import DICTIONARY, SkillInfo


class DictionaryUnavailable(Exception):
    """Сервис справочника недоступен."""


class InvalidDictionaryResponse(Exception):
    """Ответ сервиса справочника нельзя использовать."""


class RemoteCompetency(BaseModel):
    code: str = Field(min_length=1)
    direction: str = Field(min_length=1)
    target: int = Field(strict=True, ge=0, le=100)
    importance: int = Field(strict=True, ge=1, le=3)
    is_active: bool = Field(strict=True)


COMPETENCIES = TypeAdapter(list[RemoteCompetency])


def fetch_dictionary(
    base_url: str,
    timeout: float,
    *,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, SkillInfo]:
    url = f"{base_url.rstrip('/')}/profile/getAccType"

    try:
        with httpx.Client(timeout=timeout, transport=transport) as client:
            response = client.get(url)
    except httpx.RequestError as error:
        raise DictionaryUnavailable("не удалось связаться со справочником") from error

    if response.status_code == 429 or response.status_code >= 500:
        raise DictionaryUnavailable("сервис справочника временно недоступен")
    if response.status_code != 200:
        raise InvalidDictionaryResponse("неожиданный статус ответа справочника")

    try:
        entries = COMPETENCIES.validate_json(response.content)
    except ValidationError as error:
        raise InvalidDictionaryResponse("ожидался список компетенций") from error

    result: dict[str, SkillInfo] = {}
    for entry in entries:
        if not entry.is_active:
            continue

        code = entry.code.strip().upper()
        direction = entry.direction.strip().upper()
        if not code or not direction:
            raise InvalidDictionaryResponse("пустой код навыка или направления")
        if code in result:
            raise InvalidDictionaryResponse(f"повторяется код навыка {code}")

        result[code] = SkillInfo(
            direction=direction,
            target=entry.target,
            importance=entry.importance,
        )

    return result


def get_dictionary() -> dict[str, SkillInfo]:
    base_url = settings.accreditation_base_url
    if base_url is None:
        return DICTIONARY.copy()

    return fetch_dictionary(str(base_url), settings.accreditation_timeout)