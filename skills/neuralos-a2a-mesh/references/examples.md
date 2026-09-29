# Examples — simple to complex, end to end

Each example is self-contained: what you need, the steps, the verify command,
and what "good" looks like. Values in `<angle brackets>` come from
`references/parameters.md`.

---

## 1. Simplest: one machine, one butler, local NATS (no mesh yet)

Goal: prove the engine grounds a question before any network is involved.

```bash
# terminal 1 — engine + menu + harness (local test, no gateway)
export NEEDLE_ENGINE_DIR="$HOME/neuralos/needle"
export BUTLER_SKILL="butler.query"
python3 scripts/butler_template.py "which customer spent the most?"
```

Good output:
```json
{"ok": true, "reply": {"result": "{\"rows\": [{\"customer\": \"Helena Holý\", \"spend\": 49.62}]}",
                       "elapsed_s": 0.6, "grounding": "needle engine"}}
```

Fail output (menu gap — extend the menu, do not weaken the rule):
```json
{"ok": false, "hole": true, "error": "needle engine did not select a probe"}
```

---

## 2. Two machines over a central NATS (first real mesh)

Machines: `<edge-a>` (caller, e.g. a Mac laptop) and `<edge-b>` (butler, e.g. a
Linux server). Central NATS provided by the operator.

**On `<edge-b>`:**
```bash
export NATS_URL="<nats endpoint>"; export NATS_CREDS="<creds file>"
export GATEWAY_MESH_ID="reactorpro/<edge-b>"
export NEEDLE_ENGINE_DIR="/opt/neuralos/needle"
export LIVEAGENT_GATEWAY_TOKEN="$(openssl rand -hex 32)"
bash scripts/bootstrap_edge.sh
curl -s -H "Authorization: Bearer $LIVEAGENT_GATEWAY_TOKEN" \
     localhost:3000/api/mesh/status | jq -r .fingerprint
# -> sha256:<edge-b-fp>
```

**On `<edge-a>`:** same install; then pin each other out of band:
```bash
# both sides:
export LIVEAGENT_GATEWAY_MESH_TRUSTED_PEERS="sha256:<other-side-fp>"
# add -mesh-verify-mode=require -mesh-trust-on-first-use=false to the gateway env
```

**Verify from `<edge-a>`:**
```bash
bash scripts/dispatch.sh reactorpro/<edge-b> reactorpro/<edge-b>-butler \
     butler.query "never-seen question #1"
# -> {"ok": true, ... "elapsed_s": 4.5}
```

Good: a signed reply, wall time recorded, no `3004`. If you get `3004`, the pin
is wrong or one-sided → `references/troubleshooting.md` §2.

---

## 3. Three-edge reference production (Mac + two Windows servers)

Proven pattern this skill is distilled from. All three edges mutually pinned,
each reboot-surviving, each engine-grounded; benchmark from two origins.

| Edge | OS | Service mgr | Serves |
|---|---|---|---|
| `bionic-01` | macOS | launchd | 10 instance fleet, `neuralos.query` |
| `ec2amaz-<…>` | Windows | NSSM | `coronation.query` |
| `corp-dc1` | Windows | NSSM | `butler.query` over Postgres |

Steps: repeat §2 for each edge, then:

```bash
# on macOS edge
bash scripts/dispatch.sh reactorpro/corp-dc1 reactorpro/corp-dc1-butler \
     butler.query "show the revenue breakdown by country"
# on the Windows edge (pwsh)
pwsh -File scripts\dispatch.ps1 -Target reactorpro/corp-dc1 `
     -Butler reactorpro/corp-dc1-butler -Skill butler.query `
     -Question "which country earns the most per invoice?"
```

Record both wall times. Expect a few seconds; anything over ~15 s means the
database or the WAN hop, not the engine.

---

## 4. Durable / long work (async tasks + mailbox)

Use when the caller cannot hold a connection (serverless, mobile, batch).

```bash
# create a task (idempotency key = your taskId)
curl -s -X POST localhost:3000/api/mesh/tasks \
  -H "Authorization: Bearer $LIVEAGENT_GATEWAY_TOKEN" -H 'Content-Type: application/json' \
  -d '{"target":"reactorpro/<edge-b>","skill":"skillproxy","taskId":"nightly-1",
       "input":{"target":"reactorpro/<edge-b>-butler","skill":"butler.query",
                "args":{"question":"…"}},"async":true}'
# -> handle in ~2 s

# poll
curl -s -H "Authorization: Bearer $LIVEAGENT_GATEWAY_TOKEN" \
     "localhost:3000/api/mesh/tasks/nightly-1?refresh=true" | jq .state
```

Mailbox (fire-and-forget, no reply) when the peer is intermittently offline:
```bash
curl -s -X POST localhost:3000/api/mesh/mailbox \
  -H "Authorization: Bearer $LIVEAGENT_GATEWAY_TOKEN" -H 'Content-Type: application/json' \
  -d '{"target":"reactorpro/<edge-b>","skill":"skillproxy","input":{...}}'   # HTTP 202
```

Good: `queued → working → completed`, and the mailbox returns 202 with a note
that it cannot be answered.

---

## 5. Adding a time-series probe (worked example)

Problem: "monthly revenue" returned an honest hole because the menu had
`revenue_by_year` but no monthly probe.

