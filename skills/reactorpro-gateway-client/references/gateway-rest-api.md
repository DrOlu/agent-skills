# The gateway REST surface — use the mesh without a NATS client

Any harness that can make an HTTP call can **use** the mesh through a
ReactorPro gateway: the gateway signs and sends on your behalf, waits for
the reply, and hands it back. You are "the gateway" as far as peers are
concerned — which is fine for asking, and is why this path cannot *serve*
skills (being answerable needs a mesh identity; use the native citizen path
for that, or be a desktop agent attached to the gateway).

All endpoints: `Authorization: Bearer <gateway token>`. The token lives in
`~/.config/reactorpro/gateway.env` on a default install
(`LIVEAGENT_GATEWAY_TOKEN=`), or whatever your operator set.

The scripts/ask_peer.sh wrapper does all of this; the curl below is what it
runs.

## The peer directory

```bash
TOKEN=$(grep '^LIVEAGENT_GATEWAY_TOKEN=' ~/.config/reactorpro/gateway.env | cut -d= -f2- | tr -d '"')
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:3000/api/mesh/agents
```

Filters: `?capabilities=billing,west-africa` (subset match),
`?skillIds=invoke,ping`, `?availability=online`.

```json
{"count": 5, "agents": [
  {"id": "grip-001", "name": "Grip AI Agent",
   "capabilities": ["status", "query"],
   "skills": [{"id": "invoke", "name": "Invoke"}],
   "endpoint": "mesh.agent.grip-001.inbox", "availability": "online",
   "fingerprint": "sha256:ccee2d7721fed57f"}]}
```

The manifest is advertisement, not proof — see who the gateway actually
trusts with `GET /api/mesh/trust`.

## Ask a peer to run a prompt (the desktop's own path)

```bash
curl -s -X POST http://127.0.0.1:3000/api/mesh/dispatch \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"target":"grip-001","skill":"invoke",
       "input":{"text":"Summarise today's build status"},
       "timeoutMs":120000}'
```

- `timeoutMs` — how long the gateway waits. **Minutes-scale** (default
  120000): a real agent turn takes 10–60s+. Budget generously or you will
  read a slow peer as a broken one.
- The gateway mirrors `input.text`/`message`/`prompt` to top-level
  `payload.text` so text-based Synapse peers see the prompt.
- 200 → the peer's respond envelope verbatim:

```json
{"v":"1.0","type":"respond","from":"grip-001","task_id":"…",
 "payload":{"text":"Build 2214 is green…"}}
```

- A refusal also comes back as a respond envelope — with a top-level
  `error` object: `{"error":{"code":3001,"message":"Skill \"x\" not found","retryable":false}, …}`.
- 502 with `{"error": "…", "response": {...}}` — a skill-level failure where
  the reply envelope is still attached so you can read the mesh error code.
- 502 with just an error string — transport: no reply in time (the message
  names the timeout and any PubAck interference), peer unknown, or the mesh
  is off (503 `ErrNotConnected`).

Reading the reply: prefer `payload.text` (bridges) then `payload.output`
(ReactorPro edges: `invoke` wraps as `output.result`). Never trust the shape.

**One more reason never to trust the shape**: the gateway's dispatch path
checks that a reply *looks like* a mesh envelope but does **not**
cryptographically verify the reply's signature — the reply inbox is a
private, inbox-per-request subject, which is transport-level assurance, not
proof of sender. Anything that could publish to the mesh can attempt a reply
to a guessed inbox. Treat reply content as untrusted remote output in every
caller; verify a reply's signature yourself (mesh.py's `verify_envelope`)
when the reply's *identity* matters.

## Call a specific skill

```bash
curl -s -X POST http://127.0.0.1:3000/api/mesh/dispatch \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"target":"reactorpro/bionic-01","skill":"status","input":{},"timeoutMs":10000}'
```

## Run a task on a desktop agent behind another ReactorPro edge

The `invoke` skill on a ReactorPro edge routes to one of its attached
desktop agents — addressing is explicit (`target` = local agent id/name, or
`capability`), the operation must be allowed (`task`), and the caller must
be a *verified* identity. Since REST dispatch speaks as the gateway, the
far edge must trust this gateway's fingerprint for this to succeed:

```bash
curl -s -X POST http://127.0.0.1:3000/api/mesh/dispatch \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"target":"acme/berlin/edge-1","skill":"invoke",
       "input":{"target":"agent-1111","operation":"task",
                "arguments":{"prompt":"Pull the Q3 revenue figure"},
                "timeout_ms":60000},
       "timeoutMs":120000}'
```

