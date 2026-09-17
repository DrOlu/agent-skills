---
name: reactorpro-gateway-setup
description: Install, configure, and operate the ReactorPro gateway binary as a headless service on any server — Linux (systemd), macOS (launchd), Windows, or Docker — federate it into a NATS/Synapse agent mesh, and deploy reactorpro-agentd, the headless concurrent agent worker that attaches to a gateway as a second executor. Use this skill whenever the user wants to deploy ReactorPro's gateway, stand up a ReactorPro server or VPS, run reactorpro-gateway as a background service, enable the mesh bridge, let agents in one organisation reach agents in another, connect ReactorPro desktop apps to a shared gateway, run a gateway with no desktop app attached, run a server-side headless agent (reactorpro-agentd) with a given provider, API key and model, expose a skills library to a headless worker, or troubleshoot a gateway that will not start, returns 401, reports the mesh as disconnected, or sees zero peers. Also use it for upgrading the gateway or agentd, backing up identities, and choosing mesh settings for intra- or inter-organisation deployments.
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

Pin a version by replacing `latest/download` with `download/v1.5.8`.

You can also confirm what you are running without downloading anything — GitHub exposes a
server-computed digest per asset:

```bash
gh api repos/DrOlu/ReactorPro/releases/tags/v1.5.8 --jq '.assets[]|{name,digest}'
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

**It cannot serve `invoke`** with nothing attached, because there is no local agent to route
work to — a peer asking for a task gets `3002 AGENT_UNAVAILABLE`. Its published `local_agents`
list will be empty, which is exactly how a peer can tell there is nothing behind it.

Unless you attach **reactorpro-agentd** — the headless worker. It signs into the gateway exactly
the way a desktop app does, appears in the same directory, and turns the server into an
execution node with no desktop app anywhere in sight. See the next section.

Typical uses: a VPS or jump host, a central registry/directory node for a group of organisations,
a visibility node at a partner, or a site that will have its desktop app added later — adding one
requires **no change** to any peer.

## The headless worker — reactorpro-agentd

A single static binary that signs into a gateway over the same `/ws/v2/agent` WebSocket the
desktop uses and serves remote chat turns with real tool use, **several at once**. To the
gateway it is just another attached agent — a row in the local directory, addressed by `target`
or `capability`, behind the same gates, tasks, streaming and webhooks. **No gateway or mesh
configuration changes to adopt it.** The companion detail — every flag, service files,
verification — is in `references/agentd.md`.

### When you want it

- A server/VPS should execute work, not merely relay it — and no human will sit at a desktop.
- Parallel turns: the desktop runs one turn at a time behind its user; the agentd runs
  `-concurrency` at once (default 4) with a polite queue.
- The mesh's task lifecycle (async tasks, streaming, webhooks, retry, input-required) should
  have an unattended worker to feed.

### Install

```bash
BASE=https://github.com/DrOlu/ReactorPro/releases/latest/download
curl -fsSLO "$BASE/reactorpro-agentd-linux-amd64"      # per platform; see below
curl -fsSLO "$BASE/SHA256SUMS"
sha256sum -c --ignore-missing SHA256SUMS               # macOS: shasum -a 256 -c
install -m 0755 reactorpro-agentd-linux-amd64 /usr/local/bin/reactorpro-agentd
```

Assets: `reactorpro-agentd-{linux-amd64,linux-arm64,darwin-amd64,darwin-arm64,windows-amd64.exe}`.
Pure-Go, genuinely static — no runtime dependencies. `scripts/install-agentd.sh` does the
download-verify-install for the current platform.

### Issue its credential

The agentd authenticates like a desktop: the gateway token, or better, its **own per-agent
token** (revocable independently). The agent id must be the canonical form **`agent-<uuidv4
lowercase>`** — anything else is refused:

```bash
AGENT_ID="agent-$(uuidgen | tr 'A-Z' 'a-z')"
curl -s -X POST -H "Authorization: Bearer $GATEWAY_TOKEN" \
     http://127.0.0.1:3000/api/agents/$AGENT_ID/token      # -> {"token":"agt_…"}
