from uuid import UUID

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.config import settings
from app.schemas.profile import Profile, SkillLevel
from app.services import profile_stub
from app.services.profile_stub import ProfileNotFound


class ProfileUnavailable(Exception):
    """Сервис аккредитации недоступен."""


class InvalidProfileResponse(Exception):
    """Ответ сервиса аккредитации нельзя использовать."""


class RemoteSkill(BaseModel):
    skill: str = Field(min_length=1)
    rating: int = Field(strict=True, ge=0, le=100)
    target: int = Field(strict=True, ge=0, le=100)
    direction: str | None = None


class RemoteProfile(BaseModel):
    userId: UUID
    area: str
    competencies: list[RemoteSkill] | None


class RemoteProfileEnvelope(BaseModel):
    data: RemoteProfile


def to_profile(data: RemoteProfile, requested_id: UUID) -> Profile:
    if data.userId != requested_id:
        raise InvalidProfileResponse("ID в ответе не совпадает с запрошенным")

    direction = data.area.strip().upper()
    if direction in {"", "NONE", "NULL"}:
        raise InvalidProfileResponse("у сотрудника не указано направление")

    skills: list[SkillLevel] = []
    seen: set[str] = set()

    for item in data.competencies or []:
        if item.direction and item.direction.strip().upper() != direction:
            continue

        code = item.skill.strip().upper()
        if not code or code in seen:
            raise InvalidProfileResponse("пустой или повторяющийся код навыка")

        seen.add(code)
        skills.append(SkillLevel(skill=code, level=item.rating, target=item.target))

    return Profile(user_id=str(data.userId), direction=direction, skills=skills)


def fetch_profile(
    user_id: str,
    base_url: str,
    timeout: float,
    *,
    transport: httpx.BaseTransport | None = None,
) -> Profile:
    try:
        requested_id = UUID(user_id)
    except ValueError as error:
        raise ProfileNotFound(user_id) from error

    url = f"{base_url.rstrip('/')}/dpo/{requested_id}/latest"
    try:
        with httpx.Client(timeout=timeout, transport=transport) as client:
            response = client.get(url)
    except httpx.RequestError as error:
        raise ProfileUnavailable("не удалось связаться с сервисом") from error

    if response.status_code in (204, 404):
        raise ProfileNotFound(user_id)
    if response.status_code >= 500:
        raise ProfileUnavailable("сервис аккредитации вернул ошибку")
    if response.status_code != 200:
        raise InvalidProfileResponse("неожиданный статус ответа")

    try:
        payload = response.json()
        if isinstance(payload, dict) and "data" in payload:
            data = RemoteProfileEnvelope.model_validate(payload).data
        else:
            data = RemoteProfile.model_validate(payload)
    except (ValueError, ValidationError) as error:
        raise InvalidProfileResponse("ответ не соответствует формату профиля") from error

    return to_profile(data, requested_id)


def get_profile(user_id: str) -> Profile:
    base_url = settings.accreditation_base_url
    if base_url is None:
        return profile_stub.get_profile(user_id)

    return fetch_profile(user_id, str(base_url), settings.accreditation_timeout)