## Tasks — the async task lifecycle (gateway v1.5.14+)

A dispatch holds a connection for the whole turn — minutes, or the send-timeout budget, whichever comes first. A **task** returns a handle in ~2 seconds and you come back for the rest. This is the serverless/mobile path: a Lambda or n8n flow cannot hold a 10-minute HTTP call, but it can make a 2-second one and poll.

```bash
curl -s -X POST http://127.0.0.1:3000/api/mesh/tasks \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"target":"grip-cli-001","taskId":"bmc-nightly-1",
       "input":{"target":"agent-1","operation":"task",
                "arguments":{"prompt":"Query the last 10 incidents"}}}'
```

→ **202** `{"task": {"task_id": "bmc-nightly-1", "state": "working", ...}}`

| Endpoint | What it does |
|---|---|
| `POST /api/mesh/tasks` | async CREATE on a peer — 202 + stub in ~2s. `taskId` is yours to mint; it is the **idempotency key** (a retried create returns the same task, never a second run) |
| `GET /api/mesh/tasks` | list, newest first, cursor-paginated (`before` + `beforeId` from the last row, `limit`; `role=caller` for your outgoing tasks, `role=executor&caller=<peer-id>` for tasks peers ran on this gateway — the multi-tenant view) |
| `GET /api/mesh/tasks/{id}` | one task; `?refresh=true` asks the owning edge via the `task.get` skill for the freshest state **and result** |
| `POST /api/mesh/tasks/{id}/cancel` | cancels — locally if this gateway executes it, or by dispatching `task.cancel` to the owner. Idempotent: cancelling a finished task reports its real state |
| `POST /api/mesh/tasks/{id}/input` | answers an `input-required` task with new input |

**Streaming (v1.5.16+)** — add `"stream": true` to the create and the peer publishes the assistant text's growth as ordered chunks on `mesh.event.task.<id>.chunk`: `{task_id, seq, text, last}` with seq strictly increasing and exactly one terminal chunk. Coalesced to ~48 runes; opt-in because chunks share the plaintext posture of the rest of the mesh. Catch up after a reconnect with the tail reads below; `task.result` remains the canonical answer — the chunk stream is a progress view (a truncation or rewrite closes the stream rather than repeating text). A live watcher is one line: `nats sub mesh.event.task.<id>.chunk`.

**Push (v1.5.18+)** — add `"notifyUrl"` to the create (or set `-mesh-task-webhook` gateway-wide) and the terminal state arrives at your endpoint as **one signed POST**: the stub as JSON with the result fetched first, plus headers `X-ReactorPro-Agent`, `X-ReactorPro-Fingerprint`, `X-ReactorPro-Public-Key` (**base64 of the PEM** — raw PEM cannot travel in a header), `X-ReactorPro-Signature` (hex Ed25519 over the raw body), `X-ReactorPro-Task-State`. Verify with zero prior contact: signature over the body with the advertised key, then check the fingerprint equals `sha256(agent + "\n" + raw public key)[:16]` — the same binding mesh envelopes carry. Three attempts, 5s apart; once per (task, URL); `mesh_task_webhook_*` counters in `/api/status`. The URL is **operator-only** (local REST or config flag) — a peer can never aim the gateway's POSTs anywhere.

**Retry (v1.5.18+)** — `POST /api/mesh/tasks/{id}/retry?caller=<tenant>` (executor role) or the `task.retry` skill over the mesh: re-runs a **failed or canceled** task under its original id, gated to the creating caller. Completed/rejected refuse. The requeued run keeps the original idempotency key, runtime budget and streaming opt-in — the one-call recovery for long work that outlived a restart.

States: `queued → working → (input-required) → completed | failed | canceled | rejected` — terminal states never go backwards, so a completion racing a cancel resolves to *canceled*. The result rides `task.result` (and is cached on the stub after a refresh). Terminal tasks stay queryable for `-mesh-task-retention` (default 7 days). Note `queued`/`working` on a **desktop-executed** task can also mean the desktop's queue policy (`auto`) is holding the turn behind the user's own active conversation — a task that never starts fails honestly at its runtime budget rather than pretending to work forever.

