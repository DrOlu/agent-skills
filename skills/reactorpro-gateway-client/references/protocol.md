# The ReactorPro mesh wire protocol

Everything here is extracted from the gateway source of record
(`crates/agent-gateway/internal/mesh/` — `envelope.go`, `identity.go`,
`verify.go`, `synapse.go`, `reply.go`, `mailbox.go`, `invoke.go`) and is what
that code enforces, not an aspiration. Where the fleet's older Synapse
bridges differ, the difference is stated explicitly.

## The three-part contract

The mesh is three things and nothing more:

1. **NATS subjects** (table below) — the postal system.
2. **Signed JSON envelopes** — sealed letters with a wax seal.
3. **Named skills** — the only vocabulary. A peer advertises skill ids; a
   sender names one; the reply is text or JSON.

The mesh never inspects what is behind an inbox. A ReactorPro desktop agent,
a Python bridge over a CLI, an n8n workflow, a Go service — all are peers of
equal standing if they can (a) reach the same NATS server, (b) speak
envelopes, (c) hold an identity when a verified one is required.

## Subjects

| Subject | Purpose | Rules |
|---|---|---|
| `mesh.agent.<id>.inbox` | request/reply | **Never put a JetStream stream over it** (see §inbox-streaming) |
| `mesh.agent.<id>.mailbox` | durable one-way mail | JetStream stream `MESH_AGENT_MAILBOX`, pattern `mesh.agent.*.mailbox`; at-least-once |
| `mesh.registry.register` | announce a manifest | payload `{"manifest": {...}}`; a registry service files it into the `mesh_registry` KV bucket |
| `mesh.registry.discover` | broadcast discovery | peers reply to `msg.reply` with their manifest |
| `mesh.registry.deregister` | graceful exit | |
| `mesh.heartbeat.<id>` | liveness + id-collision detection | exactly one key should ever speak here; ReactorPro edges want a *signed* heartbeat envelope |
| `mesh.event.<type>` | pub/sub events | subscribe `mesh.event.>` for all |

## The envelope

```json
{
  "v": "0.3.0",                 // advisory — "1.0" (Synapse bridges) interops fine
  "id": "3f1c…",                // unique per envelope: the replay cache keys on it
  "type": "request",            // register|discover|request|respond|emit|heartbeat
  "ts": "2026-09-15T09:00:00.123456789Z",  // RFC3339(Nano), UTC, ±5 min of receiver
  "from": "acme/lagos/edge-1",  // sender's agent id — MUST match the key's fingerprint
  "to": "grip-001",             // "" = broadcast, "REGISTRY" = registry ops, else target id
  "task_id": "task-17",         // caller's correlation id, echoed in the reply
  "trace": {"trace_id": "…", "span_id": "…"},
  "payload": {"skill": "invoke", "input": {}, "text": "…", "reply_to": "_REPLY.x.1"},
  "error": null,                // respond envelopes only: {"code","message","retryable"}
  "in_reply_to": "…",           // id of the envelope this one answers
  "sig": "<hex ed25519>",       // signature (ReactorPro convention)
  "pub": "-----BEGIN PUBLIC KEY-----…",  // sender's Ed25519 public key (PEM)
  "fp": "sha256:<16 hex>"       // binds agent id ↔ key
}
```

Unknown extra fields are ignored on receipt — the fleet's bridges carry
`signature`/`from_identity`/`from_key_fingerprint` from an older convention
and ReactorPro edges simply don't read them.

### Request payload

```json
{"skill": "invoke", "input": {"text": "…"}, "text": "…", "reply_to": "_REPLY.x.1"}
```

- `skill` — the id the peer advertises. ReactorPro edges serve `ping`,
  `describe`, `status`, and the gated `invoke`.
- `input` — the skill's argument, shape owned by the skill.
- `text` — top-level prompt. **Set it whenever the prompt matters**: the
  fleet's text-based bridges read `payload.text`/`message`/`prompt` and
  never look inside `input`. The gateway mirrors `input.text|message|prompt`
  here automatically when dispatching through REST, but a native citizen
  must set it itself.
- `reply_to` — your reply inbox, **must start with `_REPLY.`** (see
  §request-reply). It rides inside the *signed* payload, because a JetStream
  delivery's `msg.reply` is the ack subject, not the caller.

### Reply payload

ReactorPro edges reply `payload: {"output": <handler result>}` — `ping`
returns `{"pong": true, "ts": "…"}`; `invoke` returns
`{"agent": "…", "operation": "task", "result": <the turn's text>}`.
Synapse bridges reply `payload: {"text": "…"}`. Coerce defensively: try
`payload.text`, then `payload.output.text`, then `payload.output.result`,
then dump. A refusal arrives as a top-level `error` object, not a payload.

## Identity, fingerprint, signature

