# The NATS / Synapse mesh bridge

ReactorPro's gateway can join a NATS event mesh as a full-duplex **Synapse agent**:
it registers itself, discovers peers, serves skill requests, dispatches requests to other
agents, and publishes and subscribes to events.

The bridge is **disabled by default**. With it disabled, nothing connects anywhere — this
is deliberate, so the shipping configuration has no network side effects.

## Contents

- [What works today, and what does not](#what-works-today-and-what-does-not)
- [Enabling the bridge](#enabling-the-bridge)
- [Agent identity](#agent-identity)
- [Authentication](#authentication)
- [Wire protocol](#wire-protocol)
- [Discovery behaviour](#discovery-behaviour)
- [Reputation and governance](#reputation-and-governance)
- [Interoperating with RTerm](#interoperating-with-rterm)
- [Running a NATS server](#running-a-nats-server)

## What works today, and what does not

Being explicit about this saves hours:

**Works:** registering with a registry, discovering peers, participating in the mesh as a
discoverable agent with a stable cryptographic identity, emitting and subscribing to
events, the reputation and governance subsystems, and the HTTP API for all of it.

**Does not work yet:** the gateway **serves no skills**. Verify this yourself against a
running instance —

```bash
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/mesh/status | grep skills
# "skills": []
```

The `RegisterSkill` API exists and is tested, but nothing in production calls it, so the
manifest advertises an empty skill list. Consequence: **another agent that dispatches a
skill request to this gateway gets error `3001` (`SKILL_NOT_FOUND`)** — not a crash, not a
timeout. If you are setting up a gateway expecting it to answer inbound calls, that is the
limitation to know about first. Making it answer requires adding a skill handler in the
gateway's startup path.

Discovery, registration and events all work regardless.

## Enabling the bridge

The minimum is three settings:

```bash
LIVEAGENT_GATEWAY_MESH_ENABLED=true
LIVEAGENT_GATEWAY_MESH_URL=nats://127.0.0.1:4222
LIVEAGENT_GATEWAY_MESH_AGENT_ID=drolu/reactorpro
```

Or as flags on the command line:

```bash
reactorpro-gateway \
  --http-addr=127.0.0.1:3000 \
  --mesh-enabled \
  --mesh-url=nats://127.0.0.1:4222 \
  --mesh-agent-id=drolu/reactorpro
```

A tick to watch: **`--mesh-enabled` without `--mesh-url` is refused**, and so is a user
without a password. The bridge declines to half-start rather than running in a state that
looks configured but connects nowhere.

A *connection* failure is different — it is logged and non-fatal. The gateway keeps
serving HTTP and records the reason on `/api/mesh/status`. This is a deliberate design
choice (a mesh outage should not take the gateway down), and it means the only reliable
health check is the API, never the service status.

## Agent identity

This is the part of ReactorPro's mesh that differs most from other Synapse
implementations, and the part most likely to bite you operationally.

The identity is an **Ed25519 keypair whose fingerprint covers both the agent id and the
public key**:

```
fingerprint = "sha256:" + hex(sha256(agentID + "\n" + publicKey))[:16]
```

Because the id is part of the hash, the id cannot be quietly changed:

- Editing the id inside the identity file invalidates the fingerprint and the file refuses
  to load (`ErrIdentityTampered`).
- Pointing the configuration at a different id than the file contains fails with
  *"the agent id is part of the fingerprint and cannot be reassigned"*.
- Every envelope is signed (`sig` + `pub`) and verified against the embedded key, so a
  peer cannot impersonate the agent by copying its manifest.

Operationally:

| | |
|---|---|
| Location | `<data dir>/mesh/reactorpro-identity.json` |
| Permissions | `0600` (it contains the private key) |
| Created | On first start, automatically |
| Back it up | **Yes — before your first upgrade** |

### What the identity does and does not enforce

The immutable-id guarantee is **local**. Editing the id in the file invalidates the
fingerprint and the file refuses to load; pointing the config at a different id fails with
*"cannot be reassigned"*. That is real and enforced at load time.

Two limits are worth knowing before you rely on it for trust:

1. **Nothing verifies the signatures.** `Sign` is called on every outbound envelope, but
   `VerifyEnvelope` is reachable only from tests — the inbound path decodes a request,
   checks its type, and dispatches it without any signature check. Until that is wired up,
   `sig`/`pub` are metadata, not a control.
2. **Peers never see the fingerprint.** It is not a field on the manifest, so it is not
   discoverable and cannot be pinned by another agent. It appears only on the local
   `/api/mesh/status`.

Consequence: losing the identity file mints a new keypair under the *same* agent id. The
agent peers see keeps its name; only the local fingerprint changes; and because no peer
receives or verifies it, nothing else notices. The gateway looks healthy throughout.

Back the file up regardless. It is the only copy of the private key, and if signature
verification is ever enforced, an identity mismatch flips from invisible to fatal.

Copying the file to a new host *does* carry the keypair, which is the supported way to
migrate a gateway to new hardware.

`LIVEAGENT_GATEWAY_MESH_AGENT_ID` is only a default for the first run. After that the file
wins.

## Authentication

The gateway supports two of NATS' three auth modes, with strict precedence:

1. `-mesh-token` / `LIVEAGENT_GATEWAY_MESH_TOKEN`
2. `-mesh-user` + `-mesh-password`

**Exactly one is used.** Setting a token *and* a user sends only the token, silently.
(This mirrors the NATS client convention that also puts a creds file first, but the gateway
exposes no creds-file flag, so from here it is token or user/password.)

Passwords frequently come out of a NATS config file, where they are often written quoted:

```conf
authorization {
  user: admin
  password: "s3cret"
}
```

The gateway does **not** strip surrounding quotes — that is done by whatever loads the
value. If your launcher extracts the password with `awk`/`sed`, strip the quotes there, or
the bridge will fail with an authorization violation while the password "looks right" in
the config. This is the single most common mesh setup failure.

## Wire protocol

Envelope version **`0.3.0`**, JSON over NATS.

### Subjects

| Subject | Direction | Purpose |
|---|---|---|
| `mesh.registry.register` | publish | Announce this agent's manifest. Fire-and-forget; reply optional. |
| `mesh.registry.discover` | request/reply | Ask for agents matching a filter. |
| `mesh.registry.deregister` | publish | Withdraw on clean shutdown. |
| `mesh.agent.<agentId>.inbox` | subscribe | Inbound skill requests for this agent. |
| `mesh.heartbeat.<agentId>` | publish | Liveness, every 30 s. |
| `mesh.event.<type>` | pub/sub | Events. `mesh.event.>` subscribes to all. |

Note the agent id appears **verbatim** in the subject, including its `/`. The default
`drolu/reactorpro` yields `mesh.agent.drolu/reactorpro.inbox`. A NATS account with
restrictive subject permissions must allow `/` in that position, or registration will
appear to succeed while requests never arrive.

### Message types

`register`, `discover`, `request`, `respond`, `emit`.

### Error codes

| Code | Name | Meaning |
|---|---|---|
| `2002` | Invalid request | Malformed envelope or payload. |
| `3001` | Skill not found | No handler for the requested skill — **what you get today**. |
| `4010` | Unauthorized | |
| `4030` | Governance denied | An approval was denied. |
| `5001` | Handler failed | The skill handler returned an error. |
| `5003` | Not configured | The capability is not configured. |

Codes `2002` and `3001` are not retryable; `5001` is.

### Manifest

What a gateway advertises about itself. The live values for a default deployment:

```json
{
  "id": "drolu/reactorpro",
  "name": "ReactorPro Gateway",
  "description": "ReactorPro desktop agent and gateway",
  "capabilities": ["agent", "reactorpro"],
  "skills": [],
  "endpoint": "mesh.agent.drolu/reactorpro.inbox",
  "availability": "online",
  "last_heartbeat": "2026-09-12T19:30:57.644471Z"
}
```

`name` comes from `LIVEAGENT_GATEWAY_MESH_NAME`. `capabilities` and `description` are not
configurable through the gateway's flags.

## Discovery behaviour

Discovery is **a fixed collection window, not a per-reply timeout**. The caller publishes
to `mesh.registry.discover` and then collects replies for the whole window (default **2
seconds**), because agents answer individually as well as the registry — stopping at the
first reply would silently miss peers.

Two practical consequences:

- **`GET /api/mesh/agents` takes about two seconds.** That is correct behaviour. A client
  with a 1-second timeout will report a failure on a perfectly healthy mesh; allow at
  least 3 seconds.
- The window is **not configurable** through the gateway. It is a bridge default
  (`DiscoveryWindow`), unlike the dispatch timeout, which is also fixed at 120s.

A peer is only returned if it has both an `id` and a `name` — the SDK requires both in a
manifest, so an agent missing either is filtered out rather than shown as a broken entry.

## Reputation and governance

Two optional extensions ride along with the bridge:

- **Reputation** scores peers by success and failure, with time-based decay toward an
  initial score, clamped between a minimum and maximum. Visible at
  `GET /api/mesh/reputation`, ordered best-first.
- **Governance** gates designated skills behind human approval. When a skill requires
  approval, the request blocks until an operator approves or denies it, and every decision
  is recorded in history. Pending items are listed at `GET /api/mesh/approvals` and decided
  with `POST /api/mesh/approvals/{id}/decision`.

A decision can be made once. A second decision on the same approval is rejected rather
than silently overwriting the first — so a retry after a network error surfaces as a
conflict, not a duplicate approval.

## Interoperating with RTerm

ReactorPro's bridge was written to mirror the one in
[RTerm](https://github.com/DrOlu/RTerm). The protocol layer matches, but **several deltas
are documented and not yet reconciled** — see `crates/agent-gateway/internal/mesh/MESH.md`
in the ReactorPro repository for the authoritative list. The ones that affect interop:

1. **Subject prefix is hardcoded here** (`mesh`) but configurable in RTerm
   (`settings.synapse.prefix`). Two meshes configured with a different prefix will not see
   each other.
2. **No `in_reply_to` field.** RTerm sets it on `respond`; this envelope has none.
3. **Heartbeat and deregistration are additions.** RTerm has neither. Harmless against a
   registry that ignores them, but extra surface upstream does not have.
4. **Reputation formula differs.** RTerm weights success rate, speed, freshness and a
   lying penalty, keyed by `agent_id::skill`; this implementation uses a simpler per-agent
   success/failure model with half-life decay. Scores are therefore **not comparable across
   implementations** — do not treat a ReactorPro score as meaningful to an RTerm peer.
5. **Governance transport differs** in how approvals are negotiated.

ReactorPro↔ReactorPro works. ReactorPro↔RTerm should be validated in a test mesh before
being relied on.

## Running a NATS server

The bridge needs a NATS server; it does not embed one. Minimal local server with one user:

```conf
# /etc/nats/nats.conf
listen: 127.0.0.1:4222

authorization {
  user: reactorpro
  password: "change-me"
}
```

```bash
nats-server -c /etc/nats/nats.conf
```

Then point the gateway at it:

```bash
LIVEAGENT_GATEWAY_MESH_URL=nats://127.0.0.1:4222
LIVEAGENT_GATEWAY_MESH_USER=reactorpro
LIVEAGENT_GATEWAY_MESH_PASSWORD=change-me
```

If the gateway and NATS are on different hosts, enable TLS in NATS and use a `tls://` URL.
Mesh traffic carries signed envelopes but the payloads are not encrypted by the bridge —
NATS transport security or a private network is what protects them in transit.

Verify the bridge end to end:

```bash
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/mesh/status
# enabled: true, connected: true, serving: true, agentId, fingerprint, url
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/mesh/agents
```

`enabled: true` with `connected: false` means configuration is right and reachability or
credentials are wrong — read `lastError`.
