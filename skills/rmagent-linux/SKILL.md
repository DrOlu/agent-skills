---
name: rmagent-linux
description: >
  Pull-based remote-witness habit for Linux and macOS hosts — the Linux sibling
  of rmagent-windows. Same philosophy: pull-only, allowlisted questions, no
  agent install, watch-only (Phase 0), capped answers, holes instead of dumps.
  Five questions (attest, sketch, edges, explain, attackmap) over SSH reading
  journald/auth.log/ss/systemd/cron. Use when the estate grows beyond Windows
  so the security observatory is actually multi-plane. macOS paths documented
  as experimental.
---

# rmagent-linux — Pull-based remote witness for Linux/macOS hosts

The Linux sibling of `rmagent-windows`. Same philosophy: **pull-only,
allowlisted questions, no agent install, watch-only (Phase 0), capped answers,
holes instead of dumps.**

Use when the estate grows beyond Windows — a Mac jump host, a Linux app box —
so the observatory is actually multi-plane instead of Windows-only.

## Non-negotiables (identical to rmagent-windows)

- **Watch only.** No `actuate`. No `systemctl stop`, no `usermod`, no firewall edits.
- **Allowlisted questions only** — never an arbitrary shell.
- **Capped answers** (32 KB) — oversized pulls become holes, never a lake.
- **Your estate only.** No box you do not administer.
- **No tight retry** on a silent host.
- **Credentials never in the inventory file** — env or `~/.rmagent/creds.json`.

## The five questions

| Question | Payload | What you get | What you must NOT get |
|---|---|---|---|
| **Alive?** (attest) | `attest.sh` | host, utc, uptime, load, failed sudo in window, root logins 5m, users in wheel/sudo group | full auth.log |
| **Anything odd?** (sketch) | `sketch.sh` | new users 24h (from /etc/passwd mtime), users added to sudo group, world-writable files in /etc, SUID binaries changed recently | raw log lists |
| **Who did they touch?** (edges) | `edges.sh` | accepted SSH logins (time, user, src IP) + sudo escalations + outbound conns by root, capped | the whole connection table |
| **What changed?** (explain) | `explain.sh` | user/group changes, new cron entries, new systemd units, package installs in window, auditd rule changes | the whole journal |
| **What persistence exists?** (attackmap) | `attackmap.sh` | cron for all users, systemd timers, shell rc files touched recently, authorized_keys mtime, /etc/ld.so.preload | the whole filesystem |

Every payload runs as ONE non-interactive `bash -c` over SSH, emits ONE JSON
object, and is capped. `journalctl`/`grep` output is trimmed to `$Limit`.

## Setup (one time)

```bash
# 1. Key-based SSH from the jump host to each Linux witness
ssh-copy-id user@linux-box

# 2. Inventory — same shape as the Windows skill
cat > estate-linux.yaml <<'YAML'
witnesses:
  - id: lx1
    name: App server
    plane: endpoint
    os: linux
    door: ssh
    address: 10.0.0.20
    user: deploy
    skills: [attest, sketch, edges, explain, attackmap]
    track: [root, deploy]
YAML

# 3. Verify
python3 scripts/census.py --inventory estate-linux.yaml
```

`sudo` questions need passwordless sudo for the *specific* read-only commands
in the payloads (`journalctl`, `grep`, `stat`). If sudo needs a password, the
payload returns a hole saying so — it never prompts.

## Scripts

| Job | Script | Notes |
|---|---|---|
| Census | `scripts/census.py` | reuses the Windows engine; SSH door |
| Walk | `scripts/hunt.py` | same; writes path.json + holes.jsonl |
| Correlate | `scripts/correlate.py` | joins Linux answers with Windows ones |
| Drift | `scripts/drift.py` | baseline + diff for admins/sudoers |
| Allowlisted payloads | `scripts/questions/linux/*.sh` | attest / sketch / edges / explain / attackmap |

The engine (`lib.py`) is shared with rmagent-windows — only the door differs
(`ssh` instead of `winrm`) and the payload directory (`questions/linux/`).

## What this skill will NOT do

- No `actuate` — no service restarts, user changes, firewall edits.
- No journal export. No `tar` of `/var/log`. No packet capture.
- No witness for a box you do not administer.
- No replacement for auditd/EDR — this is the pull-based witness, not the sensor.

## Fidelity gaps (documented, not hidden)

- **No persistent ring.** Like Windows `edges`, `edges.sh` reads the current
  state + recent journal — a sub-second connection that closed before the poll
  is missed. `auditd` with `auditctl -a always,exit -F arch=b64 -S connect`
  is the resident answer (an estate change, not Phase 0).
- **journald retention varies.** `SystemMaxUse` may keep hours or weeks;
  payloads clamp to `$SinceHours` and cap at `$Limit` regardless.
- **macOS**: works for attest/sketch/edges via `log show`/`last`; `attackmap`
  checks launchd dirs instead of systemd. Untested on this estate — treat as
  experimental until live-validated.
