# Troubleshooting the gateway

Work in this order: process up → HTTP reachable → token accepted → mesh connected → peers
visible. Each step depends on the previous one, and checking them out of order sends you
chasing the wrong layer.

## Contents

- [Startup failures](#startup-failures)
- [Authentication failures](#authentication-failures)
- [Reachability](#reachability)
- [Mesh failures](#mesh-failures)
- [Identity problems](#identity-problems)
- [Performance and limits](#performance-and-limits)
- [Diagnostic commands](#diagnostic-commands)

## Startup failures

### Exits immediately: "gateway token is required"

The token is empty. The gateway prints usage and panics — by design, since a gateway with
no token would be open to anyone.

```bash
systemctl show reactorpro-gateway -p Environment      # what systemd thinks it passes
journalctl -u reactorpro-gateway -n 20
```

Common causes: the `EnvironmentFile` path is wrong; the variable is misspelled; systemd
was not reloaded after editing the unit; or the file is not readable by systemd. Note that
systemd reads `EnvironmentFile` as root, so `0600 root:root` is fine — but if you start
the binary by hand as a non-root user, that same file is unreadable and you get this error.

### Exits immediately: "mesh is enabled but no NATS URL is configured"

`LIVEAGENT_GATEWAY_MESH_ENABLED=true` without `LIVEAGENT_GATEWAY_MESH_URL`. This is a
deliberate refusal to half-start. Add the URL or turn the mesh off.

Two related refusals:

- `mesh user is set but the password is empty`
- `mesh is enabled but no agent id is configured`

### Starts, then dies when a client connects

Almost always the file-descriptor limit. Check:

```bash
systemctl show reactorpro-gateway -p LimitNOFILE
cat /proc/$(pgrep -f reactorpro-gateway)/limits | grep 'open files'
```

Each connected agent uses more than one descriptor. Raise `LimitNOFILE` before raising the
connection caps.

### The data directory is not writable

```
open gateway db failed  path=/var/lib/reactorpro-gateway/gateway.db
```

The service user cannot create the database. Check ownership of the directory, not just
the file. With systemd hardening, `ProtectSystem=strict` makes everything read-only except
paths listed in `ReadWritePaths` — verify that the data directory is listed, or use
`StateDirectory=` which handles it automatically.

## Authentication failures

### Every request returns 401, but the token is definitely right

Check, in this order:

**1. Quotes that are part of the value rather than file syntax.** The gateway trims
whitespace but does **not** strip quote characters itself, so what matters is whether the
quotes were already removed by whatever read the file.

Safe — the environment-file parser (systemd) or the shell (a sourced file) strips the
quotes before the gateway sees them:

```bash
LIVEAGENT_GATEWAY_TOKEN="abc123"      # gateway receives: abc123
```

Broken — the quotes are inside the value and reach the process:

```bash
docker run -e LIVEAGENT_GATEWAY_TOKEN='"abc123"'   # gateway receives: "abc123"
```

In the broken case the gateway expects every client to send the quotes too:

```bash
curl -H 'Authorization: Bearer abc123'   localhost:3000/api/status   # 401
curl -H 'Authorization: Bearer "abc123"' localhost:3000/api/status   # 200
```

Use that second command to confirm the diagnosis before editing anything. The same pattern
bites when a NATS password is lifted verbatim out of a config line written
`password: "s3cret"`.

Confirm what the process actually received:

```bash
tr '\0' '\n' < /proc/$(pgrep -f reactorpro-gateway)/environ | grep TOKEN
```

**2. A trailing newline or carriage return.** A file created on Windows and copied to Linux
can carry `\r`. The token is trimmed of whitespace, so a trailing `\n` is harmless, but
inspect the bytes if the value looks right and still fails:

```bash
wc -c < /etc/reactorpro-gateway.env
od -c /etc/reactorpro-gateway.env | tail -3
```

**3. The header form.** Only `Authorization: Bearer <token>` is accepted. A bare token,
`?token=`, or `X-API-Key` all fail.

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "Authorization: Bearer $TOKEN" localhost:3000/api/status
```

**4. A per-agent token where the gateway token is needed.** Both work on `/api/*`, but a
token issued for one agent is not a substitute if it was revoked by rotation.

### Rotating a per-agent token drops that agent

Expected. Rotation invalidates the previous credential immediately for the next
connection and disconnects the live session. `POST /api/agents/{id}/token` reports
`"disconnected": true` when it dropped one. Do it during a maintenance window.

## Reachability

### Works on the host, not from another machine

**Bound to loopback.** If `--http-addr=127.0.0.1:3000`, only the host can reach it. Use
`:3000` for LAN access, or put a reverse proxy on the same host and keep it on loopback.

```bash
ss -ltnp | grep 3000        # look at the local address column
```

The local address tells you the truth: `127.0.0.1:3000` is loopback only, `*:3000` or
`0.0.0.0:3000` is all interfaces.

**Firewall.** Then check the host firewall and any cloud security group:

```bash
# Linux
sudo iptables -L -n | grep 3000
sudo ufw status

# macOS — the application firewall blocks inbound per-app by default
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --listapps | grep -i reactorpro
```

**Container.** A container listening on `127.0.0.1` is unreachable through a published
port. Bind `:3000` inside the container.

### The desktop app reports a TLS error

The Gateway URL in **Settings → Remote** lacks a scheme. The client normalises a bare host
to `https://`, which fails against a plain-HTTP gateway. Write `http://host`, explicitly.

### WebSocket connections keep dropping through a proxy

The proxy's idle timeout is shorter than the 15s WebSocket heartbeat, or it is not
upgrading. Check for `Upgrade`/`Connection` headers in the proxy config and raise
`proxy_read_timeout`. Symptoms are a UI that reconnects constantly and terminal sessions
that die after a predictable interval.

## Mesh failures

A mesh failure **never stops the gateway**. The HTTP API stays up and the reason is
recorded in `lastError` on `/api/mesh/status`. Always read that field first — the service
being "running" tells you nothing about the mesh.

Related: `GET /api/mesh/agents` returning **503** does not mean the endpoint is wrong or
that the mesh is unconfigured. Those routes always exist and return 503 whenever there is
no live connection, including when the mesh is disabled entirely. `/api/mesh/status`
distinguishes the two cases via its `enabled` field.

```bash
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/mesh/status \
  | python3 -m json.tool
```

| `lastError` contains | Meaning | Fix |
|---|---|---|
| `authorization violation` | NATS rejected the credentials | Wrong user/password/token, or the password still has quotes from the NATS config |
| `connect` / `connection refused` | NATS unreachable | Check `mesh.url`, that NATS is listening, and the firewall between hosts |
| `no such host` / `i/o timeout` | DNS or network | Resolve the NATS hostname from the gateway's host |
| `tls` | TLS mismatch | `nats://` against a TLS-only server, or an untrusted certificate |

### `enabled: true, connected: false`

Configuration is being read and the connection is failing. The config layer is fine;
this is credentials or reachability. Read `lastError`.

### `enabled: false`

The bridge was never turned on. `LIVEAGENT_GATEWAY_MESH_ENABLED` is unset, misspelled, or
set to a value the parser does not recognise.

**Booleans fail silently.** Only `1/true/yes/on` and `0/false/no/off` (case-insensitive)
are recognised. A typo such as `ture`, or a value like `TRUE ` with unusual whitespace, falls
back to the default `false` with no warning. If the mesh "will not turn on", print the
variable and check it character by character.

### `connected: true` but no peers

- **Another agent may just not be there.** `GET /api/mesh/agents` takes ~2s by design and
  returns what answered in that window; an empty list with `connected: true` can be correct.
- **Different subject prefix.** Subjects are hardcoded to `mesh.*` here. A NATS account
  with restrictive subject permissions must allow `mesh.>` — including the `/` in
  `mesh.agent.<id>.inbox`, which some permission patterns treat as a delimiter.
- **Different mesh entirely.** Two NATS servers, or two accounts on one server, are
  separate meshes. Agents only see peers on the same account.

### A peer returns 3001 SKILL_NOT_FOUND

Expected today. The gateway registers no skill handlers, so its manifest advertises
`"skills": []` and it cannot answer inbound requests. Discovery, registration, heartbeat
and events all still work. See `mesh.md`.

### Detection is slow or a client times out

`GET /api/mesh/agents` waits a **fixed ~2 second window** for replies, because peers answer
individually as well as the registry. A client with a 1s timeout will report a failure on a
healthy mesh. Allow at least 3s.

## Identity problems

### The fingerprint changed after an upgrade or migration

The process started with an empty or different data directory and minted a new identity.
It will look completely healthy.

```bash
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/mesh/status | grep fingerprint
ls -l /var/lib/reactorpro-gateway/mesh/reactorpro-identity.json
```

Fix the data directory path and restore the identity file from backup — the original
keypair is the only thing that reproduces the old fingerprint, since it is derived from the
key and cannot be recomputed from the agent id alone.

In practice this is currently quiet rather than harmful: the agent id is unchanged, peers
never receive the fingerprint, and no signature verification runs, so nothing on the mesh
rejects or even notices the new key. Treat it as a warning sign anyway — it means the
process is reading a different data directory than you think, which will also have reset
the agent database and any per-agent tokens.

### "the agent id is part of the fingerprint and cannot be reassigned"

You changed `LIVEAGENT_GATEWAY_MESH_AGENT_ID` on a gateway whose identity file already
exists. This is intentional and load-bearing: the identity binds the id to the key, which
is what makes the id unchangeable.

To genuinely change the agent id you must mint a new identity — remove the identity file
(back it up first) and restart. That creates a **new agent** to the mesh; it is not a
rename.

### `mesh identity fingerprint does not match: the agent id or key was modified`

The identity file was edited, corrupted, or truncated. Restore from backup. If there is no
backup, delete the file and restart to mint a fresh identity — accepting that the agent's
identity changes.

## Performance and limits

### Connections refused with 503

Either a connection cap or the file-descriptor limit. Check both — the configured cap can
be satisfied while the OS limit is exhausted, and the error looks the same.

```bash
systemctl show reactorpro-gateway -p LimitNOFILE
cat /proc/$(pgrep -f reactorpro-gateway)/limits | grep 'open files'
ss -tn state established '( sport = :3000 )' | wc -l
```

### Memory growth

`-max-message-bytes` defaults to 64 MiB and the relay keeps 30 seconds of chat events per
connection for reconnection replay. Both scale with concurrent connections. If memory is a
concern, lower `-max-message-bytes` and `-relay-buffer-seconds`; the cost is a lower
ceiling on large file transfers and a shorter reconnect replay window.

### Large uploads fail only through the proxy

The proxy's body size limit is below 64 MiB. Raise `client_max_body_size` (nginx) or the
equivalent. Local uploads succeeding while proxied ones fail is the signature.

## Diagnostic commands

```bash
# What is the process actually configured with? (authoritative, beats reading config files)
tr '\0' '\n' < /proc/$(pgrep -f reactorpro-gateway)/environ | sort

# What is it listening on?
ss -ltnp | grep reactorpro

# Recent logs
journalctl -u reactorpro-gateway -n 100 --no-pager     # Linux
tail -100 ~/Library/Logs/reactorpro-gateway.err.log    # macOS

# Full health sweep
TOKEN=...
curl -s localhost:3000/healthz
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $TOKEN" localhost:3000/api/status
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/mesh/status | python3 -m json.tool
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/mesh/agents

# Is NATS itself healthy?
nats-server --signal ldm     # n/a; use the client instead
curl -s localhost:8222/varz  # if NATS monitoring is enabled
```

The single most useful habit when something looks wrong: read `/api/mesh/status` rather
than the service status. The gateway is designed so that the API is healthy while the mesh
is broken, and `lastError` is the only place that distinction is visible.
