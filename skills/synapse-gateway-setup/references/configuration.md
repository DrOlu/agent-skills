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

### The agent id is permanent — choose it deliberately

`-mesh-agent-id` is **an address, not a label**, and it is written into the identity file on
first start:

- it forms the subject peers send to, `mesh.agent.<id>.inbox`;
- it is **hashed into the fingerprint**, so the id and the key together are the identity.

Consequences worth knowing before you type it:

- **It cannot be reassigned.** Configuring a different id later is a *hard startup failure*
  (`identity at <path> belongs to "X", not "Y": the agent id is part of the fingerprint and
  cannot be reassigned`), not a warning. Changing it means moving the identity file aside to
  mint a new one, which changes your fingerprint and breaks every peer that pinned the old one.
- **Every edge needs a different id.** Two edges sharing one discard each other as "self", so
  the mesh looks empty while every service reports healthy. The gateway detects this and logs a
  collision warning naming both endpoints and fingerprints.
- **The legacy shared default (`drolu/reactpro`) cannot federate.** An edge still on it logs a
  loud startup warning; it is only retained so an identity minted under it keeps loading.
- Use `<org>/<site>/<edge>`. Left unset the gateway derives `reactorpro/<sanitised-hostname>`,
  which is unique per host but says nothing about who you are.

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
| `-mesh-agent-id` | `LIVEAGENT_GATEWAY_MESH_AGENT_ID` | `reactorpro/<sanitised-hostname>` | **An address, not a label** — and permanent once the identity file exists. Use `<org>/<site>/<edge>`, unique per edge. See the warning below. |
| `-mesh-identity-path` | `LIVEAGENT_GATEWAY_MESH_IDENTITY_PATH` | `<data dir>/mesh/reactorpro-identity.json` | Minted on first use, mode `0600`. |
| `-mesh-token` | `LIVEAGENT_GATEWAY_MESH_TOKEN` | *(empty)* | NATS token auth. |
| `-mesh-user` | `LIVEAGENT_GATEWAY_MESH_USER` | *(empty)* | NATS user auth. Requires a password. |
| `-mesh-password` | `LIVEAGENT_GATEWAY_MESH_PASSWORD` | *(empty)* | |
| `-mesh-creds-file` | `LIVEAGENT_GATEWAY_MESH_CREDS_FILE` | *(empty)* | NATS credentials file (NKey/JWT). The only route to the stronger NATS auth modes. |
| `-mesh-name` | `LIVEAGENT_GATEWAY_MESH_NAME` | `ReactorPro Gateway` | Display name in the mesh manifest. |

### Mesh trust and inbound limits

| Flag | Env var | Default | Notes |
|---|---|---|---|
| `-mesh-verify-mode` | `LIVEAGENT_GATEWAY_MESH_VERIFY_MODE` | `prefer` | `off`, `prefer` (verify when signed, accept unsigned), or `require` (refuse unsigned). An unrecognised value is rejected at startup rather than silently downgraded. |
| `-mesh-trusted-peers` | `LIVEAGENT_GATEWAY_MESH_TRUSTED_PEERS` | *(empty)* | Comma-separated fingerprints (`sha256:<hex16>`) accepted without first-use learning. |
| `-mesh-trust-on-first-use` | `LIVEAGENT_GATEWAY_MESH_TRUST_ON_FIRST_USE` | `true` | Record a peer's fingerprint on its first verified message. Set false to accept only `-mesh-trusted-peers`. |
| `-mesh-clock-skew` | `LIVEAGENT_GATEWAY_MESH_CLOCK_SKEW` | `5m` | How far an envelope timestamp may drift before it is refused. |
| `-mesh-max-envelope-bytes` | `LIVEAGENT_GATEWAY_MESH_MAX_ENVELOPE_BYTES` | `1048576` | Cap on a single inbound envelope. |
| `-mesh-rate-limit-per-second` | `LIVEAGENT_GATEWAY_MESH_RATE_LIMIT_PER_SECOND` | `50` | Sustained inbound messages per sender. **`0` disables the limit** — unlike the integer settings above, zero is a meaningful value here. |
| `-mesh-rate-limit-burst` | `LIVEAGENT_GATEWAY_MESH_RATE_LIMIT_BURST` | `100` | Back-to-back allowance per sender. |

Turning off first-use learning with no configured peers is rejected at startup: no peer
could ever authenticate.

### Mesh served skills

| Flag | Env var | Default | Notes |
|---|---|---|---|
| `-mesh-skills-enabled` | `LIVEAGENT_GATEWAY_MESH_SKILLS_ENABLED` | `true` | Serve mesh skills at all. **`false` serves nothing, `invoke` included.** |
| `-mesh-skills` | `LIVEAGENT_GATEWAY_MESH_SKILLS` | *(empty = all)* | Comma-separated subset to serve. An unknown id is rejected at startup rather than silently unserved. `invoke` is a valid name here. |
| `-mesh-capabilities` | `LIVEAGENT_GATEWAY_MESH_CAPABILITIES` | `agent,reactorpro` | What **this edge** advertises, so peers can filter for a site that can do something. Not the same as the capabilities of the desktop agents behind it. |

