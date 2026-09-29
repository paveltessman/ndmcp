# pyright: strict
from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterable
from typing import Final
from typing import TypeVar

from ndmcp.models import Album
from ndmcp.models import Artist
from ndmcp.models import Genre
from ndmcp.models import Song

T = TypeVar("T")


class Library:
    """An immutable snapshot of the full library, with lookup indexes."""

    def __init__(
        self,
        artists: Iterable[Artist],
        albums: Iterable[Album],
        songs: Iterable[Song],
        genres: Iterable[Genre],
    ) -> None:
        self.artists: Final = tuple(artists)
        self.albums: Final = tuple(albums)
        self.songs: Final = tuple(songs)
        self.genres: Final = tuple(genres)

        self._artist_by_id = {artist.id: artist for artist in self.artists}
        self._album_by_id = {album.id: album for album in self.albums}
        self._song_by_id = {song.id: song for song in self.songs}
        self._albums_by_artist = _group(
            sorted(self.albums, key=_album_order), lambda album: album.artist_id
        )
        self._songs_by_album = _group(self.songs, lambda song: song.album_id)

    def artist(self, artist_id: str) -> Artist | None:
        return self._artist_by_id.get(artist_id)

    def album(self, album_id: str) -> Album | None:
        return self._album_by_id.get(album_id)

    def song(self, song_id: str) -> Song | None:
        return self._song_by_id.get(song_id)

    def albums_of(self, artist_id: str) -> tuple[Album, ...]:
        """Give the albums of the artist, the oldest first."""
        return self._albums_by_artist.get(artist_id, ())

    def songs_of(self, album_id: str) -> tuple[Song, ...]:
        """Give the songs of the album, in the order of the load."""
        return self._songs_by_album.get(album_id, ())


def _album_order(album: Album) -> tuple[bool, int, str]:
    # Albums without a year go last.
    return (album.year is None, album.year or 0, album.name.casefold())


def _group(
    items: Iterable[T], key: Callable[[T], str | None]
) -> dict[str, tuple[T, ...]]:
    # Items without a key are not in a group.
    groups: dict[str, list[T]] = {}
    for item in items:
        name = key(item)
        if name is not None:
            groups.setdefault(name, []).append(item)
    return {name: tuple(group) for name, group in groups.items()}
