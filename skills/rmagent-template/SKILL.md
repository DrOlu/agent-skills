---
name: rmagent-template
description: >
  Lake-less, on-device RMAgent skill constitution and factory. Use when creating
  a new rmagent-* skill for any IT-operations plane (secops, devops, netops,
  sysops, datacenterops, mlops, aiops, payments, agentops, app tracing) — or
  when auditing an existing one against the no-lake ethos. Clone this, pick a
  grain and a sensor, write allowlisted questions, keep holes honest. Bundled
  with RTerm as the reference for every future rmagent skill.
---

# rmagent-template — the lake-less skill factory

This is **not** a witness. It is the **constitution + scaffold** every
`rmagent-*` skill is cloned from.

Use it when you are about to write a new skill that:

- watches something on boxes (or wires, or rings) you administer
- must **not** become a SIEM / PCAP lake / span warehouse
- must answer a **named question** on demand, capped, with holes

Do **not** use it as a runtime hunt. Load `rmagent-so`, `rmagent-iso`,
`rmagent-at`, … for that. This file is the pattern those skills already share.

> Push tools answer the questions you knew to ask, after the log rotated.
> An rmagent skill answers the question you just thought of — by knocking
> on the device that still has the ring.

---

## 1. The one-sentence test

Before you name the skill, finish this sentence:

> Follow **one ________** across **________** without a ________ warehouse,
> by asking **________** on devices we administer.

| Existing skill | Follow one … | across … | without a … warehouse | by asking … |
|---|---|---|---|---|
| `rmagent-so` | principal (Admin/SYSTEM) | Windows estate | Security.evtx | attest/sketch/edges/… |
| `rmagent-linux` | principal (root) | Linux/macOS hosts | journal export | attest/sketch/edges/… |
| `rmagent-fr` | work id / ticket | hops of an investigation | span lake | case/trace/trajectory |
| `rmagent-at` | application request | Windows ETW rings | ETL dump | apptrace/appslow/… |
| `rmagent-ao` | agent process | disk artifacts + LLM APIs | transcript dump | agents/agenttrace/… |
| `rmagent-iso` | STAN+RRN | ISO taps Postilion↔Finacle | PCAP lake | txntrace/txnhops/… |
| `rmagent-redteam` | drill artifact | WS1/WS2 | (stages then scores so) | stage/score/clean |

If you cannot fill the blanks, you do not have an rmagent skill yet. You have
a dashboard idea.

---

## 2. Constitution (non-negotiable)

Copy this block into every new `SKILL.md`. Delete nothing. Annotate domain
exceptions **below** it, never by editing it away.

1. **Watch only (Phase 0).** No `actuate` in the question set. Isolate /
   disable / restart / `iptables` / `usermod` live in `rmagent-actuate` (or
   the platform’s MOP), dual-controlled, journaled, reversible.
2. **Allowlisted questions only.** `ask()` refuses unknown names and refuses
   `actuate`. Never an arbitrary remote shell as the product.
3. **Capped answers (32 KB default).** Oversized → **hole**, not a truncated
   lie and not a lake. Prefer a **signal-aware cap** (keep critical rows,
   shed low-signal) over a bigger cap.
4. **A hole is an answer.** Silent box, blind witness, retention-boundary,
   unsupported field, TLS you cannot terminate, box you do not administer —
   same JSON shape as a hop: `{asked, empty, why}`.
5. **Never trust “no findings” until the witness can see.** Every plane needs
   an `*attest` with `blind_check`. Empty + blind = false negative, the worst
   failure mode.
6. **On-device rings, not shipped lakes.** Data stays where it was written
   (ETW, journald, circular JSONL, Sysmon). The jump host stores **cases**
   (megabytes: path, holes, trajectory), not event exports.
7. **Context propagates; data does not.** STC / grain ids travel. Event bodies
   do not. Depth ≤ 8, fan-out ≤ 3 — an unconstrained hunter is a worm.
8. **Credentials never in the inventory, skill, or case.** Env /
   `~/.rmagent/creds.json` (mode 600) / vault. Never print them.
9. **Your estate only.** Partner, scheme, SaaS you do not tenant, phone, NIBSS
   — hole, not a witness.
10. **No tight retry on a silent host.** Cooldown. Two missed attests = Critical.
11. **Secrets, PAN, payloads, prompt text — never stored unless the grain
    requires a *masked* form.** Env **names** not values. PAN `first6******last4`.
    Transcripts capped excerpts. PIN blocks never.
