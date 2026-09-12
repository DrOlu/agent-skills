---
name: reactorpro-gateway-setup
description: Install, configure, and operate the ReactorPro gateway binary as a headless service on any server — Linux (systemd), macOS (launchd), Windows, or Docker. Use this skill whenever the user wants to deploy ReactorPro's gateway, stand up a ReactorPro server or VPS, run reactorpro-gateway as a background service, enable the NATS/Synapse mesh bridge, connect ReactorPro desktop apps to a shared gateway, or troubleshoot a gateway that will not start, returns 401, or reports the mesh as disconnected. Also use it for upgrading the gateway and for backing up its identity.
---

# ReactorPro Gateway — Server Setup

The ReactorPro gateway is a single static Go binary. It serves the ReactorPro web UI,
brokers connections from ReactorPro desktop apps, and optionally joins a NATS/Synapse
agent mesh. There are no runtime dependencies: no Docker, no Go toolchain, no Node, no
shared libraries. One file, one token, one config.

Use this skill to stand it up on a server and keep it running.

## The shape of a deployment

Five things matter, and getting the first three wrong is the usual cause of a gateway
that "runs" but does not work:

1. **A gateway token.** The only required setting. Nothing else is mandatory.
2. **A listen address.** Defaults to `:443`, which is almost never what you want on a
   server. Set it explicitly.
3. **A persistent data directory.** Holds the SQLite database *and the mesh identity*.
   The identity is not reproducible — lose it and the keypair is gone for good.
4. **A service manager** so it survives logout, reboot, and crashes.
5. **Optionally, the mesh bridge** — disabled unless explicitly enabled and pointed at
   a NATS server.

## Quick start

Install with the bundled script — it detects the platform, downloads from GitHub
Releases, and **verifies the SHA-256 checksum before installing**:

```bash
scripts/install-gateway.sh                 # installs to /usr/local/bin (or ~/.local/bin)
scripts/install-gateway.sh --with-systemd  # ...and installs + starts a systemd service
```

Then confirm it is actually healthy, not merely running:

```bash
curl -s localhost:3000/healthz                          # {"ok":true} — no token needed
curl -s -H "Authorization: Bearer $TOKEN" \
     localhost:3000/api/mesh/status                     # agentId + fingerprint
```

`/healthz` only proves the process is listening. The authenticated checks are what tell
you the gateway is configured correctly — see **Verify the deployment** below.

## Manual install

Binaries are published per release for five targets. Download the matching one:

| Platform | Asset |
|---|---|
| Linux x86-64 | `reactorpro-gateway-linux-amd64` |
| Linux ARM64 | `reactorpro-gateway-linux-arm64` |
| macOS Intel | `reactorpro-gateway-darwin-amd64` |
| macOS Apple silicon | `reactorpro-gateway-darwin-arm64` |
| Windows x86-64 | `reactorpro-gateway-windows-amd64.exe` |

```bash
BASE=https://github.com/DrOlu/ReactorPro/releases/latest/download
curl -fsSLO "$BASE/reactorpro-gateway-linux-amd64"
curl -fsSLO "$BASE/SHA256SUMS"
sha256sum -c --ignore-missing SHA256SUMS     # macOS: shasum -a 256 -c
install -m 0755 reactorpro-gateway-linux-amd64 /usr/local/bin/reactorpro-gateway
```

Verify the checksum. These are unsigned binaries; the checksum is the only integrity
signal you get, and it is worthless if you skip it.

Pin a version by replacing `latest/download` with `download/v1.3.9`.

## Configure

Settings come from command-line flags, environment variables, or both. **Flags win over
environment variables**; for each setting the flag's value is simply initialised from the
environment, so passing the flag overrides it.

Two rules of thumb:

- **Put the token in the environment, never in the command line.** Arguments are visible
  to every user on the host via `ps`. Use an `EnvironmentFile` (systemd), a `0600` file
  sourced by a launcher (launchd), or the service's environment (Windows).