Three of the four served skills are read-only: `ping`, `describe`, `status`. `describe` now
includes this edge's **local agent directory** (the agents behind it). `status` reports only the
gateway's own identity, readiness and traffic counters — never the connected desktop agents or
their tokens. Disable the surface entirely with `-mesh-skills-enabled=false` if a peer has no
business probing you.

The fourth, `invoke`, does work. Its gates are below.

### Remote invocation

| Flag | Env var | Default | Notes |
|---|---|---|---|
| `-mesh-allow-remote-invoke` | `LIVEAGENT_GATEWAY_MESH_ALLOW_REMOTE_INVOKE` | `true` | May peers ask agents behind this edge to run tasks at all? |
| `-mesh-require-verified-invoke` | `LIVEAGENT_GATEWAY_MESH_REQUIRE_VERIFIED_INVOKE` | **`true`** | **The safety floor.** Refuse an invocation whose caller identity was not actually verified. |
| `-mesh-invoke-operations` | `LIVEAGENT_GATEWAY_MESH_INVOKE_OPERATIONS` | `task` | Exact allowlist of operations. **Empty exposes none — deliberately the opposite of the skills allowlist, where empty means all.** |
| `-mesh-invoke-timeout` | `LIVEAGENT_GATEWAY_MESH_INVOKE_TIMEOUT` | `3m0s` | How long one **synchronous** remote invocation may run before the edge gives up and tells the desktop to cancel. A caller may only *narrow* this with `timeout_ms`; work that may exceed it belongs on `POST /api/mesh/tasks`, not a longer sync wait. |

**Why the floor matters.** The default verify mode is `prefer`, which accepts unsigned envelopes.
Without `-mesh-require-verified-invoke`, an invocation would be reachable by anything able to
publish to the NATS subject — anonymous remote code execution on a desktop machine. Keep it on
across organisation boundaries. Turning it off is possible and sometimes deliberate (a trusted
single-site fleet), but it should be a decision, not an oversight.

Startup validation refuses the contradictory combination: invoke enabled + require-verified +
`verify-mode=off`. There, no caller could ever be verified and every invocation would be refused.

A gateway with **no desktop agent attached** still serves the read-only skills but can never serve
`invoke` — there is nothing to route to, and callers get `3002 AGENT_UNAVAILABLE`.

### Discovery registry

| Flag | Env var | Default | Notes |
|---|---|---|---|
| `-mesh-registry` | `LIVEAGENT_GATEWAY_MESH_REGISTRY` | `auto` | `auto` (merge registry + broadcast), `jetstream` (registry only, **startup fails** without JetStream), `broadcast` (never uses JetStream). An unrecognised value is rejected rather than silently downgraded. |
| `-mesh-registry-bucket` | `LIVEAGENT_GATEWAY_MESH_REGISTRY_BUCKET` | `mesh_registry` | JetStream KV bucket holding one manifest per edge. |
| `-mesh-registry-ttl` | `LIVEAGENT_GATEWAY_MESH_REGISTRY_TTL` | `0` (= three heartbeat intervals, ~`1m30s`) | How long an entry stays valid without a heartbeat. Expired entries are treated as absent, so a crashed edge stops being advertised. |

**`auto` merges both mechanisms, and that is not a nicety.** A peer that publishes nothing to the
bucket — an older build, or a different implementation — appears only in the broadcast. A
registry-only setting makes an upgraded edge blind to it *silently*, because the registry read
still succeeds (it returns at least your own entry), so the "read failed → fall back" path never
runs. If any edge in your fleet is not upgraded, leave this on `auto`.

**Registry entries are data, not identity.** A manifest read from the bucket can never make a peer
trusted; trust comes only from a verified signature.

**Authentication precedence is creds-file → token → user/password, and exactly one is
used.** Setting both a token and a user does not send both; the token wins.

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

## Durable mailbox flags (v1.5.4+)

| Flag | Env | Default | Meaning |
|---|---|---|---|
| `-mesh-mailbox` | `LIVEAGENT_GATEWAY_MESH_MAILBOX` | off | Buffer skill invocations for an absent agent in JetStream and deliver them when it returns |
| `-mesh-mailbox-stream` | `LIVEAGENT_GATEWAY_MESH_MAILBOX_STREAM` | `MESH_AGENT_MAILBOX` | Stream name. Do NOT name it `AGENT_INBOXES` — that name is already used by fleets for their own stream |
| `-mesh-mailbox-max-age` | `LIVEAGENT_GATEWAY_MESH_MAILBOX_MAX_AGE` | 7d | How long undelivered mail is retained |
| `-mesh-mailbox-max-msgs` | `LIVEAGENT_GATEWAY_MESH_MAILBOX_MAX_MSGS` | 10000 | Bound per stream |

Requires JetStream; enabled without it is a startup error, not a silent
downgrade. Delivery is at-least-once — skills reached through the mailbox must
be idempotent.
