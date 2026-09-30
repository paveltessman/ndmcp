from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp import Client

from ndmcp.config import env_name
from ndmcp.config import Settings
from ndmcp.models import Album
from ndmcp.models import Artist
from ndmcp.models import Genre
from ndmcp.models import Song
from ndmcp.server import create_server
from ndmcp.server import main
from ndmcp.subsonic import SubsonicClient
from ndmcp.subsonic import SubsonicError

SETTINGS = Settings.model_validate(
    {
        "url": "https://music.example.com",
        "username": "user",
        "password": "hunter2",
    }
)

SIGUR_ROS = Artist.model_validate({"id": "ar1", "name": "Sigur Rós"})
MUM = Artist.model_validate({"id": "ar2", "name": "múm"})

TAKK = Album.model_validate(
    {"id": "al1", "name": "Takk...", "artist": "Sigur Rós", "artistId": "ar1"}
)
FINALLY = Album.model_validate(
    {
        "id": "al2",
        "name": "Finally We Are No One",
        "artist": "múm",
        "artistId": "ar2",
        "year": 2002,
    }
)

# Sigur Rós has this album too, but no song of it.
AGAETIS = Album.model_validate(
    {
        "id": "al3",
        "name": "Ágætis byrjun",
        "artist": "Sigur Rós",
        "artistId": "ar1",
        "year": 1999,
    }
)

POST_ROCK = Genre.model_validate({"value": "Post-Rock"})
ELECTRONIC = Genre.model_validate({"value": "Electronic"})
JAZZ = Genre.model_validate({"value": "Jazz"})


def song(
    song_id: str, album: Album, genre: Genre, plays: int, title: str | None = None
) -> Song:
    data = {
        "id": song_id,
        "title": title or song_id,
        "albumId": album.id,
        "artist": album.artist,
        "artistId": album.artist_id,
        "genre": genre.name,
        "playCount": plays,
    }
    return Song.model_validate(data)


def make_client() -> AsyncMock:
    # Each method has an explicit reply, so no test passes on a MagicMock.
    client = AsyncMock(spec=SubsonicClient)
    client.__aenter__.return_value = client
    client.artists.return_value = [SIGUR_ROS, MUM]
    client.albums.return_value = [TAKK, FINALLY]
    client.songs.return_value = [
        song("s1", TAKK, POST_ROCK, 4),
        song("s2", TAKK, POST_ROCK, 3),
        song("s3", FINALLY, ELECTRONIC, 2),
        Song.model_validate({"id": "s4", "title": "Loose", "playCount": 1}),
    ]
    client.genres.return_value = [POST_ROCK, ELECTRONIC, JAZZ]
    return client


async def call(client: AsyncMock, tool: str, **arguments: Any) -> Any:
    server = create_server(SETTINGS, make_client=lambda _: client)
    async with Client(server) as session:
        result = await session.call_tool(tool, arguments)
    assert not result.is_error, result.content
    return result.structured_content


async def call_error(client: AsyncMock, tool: str, **arguments: Any) -> str:
    server = create_server(SETTINGS, make_client=lambda _: client)
    async with Client(server) as session:
        result = await session.call_tool(tool, arguments)
    assert result.is_error
    [content] = result.content
    assert content.type == "text"
    return content.text


@pytest.mark.anyio
async def test_lists_the_read_only_tools():
    server = create_server(SETTINGS, make_client=lambda _: make_client())

    async with Client(server) as session:
        result = await session.list_tools()

    assert [tool.name for tool in result.tools] == [
        "taste_summary",
        "artist_details",
        "album_details",
        "check_artists",
        "check_albums",
        "check_songs",
    ]
    for tool in result.tools:
        assert tool.output_schema is not None
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True


@pytest.mark.anyio
async def test_lifespan_opens_and_closes_the_client():
    client = make_client()
    settings: list[Settings] = []

    def connect(given: Settings) -> AsyncMock:
        settings.append(given)
        return client

    async with Client(create_server(SETTINGS, make_client=connect)):
        client.__aexit__.assert_not_awaited()

    assert settings == [SETTINGS]
    client.__aexit__.assert_awaited_once()
    # The server does not load the library before a tool call.
    client.songs.assert_not_awaited()


@pytest.mark.anyio
async def test_taste_summary():
    summary = await call(make_client(), "taste_summary")

    assert summary == {
        "totals": {"artists": 2, "albums": 2, "songs": 4, "genres": 3, "plays": 10},
        "top_artists": [
            {"id": "ar1", "name": "Sigur Rós", "plays": 7},
            {"id": "ar2", "name": "múm", "plays": 2},
        ],
        "top_albums": [
            {
                "id": "al1",
                "name": "Takk...",
                "artist": "Sigur Rós",
                "year": None,
                "plays": 7,
            },
            {
                "id": "al2",
                "name": "Finally We Are No One",
                "artist": "múm",
                "year": 2002,
                "plays": 2,
            },
        ],
        "top_genres": [
            {"name": "Post-Rock", "plays": 7},
            {"name": "Electronic", "plays": 2},
        ],
    }


@pytest.mark.anyio
async def test_taste_summary_obeys_the_limit():
    summary = await call(make_client(), "taste_summary", limit=1)

    assert [item["id"] for item in summary["top_artists"]] == ["ar1"]
    assert [item["id"] for item in summary["top_albums"]] == ["al1"]
    assert [item["name"] for item in summary["top_genres"]] == ["Post-Rock"]
    # The limit does not change the totals.
    assert summary["totals"]["artists"] == 2


@pytest.mark.anyio
@pytest.mark.parametrize("limit", [0, 51])
async def test_taste_summary_refuses_a_limit_out_of_range(limit: int):
    client = make_client()

    message = await call_error(client, "taste_summary", limit=limit)

    assert "limit" in message
    client.songs.assert_not_awaited()


