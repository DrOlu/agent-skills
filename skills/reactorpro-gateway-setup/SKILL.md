---
name: reactorpro-gateway-setup
description: Install, configure, and operate the ReactorPro gateway binary as a headless service on any server — Linux (systemd), macOS (launchd), Windows, or Docker — and federate it into a NATS/Synapse agent mesh. Use this skill whenever the user wants to deploy ReactorPro's gateway, stand up a ReactorPro server or VPS, run reactorpro-gateway as a background service, enable the mesh bridge, let agents in one organisation reach agents in another, connect ReactorPro desktop apps to a shared gateway, run a gateway with no desktop app attached, or troubleshoot a gateway that will not start, returns 401, reports the mesh as disconnected, or sees zero peers. Also use it for upgrading the gateway, backing up its identity, and choosing mesh settings for intra- or inter-organisation deployments.
---

# ReactorPro Gateway — Server Setup

The ReactorPro gateway is a single static Go binary. It serves the ReactorPro web UI,
brokers connections from ReactorPro desktop apps, and can join a NATS/Synapse agent mesh
so that agents in one organisation reach agents in another. There are no runtime
dependencies: no Docker, no Go toolchain, no Node, no shared libraries. One file, one
token, one config.

Use this skill to stand it up on a server and keep it running.

## Which kind of deployment are you building?

The gateway works with **or without** a desktop app attached, and the settings differ. Answer
this first — it changes what you configure and what you can expect.