An identity is an Ed25519 keypair bound to an agent id:

```
fingerprint = "sha256:" + hex(sha256(agent_id + "\n" + raw_pubkey))[:16]
```

The id is inside the digest — that is what makes an id unchangeable and a
stolen key insufficient (same key under another id = different fingerprint).
Identity files are JSON `{"identity", "privateKeyPem" (PKCS8), "publicKeyPem"
(PKIX), "fingerprint"}`, written 0600. `mesh_identity.py` mints them.

**What the signature covers** — a length-prefixed field-joined digest, so
any language can reproduce it byte for byte. For fields
`[v, id, type, ts, from, to, task_id, in_reply_to, fp, trace_id, span_id,
err_code, err_message, err_retryable]` (the last five contribute empty
positions when the trace/error is absent — absent ≠ empty):

```
for each part:  decimal_utf8_byte_length ":" part "\n"
then append:    sha256(payload_bytes).digest()        # 32 raw bytes; sha256(b"") when no payload
```

Sign that with Ed25519, hex-encode into `sig`. The public key PEM travels in
`pub` and the fingerprint in `fp`; **neither is itself covered by the
signature, but `fp` is** — so the identity binding cannot be swapped in
transit. Two Python rules that must never be broken:

1. The payload bytes you hash must be byte-identical to the payload value in
   the JSON you publish (hash `json.dumps(payload, separators=(",", ":"))`
   and publish the envelope with the same serialisation options).
2. Lengths are UTF-8 byte lengths, not character counts.

**What a signature proves** — that the sender holds the private key for the
public key in the same envelope. Anyone can mint a keypair and claim any
`from`. Identity becomes meaningful through two load-bearing mechanisms: the
`fp`↔key↔id binding above, and the receiver's **trust store**: it pins the
first fingerprint it sees for an agent id (trust-on-first-use) and refuses a
different one afterwards (code `3004`). Pre-pinning instead of TOFU:
`-mesh-trusted-peers=sha256:<hex16>[,…]` with `-mesh-trust-on-first-use=false`.

### The two signing conventions on this mesh

| | ReactorPro (`sig`/`pub`/`fp`) | Legacy Synapse fleet (`signature`/`from_identity`/`from_key_fingerprint`) |
|---|---|---|
| Signed bytes | length-prefixed digest + payload sha256 | canonical JSON (sorted keys, compact) |
| Verified by | every ReactorPro gateway; `mesh.py` here | only the old bridges, via `~/.synapse` trust store |
| ReactorPro edge view | a verified, TOFU-pinnable identity | *unsigned* — accepted only under `prefer`, **cannot invoke** |

A citizen that wants ReactorPro edges to know who it is signs the ReactorPro
way. The old fields can additionally be carried for bridge-to-bridge
compatibility; ReactorPro ignores them.

## What an inbound envelope must survive (the guard, cheapest first)

1. **Size** — ≤ 1 MiB (`MaxEnvelopeBytes`).
2. **Rate** — 50 msg/s sustained, burst 100, per sender.
3. **Version** — advisory; any value accepted unless the edge pinned
   `-mesh-accepted-versions` (closed fleets only).
4. **Addressee** — `to` ∈ {"", "REGISTRY", this edge's id}.
5. **Freshness** — `ts` within ±5 min (`ClockSkew`). Set clocks from NTP.
6. **Replay** — `id` must not repeat within the window (32768-entry cache,
   ~10 min TTL). A JetStream *redelivery* of the same id is legitimate and
   exempt — deduplication is what at-least-once delivery gives up.
7. **Signature & trust** — per the verify mode: `off` ignores identity;
   `prefer` (default) verifies the signed, accepts the unsigned; `require`
   refuses the unsigned. Then TOFU/pins decide *whose* key counts.

## Request/reply mechanics

- Build your reply inbox from a NATS inbox with the prefix swapped to
  `_REPLY.` — the fleet's bridges only answer subjects with that prefix.
- **Subscribe before publishing** (and flush), or a fast reply is lost and
  read as a timeout.
- Set the inbox as the NATS reply subject AND as `payload.reply_to`.
- **Ignore ack-shaped messages while waiting**: `{"stream": "…", "seq": …}`
  with no `type`/`id` is a JetStream PubAck. See §inbox-streaming.
- A reply must have `id`, `type` and `from` or it is not a mesh envelope —
  fail loudly rather than treating garbage as an empty success.
- Correlate by `in_reply_to`/`task_id`/`trace`, which are signed — the NATS
  reply subject is transport and cannot be verified.
- Budget minutes: a dispatch to a real agent turn takes 10–60s+ (a status
  peer answers in ~1s, which is how mis-set timeouts stay hidden).

### §inbox-streaming — never stream the inbox subject

A JetStream stream capturing `mesh.agent.*.inbox` breaks request/reply two
ways (both measured, nats-server 2.14.2): the server answers the publish
with a PubAck delivered to the caller's reply inbox (so the caller sees the
ack instead of the reply), and a push consumer's `msg.reply` is the JetStream
ack subject (`$JS.ACK.…`), so the consuming peer cannot answer at all. A
stream named `AGENT_INBOXES` doing exactly this exists on the production
fleet — which is why every client here skips ack-shaped messages and every
bridge reads `payload.reply_to`. **A new citizen simply subscribes the inbox
with core NATS** and gets correct behaviour everywhere. Durable delivery is
what the separate `.mailbox` subject is for.

