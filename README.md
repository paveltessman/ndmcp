# ndmcp

ndmcp is an MCP server for a [Navidrome](https://www.navidrome.org/) music library. It lets an AI agent read your library and play counts through the Subsonic API, and helps you discover new music based on what you own and listen to.

The server uses the stdio transport, works with one Navidrome user, and is read-only. For the full scope, see [docs/spec.md](docs/spec.md).

The project is in early development.

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

If a required variable is missing or a value is not valid, ndmcp raises a `ConfigError` that names each bad variable.
