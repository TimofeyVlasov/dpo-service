from pathlib import Path
from pydantic import AnyHttpUrl

from pydantic_settings import BaseSettings, SettingsConfigDict

# папка backend (файл лежит в backend/app/core/, поднимаемся на два уровня)
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://dpo:dpo@localhost:5432/dpo"

    # GigaChat: ключ авторизации берётся из .env, остальное можно не трогать
    gigachat_credentials: str = ""
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_model: str = "GigaChat"
    gigachat_timeout: float = 30.0  # секунд на один запрос
    gigachat_ca_bundle: str = str(
        BACKEND_DIR / "certs" / "russian_trusted_root_ca_pem.crt"
    )

    accreditation_base_url: AnyHttpUrl | None = None
    accreditation_timeout: float = 5.0
    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()