12. **Reversible persistent change.** If you create a ring (AutoLogger, SPAN
    session, analytic log), it is **MOP**, dry-run default, `--apply` required,
    `--teardown` exists and is tested.
13. **Honest fidelity gaps, documented in the skill.** Do not silently degrade
    Sysmon → kernel burst and still call it Sysmon. Separate question or a hole.
14. **Keep the existing sensor.** EDR, auditd, Postilion, Finacle, Ollama stay.
    This is the knock, not a rip-and-replace.

**The lake test:** if a new operator would `scp` home a file that grows without
bound, you have failed. Circular overwrite, case prune, 32 KB pull.

---

## 3. Anatomy of a skill

Every rmagent skill is five nouns.

```
GRAIN  →  SENSOR  →  DOOR  →  QUESTIONS  →  CASE
  |         |         |           |           |
  STAN    ring/ETW   ssh/winrm   ask()      fr case
  ticket  journal    local file  attest     trajectory
  PID     SPAN       tshark-in   hops       holes.jsonl
  principal
```

### 3.1 Grain

The **unit you follow**. One string you can put on a case and query back.

| Plane | Grain | Not a grain |
|---|---|---|
| SecOps | `(host, principal, logonid)` | source IP (NAT lies) |
| Reliability | ticket / work id | “the outage” |
| App / APM | request / trace_id | “the service” |
| Payments | `(STAN, RRN)` [+ TID] | PAN |
| AgentOps | `(host, agent, session)` | “AI” |
| NetOps | `(flow 5-tuple, window)` or `(circuit_id)` | “the WAN” |
| MLOps | `(job_id, model, run)` | “the GPU box” |
| DCOps | `(asset_tag, PDU/circuit)` | “the row” |

Rules:

- Grain fields **reject** `;` and `=` if you encode STC-style (injection).
- Recyclable ids (STAN, PID, LogonId) **always** pair with a window or a
  second key (RRN, start time, ProcessGuid).
- The grain is **not** the ticket. The ticket is an alias (`rmagent-fr`).

### 3.2 Sensor

Where the bits already are. Prefer **resident circular** over “start capture.”

| Sensor class | Examples | Lake risk |
|---|---|---|
| OS diary | Security log, journald, auditd | export = lake |
| Kernel ring | ETW AutoLogger, kprobes (not default) | grow-forever file |
| App ring | Sysmon, HTTP.sys, .NET EventSource | ETL copy home |
| Wire ring | SPAN → decoded JSONL (not pcap) | pcap-on-disk |
| Disk artifacts | agent transcripts, unit files | full transcript |
| Local API | Ollama `/api/ps`, `kubectl get` (capped) | cluster dump |
| Counter | `flowstats`, SNMP ifInOctets | 1-min poll lake |

**Decoder lives at ingest, mask at the boundary.** `rmagent-iso` unpacks ISO
in memory, writes PAN-masked JSONL. Never write the sensitive form.

### 3.3 Door

How the jump host knocks. One skill may have many doors; `ask()` is door-aware.

| Door | Typical OS | Notes |
|---|---|---|
| `winrm` / `psrp` | Windows | PSRP if payload > ~8191 UTF-16LE chars |
| `ssh` | Linux/macOS/network-os | key auth; passwordless sudo **only** for named reads |
| `ring` | local file | questions never call `tshark`; ingest is a separate process |
| `http-local` | model servers, kube | allowlisted paths only |
| `snmp` | DC / net | GET/WALK allowlist, not full table dumps |

Doors you **do not** add as the product: unrestricted `exec`, RDP, serial as
god-shell, MITM of a TLS link you do not terminate as a broker you own.

### 3.4 Questions

A **closed set**. Name them after the English question, not the vendor API.

The canonical six (rename per domain, keep the *jobs*):

| Job | Typical name | Returns | Must NOT |
|---|---|---|---|
| Alive + sighted? | `attest` | up, clock, blind_check, oldest event | full log |
| Anything odd? | `sketch` | deltas in window (new X, failed Y) | raw lists |
| Who/what did they touch? | `edges` | capped join-keyed hops | whole table |
| What changed? | `explain` | identity/config/deploy in window | whole journal |
| Follow one grain | `trace` / `*trace` | one reconstructed journey | every event |
| Localize / slow | `hops` / `*slow` | per-hop ms vs baseline | continuous stream |
| Failures | `*fail` | timeouts, mismatches, candidates | dumps |
| Normal | `*baseline` | p50/p95/p99, **n ≥ 30 or hole** | warehouse |
| Persistence / drift | `attackmap` / `*drift` | state vs last baseline | filesystem walk |
| Deep (optional, time-boxed) | `*deep` | 10s burst, nothing persists | a new agent |

