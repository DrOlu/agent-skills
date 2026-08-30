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
| `attest` | alive, last boot, admin failed/ok logons, local admin count, SYSTEM conns, **raw_4624_24h + blind_check + blind_count + oldest_security_event** | a full Security log dump |
| `sketch` | admin failed in window, new local admins 24h, running priv services, new services/tasks | raw event lists |
| `edges` | tracked logons (src IP, LogonId, auth pkg) + explicit-cred uses (4648) + special-priv grants (4672) + outbound conns, capped | the whole connection table |
| `explain` | identity/svc/task changes + 4648/4672 + WMI subs + audit-cleared (1102) + LOLBin spawns w/ cmdline, capped | the whole ring/tenant export |
| `netedges` | Sysmon ring: conns + DNS + LSASS access (T1003) + thread injection (T1055) + file creates + registry sets | the full netflow |
| `pslogs` | PowerShell script blocks (4104) — the ACTUAL CODE being executed, decompiled | the whole PowerShell log |
| `kernring` | 10-second burst capture of process events from the Sysmon ring | a persistent agent |
| `attackmap` | 13 registry persistence locations, ATT&CK-tagged, FP-allowlisted | the whole filesystem |
| `flowstats` | per-adapter byte totals + top destinations (the T1041 volume baseline) | the full packet capture |
| `deepwindow` | a short-lived ETW kernel trace, captured at full fidelity, stopped, read back | a persistent agent |
| `canary` | any auth attempt against a decoy identity (4624/4625/4740) + the source IPs | anything about real accounts |

### `canary` — the patient-zero tripwire (Rev 15)

A canary is a decoy identity that exists **only to be touched**. Any
authentication attempt against it is critical by definition — there is no
legitimate reason to log on as `honeyadmin`. This turns patient-zero
detection from a graph walk into a tripwire: near-zero false positive, no
correlation needed.

- Declare canaries in the inventory: `canaries: [honeyadmin, svcbackup2]`
- With none declared, the payload falls back to decoy-name heuristics
  (`canary`, `honey`, `decoy`, `tripwire`, …) so an estate that planted
  decoys without updating the inventory still gets coverage
- A hit surfaces as a **critical** `canary_tripped` finding in both `drift`
  and `correlate`, carrying the source IPs — the shortlist for
  `actuate.py block_ip`

## The scripts

| Script | Role |
|---|---|
| `scripts/lib.py` | The engine — allowlisted `ask()`, **signal-aware cap**, holes, pywinrm transport, scrt credential fallback, attackmap FP allowlist |
| `scripts/hunt.py` | The walk — edges → explain → pslogs where smoke; smoke → Telegram. Runs correlate at the end. |
| `scripts/correlate.py` | Cross-witness join — cross-host-account, lateral-hop (critical), explicit-cred-to-peer, shared-logonid (critical), canary_tripped. **Adds triage ranking + recommended actuate actions.** |
| `scripts/patient_zero.py` | The backward graph walk with **honest termination** — origin vs retention-boundary vs blind-witness vs no-signal vs cycle |
| `scripts/drift.py` | Baseline + diff — new_admins (critical), sysmon_change (critical), witness_blind (critical), new_persistence, **canary_tripped (critical)** |
| `scripts/case.py` | Open / list / close a one-page case. `--ticket PAY-4419` threads a business id through everything. |
| `scripts/notify.py` | Telegram helper (token+chat from secrets store). |
| `scripts/test_enterprise.py` | Pure-logic test suite for all of the above (57 assertions). |
| `scripts/test_budget.py` | Enforces the WinRM ~8191-char budget on every payload. |
| `scripts/questions/windows/*.ps1` | The payloads above. Compact — preamble+payload must encode under WinRM's ~8191-char budget (×2.7 for UTF-16LE base64). |

### The signal-aware cap (Rev 15)

The flat 32 KB cap was an **evasion surface**: a noisy host (or an attacker
flooding events) pushed the signal past the window and the whole answer
became a hole — the loudest box got ignored.

Now an over-budget answer is **triaged, not dropped**: low-signal rows are
shed first, and rows carrying critical event IDs (4648, 4672, 5861, 1102,
4104, 4698, 7045, 4732, 4688) always survive the trim. The cap is never
raised — we only choose *what* survives it. Still no lake.

An answer that was trimmed carries `capped: true` and a `cap_note`, so the
operator knows the window was narrowed rather than being silently deceived.

### Triage (Rev 15)

With 50 findings across 10 hosts, an operator needs to know what to actuate
FIRST. Every correlate finding now carries a `triage_rank`, a `triage_why`,
and `recommended_actions` (drawn only from the actuate allowlist):

| rank | kind | why | actuate |
|---|---|---|---|
| 0 | `canary_tripped` | near-zero FP, patient-zero candidate | block_ip, disable_user, kill_process |
| 1 | `shared-logonid` | stolen credential in active use | disable_user, block_ip |
| 2 | `lateral-hop` | active movement | block_ip, kill_process |
| 3 | `new_admins` | privilege gained since baseline | remove_admin, disable_user |
| 4 | `new_tracked_proc` | new process as a tracked principal | kill_process, quarantine_file |
| 5 | `witness_blind` | every other answer is suspect | *(policy fix, not actuate)* |
| 6 | `explicit-cred-to-peer` | explicit creds against a peer | disable_user |
| 7 | `cross-host-account` | could be legitimate admin | disable_user |
| 8 | `sysmon_change` | the tripwire itself moved | *(investigate)* |
| 9 | `new_persistence` | persistence grew | delete_task, stop_service, disable_wmi_sub |

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