curl -s -X PATCH -H "Authorization: Bearer $GATEWAY_TOKEN" -H 'Content-Type: application/json' \
     -d '{"name":"ReactorPro Agentd (server 1)"}' http://127.0.0.1:3000/api/agents/$AGENT_ID
```

The friendly name is what peers see in the published directory — set it.

### Configure and run

```bash
LIVEAGENT_AGENTD_PROVIDER_KEY=sk-… \
reactorpro-agentd \
  -gateway ws://127.0.0.1:3000/ws/v2/agent \
  -agent-id "$AGENT_ID" -token "$AGENT_TOKEN" \
  -name "ReactorPro Agentd (server 1)" \
  -provider-url https://api.openai.com/v1 \
  -provider-model gpt-5 \
  -workdir /srv/agentd-work \
  -skills-dir /opt/agent-skills \
  -concurrency 4
```

The essential settings:

| Setting | Flag | Env twin | Notes |
|---|---|---|---|
| Gateway link | `-gateway` | `LIVEAGENT_AGENTD_GATEWAY` | `ws://` or `wss://` agent endpoint |
| Identity | `-agent-id` | `LIVEAGENT_AGENTD_ID` | `agent-<uuidv4>` — its directory address |
| Credential | `-token` | `LIVEAGENT_AGENTD_TOKEN` | gateway or per-agent (`agt_…`) token |
| Provider | `-provider-url` / `-provider-key` / `-provider-model` | `LIVEAGENT_AGENTD_PROVIDER_*` | any OpenAI-compatible `/v1` endpoint; the **worker holds this key**, not the gateway |
| Sandbox | `-workdir` | `LIVEAGENT_AGENTD_WORKDIR` | every file tool + shell cwd confined here (symlink-safe) |
| Skills | `-skills-dir` | `LIVEAGENT_AGENTD_SKILLS_DIR` | library of SKILL.md collections, exposed read-only |
| Parallelism | `-concurrency` | `LIVEAGENT_AGENTD_CONCURRENCY` | default 4; extra commands queue |
| Reach | `-shell` / `-fetch` | `LIVEAGENT_AGENTD_SHELL` / `_FETCH` | toggle the two wide-blast tools |

Run it under systemd/launchd like the gateway (a full unit file is in `references/agentd.md`).
Reconnects with bounded backoff; a dropped link cancels local runs and the gateway fails them at
their budget.

### What it serves — and what it does not

Served: `invoke` tasks (mesh dispatch and async tasks alike), streaming chunks, webhooks, retry,
`input-required` — the full task contract; a curated tool set (`read_file`, `write_file`,
`list_dir`, `run_command`, `fetch_url`) plus read-only skill tools (`read_skill`,
`read_skill_file`) when `-skills-dir` is set.

Not served: desktop-surface requests it does not implement are answered instantly with a typed
501 refusal (it is an executor, not a desktop), and `history_list` returns an honest empty list —
the agentd keeps no conversation history. Chatting with it through the web UI works on the live
conversation view; persisted history does not exist.

### Verify

```bash
# 1. It signed in (agentd log): "agentd signed into the gateway"
# 2. The gateway sees it — the agents list on /api/status includes the id
curl -s -H "Authorization: Bearer $GATEWAY_TOKEN" http://127.0.0.1:3000/api/status
# 3. Peers can discover it (within one heartbeat of the gateway): describe shows
#    local_agents carrying the worker by name
# 4. A real turn end to end:
curl -s -X POST -H "Authorization: Bearer $GATEWAY_TOKEN" -H 'Content-Type: application/json' \
     -d '{"target":"<your-edge-id>","skill":"invoke","timeoutMs":180000,
          "input":{"target":"'"$AGENT_ID"'","operation":"task",
                   "arguments":{"prompt":"Say OK and nothing else."}}}' \
     http://127.0.0.1:3000/api/mesh/dispatch
```

---

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