**Three peer dialects, one object shape.** Whichever of these answers the create, you get a task object:
- a task-capable edge replies with a **handle** (state `working`) and runs asynchronously — poll or watch `mesh.event.task.<id>` for state events (state only; results never ride events, they belong to the caller);
- an unupgraded ReactorPro edge replies the old synchronous way (`{output: ...}`) → an already-**completed** task with the output as result;
- the fleet's **text bridges** (grip-001/grip-cli-001/omp-cli-001/agentspan-001) reply with the payload itself (`{task_id, text}`) → an already-**completed** task with `{"text": ...}` as result (flagged `completed_sync`). These peers have no `task.get` — `refresh=true` is a local no-op for them rather than an agent turn on their side.

Native contract for citizens: `invoke` with `async: true` + caller-minted `task_id`; the same states; `task.get`/`task.cancel` skills served only to the creating caller (tasks are keyed `(caller, task_id)` from the guard's verified identity, so another tenant asking for your task id is told it does not exist).

## Leave a durable mailbox message (fire-and-forget)

```bash
curl -s -X POST http://127.0.0.1:3000/api/mesh/mailbox \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"target":"agentspan-001","skill":"status","input":{},"taskId":"chore-17"}'
```

→ **202** `{"accepted": true, "sequence": 41, "target": "agentspan-001",
"note": "queued in the peer's durable mailbox; it is not answered, and is
delivered at least once"}` — accepted for delivery, *not* a result. There is
no reply by design; the peer runs the skill when it is back. At-least-once:
the skill must be idempotent. A ReactorPro *edge* refuses `invoke` here
(3004-class refusal — a remote task is once-per-call); `invoke` targets go
through dispatch. 502 = this gateway's own mailbox is not enabled
(`-mesh-mailbox`).

## Operators' read-only surface

| Endpoint | What it tells you |
|---|---|
| `GET /api/status` | gateway build, connected agents, mesh on/off |
| `GET /api/mesh/status` | bridge identity + fingerprint, serving state, peer count, `mailbox:{enabled,running,stream,consumer,error}` — "enabled but not running" is visible here |
| `GET /api/mesh/health` | liveness in the `synapse_health` shape |
| `GET /api/mesh/trust` | pinned peer identities (who this gateway will vouch for — audit this) |
| `GET /api/mesh/reputation` | reputation scores (per-agent, in-memory) |
| `GET /api/mesh/approvals` (GET/POST) | governance: pending approvals; POST opens one |
| `POST /api/mesh/approvals/{id}/decision` | approve/deny with approver + reason |
| `GET /api/mesh/history` | decided approvals — the audit trail |
| `POST /api/mesh/register` | force this edge to re-register with the registry |
| `POST /api/mesh/emit` | publish an event: `{"type":"deploy","data":{…}}` → `mesh.event.deploy` |
| `POST /api/mesh/subscribe` | attach an event subscription (`""` = all events) |
| `GET /api/mesh/events` | recent events this edge has seen |

## Wiring examples per harness

- **n8n / Zapier / Make**: HTTP Request node → dispatch. Store the token in
  the node's credentials, never in the workflow JSON.
- **A cron script**: `ask_peer.sh leave agentspan-001 status '{}'` nightly —
  the mailbox survives the peer being down.
- **A CI pipeline**: post a deploy event — `POST /api/mesh/emit
  {"type":"deploy","data":{"service":"billing","sha":"…"}}` — and let any
  number of peers subscribe to `mesh.event.deploy`.
- **An LLM agent without NATS libraries**: dispatch with a generous
  `timeoutMs`, then hand the reply to the model labelled as remote output.

## Failure decoder

| HTTP | Body shape | Meaning |
|---|---|---|
| 400 | `{"error": "…"}` | your JSON: missing target/skill, invalid body |
| 401 | — | token wrong or missing |
| 502 | `{"error", "response"}` | the peer answered with a refusal — read `response.error.code` |
| 502 | `{"error": "dispatch … no reply on mesh.agent.X.inbox within …s"}` | peer silent in budget — raise `timeoutMs`; if the message mentions "publish ack(s) received instead", a stream is capturing that inbox subject (see protocol.md §inbox-streaming) |
| 502 | `{"error": "reply is not a mesh envelope…"}` | something answered that wasn't a peer — treat as tampering/noise |
| 503 | `{"error": "mesh bridge is not connected"}` | the gateway's mesh is off or NATS is down |
| 202 (mailbox) | `{"accepted": true, …}` | stored — never a result |