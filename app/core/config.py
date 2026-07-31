from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict
from t_tech.invest.constants import INVEST_GRPC_API


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["local", "prod"] = "local"
    debug: bool = False

    database_url: PostgresDsn
    db_echo: bool = False

    # Cloud Run injects PORT; the container must listen on it.
    port: int = 8080

    cors_origins: list[str] = Field(default_factory=list)

    # T-Invest gRPC API — used to check a token is alive before it is stored. The default
    # is the SDK's own production endpoint; override it to reach the sandbox.
    tinvest_grpc_target: str = INVEST_GRPC_API
    tinvest_timeout_seconds: float = 5.0

    # T-Invest is served under the Russian Trusted Root CA, which is in no default trust
    # store — without this the TLS handshake fails. The SDK ships that root and reads this
    # exact variable out of the environment, so `lifespan` puts the value back there.
    ssl_tbank_verify: bool = True

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]  # values come from env
