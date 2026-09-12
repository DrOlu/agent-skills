# Gateway configuration reference

Every setting is available as a command-line flag and as an environment variable. This
file is the complete list, taken from `reactorpro-gateway --help` and the loader in
`internal/config/config.go`.

**Precedence: flag beats environment.** Each flag's default *is* the environment value, so
`--http-addr=:3000` overrides `LIVEAGENT_GATEWAY_HTTP_ADDR` rather than conflicting with it.

## Contents

- [Identity and storage](#identity-and-storage)
- [Network](#network)
- [TLS](#tls)
- [Mesh / Synapse bridge](#mesh--synapse-bridge)
- [Timeouts](#timeouts)
- [WebSocket tuning](#websocket-tuning)
- [Connection limits](#connection-limits)
- [Environment variables with no flag](#environment-variables-with-no-flag)
- [Value parsing rules](#value-parsing-rules)
- [Deprecated arguments](#deprecated-arguments)

## Identity and storage

| Flag | Env var | Default | Notes |
|---|---|---|---|
| `-token` | `LIVEAGENT_GATEWAY_TOKEN` | *(none)* | **Required.** Empty → prints usage and panics with `gateway token is required`. Whitespace-trimmed. Generate with `openssl rand -hex 32`. |
| `-agent-db` | `LIVEAGENT_GATEWAY_AGENT_DB` | `<data dir>/gateway.db` | SQLite path for per-agent tokens. Auto-created. If set to empty it silently falls back to the default — it cannot be disabled. |
| — | `LIVEAGENT_GATEWAY_DATA_DIR` | OS user-config dir | Base for `gateway.db` and `mesh/`. No flag. See below. |

`LIVEAGENT_GATEWAY_DATA_DIR` resolves two defaults:

```
<data dir>/gateway.db
<data dir>/mesh/reactorpro-identity.json
```

Without it, the OS user-config directory is used: `~/.config/liveagent` (Linux),
`~/Library/Application Support/liveagent` (macOS), `%AppData%\liveagent` (Windows).

Set it explicitly on a server. An unset data dir on a service running as a system user
resolves somewhere surprising and easy to lose on upgrade.

The database is safe to copy while the gateway is stopped. The identity file is not
interchangeable between hosts if you want to keep the same fingerprint — copying it *does*
carry the identity across, deliberately, which is how you migrate a gateway to new
hardware without changing who it is.

## Network

| Flag | Env var | Default | Notes |
|---|---|---|---|
| `-http-addr` | `LIVEAGENT_GATEWAY_HTTP_ADDR` | `:443`, or `:$PORT` | Listen address. **Always set this explicitly.** |

The default deserves attention: if the `PORT` environment variable is set — the convention
on Heroku, Railway, Render, and similar platforms — the gateway listens on `:$PORT`
instead of `:443`. That is convenient on those platforms and a silent surprise elsewhere,
so set the address rather than relying on it.

Forms:

- `:3000` — all interfaces, port 3000. Needed for LAN access and containers.
- `127.0.0.1:3000` — loopback only. Right answer behind a reverse proxy.
- `0.0.0.0:3000` — equivalent to `:3000`, explicit.

## TLS

| Flag | Env var | Default |
|---|---|---|
| `-tls-cert` | `LIVEAGENT_GATEWAY_TLS_CERT` | *(empty)* |
| `-tls-key` | `LIVEAGENT_GATEWAY_TLS_KEY` | *(empty)* |

If **either** is non-empty the server calls `ListenAndServeTLS`, so set both or neither —
setting only one fails at startup with a file error.

Prefer terminating TLS at a reverse proxy and binding the gateway to `127.0.0.1`. That
keeps certificate renewal out of the service, lets you use the proxy's existing tooling,
and avoids restarting the gateway on every renewal. Configure TLS here only when the
gateway is directly internet-facing and no proxy exists.

## Mesh / Synapse bridge

The bridge is **disabled by default**. With it disabled, nothing connects anywhere.

| Flag | Env var | Default | Notes |
|---|---|---|---|
| `-mesh-enabled` | `LIVEAGENT_GATEWAY_MESH_ENABLED` | `false` | Accepts `1/true/yes/on` and `0/false/no/off`, case-insensitive. |
| `-mesh-url` | `LIVEAGENT_GATEWAY_MESH_URL` | *(empty)* | NATS URL, e.g. `nats://127.0.0.1:4222`, `tls://nats.example.com:4222`. |
| `-mesh-agent-id` | `LIVEAGENT_GATEWAY_MESH_AGENT_ID` | `drolu/reactorpro` | Overridden by the identity file once it exists. |
| `-mesh-identity-path` | `LIVEAGENT_GATEWAY_MESH_IDENTITY_PATH` | `<data dir>/mesh/reactorpro-identity.json` | Minted on first use, mode `0600`. |
| `-mesh-token` | `LIVEAGENT_GATEWAY_MESH_TOKEN` | *(empty)* | NATS token auth. |
| `-mesh-user` | `LIVEAGENT_GATEWAY_MESH_USER` | *(empty)* | NATS user auth. Requires a password. |
| `-mesh-password` | `LIVEAGENT_GATEWAY_MESH_PASSWORD` | *(empty)* | |
| `-mesh-name` | `LIVEAGENT_GATEWAY_MESH_NAME` | `ReactorPro Gateway` | Display name in the mesh manifest. |

**Authentication precedence is creds-file → token → user/password, and exactly one is
used.** Setting both a token and a user does not send both; the token wins. The gateway
exposes no creds-file flag, so from the gateway's side it is token or user/password.

Validation refuses to half-start:

- enabled with no URL → `mesh is enabled but no NATS URL is configured`
- user set with an empty password → `mesh user is set but the password is empty`
- empty agent id → `mesh is enabled but no agent id is configured`

A *connection* failure is different: it is logged, not fatal. The gateway keeps serving
and records the reason on `GET /api/mesh/status`. Never treat "the service is running" as
proof the mesh works.

Three mesh tunables exist in the bridge but are **not exposed** by the gateway, so they
always take their defaults: heartbeat interval 30s, dispatch timeout 120s, discovery
window 2s. If you need a different discovery window, that is a code change, not config.

See `mesh.md` for the identity model and wire behaviour.

## Timeouts

| Flag | Env var | Default | Meaning |
|---|---|---|---|
| `-request-timeout` | `LIVEAGENT_GATEWAY_REQUEST_TIMEOUT` | `2m` | Non-streaming API calls, including proxied fetches. |
| `-chat-prepare-timeout` | `LIVEAGENT_GATEWAY_CHAT_PREPARE_TIMEOUT` | `2s` | Pre-submit liveness probe of the desktop agent. |
| `-chat-delivery-timeout` | `LIVEAGENT_GATEWAY_CHAT_DELIVERY_TIMEOUT` | `5s` | Delivering an accepted chat command to the agent stream. |
| `-chat-start-timeout` | `LIVEAGENT_GATEWAY_CHAT_START_TIMEOUT` | `5s` | Waiting for a delivered remote chat to start. |
| `-chat-render-start-timeout` | `LIVEAGENT_GATEWAY_CHAT_RENDER_START_TIMEOUT` | `10s` | Extra wait for the desktop app to begin rendering. |
| `-heartbeat-period` | `LIVEAGENT_GATEWAY_HEARTBEAT_PERIOD` | `30s` | Ping interval on agent connections. |
| `-relay-buffer-seconds` | `LIVEAGENT_GATEWAY_RELAY_BUFFER_SECONDS` | `30` | Seconds of chat events buffered for brief reconnections. |

Durations use Go syntax: `30s`, `2m`, `1h30m`, `500ms`.

Raise `-chat-*-timeout` if agents are on slow or high-latency links and remote chats are
being reported as failed before the desktop app has had a chance to react.

## WebSocket tuning

| Flag | Env var | Default | Meaning |
|---|---|---|---|
| `-websocket-heartbeat-period` | `LIVEAGENT_GATEWAY_WS_HEARTBEAT_PERIOD` | `15s` | Ping interval for browser connections. |
| `-websocket-heartbeat-grace` | `LIVEAGENT_GATEWAY_WS_HEARTBEAT_GRACE` | `5s` | Slack added to the browser idle timeout (idle = 3× period + grace). |
| `-websocket-write-timeout` | `LIVEAGENT_GATEWAY_WS_WRITE_TIMEOUT` | `10s` | Write timeout for browser sockets. |
| `-websocket-write-queue-size` | `LIVEAGENT_GATEWAY_WS_WRITE_QUEUE_SIZE` | `512` | Write buffer depth. Raise if slow clients cause drops. |

Proxies in front of the gateway must allow WebSocket upgrades on `/ws/v2` and must not
impose an idle timeout shorter than the heartbeat interval — see
`service-managers.md`.

## Connection limits

Requests over a limit get `503` before the connection is upgraded. Defaults assume roughly
100 concurrent desktop agents.

| Flag | Env var | Default |
|---|---|---|
| `-max-agent-connections` | `LIVEAGENT_GATEWAY_MAX_AGENT_CONNECTIONS` | `256` |
| `-max-browser-connections` | `LIVEAGENT_GATEWAY_MAX_BROWSER_CONNECTIONS` | `128` |
| `-max-terminal-connections` | `LIVEAGENT_GATEWAY_MAX_TERMINAL_CONNECTIONS` | `512` |
| `-max-message-bytes` | `LIVEAGENT_GATEWAY_MAX_MESSAGE_BYTES` | `67108864` (64 MiB) |

A value of zero or below falls back to the default — these cannot be disabled by setting
zero. Raising the limits also means raising the process file-descriptor limit; check
`LimitNOFILE` in systemd before blaming the gateway for refusing connections. As a rough
guide, budget 20–30 descriptors per connected agent plus the terminal data plane.

## Environment variables with no flag

| Variable | Effect |
|---|---|
| `LIVEAGENT_GATEWAY_DATA_DIR` | Base path for the database and mesh identity. |
| `PORT` | Used as the default listen address when `--http-addr` is unset. |

## Value parsing rules

These are worth knowing because several of them fail *silently*:

- **Booleans** accept `1/true/yes/on` and `0/false/no/off`, case-insensitive. Anything
  else — including a typo like `ture` — falls back to the default (`false`). There is no
  warning, so a mesh that "will not turn on" can be a misspelled boolean.
- **Durations** use Go syntax; an unparsable value falls back to the default silently.
- **Integers** must be positive; zero, negative, or non-numeric falls back to the default
  silently.
- **Strings** are whitespace-trimmed. Quote characters are **not** removed *by the
  gateway* — but that is not the same as saying an env file must be unquoted, and the
  distinction matters:

  - `KEY="value"` in an environment file is **safe**. systemd's `EnvironmentFile` parser
    and a shell `source` both strip the surrounding quotes, so the gateway receives
    `value`. Quoting is in fact the correct way to pass a value containing spaces, such as
    a data directory like `/var/lib/ReactorPro Gateway`.
  - The trap is quotes that end up **inside the value**: `docker run -e KEY='"value"'`, or
    extracting a field verbatim from a file where the quotes are part of the field. The
    gateway then treats the quotes as part of the secret, and every client that sends the
    bare value gets a 401 — while the value "looks right" everywhere you inspect it.

  The same trap shows up when reading a NATS password out of a config file, where the
  line is commonly written `password: "s3cret"`. Strip the quotes while loading it, or the
  bridge reports an authorization violation with credentials that appear correct.

Because several of these fall back silently, verify behaviour by calling the API rather
than by re-reading the config. `/api/mesh/status` reports what the process actually did.

## Deprecated arguments

Removed flag names are stripped before parsing so an old unit file does not fail with
"flag provided but not defined". They no longer appear in `--help` and do not restore the
behaviour they once named:

- `-grpc-addr`, `-command-queue-timeout` — accepted and ignored.
- `-grpc-max-message-bytes` — translated to `-max-message-bytes` (the new name wins if
  both are present).
- `LIVEAGENT_GATEWAY_GRPC_MAX_MESSAGE_BYTES` — used as a fallback for
  `LIVEAGENT_GATEWAY_MAX_MESSAGE_BYTES` if the newer variable is unset.

Genuinely unknown arguments are still rejected. Prefer the current names in new
deployments.
