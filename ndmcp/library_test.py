import asyncio
from unittest.mock import AsyncMock

import pytest

from ndmcp.library import Library
from ndmcp.library import LibraryCache
from ndmcp.library import normalize
from ndmcp.library import Plays
from ndmcp.models import Album
from ndmcp.models import Artist
from ndmcp.models import Genre
from ndmcp.models import Song
from ndmcp.subsonic import SubsonicClient
from ndmcp.subsonic import SubsonicError


def artist(artist_id: str, name: str) -> Artist:
    return Artist.model_validate({"id": artist_id, "name": name})


def album(
    album_id: str,
    name: str,
    artist_id: str,
    year: int | None = None,
    artist: str | None = None,
    *,
    artists: list[tuple[str, str]] | None = None,
) -> Album:
    data = {
        "id": album_id,
        "name": name,
        "artistId": artist_id,
        "year": year,
        "artist": artist,
        "artists": credits(artists),
    }
    return Album.model_validate(data)


def song(
    song_id: str,
    title: str,
    album_id: str | None = None,
    artist: str | None = None,
    *,
    artist_id: str | None = None,
    artists: list[tuple[str, str]] | None = None,
    genre: str | None = None,
    plays: int = 0,
) -> Song:
    data = {
        "id": song_id,
        "title": title,
        "albumId": album_id,
        "artist": artist,
        "artistId": artist_id,
        "artists": credits(artists),
        "genre": genre,
        "playCount": plays,
    }
    return Song.model_validate(data)


def credits(artists: list[tuple[str, str]] | None) -> list[dict[str, str]]:
    return [{"id": artist_id, "name": name} for artist_id, name in artists or []]


def genre(name: str) -> Genre:
    return Genre.model_validate({"value": name})


SIGUR_ROS = artist("ar1", "Sigur Rós")
MUM = artist("ar2", "múm")

AGAETIS = album("al1", "Ágætis byrjun", "ar1", 1999, "Sigur Rós")
TAKK = album("al2", "Takk...", "ar1", 2005, "Sigur Rós")
BOOTLEG = album("al3", "Bootleg", "ar1", artist="Sigur Rós")
FINALLY = album("al4", "Finally We Are No One", "ar2", 2002, "múm")

SVEFN = song("s1", "Svefn-g-englar", "al1", "Sigur Rós")
STARALFUR = song("s2", "Starálfur", "al1", "Sigur Rós")
HOPPIPOLLA = song("s3", "Hoppípolla", "al2", "Sigur Rós")
LOOSE = song("s4", "Loose track")

POST_ROCK = genre("Post-Rock")


def make_library() -> Library:
    return Library(
        artists=[SIGUR_ROS, MUM],
        albums=[TAKK, BOOTLEG, FINALLY, AGAETIS],
        songs=[SVEFN, HOPPIPOLLA, LOOSE, STARALFUR],
        genres=[POST_ROCK],
    )


def test_keeps_all_items_in_load_order():
    library = make_library()

    assert library.artists == (SIGUR_ROS, MUM)
    assert library.albums == (TAKK, BOOTLEG, FINALLY, AGAETIS)
    assert library.songs == (SVEFN, HOPPIPOLLA, LOOSE, STARALFUR)
    assert library.genres == (POST_ROCK,)


def test_lookups_by_id():
    library = make_library()

    assert library.artist("ar2") == MUM
    assert library.album("al2") == TAKK
    assert library.song("s3") == HOPPIPOLLA


def test_lookups_of_unknown_id_give_none():
    library = make_library()

    assert library.artist("s1") is None
    assert library.album("ar1") is None
    assert library.song("al1") is None


def test_albums_of_artist_oldest_first_and_no_year_last():
    library = make_library()

    assert library.albums_of("ar1") == (AGAETIS, TAKK, BOOTLEG)
    assert library.albums_of("ar2") == (FINALLY,)


def test_albums_of_same_year_sort_by_name():
    later = album("al5", "b side", "ar1", 1999)
    earlier = album("al6", "A side", "ar1", 1999)
    library = Library(artists=[], albums=[later, earlier], songs=[], genres=[])

    assert library.albums_of("ar1") == (earlier, later)


def test_songs_of_album_keep_load_order():
    library = make_library()

    assert library.songs_of("al1") == (SVEFN, STARALFUR)
    assert library.songs_of("al2") == (HOPPIPOLLA,)


def test_drill_down_of_unknown_id_is_empty():
    library = make_library()

    assert library.albums_of("unknown") == ()
    assert library.songs_of("unknown") == ()
    assert library.songs_of("al4") == ()


