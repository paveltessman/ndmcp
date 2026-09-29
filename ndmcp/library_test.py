import pytest

from ndmcp.library import Library
from ndmcp.library import normalize
from ndmcp.library import Plays
from ndmcp.models import Album
from ndmcp.models import Artist
from ndmcp.models import Genre
from ndmcp.models import Song


def artist(artist_id: str, name: str) -> Artist:
    return Artist.model_validate({"id": artist_id, "name": name})


def album(
    album_id: str,
    name: str,
    artist_id: str,
    year: int | None = None,
    artist: str | None = None,
) -> Album:
    data = {
        "id": album_id,
        "name": name,
        "artistId": artist_id,
        "year": year,
        "artist": artist,
    }
    return Album.model_validate(data)


def song(
    song_id: str,
    title: str,
    album_id: str | None = None,
    artist: str | None = None,
    *,
    artist_id: str | None = None,
    genre: str | None = None,
    plays: int = 0,
) -> Song:
    data = {
        "id": song_id,
        "title": title,
        "albumId": album_id,
        "artist": artist,
        "artistId": artist_id,
        "genre": genre,
        "playCount": plays,
    }
    return Song.model_validate(data)


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


def test_statistics_of_empty_library():
    library = Library(artists=[], albums=[], songs=[], genres=[])

    assert library.top_artists(10) == ()
    assert library.rarely_played_albums(max_plays=0, limit=10) == ()
