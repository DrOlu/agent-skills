# Deployment scenarios

Pick the scenario that matches what you are building. Each one states what to set, how to
verify it, and — just as importantly — **what that scenario cannot do**, so you don't spend
an afternoon debugging a limitation you chose.

## Contents

- [Start here: which scenario am I?](#start-here-which-scenario-am-i)
- [S1 — Gateway only, no desktop agent](#s1--gateway-only-no-desktop-agent)
- [S2 — Gateway with desktop agents, one site](#s2--gateway-with-desktop-agents-one-site)
- [S3 — Several sites, one organisation](#s3--several-sites-one-organisation)
- [S4 — Two organisations federated](#s4--two-organisations-federated)
- [S5 — Mixed fleet (some edges not upgraded yet)](#s5--mixed-fleet-some-edges-not-upgraded-yet)
- [S6 — Closed fleet, high assurance](#s6--closed-fleet-high-assurance)
- [S7 — A partner organisation that has no desktop agents](#s7--a-partner-organisation-that-has-no-desktop-agents)
- [Choosing the NATS topology](#choosing-the-nats-topology)
- [Scenario comparison table](#scenario-comparison-table)

---

## Start here: which scenario am I?

Answer three questions:

**1. Will any ReactorPro desktop app connect to this gateway?**
- No → **[S1](#s1--gateway-only-no-desktop-agent)**. A perfectly valid deployment: the gateway
  serves the web UI and joins the mesh, but it cannot run work for anyone.
- Yes → continue.

**2. Is everything you connect to owned by you?**
- Yes, and it is one site → **[S2](#s2--gateway-with-desktop-agents-one-site)**.
- Yes, but several sites/offices → **[S3](#s3--several-sites-one-organisation)**.
- No — another company is involved → **[S4](#s4--two-organisations-federated)**.

**3. Is your fleet all on the same version?**
- No, or you are not sure → read **[S5](#s5--mixed-fleet-some-edges-not-upgraded-yet)** first.
  It is short and it prevents the single most confusing failure in this whole system.

If you are handling regulated or hostile-adjacent traffic, read **[S6](#s6--closed-fleet-high-assurance)**
after whichever scenario applies.

> **Two rules that apply to every scenario.** Give every edge a **unique** id
> (`<org>/<site>/<edge>`), and **keep `-mesh-require-verified-invoke` on** unless you have a
> specific reason not to. Both are explained where they first matter, below.

---

## S1 — Gateway only, no desktop agent

**You are here if:** you want a ReactorPro gateway on a server — a VPS, a jump host, a central
node — and no ReactorPro desktop app will connect to it.

This is a legitimate deployment, not a half-finished one. A gateway with no agents behind it:

- serves the **web UI** and the HTTP API;
- holds a **mesh identity** and can sign and verify like any other edge;
- **appears in the directory** so peers can see who you are;
- answers the read-only skills: `ping`, `describe`, `status`.

### Set

```bash
LIVEAGENT_GATEWAY_TOKEN=<32+ byte random value>       # required
LIVEAGENT_GATEWAY_HTTP_ADDR=127.0.0.1:3000            # behind a reverse proxy

# Optional: join the mesh
LIVEAGENT_GATEWAY_MESH_ENABLED=true
LIVEAGENT_GATEWAY_MESH_URL=nats://127.0.0.1:4222
LIVEAGENT_GATEWAY_MESH_AGENT_ID=acme/lagos/jumpbox-1   # unique; see the note below
LIVEAGENT_GATEWAY_MESH_NAME=Acme Jump Host
LIVEAGENT_GATEWAY_MESH_CAPABILITIES=agent,reactorpro    # what THIS EDGE advertises
```

### Verify

```bash
curl -s localhost:3000/healthz                       # {"ok":true}
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/status
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/mesh/status
```

`/api/status` should show **no agents** (nothing is connected) — that is expected, not a fault.

### What this scenario cannot do

- **It cannot serve `invoke`.** There is no desktop agent to route work to, so a peer asking for
  a task gets `3002 AGENT_UNAVAILABLE`. The read-only skills still work.
- Its published `local_agents` directory will be **empty**.

If a peer needs to *run* work, it must be an edge with a desktop agent attached — see S2.

---

## S2 — Gateway with desktop agents, one site

**You are here if:** one organisation, one place, one or more ReactorPro desktop apps talking to
one gateway. This is the common case.

### Set

```bash
LIVEAGENT_GATEWAY_TOKEN=<32+ byte random value>
LIVEAGENT_GATEWAY_HTTP_ADDR=:3000                      # LAN clients connect directly
LIVEAGENT_GATEWAY_DATA_DIR=/var/lib/reactorpro-gateway # keep the identity somewhere obvious

LIVEAGENT_GATEWAY_MESH_ENABLED=true
LIVEAGENT_GATEWAY_MESH_URL=nats://127.0.0.1:4222
LIVEAGENT_GATEWAY_MESH_AGENT_ID=acme/lagos/edge-1
LIVEAGENT_GATEWAY_MESH_CAPABILITIES=agent,reactorpro
```

Then connect each desktop app: **Settings → Remote** → Gateway URL `http://<host>`, port `3000`,
and the gateway token (or a per-agent token — preferred, so you can revoke one machine without
rotating everyone).

### Verify

```bash
# the desktop agent registered
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/status | grep -o '"online":true'

# the edge publishes a directory of agents behind it
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/mesh/status
```

You want to see the agent listed, and the edge's manifest carrying a non-empty `local_agents`
with the agent's advertised capabilities.

### About the agent id — read this once

`LIVEAGENT_GATEWAY_MESH_AGENT_ID` is an **address, not a label**. It forms the subject peers send
to (`mesh.agent.<id>.inbox`) and it is **hashed into the identity fingerprint**. On first start
the gateway mints an identity file, and from then on the id is **permanent**: configuring a
different one later is a **hard startup failure**, not a warning. Changing it means moving the
identity file aside to mint a new one, which changes your fingerprint and breaks every peer that
pinned it.

Use `<org>/<site>/<edge>`. **Every edge needs a different id** — two edges sharing one discard
each other as "self", and the mesh looks empty while everything reports healthy.

### What this scenario can do

Serve the read-only skills, and — with desktop agents attached and invocation left enabled —
accept remote tasks from verified peers. If you have no peers yet, that is fine: nothing is
reachable until you federate.

---

## S3 — Several sites, one organisation

**You are here if:** you have more than one office or site, all yours, and you want them to find
and use each other.

### Topology

One edge per site, all connected to your NATS server. Each publishes its own identity and its own
agent directory; everyone can see everyone.

```
        acme/lagos/edge-1 ─┐
        acme/abuja/edge-1 ─┼── your NATS server
        acme/porto/edge-1 ─┘
```

### Set

Per edge, identical except for the id and display name:

```bash
LIVEAGENT_GATEWAY_MESH_AGENT_ID=acme/lagos/edge-1        # <org>/<site>/<edge>, unique per site
LIVEAGENT_GATEWAY_MESH_NAME=Acme Lagos
LIVEAGENT_GATEWAY_MESH_CAPABILITIES=agent,reactorpro,warehouse   # per-site tags, your choice

# Discovery: the default. Keep it unless you know every edge publishes to the bucket.
LIVEAGENT_GATEWAY_MESH_REGISTRY=auto

# Trust: your own fleet, so first-use learning is reasonable
LIVEAGENT_GATEWAY_MESH_TRUST_ON_FIRST_USE=true
LIVEAGENT_GATEWAY_MESH_VERIFY_MODE=prefer
```

### Using it: address by capability, not by machine

Each site's agents advertise what they can do, so you can ask for *the capability* and let the
receiving edge choose an online agent:

```bash
curl -s -X POST localhost:3000/api/mesh/dispatch \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{
        "target": "acme/porto/edge-1",
        "skill": "invoke",
        "input": {"capability": "task", "operation": "task",
                  "arguments": {"prompt": "Reconcile last night'\''s stock movements."}}
      }'
```

Two different lists are in play and they are easy to confuse:

- `-mesh-capabilities` — what **the edge itself** advertises, so peers can find a *site* that can
  do something.
- the `capability` field in an `invoke` request — what the **attached desktop agents** advertise,
  so the receiving edge can pick an *agent* that can do something.

### Verify

```bash
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/mesh/agents
```

Expect one entry per site, each with a `local_agents` list. A site that shows up with an empty
directory either has no desktop app connected, or is an S1 gateway.

---

## S4 — Two organisations federated

**You are here if:** another company's agents need to talk to yours. The two sides trust each
other's identity but nothing else, and either side must be able to say exactly who asked for what.

### Before you start

Exchange **fingerprints**, out of band. Each side reads its own:

```bash
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/mesh/status   # fingerprint field
```

### Set — on both sides, symmetrically

```bash
# Identity: unique, org-namespaced
LIVEAGENT_GATEWAY_MESH_AGENT_ID=acme/lagos/edge-1          # theirs: globex/berlin/edge-1

# Trust: strict. No learning, only pinned fingerprints.
LIVEAGENT_GATEWAY_MESH_VERIFY_MODE=require                 # refuse unsigned entirely
LIVEAGENT_GATEWAY_MESH_TRUST_ON_FIRST_USE=false
LIVEAGENT_GATEWAY_MESH_TRUSTED_PEERS=sha256:<their-fingerprint>,sha256:<their-other-edge>

# What work you accept. As narrow as you can live with.
LIVEAGENT_GATEWAY_MESH_REQUIRE_VERIFIED_INVOKE=true        # the floor — keep on
LIVEAGENT_GATEWAY_MESH_INVOKE_OPERATIONS=task
LIVEAGENT_GATEWAY_MESH_INVOKE_TIMEOUT=60s

# Discovery
LIVEAGENT_GATEWAY_MESH_REGISTRY=auto                        # unless the whole fleet is upgraded
```

### Why `require` and the floor both matter

The **default** verify mode is `prefer`: it verifies a signature when one is present but **still
accepts unsigned messages**. That is fine inside one organisation.

Across an organisation boundary it is not, because of this chain: invocation is allowed by
default, `prefer` accepts unsigned senders, and therefore anything able to publish to the shared
NATS subject could ask one of your laptops to run work. That is a remote-code hole, not a feature.

Two settings break that chain, and both are needed:

- `-mesh-verify-mode=require` — no identity, no service.
- `-mesh-require-verified-invoke=true` — and even with a declared identity, an invocation is
  refused unless that identity was **actually verified** (a signature that matched a pinned
  fingerprint). This is the floor. It is on by default; leave it on.

With both, "allowed to invoke" means "allowed for an authenticated peer".

### Verify

```bash
# Do we trust them?
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/mesh/trust

# Can we see them?
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/mesh/agents

# Cheap, read-only liveness before you send real work
curl -s -X POST localhost:3000/api/mesh/dispatch \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"target":"globex/berlin/edge-1","skill":"ping","input":{},"timeoutMs":5000}'
```

If that ping returns `4003 GOVERNANCE_DENIED`, the floor is doing its job: their fingerprint is
not pinned on your side, or yours is not pinned on theirs.

### Operational notes

- **Cancellation is best-effort.** If the caller's deadline passes, the edge tells the desktop to
  cancel so an abandoned request stops consuming the local user's quota — but if the desktop is
  unreachable at that moment, the cancel cannot be delivered.
- **The receiving edge is the audit point** for who asked for what. The desktop itself keeps no
  record of a remote invocation.
- Start with `ping` and `describe` before sending work. They cost nothing and prove the whole
  path — identity, trust, routing, reply — without executing anything.

---

## S5 — Mixed fleet (some edges not upgraded yet)

**You are here if:** you have upgraded some edges and not others, or you peer with an
implementation that is not this one.

**This scenario exists because of a real bug.** In v1.5.1, the default discovery mode was
registry-only. An upgraded edge would then go **blind to every peer that had not upgraded** —
and it failed silently, because the registry read *succeeds* (it returns at least your own
entry), so the "read failed, fall back to broadcast" path never ran. The mesh looked healthy and
empty at the same time.

### Set

```bash
LIVEAGENT_GATEWAY_MESH_REGISTRY=auto     # the default — MAKE SURE IT IS NOT OVERRIDDEN
```

`auto` merges **both** mechanisms: the JetStream registry *and* the broadcast window. A peer that
publishes nothing to the bucket appears only in the broadcast, and `auto` sees it.

### Verify

```bash
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/mesh/agents    # count them
```

If the count drops after an upgrade, this is the first thing to check. As an immediate
workaround, `-mesh-registry=broadcast` restores the old behaviour without upgrading.

### The rule

- **`auto`** — mixed fleet. Registry *and* broadcast, merged. **Use this unless you are certain.**
- **`jetstream`** — registry only, and start-up fails without JetStream. Only for a closed fleet
  where you know every peer publishes to the bucket.
- **`broadcast`** — never touches JetStream. Simple, but lossy: a slow peer is silently missed.

Fixed properly in **v1.5.2**. If you are on v1.5.1, upgrade.

---

## S6 — Closed fleet, high assurance

**You are here if:** you control every edge, the traffic is sensitive, and you would rather refuse
something legitimate than accept something unverified.

### Set

```bash
LIVEAGENT_GATEWAY_MESH_VERIFY_MODE=require              # no unsigned traffic, ever
LIVEAGENT_GATEWAY_MESH_TRUST_ON_FIRST_USE=false         # no learning; pins only
LIVEAGENT_GATEWAY_MESH_TRUSTED_PEERS=sha256:<a>,sha256:<b>,sha256:<c>
LIVEAGENT_GATEWAY_MESH_ACCEPTED_VERSIONS=0.3.0          # only if every peer is this build
LIVEAGENT_GATEWAY_MESH_REGISTRY=jetstream                # every peer publishes; fail fast if not
LIVEAGENT_GATEWAY_MESH_INVOKE_OPERATIONS=task            # narrowest allowlist you can live with
LIVEAGENT_GATEWAY_MESH_RATE_LIMIT_PER_SECOND=20          # tighten to your real traffic shape
LIVEAGENT_GATEWAY_MESH_MAX_ENVELOPE_BYTES=262144         # 256 KiB is plenty for control messages
```

### Two cautions

- `-mesh-accepted-versions` is **not** recommended by default. Peers in the wild declare `1.0`
  and `0.3.0` alike, and a version string you do not recognise is not evidence of incompatibility
  — the envelope shape is what actually matters, and it is validated field by field. Pin it only
  when you genuinely control every peer's build, or you will reject working peers over a label.
- `-mesh-registry=jetstream` makes start-up fail if the bucket is unavailable. That is the point
  (fail fast, no silent degradation) — but it means a JetStream problem becomes a startup outage.

### Verify

```bash
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/mesh/trust      # only your pins
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/mesh/agents
# a peer that is not pinned must NOT be able to invoke
```

Watch `mesh_trust_mismatch_total` and `mesh_verify_failed_total` on `/api/status`. Both should
sit at **zero**. Non-zero means signatures or pinned identities are disagreeing — investigate
immediately rather than assuming a peer is broken.

---

## S7 — A partner organisation that has no desktop agents

**You are here if:** you are federating with an organisation that runs a gateway but no ReactorPro
desktop app — a partner who wants to be *reachable and visible*, or who acts as a central node.

This works, and it is a useful shape. Their edge:

- holds an identity and can be **found** (`describe`) and **checked** (`ping`, `status`);
- publishes a directory — just an **empty one**;
- **cannot serve `invoke`.**

### What the peer sees

A `describe` returns their manifest with `local_agents: []` and `local_agent_total: 0`, so you can
tell at a glance that there is nothing behind them to run work on. This is why the directory is
published at all: you can see the shape of a partner's estate before sending anything.

### What happens if you ask anyway

```json
{"target": "partner/edge-1", "skill": "invoke",
 "input": {"capability": "task", "operation": "task", "arguments": {"prompt": "..."}}}
```

→ `3002 AGENT_UNAVAILABLE`. A precise refusal, not a hang and not a generic internal error —
you can distinguish "nobody there" from "I broke".

### Typical uses

- **A central registry / directory node** for a group of organisations: it hosts the shared
  JetStream bucket and the NATS server, holds an identity so it is addressable, and runs no work.
- **A visibility node** at a partner that wants to see who is on the mesh without exposing a
  laptop.
- **A future site**: the gateway is deployed and trusted ahead of the desktop app arriving.
  Adding an agent later requires **no change** to any peer — the directory simply fills in.

---

## Choosing the NATS topology

| Topology | Shape | Use when |
|---|---|---|
| **One shared bus** | Every edge connects to one NATS server. | A pilot, one trusted partner, or your own multi-site estate. Simplest. |
| **Bus per organisation, linked** | Each org runs its own NATS; a route or leaf node joins them so `mesh.*` subjects flow. | Real cross-organisation use. Each side keeps its own credentials, firewall and monitoring. |
| **Gateway-only registry node** | One NATS + one gateway, no desktops, acting as the directory. | A group of organisations wanting a shared directory without a shared execution surface. |

If you link two NATS servers, remember that **JetStream and KV subjects cross a leaf node too**.
Decide deliberately whether they should: letting a partner's server see your `$JS.API.*` subjects
is usually not what you want, and the standard practice is to deny them on the leaf and keep
discovery flowing over ordinary `mesh.*` subjects.

---

## Scenario comparison table

| | S1 gateway-only | S2 one site | S3 multi-site | S4 federated | S6 closed fleet | S7 desktop-less partner |
|---|---|---|---|---|---|---|
| Serves web UI + API | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Holds a mesh identity | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Read-only skills (`ping`/`describe`/`status`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Published agent directory | empty | yes | yes | yes | yes | empty |
| Can serve `invoke` | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ |
| `verify-mode` | `prefer` | `prefer` | `prefer` | **`require`** | **`require`** | `require` |
| Trust | n/a | TOFU ok | TOFU ok | **pinned** | **pinned** | pinned |
| Registry | `auto` | `auto` | `auto` | `auto` | `jetstream` | `auto` |

---

## A last sanity check for any scenario

Before you call a deployment done, confirm all four:

```bash
curl -s localhost:3000/healthz                                              # listening
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $TOKEN" \
     localhost:3000/api/status                                              # 200, token good
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/mesh/status    # connected, id, fingerprint
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/mesh/agents    # peers, if any
```

If the mesh is enabled, also confirm **the fingerprint has not changed** since you last recorded
it. An unchanged fingerprint after an upgrade means you kept your identity; a changed one means
the process is looking at a different data directory and has minted a new identity — fix that
before anything else, because peers have already seen the new one.