def test_empty_library():
    library = Library(artists=[], albums=[], songs=[], genres=[])

    assert library.songs == ()
    assert library.artist("ar1") is None
    assert library.albums_of("ar1") == ()
    assert library.find_album("Takk") == ()


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("Sigur Rós", "sigur ros"),
        ("Ágætis byrjun", "agaetis byrjun"),
        ("Røyksopp", "royksopp"),
        ("The Beatles", "beatles"),
        ("The The", "the"),
        ("Theatre of Tragedy", "theatre of tragedy"),
        ("Simon & Garfunkel", "simon and garfunkel"),
        ("Don't Look Back", "dont look back"),
        ("AC/DC", "ac dc"),
        ("Svefn-g-englar", "svefn g englar"),
        ("  Takk...  ", "takk"),
        ("OK Computer (Remastered)", "ok computer"),
        ("Album (Deluxe) [2011 Remaster]", "album"),
        ("(What's the Story) Morning Glory?", "whats the story morning glory"),
        ("[Untitled]", "untitled"),
        ("...", ""),
    ],
)
def test_normalize(name: str, key: str):
    assert normalize(name) == key


def test_find_artist_ignores_case_and_accents():
    library = make_library()

    assert library.find_artist("SIGUR ROS") == (SIGUR_ROS,)
    assert library.find_artist("Mum") == (MUM,)
    assert library.find_artist("Sigur") == ()


def test_find_album_without_artist():
    library = make_library()

    assert library.find_album("agaetis byrjun") == (AGAETIS,)
    assert library.find_album("Takk") == (TAKK,)
    assert library.find_album("Agaetis") == ()


def test_find_album_with_artist():
    library = make_library()

    assert library.find_album("Takk", artist="sigur ros") == (TAKK,)
    assert library.find_album("Takk", artist="múm") == ()


def test_find_album_gives_each_edition():
    deluxe = album("al5", "Takk... (Deluxe Edition)", "ar1", 2005, "Sigur Rós")
    library = Library(artists=[], albums=[TAKK, deluxe], songs=[], genres=[])

    assert library.find_album("Takk") == (TAKK, deluxe)


def test_find_song_with_and_without_artist():
    library = make_library()

    assert library.find_song("Hoppipolla") == (HOPPIPOLLA,)
    assert library.find_song("hoppipolla", artist="Sigur Rós") == (HOPPIPOLLA,)
    assert library.find_song("Hoppipolla", artist="múm") == ()


def test_find_with_artist_skips_items_without_artist():
    library = make_library()

    assert library.find_song("Loose track") == (LOOSE,)
    assert library.find_song("Loose track", artist="") == ()


COME2FIND = song(
    "s7",
    "come2find",
    artist="Moore Kismet & YAOUNDÉBOXINGCLUB",
    artists=[("ar4", "Moore Kismet"), ("ar5", "YAOUNDÉBOXINGCLUB")],
)
UNICORN = album(
    "al6",
    "Call of the Unicorn",
    "ar4",
    artist="Moore Kismet feat. Tasha Baxter",
    artists=[("ar4", "Moore Kismet"), ("ar6", "Tasha Baxter")],
)


@pytest.mark.parametrize(
    "candidate",
    [
        "Moore Kismet",
        "YAOUNDEBOXINGCLUB",
        "Moore Kismet & YAOUNDEBOXINGCLUB",
        "YAOUNDEBOXINGCLUB feat. Moore Kismet",
    ],
)
def test_find_song_matches_each_credited_artist(candidate: str):
    library = Library(artists=[], albums=[], songs=[COME2FIND], genres=[])

    assert library.find_song("come2find", artist=candidate) == (COME2FIND,)


def test_find_album_matches_each_credited_artist():
    library = Library(artists=[], albums=[UNICORN], songs=[], genres=[])

    assert library.find_album("Call of the Unicorn", artist="Tasha Baxter") == (
        UNICORN,
    )
    assert library.find_album("Call of the Unicorn", artist="Skrillex") == ()


@pytest.mark.parametrize(
    "credit",
    [
        "Wherefore & Moore Kismet",
        "Wherefore, Moore Kismet",
        "Wherefore / Moore Kismet",
        "Wherefore; Moore Kismet",
        "Wherefore feat. Moore Kismet",
        "Wherefore Feat Moore Kismet",
        "Wherefore ft. Moore Kismet",
        "Wherefore featuring Moore Kismet",
        "Wherefore x Moore Kismet",
        "Wherefore vs. Moore Kismet",
    ],
)
def test_find_song_splits_the_credit_without_artists(credit: str):
    # Servers without the "artists" field give only the full credit.
    why2k = song("s8", "WHY2K!", artist=credit)
    library = Library(artists=[], albums=[], songs=[why2k], genres=[])

    assert library.find_song("WHY2K", artist="Wherefore") == (why2k,)
    assert library.find_song("WHY2K", artist="moore kismet") == (why2k,)
    assert library.find_song("WHY2K", artist="Skrillex") == ()


