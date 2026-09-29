from ndmcp.library import Library
from ndmcp.models import Album
from ndmcp.models import Artist
from ndmcp.models import Genre
from ndmcp.models import Song


def artist(artist_id: str, name: str) -> Artist:
    return Artist.model_validate({"id": artist_id, "name": name})


def album(album_id: str, name: str, artist_id: str, year: int | None = None) -> Album:
    data = {"id": album_id, "name": name, "artistId": artist_id, "year": year}
    return Album.model_validate(data)


def song(song_id: str, title: str, album_id: str | None = None) -> Song:
    return Song.model_validate({"id": song_id, "title": title, "albumId": album_id})


SIGUR_ROS = artist("ar1", "Sigur Rós")
MUM = artist("ar2", "múm")

AGAETIS = album("al1", "Ágætis byrjun", "ar1", 1999)
TAKK = album("al2", "Takk...", "ar1", 2005)
BOOTLEG = album("al3", "Bootleg", "ar1")
FINALLY = album("al4", "Finally We Are No One", "ar2", 2002)

SVEFN = song("s1", "Svefn-g-englar", "al1")
STARALFUR = song("s2", "Starálfur", "al1")
HOPPIPOLLA = song("s3", "Hoppípolla", "al2")
LOOSE = song("s4", "Loose track")

POST_ROCK = Genre.model_validate({"value": "Post-Rock"})


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
