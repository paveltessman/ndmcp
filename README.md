# ndmcp

ndmcp is an MCP server for a [Navidrome](https://www.navidrome.org/) music library. It lets an AI agent read your library and play counts through the Subsonic API, and helps you discover new music based on what you own and listen to.

The server uses the stdio transport, works with one Navidrome user, and is read-only. For the full scope, see [docs/spec.md](docs/spec.md).

The project is in early development.

## Installation

ndmcp needs Python 3.10 or later. Install it into a virtual environment:

```sh
python -m venv .venv
.venv/bin/pip install -e .
```

This step adds the `ndmcp` command to `.venv/bin`.

## Configuration

ndmcp reads its settings from environment variables. Each variable has the `NDMCP_` prefix. The server treats an empty variable as not set.

| Variable           | Required | Default | Description                                                                    |
| ------------------ | -------- | ------- | ------------------------------------------------------------------------------ |
| `NDMCP_URL`        | Yes      |         | The base URL of the Navidrome server, for example `https://music.example.com`. |
| `NDMCP_USERNAME`   | Yes      |         | The Navidrome user name.                                                       |
| `NDMCP_PASSWORD`   | Yes      |         | The password for the Navidrome user.                                           |
| `NDMCP_TIMEOUT`    | No       | `10`    | The HTTP timeout for one Subsonic request, in seconds. Must be more than 0.    |
| `NDMCP_CACHE_TTL`  | No       | `300`   | How long the in-memory cache keeps data, in seconds. Must be 0 or more.        |
| `NDMCP_VERIFY_TLS` | No       | `true`  | Set to `false` to skip the check of the server TLS certificate.                |
| `NDMCP_LOG_LEVEL`  | No       | `INFO`  | One of `DEBUG`, `INFO`, `WARNING`, `ERROR`. The value is not case-sensitive.   |

If a required variable is missing or a value is not valid, ndmcp stops at startup. It writes a message to stderr that names each bad variable, and exits with the code 1.

## Running

The MCP client starts `ndmcp` and talks to it through stdin and stdout.

This example adds ndmcp to a client that uses the `mcpServers` config format, for example Claude Desktop:

```json
{
  "mcpServers": {
    "navidrome": {
      "command": "/path/to/ndmcp/.venv/bin/ndmcp",
      "env": {
        "NDMCP_URL": "https://music.example.com",
        "NDMCP_USERNAME": "alice",
        "NDMCP_PASSWORD": "secret"
      }
    }
  }
}
```

For Claude Code, use this command:

```sh
claude mcp add navidrome \
  -e NDMCP_URL=https://music.example.com \
  -e NDMCP_USERNAME=alice \
  -e NDMCP_PASSWORD=secret \
  -- /path/to/ndmcp/.venv/bin/ndmcp
```

The server does not connect to Navidrome at startup. The first tool call loads the full library, and the server keeps it for `NDMCP_CACHE_TTL` seconds. If Navidrome is not available, the tool call gives an error to the agent, but the server continues to run.

## Tools

All tools are read-only and give structured output. Each artist and album in a result has an `id` for the drill-down tools.

| Tool                    | Arguments                                        | Result                                                                          |
| ----------------------- | ------------------------------------------------ | ------------------------------------------------------------------------------- |
| `taste_summary`         | `limit` (1 to 50, default 10)                    | The library totals, and the most played artists, albums and genres.             |
| `artist_details`        | `artist_id`                                      | The artist with its play count, and its albums with play counts, oldest first.  |
| `album_details`         | `album_id`                                       | The album with its play count, and its songs with play counts.                  |
| `check_artists`         | `names`: 1 to 50 names                           | For each candidate, the artists in the library with the same name.              |
| `check_albums`          | `albums`: 1 to 50 of `{name, artist?}`           | For each candidate, the albums in the library with the same name, all editions. |
| `check_songs`           | `songs`: 1 to 50 of `{title, artist?}`           | For each candidate, the songs in the library with the same title.               |
| `rarely_played_artists` | `max_plays` (default 0), `limit` (default 20)    | The artists with `max_plays` plays or less, the least played first.             |
| `rarely_played_albums`  | `max_plays` (default 0), `limit` (default 20)    | The albums with `max_plays` plays or less, the least played first.              |

The check tools compare normalized names. The comparison ignores case, accents, punctuation, a leading "The" and trailing groups in brackets, for example "(Remastered)". The artist filter of `check_albums` and `check_songs` matches each credited artist, so "Moore Kismet" matches a song by "Moore Kismet & YAOUNDÉBOXINGCLUB". An empty list of matches means that the library does not have the item.

A play count is the sum of the play counts of the songs. Navidrome counts the plays for the configured user only.