def test_find_song_does_not_split_inside_a_name():
    track = song("s9", "Track", artist="Malcolm X")
    library = Library(artists=[], albums=[], songs=[track], genres=[])

    assert library.find_song("Track", artist="Malcolm X") == (track,)
    assert library.find_song("Track", artist="Malcolm") == ()


def test_name_without_key_is_not_found():
    dots = artist("ar3", "...")
    library = Library(artists=[dots], albums=[], songs=[], genres=[])

    assert library.find_artist("...") == ()


ELECTRONIC = genre("Electronic")
JAZZ = genre("Jazz")


def make_played_library() -> Library:
    # Sigur Rós: 3 + 2 + 4 = 9 plays. múm: 5 plays.
    songs = [
        song(
            "s1", "Svefn-g-englar", "al1", artist_id="ar1", genre="Post-Rock", plays=3
        ),
        song("s2", "Starálfur", "al1", artist_id="ar1", genre="Post-Rock", plays=2),
        song("s3", "Hoppípolla", "al2", artist_id="ar1", genre="Post-Rock", plays=4),
        song("s5", "Green Grass", "al4", artist_id="ar2", genre="Electronic", plays=5),
        song("s6", "Unknown", plays=7),
    ]
    return Library(
        artists=[SIGUR_ROS, MUM],
        albums=[TAKK, BOOTLEG, FINALLY, AGAETIS],
        songs=songs,
        genres=[JAZZ, ELECTRONIC, POST_ROCK],
    )


def test_plays_of_one_artist_and_album():
    library = make_played_library()

    assert library.artist_plays("ar1") == 9
    assert library.artist_plays("ar2") == 5
    assert library.album_plays("al1") == 5
    assert library.album_plays("al2") == 4


def test_plays_of_unplayed_or_unknown_id_are_zero():
    library = make_played_library()

    assert library.album_plays("al3") == 0
    assert library.artist_plays("unknown") == 0
    assert library.album_plays("unknown") == 0


def test_top_artists_sum_song_plays():
    library = make_played_library()

    assert library.top_artists(10) == (Plays(SIGUR_ROS, 9), Plays(MUM, 5))


def test_top_albums_sort_equal_plays_by_name_and_skip_unplayed():
    library = make_played_library()

    # "Ágætis byrjun" sorts as "agaetis byrjun", so it is before "Finally".
    assert library.top_albums(10) == (
        Plays(AGAETIS, 5),
        Plays(FINALLY, 5),
        Plays(TAKK, 4),
    )


def test_top_genres_skip_unplayed():
    library = make_played_library()

    assert library.top_genres(10) == (Plays(POST_ROCK, 9), Plays(ELECTRONIC, 5))


def test_top_obeys_the_limit():
    library = make_played_library()

    assert library.top_albums(2) == (Plays(AGAETIS, 5), Plays(FINALLY, 5))
    assert library.top_artists(0) == ()
    assert library.top_artists(-1) == ()


def test_song_without_keys_does_not_count():
    # Song s6 has 7 plays, but no artist, album or genre.
    library = make_played_library()

    assert sum(count.plays for count in library.top_artists(10)) == 14
    assert sum(count.plays for count in library.top_albums(10)) == 14
    assert sum(count.plays for count in library.top_genres(10)) == 14


def test_rarely_played_albums_least_played_first():
    library = make_played_library()

    assert library.rarely_played_albums(max_plays=4, limit=10) == (
        Plays(BOOTLEG, 0),
        Plays(TAKK, 4),
    )
    assert library.rarely_played_albums(max_plays=0, limit=10) == (Plays(BOOTLEG, 0),)


def test_rarely_played_artists():
    library = make_played_library()

    assert library.rarely_played_artists(max_plays=5, limit=10) == (Plays(MUM, 5),)
    assert library.rarely_played_artists(max_plays=9, limit=1) == (Plays(MUM, 5),)
    assert library.rarely_played_artists(max_plays=4, limit=10) == ()


MOORE_KISMET = artist("ar4", "Moore Kismet")
YAOUNDE = artist("ar5", "YAOUNDÉBOXINGCLUB")
KISMET_AND_YAOUNDE = [("ar4", "Moore Kismet"), ("ar5", "YAOUNDÉBOXINGCLUB")]