Add domain questions **only** when a job above cannot express them.
`pslogs`, `txnfail`, `agentmodels` earned their names. `dump_everything` did not.

### 3.5 Case

Reuse `rmagent-fr` when the human cares about **one ticket**:

```
case.py open --title "…" --ticket GRAIN-OR-TICKET --principal <grain-type>
hunt.py … --case-dir <that>
trace.py --ticket …
```

The ISO/app/agent skill **answers**. fr **records the investigation**.
Do not fork case/trajectory/STC unless you must (injection rules stay).

---

## 4. Repository layout (clone this)

```
rmagent-<domain>/
  SKILL.md                 # constitution + this domain's grain/sensor/questions
  SAFETY.md                # estate, confirm flags, what we will not do
  estate.example.yaml      # no secrets
  EXAMPLES.md              # worked questions with expected JSON shape
  scripts/
    lib.py                 # ALLOWED, ask(), cap, holes, door, creds
    hunt.py                # CLI: question names only
    case.py                # optional; prefer rmagent-fr
    stc.py                 # optional; copy from fr (injection-hardened)
    test_<domain>.py       # pure-logic; fixtures; no live estate required
    test_budget.py         # WinRM 8191 if you have .ps1
    questions/
      windows/*.ps1        # compact, $Track $SinceHours $Limit
      linux/*.sh           # one bash -c, one JSON
    generate_fixture.py    # demo rings/answers
    ingest.py              # door only (tshark/SPAN) — not a question
    teardown.py            # if you created a ring
  examples/rings|answers/  # fixtures committed, PAN/secrets masked
```

`scripts/new_skill.py` in **this** template repo stamps that tree.

---

## 5. How to mint a skill (procedure)

```bash
python3 ~/.agents/skills/rmagent-template/scripts/new_skill.py \
  --name rmagent-net \
  --title "Circuit Flight Recorder" \
  --grain "circuit_id + time window" \
  --sensor "SNMP counters + syslog ring on the collector" \
  --plane netops \
  --out ~/.agents/skills/rmagent-net
```

Then, in order (do not skip):

1. Fill the **one-sentence test** in the new `SKILL.md`.
2. Write the **question table** (job / returns / must-not) before any payload.
3. Implement `ask()` allowlist + cap + hole in `lib.py`.
4. One **attest** with `blind_check` — prove sightedness first.
5. Fixtures + `test_*.py` that never need the live estate.
6. `check_constitution.py` against the new skill (must exit 0).
7. One **worked example** with a grain that localizes a hop.
8. Document fidelity gaps (TLS, no terminal tap, n<30, ring overwrite).
9. Only then: live door against boxes you administer.

**Red team for a watch skill** is optional (`rmagent-redteam` pattern): stage
benign prefixed artifacts, score detection, clean, `--confirm`.

---

## 6. Domain cookbooks

Each row is a *starter* grain/sensor/question set. Specialize; do not copy
all questions into one mega-skill. **One grain per skill.**

### 6.1 SecOps — identity-led (`rmagent-so` / `windows` / `linux`)

- Grain: principal + LogonId. Sensor: Security log / journald / Sysmon.
- Questions: attest, sketch, edges, explain, netedges, pslogs, attackmap,
  canary, drift. Correlate **across** witnesses (lateral-hop, shared-logonid).
- Must not: evtx copy, YARA filesystem, memory scan, disable EDR.
- Blind: auditpol / auditd rules. WS2 Failure-only Logon = fake clean.

### 6.2 Reliability / incident — ticket-led (`rmagent-fr`)

- Grain: ticket. Sensor: none of its own — joins other skills’ answers.
- Scripts: STC, trajectory DAG, hop index, causal blast radius, OTel emit.
- Honest limit: **business must stamp the ticket** OR another skill (iso/at)
  supplies the grain. fr does not invent payment events.

### 6.3 App / sysops tracing — Windows ETW (`rmagent-at`)