1. Add the function to the bridge (read-only, one query, small digest):
```python
def revenue_by_month() -> dict:
    """Revenue and orders per month, calendar order."""
    rows = _q("""SELECT to_char(date_trunc('month', "InvoiceDate"), 'YYYY-MM') AS month,
                        COUNT(*) AS invoices,
                        ROUND(SUM("Total"), 2) AS revenue
                 FROM "Invoice" GROUP BY 1 ORDER BY 1""")
    for r in rows:
        r["revenue"] = float(r["revenue"])
    return {"months": len(rows), "rows": rows}
```
2. Append the menu entry with real triggers:
```json
{"name":"revenue_by_month",
 "description":"Revenue and orders per month, in calendar order.",
 "parameters":{"type":"object","properties":{}},
 "triggers":["revenue by month","monthly revenue","sales by month",
             "revenue trend by month","month by month revenue","monthly sales"]}
```
3. Restart the butler service; verify with three fresh phrasings; confirm the
   total reconciles with a direct query.

Good: previously-failing phrasings now ground in a few seconds. Note the
pattern — the menu gap produced a *correct* hole, not a wrong answer; that is
the design working.

---

## 6. Cross-organisation (two companies, shared exchange)

Differences from §2:
1. Both parties run **separate NATS accounts** (`ORG_A`, `ORG_B`) on the shared
   exchange; no shared credentials.
2. Fingerprints are exchanged **contractually**, not over chat.
3. Both run `-mesh-verify-mode=require -mesh-trust-on-first-use=false`.
4. Skills are **allowlisted** — expose exactly the agreed skill, never `all`.
5. Reply content is treated as remote material; a hostile peer's reply must
   never steer your agent.

```bash
# Acme calls Globex's agreed skill
curl -s -X POST localhost:3000/api/mesh/dispatch \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"target":"globex/berlin/edge-1","skill":"skillproxy","timeoutMs":120000,
       "input":{"target":"globex/berlin/edge-1-butler","skill":"butler.query",
                "args":{"question":"summarise the Q3 report"}}}'
```

---

## 7. Leaf node for an on-prem site (no direct WAN route)

Site B has no outbound route to the central server, or must keep one host as
the only WAN consumer.

```hcl
# site B: /etc/nats/nats-b.conf
port: 4222
server_name: site-b-local
jetstream { store_dir: "/var/lib/nats/jetstream" }     # site-local durability
leafnodes {
  remotes = [
    { url: "tls://<central>:7422", creds: "/etc/nats/site-b.creds",
      account: "REMOTE",
      deny_exports: [ "mesh.registry.>", "mesh.agent.>", "mesh.heartbeat.>", "mesh.task.>" ],
      deny_imports: [ "mesh.registry.>", "mesh.agent.>", "mesh.heartbeat.>", "mesh.task.>" ] }
  ]
}
```

Edges at site B connect to `nats://site-b-local:4222`; only the leaf node host
crosses the WAN. Verify: `curl http://site-b-local:8222/leafz` and
`curl http://site-b-local:8222/jsz` → `api.errors == 0`.

---

## 8. Africa multi-country hub-and-spoke playbook (the template)

Shape: **one central cloud NATS hub** (choose a region per data-residency
rules) + **one edge per site** + **leaf nodes** for on-prem sites.

### Phase 0 — intake
Collect for the hub and every site: `references/parameters.md` §A and §B.
Record the outage pattern per site (last-mile, generator windows) — it sets
timeout and mailbox policy.

### Phase 1 — stand up the hub
```bash
# on the cloud VM
sudo nats-server -c scripts/nats_central.conf -t          # validate
sudo systemctl enable --now nats                          # TLS + accounts + JetStream
curl -s localhost:8222/varz | jq '{version,jetstream}'
curl -s localhost:8222/jsz  | jq '.api.errors'            # 0
```

### Phase 2 — rollout per country, one site at a time
Repeat §2/§3/§7. After each site: benchmark that site → the hub-adjacent
reference edge, both directions, and record it. Do not roll two sites at once.

### Phase 3 — resilience
- Mailbox on for every site with a known intermittent link.
- Task retention set to the audit requirement.
- One edge per country kept as a canary for engine upgrades.

### Phase 4 — operations
- `references/operate.md` §9 incident record per site.
- Weekly: doctor on every edge; monthly: benchmark sweep with fresh phrasings.
- Keep a **fingerprint register** (site → id → fingerprint) in the ops runbook;
  it is the single most useful artifact when trust breaks.

### Typical failure patterns seen in the field
| Symptom | Usual cause in this topology |
|---|---|
| Site answers slowly only in peak hours | last-mile WAN, not the engine — check `elapsed_s` vs engine tps |
| One site cannot invoke any peer | its own fingerprint pin list missing/wrong after a rebuild |
| JetStream errors only from a leaf site | leaf account not isolated; JetStream on the wrong account |
| Answers correct but a specific ask always holes | menu gap at that site → extend its menu (§5) |

---

## 9. Offline / air-gapped edge

No WAN: run the engine, menu and gateway locally; the mesh is not required for
local Q&A. If envelopes must move at all, do it by physical media and document
the process; the single-edge pattern covers most air-gapped needs.

```bash
export NEEDLE_ENGINE_DIR=/opt/neuralos/needle
python3 scripts/butler_template.py "never-seen local question"
```

Good: identical grounding behaviour with the network off — this is the whole
point of on-device inference.