def make_collab_library() -> Library:
    # Moore Kismet: 5 + 3 = 8 plays. YAOUNDÉBOXINGCLUB: 5 plays.
    songs = [
        song("s7", "come2find", artist_id="ar4", artists=KISMET_AND_YAOUNDE, plays=5),
        song("s10", "Solo", artist_id="ar4", plays=3),
    ]
    return Library(artists=[MOORE_KISMET, YAOUNDE], albums=[], songs=songs, genres=[])


def test_song_plays_count_for_each_credited_artist():
    library = make_collab_library()

    assert library.artist_plays("ar4") == 8
    assert library.artist_plays("ar5") == 5


def test_featured_artist_is_not_rarely_played():
    library = make_collab_library()

    assert library.rarely_played_artists(max_plays=0, limit=10) == ()
    assert library.top_artists(10) == (Plays(MOORE_KISMET, 8), Plays(YAOUNDE, 5))


def test_artist_twice_in_the_credits_counts_once():
    twice = [("ar4", "Moore Kismet"), ("ar4", "Moore Kismet")]
    songs = [song("s7", "come2find", artist_id="ar4", artists=twice, plays=5)]
    library = Library(artists=[MOORE_KISMET], albums=[], songs=songs, genres=[])

    assert library.artist_plays("ar4") == 5


def test_albums_of_gives_the_albums_of_each_credited_artist():
    solo = album("al7", "UNIVERSE", "ar4", 2021, "Moore Kismet")
    collab = album("al8", "Collab", "ar4", 2022, artists=KISMET_AND_YAOUNDE)
    library = Library(artists=[], albums=[collab, solo], songs=[], genres=[])

    assert library.albums_of("ar4") == (solo, collab)
    assert library.albums_of("ar5") == (collab,)


def test_statistics_of_empty_library():
    library = Library(artists=[], albums=[], songs=[], genres=[])

    assert library.top_artists(10) == ()
    assert library.rarely_played_albums(max_plays=0, limit=10) == ()


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make_client() -> AsyncMock:
    # Each method has an explicit reply, so no test passes on a MagicMock.
    client = AsyncMock(spec=SubsonicClient)
    client.artists.return_value = [SIGUR_ROS]
    client.albums.return_value = [AGAETIS]
    client.songs.return_value = [SVEFN]
    client.genres.return_value = [POST_ROCK]
    return client


def load_count(client: AsyncMock) -> int:
    counts = {
        client.artists.await_count,
        client.albums.await_count,
        client.songs.await_count,
        client.genres.await_count,
    }
    # Each load calls all four methods.
    [count] = counts
    return count


@pytest.mark.anyio
async def test_cache_loads_the_library():
    client = make_client()
    cache = LibraryCache(client, ttl=300, clock=FakeClock())

    library = await cache.get()

    assert library.artists == (SIGUR_ROS,)
    assert library.albums == (AGAETIS,)
    assert library.songs == (SVEFN,)
    assert library.genres == (POST_ROCK,)
    assert load_count(client) == 1


@pytest.mark.anyio
async def test_cache_keeps_the_library_for_the_ttl():
    client = make_client()
    clock = FakeClock()
    cache = LibraryCache(client, ttl=300, clock=clock)

    first = await cache.get()
    clock.now += 299.9
    second = await cache.get()

    assert second is first
    assert load_count(client) == 1


@pytest.mark.anyio
async def test_cache_loads_again_after_the_ttl():
    client = make_client()
    clock = FakeClock()
    cache = LibraryCache(client, ttl=300, clock=clock)

    first = await cache.get()
    clock.now += 300
    second = await cache.get()

    assert second is not first
    assert load_count(client) == 2


@pytest.mark.anyio
async def test_cache_with_zero_ttl_loads_each_time():
    client = make_client()
    cache = LibraryCache(client, ttl=0, clock=FakeClock())

    await cache.get()
    await cache.get()

    assert load_count(client) == 2


@pytest.mark.anyio
async def test_parallel_calls_share_one_load():
    client = make_client()

    async def slow_songs() -> list[Song]:
        # The load stops here, so the second call starts during the load.
        await asyncio.sleep(0)
        return [SVEFN]

    client.songs.side_effect = slow_songs
    cache = LibraryCache(client, ttl=300, clock=FakeClock())

    first, second = await asyncio.gather(cache.get(), cache.get())

    assert second is first
    assert load_count(client) == 1


@pytest.mark.anyio
async def test_failed_load_is_not_kept():
    client = make_client()
    client.songs.side_effect = [SubsonicError("Subsonic request failed."), [SVEFN]]
    cache = LibraryCache(client, ttl=300, clock=FakeClock())

    with pytest.raises(SubsonicError):
        await cache.get()
    library = await cache.get()

    assert library.songs == (SVEFN,)
    assert load_count(client) == 2