Eight skills are served (v1.5.19+): read-only (`ping`, `describe`, `status`), the caller-scoped task set (`task.get`, `task.cancel`, `task.retry`, `task.input`), and the gated `invoke`. `describe` returns the full manifest **including this edge's agent directory** — desktops and headless workers, refreshed every heartbeat since v1.5.24.

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
| `-mesh-invoke-timeout` | `3m` | How long one synchronous remote job may run (a caller may only narrow it; hours-long work is the async task API) |
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
- `references/agentd.md` — the headless worker: every flag and env twin, per-agent token
  issuance, service files, the skills library, verification, upgrade and limits.
- `references/troubleshooting.md` — symptom → diagnosis → fix, with commands.

For questions about the ReactorPro desktop application itself (features, skills, MCP servers), use
the `reactorpro-doc` skill instead — this one is about the server.

## Recent changes you must know about (v1.5.4 → v1.5.35)

**The durable mailbox (v1.5.4, opt-in).** `-mesh-mailbox` buffers skill
invocations for an absent agent in JetStream (`mesh.agent.*.mailbox`, stream
`MESH_AGENT_MAILBOX`) and delivers them when it returns. At-least-once: skills
reached this way must be idempotent. Send with `POST /api/mesh/mailbox` (202).

**Never stream the inbox subject, and never reuse a name you do not own (v1.5.5).**
A JetStream stream over `mesh.agent.*.inbox` breaks request/reply outright: the
server answers the publish, so callers receive a PubAck instead of the
response, and a push consumer's `msg.reply` is the ack subject, so the peer
cannot reply at all. Durability belongs on `.mailbox`. If a stream with the
configured name already exists, the edge adopts it only when it genuinely
captures this agent's mailbox subject, otherwise it refuses with an actionable
message — it never rewrites a stream it did not create. A mailbox failure is
non-fatal and shows as `mailbox.running=false` + `error` on `/api/mesh/status`.

**Dispatch is honest now (v1.5.6–v1.5.8).** It ignores ack-shaped messages,
refuses to treat a non-envelope as a successful reply, and names the likely
cause on timeout. Requests also carry a top-level `text` (from
`input.text/message/prompt`) and a signed `payload.reply_to` with a `_REPLY`
prefix, which is what the Synapse cli/agentspan bridges require. Cross-fleet
dispatch with a text prompt is a real agent turn — allow 120s+.
See `references/mesh.md` § "The durable mailbox and the inbox hazard".

**The async task lifecycle (v1.5.12–v1.5.19).** The mesh send ceiling rose to 30 minutes
(`timeoutMs` up to 1800000), and `invoke` gained `"async": true` — a task object with states
(`queued → working → (input-required) → completed | failed | canceled | rejected`), a
caller-minted id as the idempotency key, state events on `mesh.event.task.<id>`, opt-in chunk
streaming, signed webhook push on completion, one-call retry, and an interactive
pause-and-ask protocol (`allowInput` + `[[INPUT_REQUIRED: …]]`) that resumes in the same
conversation. Tasks are served by any attached agent — desktop or headless worker.

**The headless worker, reactorpro-agentd (v1.5.20–v1.5.22).** A second executor ships in the
box: a static binary that attaches as an agent and runs turns in parallel. First release, then
the skills library (`-skills-dir`, read-only `read_skill`/`read_skill_file` tools), then the
browser-surface fix — desktop-surface requests it does not implement are answered instantly
with a typed 501 instead of hanging the web UI, and `history_list` returns an honest empty list.

**Discovery publishes the directory now (v1.5.23–v1.5.24).** Two stacked bugs had silently
kept every edge's published `local_agents` empty since v1.5.5: registration ran once at boot
(never refreshed), and the async registry probe was discarded whenever it won the start-up
race. Both fixed — the heartbeat now rebuilds the manifest from the live directory and
re-registers, so peers see your attached agents (desktop and headless alike) within one
heartbeat, and the registry KV entry can no longer outlive its TTL. If an upgraded peer still
reports an empty directory, its edge simply needs one heartbeat (~30s).

**The bug-sweep release (v1.5.25).** Three concurrency/platform/discovery fixes: the agentd
enforces one run per conversation atomically (a cancel while queued settles the run as
cancelled without a provider call); `run_command` works on Windows (`cmd /c` there, `sh -c`
elsewhere); and a cleanly stopped edge can no longer be resurrected in the discovery registry
by a straggling heartbeat tick — the entry's removal is final.

