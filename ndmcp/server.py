# pyright: strict
# The SDK reads the tool signatures at run time, so the annotations stay real
# types, without "from __future__ import annotations".
import sys
from collections.abc import AsyncGenerator
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Annotated
from typing import Any

from mcp.server.mcpserver import Context
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from ndmcp.config import ConfigError
from ndmcp.config import load_settings
from ndmcp.config import Settings
from ndmcp.library import Library
from ndmcp.library import LibraryCache
from ndmcp.library import Plays
from ndmcp.models import Album
from ndmcp.models import Artist
from ndmcp.models import Genre
from ndmcp.subsonic import SubsonicClient
from ndmcp.subsonic import SubsonicError

SERVER_NAME = "ndmcp"

INSTRUCTIONS = (
    "Read-only access to the Navidrome music library of one user. "
    "Start with taste_summary. Each artist and album has an id for the "
    "drill-down tools."
)

# The maximum number of items in one list of a tool result.
MAX_LIMIT = 50

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)

Limit = Annotated[int, Field(ge=1, le=MAX_LIMIT)]
ClientFactory = Callable[[Settings], SubsonicClient]
LibraryContext = Context[LibraryCache, Any]


class _Output(BaseModel):
    model_config = ConfigDict(frozen=True)


class ArtistPlays(_Output):
    id: str
    name: str
    plays: int


class AlbumPlays(_Output):
    id: str
    name: str
    artist: str | None
    year: int | None
    plays: int


class GenrePlays(_Output):
    name: str
    plays: int


class Totals(_Output):
    artists: int
    albums: int
    songs: int
    genres: int
    # The sum of the play counts of all songs.
    plays: int


class TasteSummary(_Output):
    totals: Totals
    top_artists: list[ArtistPlays]
    top_albums: list[AlbumPlays]
    top_genres: list[GenrePlays]


async def taste_summary(ctx: LibraryContext, limit: Limit = 10) -> TasteSummary:
    """Give a compact summary of the music taste of the user.

    The summary has the library totals, and the most played artists, albums
    and genres. Each list has limit items at most. Items without plays are not
    in the lists.
    """
    library = await _library(ctx)
    return TasteSummary(
        totals=_totals(library),
        top_artists=[_artist_plays(count) for count in library.top_artists(limit)],
        top_albums=[_album_plays(count) for count in library.top_albums(limit)],
        top_genres=[_genre_plays(count) for count in library.top_genres(limit)],
    )


def create_server(
    settings: Settings, make_client: ClientFactory | None = None
) -> MCPServer[LibraryCache]:
    connect = make_client or _connect

    @asynccontextmanager
    async def lifespan(
        _: MCPServer[LibraryCache],
    ) -> AsyncGenerator[LibraryCache, None]:
        # The first tool call loads the library, so the server starts even
        # when Navidrome is not available.
        async with connect(settings) as client:
            yield LibraryCache(client, settings.cache_ttl)

    server = MCPServer(
        SERVER_NAME,
        instructions=INSTRUCTIONS,
        log_level=settings.log_level,
        lifespan=lifespan,
    )
    server.add_tool(taste_summary, annotations=READ_ONLY)
    return server


def main() -> None:
    try:
        settings = load_settings()
    except ConfigError as error:
        # Stdout carries the MCP messages, so the error goes to stderr.
        sys.exit(f"ndmcp: the configuration is not valid.\n{error}")
    create_server(settings).run("stdio")


def _connect(settings: Settings) -> SubsonicClient:
    return SubsonicClient(settings, transport=None)


async def _library(ctx: LibraryContext) -> Library:
    # A ToolError gives the message to the model. The SubsonicError messages
    # do not show the URL or the auth token.
    cache = ctx.request_context.lifespan_context
    try:
        return await cache.get()
    except SubsonicError as error:
        raise ToolError(str(error)) from error


def _totals(library: Library) -> Totals:
    return Totals(
        artists=len(library.artists),
        albums=len(library.albums),
        songs=len(library.songs),
        genres=len(library.genres),
        plays=sum(song.play_count for song in library.songs),
    )


def _artist_plays(count: Plays[Artist]) -> ArtistPlays:
    artist = count.item
    return ArtistPlays(id=artist.id, name=artist.name, plays=count.plays)


def _album_plays(count: Plays[Album]) -> AlbumPlays:
    album = count.item
    return AlbumPlays(
        id=album.id,
        name=album.name,
        artist=album.artist,
        year=album.year,
        plays=count.plays,
    )


def _genre_plays(count: Plays[Genre]) -> GenrePlays:
    return GenrePlays(name=count.item.name, plays=count.plays)
