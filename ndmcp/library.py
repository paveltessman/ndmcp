# pyright: strict
from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final
from typing import Generic
from typing import Protocol
from typing import TypeVar

from ndmcp.models import Album
from ndmcp.models import Artist
from ndmcp.models import Genre
from ndmcp.models import Song

T = TypeVar("T")

# Letters that NFKD does not split into a base letter and an accent.
_LETTERS = str.maketrans({"æ": "ae", "œ": "oe", "ø": "o", "ð": "d", "þ": "th"})
# A group in brackets at the end, for example "(Remastered 2011)".
_TRAILING_GROUP = re.compile(r"\s*[(\[][^()\[\]]*[)\]]$")
_APOSTROPHES = re.compile(r"['’]")
_PUNCTUATION = re.compile(r"[^\w\s]|_")


@dataclass(frozen=True)
class Plays(Generic[T]):
    """An artist, album or genre with the sum of the play counts of its songs."""

    item: T
    plays: int


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

        self._artists_by_key = _group(self.artists, lambda artist: _key(artist.name))
        self._albums_by_key = _group(self.albums, lambda album: _key(album.name))
        self._songs_by_key = _group(self.songs, lambda song: _key(song.title))

        self._artist_plays = _sum_plays(self.songs, lambda song: song.artist_id)
        self._album_plays = _sum_plays(self.songs, lambda song: song.album_id)
        self._genre_plays = _sum_plays(self.songs, lambda song: song.genre)

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

    def find_artist(self, name: str) -> tuple[Artist, ...]:
        """Give the artists with the same normalized name."""
        return self._artists_by_key.get(normalize(name), ())

    def find_album(self, name: str, artist: str | None = None) -> tuple[Album, ...]:
        """Give the albums with the same normalized name, and artist if given."""
        albums = self._albums_by_key.get(normalize(name), ())
        return _by_artist(albums, artist)

    def find_song(self, title: str, artist: str | None = None) -> tuple[Song, ...]:
        """Give the songs with the same normalized title, and artist if given."""
        songs = self._songs_by_key.get(normalize(title), ())
        return _by_artist(songs, artist)

    def top_artists(self, limit: int) -> tuple[Plays[Artist], ...]:
        """Give the most played artists. Artists without plays are not in it."""
        return _top(self._artist_counts(), limit)

    def top_albums(self, limit: int) -> tuple[Plays[Album], ...]:
        """Give the most played albums. Albums without plays are not in it."""
        return _top(self._album_counts(), limit)

    def top_genres(self, limit: int) -> tuple[Plays[Genre], ...]:
        """Give the most played genres. Genres without plays are not in it."""
        counts = [Plays(g, self._genre_plays.get(g.name, 0)) for g in self.genres]
        return _top(counts, limit)

    def rarely_played_artists(
        self, max_plays: int, limit: int
    ) -> tuple[Plays[Artist], ...]:
        """Give the artists with max_plays or less, the least played first."""
        return _rarest(self._artist_counts(), max_plays, limit)

    def rarely_played_albums(
        self, max_plays: int, limit: int
    ) -> tuple[Plays[Album], ...]:
        """Give the albums with max_plays or less, the least played first."""
        return _rarest(self._album_counts(), max_plays, limit)

    def _artist_counts(self) -> list[Plays[Artist]]:
        return [Plays(a, self._artist_plays.get(a.id, 0)) for a in self.artists]

    def _album_counts(self) -> list[Plays[Album]]:
        return [Plays(a, self._album_plays.get(a.id, 0)) for a in self.albums]


def normalize(name: str) -> str:
    """Give the key that the candidate check uses to compare two names.

    The key has no case, accents, punctuation, leading "the" or trailing
    groups in brackets. "The Beatles" and "beatles" give the same key.
    """
    text = unicodedata.normalize("NFKD", name.casefold().translate(_LETTERS))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = _strip_trailing_groups(text.replace("&", " and "))
    text = _PUNCTUATION.sub(" ", _APOSTROPHES.sub("", text))
    words = text.split()
    if len(words) > 1 and words[0] == "the":
        words = words[1:]
    return " ".join(words)


def _strip_trailing_groups(text: str) -> str:
    # A name that is only a group in brackets keeps the group.
    while True:
        stripped = _TRAILING_GROUP.sub("", text.strip())
        if stripped in (text.strip(), ""):
            return text
        text = stripped


def _key(name: str) -> str | None:
    # A name without letters or digits has no key, so no search finds it.
    return normalize(name) or None


class _HasArtist(Protocol):
    @property
    def artist(self) -> str | None: ...


A = TypeVar("A", bound=_HasArtist)


def _by_artist(items: tuple[A, ...], artist: str | None) -> tuple[A, ...]:
    if artist is None:
        return items
    key = normalize(artist)
    return tuple(item for item in items if _key(item.artist or "") == key)


def _sum_plays(
    songs: Iterable[Song], key: Callable[[Song], str | None]
) -> dict[str, int]:
    # Songs without a key do not count.
    totals: dict[str, int] = {}
    for song in songs:
        name = key(song)
        if name is not None:
            totals[name] = totals.get(name, 0) + song.play_count
    return totals


class _HasName(Protocol):
    @property
    def name(self) -> str: ...


N = TypeVar("N", bound=_HasName)


def _top(counts: Iterable[Plays[N]], limit: int) -> tuple[Plays[N], ...]:
    # Equal counts sort by name.
    played = [count for count in counts if count.plays > 0]
    played.sort(key=lambda count: (-count.plays, normalize(count.item.name)))
    return tuple(played[: max(limit, 0)])


def _rarest(
    counts: Iterable[Plays[N]], max_plays: int, limit: int
) -> tuple[Plays[N], ...]:
    # Equal counts sort by name.
    rare = [count for count in counts if count.plays <= max_plays]
    rare.sort(key=lambda count: (count.plays, normalize(count.item.name)))
    return tuple(rare[: max(limit, 0)])


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
