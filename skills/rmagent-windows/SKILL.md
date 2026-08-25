---
name: rmagent-windows
description: >
  Pull-based remote-witness habit for a Windows estate — the "RMAgent" knock.
  Ask two workgroup Windows servers (WS1/WS2) eight allowlisted named questions
  (attest, sketch, edges, explain, netedges, pslogs, kernring, attackmap) over pywinrm/WinRM :5985, tracking the
  Administrator and SYSTEM accounts. Use for identity-led compromise, lateral
  movement, living-off-the-land, silent hosts, and honest root-cause on Windows
  boxes you administer — without building a log lake and without switching off
  the EDR. Phase 0 is watch only; there is no actuate. Does NOT replace
  CrowdStrike/Defender. Prefer this skill for the two-box estate and
  Administrator/SYSTEM tracking; use the parent `security-observatory` skill
  for multi-plane (identity, cloud, network) hunts.
---

# RMAgent for Windows

You operate a **pull-based witness habit** on a two-box Windows estate (Windows Server 1 `44.197.31.152`, Windows Server 2 `52.3.242.251`), tracking the **Administrator** and **SYSTEM** accounts. You do not build a log lake. You do not retire Defender or CrowdStrike. You ask each box a small named question over WinRM, write a one-page case, and write a **hole** when a box is silent or a hop is stripped.

RMAgent is the **knock from the jump host**. On the Windows side it is just WinRM with an allowlist; on the jump host it is `scripts/lib.py` (`ask()`) plus four tiny `.ps1` payloads. There is no agent installed on the targets. There is no `actuate`.

Canonical architecture: `Hyperspace_Security_Observatory.pdf` (HT-ARCH-SEC-2026-01). This skill is the estate-specific, Administrator/SYSTEM-scoped child of the `security-observatory` skill.

## Non-negotiables

- **Keep the EDR.** Defender / CrowdStrike stays on. Commodity malware is out of this watch. Say so if anyone asks to switch it off.
- **Named questions only.** `attest`, `sketch`, `edges`, `explain`. `ask()` refuses anything else, and refuses `actuate` outright. Watch is not actuate. Isolate / disable / revoke is later, dual-controlled, after Phase 0 is proven. Never arbitrary remote script.
- **Track Administrator and SYSTEM.** Every payload filters to the `track:` principals in the inventory (default `[Administrator, SYSTEM]`). You follow the person/account, not the IP. NAT lies; a hashed LogonId does not.
- **Credentials never live in the skill, the inventory, or the case.** Read from env (`RMAgent_<ID>_USER` / `RMAgent_<ID>_PASS`) or `~/.rmagent/creds.json` (mode 600). Never print them. Never paste them onto a case.
- **Do not become a lake.** Every answer is capped at 32 KB. Oversized pulls become holes. Do not copy `Security.evtx`, `Get-WinEvent` dumps, or tenant exports home. The case is a one-page blackboard.
- **A hole is an answer.** Silent box, stripped ticket, missing field, liar — `{asked, empty, why}`, same shape as a hop. Do not tight-retry a silent host (lockout). Two missed attests = Critical.
- **Cap the walk.** depth ≤ 8, fan-out ≤ 3, 2 concurrent hunts, 15 min explain, 50 edges, 5 min cooldown on the same identity. Census may knock 3 boxes at once (all-windows budget); Hunter is serial.
- **Authorised estate only.** Only WS1 and WS2 (or boxes the user is authorised to administer). A partner box, SaaS you do not tenant, an unmanaged phone, NIBSS — those are holes, not witnesses.

## Setup (one time)

### 1. Jump host (macOS, Linux, or Windows)

The jump host is the trusted desk that knocks. It runs on macOS, Linux, or Windows. pywinrm connects over WinRM from any of them; PowerShell 7 (`pwsh`) is only needed if you use the optional `winrm_pool.ps1` RunspacePool path.

```bash
python3 --version          # 3.11+
pip3 install pywinrm pyyaml
export SKILL_DIR=~/.claude/skills/rmagent-windows
ls "$SKILL_DIR/scripts"/{census,hunt,case,lib}.py
ls "$SKILL_DIR/scripts/questions/windows/"   # attest sketch edges explain netedges
```

