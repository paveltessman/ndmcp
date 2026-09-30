from datetime import datetime
from datetime import timezone

from ndmcp.models import Album
from ndmcp.models import Artist
from ndmcp.models import ArtistRef
from ndmcp.models import Genre
from ndmcp.models import Song


def test_song_from_navidrome_json():
    song = Song.model_validate(
        {
            "id": "s1",
            "parent": "al1",
            "isDir": False,
            "title": "Svefn-g-englar",
            "album": "Ágætis byrjun",
            "albumId": "al1",
            "artist": "Sigur Rós",
            "artistId": "ar1",
            "track": 2,
            "year": 1999,
            "genre": "Post-Rock",
            "duration": 604,
            "playCount": 12,
            "played": "2026-09-01T20:15:00.000Z",
            "bitRate": 320,
            "suffix": "mp3",
        }
    )

    assert song.id == "s1"
    assert song.title == "Svefn-g-englar"
    assert song.album == "Ágætis byrjun"
    assert song.album_id == "al1"
    assert song.artist == "Sigur Rós"
    assert song.artist_id == "ar1"
    assert song.year == 1999
    assert song.genre == "Post-Rock"
    assert song.duration == 604
    assert song.play_count == 12
    assert song.played == datetime(2026, 9, 1, 20, 15, tzinfo=timezone.utc)


def test_song_with_only_required_fields():
    song = Song.model_validate({"id": "s1", "title": "Untitled"})

    assert song.album is None
    assert song.artist is None
    assert song.year is None
    assert song.genre is None
    assert song.duration is None
    assert song.play_count == 0
    assert song.played is None


def test_album_from_navidrome_json():
    album = Album.model_validate(
        {
            "id": "al1",
            "name": "Ágætis byrjun",
            "artist": "Sigur Rós",
            "artistId": "ar1",
            "year": 1999,
            "genre": "Post-Rock",
            "songCount": 10,
            "duration": 4312,
            "playCount": 40,
            "played": "2026-09-01T20:15:00Z",
            "created": "2025-01-01T00:00:00Z",
        }
    )

    assert album.name == "Ágætis byrjun"
    assert album.artist_id == "ar1"
    assert album.song_count == 10
    assert album.duration == 4312
    assert album.play_count == 40
    assert album.played == datetime(2026, 9, 1, 20, 15, tzinfo=timezone.utc)


def test_album_without_play_count_has_zero():
    album = Album.model_validate({"id": "al1", "name": "Never played"})

    assert album.play_count == 0
    assert album.played is None


def test_artist_from_navidrome_json():
    artist = Artist.model_validate(
        {"id": "ar1", "name": "Sigur Rós", "albumCount": 3, "coverArt": "ar-ar1"}
    )

    assert artist.name == "Sigur Rós"
    assert artist.album_count == 3


def test_genre_name_comes_from_value():
    genre = Genre.model_validate(
        {"value": "Post-Rock", "songCount": 25, "albumCount": 3}
    )

    assert genre.name == "Post-Rock"
    assert genre.song_count == 25
    assert genre.album_count == 3


def test_song_keeps_each_credited_artist():
    song = Song.model_validate(
        {
            "id": "s1",
            "title": "come2find",
            "artist": "Moore Kismet & YAOUNDÉBOXINGCLUB",
            "artistId": "ar1",
            "displayArtist": "Moore Kismet & YAOUNDÉBOXINGCLUB",
            "artists": [
                {"id": "ar1", "name": "Moore Kismet"},
                {"id": "ar2", "name": "YAOUNDÉBOXINGCLUB"},
            ],
        }
    )

    assert song.artists == (
        ArtistRef(id="ar1", name="Moore Kismet"),
        ArtistRef(id="ar2", name="YAOUNDÉBOXINGCLUB"),
    )


def test_album_keeps_each_credited_artist():
    album = Album.model_validate(
        {
            "id": "al1",
            "name": "Call of the Unicorn",
            "artist": "Moore Kismet feat. Tasha Baxter",
            "artistId": "ar1",
            "artists": [
                {"id": "ar1", "name": "Moore Kismet"},
                {"id": "ar3", "name": "Tasha Baxter"},
            ],
        }
    )

    assert album.artists == (
        ArtistRef(id="ar1", name="Moore Kismet"),
        ArtistRef(id="ar3", name="Tasha Baxter"),
    )


def test_song_and_album_without_artists_have_none():
    # Servers without OpenSubsonic do not send "artists".
    song = Song.model_validate({"id": "s1", "title": "Untitled"})
    album = Album.model_validate({"id": "al1", "name": "Untitled"})

    assert song.artists == ()
    assert album.artists == ()