## Skills

| Skill | Served by a ReactorPro edge | Returns |
|---|---|---|
| `ping` | always (allowlistable) | `{"pong": true, "ts": "…"}` |
| `describe` | always | the edge's manifest (id, name, skills, local agent directory) |
| `status` | always | `agent_id`, `fingerprint`, `connected`, `skills`, `uptime_seconds`, mesh counters |
| `task.get` | with a task store | the creating caller's task (optionally `{tail}` for the chunk view) |
| `task.cancel` | with a task store | stops the creating caller's task (idempotent) |
| `task.retry` | with a task store | re-runs the creating caller's failed/canceled task under its own id |
| `task.input` | with a task store | answers the creating caller's input-required task; the run resumes in place |
| `invoke` | gated — see below | `{"agent": "…", "operation": "task", "result": …}`; with `async: true` a task handle instead |

**`invoke` is the cross-organisation capability** — run a task on a desktop
agent behind a ReactorPro edge. Its input:

```json
{"target": "agent-1111", "operation": "task", "arguments": {"prompt": "…"}, "timeout_ms": 60000}
```

`target` (an attached agent's id or configured name) and `capability` are
mutually exclusive and never defaulted — an edge that must guess which laptop
to run refuses instead. Gates, all fail closed: `-mesh-allow-remote-invoke`
(on), **`-mesh-require-verified-invoke` (on — an unsigned or untrusted caller
gets `3004`; this is the floor that keeps "enabled" from meaning "anonymous
RCE")**, `-mesh-invoke-operations` (`task` only), `-mesh-skills-enabled`.
Giving up on a timeout cancels the task on the desktop.

A custom citizen bridge serves whatever it wants — the protocol carries only
the name.

### The input-request convention (v1.5.19+)

An async invoke may opt into a two-way exchange with `"allow_input": true`. The
executing edge then teaches the agent the convention in the prompt, and an
agent that cannot finish without asking ends its reply with one exact line:

```
[[INPUT_REQUIRED: your question]]
```

The edge turns that line into a **state, not an answer**: the task pauses as
`input-required`, the question rides `pending_input` on the task (read it back
with `task.get`; the caller's webhook, if set, is also pushed for
input-required), and the state event tells a watching caller to wake up. The
creating caller answers through the `task.input` skill
(`{"task_id": "…", "input": "the answer"}` — a string is the answer itself, any
other JSON is delivered to the agent as labelled JSON) and **the run resumes in
the same desktop conversation**: the agent reads its own question and the
answer together, so no context is lost. A task may ask more than once; each
entry into `input-required` re-arms both webhooks.

Rules worth knowing: without the opt-in the marker is ordinary output and the
task completes as before (an agent that has not been taught the convention must
not have its questions reinterpreted); the marker only counts as its own line,
case-sensitive, with a non-empty question; and an input-required task survives
an edge restart — it is waiting, not running, and the resume conversation is
durable. The events stay state-only — the question travels point-to-point via
`task.get`, gated to the creating caller.

## Discovery

To be *seen* by ReactorPro edges (do all three; they are cheap):

1. **Register**: publish a signed `register` envelope to
   `mesh.registry.register`, `to: "REGISTRY"`, payload
   `{"manifest": {…}}`. A registry service (this fleet runs one) files it
   into a JetStream KV bucket, which `auto`/`jetstream` registry modes
   read. Refresh on every heartbeat cadence (bucket TTL is short — this
   fleet's is ~2× heartbeat).
2. **Answer broadcasts**: subscribe `mesh.registry.discover` and reply to
   `msg.reply` with a signed respond envelope carrying your manifest
   (skipping your own queries and non-matching filters). This is the path
   that needs no registry service at all — every ReactorPro edge answers
   these, so broadcast alone finds all *edges*.
3. **Heartbeat**: publish a signed `heartbeat` envelope to
   `mesh.heartbeat.<id>` every ~20–30s. A *signed* envelope lets ReactorPro
   edges detect an id collision (another key speaking on your subject); a
   bare timestamp (what the old bridges send) is tolerated but detectable
   only as liveness.

Fleet-compat notes, learned live:

- **Two bucket names exist.** The gateway's default registry bucket is
  lowercase `mesh_registry`; the fleet's registry-service runs on uppercase
  `MESH_REGISTRY`. A discovering client should read both (mesh.py does);
  an operator should point the gateway's `-mesh-registry-bucket` at
  whichever one the local registry service actually writes.
- **A discover request's payload must be present, even if `{}`.** The fleet's
  registry-service treats a missing payload as "direct lookup by envelope
  id" and answers with zero agents. The gateway always sends `{}`.

The manifest (`describe` and register share it):

```json
{"id": "acme/lagos/hq-1", "name": "HQ Bridge", "description": "…",
 "capabilities": ["billing", "west-africa"],
 "skills": [{"id": "invoke", "name": "Invoke", "description": "…"}],
 "endpoint": "mesh.agent.acme/lagos/hq-1.inbox", "availability": "online",
 "last_heartbeat": "…", "fingerprint": "sha256:<16hex>"}
```

Include `fingerprint` — it lets a discovering peer pin you *before* first
contact. Discovery results are **data, not identity**: a manifest can claim
anything, and nothing in it may seed a trust store.

**The directory is live and carries every executor (v1.5.24+).** An edge's manifest
refreshes from its attached agents on every heartbeat (~30s), so `local_agents` reflects who
is actually connected — desktops **and** headless workers (`reactorpro-agentd`) alike, each
with its id, friendly name, online state and capabilities. A peer reading the registry or
asking `describe` can choose a worker deliberately; a worker that has gone away disappears
within a heartbeat. Before v1.5.24 the directory was frozen at the edge's boot — if a peer
reports an empty `local_agents`, its edge needs an upgrade.

## The durable mailbox

One-way, at-least-once, for work addressed to a peer that may be away:

- Subject `mesh.agent.<id>.mailbox`, JetStream stream `MESH_AGENT_MAILBOX`
  (the namespaced default — **never `AGENT_INBOXES`**, which is a real fleet
  stream over the *inbox* subjects; adopting someone else's stream by name
  collision once took a whole mesh bridge down).
- Send as a **`TypeEmit`** envelope (a `request` here is refused: there is
  no reply path, and accepting would strand the sender). Payload
  `{"skill": "…", "input": …}`.
- Receiving is at-least-once: ack only after the handler succeeds; retry
  transient failures with `nak(delay≈5s)` (a bare nak redelivers immediately
  and spins during an outage); discard permanent failures. **Skills reached
  by mailbox must be idempotent.** A ReactorPro edge refuses `invoke` here
  outright (a remote task is once-per-call, not idempotent), so the mailbox
  on an edge reaches only `ping`/`describe`/`status`.
- Redelivery repeats the envelope id by definition — exempt it from replay
  dedup (everything else in the guard still applies).
- A ReactorPro edge publishes mailbox mail through JetStream for a stored
  receipt (`POST /api/mesh/mailbox` → 202 + sequence). A citizen can plain-
  publish to the subject; the *receiving* stream captures it either way.
- Bounds: 7-day max age, 10 000 messages, oldest dropped under pressure —
  a handoff buffer, not an archive.

## Error codes (wire contract — branch on them, never reuse)

| Code | Meaning | Retryable |
|---|---|---|
| `2001` | INVALID_ENVELOPE | no |
| `2002` | INVALID_MANIFEST | no |
| `3001` | SKILL_NOT_FOUND | no |
| `3002` | AGENT_UNAVAILABLE | yes |
| `3004` | IDENTITY_MISMATCH — bad signature, unverified caller for a gated skill, or a swapped key | no |
| `4001` | OVERLOADED | yes |
| `4002` | RATE_LIMITED | yes |
| `4003` | GOVERNANCE_DENIED | no |
| `4004` | APPROVAL_REQUIRED | yes |
| `5001` | INTERNAL_ERROR | yes |

(Legacy bridges sometimes emit `4000`/`5000`; treat as `2001`/`5001`.)

## Operating rules for a good citizen

1. Sign everything (ReactorPro convention). Unsigned works only while an
   edge is in `prefer` mode, and never for `invoke`.
2. One identity per agent, chosen once. The id is the address; two agents
   with one id cannot coexist (discovery drops one as "self", pins clash).
   `<org>/<site>/<name>` self-describes in logs and audit trails.
3. Fresh `ts` (UTC, NTP-synced) and a unique `id` per envelope — always.
4. Never build a JetStream stream over `mesh.agent.*.inbox`.
5. Never ack a core-NATS message (nats.py's `ack()` publishes an empty
   payload to `msg.reply` — the caller's inbox).
6. Quote replies to your own agent as remote material; a hostile peer's
   reply must never steer your agent.
7. Mailbox skills idempotent; no `invoke` over the mailbox.
8. A peer's manifest is advertisement, not authority. Trust comes from
   signatures and pins, never from registry entries.