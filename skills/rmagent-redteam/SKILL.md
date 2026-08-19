---
name: rmagent-redteam
description: >
  Purple-team DRILL for the rmagent-windows skill. Stages reversible
  living-off-the-land (LOTL) artifacts on WS1/WS2 — failed Administrator
  logons, a new local admin, a SYSTEM scheduled task, a new LocalSystem
  service, PowerShell spawns, and a SYSTEM outbound connection — then runs
  rmagent census+hunt to score what it detects, and sends a Telegram alert
  with the detection report. Use to TEST rmagent effectiveness. This is a
  benign drill, not a real attack: every artifact is prefixed RMAgentDrill_
  and is reversible with clean. Requires --confirm. Do NOT use against boxes
  you do not administer.
---

# RMAgent Red-Team (drill)

A **purple-team drill** that stages living-off-the-land artifacts on your Windows estate (WS1/WS2), then runs the `rmagent-windows` skill to score what it detects — and Telegrams you the report. This is how you answer "does rmagent actually work?"

It is a **DRILL, not a real attack.** Every artifact is prefixed `RMAgentDrill_`, uses benign payloads (a network test to `1.1.1.1`, an echo to a temp file), is non-persistent, and is fully reversible with `clean`. It requires `--confirm` and never runs against a box you do not administer.

## The attack this simulates (the Ada story, class 03 "Walk")

The drill stages the exact kind of movement rmagent is built to catch — **identity-led, living-off-the-land, no new malware.** Each artifact maps to a specific rmagent signal:

| Staged artifact | Windows event | rmagent signal it should fire |
|---|---|---|
| 2 failed Administrator logons | 4625 | `attest.admin_failed_60s`, `sketch.admin_failed` |
| New local admin `RMAgentDrill_Test` | 4720 + 4732 | `explain.identity_changes`, `sketch.new_local_admins` |
| New SYSTEM scheduled task `RMAgentDrill_Task` | 4698 | `explain.task_events`, `sketch.new_tasks` |
| New LocalSystem service `RMAgentDrillSvc` | 7045 | `explain.service_events`, `sketch.new_services` |
| PowerShell spawns | 4688 (if Process Creation audited) | `explain.proc_spawns` |
| SYSTEM outbound connection to 1.1.1.1:80 | Sysmon EID3 | `netedges` (reads the Sysmon `Microsoft-Windows-Sysmon/Operational` ring — catches transient conns `edges` misses). Requires `<NetworkConnect onmatch="exclude">` |

## Prerequisites

> **Jump host: macOS, Linux, or Windows.** pywinrm connects to the Windows targets from any. On a non-macOS jump host, the `secrets` scrt master password is provided via `SCRT_PASS` env var or a `~/.scrt_pass` file (macOS uses Keychain automatically). The `winrm_pool.ps1` RunspacePool path needs PowerShell 7.

1. The `rmagent-windows` skill works (census passes on WS1/WS2). See its README.
2. Telegram alerting configured — token `telegram-bot-token` and chat `telegram-chat-id` in the `secrets` scrt store (already present), OR env `RMAgent_TELEGRAM_TOKEN` / `RMAgent_TELEGRAM_CHAT`.
3. Windows credentials — env `RMAgent_<ID>_PASS`, OR the scrt keys `windows-server1-password` / `windows-server2-password` (auto-loaded if env is missing).
4. **Audit subcategories on** (so Windows writes the events to its diary). On each box, run:
   ```powershell
   auditpol /set /subcategory:"Process Creation" /success:enable            # 4688 process spawns
   auditpol /set /subcategory:"Other Object Access Events" /success:enable  # 4698 scheduled tasks
   auditpol /set /subcategory:"Security Group Management" /success:enable   # 4732 group-add (new local admin) — NOT "Account Management" (that's 4720)
   ```
   Without these, three of the six drill signals cannot be detected by any pull-based tool — Windows writes no event. On this estate they are already enabled.
5. **Sysmon NetworkConnect on** (for the transient outbound-connection signal): Sysmon is already installed on WS1/WS2; enable its network-connection ring with a minimal config (`<NetworkConnect onmatch="exclude">` to log all), applied via `Sysmon64.exe -c <config>`. Then the `netedges` question reads the Sysmon EID3 ring. Without it, `system_outbound_conn` shows 0 — a point-in-time `edges` snapshot misses sub-second connections. On this estate it is already enabled.

## Run

```bash
export SKILL_DIR=~/.claude/skills/rmagent-redteam
cp ~/.claude/skills/rmagent-windows/assets/inventory.example.yaml ./estate.yaml

# Full loop: stage -> rmagent census+hunt -> score -> telegram -> clean
python3 "$SKILL_DIR/scripts/redteam.py" run --inventory ./estate.yaml --confirm

# Or step by step:
python3 "$SKILL_DIR/scripts/redteam.py" stage --inventory ./estate.yaml --confirm   # stage artifacts
python3 "$SKILL_DIR/scripts/redteam.py" clean --inventory ./estate.yaml             # remove them
```

`--keep` leaves artifacts staged after a `run` (clean later with `clean`).

## What happens during a `run`

1. **Telegram**: "drill started" message listing the artifacts it will stage.
2. **Stage** `drill.ps1` on each box.
3. **Wait 8s** for events to land in the logs.
4. **Run `rmagent-windows` census + hunt** (1h window) into a case folder.
5. **Score** detected vs staged — compares what rmagent recorded to the 6 expected signals.
6. **Telegram**: a detection report — `Detected (N/6)` with each signal, plus any missed, plus the case name.
7. **Clean** `clean.ps1` on each box (unless `--keep`).
8. **Telegram**: "artifacts cleaned."

## Output you owe the user

After a run, state plainly:
1. **What was staged** (the 6 artifacts).
2. **What rmagent detected** (N/6, with each signal and which rmagent field fired).
3. **What was missed** and *why* (e.g., Process Auditing off → no 4688).
4. **The case path** so the walk can be re-read.
5. **That artifacts were cleaned** (or kept).

## Non-negotiables

- **Authorised estate only.** WS1/WS2, or boxes the operator administers. Never a partner/NIBSS/production-critical box without explicit written consent.
- **`--confirm` required** for `stage` and `run`. No silent staging.
- **Reversible.** `clean.ps1` removes every `RMAgentDrill_*` artifact. Idempotent. Run it after every drill unless you used `--keep`.
- **Benign payloads only.** A network test to `1.1.1.1:80` and an echo to a temp file. No exfiltration, no persistence, no destructive action.
- **Telegram is the alert channel, not a data channel.** Send detection summaries, never credentials, Event Logs, or case contents.
- **Don't compete with EDR.** Defender/CrowdStrike may alert on the drill too — that's good. Coordinate timing if your SOC is staffed.

## Limits

- `proc_spawns` (4688) needs Process Creation auditing on the target. If it shows 0, check `auditpol /get /subcategory:"Process Creation"`.
- `system_outbound_conn` needs the Sysmon NetworkConnect ring enabled (`<NetworkConnect onmatch="exclude">`). The point-in-time `edges` snapshot misses a sub-second connection that already closed; the Sysmon ring persists it. If it shows 0, confirm Sysmon's NetworkConnect config is on.
- The drill runs as Administrator over WinRM, so the staged "failed Administrator logon" events are real 4625s for the local Administrator account.