**The synchronous-invoke deadline is 3 minutes (v1.5.26).** The edge's own patience for one
remote invoke was 60s, which killed real agent turns that were still working (`4001` + a
cancel of a healthy run). A caller can still narrow it per invoke with `timeout_ms`; hours-long
work belongs to the async task API.

**Concurrent inbox and the real invoke deadline (v1.5.32–v1.5.33).** The sweep that
followed the UI work found two more, both live-verified: the inbox subscription ran its
handler on nats.go's single delivery goroutine, so one minutes-long invoke queued every
other mesh message to the edge (pings, cancels, other peers' invokes) behind it — it is
now a bounded worker pool (16 workers, 256-deep queue), pinned by a regression test that
fails with the pool forced to 1. And the synchronous-invoke deadline was still 60 seconds
despite v1.5.26: the gateway-level `-mesh-invoke-timeout` flag carried its own 60s literal
default that silently overrode the raised mesh-package constant — the flag default is now
`mesh.DefaultInvokeTimeout` (3 minutes), so the two cannot disagree. Operators tune it
with the flag or `LIVEAGENT_GATEWAY_MESH_INVOKE_TIMEOUT`.

**Transcript rendering and retention (v1.5.30–v1.5.31).** Two follow-ups found by
browser-reproducing the transcript view: the worker's user entries now carry the
`attachments: []` array the webui's snapshot validation requires (without it every
projection the worker committed was silently discarded — prompts rendered, answers
never did), and a finished headless conversation retains its final projection on the
gateway's stream until the stream is reaped, so the history view lives the stream's
full ~30-minute idle life instead of the event log's 10-minute clock. Verified in the
real browser: the worker's answers now render in the chat view, including replies to
messages typed in the management UI.

**The headless sidebar fix (v1.5.29).** The webui scopes an agent's sidebar to "none" — an
empty list that never asks the gateway — when the settings' execution mode is not "text" and
no workspace project is active, and a headless worker landed there every time (its
`settings_get` used to fail against the worker's typed 501). The gateway now serves
`settings_get` for headless workers with the plain-text execution mode (and `history_workdirs`
as an honest empty list), so the sidebar lists the worker's conversations like the desktop's.
Before this, they were reachable only via Search Conversations.

**Headless workers have history and memory (v1.5.27–v1.5.28).** The agentd declares the
`agentd` capability in its hello, and the gateway keys two conveniences on it: the management
UI's history arms for a headless worker are answered **by the gateway** from its conversation
store (recent activity — ~30-min retention, cleared by a gateway restart), and a synchronous
`invoke` that passes `conversation_id` **continues that conversation** — the desktop continues
its own thread, while a headless worker is rehydrated with its prior turns (newest 16 / 24 KiB).
Replies carry `conversation_id` so the caller can hold the session. The served transcript
merges all of a conversation's runs, titled from the original prompt.

**Streamed provider rounds and bounded proxy silence (v1.5.35).** During a slow-provider
window (2026-09-17) both LLM clients treated a slow upstream as a dead one: the agentd sent
non-streaming completions under a 120s total client timeout (a stalled round died with
"context deadline exceeded … awaiting headers" and lost the turn), and the desktop's proxy
client had no timeout at all (the same stall hung until the connection dropped and surfaced
as `502 Failed to forward the proxy request upstream`). The agentd now streams
(`stream: true`, SSE deltas assembled — including fragmented tool calls), and
`-request-timeout` is an **idle timeout**: the longest the provider may stay silent between
bytes, before or after headers, with a 15-minute per-round hard cap; a stalled round fails
fast with `provider stream stalled: no data from the provider for …`. Slow-but-alive
providers that keep sending bytes or SSE keepalives are never cut, and a provider answering
a streamed request with plain JSON is still served. The desktop's proxy and system-proxy
clients gained `connect_timeout(15s)` + `read_timeout(300s)` (idle-between-bytes) with no
total timeout by design — streamed answers are only ever cut by upstream silence.