> The `secrets` scrt store unlocks with a master password resolved cross-platform: **`SCRT_PASS` env var** (everywhere) → macOS Keychain (macOS only) → **`~/.scrt_pass`** file (first line, restricted — the Linux/Windows fallback). On a Linux/Windows jump host, either `export SCRT_PASS=...` or create `~/.scrt_pass`.

### 2. Open the door on each Windows witness

**NTLM (default, zero-config on AWS):** WinRM is already listening on 5985 on
EC2 Windows instances. Just confirm the firewall allows the jump host:

```powershell
Enable-PSRemoting -Force
Set-Service WinRM -StartupType Automatic; Start-Service WinRM
New-NetFirewallRule -Name "WinRM-5985-JumpHost" -DisplayName "WinRM HTTP from jump host" `
  -Enabled True -Direction Inbound -Protocol TCP -LocalPort 5985 -Action Allow
```

**Basic (alternative — only if you set `transport: basic` in the inventory):**
also enable Basic auth and allow unencrypted (workgroup, HTTP 5985):

```powershell
Set-Item WSMan:\localhost\Service\Auth\Basic -Value $true
Set-Item WSMan:\localhost\Service\AllowUnencrypted -Value $true
```

> The live validation on WS1/WS2 used NTLM and worked with no server-side
> changes. For production, prefer HTTPS 5986 or Kerberos in a real domain.
> The habit — allowlisted named questions — is unchanged either way.

### 3. Credentials (env, recommended)

```bash
export RMAgent_WS1_USER=Administrator
export RMAgent_WS1_PASS='...'      # from your vault / the secrets skill — never commit
export RMAgent_WS2_USER=Administrator
export RMAgent_WS2_PASS='...'
```

Or store in `~/.rmagent/creds.json` (mode 600):

```json
{ "ws1": { "user": "Administrator", "password": "..." },
  "ws2": { "user": "Administrator", "password": "..." } }
