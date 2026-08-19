# Lab A — the live knock on WS1 and WS2

> Goal: prove three things on your real estate — (1) RMAgent can ask a named
> question, (2) a silent box becomes a hole, (3) you will not hammer the door.
> This is Census, not the hunt. attest only.

## What you need

| Item | Value |
|---|---|
| Jump host | your laptop (Python 3.11+, pywinrm) |
| Witness 1 | WS1 `44.197.31.152` — Administrator |
| Witness 2 | WS2 `52.3.242.251` — Administrator |
| Door | WinRM 5985, Basic, AllowUnencrypted (workgroup lab) |
| Inventory | `estate.yaml` (copy of `assets/inventory.example.yaml`) |
| Credentials | `RMAgent_WS1_PASS`, `RMAgent_WS2_PASS` env vars |

## Step 1 — both doors open

```bash
export SKILL_DIR=~/.claude/skills/rmagent-windows
python3 "$SKILL_DIR/scripts/census.py" --inventory ./estate.yaml
```

Expected (both alive, ~1–2 s each):

```
[census 2026-08-19T19:49:00Z] 2 witnesses
  ok   ws1   alive=True admin_fail_60s=0 admin_ok_5m=0 local_admins=2 sys_conns=4
  ok   ws2   alive=True admin_fail_60s=0 admin_ok_5m=0 local_admins=2 sys_conns=1
```

The raw claim (no log dump) looks like:

```json
{"skill":"attest","host":"EC2AMAZ-8NK9FUP","utc":"2026-08-19T...","alive":true,
 "last_boot":"...","track":["Administrator","SYSTEM"],"admin_failed_60s":0,
 "admin_ok_5min":0,"local_admin_count":2,"system_remote_conns":4}
```

If either box is silent now — stop. You do not have a door yet; fix WinRM before
continuing. Do **not** go on.

## Step 2 — arm the restore, then silence WS2

On WS2 (RDP / an admin shell you already have), schedule the door to reopen,
then close it once:

```powershell
# book the unlock FIRST (runs as SYSTEM in 3 min even if your session dies)
$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
  -Argument '-NoProfile -Command "Start-Service WinRM"'
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(3)
Register-ScheduledTask -TaskName RMAgentRestoreWinRM -Action $action -Trigger $trigger `
  -RunLevel Highest -User SYSTEM -Force
# now close the door once
Stop-Service WinRM -Force
```

## Step 3 — ask once, write the hole

```bash
python3 "$SKILL_DIR/scripts/census.py" --inventory ./estate.yaml --case-dir ./cases/lab-a
```

Expected:

```
[census 2026-08-19T19:51:00Z] 2 witnesses
  ok     ws1     alive=True admin_fail_60s=0 ...
  CRITICAL ws2   hole — unreachable: ...  (misses=2)   # after a second run
```

One ask. 25 s timeout. **No retry.** The case folder `./cases/lab-a/holes.jsonl`
now contains:

```json
{"t":"2026-08-19T19:51:..Z","asked":"ws2 attest","empty":true,"why":"2 missed check-ins: unreachable: ..."}
```

That is the product: `asked / empty / why`, not "the server is down."

## Step 4 — restore, confirm

~3 minutes later the scheduled task restarts WinRM. Confirm:

```bash
python3 "$SKILL_DIR/scripts/census.py" --inventory ./estate.yaml
```

Both `ok` again. Do not leave WS2 with WinRM off.

## Pass / fail

- **Pass** — two claims in round 1, one hole in round 2, `Security.evtx` never
  left either box, one ask with no retry, restore booked before you closed the
  door. You can read the case aloud in two minutes.
- **Fail** — you tight-looped WS2, copied a log home "to debug," used a second
  door, called the timeout "nothing happened," or left WinRM off.

## What this proves for Phase 0

RMAgent can ask a named question, a silent box is an answer, and the hunter
discipline holds. Only then does Hunter (`examples/walk-administrator.md`)
make sense.
