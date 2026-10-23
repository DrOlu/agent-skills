---
name: neuralosd-synapse
description: >-
  Set up neuralOSd with Synapse mesh integration for agent-to-agent
  communication. Register probe menus as mesh capabilities, serve verified
  data answers to any agent on the mesh, discover peer agents by domain
  nouns, delegate refused questions to peers, deploy with template forks
  for fast redeploys, and monitor the fleet. Use when the user mentions
  neuralOSd Synapse, agent mesh, agent-to-agent, NATS, Synapse Gateway,
  mesh serve, mesh discover, mesh delegate, or wants neuralOSd instances
  to talk to each other.
---

# neuralOSd + Synapse: Agent Mesh Integration

neuralOSd instances become first-class citizens on the Synapse agent mesh.
Their verified probes are published as callable capabilities, requests are
served through the same refusal gate and accounting ledger as the HTTP door,
and gaps that can't be closed locally are routed to peer agents that can.

## Prerequisites

| Requirement | Check | Install |
|---|---|---|
| neuralosd ≥ 1.9.0 | `neuralosd --version` | `pip install 'neuralosd[all]'` |
| synapse-gateway | `curl http://127.0.0.1:8090/health` | `pip install synapse-gateway` |
| NATS server | `curl -s localhost:8222` | `docker run -p 4222:4222 -p 8222:8222 nats:latest` |
| Ollama (optional) | `ollama list` | `curl -fsSL https://ollama.com/install.sh \| sh` |

## Quick Start (5 minutes)

```bash
# 1. Build an instance
neuralosd init --source your_data.csv --name myservice --out ./myservice

# 2. Verify it answers
neuralosd ask --instance-dir ./myservice "how many rows"

# 3. Serve it on the Synapse mesh
neuralosd mesh serve --instance-dir ./myservice --gateway http://127.0.0.1:8090

# 4. From another terminal, discover it
neuralosd mesh discover --gateway http://127.0.0.1:8090 --skill "rows"

# 5. Ask it through the mesh
curl -X POST http://127.0.0.1:8090/request \
  -H 'Content-Type: application/json' \
  -d '{"agent_id": "myservice", "text": "how many rows"}'
```

## Architecture

```
┌─────────────┐     register      ┌──────────────┐
│ neuralosd   │──────────────────►│ Synapse mesh │
│ (instance)  │                   │ (NATS bus)   │
│             │                   └──────┬───────┘
│ probes:     │         discover        │
│   row_count │◄─────────────────────────┤
│   total_rev │                          │
│   breakdown │                          ▼
└─────────────┘                   ┌──────────────┐
                                  │ ReactorPro   │
                                  │ SuperAgent   │
                                  │ any agent    │
                                  └──────────────┘
```

Every probe is a declared capability with caged args, triggers, and a
verification gate. On the mesh, that's exactly what a registered skill is.

## The Three Capabilities

### 1. REGISTER — publish the probe menu

The probe menu becomes the agent's declared capabilities on the Synapse
registry. Other agents can discover what this instance can answer.

```bash
neuralosd mesh register --instance-dir ./myservice
```

### 2. SERVE — answer questions through the verified pipeline

Incoming mesh requests go through `router.ask()`: the same refusal gate,
the same accounting ledger, the same cache. The mesh is just another door.

```bash
neuralosd mesh serve --instance-dir ./myservice --gateway http://127.0.0.1:8090
```

The serve process is long-running. Press Ctrl+C to stop.

### 3. DISCOVER — find peer agents

When neuralosd refuses a question, it might be because another agent has
the capability. Discover peers by domain noun:

```bash
neuralosd mesh discover --gateway http://127.0.0.1:8090 --skill "incidents"
```

Returns agents whose skills match the query. The `matched` field shows
which domain nouns overlapped.

## The Refusal-to-Delegation Flow

When neuralosd can't answer a question locally, the Synapse discovery
mechanism finds a peer that can:

```
1. neuralosd refuses: "I can't answer this"  (local gate)
2. Synapse discovers: "but this peer might"  (mesh registry)
3. neuralosd delegates: "here's your question"  (mesh request)
4. The peer's answer is TAGGED as peer-sourced  (not verified locally)
```

The tagged response carries `source: "synapse_peer"` so downstream
consumers know it didn't come from a local probe. The caller decides
whether to trust it.

## Deploying Instances for the Mesh

### msb (recommended)