- **Quote only what needs quoting.** The gateway trims whitespace but does **not** strip
  quote characters from a value — so quotes must not be part of the value. Quotes that are
  *file syntax* are fine: systemd's environment-file parser and a shell `source` both
  remove surrounding quotes before the gateway sees the value, which is how you pass a
  path containing spaces. The failure mode is quotes that reach the process literally,
  e.g. `docker run -e LIVEAGENT_GATEWAY_TOKEN='"abc"'` — the gateway then expects the
  quotes to be sent by every client, and `Bearer abc` gets a 401.

Minimal configuration:

```bash
LIVEAGENT_GATEWAY_TOKEN=$(openssl rand -hex 32)   # 256-bit; 32+ chars is sensible
LIVEAGENT_GATEWAY_HTTP_ADDR=:3000
LIVEAGENT_GATEWAY_DATA_DIR=/var/lib/reactorpro-gateway
```

The five settings that cover almost every deployment:

| Setting | Flag | Env var | Default |
|---|---|---|---|
| Gateway token | `-token` | `LIVEAGENT_GATEWAY_TOKEN` | *(required)* |
| Listen address | `-http-addr` | `LIVEAGENT_GATEWAY_HTTP_ADDR` | `:443`, or `:$PORT` if `PORT` is set |
| Data directory | — | `LIVEAGENT_GATEWAY_DATA_DIR` | user config dir |
| TLS cert / key | `-tls-cert` / `-tls-key` | `LIVEAGENT_GATEWAY_TLS_CERT` / `_KEY` | *(off — plain HTTP)* |
| Mesh on/off | `-mesh-enabled` | `LIVEAGENT_GATEWAY_MESH_ENABLED` | `false` |

Run `reactorpro-gateway --help` for the full list. `references/configuration.md` documents
every flag with its default and when to change it.

### Choosing a listen address

- `127.0.0.1:3000` — behind a reverse proxy or only for local apps. **Preferred for
  anything internet-facing**; the proxy terminates TLS.
- `:3000` — reachable from the LAN. Required when desktop apps on other machines connect
  directly, and when running in a container.
- `:443` (the default) — only correct if the gateway itself terminates TLS.

The gateway speaks plain HTTP unless you give it `-tls-cert` and `-tls-key`. Terminating
TLS at nginx/Caddy/Cloudflare in front of a loopback bind is simpler to operate and keeps
certificate renewal out of the gateway.

### The data directory

`LIVEAGENT_GATEWAY_DATA_DIR` is the base for two files:

- `gateway.db` — SQLite database of per-agent tokens. Auto-created. Safe to back up.
- `mesh/reactorpro-identity.json` — the mesh identity. **Not** reproducible. See below.

Without it the gateway falls back to the OS user-config directory
(`~/.config/liveagent` on Linux, `~/Library/Application Support/liveagent` on macOS,
`%AppData%\liveagent` on Windows). Set it explicitly on a server so the location is
obvious and service-independent.

**Back up `mesh/reactorpro-identity.json` before your first upgrade.** The file holds an
Ed25519 keypair and a fingerprint computed over the agent id *and* the public key. Edit the
id inside it and the file refuses to load; point the config at a different id and startup
fails with *"the agent id is part of the fingerprint and cannot be reassigned"*. That is
what makes the agent id unchangeable — **locally**.

Be precise about what that does and does not buy you today. The gateway signs every
envelope it sends (`sig` + `pub`), but **nothing verifies those signatures**: the
verification function exists yet is only called from tests, and inbound requests are
processed without checking them. The fingerprint is local-only too — it is not part of the
manifest, so peers never receive it and cannot pin it. So a lost identity file mints a new
keypair under the *same* agent id, and peers notice nothing.

Back it up anyway. It is the only copy of the key, and the moment signature verification is
enforced the identity becomes load-bearing — at which point a host with the wrong key is
refused rather than silently trusted.

### Access control

The gateway has exactly one authentication mechanism:

```
Authorization: Bearer <gateway token>
```

That header form is required — a bare token, `?token=`, or a custom header is rejected
with 401. Everything under `/api/` is gated by it. Two exceptions:

- `GET /healthz` — unauthenticated, returns `{"ok":true}`. Safe for load balancers and
  orchestrator probes.
- `GET /` plus `/assets/*` — the embedded web UI, unauthenticated (the UI asks for the
  token itself).

Give each desktop agent its own credential rather than sharing the gateway token:
`POST /api/agents/{id}/token`. Per-agent tokens let you revoke one machine without
rotating every client. `references/api.md` has the request shapes.

## Run it as a service

Pick the section for the platform. Full unit files, hardening options, and Docker notes
are in `references/service-managers.md`.

### Linux — systemd

```ini
# /etc/systemd/system/reactorpro-gateway.service
[Unit]
Description=ReactorPro Gateway
After=network-online.target
Wants=network-online.target

[Service]
User=reactorpro
EnvironmentFile=/etc/reactorpro-gateway.env
ExecStart=/usr/local/bin/reactorpro-gateway --http-addr=127.0.0.1:3000
Restart=always
RestartSec=5
StateDirectory=reactorpro-gateway

[Install]
WantedBy=multi-user.target
```

```bash
install -d -m 0750 -o reactorpro -g reactorpro /var/lib/reactorpro-gateway
printf 'LIVEAGENT_GATEWAY_TOKEN=%s\n' "$(openssl rand -hex 32)" \
  > /etc/reactorpro-gateway.env
chmod 0600 /etc/reactorpro-gateway.env
# add: LIVEAGENT_GATEWAY_DATA_DIR=/var/lib/reactorpro-gateway
systemctl daemon-reload && systemctl enable --now reactorpro-gateway
```

The environment file **must** be readable by the service user — `0600` owned by root
works because systemd reads it as root before dropping privileges, but `0640`
root:reactorpro is clearer if you ever start the binary by hand.

### macOS — launchd

`~/Library/LaunchAgents/ng.reactorpro.gateway.plist` starts at **login**; put the same
file in `/Library/LaunchDaemons/` to start at **boot** (needs `sudo` and a `UserName`).
`RunAtLoad` starts it, `KeepAlive` restarts it after a crash. Keep the token in a `0600`
file the launcher reads at start time rather than inline in the plist. A working pair of
files is in `references/service-managers.md`, and the templates ship in `scripts/`.

### Windows

The binary is **not** a Windows service — `sc.exe create` will fail. Either use a wrapper
(NSSM, WinSW) or a Task Scheduler entry with "Run whether user is logged on or not" and
a trigger of "At startup". Set the token as a machine environment variable
(`setx /M`) so it is not in the task's arguments.

### Docker

An image is published as `ghcr.io/drolu/liveagent-gateway`. That name is a legacy
internal identifier kept deliberately; it is the ReactorPro gateway. Mount the data
directory as a volume so the identity survives container replacement, and remember to
publish the port (`-p 3000:3000`) with `--http-addr=:3000`.

## Verify the deployment

Work down this list — each step depends on the one before it:

```bash
TOKEN=$(grep -oP '(?<=LIVEAGENT_GATEWAY_TOKEN=).*' /etc/reactorpro-gateway.env)

# 1. Process is listening (no auth)
curl -s localhost:3000/healthz

# 2. Token is accepted. A 401 here means the token is wrong, was rotated, or has
#    quote characters inside the value — see references/troubleshooting.md.
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "Authorization: Bearer $TOKEN" localhost:3000/api/status

# 3. The web UI is served
curl -s localhost:3000/ | grep -o '<title>.*</title>'

# 4. Mesh — only meaningful if you enabled it
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/mesh/status

# 5. Peers are reachable
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/mesh/agents
```

Expected results:

- `/healthz` → `{"ok":true}`
- `/api/status` → `200`
- `/api/mesh/status` → `connected: true`, an `agentId`, and a `fingerprint` of the form
  `sha256:<16 hex chars>`
- `/api/mesh/agents` → a list of peers

**`/api/mesh/agents` takes about two seconds, and that is correct.** Discovery collects
replies for a fixed window rather than stopping at the first answer, because agents
respond individually as well as the registry. Do not point a 1-second HTTP timeout at it
and conclude the mesh is broken; allow at least 3 seconds.

