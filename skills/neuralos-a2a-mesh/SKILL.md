---
name: neuralos-a2a-mesh
description: Install, configure, operate and troubleshoot an end-to-end agent-to-agent (A2A) messaging and communication system across multiple, diverse and disparately-networked systems using neuralOS on-device inference plus the ReactorPro gateway mesh, over a central NATS server. Use when deploying, extending, benchmarking, hardening or repairing a neuralOS/Gateway multi-edge mesh — macOS, Linux, Windows, cloud VMs, on-prem servers, edge devices, intermittent or air-gapped networks. Covers requirement gathering (asks when parameters are missing), cross-platform installation and service wiring, signed skillproxy butler lanes with mandatory needle grounding, cross-organisation trust, day-2 operations, upgrade/rollback, and deep connection troubleshooting including NATS/TLS/permissions/leaf-node/fingerprint/engine-selection failures. This is the standard template for neuralOS/Gateway A2A deployments across Africa and beyond.
---

# neuralOS A2A Mesh — deploy, operate, troubleshoot

An end-to-end **agent-to-agent (A2A) messaging system** built from three
layers that this skill wires together:

| Layer | Component | What it provides |
|---|---|---|
| **Transport** | NATS / Synapse subjects | request/reply, pub/sub, JetStream durability, leaf nodes across networks |
| **Trust + routing** | `reactorpro-gateway` (v1.7.5+) | Ed25519-signed envelopes, fingerprint pins, `invoke` + `skillproxy` lanes, REST/UI on `:3000` |
| **Intelligence** | neuralOS / needle engine | offline 121M tool-calling model that grounds every butler query to a read-only probe |

Every remote action is: **question in → engine selects a probe → read-only
execution → small capped digest back over a signed envelope.** There is no
keyword-only fallback in the serving path.

## The one rule

**Every requirement is either already given or you must ask for it.** Never
invent a NATS URL, account, credential, fingerprint, service account, path or
port. Run the intake in `references/parameters.md` before installing anything;
if a required value is missing, request it from the operator and wait.

## Workflow

1. **Intake** — read `references/parameters.md`, collect every REQUIRED
   parameter (central NATS server, per-edge identity, creds, pins, ports,
   service accounts, engine dir, butler skills). Ask for anything missing.
2. **Design the topology** — pick from `references/architecture.md`
   (single edge → two-edge → three-edge → multi-country hub-and-spoke with
   leaf nodes). Confirm the shape with the operator.
3. **Install per host** — follow `references/install.md` for macOS, Linux and
   Windows (engine, gateway, butler harness, service wiring, verification).
4. **Wire trust** — exchange fingerprints out of band, set mutual
   `LIVEAGENT_GATEWAY_MESH_TRUSTED_PEERS`, `-mesh-verify-mode=require`,
   `-mesh-trust-on-first-use=false` on every edge.
5. **Stand up a butler** — use `references/butler-harness.md` and
   `scripts/butler_template.py`; mandatory needle grounding, read-only probes,
   honest holes.
6. **Verify end to end** — run `scripts/doctor.sh` / `doctor.ps1`, then a
   never-seen-before benchmark from at least two origins
   (`scripts/dispatch.sh`). Do not sign off without it.
7. **Operate** — `references/operate.md` (health, upgrades, rollback, reboot
   survival, capacity, key/credential rotation, adding an edge or skill).
8. **Troubleshoot** — `references/troubleshooting.md` when anything fails;
   work top-down: transport → trust → gateway → butler → engine → data.

## References (one hop, load on demand)

| File | Read when |
|---|---|
| `references/architecture.md` | designing the topology; envelope/subject/trust semantics; leaf nodes and cross-org |
| `references/parameters.md` | **before every install** — the full intake questionnaire + central NATS server parameters |
| `references/install.md` | installing engine/gateway/butler on macOS, Linux or Windows; service wiring |
| `references/butler-harness.md` | writing or extending a butler skill; menu design; skillproxy contract |
| `references/operate.md` | day-2: health, benchmarks, upgrades, rotation, reboot survival, new edges |
| `references/troubleshooting.md` | any failure — connection, TLS, permissions, trust, engine selection, cross-platform |
| `references/examples.md` | simple → complex worked examples end to end, including the Africa multi-country playbook |

## Scripts

| Script | Purpose |
|---|---|
| `scripts/doctor.sh` / `doctor.ps1` | full environment + connectivity diagnostic; prints a pass/fail report |
| `scripts/dispatch.sh` / `dispatch.ps1` | call a remote butler through the signed `skillproxy` lane; measures wall time |
| `scripts/butler_template.py` | cross-platform butler harness: ask.py retrieval → needle → read-only probe → capped digest |
| `scripts/bootstrap_edge.sh` / `bootstrap_edge.ps1` | install engine + gateway + butler as a reboot-surviving service |
| `scripts/nats_central.conf` | central cloud NATS server template (TLS, accounts, JetStream, leaf-node acceptor) |
| `scripts/nats_edge.conf` | edge/client-side NATS config + leaf-node remote template |

Run a script with the platform's shell: `bash scripts/doctor.sh`,
`pwsh -File scripts\doctor.ps1`. Scripts read parameters from environment
variables and say exactly which are missing.

## Non-negotiable constitution

- **Mandatory needle grounding.** Every butler query routes through the
  on-device engine. No deterministic keyword fallback in the serving path.
- **Read-only probes.** Buttlers execute only probes from their
  `needle_menu.json`. No writes, no arbitrary shell, no credentials.
- **Honest holes.** Upstream failure ⇒ relay the error verbatim. No probe
  selected ⇒ say so. Never fabricate data.
- **Signed everything.** Envelopes are Ed25519-signed; peer fingerprints are
  mutually pre-pinned. Reaching the bus is not being trusted.
- **Reboot-surviving by default.** launchd `RunAtLoad`+`KeepAlive`, systemd
  `Restart=always`, NSSM `AUTO_START`.
- **Never hardcode engine paths.** Resolve through `NEEDLE_ENGINE_DIR`.

## Quick start (two machines, one central NATS)

```bash
# On each edge: 1) install  2) set env  3) verify
export NATS_URL="tls://nats.example.africa:4222"
export NATS_CREDS="~/.nats/edge1.creds"
export GATEWAY_MESH_ID="reactorpro/edge1"
export NEEDLE_ENGINE_DIR="/opt/neuralos/needle"
bash scripts/bootstrap_edge.sh          # macOS/Linux
pwsh -File scripts\bootstrap_edge.ps1   # Windows

bash scripts/doctor.sh                  # expect all PASS
bash scripts/dispatch.sh reactorpro/edge2 reactorpro/edge2-butler butler.query \
     "which customer spent the most?"
```

Then read `references/examples.md` for the multi-edge, cross-org and
Africa multi-country patterns.