# Architecture — how a neuralOS A2A mesh is put together

## 1. The three layers

```
   EDGE A (macOS/Linux/Windows)                 EDGE B (another OS/network)
   ┌──────────────────────────────┐             ┌──────────────────────────────┐
   │ caller (script, app, agent)  │             │ butler harness (service)     │
   │        │ REST :3000          │             │        ▲ skillproxy          │
   │  reactorpro-gateway          │             │  reactorpro-gateway          │
   │  signs+verifies envelopes    │             │  signs+verifies envelopes    │
   └──────────────┬───────────────┘             └──────────────┬───────────────┘
                  │ outbound only                              │ outbound only
                  └──────────────► NATS (central, cloud) ◄─────┘
                                    subjects: mesh.agent.*.inbox,
                                    mesh.registry.*, mesh.event.*, mesh.task.*
                                        │
                          (optional) leaf nodes for on-prem/air-gapped sites
```

- **NATS** carries small JSON envelopes. It is the only thing reached over the
  public internet. Central cloud server = the exchange.
- **Gateway** is the only network citizen per site. It holds the identity key,
  the trust pins, the policy gates, and the local `:3000` REST/UI surface.
- **Butler harness** is a headless executor with **no model key**: it answers
  by grounding through the local neuralOS/needle engine against read-only
  probes, then returns a capped digest.

## 2. Identity, signing and trust

- Each gateway mints an Ed25519 keypair on first start. Its **fingerprint**:
  `sha256: ` + first 16 hex of `sha256(agent_id + "\n" + raw_public_key)`.
- The agent id is *inside* the fingerprint, so the same key under a different
  name is a different identity. Changing the id breaks every pin.
- Trust = **explicit pins**, exchanged out of band (the same channel you would
  use to verify bank details). Production never relies on trust-on-first-use.
- Every envelope carries `sig` (Ed25519), `pub` (PEM), `fp` (fingerprint).
  The receiver verifies signature + freshness + replay + pin match, and only
  then applies policy.

## 3. The wire object (envelope v0.3.0)

```json
{
  "v": "0.3.0",
  "id": "pWvX…",
  "type": "request",
  "ts": "2026-09-28T09:45:50.123Z",
  "from": "reactorpro/lagos-01",
  "to": "reactorpro/nairobi-02",
  "task_id": "report-17",
  "trace": {"trace_id": "…", "span_id": "…"},
  "payload": {
    "skill": "skillproxy",
    "input": {
      "target": "reactorpro/nairobi-02-butler",
      "skill": "butler.query",
      "args": {"question": "which customer spent the most?"}
    },
    "text": "which customer spent the most?",
    "reply_to": "_REPLY.xj3.21"
  },
  "sig": "<hex>", "pub": "-----BEGIN PUBLIC KEY-----…", "fp": "sha256:<16hex>"
}
```

`id` is the replay key; `ts` must be inside the ±5 min window; `text` mirrors
the prompt for text-only bridges; `reply_to` travels inside the signed payload
so JetStream-captured inboxes still work.

## 4. Subjects and primitives (Synapse)

| Primitive | Subject | Use |
|---|---|---|
| register | `mesh.registry.register` (`.deregister`) | announce agents/capabilities |
| discover | `mesh.registry.discover` (+ `.ranked`, `mesh.registry.get.{id}`) | find agents by capability |
| request | `mesh.agent.{id}.inbox` | ask an agent to do work |
| respond | reply `_INBOX`/`_REPLY` subject | return result/error |
| emit | `mesh.event.{type}` | broadcast |
| subscribe | `mesh.event.{pattern}` (wildcards) | listen |
| heartbeat | `mesh.heartbeat.{id}` | liveness |
| tasks | `mesh.task.>` | task state, chunks |
| mailbox | `mesh.agent.{id}.mailbox` | durable, no reply (JetStream) |

Gateway skill surface: `ping`, `describe`, `status`, `invoke`, and (v1.7.5+)
`skillproxy` — the signed lane that reaches butler skills.

## 5. Dispatch envelope (what a caller actually sends)

```bash
curl -s -X POST http://127.0.0.1:3000/api/mesh/dispatch \
  -H "Authorization: Bearer $LIVEAGENT_GATEWAY_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "target": "reactorpro/nairobi-02",
    "skill": "skillproxy",
    "timeoutMs": 120000,
    "input": {
      "target": "reactorpro/nairobi-02-butler",
      "skill": "butler.query",
      "args": {"question": "show the revenue breakdown by country"}
    }
  }'
```

Reply: `payload.output.reply = {"ok": true, "result": "…", "elapsed_s": N,
"grounding": "needle engine"}` or, on a miss,
`{"ok": false, "hole": true, "error": "needle engine did not select a probe"}`.
Butlers accept the question under `args` (canonical) or `input`/`message`.

## 6. Topology patterns

1. **Single edge (dev)** — gateway + butler on one host, local NATS.
   Use for building the butler before any network is involved.
2. **Two edges (first real mesh)** — e.g. a laptop/lab edge and a server edge;
   mutual pins; benchmark both directions.
3. **Three edges (reference production)** — Mac + two Windows servers, as
   proven here: mutual pins, every edge engine-grounded, reboot-surviving.
4. **Multi-country hub-and-spoke (Africa template)** — central cloud NATS as
   the hub; each country site runs an edge that reaches *out* to the hub;
   on-prem sites with no route use a **leaf node** (site-local NATS bridging
   to the hub) so only one host crosses the WAN.
5. **Cross-organisation** — separate NATS accounts, pins exchanged
   contractually, `require` mode, allowlisted skills, no shared credentials.
6. **Intermittent / low-bandwidth** — same edge, plus the durable mailbox for
   fire-and-forget work, and a benchmark that records real latency windows.
7. **Air-gapped** — no WAN at all: ship the neuralOS bundle and menu in, run
   the engine and gateway locally, and exchange envelopes by physical media
   only if a mesh is genuinely required (document it; most air-gapped cases
   need only the local single-edge pattern).

## 7. Why the design is shaped like this

- **Outbound-only** means no firewall exceptions, no VPN, no exposed laptop.
- **Signed + pinned** means a reachable bus is not a trusted bus.
- **Engine-grounded butlers** mean answers are cheap, offline, auditable, and
  cannot be invented — the serving path has no keyword fallback.
- **Small digests** mean the model (121M) never has to hold a payload; data
  gravity stays at the edge.