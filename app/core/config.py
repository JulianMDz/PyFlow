from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://payflow:payflow@localhost:5432/payflow"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "qwen/qwen3.8-27b"
    API_V1_PREFIX: str = "/api/v1"
    SQL_ECHO: bool = False
    # Browser origins allowed to call the API (the Vite dev server by default).
    # localhost and 127.0.0.1 are different origins for the browser, so both are listed.
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
