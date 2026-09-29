import hashlib
from collections.abc import Callable

import httpx2
import pytest

from ndmcp.config import Settings
from ndmcp.subsonic import SubsonicClient
from ndmcp.subsonic import SubsonicError

pytestmark = pytest.mark.anyio

SETTINGS = Settings.model_validate(
    {
        "url": "https://music.example.com",
        "username": "user",
        "password": "hunter2",
        "timeout": 2.5,
    }
)

Handler = Callable[[httpx2.Request], httpx2.Response]


def make_client(handler: Handler, settings: Settings = SETTINGS) -> SubsonicClient:
    return SubsonicClient(settings, transport=httpx2.MockTransport(handler))


def reply(status: str = "ok", **payload: object) -> httpx2.Response:
    body = {"status": status, "version": "1.16.1"} | payload
    return httpx2.Response(200, json={"subsonic-response": body})


async def test_ping_sends_auth_params():
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return reply()

    async with make_client(handler) as client:
        await client.ping()

    [request] = requests
    params = request.url.params
    salt = params["s"]
    assert request.url.path == "/rest/ping"
    assert params["u"] == "user"
    assert params["t"] == hashlib.md5(b"hunter2" + salt.encode()).hexdigest()
    assert params["v"] == "1.16.1"
    assert params["c"] == "ndmcp"
    assert params["f"] == "json"
    assert "hunter2" not in str(request.url)


async def test_each_request_has_new_salt():
    salts: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        salts.append(request.url.params["s"])
        return reply()

    async with make_client(handler) as client:
        await client.ping()
        await client.ping()

    assert salts[0] != salts[1]


async def test_url_path_is_kept():
    paths: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        paths.append(request.url.path)
        return reply()

    settings = Settings.model_validate(
        SETTINGS.model_dump() | {"url": "https://example.com/navidrome"}
    )
    async with make_client(handler, settings) as client:
        await client.ping()

    assert paths == ["/navidrome/rest/ping"]


async def test_timeout_setting_is_used():
    timeouts: list[object] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        timeouts.append(request.extensions["timeout"])
        return reply()

    async with make_client(handler) as client:
        await client.ping()

    assert timeouts == [{"connect": 2.5, "read": 2.5, "write": 2.5, "pool": 2.5}]


async def test_get_returns_payload():
    def handler(_: httpx2.Request) -> httpx2.Response:
        return reply(genres={"genre": []})

    async with make_client(handler) as client:
        payload = await client._get("getGenres", None)

    assert payload == {"version": "1.16.1", "genres": {"genre": []}}


async def test_failed_status_gives_code_and_message():
    def handler(_: httpx2.Request) -> httpx2.Response:
        return reply(
            "failed", error={"code": 40, "message": "Wrong username or password"}
        )

    async with make_client(handler) as client:
        with pytest.raises(SubsonicError) as info:
            await client.ping()

    assert info.value.code == 40
    assert str(info.value) == (
        "Subsonic request ping failed: Wrong username or password (code 40)."
    )


async def test_failed_status_without_details():
    def handler(_: httpx2.Request) -> httpx2.Response:
        return reply("failed")

    async with make_client(handler) as client:
        with pytest.raises(SubsonicError) as info:
            await client.ping()

    assert info.value.code == 0


async def test_http_error_status():
    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(500)

    async with make_client(handler) as client:
        with pytest.raises(SubsonicError) as info:
            await client.ping()

    assert str(info.value) == "Subsonic request ping failed with HTTP 500."
    assert info.value.code is None


@pytest.mark.parametrize(
    "content",
    [b"<html></html>", b'{"status": "ok"}', b"[]"],
)
async def test_reply_that_is_not_subsonic(content: bytes):
    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=content)

    async with make_client(handler) as client:
        with pytest.raises(SubsonicError) as info:
            await client.ping()

    assert str(info.value) == (
        "Subsonic request ping failed: the reply is not a Subsonic response."
    )


async def test_timeout():
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("timed out", request=request)

    async with make_client(handler) as client:
        with pytest.raises(SubsonicError) as info:
            await client.ping()

    assert str(info.value) == "Subsonic request ping timed out."


async def test_connect_error_hides_the_url():
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError(f"cannot reach {request.url}", request=request)

    async with make_client(handler) as client:
        with pytest.raises(SubsonicError) as info:
            await client.ping()

    assert str(info.value) == "Subsonic request ping failed: ConnectError."
    assert info.value.__cause__ is None
    assert info.value.__suppress_context__ is True
