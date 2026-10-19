---
name: plasma
description: Install, configure, operate and troubleshoot Plasma — a lake-less Windows EDR with an on-device frozen neuralOS brain, krabsetw ETW tap, WHIDS (detect-only) sensor, identity plane, drift baselines, human-gated actuation, fleet correlation, self-update and health/watch ops. Use when the user mentions Plasma, wants to deploy/install Plasma on a Windows node, run drills, pull/collect events, push IOCs, observe/attest/sketch a box, set up health/watch/alerting (telegram/webhook), self-update nodes, run two-host fleet scans, or troubleshoot WHIDS hang / WinRM lockout / PS 5.1 quirks on Plasma nodes.
---

# Plasma — Installation, Configuration & Operations

Plasma is a **lake-less Windows EDR**: sensors watch on the device, a 35 MB
frozen neuralOS brain answers plain-language questions on the device, and
nothing leaves the box unless you pull it. Detection is deterministic rules
you can read. Response is human-gated, dry-run first, journaled, and
lockout-proof.

**Current release line:** v0.11.1 · repo `DrOlu/plasma` (private — PAT
needed for downloads) · single `plasma-<ver>-windows-x64.exe`.

---

## 1. Architecture in 60 seconds

```
SENSORS (on the node, all detect-only)
  Sysmon ──► WHIDS 1.7.0 ──► alerts JSONL ──┐
  krabsetw ETW tap ──► matches JSONL ───────┤
  Event Log API ──► identity (4624/4625) ───┤
                                            ▼
                            events.jsonl (strict PlasmaEvent contract)
                                            ▲
BRAIN (frozen instance, offline) ── ask/probe┘   drift • actuate • update
DESK (your Mac/Linux) ── fleet pull/correlate/report • update check/apply
```

- **WHIDS** = Go HIDS consuming Sysmon; **detect-only by config** (its
  v1.7.0 engine has no kill/block actions at all).
- **Tap** = krabsetw C++ sidecar streaming PowerShell/WMI/DNS/dotnet/
  Schannel providers; in-memory scoring against `plasma-tap-rules.json`;
  writes **matches only**.
- **Identity** = 4624/4625 logons read from the Security channel via the
  Event Log API (NOT ETW — audit events are never re-emitted to realtime
  ETW sessions; proven on WS1).
- **Brain** = frozen neuralOS instance: 10 read-only probes, plain-language
  `plasma ask`.
- **Fleet** = desk-side: pull capped tails from N nodes, correlate, report.
  No server, no lake.

