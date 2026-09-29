# ndmcp: Navidrome MCP server, v1 spec

## Purpose

ndmcp is an MCP server for a Navidrome library.

## Scope

In scope for v1:

AI agent helps the user discover new music based on the library contents and play counts.

Tools should provide these capabilities:

- Read the library (songs, albums, artists, genres) and song play counts from Navidrome.
- Give a compact taste summary, with drill-down tools for more detail.
- Check candidate albums and songs against the library.
- Discovery inside the library (owned music that the user rarely plays).

Out of scope for v1:

- Write actions (playlists, stars, ratings, tags, organizing).
- Memory of past suggestions across chats. The server is stateless.
- Remote HTTP transport and server auth.
- External services (Last.fm, ListenBrainz, MusicBrainz).

## Decisions

| Topic         | Decision                                  |
| ------------- | ----------------------------------------- |
| Transport     | stdio                                     |
| Navidrome API | Subsonic API                              |
| Output        | Structured output                         |
| State         | Stateless, except a short in-memory cache |
| Users         | One Navidrome user                        |

## Library size

The user's library is small: fewer than about 300 artists or 1,000 albums. The server can load all songs into memory.

## Project layout and tooling (defaults)

```
ndmcp/
  __init__.py
  server.py
  subsonic.py
  library.py
  models.py
  ...
```

tests files lay next to their original file, e. g.:

```
...
server.py
server_test.py
...
```

- `pip`, `.venv` for the environment and dependencies. Dependencies: `mcp`, `httpx2`, `pydantic`.
- `pytest` for tests.
- `black`, `flake8`, `pyright` for lint, format and type checking.
