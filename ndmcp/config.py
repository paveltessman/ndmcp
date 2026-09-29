# pyright: strict
import os
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator
from pydantic import HttpUrl
from pydantic import SecretStr
from pydantic import ValidationError

from ndmcp.exceptions import NdmcpException

ENV_PREFIX = "NDMCP_"

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class ConfigError(NdmcpException):
    """A setting is missing or has a value that is not valid."""


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: HttpUrl
    username: str
    password: SecretStr

    # HTTP timeout for one Subsonic request, in seconds.
    timeout: float = Field(default=10.0, gt=0)

    cache_ttl: float = Field(default=300.0, ge=0)
    verify_tls: bool = True
    log_level: LogLevel = "INFO"

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value


def env_name(field: str) -> str:
    return ENV_PREFIX + field.upper()


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if environ is None else environ
    raw = {
        field: env[env_name(field)]
        for field in Settings.model_fields
        if env.get(env_name(field))
    }
    try:
        return Settings.model_validate(raw)
    except ValidationError as error:
        raise ConfigError(_describe(error)) from None


def _describe(error: ValidationError) -> str:
    lines: list[str] = []
    for item in error.errors(include_input=False):
        name = env_name(str(item["loc"][0]))
        if item["type"] == "missing":
            lines.append(f"{name} is not set.")
        else:
            lines.append(f"{name} is not valid: {item['msg']}.")
    return "\n".join(lines)
