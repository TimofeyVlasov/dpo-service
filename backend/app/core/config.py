from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://dpo:dpo@localhost:5432/dpo"
    deepseek_api_key: str = ""

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()