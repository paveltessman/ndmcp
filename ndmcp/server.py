# pyright: strict
# The SDK reads the tool signatures at run time, so the annotations stay real
# types, without "from __future__ import annotations".
import sys
from collections.abc import AsyncGenerator
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Annotated
from typing import Any
from typing import TypeVar

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
from ndmcp.models import Song
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

T = TypeVar("T")

Limit = Annotated[int, Field(ge=1, le=MAX_LIMIT)]
MaxPlays = Annotated[int, Field(ge=0)]
Name = Annotated[str, Field(min_length=1)]
# One call checks MAX_LIMIT candidates at most.
Candidates = Annotated[list[T], Field(min_length=1, max_length=MAX_LIMIT)]
ClientFactory = Callable[[Settings], SubsonicClient]
LibraryContext = Context[LibraryCache, Any]


class _Input(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class _Output(BaseModel):
    model_config = ConfigDict(frozen=True)


class AlbumCandidate(_Input):
    name: Name
    artist: Name | None = None


class SongCandidate(_Input):
    title: Name
    artist: Name | None = None


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


class SongPlays(_Output):
    id: str
    title: str
    artist: str | None
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


class ArtistDetails(_Output):
    artist: ArtistPlays
    # The oldest album first. Albums without a year go last.
    albums: list[AlbumPlays]


class AlbumDetails(_Output):
    album: AlbumPlays
    songs: list[SongPlays]


class ArtistMatch(_Output):
    name: str
    # An empty list means that the library does not have the artist.
    matches: list[ArtistPlays]


class AlbumMatch(_Output):
    name: str
    artist: str | None
    # An empty list means that the library does not have the album.
    matches: list[AlbumPlays]


class SongMatch(_Output):
    title: str
    artist: str | None
    # An empty list means that the library does not have the song.
    matches: list[SongPlays]


class ArtistCheck(_Output):
    results: list[ArtistMatch]


class AlbumCheck(_Output):
    results: list[AlbumMatch]


class SongCheck(_Output):
    results: list[SongMatch]


class RarelyPlayedArtists(_Output):
    # The least played first.
    artists: list[ArtistPlays]


class RarelyPlayedAlbums(_Output):
    # The least played first.
    albums: list[AlbumPlays]


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


async def artist_details(ctx: LibraryContext, artist_id: str) -> ArtistDetails:
    """Give the artist with its play count, and its albums with play counts.

    Get the artist_id from another tool, for example taste_summary.
    """
    library = await _library(ctx)
    artist = library.artist(artist_id)
    if artist is None:
        raise ToolError(f"No artist has the id {artist_id!r}.")
    return ArtistDetails(
        artist=_artist_with_plays(library, artist),
        albums=[_album_with_plays(library, a) for a in library.albums_of(artist.id)],
    )


async def album_details(ctx: LibraryContext, album_id: str) -> AlbumDetails:
    """Give the album with its play count, and its songs with play counts.

    Get the album_id from another tool, for example artist_details.
    """
    library = await _library(ctx)
    album = library.album(album_id)
    if album is None:
        raise ToolError(f"No album has the id {album_id!r}.")
    return AlbumDetails(
        album=_album_with_plays(library, album),
        songs=[_song_plays(song) for song in library.songs_of(album.id)],
    )


async def check_artists(ctx: LibraryContext, names: Candidates[Name]) -> ArtistCheck:
    """Find which candidate artists are in the library.

    Use it before you suggest an artist. The check ignores case, accents,
    punctuation and a leading "The". Each result echoes the candidate, and
    gives the matches with play counts. No matches means a new artist.
    """
    library = await _library(ctx)
    return ArtistCheck(results=[_artist_match(library, name) for name in names])


async def check_albums(
    ctx: LibraryContext, albums: Candidates[AlbumCandidate]
) -> AlbumCheck:
    """Find which candidate albums are in the library.

    Use it before you suggest an album. Give the artist to skip albums of
    other artists with the same name. An album matches when it credits the
    artist, also as one artist of a collaboration. The check ignores case,
    accents, punctuation and trailing groups in brackets, for example
    "(Remastered)". Each result echoes the candidate, and gives all editions
    with play counts. Read the full names to tell the editions apart.
    """
    library = await _library(ctx)
    return AlbumCheck(results=[_album_match(library, album) for album in albums])


async def check_songs(
    ctx: LibraryContext, songs: Candidates[SongCandidate]
) -> SongCheck:
    """Find which candidate songs are in the library.

    Use it before you suggest a song. Give the artist to skip songs of other
    artists with the same title. A song matches when it credits the artist,
    also as one artist of a collaboration. The check ignores case, accents,
    punctuation and trailing groups in brackets. Each result echoes the
    candidate, and gives the matches with play counts.
    """
    library = await _library(ctx)
    return SongCheck(results=[_song_match(library, song) for song in songs])


async def rarely_played_artists(
    ctx: LibraryContext, max_plays: MaxPlays = 0, limit: Limit = 20
) -> RarelyPlayedArtists:
    """Give the artists in the library with max_plays plays or less.

    Use it to find owned music that the user does not play. The least played
    artists come first. The default max_plays of 0 gives only unplayed artists.
    """
    library = await _library(ctx)
    counts = library.rarely_played_artists(max_plays, limit)
    return RarelyPlayedArtists(artists=[_artist_plays(count) for count in counts])


async def rarely_played_albums(
    ctx: LibraryContext, max_plays: MaxPlays = 0, limit: Limit = 20
) -> RarelyPlayedAlbums:
    """Give the albums in the library with max_plays plays or less.

    Use it to find owned music that the user does not play. The least played
    albums come first. The default max_plays of 0 gives only unplayed albums.
    """
    library = await _library(ctx)
    counts = library.rarely_played_albums(max_plays, limit)
    return RarelyPlayedAlbums(albums=[_album_plays(count) for count in counts])


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
    tools = (
        taste_summary,
        artist_details,
        album_details,
        check_artists,
        check_albums,
        check_songs,
        rarely_played_artists,
        rarely_played_albums,
    )
    for tool in tools:
        server.add_tool(tool, annotations=READ_ONLY)
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


def _artist_with_plays(library: Library, artist: Artist) -> ArtistPlays:
    return _artist_plays(Plays(artist, library.artist_plays(artist.id)))


def _album_with_plays(library: Library, album: Album) -> AlbumPlays:
    return _album_plays(Plays(album, library.album_plays(album.id)))


def _song_plays(song: Song) -> SongPlays:
    return SongPlays(
        id=song.id, title=song.title, artist=song.artist, plays=song.play_count
    )


def _artist_match(library: Library, name: str) -> ArtistMatch:
    matches = [_artist_with_plays(library, a) for a in library.find_artist(name)]
    return ArtistMatch(name=name, matches=matches)


def _album_match(library: Library, candidate: AlbumCandidate) -> AlbumMatch:
    albums = library.find_album(candidate.name, candidate.artist)
    return AlbumMatch(
        name=candidate.name,
        artist=candidate.artist,
        matches=[_album_with_plays(library, album) for album in albums],
    )


def _song_match(library: Library, candidate: SongCandidate) -> SongMatch:
    songs = library.find_song(candidate.title, candidate.artist)
    return SongMatch(
        title=candidate.title,
        artist=candidate.artist,
        matches=[_song_plays(song) for song in songs],
    )


def _genre_plays(count: Plays[Genre]) -> GenrePlays:
    return GenrePlays(name=count.item.name, plays=count.plays)