If `/api/mesh/status` reports `connected: false`, read its `lastError` field — it carries
the reason. Check `references/troubleshooting.md` for the common ones.

## Connecting desktop apps

In each ReactorPro desktop app, open **Settings → Remote**:

| Field | Value |
|---|---|
| Gateway URL | `http://<host>` — **include the scheme** |
| Port | the `--http-addr` port, e.g. `3000` |
| Access Token | the gateway token, or a per-agent token |

Include `http://`. A bare host is normalised to `https://` by the client, which then fails
against a plain-HTTP gateway with a TLS error that looks nothing like a config mistake.

## Enabling the mesh

Disabled by default; with it disabled nothing connects anywhere. To join a NATS server:

```bash
LIVEAGENT_GATEWAY_MESH_ENABLED=true
LIVEAGENT_GATEWAY_MESH_URL=nats://127.0.0.1:4222
LIVEAGENT_GATEWAY_MESH_AGENT_ID=drolu/reactorpro
LIVEAGENT_GATEWAY_MESH_USER=reactorpro
LIVEAGENT_GATEWAY_MESH_PASSWORD=<password>
```

Mesh authentication accepts exactly one of: a token, or user + password (in that
precedence). Enabling the mesh without a URL is refused at startup, and setting a user
without a password is refused too — the bridge refuses to half-start. A *connection*
failure, by contrast, is **not** fatal: the gateway keeps serving and records the reason
on `/api/mesh/status`. So "the service is running" never proves the mesh works.

`LIVEAGENT_GATEWAY_MESH_AGENT_ID` is only a default. Once the identity file exists, the id
inside it wins and cannot be reassigned — see `references/mesh.md` for the full model,
including capabilities, the agent inbox subject, and events.

## Upgrading

The upgrade is: replace the binary, keep the data directory, restart.

```bash
systemctl stop reactorpro-gateway
install -m 0755 reactorpro-gateway-linux-amd64 /usr/local/bin/reactorpro-gateway
systemctl start reactorpro-gateway
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/mesh/status
```

Confirm the **fingerprint is unchanged** afterwards. If it changed, you pointed the new
process at a different data directory and it minted a fresh identity — fix the path and
restore the backup before anything else, because peers have already seen the new one.

## Troubleshooting index

| Symptom | Likely cause |
|---|---|
| Exits immediately, "gateway token is required" | `LIVEAGENT_GATEWAY_TOKEN` empty or unset |
| Service runs, every client gets 401 | Quotes round the token in the env file, or a trailing newline |
| Reachable on the host, not from outside | Bound to `127.0.0.1`; or host/cloud firewall |
| `connected: false`, `lastError` mentions authorization | Wrong NATS user/password; check for quotes in the NATS config |
| `connected: false`, `lastError` mentions connect | NATS unreachable at `LIVEAGENT_GATEWAY_MESH_URL` |
| Peers see a different fingerprint after a move | Identity file was lost or the data dir changed |
| `/api/mesh/agents` times out in a client | Client timeout under ~3s; discovery is a fixed ~2s window |
| TLS handshake error from the desktop app | Gateway URL lacks `http://` |
| WebSocket failures through a proxy | Proxy not configured for upgrade on `/ws/v2*` |

`references/troubleshooting.md` covers each with diagnosis commands.

## Reference files

Read these when you need the detail — they are not loaded until you open them.

- `references/configuration.md` — every flag and environment variable, with defaults and
  guidance on when a value needs changing.
- `references/mesh.md` — the NATS/Synapse mesh: identity model, authentication,
  capabilities, subjects, events, and governance.
- `references/service-managers.md` — complete systemd, launchd, Windows, and Docker
  setups, including reverse-proxy configuration.
- `references/api.md` — HTTP endpoints, authentication, request/response shapes, and
  agent token issuance.
- `references/troubleshooting.md` — symptom → diagnosis → fix, with commands.

For questions about the ReactorPro desktop application itself (features, skills, MCP
servers), use the `reactorpro-doc` skill instead — this one is only about the server.
