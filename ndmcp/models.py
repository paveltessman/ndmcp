# pyright: strict
from datetime import datetime

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic.alias_generators import to_camel


class _Model(BaseModel):
    # Subsonic uses camelCase keys, for example "playCount".
    model_config = ConfigDict(alias_generator=to_camel, frozen=True)


class Artist(_Model):
    id: str
    name: str
    album_count: int | None = None


class Album(_Model):
    id: str
    name: str
    artist: str | None = None
    artist_id: str | None = None
    year: int | None = None
    genre: str | None = None
    song_count: int | None = None
    # In seconds.
    duration: int | None = None
    # Navidrome does not send "playCount" when the count is 0.
    play_count: int = 0
    played: datetime | None = None


class Song(_Model):
    id: str
    title: str
    album: str | None = None
    album_id: str | None = None
    artist: str | None = None
    artist_id: str | None = None
    year: int | None = None
    genre: str | None = None
    # In seconds.
    duration: int | None = None
    # Navidrome does not send "playCount" when the count is 0.
    play_count: int = 0
    played: datetime | None = None


class Genre(_Model):
    name: str = Field(alias="value")
    song_count: int | None = None
    album_count: int | None = None
