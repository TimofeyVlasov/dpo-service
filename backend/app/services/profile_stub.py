"""ЗАГЛУШКА профиля. Позже вместо неё будет запрос к модулю аккредитации."""

from app.schemas.profile import Profile, SkillLevel


class ProfileNotFound(Exception):
    pass


STUB_PROFILES: dict[str, Profile] = {
    # слабый почти везде: есть что подтягивать
    "demo-weak": Profile(
        user_id="demo-weak",
        direction="BACKEND",
        skills=[
            SkillLevel(skill="PYTHON", level=30, target=70),
            SkillLevel(skill="SQL", level=20, target=70),
            SkillLevel(skill="ASYNC", level=25, target=60),
            SkillLevel(skill="DOCKER", level=10, target=60),
            SkillLevel(skill="GIT", level=65, target=60),
        ],
    ),
    # слабое место только одно
    "demo-sql": Profile(
        user_id="demo-sql",
        direction="BACKEND",
        skills=[
            SkillLevel(skill="PYTHON", level=75, target=70),
            SkillLevel(skill="SQL", level=35, target=70),
        ],
    ),
    # пробелов нет
    "demo-strong": Profile(
        user_id="demo-strong",
        direction="BACKEND",
        skills=[
            SkillLevel(skill="PYTHON", level=80, target=70),
            SkillLevel(skill="SQL", level=75, target=70),
        ],
    ),
}


def get_profile(user_id: str) -> Profile: # ищет человека в словаре и возвращает его профиль
    profile = STUB_PROFILES.get(user_id)
    if profile is None:
        raise ProfileNotFound(user_id)
    return profile