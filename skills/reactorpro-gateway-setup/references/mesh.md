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

## What it can do

**Works:** registering with a registry, discovering peers, being dispatched to, emitting and
subscribing to events, the reputation and governance subsystems, the HTTP API for all of it,
and answering a small read-only skill surface.

It serves three built-in skills, so a peer that discovers this gateway gets a real answer
rather than `3001`:

| Skill | Returns |
|---|---|
| `ping` | `{pong: true, ts}` |
| `describe` | the agent's manifest — what it is and what it serves |
| `status` | `agent_id`, `fingerprint`, `connected`, `skills`, `uptime_seconds`, and mesh traffic counters |

Confirm what a running gateway advertises:

```bash
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/mesh/status | grep skills
# "skills": ["describe","ping","status"]
```

All three are read-only: the gateway cannot be asked to run a command, touch the filesystem,
or reveal the desktop agents connected to it. Turn them off with `-mesh-skills-enabled=false`,
or restrict them with `-mesh-skills=ping`.

**What it still cannot do:** anything stateful. If you need a peer to *do* something rather
than describe itself, that has to be added as an explicit skill — which is a deliberate
safety property, not an oversight.

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

### What the identity enforces

The immutable-id guarantee is **local**: editing the id in the file invalidates the
fingerprint and the file refuses to load, and pointing the config at a different id fails
with *"cannot be reassigned"*.

Since the trust hardening, that is no longer the whole story — signatures are now checked
on inbound traffic, subject to the verification mode:

| Mode | Behaviour |
|---|---|
| `off` | Signature fields are not consulted at all. |
| `prefer` **(default)** | A signed envelope must verify or it is refused `3004`; an unsigned envelope is still accepted, so peers that cannot sign keep working. |
| `require` | Unsigned envelopes are refused `3004`. Correct for a closed fleet. |

Two things make a signature meaningful rather than decorative, and both are on by default:

- **The fingerprint is bound to the sender.** The envelope carries a fingerprint covering
  the agent id and the public key, and it is covered by the signature. Without this, a
  signature only proves the sender holds *some* key — anyone can mint a pair and sign a
  message claiming to be someone else.
- **Fingerprints are pinned across messages.** The first identity an agent id presents is
  remembered; a different one later is refused. That is what detects impersonation or a key
  swap. Configure pins explicitly with `-mesh-trusted-peers`, and turn off first-use
  learning with `-mesh-trust-on-first-use=false` to accept only those pins.

The manifest now advertises the fingerprint, so a peer can pin this gateway before it ever
receives a message from it.

Losing the identity file still mints a new keypair under the *same* agent id — the name
peers see is unchanged, but the fingerprint changes. With `prefer` a peer that already
pinned the old fingerprint will now refuse this gateway as an identity mismatch, which is
exactly the intended behaviour: back the file up.

Copying the file to a new host *does* carry the keypair, which is the supported way to
migrate a gateway to new hardware without changing its identity.

### Other inbound gates

Beyond signatures, every inbound message is subject to a size cap (1 MiB by default), a
protocol-version check, an addressee check, a clock-skew window (5 minutes) that bounds how
long a captured message stays replayable, replay detection on envelope ids, and a
per-sender rate limit that fails closed once its tracked population is full. See the
ReactorPro repository's `internal/mesh/MESH.md` for the authoritative description.

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

Aligned with the Synapse protocol table, so a spec-conformant peer reads them correctly.

| Code | Name | Retryable | Meaning |
|---|---|---|---|
| `2001` | INVALID_ENVELOPE | no | Could not be decoded or failed an inbound check (version, addressee, timestamp, replay, size) |
| `2002` | INVALID_MANIFEST | no | Manifest missing required fields |
| `3001` | SKILL_NOT_FOUND | no | No handler for the requested skill |
| `3002` | AGENT_UNAVAILABLE | yes | Agent offline or unreachable |
| `3004` | IDENTITY_MISMATCH | no | Signature or pinned identity does not match |
| `4001` | OVERLOADED | yes | Agent too busy |
| `4002` | RATE_LIMITED | yes | Too many requests from this sender |
| `4003` | GOVERNANCE_DENIED | no | Blocked by policy |
| `4004` | APPROVAL_REQUIRED | yes | Awaiting approver sign-off |
| `5001` | INTERNAL_ERROR | yes | Handler failure |

The `retryable` flag on a reply is derived from the code, so the two can never disagree.

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
