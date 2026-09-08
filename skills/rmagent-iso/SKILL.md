---
name: rmagent-iso
description: The payments Flight Recorder — reconstruct one ATM/POS/FEP transaction across Postilion and Finacle from passive ISO 8583 taps, without modifying the switch or CBA. Pull-based, capped, STAN/RRN-grained, holes instead of a packet lake. Use when a withdrawal is slow, a debit-without-dispense dispute needs hop localization, or channel/switch/core teams cannot agree which segment failed.
---

# rmagent-iso — The payments Flight Recorder

Follow **one card transaction** (STAN + RRN) across the ATM/POS → acquirer →
Postilion FEP → Finacle CBA path **without a span warehouse and without
changing Postilion or Finacle**.

The ISO sibling of `rmagent-fr` (ticket-led Flight Recorder) and `rmagent-at`
(Windows ETW ring). Same constitution: **pull-only, named questions, capped
answers, holes instead of dumps.** Different grain, different sensor.

> Push tools answer the questions you knew to ask. This answers: *where did
> STAN 123456 wait?*

## When to use

- Channel / switch / core cannot agree where a delay sat.
- Debit-without-dispense / timeout disputes.
- Per-hop latency vs a baseline, **without** instrumenting the apps.
- You have (or can get) SPAN/ERSPAN on FEP ingress and the CBA interface.

**Do not use** for identity-led compromise (`rmagent-so` / `rmagent-linux`) or
Windows process tracing (`rmagent-at`). Those are the host tape beside this.

## Non-negotiables

- **Watch only.** No Postilion/Finacle config changes.
- **Allowlisted questions only.** Ingest is a door; hunt never runs tshark.
- **32 KB cap.** Oversized → hole.
- **Circular decoded JSONL rings**, not PCAP lakes.
- **PAN never stored.** Mask `first6******last4` before the ring. PAN is not a
  join key. The tap host is still CDE-adjacent.
- **A hole is an answer.** Segment A and D-internals default to holes.
- **Never trust “no findings” until `txnattest.blind_check=ok`.**

## Grain

```
iso: stan=123456; rrn=123456789012
```

Join `(STAN, RRN)` then TID. Never PAN. A dispute ticket is an alias via
`rmagent-fr` `--ticket`.

## Sensor (two rings are enough)

| Segment | Tap | Default |
|---|---|---|
| A Terminal ↔ acquirer | ATM EJ (optional) | hole unless EJ ring has rows |
| B Acquirer ↔ Postilion | `tap-fep-acq` | required |
| C Postilion ↔ Finacle | `tap-fep-cba` | required |
| D Finacle internal | not on the wire | **inferred** `C_resp − C_req` |
| E Return to terminal | same taps | terminal still a hole |

## Questions

| Question | Returns | Must NOT |
|---|---|---|
| txnattest | tap alive, n, bytes, blind_check | the PCAP |
| txntrace | one STAN/RRN (MTI times RC amount TID hops) | every message |
| txnhops | per-segment ms; A/E hole if unseen | a stream |
| txnslow | total ≥ threshold, slowest hop first | every txn |
| txnfail | timeout / missing 0210 / RC / DWD **candidates** | raw dumps |
| txnbaseline | p50/p95/p99; **n<30 → hole** | a warehouse |

## Hop math (on-us 0200/0210)

```
B_req  = t_cba_req  − t_acq_req
D      = t_cba_resp − t_cba_req     (inferred)
B_resp = t_acq_resp − t_cba_resp
total  = t_acq_resp − t_acq_req
```

Timeout = 0200 seen, no 0210. `last_seen` is the localization.

DWD = RC=00 **and** EJ ring is sighted **and** this STAN has no EJ completion.
Empty EJ ring → hole, not 40 false DWD hits.

## Setup

```bash
cd /Users/olu/.agents/skills/rmagent-iso/scripts
python3 generate_fixture.py --out ../examples/rings
python3 hunt.py attest --rings ../examples/rings
python3 test_iso.py
```

SPAN/ring setup is **MOP**: dry-run the collector, `--apply` to start ingest,
tested **teardown** (stop tshark/ingest, leave rings to rotate — do not keep
PCAPs). Hunt never starts a capture.

Live ingest (sensor box, not the question path):

```bash
tshark -i eth1 -l -T fields -e frame.time_epoch -e ip.src -e tcp.srcport \
       -e ip.dst -e tcp.dstport -e tcp.payload \
  | python3 ingest.py --tap tap-fep-cba --ring /var/rmagent-iso/rings/tap-fep-cba.jsonl
```

SPAN design is `netops`. Worked CLI output: `EXAMPLES.md`.

## Scripts

| Script | Job |
|---|---|
| `scripts/iso.py` | grain, PAN mask, 32 KB cap |
| `scripts/decode.py` | ASCII ISO 8583 pack/unpack; mask on unpack_record |
| `scripts/ring.py` | circular JSONL |
| `scripts/txn.py` | reconstruct + hop math |
| `scripts/lib.py` | allowlisted `ask()` |
| `scripts/hunt.py` | CLI |
| `scripts/ingest.py` | tshark-hex → ring |
| `scripts/generate_fixture.py` | 40 healthy + 3 incidents |
| `scripts/test_iso.py` | decoder, hops, DWD, baseline, no-PAN |

## Relationship

| Skill | Role |
|---|---|
| rmagent-fr | case, STC, ticket join, OTel of the *investigation* |
| rmagent-at | Windows Postilion host (process/TCP/`appslow`) |
| rmagent-so | is the FEP box sighted / compromised? |
| rmagent-linux | is Finacle up / load / new units? |
| netops | plant the SPAN |

**so/linux/at = were the machines lying or dying. This skill = where the 0200 waited.**

## Will not do

- Modify Postilion or Finacle.
- Store PAN / track2 / PIN.
- Keep PCAPs.
- See Segment A without an EJ/terminal tap.
- Claim Finacle SQL waits (D is interface time).
- Unbounded ML. Baseline is percentiles with n ≥ 30.

## Fidelity gaps

- No terminal tap ⇒ no dispense **proof**.
- STAN recycles — always STAN+RRN.
- TLS on FEP–CBA without a broker you administer ⇒ Segment C is a hole. Do not MITM a bank link.
- Busy switch fills a 64 MiB ring in minutes-to-hours. Size it or accept retention-boundary.