**Two install modes** (the installer picks automatically):
- **FULL** — internet available: Sysmon is downloaded from Sysinternals
  (EULA accepted via `-accepteula` on the operator's behalf), WHIDS is
  provisioned from the signed bundle (no internet needed for it).
- **MINIMAL** — no internet / download failure / `--skip-whids`: WHIDS and
  Sysmon skipped, reason recorded in `config.json`; node stays fully
  operational on tap + identity + instance + drift + actuate + fleet.
- `--require-whids` restores fail-closed; `--skip-whids` /
  `--skip-sysmon-check` force minimal.

---

## 2. Installation

### 2.1 Requirements

| Requirement | Notes |
|---|---|
| Windows x64, Win10/11 or Server 2016+ | PS 5.1 present by default |
| Administrator at install time | installer + service registration + ETW |
| ~200 MB disk, modest RAM | single exe + runtime + stores |
| Internet (FULL mode only) | for the Sysmon download only |
| Desk-side channel (optional) | WinRM 5985 **or** SSM w/ IAM profile — for fleet pulls |

No Python, no .NET additions, no pre-existing agents. Sysmon is NOT
required on the node — the installer acquires it when it can.

### 2.2 One-liner install (on the node, elevated)

```powershell
# fetch + verify + install (FULL or MINIMAL chosen automatically)
$pat = $env:PLASMA_GITHUB_TOKEN   # PAT with repo read access
Invoke-WebRequest -UseBasicParsing `
  -Uri "https://api.github.com/repos/DrOlu/plasma/releases/latest" `
  -Headers @{ Authorization = "Bearer $pat" } -OutFile rel.json
$rel  = Invoke-RestMethod -Uri 'https://api.github.com/repos/DrOlu/plasma/releases/latest' `
        -Headers @{ Authorization = "Bearer $pat" }
$asset = $rel.assets | Where-Object name -like 'plasma-*.exe' | Select-Object -First 1
Invoke-WebRequest -UseBasicParsing -Uri $asset.url `
  -Headers @{ Authorization = "Bearer $pat"; Accept = 'application/octet-stream' } `
  -OutFile plasma-latest.exe -TimeoutSec 300
.\plasma-latest.exe install
```

What it does: verifies the SHA256 manifest → stages
`C:\ProgramData\Plasma\instances\plasma-<ver>` → flips the `current`
junction → writes `config.json` → registers WHIDS (FULL) or records the
skip reason (MINIMAL) → exits 0. Re-run with `--force` to upgrade.

### 2.3 Verify

```powershell
.\plasma-latest.exe --version          # plasma 0.11.1
.\plasma-latest.exe health             # ok | degraded | down (json verdict)
Get-Service Whids, Sysmon64            # FULL mode: both Running
```

### 2.4 Remote bootstrap (SSM pattern — use when WinRM is locked out)

```bash
export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=...
aws ssm send-command --instance-ids i-xxx --document-name AWS-RunPowerShellScript \
  --parameters commands="..."     # same fetch+install block as 2.2
```

---

## 3. Configuration

Everything lives under `C:\ProgramData\Plasma`:

| File | Purpose |
|---|---|
| `config.json` | install decision, sensor states, events path, degraded flag |
| `data\events.jsonl` | the ONE event store (strict PlasmaEvent rows) |
| `notify.json` | alert channels (create manually) |
| `current\` | junction → active instance |
| `instances\plasma-<ver>\` | staged releases |

### 3.1 Alert channels (`C:\ProgramData\Plasma\notify.json`)

```json
{
  "channels": [
    {"type": "telegram", "token_env": "PLASMA_TG_TOKEN", "chat_id": "123456"},
    {"type": "webhook", "url": "https://hooks.example.com/plasma"}
  ],
  "min_score": 7
}
```

**Secrets never live in this file.** Telegram uses `token_env` (the token
comes from the named environment variable); inline `token` fields are
refused. Validate and test:

```powershell
plasma notify show    # validates config
plasma notify test    # sends a test message to every channel
```

### 3.2 Tap rules (`sensors/plasma-tap-rules.json` in the bundle)

31 deterministic rules: provider + event_id + case-insensitive substring
on one named field (`*` = all parsed fields, empty substr = match-all).
Add a rule by appending to `rules[]`:

```json
{"name": "ps-my-detection", "provider": "powershell", "event_id": 4104,
 "field": "ScriptBlockText", "substr": "Invoke-CustomThing",
 "severity": "high", "technique": "T1059.001"}
```

`severity` ∈ info|low|medium|high|critical; `technique` must match
`T\d{4}(\.\d{3})?`. Rules ship inside the signed bundle — changing them
means a new release (or editing the rendered copy for testing).

### 3.3 WHIDS gene rules

`Database\Rules\plasma-iocs.gen` — **owned by `plasma whids push`**
(regenerated from the events store on every apply; do not hand-edit).
`Database\Rules\plasma-baseline.gen` — 10 shipped baseline gene rules
(certutil, Office-spawns-shell, SAM dump, bitsadmin, mshta, rundll32-js,
net-add, encoded-cmd, schtasks, wmic). Schema **1.0.0** syntax:

```
{"Name":"...","Tags":[...],"Meta":{"EventIDs":[1],"Channels":
["Microsoft-Windows-Sysmon/Operational"],"Computers":[],"Criticality":7,
"Author":"Plasma","Comment":"...","Schema":"1.0.0"},
"Matches":["$a: Image ~= '(?i:..)'","$b: CommandLine ~= '(?i:..)'"],
"Condition":"$a and $b"}
```

Regexes are single-quoted, `~=` match / `=` equality; backslashes must be
JSON-escaped (`\\.`). One JSON object per line (concatenated docs OK).
A bad rule fails WHIDS load **fail-closed** — validate JSON before shipping.

### 3.4 Known-good Sysmon baseline config

```xml
<Sysmon schemaversion="4.90"><EventFiltering>
<ProcessCreate onmatch="exclude"/><FileCreateTime onmatch="exclude"/>
<NetworkConnect onmatch="exclude"/><ProcessTerminate onmatch="exclude"/>
<ImageLoad onmatch="exclude"/><FileCreate onmatch="exclude"/>
<RegistryEvent onmatch="exclude"/><DnsQuery onmatch="exclude"/>
</EventFiltering></Sysmon>
```

The installer writes this automatically when it auto-installs Sysmon.

---

## 4. Operation

### 4.1 Health & watch (tell me when something's wrong)

```powershell
plasma health        # ok | degraded | down + per-check detail
plasma watch once    # sweep: health + drift + canary + unpulled alerts
plasma watch loop --every 3600   # or schedule `watch once` in Task Scheduler
```

Watch is quiet when clean and notifies through configured channels when
findings cross the threshold. State lands in
`C:\ProgramData\Plasma\watch-state.json`.

### 4.2 Observe (read-only questions, rmagent lineage)

```powershell
plasma observe attest        # witness liveness + blind_check
plasma observe sketch        # admins, new services/tasks, drivers
plasma observe edges         # 4624 logon edges (who/where)
plasma observe explain       # account/group/WMI changes + LOLBins
plasma observe pslogs        # scriptblock 4104 snippets
plasma observe attackmap     # Run/IFEO/Winlogon/LSA persistence
plasma observe regedges      # Sysmon registry edges
plasma observe flowstats     # adapters + top remote peers
plasma observe canary --canary plasma-canary
plasma observe sysmon_health # channel volume by event id
```

### 4.3 Drift (what changed since I last looked)

```powershell
plasma drift record --question attest    # snapshot baseline
plasma drift score  --question attest    # 0-10 scored diff + verdict
plasma drift list
```

Scores: canary_tripped 10, sensor_down 10, admin_added 9, new_persistence 9,
blind_drift 8, new_service 8, new_task 7.

### 4.4 Actuation (human-gated response)

```powershell
plasma actuate actions                                            # the allowlist
plasma actuate apply block_ip --target 1.2.3.4 --reason "C2"      # dry-run -> journal id
plasma actuate apply block_ip --target 1.2.3.4 --reason "C2" --apply --plan 3
plasma actuate undo --id 3 --apply
```

Guarantees: dry-run default, `--reason` mandatory, journal with undo
payloads + verification, protected targets refused (WinRM, TermService,
WHIDS, Sysmon, BFE, MpsSvc, lsass…), and `isolate_host` always keeps
RDP-3389 + WinRM-5985 reachable.

### 4.5 Events in/out

```powershell
plasma whids pull --root 'C:\Program Files\Whids' --out C:\ProgramData\Plasma\data\events.jsonl
plasma tap run --providers powershell,wmi,dns,security --for 60s --out-dir C:\ProgramData\Plasma\tap --events C:\ProgramData\Plasma\data\events.jsonl
plasma identity pull --events C:\ProgramData\Plasma\data\events.jsonl --since 60
plasma ask --prompt "critical alerts" --events C:\ProgramData\Plasma\data\events.jsonl
```

### 4.6 Intelligence push-back

```powershell
plasma whids push --root 'C:\Program Files\Whids' --events <store> `
  --min-confidence 3 --apply --reason "why"
plasma whids status --root 'C:\Program Files\Whids' --events <store>
```

Push **replaces** the gene rule (backup kept) — WHIDS needs a restart to
reload (no manager, no hot reload). Gene rules must be schema 1.0.0
(the push generates this automatically).

### 4.7 Identity plane

```powershell
plasma identity pull --events <store> --since 60    # 4624/4625 -> kind=auth rows
```

Machine accounts filtered, dedupe by content, logon type/source IP in the
description.

### 4.8 Fleet (one desk, many computers)

Inventory file (e.g. `fleet.json`):

```json
{"hosts": [
  {"name": "WS2", "transport": "winrm", "endpoint": "52.x.x.x",
   "username": "Administrator", "password_env": "WS2PW",
   "events_path": "C:\\ProgramData\\Plasma\\data\\events.jsonl"},
  {"name": "WS1", "transport": "file", "events_path": "/tmp/ws1-events.jsonl"}
]}
```

```bash
pip install 'plasma-edr[desk]'          # adds pywinrm
plasma fleet scan  --inventory fleet.json --case incident-42 --window 21600
plasma fleet report --case incident-42
```

Joins: lateral_hop 9 (same user, 2+ hosts, within window), shared_hash 8,
shared_domain 7, shared_ip 7, canary_tripped 10, blind_host 8. Verdicts:
clean / investigate / act now. Case dossiers land in
`<root>/fleet-cases/<case>/`. Passwords only via `password_env` (env var
indirection — inline secrets refused, enforced by test).

### 4.9 Self-update

```powershell
$env:PLASMA_GITHUB_TOKEN = "<PAT>"
plasma update check                        # exit 0 = up to date, 2 = update available
plasma update apply --bin C:\ProgramData\Plasma\bin\plasma.exe
```

Verifies SHA256SUMS before install; rotates the running binary by rename.
**Nodes older than v0.11.0 lack the update command** — bootstrap those
manually once (§2.2), then self-update forever.

### 4.10 Ask the brain

```powershell
plasma ask --prompt "critical alerts" --events C:\ProgramData\Plasma\data\events.jsonl
plasma probe --tool plasma_alerts --events C:\ProgramData\Plasma\data\events.jsonl
```

---

## 5. End-to-end drill (validated on WS1/WS2)

See `scripts/identity-drill.ps1` — it runs a 60s tap window, trips the
base64 + DNS rules, pulls WHIDS, pushes the drill domain into WHIDS,
restarts, re-drills for a WHIDS alert, then collects everything:

```powershell
.\identity-drill.ps1 -PlasmaExe C:\ProgramData\PlasmaSetup\plasma-0.11.1-windows-x64.exe
```

Expected: tap matches on `ps-base64-decode` (T1027) and
`dns-tunnel-domain-top` (T1071.004); after push+restart, a WHIDS alert
criticality 9 signature "Plasma IOC Feed". Desk-side:

```bash
plasma fleet scan --inventory fleet.json --case drill --window 86400
# lateral_hop 9/10 when the same account appears on 2 hosts
```

---

## 6. Safety model (memorize this)

1. **Detect-only sensors.** WHIDS v1.7.0 has no kill/block actions; the
   tap writes matches only; nothing auto-responds.
2. **Human-gated response.** Actuate = dry-run first + `--apply --plan <dry-run id>` (apply refuses without the id of a seen dry-run for the same action+target) +
   `--reason` mandatory + journaled verified undo.
3. **Lockout-proof.** Protected services/processes/accounts refused;
   isolation keeps RDP/WinRM alive.
4. **Lake-less.** Matches only, capped rows, on-device scoring. Raw
   streams die with the process.
5. **Model is advisory.** The neuralOS brain selects read-only probes and
   never executes anything.

---

## 7. Troubleshooting (field lessons, each one bit us)

| Symptom | Root cause | Fix |
|---|---|---|
| WHIDS stuck StartPending forever, healthy-looking log | deterministic go-runtime hang in WHIDS v1.7.0 channel-set iteration on some boxes (WS1) | open issue — run MINIMAL mode (identity+tap carry detection); document in config.json |
| WHIDS "Expecting rule version >= 2.0.0" / "already exists" | schema-2.0.0 or duplicate-name gene rules | gene schema **1.0.0** only; push replaces the file (v0.8.2+) |
| WinRM reachable but auth always denied | `SeNetworkLogonRight` stripped / Administrator disabled / listener never activated | SSM: `winrm quickconfig -force`, `Enable-LocalUser`, secedit fix `SeNetworkLogonRight = *S-1-5-32-544,*S-1-5-11`, reboot |
| ETW tap "no providers resolved" | TDH provider names differ from channel names | Security channel = `Microsoft-Windows-Security-Auditing` |
| Security audit events invisible to ETW tap | audit events are not re-emitted to realtime ETW | use `plasma identity pull` (Event Log API) |
| JSON lines break in transit with `â€"` mojibake | PS 5.1 console codepage mangles non-ASCII | tap reads files as base64 bytes; keep descriptions ASCII |
| `Get-Content -Raw -Tail` error | PS 5.1 forbids both together | use `-Tail` alone |
| config.json unparsable, health config fail | PS 5.1 `Set-Content -Encoding UTF8` writes BOM | rewrite without BOM; health reads utf-8-sig now |
| `Remove-Item` hangs on junctions | PS 5.1 non-interactive reparse-point bug | junction removal via `cmd /c rmdir` or `[IO.Directory]::Delete` |
| `net`/`reg` "cannot find file" on a node | broken Python wrappers shadow PATH | use `C:\Windows\System32\reg.exe` full path |
| WinRM PS `-Command "..$var.."` empty | double-quote expansion | single-quote the payload, double inner quotes |
| GitHub asset 404 | repo private | PAT with `Authorization: Bearer` + octet-stream Accept |
| installer "target exists" | crashed prior upgrade | `install --force` |
| driver StopPending after Sysmon reinstall | dirty shutdown mid-install | clean reboot, then reinstall |

---

## 8. Ops quick reference (cheat sheet)

```
INSTALL     plasma install [--force] [--skip-whids] [--require-whids]
HEALTH      plasma health                # ok/degraded/down + checks
WATCH       plasma watch once            # sweep + notify (needs notify.json)
DRIFT       plasma drift record|score --question attest
OBSERVE     plasma observe attest|sketch|edges|explain|pslogs|attackmap|...
TAP         plasma tap list|selftest|run --providers p,w,d --for 5m
IDENTITY    plasma identity pull --events store.jsonl --since 60
WHIDS       plasma whids pull|push|status --root 'C:\Program Files\Whids'
ACTUATE     plasma actuate apply <action> --target X --reason Y [--apply --plan <id>]
            plasma actuate undo --id N --apply | journal
FLEET       plasma fleet scan|report --inventory fleet.json --case NAME
UPDATE      plasma update check|apply --token-env PLASMA_GITHUB_TOKEN
ASK         plasma ask --prompt "..." --events store.jsonl
```
