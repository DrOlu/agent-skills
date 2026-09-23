---
name: rmagent-pay
description: >
  The payments Flight Recorder — reconstruct one ATM/POS/FEP transaction
  across Postilion and Finacle from each hop's own logs (STAN/RRN), without
  modifying the switch or CBA. Pull-based, capped, STAN/RRN-grained, holes
  instead of a packet lake. Use when a withdrawal is slow, a debit-without-dispense
  dispute needs hop localization, or channel/switch/core teams cannot agree
  which segment failed. Answers delay_on: finacle-posting | postilion-ingress |
  never-reached-core. PCI mask on the device. Demo runs on fixtures with no
  bank hosts.
---

# rmagent-pay — Payment hop observatory (the default)

**Load this first.** Pull **one STAN/RRN** from Postilion and Finacle **on each
hop’s own diary** (switch journal / CBA posting log). Compare ingress vs posting.
**No lake, no SPAN by default, no PAN home.**

`rmagent-iso` is the **last-resort wire adapter** — only if `pay_attest` cannot
join both hops. Do not SPAN a bank link because this skill exists.

Use when Switching asks: *was the delay on Postilion ingress or Finacle posting?*
Not for ATM packet capture. Not APM inside the apps. Sibling of `rmagent-so`
(identity) and `rmagent-fr` (case/ticket).

## Needle tier 0 — offline extraction and drift

Alongside the Laya matrices, every skill in this family can call
**needle** — a 121M on-device model (Cactus Compute Needle, ~35 MB, no
network, no keys, ~100 MB RAM) installed once on the jump host, never on
the witnesses. It is the free tier of the judgment stack: needle extracts
and compares offline, Laya judges, the LLM reasons.

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
air-gapped estate this tier keeps working — and the judgment tier with it: Laya is offline too (pre-seed its HF-cache checkpoint on air-gapped hosts), so no matrix judgment waits for a connected session.

## Non-negotiables

- **Watch only.** No Postilion/Finacle config changes.
- **Allowlisted questions only.**
- **Capped answers (32 KB).** Floods become holes.
- **Ticket is the grain** (`RRN-…` / `STAN-…`). Context travels; ISO bodies do not.
- **PCI on the device.** PAN masked (first 6 + last 4). PIN / Track2 / CVV stripped.
- **Empty is not clean.** `pay_attest.blind` first — same standing rule as so.
- **Your estate only.** Inventory hops you administer.
- **No tight retry** on a silent hop.

## The questions

| Question | Hop | Returns | Must NOT return |
|---|---|---|---|
| `pay_attest` | any | artifact exists, has STAN/RRN, oldest ts, `blind` | log dump |
| `switch_txn` | Postilion (fep) | rows for **this ticket**: in_ts, out_ts, RC, masked PAN | journal file, PIN |
| `core_auth` | Finacle (cba) | rows: recv_ts, post_ts, RC | CBA extract |
| `pay_sketch` | any | counts by RC / timeouts | every txn |
| `hop_delta` | jump host | T_ingress vs T_core, `delay_on` | re-pull of logs |

`hop_delta` is **local** (`lib.hop_delta(switch, core)`). It never knocks.

Honest `delay_on` values: `finacle-posting` | `postilion-ingress` | `never-reached-core` | `unknown`.

Honest termination: `origin` | `blind-witness` | `no-signal` | `no-signal-core` | `core-hole`.

## Doors

| door | When |
|---|---|
| `fixture` | Demo JSONL in `examples/fixtures/` — **no network**. Skill is usable today. |
| `psrp` / `winrm` | Windows Postilion — `questions/windows/*.ps1` |
| `ssh` | Linux/AIX Finacle — `questions/linux/*.sh` |

## Run (fixture — works now)

```bash
cd ~/.agents/skills/rmagent-pay/scripts
python3 test_pay.py
python3 hunt.py --inventory ../examples/estate.yaml --ticket RRN-000000123456 --since 24
```

Expected hunt: `delay_on=finacle-posting` for RRN `000000123456` (core ~7850 ms, ingress ~250 ms).

Blind hop `blind-hop` → `pay_attest.blind=true`; `switch_txn` is a **hole**, not “switch was fine”.

## Production

1. Copy `examples/estate.production.yaml`, set addresses and **real artifact paths**.
2. Creds: `RMAgent_POSTILION-1_PASS` or `~/.rmagent/creds.json` (mode 600). Never in YAML.
3. Prove one RRN exists on **both** hops (Switching sample). If not, the skill reports `blind` / `no-signal` — it does not start sniffing.
4. `python3 hunt.py --inventory estate.production.yaml --ticket RRN-<the rrn>`

Windows payloads grep `stan=` / `rrn=` style lines. If Postilion journals are binary or different, **adapt the regex in `switch_txn.ps1`** — do not widen to copy the whole file.

## Combine with so / at / fr

```
case.py open --ticket RRN-000000123456
hunt.py (this skill)     → hop times
so attest/edges          → who walked / can the Windows box see 4624
at appslow               → was the Windows process sick (not ISO hops)
trace.py --ticket RRN-…  → one case file
```

## Packet sniff

Only if `pay_attest` says both hops **cannot** join. Then SPAN at Segment C is a **last-resort payload**, mask on the sensor, cap JSON, no pcap warehouse. Not shipped in v1. Any SPAN/ingest sensor is an estate change: **MOP-level**, dry-run default, tested **teardown**. Questions never start a capture.

WinRM payloads are compact and must respect the ~8191-char UTF-16LE base64 command budget (same rule as the other rmagent Windows skills; a budget test is part of validation).

## Laya-assisted hop localization

The recurring question — which segment failed for this STAN/RRN — can be
answered by a fast, typed decision model (Laya, via the `use-laya` skill) over
the joined hop diaries before a human reads them. One matrix lives in
`decisions/`:

- `hop_localize.json` — genuine_failure (noul) / failed_segment (choice:
  channel, switch, core, or unclear — escalate) / severity (score).

```bash
scripts/laya_decide.py hop_localize --state-file txn.json
```

Policy: confidence below 0.5 is flagged ESCALATE — unclear or low-confidence
segment verdicts go to the LLM or the three teams, never auto-assigned. Pulls
stay read-only and STAN/RRN-grained.

## Scripts

| File | Role |
|---|---|
| `scripts/lib.py` | `ask()`, PCI scrub, fixture/psrp/winrm/ssh, `hop_delta` |
| `scripts/hunt.py` | attest → txn → delta |
| `scripts/test_pay.py` | fixture tests |
| `scripts/questions/windows/*.ps1` | live Postilion (Windows) |
| `scripts/questions/linux/*.sh` | live Finacle (Linux/AIX) |
| `examples/estate.yaml` | fixture inventory |
| `examples/fixtures/*.jsonl` | sample switch/core/blind rows |