- Grain: request-ish (time + PID + URL if present). Sensor: AutoLogger rings.
- Setup is **MOP**. Questions: apptrace, appslow, apperrors, appnet, appproc.
- Honest: Kernel-Network may be empty on Server 2022; fallback is a **named**
  hole or Sysmon EID3, not a fake quiet box.

### 6.4 AgentOps (`rmagent-ao`)

- Grain: `(host, agent, session)`. Sensor: process + transcripts + local APIs.
- Tiers 1–4; Tier 4 is a hole. Never read API key **values**.

### 6.5 Payments / channel (`rmagent-iso`)

- Grain: STAN+RRN. Sensor: SPAN → decoded circular JSONL.
- Questions: txnattest, txntrace, txnhops, txnslow, txnfail, txnbaseline.
- PAN masked. Segment A/D often holes. DWD is a **candidate** if EJ sighted.

### 6.6 NetOps

- Grain: `(src, dst, proto, sport, dport)` in a window, or `circuit_id` /
  BGP neighbor. Sensor: interface counters, syslog/BMP, ERSPAN **decoded**
  to flow records (not pcap keep).
- Questions (starter): `netattest` (ifUp, error_delta, ntp), `netedges`
  (top talkers capped), `netfail` (flaps, CRC, BGP down), `nethops`
  (traceroute-like from existing telemetry — do not blast 65k pings),
  `netbaseline` (error/discards p95, n≥30).
- Must not: full `tcpdump -w`, MAC table dump of the campus, attacking
  `ping -f`. SPAN design may live in `netops` skill; rmagent **consumes rings**.

### 6.7 DevOps / platform

- Grain: `(deploy_id | git_sha | rollout)`. Sensor: kube events, systemd
  units, CI logs **on the runner you administer**.
- Questions: `platattest` (api-server reachable, node NotReady count),
  `platsketch` (CrashLoop, image-pull-backoff, new ClusterRoleBinding),
  `plattrace` (one ReplicaSet’s events), `platfail` (failed jobs).
- Must not: `kubectl logs --all-containers --all-namespaces` home.
  Cap pod names. Secrets in env = names only.

### 6.8 SysOps / datacenter

- Grain: `(hostname)` or `(asset_tag, sensor)`. Sensor: IPMI/Redfish
  **allowlisted GETs**, SMART, PDU SNMP.
- Questions: `dcatest` (power, inlet temp, PSU redundancy), `dcfail`
  (predictive fail, UID, lost redundancy), `dcbaseline` (temp p95).
- Must not: firmware flash, chassis locate as a toy, full SEL export lake.

### 6.9 MLOps

- Grain: `(job_id, model_name, revision)`. Sensor: scheduler API, GPU
  counters (`nvidia-smi -q` parsed, capped), artifact mtimes.
- Questions: `mlattest` (GPU visible, driver), `mlslow` (step time vs
  baseline), `mlfail` (OOM, NaN loss **if already in the job log**),
  `mldrift` (new models on disk).
- Must not: weight files, dataset copies, wandb dumps.

### 6.10 AIOps (the reasoning layer — do not confuse with a lake)

AIOps in this ethos is **`thinker.py` over census history**, not a training
set of every txn.

- Inputs: attest time series, hop latency percentiles, blind_count, holes.
- Outputs: cliff, silence, acceleration, z-score with **n ≥ 30** else hole.
- Must not: ship raw events to a model vendor. Must not page on 20 samples.

`rmagent-fr` thinker / `rmagent-iso` txnbaseline are the reference.

### 6.11 Purple team (`rmagent-redteam`)

- Not a watch plane. Stages **prefixed, reversible, `--confirm`** artifacts,
  scores the watch skill, cleans. Never against boxes you do not administer.

---

## 7. `ask()` contract

Every `lib.py` exposes:

```python
ALLOWED = {"attest", "sketch", ...}   # closed
MAX_PULL_BYTES = 32 * 1024
WALK_DEPTH = 8
WALK_FANOUT = 3
COOLDOWN_SEC = 300

def ask(row, question: str, **params) -> dict:
    """row = inventory witness. Returns JSON-ready dict. Never raises secrets."""
```

Return shapes:

```json
{"ok": true, "witness": "ws1", "question": "attest", "blind_check": "ok", "...": "..."}
{"hole": true, "asked": "edges", "empty": true, "why": "witness-blind"}
{"hole": true, "reason": "not-allowlisted", "question": "actuate"}
{"hole": true, "reason": "capped", "bytes": 90000, "limit": 32768}
```

