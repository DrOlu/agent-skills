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

# rmagent-pay — Payment hop observatory

Pull **one STAN/RRN** from Postilion and Finacle **on each hop’s own artifact**.
Compare ingress vs posting. **No lake, no SPAN by default, no PAN home.**

Use when Switching asks: *was the delay on Postilion ingress or Finacle posting?*
Not for ATM packet capture. Not APM inside the apps. Sibling of `rmagent-so`
(identity) and `rmagent-fr` (case/ticket).

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

Only if `pay_attest` says both hops **cannot** join. Then SPAN at Segment C is a **last-resort payload**, mask on the sensor, cap JSON, no pcap warehouse. Not shipped in v1.

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