@pytest.mark.anyio
async def test_artist_details_give_the_albums_oldest_first():
    client = make_client()
    client.albums.return_value = [TAKK, FINALLY, AGAETIS]

    details = await call(client, "artist_details", artist_id="ar1")

    assert details == {
        "artist": {"id": "ar1", "name": "Sigur Rós", "plays": 7},
        "albums": [
            {
                "id": "al3",
                "name": "Ágætis byrjun",
                "artist": "Sigur Rós",
                "year": 1999,
                "plays": 0,
            },
            {
                "id": "al1",
                "name": "Takk...",
                "artist": "Sigur Rós",
                "year": None,
                "plays": 7,
            },
        ],
    }


@pytest.mark.anyio
async def test_album_details_give_the_songs_with_plays():
    details = await call(make_client(), "album_details", album_id="al1")

    assert details == {
        "album": {
            "id": "al1",
            "name": "Takk...",
            "artist": "Sigur Rós",
            "year": None,
            "plays": 7,
        },
        "songs": [
            {"id": "s1", "title": "s1", "artist": "Sigur Rós", "plays": 4},
            {"id": "s2", "title": "s2", "artist": "Sigur Rós", "plays": 3},
        ],
    }


@pytest.mark.anyio
async def test_album_details_of_album_without_songs():
    client = make_client()
    client.albums.return_value = [TAKK, FINALLY, AGAETIS]

    details = await call(client, "album_details", album_id="al3")

    assert details["album"]["plays"] == 0
    assert details["songs"] == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool", "arguments", "message"),
    [
        ("artist_details", {"artist_id": "al1"}, "No artist has the id 'al1'."),
        ("album_details", {"album_id": "ar1"}, "No album has the id 'ar1'."),
    ],
)
async def test_details_of_unknown_id_are_a_tool_error(
    tool: str, arguments: dict[str, str], message: str
):
    error = await call_error(make_client(), tool, **arguments)

    assert error == f"Error executing tool {tool}: {message}"


@pytest.mark.anyio
async def test_check_artists_keeps_the_candidate_order():
    check = await call(
        make_client(), "check_artists", names=["Radiohead", "SIGUR ROS", "The Mum"]
    )

    assert check == {
        "results": [
            {"name": "Radiohead", "matches": []},
            {
                "name": "SIGUR ROS",
                "matches": [{"id": "ar1", "name": "Sigur Rós", "plays": 7}],
            },
            {
                "name": "The Mum",
                "matches": [{"id": "ar2", "name": "múm", "plays": 2}],
            },
        ]
    }


@pytest.mark.anyio
async def test_check_albums_with_and_without_artist():
    albums = [
        {"name": "takk (Remastered)"},
        {"name": "Takk...", "artist": "sigur ros"},
        {"name": "Takk...", "artist": "múm"},
    ]

    check = await call(make_client(), "check_albums", albums=albums)

    takk = {
        "id": "al1",
        "name": "Takk...",
        "artist": "Sigur Rós",
        "year": None,
        "plays": 7,
    }
    assert check == {
        "results": [
            {"name": "takk (Remastered)", "artist": None, "matches": [takk]},
            {"name": "Takk...", "artist": "sigur ros", "matches": [takk]},
            {"name": "Takk...", "artist": "múm", "matches": []},
        ]
    }


@pytest.mark.anyio
async def test_check_songs_with_and_without_artist():
    client = make_client()
    client.songs.return_value = [song("s1", TAKK, POST_ROCK, 4, title="Hoppípolla")]
    songs = [
        {"title": "hoppipolla"},
        {"title": "Hoppipolla", "artist": "múm"},
        {"title": "Glósóli"},
    ]

    check = await call(client, "check_songs", songs=songs)

    hoppipolla = {"id": "s1", "title": "Hoppípolla", "artist": "Sigur Rós", "plays": 4}
    assert check == {
        "results": [
            {"title": "hoppipolla", "artist": None, "matches": [hoppipolla]},
            {"title": "Hoppipolla", "artist": "múm", "matches": []},
            {"title": "Glósóli", "artist": None, "matches": []},
        ]
    }


@pytest.mark.anyio
async def test_check_accepts_the_maximum_of_candidates():
    check = await call(make_client(), "check_artists", names=["múm"] * 50)

    assert len(check["results"]) == 50


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("check_artists", {"names": []}),
        ("check_artists", {"names": ["Sigur Rós"] * 51}),
        ("check_artists", {"names": [""]}),
        ("check_albums", {"albums": [{"name": "Takk", "artist": ""}]}),
        ("check_albums", {"albums": [{"name": "Takk", "year": 2005}]}),
        ("check_songs", {"songs": [{"name": "Hoppipolla"}]}),
    ],
)
async def test_check_refuses_bad_candidates(tool: str, arguments: dict[str, Any]):
    client = make_client()

    await call_error(client, tool, **arguments)

    client.songs.assert_not_awaited()


@pytest.mark.anyio
async def test_subsonic_error_becomes_a_tool_error():
    client = make_client()
    client.songs.side_effect = SubsonicError("Subsonic request search3 timed out.")

    message = await call_error(client, "taste_summary")

    # The SDK adds the name of the tool.
    assert message == (
        "Error executing tool taste_summary: Subsonic request search3 timed out."
    )


def test_main_exits_on_a_config_error(monkeypatch: pytest.MonkeyPatch):
    for field in Settings.model_fields:
        monkeypatch.delenv(env_name(field), raising=False)

    with pytest.raises(SystemExit) as raised:
        main()

    message = str(raised.value.code)
    assert message.startswith("ndmcp: the configuration is not valid.\n")
    assert "NDMCP_URL is not set." in message
