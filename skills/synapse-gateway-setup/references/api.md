# Gateway HTTP API

Everything the gateway exposes over HTTP, with the auth rules and request shapes.

## Contents

- [Authentication](#authentication)
- [Endpoints](#endpoints)
- [Health and status](#health-and-status)
- [Agent directory and tokens](#agent-directory-and-tokens)
- [Mesh](#mesh)
- [WebSocket endpoints](#websocket-endpoints)
- [Web UI and public routes](#web-ui-and-public-routes)
- [Error handling](#error-handling)

## Authentication

One mechanism only:

```
Authorization: Bearer <token>
```

The header must be exactly `Bearer <token>` — the scheme comparison is case-insensitive,
but the token itself is compared in full. A naked token, `?token=`, a custom header, or a
cookie are all rejected with **401**. There is no session, no cookie, no API-key alias.

Two credential kinds are accepted, and they are interchangeable at the transport layer:

- **The gateway token** — one per deployment, from `LIVEAGENT_GATEWAY_TOKEN`. Grants full
  access to every endpoint.
- **Per-agent tokens** — issued per desktop agent. Intended so one machine can be revoked
  without rotating the whole deployment.

Everything under `/api/` is gated. `/healthz` is not, and neither is the web UI — the UI
asks for the token itself and then calls the API with it.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/healthz` | Liveness. **No auth.** `{"ok":true}`. |
| `GET` | `/api/status` | Gateway status: connected agents and protocol usage. |
| `GET` | `/api/agents` | Agent directory. |
| `POST` | `/api/agents/{id}/token` | Issue (or rotate) a per-agent token. |
| `PATCH` | `/api/agents/{id}` | Rename an agent. |
| `DELETE` | `/api/agents/{id}` | Remove an agent. |
| `POST` | `/api/files/import` | Import readable files. |
| `POST` | `/api/files/import-directory` | Import a directory. |
| `GET` | `/api/mesh/status` | Mesh bridge status. |
| `GET` | `/api/mesh/health` | Mesh health summary. |
| `POST` | `/api/mesh/register` | Re-register this agent with the registry. |
| `GET` | `/api/mesh/agents` | Discover peers. **Takes ~2s.** |
| `POST` | `/api/mesh/dispatch` | Send a skill request to a peer. |
| `POST` | `/api/mesh/emit` | Publish an event. |
| `POST` | `/api/mesh/subscribe` | Subscribe to an event subject. |
| `GET` | `/api/mesh/events` | Recently received events. |
| `GET` | `/api/mesh/reputation` | Peer reputation scores, best first. |
| `GET` | `/api/mesh/approvals` | Pending governance approvals. |
| `POST` | `/api/mesh/approvals` | Request an approval. |
| `POST` | `/api/mesh/approvals/{id}/decision` | Approve or deny. |

**The `/api/mesh/*` routes always exist, whether or not the mesh is enabled.** They do not
404 when it is off. Instead:

| Endpoint | Mesh disabled | Mesh enabled but not connected |
|---|---|---|
| `/api/mesh/status` | `200`, `enabled: false` | `200`, `connected: false`, `lastError` set |
| `/api/mesh/health` | `200` | `200` |
| `/api/mesh/reputation` | `200` | `200` |
| `/api/mesh/agents`, `/dispatch`, `/emit` | `503` | `503` |

So `/api/mesh/status` is the reliable way to tell "not configured" from "configured but
broken", and **`503` on the operational endpoints means "no live mesh connection"** rather
than "bad request".

## Health and status

### `GET /healthz`

```json
{"ok": true}
```

Unauthenticated and cheap. This is the right liveness probe. It proves the process is
serving HTTP and nothing more — not that the token works, not that the mesh is connected.

### `GET /api/status`

```json
{
  "agents": [ ... ],
  "protocol_usage": { "v2": 1 }
}
```

Per-agent connection state, useful for answering "which desktop apps are connected".

### `GET /api/mesh/status`

The single most useful diagnostic on the gateway:

```json
{
  "enabled": true,
  "connected": true,
  "agentId": "acme/lagos/edge-1",
  "fingerprint": "sha256:196e19cc7c370cf9",
  "url": "nats://127.0.0.1:4222",
  "serving": true,
  "skills": [],
  "manifest": { "id": "...", "name": "...", "capabilities": [ ... ],
                "skills": [], "endpoint": "mesh.agent.<id>.inbox",
                "availability": "online", "last_heartbeat": "..." },
  "subscriptions": [],
  "reputation": [],
  "pendingApprovals": [],
  "lastError": ""
}
```

Reading it:

| Field | Meaning |
|---|---|
| `enabled` | The bridge was configured on. False means nothing was attempted. |
| `connected` | A live NATS connection exists right now. |
| `serving` | Subscribed and able to receive requests. |
| `fingerprint` | The stable identity. **Compare this after upgrades and migrations.** |
| `skills` | Skills this gateway can answer. Empty until handlers are registered. |
| `lastError` | Why the last connect or operation failed. Read this when `connected` is false — it is the only place the reason appears, because a mesh failure is not fatal and never stops the process. |

## Agent directory and tokens

### `GET /api/agents`

```json
[
  {
    "agent_id": "...",
    "online": true,
    "has_token": true,
    "registered_at": "...",
    "token_created_at": "...",
    "name": "...",
    "agent_version": "...",
    "connected_since": 0
  }
]
```

`online` reflects a live connection; `has_token` reflects whether a per-agent credential
has been issued. An agent can be listed with `has_token: false` if it authenticates with
the shared gateway token.

### `POST /api/agents/{id}/token`

Issue or rotate a credential for one agent.

```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:3000/api/agents/my-laptop/token
```

```json
{
  "agent_id": "my-laptop",
  "token": "<plaintext, shown once>",
  "disconnected": true
}
```

**The token is returned in plaintext exactly once.** The gateway stores only what it needs
to verify future connections, so a lost token cannot be recovered — issue a new one.

Rotation takes effect immediately: the previous credential stops working for the next
connection, and `disconnected: true` means any live session for that agent was dropped as
part of the rotation. Issue tokens during a maintenance window, not mid-session.

### `PATCH /api/agents/{id}`

```json
{"name": "Build server"}
```

### `DELETE /api/agents/{id}`

Removes the agent and its stored credential.

## Mesh

### `POST /api/mesh/dispatch`

Send a skill request to another agent and wait for its reply.

```json
{
  "target": "grip-001",
  "skill": "ping",
  "input": {"host": "example.com"},
  "timeoutMs": 30000
}
```

`timeoutMs` is optional; omitted or non-positive, the bridge's dispatch timeout (120s)
applies. Note the default is measured in **minutes**, so an explicit `timeoutMs` is worth
setting for anything interactive — an HTTP client in front of this will usually give up
first.

**A ReactorPro peer answers `ping`, `describe`, `status` and `invoke`; anything else returns
`3001 SKILL_NOT_FOUND`.** The first three are read-only; `invoke` asks the target to run a task
on one of its desktop agents and is gated by its own policy — see `mesh.md`.

`invoke` takes its arguments inside `input`:

```json
{
  "target": "acme/lagos/edge-1",
  "skill": "invoke",
  "timeoutMs": 90000,
  "input": {
    "target": "agent-1111",
    "operation": "task",
    "arguments": {"prompt": "Summarise today's orders."}
  }
}
```

`input.target` may be replaced by `input.capability` ("any online agent that advertises this"),
but not both. A refusal arrives with a meaningful code — `3002` no such agent or offline, `4003`
refused by policy — so you can tell "route elsewhere" from "retry".

Check `skills` on the target's `/api/mesh/status` (or its `describe` output) to see what it will
accept before dispatching. See `mesh.md`.

### `POST /api/mesh/emit`

```json
{"type": "deploy.finished", "data": {"env": "prod"}}
```

Publishes to `mesh.event.<type>`.

### `POST /api/mesh/subscribe`

```json
{"subject": "deploy.>"}
```

A bare name is prefixed with `mesh.event.`. An empty subject subscribes to the whole event
wildcard.

### `GET /api/mesh/events`

Recently received events, newest first, each with `subject`, `event` and `at`. Bounded —
this is a recent-history view, not a durable log.

### `GET /api/mesh/reputation`

Peer scores, ordered best first. Two entries only exist for agents that have been
dispatched to. Scores are implementation-specific and not comparable with other Synapse
implementations.

### Governance approvals

Request one:

```json
{"target": "grip-001", "skill": "deploy", "input": {"env": "prod"}}
```

Decide one:

```json
{"approver": "operator", "decision": "approve", "reason": "reviewed"}
```

`decision` must be a recognised verb (`approve` or `deny`); anything else is rejected.
Approvals expire on a timeout if nobody decides. **An approval can be decided once** — a
second decision returns an error rather than overwriting the first, so a retried request
after a network failure surfaces as a conflict, which is the behaviour you want.

## WebSocket endpoints

| Path | Purpose |
|---|---|
| `/ws/v2` | Browser/UI connection. |
| `/ws/v2/agent` | Desktop agent control connection. |
| `/ws/v2/terminal` | Terminal data plane. |

These are protobuf over WebSocket and authenticate with the same bearer token. A proxy in
front must allow the upgrade — see `service-managers.md`. Connection counts per type are
capped and over-limit connections get `503`; the caps are configurable (see
`configuration.md`).

## Web UI and public routes

| Path | Notes |
|---|---|
| `/` | The embedded web UI (SPA). Served from the binary; no separate hosting. |
| `/assets/*` | Static assets, served with a long immutable cache. |
| `/t/` | Public tunnel proxy. |
| `/image-proxy` | Image fetch proxy. |
| `/api/public/history-shares/{token}` | Public, tokenised history share. |

The web UI and `/healthz` are unauthenticated by design — the UI collects the token
itself. If the gateway is internet-facing, that means the login surface is public. Keep it
behind TLS, and prefer a reverse proxy with rate limiting rather than exposing the port
directly.

## Error handling

- **401** — missing, malformed, or wrong token. Check for un-stripped quotes in the
  environment file first; that is the most common cause of a token that "looks correct".
- **403** — governance denied, or an approval that was denied or expired.
- **503 on `/api/mesh/agents`, `/dispatch` or `/emit`** — no live mesh connection. These
  routes exist even with the mesh disabled, so a 503 means "not connected", not "not
  configured" and not "bad URL". Check `enabled` on `/api/mesh/status` to tell the two
  apart; a genuinely wrong path returns 404 like any other unrouted request.
- **409** — an approval was already decided.
- **503** — mesh not connected (`ErrNotConnected`), or a connection limit was hit. For the
  latter, check the file-descriptor limit as well as the configured cap.
- **500** — a skill handler returned an error (`5001` in the envelope when the failure is
  reported over the mesh rather than HTTP).

Errors carry a JSON body. When debugging anything mesh-related, prefer
`GET /api/mesh/status`'s `lastError` over the HTTP status — a mesh failure is deliberately
non-fatal, so the process stays healthy and the HTTP layer may report nothing at all.

## Durable mailbox (v1.5.4+)

```bash
# Leave work for an agent that may not be running (returns as soon as it is STORED)
curl -X POST http://127.0.0.1:3000/api/mesh/mailbox   -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json'   -d '{"target":"acme/lagos/edge-1","skill":"ping","input":{"text":"run when you are back"},"taskId":"t-1"}'
# -> HTTP 202 {"accepted":true,"sequence":1,...}  — it is NOT answered; 202 says so

# Is the mailbox running? (present even when off, so "off" ≠ "on but broken")
curl -s http://127.0.0.1:3000/api/mesh/status -H "Authorization: Bearer $TOKEN" | jq .mailbox
# {"enabled":true,"running":true,"stream":"MESH_AGENT_MAILBOX","consumer":"mailbox-…"}
```

`/api/mesh/dispatch` waits for a result; `/api/mesh/mailbox` does not and
cannot — a mailbox message has no reply path by construction.
