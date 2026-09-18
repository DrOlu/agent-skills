---
name: rmagent-iso
description: Last-resort payments wire adapter — reconstruct one STAN/RRN from passive ISO 8583 SPAN rings ONLY after rmagent-pay cannot join hop diaries. Circular decoded JSONL, not a PCAP lake. PAN masked. Hunt never runs tshark.
---

# rmagent-iso — last-resort SPAN adapter (not the default)

**Default payments skill is `rmagent-pay`.** Load iso only after `pay_attest`
cannot join both hops. Same grain (STAN+RRN). Different sensor: decoded
circular JSONL from a SPAN you already own — **not** a PCAP lake, **not**
MITM of FEP–CBA TLS.

Follow **one card transaction** (STAN + RRN) across acquirer → Postilion →
Finacle **without changing the switch or CBA**. Hunt never runs tshark.
Ingest is a separate MOP door with teardown.

> Push tools answer the questions you knew to ask. This answers: *where did
> STAN 123456 wait on the wire?* after the diaries could not.

## When to use

- `pay_attest` is blind on a hop you administer **and** you already have SPAN.
- Debit-without-dispense **candidates** when an EJ ring is sighted.
- Per-hop wire latency vs baseline (`n≥30` or hole).

**Do not use** as the first payments knock. Do not use for identity (`rmagent-so`)
or Windows process tracing (`rmagent-at`).

## Needle tier 0 — offline extraction and drift

Alongside the Jev matrices, every skill in this family can call
**needle** — a 121M on-device model (Cactus Compute Needle, ~35 MB, no
network, no keys, ~100 MB RAM) installed once on the jump host, never on
the witnesses. It is the free tier of the judgment stack: needle extracts
and compares offline, Jev judges, the LLM reasons.

Two scripts ship in `scripts/`:

- `needle_extract.py` — typed field extraction from a witness fragment
  (`count`, `source_ip`, …). Rigid tokens (numbers, IPs) are reliable;
  semantic fields are not, so the wrapper validates what it can (`:ip`,
  `:int`) and blanks anything it cannot trust — never a guess.
  ```bash
  echo "<attest answer>" | scripts/needle_extract.py user count:int source_ip:ip --json
  ```
- `needle_drift.py` — baseline-drift detection via needle's 3072-dim
  embeddings: record what an answer normally looks like, score today's
  answer against it (similar / drifted / changed, thresholds calibrated
  empirically). Separates shape and topic, not field values — value drift
  stays the job of the field rules and correlate joins.
  ```bash
  echo "<routine answer>" | scripts/needle_drift.py record <host>-<question>
  echo "<today's answer>" | scripts/needle_drift.py score <host>-<question>
  ```

The engine runs in-process on the jump host (the wrapper finds a Python
with `cactus-needle` — set `NEEDLE_PYTHON` if it lives elsewhere). No port
is opened, nothing is installed on any witness, and the baselines are
kilobyte holes under `~/.rmagent/needle-drift/`, not a lake. On an
air-gapped estate this tier keeps working when the Jev tier cannot reach
OpenRouter — matrix judgments defer to the next connected session rather
than being guessed.

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

## Jev-assisted message triage

Decoded SPAN-ring excerpts for a STAN/RRN can be scored by a fast, typed
decision model (Jev, via the `use-jev` skill). One matrix lives in
`decisions/`:

- `message_triage.json` — genuine_failure (noul) / failure_kind (choice:
  issuer decline, switch timeout, channel error, missing reversal, clean flow,
  or escalate to the LLM) / severity (score).

```bash
scripts/jev_decide.py message_triage --state-file span.json
```

Policy: confidence below 0.5 is flagged ESCALATE. Verdicts are advisory; the
rings stay passive, decoded JSONL, PAN-masked, and this stays the last-resort
adapter after rmagent-pay.

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
