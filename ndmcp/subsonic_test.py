import hashlib
from collections.abc import Callable

import httpx2
import pytest

from ndmcp import subsonic
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


def song(number: int) -> dict[str, object]:
    return {"id": f"s{number}", "title": f"Song {number}"}


def search_handler(requests: list[httpx2.Request], sizes: list[int]) -> Handler:
    # Each reply has the next number of songs from sizes.
    def handler(request: httpx2.Request) -> httpx2.Response:
        start = int(request.url.params["songOffset"])
        size = sizes[len(requests)]
        requests.append(request)
        songs = [song(number) for number in range(start, start + size)]
        return reply(searchResult3={"song": songs})

    return handler


async def test_songs_pages_through_search3(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(subsonic, "PAGE_SIZE", 2)
    requests: list[httpx2.Request] = []

    async with make_client(search_handler(requests, [2, 2, 1])) as client:
        songs = await client.songs()

    assert [s.id for s in songs] == ["s0", "s1", "s2", "s3", "s4"]
    assert [r.url.params["songOffset"] for r in requests] == ["0", "2", "4"]
    for request in requests:
        assert request.url.path == "/rest/search3"
        assert request.url.params["query"] == ""
        assert request.url.params["songCount"] == "2"
        assert request.url.params["albumCount"] == "0"
        assert request.url.params["artistCount"] == "0"


async def test_songs_stop_on_empty_page_after_full_page(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(subsonic, "PAGE_SIZE", 2)
    requests: list[httpx2.Request] = []

    async with make_client(search_handler(requests, [2, 0])) as client:
        songs = await client.songs()

    assert len(songs) == 2
    assert len(requests) == 2


@pytest.mark.parametrize(
    "response",
    [reply(), reply(searchResult3={})],
)
async def test_songs_of_empty_library(response: httpx2.Response):
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return response

    async with make_client(handler) as client:
        songs = await client.songs()

    assert songs == []
    assert len(requests) == 1


async def test_artists_use_artist_page():
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        artist = {"id": "ar1", "name": "Sigur Rós"}
        return reply(searchResult3={"artist": [artist]})

    async with make_client(handler) as client:
        artists = await client.artists()

    assert [a.name for a in artists] == ["Sigur Rós"]
    [request] = requests
    assert request.url.params["artistCount"] == "500"
    assert request.url.params["artistOffset"] == "0"
    assert request.url.params["albumCount"] == "0"
    assert request.url.params["songCount"] == "0"


async def test_albums_use_album_page():
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        album = {"id": "al1", "name": "Ágætis byrjun"}
        return reply(searchResult3={"album": [album]})

    async with make_client(handler) as client:
        albums = await client.albums()

    assert [a.name for a in albums] == ["Ágætis byrjun"]
    [request] = requests
    assert request.url.params["albumCount"] == "500"
    assert request.url.params["albumOffset"] == "0"
    assert request.url.params["artistCount"] == "0"
    assert request.url.params["songCount"] == "0"


async def test_genres():
    paths: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        paths.append(request.url.path)
        genre = {"value": "Post-Rock", "songCount": 25, "albumCount": 3}
        return reply(genres={"genre": [genre]})

    async with make_client(handler) as client:
        genres = await client.genres()

    assert paths == ["/rest/getGenres"]
    assert [(g.name, g.song_count, g.album_count) for g in genres] == [
        ("Post-Rock", 25, 3)
    ]


async def test_genres_of_empty_library():
    def handler(_: httpx2.Request) -> httpx2.Response:
        return reply(genres={})

    async with make_client(handler) as client:
        assert await client.genres() == []


async def test_payload_with_unexpected_format():
    def handler(_: httpx2.Request) -> httpx2.Response:
        return reply(searchResult3={"song": [{"title": "No id"}]})

    async with make_client(handler) as client:
        with pytest.raises(SubsonicError) as info:
            await client.songs()

    assert str(info.value) == (
        "Subsonic request search3 failed: the reply has an unexpected format."
    )


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
