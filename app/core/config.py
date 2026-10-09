import json
from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import make_url

# libpq options that asyncpg doesn't understand; sslmode is translated, the rest are dropped
_LIBPQ_ONLY_OPTIONS = ("sslmode", "channel_binding")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://payflow:payflow@localhost:5432/payflow"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "qwen/qwen3.8-27b"
    API_V1_PREFIX: str = "/api/v1"
    SQL_ECHO: bool = False
    # Browser origins allowed to call the API (the Vite dev server by default).
    # localhost and 127.0.0.1 are different origins for the browser, so both are listed.
    # Accepts a JSON list or comma-separated origins.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    # Public demo: reject every write except risk checks, so visitors can't fill the data with junk
    DEMO_MODE: bool = False
    # Risk checks allowed per client IP and minute; 0 disables the limit
    RISK_CHECKS_PER_MINUTE: int = 0

    @field_validator("DATABASE_URL")
    @classmethod
    def use_asyncpg_driver(cls, url: str) -> str:
        """Hosting providers hand out libpq URLs (postgres://…?sslmode=require); asyncpg needs its own."""
        parsed = make_url(url)
        if parsed.drivername in ("postgres", "postgresql"):
            parsed = parsed.set(drivername="postgresql+asyncpg")
        if parsed.drivername != "postgresql+asyncpg":
            return url
        sslmode = parsed.query.get("sslmode")
        parsed = parsed.difference_update_query(_LIBPQ_ONLY_OPTIONS)
        if isinstance(sslmode, str) and "ssl" not in parsed.query:
            parsed = parsed.update_query_dict({"ssl": sslmode})
        return parsed.render_as_string(hide_password=False)

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                return json.loads(text)
            return [origin.strip() for origin in text.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
