# HUNT KIT — what to equip a Windows estate with

`rmagent-so` + `rmagent-fr` are two **halves**, not a whole kit. This file says
exactly which skills to deploy for **on-device, lake-less, federated threat
hunting on a Windows network**, and what each one adds.

## The four-skill minimum

| Skill | Role | What breaks without it |
|---|---|---|
| **rmagent-core** | The shared engine (allowlist, cap, holes, doors) | the rest don't run |
| **rmagent-so** | The questions (identity + AD). Watch-only. | nothing to ask |
| **rmagent-windows** | The hunt driver: `hunt.py`, `patient_zero.py`, `drift.py` | no walk, no backward graph, no baseline |
| **rmagent-fr** | The case file, STC, trajectory, OTel, `trace.py --ticket` | findings don't become one tape |

Add these for a complete loop:

| Skill | Adds |
|---|---|
| **rmagent-redteam** | drills — proves detection actually fires |
| **rmagent-actuate** | named, journaled, reversible response (block/disable/isolate) |
| **rmagent-linux** | the moment any hop is Linux/AIX (SSH door) |
| **rmagent-at** | Windows host/application tracing (ETW), for "was the box sick" |

## Federation

- **Windows witnesses** -> WinRM (5985) or **PSRP** (`door: psrp`, no 8191 budget).
- **Non-Windows witnesses** -> **SSH** (`door: ssh` or `os: linux`); payloads in
  `questions/linux/*.sh`, run over stdin.
- **Context propagates, data does not** (`stc.py`): a hop receives the case id,
  principal, depth, ticket — never the previous host's logs.
- **`trace_merge.py`** fans out over SSH to merge multiple jump hosts.

## Domain coverage (Rev 21)

On a **DC**, three questions cover the domain-level attacks a member-server view
cannot see:

| Question | Covers |
|---|---|
| `krb` | 4768 TGT (AS-REP roast), 4769 TGS (**Kerberoasting, RC4 0x17**), 4771 pre-auth spray, 4776 NTLM validation |
| `dcsync` | 4662 with **DRS replication-rights GUIDs** (DCSync), 5136 dir changes (DCShadow) |
| `dirchange` | 4720/4726 accounts, 4728/4732/4756 privileged-group adds, 4740 lockout, 1102 audit cleared |

`attest` reports `domain_role` (dc/member/wg) and, on a DC, a `DC-Audit`
blind_check — so a member server never pretends "no DCSync" is a clean answer.

## The blind-check rule holds on every hop

**Never trust a "no findings" result until you have confirmed the witness can
see.** A blind Security log, an off 4688/4104 policy, a member server asked DC
questions, a silent host in cooldown — each is reported as a hole, not a clean
bill.

## Minimal inventory

```yaml
witnesses:
  - id: dc1
    os: windows
    door: psrp
    role: dc
    track: [Administrator, SYSTEM, krbtgt]
    skills: [attest, edges, krb, dcsync, dirchange]
  - id: ws1
    os: windows
    door: psrp
    skills: [attest, sketch, edges, explain, netedges, pslogs, attackmap, regedges, canary]
  - id: app-lin1
    os: linux
    door: ssh
    user: svc_audit
    track: [root]
    skills: [attest, sketch, edges, explain, attackmap]
```

Credentials: env `RMAgent_<ID>_USER/_PASS` or `~/.rmagent/creds.json` (mode 600).
Never in the inventory file.
