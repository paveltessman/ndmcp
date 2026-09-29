# pyright: strict
import hashlib
import secrets
from collections.abc import Mapping
from types import TracebackType
from typing import Any

import httpx2
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import ValidationError

from ndmcp.config import Settings
from ndmcp.exceptions import NdmcpException

API_VERSION = "1.16.1"
CLIENT_NAME = "ndmcp"

Params = Mapping[str, str | int]


class SubsonicError(NdmcpException):
    """A Subsonic request failed, or the server replied with an error."""

    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class _Error(BaseModel):
    code: int
    message: str = ""


class _Envelope(BaseModel):
    # The endpoint payload, for example "genres", stays in the extra fields.
    model_config = ConfigDict(extra="allow")

    status: str
    error: _Error | None = None


class _Reply(BaseModel):
    body: _Envelope = Field(alias="subsonic-response")


class SubsonicClient:
    def __init__(
        self,
        settings: Settings,
        transport: httpx2.AsyncBaseTransport | None,
    ) -> None:
        self._username = settings.username
        self._password = settings.password
        self._http = httpx2.AsyncClient(
            base_url=str(settings.url).rstrip("/") + "/rest/",
            timeout=settings.timeout,
            verify=settings.verify_tls,
            transport=transport,
        )

    async def __aenter__(self) -> "SubsonicClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        _ = exc_type
        _ = exc
        _ = traceback
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def ping(self) -> None:
        await self._get("ping", None)

    async def _get(self, endpoint: str, params: Params | None) -> dict[str, Any]:
        response = await self._send(endpoint, params or {})
        return _unwrap(endpoint, response)

    async def _send(self, endpoint: str, params: Params) -> httpx2.Response:
        query = {**self._auth_params(), **params}
        # The URL holds the auth token. The errors below do not show the URL,
        # and "from None" drops the httpx2 error that shows it.
        try:
            response = await self._http.get(endpoint, params=query)
        except httpx2.TimeoutException:
            raise SubsonicError(f"Subsonic request {endpoint} timed out.") from None
        except httpx2.RequestError as error:
            name = type(error).__name__
            raise SubsonicError(
                f"Subsonic request {endpoint} failed: {name}."
            ) from None
        if response.is_error:
            raise SubsonicError(
                f"Subsonic request {endpoint} failed with HTTP {response.status_code}."
            )
        return response

    def _auth_params(self) -> dict[str, str]:
        # Each request gets a new salt, so each token is different.
        salt = secrets.token_hex(8)
        secret = self._password.get_secret_value() + salt
        token = hashlib.md5(secret.encode(), usedforsecurity=False).hexdigest()
        return {
            "u": self._username,
            "t": token,
            "s": salt,
            "v": API_VERSION,
            "c": CLIENT_NAME,
            "f": "json",
        }


def _unwrap(endpoint: str, response: httpx2.Response) -> dict[str, Any]:
    try:
        body = _Reply.model_validate_json(response.content).body
    except ValidationError:
        raise SubsonicError(
            f"Subsonic request {endpoint} failed: "
            "the reply is not a Subsonic response."
        ) from None
    if body.status != "ok":
        error = body.error or _Error(code=0, message="no error details")
        raise SubsonicError(
            f"Subsonic request {endpoint} failed: {error.message} "
            f"(code {error.code}).",
            code=error.code,
        )
    return body.model_extra or {}
