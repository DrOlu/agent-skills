---
name: rmagent-so
description: >
  The Security Observatory — the witness-question half of the RMAgent security
  observatory. Pull-based, allowlisted named questions over WinRM :5985
  tracking Administrator and SYSTEM: attest (with blind_check — can this
  witness actually see?), sketch, edges, explain, netedges, pslogs, kernring,
  attackmap, flowstats, deepwindow. Cross-witness correlation joins the answers
  (cross-host-account, lateral-hop, shared-logonid); baseline drift flags new
  admins and witness blindness as critical. Use for identity-led compromise,
  lateral movement, living-off-the-land, silent hosts, and honest root-cause on
  Windows boxes you administer. Watch-only, capped at 32 KB, holes instead of
  dumps — no lake, no agent install.
---

# rmagent-so — The Security Observatory

The witness-question half of the RMAgent security observatory: **ask a small
set of allowlisted named questions, track the identities that matter, and
never copy the log home.**

This is the Security Observatory engine, split out of `rmagent-windows` so the
question half can be reasoned about (and loaded) on its own. `rmagent-windows`
remains the complete, runnable skill; `rmagent-fr` is the Flight Recorder
(tracing) half. The three skills share one constitution.

## Non-negotiables

- **Watch only.** No `actuate`. No `systemctl stop`, no `usermod`, no firewall edits.
- **Allowlisted questions only** — never an arbitrary shell.
- **Capped answers** (32 KB) — oversized pulls become holes, never a lake.
- **Your estate only.** No box you do not administer.
- **No tight retry** on a silent host.
- **Credentials never in the inventory file** — env or `~/.rmagent/creds.json`.
- **Never trust a "no findings" result until you have confirmed the witness can see.**

## The questions

| Question | Returns | Must NOT return |
|---|---|---|
| `attest` | alive, last boot, admin failed/ok logons, local admin count, SYSTEM conns, **raw_4624_24h + blind_check + blind_count** | a full Security log dump |
| `sketch` | admin failed in window, new local admins 24h, running priv services, new services/tasks | raw event lists |
| `edges` | tracked logons (src IP, LogonId, auth pkg) + explicit-cred uses (4648) + special-priv grants (4672) + outbound conns, capped | the whole connection table |
| `explain` | identity/svc/task changes + 4648/4672 + WMI subs + audit-cleared (1102) + LOLBin spawns w/ cmdline, capped | the whole ring/tenant export |
| `netedges` | Sysmon ring: conns + DNS + LSASS access (T1003) + thread injection (T1055) + file creates + registry sets | the full netflow |
| `pslogs` | PowerShell script blocks (4104) — the ACTUAL CODE being executed, decompiled | the whole PowerShell log |
| `kernring` | 10-second burst capture of process events from the Sysmon ring | a persistent agent |
| `attackmap` | 13 registry persistence locations, ATT&CK-tagged, FP-allowlisted | the whole filesystem |
| `flowstats` | per-adapter byte totals + top destinations (the T1041 volume baseline) | the full packet capture |
| `deepwindow` | a short-lived ETW kernel trace, captured at full fidelity, stopped, read back | a persistent agent |

## The scripts

| Script | Role |
|---|---|
| `scripts/lib.py` | The engine — allowlisted `ask()`, 32 KB cap, holes, pywinrm transport, scrt credential fallback, attackmap FP allowlist |
| `scripts/hunt.py` | The walk — edges → explain → pslogs where smoke; smoke → Telegram. Runs correlate at the end. |
| `scripts/correlate.py` | Cross-witness join — cross-host-account, lateral-hop (critical), explicit-cred-to-peer, shared-logonid (critical). Reads `case/answers/*.json`. |
| `scripts/drift.py` | Baseline + diff — new_admins (critical), sysmon_change (critical), witness_blind (critical), new_persistence. `--reset` re-baselines. |
| `scripts/case.py` | Open / list / close a one-page case. `--ticket PAY-4419` threads a business id through everything. |
| `scripts/notify.py` | Telegram helper (token+chat from secrets store). |
| `scripts/questions/windows/*.ps1` | The payloads above. Compact — preamble+payload must encode under WinRM's ~8191-char budget (×2.7 for UTF-16LE base64). |

## The blind check (standing rule)

Found live on WS2: the Logon audit policy was Failure-only, so `edges` returned
**zero logons while an Administrator session was connected**. Every "clean"
report from that box was a silent false negative.

Every `attest` now carries `raw_4624_24h` (unfiltered 4624 count), `blind_check`
(per-subcategory ok/BLIND/unknown for the six the questions depend on), and
`blind_count` (must be 0). `drift` treats a growing `blind_count` as **critical**.

**Standing rule: never trust a "no findings" result until you have confirmed
the witness can see.** An empty answer is not a clean answer.

## Relationship to the other skills

| Skill | Half |
|---|---|
| `rmagent-windows` | The complete skill — both halves, fully runnable |
| `rmagent-fr` | The Flight Recorder (tracing) half |
| `rmagent-so` | This skill — the witness-question (Security Observatory) half |
| `rmagent-redteam` | The drill — stages artifacts, scores detection |
| `rmagent-actuate` | Phase 1 response — named, journaled, reversible |
| `rmagent-linux` | The Linux/macOS sibling of this skill |