```

### 4. Inventory

```bash
cp "$SKILL_DIR/assets/inventory.example.yaml" ./estate.yaml
# edit only if you add a box you administer. Never add passwords here.
```

## The four questions (what each returns, Administrator/SYSTEM-scoped)

| Question | Payload | What you get | What you must NOT get |
|---|---|---|---|
| **Alive?** (attest) | `attest.ps1` | host, utc, last boot, admin failed logons 60s, admin ok logons 5min, local admin count, SYSTEM remote conns | a full Security log dump |
| **Anything odd?** (sketch) | `sketch.ps1` | admin failed in window, new local admins 24h, running privileged services, new services/tasks | raw event lists |
| **Who did they touch?** (edges) | `edges.ps1` | recent Administrator/SYSTEM logons (time, type, src IP, LogonId, auth package) + **explicit-credential uses (4648: who→became→dest)** + **special-privilege grants (4672: privilege set)** + outbound conns owned by them, capped | the whole connection table |
| **What changed?** (explain) | `explain.ps1` | group/service/task/account changes + **4648/4672** (explicit creds, special privs) + **WMI event subscriptions (5861 — fileless persistence, ATT&CK T1546.003)** + **audit-log-cleared (1102 — anti-forensics)** + **LOLBin spawns with command line (4688)** + process spawns by Administrator/SYSTEM in the window, capped | the whole tenant/ring export |
| **What connected?** (netedges) | `netedges.ps1` | SYSTEM/Administrator-owned outbound connections from the **Sysmon EID3 ring** (a persisted log, not a point-in-time snapshot) — catches transient connections after they close. Requires Sysmon with `<NetworkConnect onmatch="exclude">` | the full netflow / packet capture |
| **What code ran?** (pslogs) | `pslogs.ps1` | **PowerShell script blocks (4104) — the actual code being executed**, decompiled. An `-enc` payload appears here as readable text. Requires script-block logging (was already ON on both boxes). NOTE: 4104's UserId field is often empty; blocks are returned unfiltered (capped) because every block is worth reading | the whole PowerShell operational log |
| **What if Sysmon is gone?** (kernring) | `kernring.ps1` | Process + network events from the **built-in kernel analytic channels** (`Kernel-Process/Analytic`, `Kernel-Network/Analytic`) — the no-Sysmon fallback. Also reports `sysmon_status` (the tripwire). Requires setup step D3. **Degraded mode**: no process names on net events, no command lines, short ring (minutes not days) | the whole ETW stream |
| **What persistence already exists?** (attackmap) | `attackmap.ps1` | **ATT&CK-mapped persistence STATE check** — reads the registry locations BLUESPAWN enumerated (Run keys, IFEO debuggers, AppCert/AppInit DLLs, SSPs, Winlogon hijack, Netsh helpers, port monitors, logon scripts). Every finding carries its technique ID (T1547.001, T1546.010, etc.). Catches persistence that predates our monitoring window | the whole registry |

> `edges` reads *currently-Established* connections — a point-in-time snapshot that misses sub-second connections. `netedges` reads the **Sysmon ring**, which persists them. Use `netedges` when you need to catch transient SYSTEM/Administrator outbound connections (e.g. a short C2 beacon). Both stay pull-only, both capped — no lake.

Engine injects `$Track`, `$SinceHours`, `$Limit` as a preamble; payloads read them. No payload is a god-shell.

## Operating loop

```
every 1 min ± jitter →  census (attest only; alive + Admin/SYSTEM smoke digest)
every 5–15 min       →  scout  (sketch: new admins, priv services, new tasks/services)
on smell/silence     →  hunter (edges → explain on hosts with smoke), serial, capped
on High case         →  human (Judge) pins, closes, or escalates. No isolate from Phase 0.
never                →  copy Security.evtx, dump rings, tight-retry silent hosts, actuate
```

Agents are not a SOC. After hours, a human is still on call for Hunter and any explain that touches a person.

## Scripts

Resolve `$SKILL_DIR` as the folder containing this `SKILL.md`.

| Job | Script | Notes |
|---|---|---|
| Minute watch | `scripts/census.py` | pywinrm, max-3 knock budget, 2 misses = Critical |
| Administrator/SYSTEM walk | `scripts/hunt.py` | serial, depth-capped; writes path.json + holes.jsonl |
| Write / list / close a case | `scripts/case.py` | one-page blackboard |
| Allowlisted payloads | `scripts/questions/windows/*.ps1` | attest / sketch / edges / explain |
| Optional all-pwsh path | `scripts/winrm_pool.ps1` | Invoke-Command + RunspacePool (max 3), creds from env |

```bash
# Census — are WS1/WS2 alive?
python3 "$SKILL_DIR/scripts/census.py" --inventory ./estate.yaml

# Open a case, then walk Administrator/SYSTEM across both boxes
CASE=$(python3 "$SKILL_DIR/scripts/case.py" open --title "admin walk" --principal Administrator)
python3 "$SKILL_DIR/scripts/hunt.py" --inventory ./estate.yaml --since 2h --case-dir "$CASE"

# All-pwsh alternate (only if every door is winrm)
pwsh -NoProfile -File "$SKILL_DIR/scripts/winrm_pool.ps1" -Skill attest `
  -ComputerName '44.197.31.152','52.3.242.251' -Ids ws1,ws2 -MaxRunspaces 3
```

## Identifier, pin, hole

| Object | Contract |
|---|---|
| Hop id | LogonId (hex) or a work/request id for app hops. Same id across hosts = same session. |
| Ticket / session | Never store Kerberos/NTLM. The LogonId from a 4624 event is the join, not a secret. |
| If stripped | Idempotency key, then producer child, then **hole**. Never join on public IP. |
| Pin | Auto on 2 missed attests, Hunter walk, human incident. Days (default 14). |
| Hole | `{asked, empty, why}` — same shape as a hop. |

## What success looks like (Phase 0)

You can read the case aloud in two minutes: hops for `ws1` and `ws2`, any holes written, `Security.evtx` still on the boxes, EDR still drawing. **Fail:** you exported `Security.evtx`, isolated a host, invented a hop, or called a timeout "nothing happened."

## Examples

- `examples/lab-a-live.md` — Lab A: attest both, silence one, write the hole.
- `examples/walk-administrator.md` — a full Administrator/SYSTEM hunt across WS1+WS2.

## What this skill will NOT do

- No `actuate`. `ask()` returns a hole for it. Isolate/disable/revoke stays with the EDR/IAM and a human.
- No log lake. No `Security.evtx` copy. No tenant/ring dump.
- No inventing a witness for a box you do not administer (NIBSS, a partner, a phone).
- No tight retry on a silent host.
- No replacement for the EDR. Commodity malware stays with Defender/CrowdStrike.

## Hardening changelog (2026-08-19)

Live-verified bug fixes from a purple-team drill on WS1/WS2:

- **`creds_for()` now falls back to the scrt store** (env → `~/.rmagent/creds.json` → scrt). Previously `census.py`/`hunt.py` failed with "no credential" unless env vars were manually exported.
- **Census miss-state is now stable** at `~/.rmagent/.census_miss.json` (was CWD/case-dir — "2 misses = Critical" could never trigger across runs).
- **`attest`/`sketch` match only `TargetUserName`** on 4624/4625 — matching any event field counted SYSTEM-subject events as admin failures (false positives).
- **`sketch.new_local_admins` only reports members still in the group** — deleted users' 4732 events linger 24h as stale SIDs.
- **`netedges` is advertised in the example inventory** — fresh installs previously scored max 5/6 on drills.
- Payloads compacted under the WinRM UTF-16LE base64 command-line budget (~8191 chars).

## Lateral-movement & persistence additions (2026-08-19, rev 2)

New event coverage in `edges` and `explain`, live-verified on WS1:

- **`edges.explicit_creds` (4648)** — *the* lateral-movement signal: `runas`, `Invoke-Command -Credential`, any explicit-credential logon. Each record shows `who → became → dest` in one line. Live test found 2 uses on WS1 in a 2h window (`EC2AMAZ-8NK9FUP$ → Administrator @ localhost`).
- **`edges.special_privs` (4672)** — the privilege set granted at each admin logon. `SeDebugPrivilege` = process injection; `SeTcbPrivilege` = act-as-OS. Anomalous grants are now visible.
- **`edges` logons now carry the auth package** (`NTLM` vs `Kerberos`) — NTLM on a Kerberos-capable box is itself a signal.
- **`explain.wmi_subscriptions` (5861)** — WMI event subscriptions, the classic fileless persistence (ATT&CK T1546.003), read from `Microsoft-Windows-WMI-Activity/Operational`. Zero is the healthy steady state; any non-zero is an immediate finding.
- **`explain.identity_changes` now include 4648/4672**, and `hunt.py` fires a Telegram smoke alert naming them.
- `hunt.py` output and the case `path.json` record `explicit_creds`, `special_privs`, `wmi_subscriptions` as first-class hop fields.

**Audit prerequisite:** 4648/4672 need "Audit Logon" (success) — same subcategory as the 4625 failure auditing. 5861 needs no audit policy; the WMI-Activity operational log writes it when a subscription is created.

## Rev 3 — 4688 upgrade, anti-forensics, DNS, and PowerShell code (2026-08-19)

Driven by a live probe of what sources actually exist on WS1/WS2:

- **4688 split into two collections.** `proc_spawns` (all, capped) stays for volume; new **`lolbin_spawns`** filters to LOLBins — `powershell`, `cmd`, `wscript`, `cscript`, `mshta`, `rundll32`, `regsvr32`, `certutil`, `bitsadmin`, `msiexec`, `schtasks`, `wmic`, `psexec`, `curl`, `tar` — **and carries `CommandLine`** when command-line auditing is on. "PowerShell ran" becomes "PowerShell ran `-enc SQBFAFgA...`". Probe showed 3,464 raw 4688s/day on WS1 — the LOLBin cut is what makes it signal instead of noise.
- **`audit_cleared` (1102)** — the audit log was cleared. The classic anti-forensics move; on a healthy box this is *always* zero, so any hit is an immediate Critical-grade finding. Telegram alert names it explicitly.
- **`task_events` now includes 4699** (task *deleted*) alongside 4698/4702 — an attacker deleting the task they used is as interesting as creating it.
- **`netedges.dns_queries` (Sysmon 22)** — DNS queries by tracked principals: the domain a beacon resolves *before* the connection. Pair a DNS query with the matching netedges connection and you have the full C2 story. Requires `<DnsQuery onmatch="exclude">` in the Sysmon config (WS2 had 10 in 24h at probe time; WS1 had none — the config differs per box).
- **New question `pslogs` (4104)** — PowerShell script-block logging: **the actual code being executed**, decompiled from the script block. This is the highest-fidelity signal in the skill. Probe found it already enabled on both boxes (348/342 events in 24h). Live-tested: returns the real script text. Caveat discovered live: 4104's `UserId`/`Path` Data fields are often *empty* (the user lives in the event's Security descriptor), so blocks are returned unfiltered and capped — every block is worth reading, unlike a process count. Each block's text is truncated to 500 chars to respect the 32 KB answer cap.
- `hunt.py` prints and records all of it; Telegram smoke alerts name the new signals (audit-cleared gets an explicit "anti-forensics!" flag).

**Prerequisites for the new signals:** 4688 command lines need `auditpol /set /subcategory:"Process Creation" /success:enable` **plus** the registry key `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System\Audit\ProcessCreationIncludeCmdLine_Enabled = 1`. 4104 needs script-block logging (Group Policy: Administrative Templates → Windows Components → Windows PowerShell → PowerShell Script Block Logging; or the registry equivalent under `HKLM\SOFTWARE\Wow6432Node\Policies\Microsoft\Windows\PowerShell\ScriptBlockLogging`). Sysmon 22 needs the DnsQuery rule in the config.

## Rev 4 — kernring: the no-Sysmon fallback (2026-08-20)

**Why:** sophisticated attackers target Sysmon specifically — `Stop-Service Sysmon64; sc.exe delete Sysmon64` — and if Sysmon is your only process/network ring, that one command blinds you. The kernel analytic channels are built into Windows, have no obvious service to stop, and give you a degraded but functional ring when Sysmon is gone.

**What was added:**

- **New seventh question `kernring`** — reads `Microsoft-Windows-Kernel-Process/Analytic` (process start/stop with PID, image, parent PID, and command line where available) and `Microsoft-Windows-Kernel-Network/Analytic` (TCP/UDP connect with PID, dest IP, dest port). Also reports `sysmon_status` in every response.
- **`sysmon_status` tripwire in `attest`** — every census now reports whether Sysmon is Running, Stopped, or not-installed. A change from Running to anything else is a finding: either the sensor died or someone stripped it. This is the signal that tells you when to fall back to kernring.
- **`hunt.py` fires a Telegram smoke alert when Sysmon is not running** — "the primary ring is down; kernring is the fallback."
- **Setup step D3** — `wevtutil sl Microsoft-Windows-Kernel-Process/Analytic /e:true` and the Network equivalent, wired into the setup docs alongside D1 (auditpol) and D2 (Sysmon ring).

**The honest fidelity gap** (documented, not hidden):

| | netedges (Sysmon) | kernring (kernel channels) |
|---|---|---|
| Process name on network events | ✅ | ❌ PID only — must join |
| Command lines | ✅ | ⚠️ version-dependent |
| Process hashes | ✅ | ❌ |
| Stable GUIDs / parent chains | ✅ | ❌ PID-based, PIDs recycle |
| Ring depth | Days (configurable) | **Minutes** (small fixed buffer) |
| Survives Sysmon deletion | ❌ | ✅ |

**Design decision:** kernring is a *separate question*, not a silent fallback inside `netedges`. If `netedges` silently degraded, the operator would think they're getting Sysmon-quality data when they're not — a lie by omission that violates the "a hole is an answer" principle. The operator asks the question that matches the fidelity they need.

**Status: LIVE-VALIDATED 2026-08-25.** Ran against both WS1 and WS2 (estate reachable): `kernring` returns process events from the kernel analytic channels with the expected fields, and reports `sysmon_status` on every call (Sysmon64=Running on ws1, Sysmon=Running on ws2). **Reality check discovered in live testing:** on this estate the kernel channels are NOT enabled as a persistent ring — the payload works as a **10-second burst capture** (`burst_seconds: 10`, note: "burst capture - 10s window, not a ring. Sysmon is the ring."), not the minutes-deep ring the design assumed. To get a persistent ring, setup step D3 (`wevtutil sl Microsoft-Windows-Kernel-Process/Analytic /e:true`) must be run on each box first; until then kernring is a spot-check, not a fallback ring.

## Rev 5 — attackmap + ATT&CK tagging + expanded LOLBins (2026-08-21)

**Source:** BLUESPAWN's ATT&CK-mapped hunt registry (github.com/ION28/BLUESPAWN, MIT license). We took the *knowledge* — the registry locations, the technique mappings, the LOLBin list — and reimplemented it pull-only. We did not take the agent, the YARA scanning, the process-memory scanning, or the mitigation system. Those violate the architecture.

**What was added:**

- **New eighth question `attackmap`** — an ATT&CK-mapped persistence STATE check. Reads 13 registry locations BLUESPAWN enumerated: Run keys (T1547.001), IFEO debuggers (T1546.010), AppCert DLLs (T1546.009), AppInit DLLs (T1546.010), Security Support Providers (T1547.005), Notification packages (T1547.002), Winlogon hijack (T1547.004), Netsh helpers (T1546.007), port monitors (T1547.010), logon scripts (T1037.001), recent accounts (T1136.001), disabled firewall profiles (T1562.004). Every finding carries its technique ID.
- **Why state, not events:** `explain` catches when persistence is CREATED (4698, 7045, 4720). `attackmap` catches persistence that ALREADY EXISTS — including anything that predates our monitoring window or was staged before rmagent was installed. This is the "what was already on the box when we started" check.
- **ATT&CK tags on existing findings.** `sketch` now returns `admin_failed_attack='T1110'`, `new_local_admins_attack='T1136.001'`, `new_services_attack='T1543.003'`, `new_tasks_attack='T1053.005'`. The operator sees not just "a task was created" but "T1053.005: Scheduled Task persistence."
- **LOLBin list expanded 18 → 80** (from BLUESPAWN's curated list). Adds `msxsl`, `installutil`, `msbuild`, `forfiles`, `diskshadow`, `dnscmd`, `cmstp`, `msdt`, `odbcconf`, `pcalua`, `rasautou`, `regasm`, `regsvcs`, `runscripthelper`, `scriptrunner`, `syncappvpublishing`, `tttracer`, `verclsid`, `wab`, `xwizard`, `appvlp`, `bginfo`, `cdb`, `csi`, `devtoolslauncher`, `dnx`, `dotnet`, `dxcap`, `mftrace`, `msdeploy`, `rcsi`, `sqlps`, `sqltoolsps`, `squirrel`, `te`, `tracker`, `update`, `vsjitdebugger`, `wsl`, and more.
- **`hunt.py` integration:** attackmap prints `N/13 ATT&CK techniques with findings`, lists each technique found, records `checked`/`found` as hop fields, and fires a Telegram smoke alert for high-severity techniques (IFEO hijack, SSP, Winlogon hijack, AppCert, firewall disabled).

**What we deliberately did NOT take from BLUESPAWN:**

| Left out | Why |
|---|---|
| The agent | Installs a service on every box. We are agentless by design. |
| YARA file scanning | Requires reading file contents off the box. Violates the no-lake rule. |
| Process memory scanning | Needs kernel access or an agent. Out of scope. |
| Their mitigation system | 20+ hardcoded registry changes with no dry-run, no journal, no undo. The Actuator does this properly. |
| Real-time ETW monitoring | Requires a persistent consumer process = an agent. kernring is our answer. |
| The C++ implementation | ~16 hunt files, thousands of lines. We took the knowledge, not the code. |

**Status: LIVE-VALIDATED 2026-08-25.** Ran against both WS1 and WS2: `attackmap` returns findings with ATT&CK tags on both boxes (ws1: T1547.001 run_keys ×1, T1546.007 netsh ×17; ws2: T1547.001 ×2, T1546.007 ×17). The full 8-signal redteam drill confirmed attackmap catches the staged drill artifacts: `run_key drill: True, ifeo drill: True` on both boxes (the two new Rev 5 signals). Drill artifacts cleaned up cleanly afterwards (0 remaining).
