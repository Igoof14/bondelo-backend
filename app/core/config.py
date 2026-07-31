from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["local", "prod"] = "local"
    debug: bool = False

    database_url: PostgresDsn
    db_echo: bool = False

    # Cloud Run injects PORT; the container must listen on it.
    port: int = 8080

    cors_origins: list[str] = Field(default_factory=list)

    # T-Invest REST API — used to check a token is alive before it is stored.
    tinvest_api_url: str = "https://invest-public-api.tbank.ru/rest"
    tinvest_timeout_seconds: float = 5.0

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]  # values come from env