Unparseable payload → hole, not `ok` with a raw blob.

---

## 8. Inventory shape

```yaml
witnesses:
  - id: unique-short
    name: human
    plane: endpoint | network | payments | agent | dc | ml
    os: windows | linux | darwin | iosxe | other
    door: winrm | ssh | ring | http-local | snmp
    address: 10.0.0.1          # never a secret
    user: deploy               # never a password
    skills: [attest, sketch]   # subset of ALLOWED
    track: [root]              # principals or grain types
    optional: false
policy:
  max_pull_bytes: 32768
  baseline_min_n: 30
  actuate: false
```

Credentials: `RMAgent_<ID>_USER` / `_PASS` or vault. **Never** this file.

---

## 9. Anti-patterns (reject at review)

| Smell | Why it fails |
|---|---|
| “We’ll just keep 7 days of pcap” | lake |
| Question named `run` / `exec` / `query` | god-shell |
| Silent fallback with worse fidelity | liar |
| PAN / key / prompt in `case.json` | constitution 11 |
| Baseline on n=8 called “normal” | noise as science |
| Tight retry on WinRM timeout | lockout |
| Skill that is “all of IT ops” | no grain |
| MITM production TLS “to see ISO” | not your broker |
| Copy-paste so.ps1 into netops | wrong grain |
| Dashboard of every txn in real time | warehouse with extra steps |
| Install an agent “just this once” | you are now the EDR |

---

## 10. Review checklist (`check_constitution.py`)

The linter looks for:

- [ ] `SKILL.md` has the constitution numbered list (or `# Constitution`)
- [ ] `ask(` / `ALLOWED` in `scripts/lib.py`
- [ ] `"actuate"` rejected (test or explicit)
- [ ] `MAX_PULL_BYTES` or `32 * 1024`
- [ ] `hole` string appears in lib or questions
- [ ] `blind` or `attest` question exists
- [ ] no `password:` in yaml examples
- [ ] `test_*.py` exists
- [ ] `EXAMPLES.md` or `examples/` exists
- [ ] if `.ps1`: budget test or a comment about 8191
- [ ] if ingest/SPAN/AutoLogger: `teardown` or MOP wording in SKILL.md

Exit 0 = shippable as a *template clone*. Live-validation is still on you.

---

## 11. Worked clone (30 minutes) — `rmagent-net` sketch

One-sentence: *Follow one circuit_id across PE routers without a NetFlow
warehouse, by asking netattest/netfail/netbaseline on boxes we administer.*

Questions:

| Q | Returns | Must not |
|---|---|---|
| netattest | ifOperStatus, crc_delta, ntp, blind (SNMP timeout) | full IF-MIB |
| netfail | flaps in window, BGP neighbor down (from syslog ring) | debug log |
| netbaseline | p95 error-delta; n<30 hole | 95th of a lake |

Sensor: already-running syslog JSONL on the collector (circular 64 MiB) +
SNMP GET of 6 OIDs. No `tcpdump`.

That is a skill. “Also add DPI and a year of pcap” is not.

---

## 12. Relationship to the family

| Skill | You clone from here when … |
|---|---|
| so / linux / windows | identity plane |
| fr | you need the case/ticket tape |
| at | Windows app ETW |
| ao | LLM agents on a box |
| iso | ISO 8583 / FEP |
| redteam | proving a watch skill |
| **template (this)** | **any new plane** |

RTerm bundles this skill so an agent that is asked “write rmagent-foo”
loads **this** first, not a SIEM tutorial.

---

## 13. Scripts in this directory

| Script | Job |
|---|---|
| `scripts/new_skill.py` | stamp a new skill tree from templates |
| `scripts/check_constitution.py` | lint a skill dir |
| `scripts/lib_skeleton.py` | copy-me `ask()` / cap / hole |
| `templates/SKILL.md.tmpl` | SKILL stub with constitution |
| `templates/estate.example.yaml` | inventory stub |
| `examples/question-table.md` | blank question table |
| `CONSTITUTION.md` | printable 14 rules |
| `COOKBOOK.md` | domain grain/sensor map (expanded) |

## Supporting files

Skill directory: `/Users/olu/.agents/skills/rmagent-template`