| If… | Go to |
|---|---|
| No ReactorPro desktop app will connect — a VPS, jump host, or central node | [**Gateway only**](#no-desktop-agent-gateway-only) |
| One organisation, one site, desktop apps connecting | [**Standard site**](#the-standard-site) |
| Several of your own sites that should find each other | `references/scenarios.md` → S3 |
| Another company involved | `references/scenarios.md` → S4 |
| Some edges are not upgraded yet | `references/scenarios.md` → S5 (**read this — it prevents the most confusing failure**) |
| Regulated or hostile-adjacent traffic | `references/scenarios.md` → S6 |
| A partner organisation with no desktop agents of their own | `references/scenarios.md` → S7 |

`references/scenarios.md` carries the full playbooks: what to set, how to verify, and what each
scenario **cannot** do.

## The shape of a deployment

Five things matter, and getting the first three wrong is the usual cause of a gateway that
"runs" but does not work:

1. **A gateway token.** The only required setting. Nothing else is mandatory.
2. **A listen address.** Defaults to `:443`, which is almost never what you want on a server.
   Set it explicitly.
3. **A persistent data directory.** Holds the SQLite database *and the mesh identity*. The
   identity is not reproducible — lose it and the keypair is gone for good.
4. **A service manager** so it survives logout, reboot, and crashes.
5. **Optionally, the mesh bridge** — disabled unless explicitly enabled and pointed at a NATS
   server.

## Quick start

Install with the bundled script — it detects the platform, downloads from GitHub Releases, and
**verifies the SHA-256 checksum before installing**:

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

`/healthz` only proves the process is listening. The authenticated checks are what tell you the
gateway is configured correctly — see **Verify the deployment** below.

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

Verify the checksum. These are unsigned binaries; the checksum is the only integrity signal you
get, and it is worthless if you skip it.

Pin a version by replacing `latest/download` with `download/v1.5.2`.

You can also confirm what you are running without downloading anything — GitHub exposes a
server-computed digest per asset:

```bash
gh api repos/DrOlu/ReactorPro/releases/tags/v1.5.2 --jq '.assets[]|{name,digest}'
```

## Configure

Settings come from command-line flags, environment variables, or both. **Flags win over
environment variables**; for each setting the flag's value is simply initialised from the
environment, so passing the flag overrides it.

Two rules of thumb:

- **Put the token in the environment, never in the command line.** Arguments are visible to every
  user on the host via `ps`. Use an `EnvironmentFile` (systemd), a `0600` file sourced by a
  launcher (launchd), or the service's environment (Windows).
- **Quote only what needs quoting.** The gateway trims whitespace but does **not** strip quote
  characters from a value — so quotes must not be part of the value. Quotes that are *file syntax*
  are fine: systemd's environment-file parser and a shell `source` both remove surrounding quotes
  before the gateway sees the value, which is how you pass a path containing spaces. The failure
  mode is quotes that reach the process literally, e.g.
  `docker run -e LIVEAGENT_GATEWAY_TOKEN='"abc"'` — the gateway then expects the quotes to be sent
  by every client, and `Bearer abc` gets a 401.

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

Run `reactorpro-gateway --help` for the full list. `references/configuration.md` documents every
flag with its default and when to change it.

### Choosing a listen address

- `127.0.0.1:3000` — behind a reverse proxy or only for local apps. **Preferred for anything
  internet-facing**; the proxy terminates TLS.
- `:3000` — reachable from the LAN. Required when desktop apps on other machines connect
  directly, and when running in a container.
- `:443` (the default) — only correct if the gateway itself terminates TLS.

The gateway speaks plain HTTP unless you give it `-tls-cert` and `-tls-key`. Terminating TLS at
nginx/Caddy/Cloudflare in front of a loopback bind is simpler to operate and keeps certificate
renewal out of the gateway.

### The data directory

`LIVEAGENT_GATEWAY_DATA_DIR` is the base for two files:

- `gateway.db` — SQLite database of per-agent tokens. Auto-created. Safe to back up.
- `mesh/reactorpro-identity.json` — the mesh identity. **Not** reproducible. See below.

Without it the gateway falls back to the OS user-config directory (`~/.config/liveagent` on
Linux, `~/Library/Application Support/liveagent` on macOS, `%AppData%\liveagent` on Windows). Set
it explicitly on a server so the location is obvious and service-independent.

**Back up `mesh/reactorpro-identity.json` before your first upgrade.** The file holds an Ed25519
keypair and a fingerprint computed over the agent id *and* the public key. Edit the id inside it
and the file refuses to load; point the config at a different id and startup fails with *"the
agent id is part of the fingerprint and cannot be reassigned"*. Every outbound envelope is signed
and carries that fingerprint, and the manifest advertises it so peers can pin this gateway.

So losing the identity file is not silent: a new keypair is minted under the *same* agent id, and
any peer that already pinned the old fingerprint will refuse this gateway as an identity mismatch.
Restore from backup, or accept the new identity and tell your peers.

### Access control

The gateway has exactly one authentication mechanism:

```
Authorization: Bearer <gateway token>
```

That header form is required — a bare token, `?token=`, or a custom header is rejected with 401.
Everything under `/api/` is gated by it. Two exceptions:

- `GET /healthz` — unauthenticated, returns `{"ok":true}`. Safe for load balancers and
  orchestrator probes.
- `GET /` plus `/assets/*` — the embedded web UI, unauthenticated (the UI asks for the token
  itself).

Give each desktop agent its own credential rather than sharing the gateway token:
`POST /api/agents/{id}/token`. Per-agent tokens let you revoke one machine without rotating every
client. `references/api.md` has the request shapes.

## Run it as a service

Pick the section for the platform. Full unit files, hardening options, and Docker notes are in
`references/service-managers.md`.

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

The environment file **must** be readable by the service user — `0600` owned by root works because
systemd reads it as root before dropping privileges, but `0640` root:reactorpro is clearer if you
ever start the binary by hand.

### macOS — launchd

`~/Library/LaunchAgents/ng.reactorpro.gateway.plist` starts at **login**; put the same file in
`/Library/LaunchDaemons/` to start at **boot** (needs `sudo` and a `UserName`). `RunAtLoad` starts
it, `KeepAlive` restarts it after a crash. Keep the token in a `0600` file the launcher reads at
start time rather than inline in the plist. A working pair of files is in
`references/service-managers.md`, and the templates ship in `scripts/`.

### Windows

The binary is **not** a Windows service — `sc.exe create` will fail. Either use a wrapper (NSSM,
WinSW) or a Task Scheduler entry with "Run whether user is logged on or not" and a trigger of "At
startup". Set the token as a machine environment variable (`setx /M`) so it is not in the task's
arguments.

### Docker

An image is published as `ghcr.io/drolu/liveagent-gateway`. That name is a legacy internal
identifier kept deliberately; it is the ReactorPro gateway. Mount the data directory as a volume
so the identity survives container replacement, and remember to publish the port (`-p 3000:3000`)
with `--http-addr=:3000`.

## Connecting desktop apps

In each ReactorPro desktop app, open **Settings → Remote**:

| Field | Value |
|---|---|
| Gateway URL | `http://<host>` — **include the scheme** |
| Port | the `--http-addr` port, e.g. `3000` |
| Access Token | the gateway token, or a per-agent token |

Include `http://`. A bare host is normalised to `https://` by the client, which then fails against
a plain-HTTP gateway with a TLS error that looks nothing like a config mistake.

Once connected, the agent appears in the gateway's local directory — and that directory is what
gets published to the mesh, so peers can see what sits behind your edge without being told.

## No desktop agent? (gateway only)

A gateway with no ReactorPro desktop app attached is a legitimate deployment, not a
half-finished one. It serves the web UI and API, holds a mesh identity, appears in the directory,
and answers the read-only skills.

**It cannot serve `invoke`**, because there is no local agent to route work to — a peer asking for
a task gets `3002 AGENT_UNAVAILABLE`. Its published `local_agents` list will be empty, which is
exactly how a peer can tell there is nothing behind it.

Typical uses: a VPS or jump host, a central registry/directory node for a group of organisations,
a visibility node at a partner, or a site that will have its desktop app added later — adding one
requires **no change** to any peer.

## The standard site

One organisation, one site, desktop apps connecting to one gateway:

```bash
LIVEAGENT_GATEWAY_MESH_ENABLED=true
LIVEAGENT_GATEWAY_MESH_URL=nats://127.0.0.1:4222
LIVEAGENT_GATEWAY_MESH_AGENT_ID=acme/lagos/edge-1
LIVEAGENT_GATEWAY_MESH_CAPABILITIES=agent,reactorpro
```

Mesh authentication accepts exactly one of: a token, user + password, or a credentials file (in
that order of precedence — `-mesh-creds-file` for NKey/JWT wins over both). Enabling the mesh
without a URL is refused at startup, and setting a user without a password is refused too — the
bridge refuses to half-start. A *connection* failure, by contrast, is **not** fatal: the gateway
keeps serving and records the reason on `/api/mesh/status`. So "the service is running" never
proves the mesh works.

### Give every edge a unique id — do this before you need it

`LIVEAGENT_GATEWAY_MESH_AGENT_ID` is an **address, not a label**:

- it forms the subject peers send to — `mesh.agent.<id>.inbox`;
- it is **hashed into the identity fingerprint**.

On first start the gateway mints an identity file, and from then on **the id is permanent**.
Configuring a different one later is a **hard startup failure** (*"the agent id is part of the
fingerprint and cannot be reassigned"*), not a warning. Changing it means moving the identity file
aside to mint a new one — which changes your fingerprint and breaks every peer that pinned it.

Use `<org>/<site>/<edge>`. **Every edge needs a different id:** two edges sharing one discard each
other as "self", so the mesh looks empty while every service reports healthy. The gateway detects
this and logs a collision warning — and if you are still on the shared legacy default
(`drolu/reactorpro`) it warns loudly at startup, because an edge on that id cannot federate.

Left unset, the id defaults to `reactorpro/<sanitised-hostname>`. Fine for one site; set it
explicitly before federating.

## What the mesh can do

Four skills are served. Three are read-only; one does work.

| Skill | Answers | Risk |
|---|---|---|
| `ping` | "Are you there?" | read-only |
| `describe` | The full manifest, **including this edge's agent directory** | read-only |
| `status` | Identity, uptime, traffic counters. Deliberately narrow — never reveals local agents or tokens | read-only |
| `invoke` | "Ask one of your agents to do this" | **does work — gated** |

### `invoke`: letting a peer reach an agent behind your edge

A verified peer asks one of your desktop agents to run a task, by naming an agent or a capability:

```jsonc
{"target": "agent-1111", "operation": "task", "arguments": {"prompt": "..."}}
{"capability": "task",   "operation": "task", "arguments": {"prompt": "..."}}
```

Give one or the other — both is refused, and neither is defaulted, because an edge should not
guess which laptop to run work on. `timeout_ms` may only **tighten** the deadline, never extend it.

Note the two different capability lists: `-mesh-capabilities` is what **this edge** advertises so
peers can find a site that can do something; the `capability` field in an `invoke` request matches
what the **attached desktop agents** advertise, so the receiving edge can pick an agent.

### How a remote task actually executes

The desktop has no separate "run a task" interface — its model, tools and agent loop all live in
its own runtime. So the edge does not invent a second way in: it submits an ordinary **chat
command** to the desktop over the same WebSocket the browser uses, the desktop runs a real
tool-using turn, and the result returns through the existing reliable chat channel. One path, so
it cannot drift from normal chat behaviour.

If the caller's deadline passes, the edge tells the desktop to **cancel**, so an abandoned request
does not keep running and spending the local user's provider quota. That cancellation is
best-effort: if the desktop is unreachable at that moment, it cannot be delivered.

### The gates — and the one that matters most

| Setting | Default | Meaning |
|---|---|---|
| `-mesh-allow-remote-invoke` | on | Is the capability offered at all? |
| `-mesh-require-verified-invoke` | **on** | **The floor.** Refuse work from a caller whose identity was not verified |
| `-mesh-invoke-operations` | `task` | Exact allowlist. **Empty exposes none, never all** |
| `-mesh-invoke-timeout` | `60s` | How long one remote job may run |
| `-mesh-skills-enabled` | on | `false` serves nothing at all, invocation included |

**Read this before you turn the floor off.** The default verify mode is `prefer`, which
**accepts unsigned envelopes**. So invocation without the floor would be reachable by anything
able to publish to the NATS subject — anonymous remote code execution on a desktop machine. With
it on, "allowed to invoke" means "allowed for an authenticated peer". Keep it on across
organisation boundaries. Startup validation refuses the contradictory combination (invoke on +
require-verified + verify-mode=off), because there every invocation would be refused.

### Finding each other: discovery and the registry

Each edge publishes its manifest into a JetStream key-value bucket, and discovery reads it —
deterministic, unlike the older broadcast window that could silently miss a slow peer.

```bash
LIVEAGENT_GATEWAY_MESH_REGISTRY=auto                  # default
LIVEAGENT_GATEWAY_MESH_REGISTRY_BUCKET=mesh_registry
LIVEAGENT_GATEWAY_MESH_REGISTRY_TTL=1m30s
```

- **`auto` (default)** uses **both** the registry and the broadcast, merged.
- **`jetstream`** is registry-only and **fails startup** without JetStream — for a closed fleet
  where you know every peer publishes to the bucket.
- **`broadcast`** never touches JetStream.

> **If any edge in your fleet is not upgraded, use `auto`.** A registry-only setting makes you
> **blind to every peer that publishes nothing to the bucket** — older builds, or a different
> implementation. It fails silently, because the registry read *succeeds* (it returns at least
> your own entry), so the fallback never runs and the mesh looks healthy while empty. See
> `references/scenarios.md` → S5.

**Registry entries are data, not identity.** An entry read from the bucket can never make a peer
trusted; trust comes only from a verified signature.

Entries also **expire** (TTL), so a crashed edge stops being advertised. That is intended, but it
means the directory is a view of *now*, not a durable record.

`references/mesh.md` has the full model: identity, subjects, error codes, and reputation.

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

# 6. Record the fingerprint. It must not change across an upgrade.
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/mesh/status \
  | grep -o '"fingerprint":"[^"]*"'
```

Expected results:

- `/healthz` → `{"ok":true}`
- `/api/status` → `200`
- `/api/mesh/status` → `connected: true`, an `agentId`, and a `fingerprint` of the form
  `sha256:<16 hex chars>`
- `/api/mesh/agents` → a list of peers (empty is correct if you have not federated yet)

**`/api/mesh/agents` takes about two seconds, and that is correct.** With `-mesh-registry=auto`,
discovery still waits out the broadcast window because peers may answer individually as well as
through the registry. Do not point a 1-second HTTP timeout at it and conclude the mesh is broken;
allow at least 3 seconds.

If `/api/mesh/status` reports `connected: false`, read its `lastError` field — it carries the
reason. `references/troubleshooting.md` covers the common ones.

## Upgrading

The upgrade is: replace the binary, keep the data directory, restart.

```bash
systemctl stop reactorpro-gateway
install -m 0755 reactorpro-gateway-linux-amd64 /usr/local/bin/reactorpro-gateway
systemctl start reactorpro-gateway
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/mesh/status
```

Confirm the **fingerprint is unchanged** afterwards. If it changed, you pointed the new process at
a different data directory and it minted a fresh identity — fix the path and restore the backup
before anything else, because peers have already seen the new one.

After upgrading a mesh, check `/api/mesh/agents` and confirm the peer count did not drop. A count
that falls to zero right after an upgrade is a discovery regression, not an outage — see
`references/scenarios.md` → S5.

## Troubleshooting index

| Symptom | Likely cause |
|---|---|
| Exits immediately, "gateway token is required" | `LIVEAGENT_GATEWAY_TOKEN` empty or unset |
| Service runs, every client gets 401 | Quotes round the token in the env file, or a trailing newline |
| Reachable on the host, not from outside | Bound to `127.0.0.1`; or host/cloud firewall |
| `connected: false`, `lastError` mentions authorization | Wrong NATS credentials; check for quotes in the NATS config |
| `connected: false`, `lastError` mentions connect | NATS unreachable at `LIVEAGENT_GATEWAY_MESH_URL` |
| **Zero peers, but everything reports healthy** | Duplicate agent id; peers not subscribed; or an unhealthy registry bucket. Work down `references/troubleshooting.md` — this is the most common mesh fault and the most misleading |
| **Peer count dropped after an upgrade** | The v1.5.1 `auto`-mode discovery regression; upgrade, or set `-mesh-registry=broadcast` as a workaround |
| Invocation refused `4003 GOVERNANCE_DENIED` | The floor working: caller unsigned, or fingerprint not pinned |
| Peer count drops to zero after an edge restarts | Its registry entry expired (TTL); it repopulates on the next heartbeat |
| `/api/mesh/agents` times out in a client | Client timeout under ~3s; discovery waits out the broadcast window |
| TLS handshake error from the desktop app | Gateway URL lacks `http://` |
| WebSocket failures through a proxy | Proxy not configured for upgrade on `/ws/v2*` |
| A log file growing very fast | A crash-looping service, usually bad credentials. Truncate it (`: > file`) — a plain delete does not free space while the writer holds the file open |

`references/troubleshooting.md` covers each with diagnosis commands.

## Knowing it is working

The counters on `/api/status` (under `protocol_usage`) tell you more than any single check:

- `mesh_inbound_total` **rising**, with `mesh_verify_failed_total` and
  `mesh_trust_mismatch_total` at **zero** — peers are genuinely talking to you.
- `mesh_invoke_denied_total` rising while `mesh_invoke_total` stays flat — your policy is holding
  a peer off, which is exactly what you want to see when you expect it.
- `mesh_outbound_total` exists but is not currently incremented; do not read its zero as meaning
  anything.

## Reference files

Read these when you need the detail — they are not loaded until you open them.

- `references/scenarios.md` — **the scenario playbooks**: gateway-only, one site, multi-site,
  federated, mixed fleet, closed fleet, and a partner with no desktops.
- `references/configuration.md` — every flag and environment variable, with defaults and guidance
  on when a value needs changing.
- `references/mesh.md` — the NATS/Synapse mesh: identity model, authentication, served skills,
  remote invocation and its gates, discovery and the registry, subjects, error codes.
- `references/service-managers.md` — complete systemd, launchd, Windows, and Docker setups,
  including reverse-proxy configuration.
- `references/api.md` — HTTP endpoints, authentication, request/response shapes, and agent token
  issuance.
- `references/troubleshooting.md` — symptom → diagnosis → fix, with commands.

For questions about the ReactorPro desktop application itself (features, skills, MCP servers), use
the `reactorpro-doc` skill instead — this one is about the server.
