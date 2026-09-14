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
- [Operational hazards](#operational-hazards) — runaway logs, duplicate services, and the fast
  diagnosis path for "it worked yesterday"

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

**This is the most misleading fault in the system** — every check looks healthy while the mesh is
empty. Work down in this order; the first two explain most cases.

1. **Is your agent id unique?** Two edges sharing an id discard each other as "self", so neither
   appears and nothing reports an error. Check the gateway log for a collision warning, which
   names both endpoints and fingerprints:
   ```bash
   journalctl -u reactorpro-gateway | grep -i collision
   ```
   Remember the id is **permanent** once the identity file exists — see `configuration.md`.

2. **Are the peers subscribed at all?** Ask the NATS server directly, rather than trusting the
   mesh's own view:
   ```bash
   curl -s localhost:8222/subsz?subs=1 | grep -o 'mesh\.agent\.[^"]*\.inbox' | sort -u
   ```
   If your peers' inboxes are absent, they are not connected to *this* broker — which is a
   peer-side or topology problem, not a gateway one. (Monitoring needs `http_port` set in the
   NATS config.)

3. **Is the registry bucket healthy?** With `-mesh-registry=auto` or `jetstream`:
   ```bash
   nats kv ls <bucket>          # default bucket: mesh_registry
   nats kv info <bucket> 2>/dev/null || true
   ```
   An empty bucket while peers claim to be registering points at the NATS server's own log — see
   the next entry.

4. **Different subject prefix or account.** Subjects are hardcoded to `mesh.*`. A NATS account
   with restrictive permissions must allow `mesh.>` — including the `/` in `mesh.agent.<id>.inbox`,
   which some permission patterns treat as a delimiter. Two servers, or two accounts on one
   server, are separate meshes: agents only see peers on the same account.

5. **Nothing is actually there.** An empty list with `connected: true` can simply be correct.
   `GET /api/mesh/agents` returns what answered in its window.

### Peers disappeared and the registry bucket is empty

Real case: the NATS server's JetStream **filestore for the registry stream was corrupted**, so
every write failed while the registry itself looked up and healthy. The directory drained to empty
as entries expired via TTL, and the peers vanished even though they were running and re-registering
continuously.

Confirm it in the NATS server's log:

```
[ERR] Filestore [KV_MESH_REGISTRY] Critical write error: lmb missing
[ERR] JetStream failed to store a msg on stream 'LOCAL > KV_MESH_REGISTRY': lmb missing
```

`lmb missing` is a filestore-level failure — not a quota or disk-space problem (check `df -h` and
`nats account info` first to rule those out, but a healthy sibling stream updating normally while
this one fails points squarely at corruption).

**Fix:** delete the broken stream and let the registry recreate it.

```bash
# via the JetStream API (the CLI verb is blocked by some shell guards)
nats stream info KV_MESH_REGISTRY          # confirm it exists and holds 0 messages
# then delete it through the JetStream API and restart the registry service:
systemctl restart <registry-service>
```

Nothing is lost: the bucket is a live directory with a short TTL, and peers re-register within a
minute. Confirm recovery with `nats kv ls` and re-check the peer count.

### Peer count dropped after upgrading a gateway

Almost certainly the **v1.5.1 `auto`-mode discovery regression**. `auto` was registry-only, which
made an upgraded edge blind to every peer publishing nothing to the bucket — and it failed
silently, because the registry read *succeeds* (it returns at least your own entry), so the
"read failed → fall back to broadcast" path never ran.

```bash
# confirm the mode in use
journalctl -u reactorpro-gateway | grep -i 'discovery registry'
```

**Fix:** upgrade to v1.5.2 or later. **Immediate workaround without upgrading:**
`LIVEAGENT_GATEWAY_MESH_REGISTRY=broadcast`, then restart. See `scenarios.md` → S5.

### Invocation is refused with 4003 GOVERNANCE_DENIED

That is the safety floor working, not a bug. The caller either sent an unsigned envelope, or
presented a fingerprint that is not pinned on your side.

```bash
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/mesh/trust   # what you pin
```

Check both ends: `-mesh-verify-mode=require`, `-mesh-trust-on-first-use=false`, and each side's
fingerprint present in the other's `-mesh-trusted-peers`. Confirm you are comparing the
`fingerprint` from `/api/mesh/status`, not the agent id.

### A peer returns 3001 SKILL_NOT_FOUND

The target does not serve that operation. A ReactorPro gateway answers `ping`, `describe`,
`status` and `invoke` by default, so anything else — and any `invoke` whose `operation` is not in
the target's `-mesh-invoke-operations` — is expected to fail this way.

Check what the target advertises before dispatching:

```bash
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/mesh/status | grep skills
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/mesh/agents
```

If `"skills": []` on your *own* gateway, the surface has been turned off
(`-mesh-skills-enabled=false`) or restricted to an empty selection. See `mesh.md`.

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

This is no longer quiet. With verification enabled (`prefer` or `require`), the fingerprint
is part of every signed envelope and is advertised in the manifest, so a peer that has
already pinned the old identity refuses this gateway with `3004 IDENTITY_MISMATCH`. Expect
that refusal, restore the identity file from backup, and restart.

Either way, treat it as a warning sign: a changed fingerprint means the process is reading a
different data directory than you think, which will also have reset the agent database and
any per-agent tokens.

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

## Operational hazards

These are not gateway bugs, but they take a working mesh down and they are easy to miss because
the symptom appears somewhere unrelated.

### A log file growing very fast, then unrelated things breaking

A crash-looping service under `KeepAlive`/`Restart=always` can write **gigabytes** in hours. The
damage is indirect: the disk fills, and then JetStream writes fail — which presents as a *mesh*
fault rather than a storage one.

Real case: a service connecting to NATS with **no credentials**, refused with
`Authorization Violation`, restarting forever. It produced ~2.5 GB of repeated tracebacks, and
two failed authentication attempts every ~2 seconds flooded the NATS server's own log.

Two lessons:

- **Look for the real error a few lines *above* the traceback**, not at the bottom of the file.
  The cause is almost always several screens up from the text that fills the disk.
- **Read the rate, not the size.** A big file may be old; what matters is whether it is still
  growing.

```bash
# how fast is it actually growing?
S1=$(stat -f%z FILE); sleep 5; S2=$(stat -f%z FILE); echo "$((S2-S1)) bytes in 5s"

# free the space immediately
: > FILE
```

**Truncate rather than delete.** For a file a running process still holds open, deleting it does
*not* free space — the process keeps writing to the unlinked inode until it restarts. Truncation
reclaims it at once.

Then fix the loop: give the service working credentials, and confirm it stays up rather than
merely starting.

### Two service definitions for the same thing

Duplicate jobs (a leftover unit from an earlier install alongside the current one) fight over the
same port. One wins; the other crash-loops forever with:

```
[FTL] Can't start monitoring: can't listen to the monitor port: bind: address already in use
```

It never succeeds, and it fills a log while doing so.

```bash
# macOS: list loaded jobs and look for two that configure the same thing
launchctl list | grep -i <name>
ls ~/Library/LaunchAgents/ | grep -i <name>

# Linux
systemctl list-units --all | grep -i <name>
```

Disable the stale one — unload it *and* rename or remove its unit file, or it returns at the next
login or boot.

### A fast path for diagnosing any "it worked yesterday" mesh problem

```bash
# 1. Is the edge up and does it know who it is?
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/mesh/status

# 2. Are peers visible? (allow 3s)
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/mesh/agents

# 3. Is anything arriving at all? A flat inbound count means nothing is reaching you.
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/status | grep -o 'mesh_inbound_total":[0-9]*'
```

If the fingerprint is unchanged, the token works, `connected: true`, and `mesh_inbound_total` is
flat, the problem is **outside this gateway** — nobody is talking to it. Check the peers are
connected to the broker before changing any gateway setting.

## New failure modes (v1.5.4 → v1.5.8)

| Symptom | Cause | Fix |
|---|---|---|
| Dispatch: "no reply … (N JetStream publish ack(s) received instead)" | A JetStream stream captures `mesh.agent.<id>.inbox`, so the server answers the publish | Remove the inbox subjects from that stream; durability belongs on `mesh.agent.<id>.mailbox` |
| Mailbox: "already exists but does not capture …" | The configured stream name is taken by an unrelated stream | Pick a free name with `-mesh-mailbox-stream`; the edge will not rewrite someone else's stream |
| `/api/mesh/status` shows `mailbox.enabled=true, running=false` with an `error` | The mailbox failed at startup; the mesh kept running | Read the `error` field — it names the stream and the flag to change |
| Dispatch to a fleet peer returns 4001 "No text/message/prompt" | The peer is text-based; the request carried no top-level text | Put the prompt in `input.text` (the gateway surfaces it) |
| Dispatch to a peer hangs though the peer logged the task completing | The peer answers `payload.reply_to`, not the NATS reply subject | Requires v1.5.8+, which carries `reply_to` in the signed payload |