```bash
# Deploy with native port forwarding
neuralosd deploy --instance-dir ./myservice --name myservice \
                 --backend msb --port 8920

# Bake a template for fast redeploys
neuralosd deploy --instance-dir ./myservice --name myservice \
                 --backend msb --port 8920 --save-template ~/templates/myservice.msb

# Redeploy from template (skips pip install, ~5x faster)
neuralosd deploy --instance-dir ./myservice --name myservice-v2 \
                 --backend msb --port 8921 \
                 --from-template ~/templates/myservice.msb
```

### boxlite

```bash
# Deploy (the inner service is verified; the host door uses a relay)
neuralosd deploy --instance-dir ./myservice --name myservice \
                 --backend boxlite --port 8930

# Bake a template box
neuralosd deploy --instance-dir ./myservice --name myservice \
                 --backend boxlite --port 8930 --save-template ~/templates/myservice.bxl

# Fork from template
neuralosd deploy --instance-dir ./myservice --name myservice-v2 \
                 --backend boxlite --port 8931 \
                 --from-template ~/templates/myservice.bxl
```

### Door management

```bash
neuralosd door list                     # every deployed door
neuralosd door stop myservice           # stop a door's sandbox and forget it
neuralosd door proxy --name myservice --port 8940   # manual relay fallback
```

## The Behavioural Banks

Every instance ships with `golden.json` (positive cases) and `traps.json`
(refusal cases). The reason loop replays both banks before installing a
new metric — if it would break a trap, the install is refused.

```bash
# golden.json — positive cases that must route correctly
{"items": [{"q": "how many rows", "expect_probe": "row_count"}]}

# traps.json — refusal cases that must NOT be answered
{"items": [{"q": "xyzzy plugh", "expect_refusal": true,
            "refusal_reason": "no_probe_matches"}]}
```

## Calibrating the Refusal Thresholds

The router's refusal thresholds (floor, margin, coverage) can be fitted
against golden + trap banks:

```bash
neuralosd calibrate --golden ./myservice/golden.json
```

This searches (floor × margin), punishes a confident wrong answer 5×
harder than a false refusal, writes the chosen operating point to
`router.json`, and prints the trade-off curve.

## The Reason Loop: Extending the Menu with AI

When the router refuses because the menu can't express the question's
SHAPE (a ratio, a comparison, a per-unit calculation), the reason loop
escalates to a reasoning model that proposes a new derived metric:

```bash
# Rehearse with nothing at stake
neuralosd reason --instance-dir ./myservice --dry-run \
  --oracle 0.193764 \
  "what share of total revenue comes from the top 10 customers"

# Install
neuralosd reason --instance-dir ./myservice \
  "what share of total revenue comes from the top 10 customers"
```

The derived metric is a JSON spec, not generated code. Nothing a model
emits is executed.

## Scripts

### scripts/serve_mesh.sh

Start a neuralosd instance on the Synapse mesh.

```bash
bash scripts/serve_mesh.sh <instance-dir> [gateway] [port]
```

### scripts/fleet_status.sh

Check the health of every deployed door.

```bash
bash scripts/fleet_status.sh
```

### scripts/register_fleet.sh

Register all instances in a directory on the Synapse mesh.

```bash
bash scripts/register_fleet.sh <instances-dir> <gateway>
```

## Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| Gateway not reachable | synapse-gateway not running | `pip install synapse-gateway && synapse-gateway --nats nats://localhost:4222 --port 8090` |
| NATS not reachable | NATS server not running | `docker run -p 4222:4222 nats:latest` |
| No agents discovered | No agents registered on the mesh | Start other agents on the same NATS server |
| reason loop refuses | Mapper can't compose a metric from the inventory | Check the inventory has enough quantities; add more probes |
| reason loop channel wedged | boxlite 0.10.5 exec channel degrades after a detached serve | Restart the box; the pipeline does this automatically |
| Calibrate fails | No traps file | Create traps.json with questions the instance must refuse |

## API Reference

### `neuralosd mesh serve`

| Flag | Default | Description |
|---|---|---|
| `--instance-dir` | required | The instance to serve |
| `--gateway` | `http://127.0.0.1:8090` | Synapse gateway URL |

### `neuralosd mesh discover`

| Flag | Default | Description |
|---|---|---|
| `--gateway` | `http://127.0.0.1:8090` | Synapse gateway URL |
| `--skill` | `""` | The skill/capability to search for |
| `--instance-name` | `""` | Exclude this agent from results |

### `neuralosd synapse.py` module

| Class/Function | Description |
|---|---|
| `SynapseHTTP` | HTTP client for the gateway (discover, request, health) |
| `MeshAgent` | Wraps a Router for mesh serving; handles requests via `router.ask()` |
| `discover_peers(transport, question, own_name)` | Find agents whose skills match domain nouns |
| `delegate_to_peer(transport, peer, question)` | Forward to a peer, tag as peer-sourced |
