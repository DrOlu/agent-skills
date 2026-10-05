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

## Needle tier 0 — offline extraction and drift

Alongside the Laya matrices, every skill in this family can call
**needle** — a 121M on-device model (Cactus Compute Needle, ~35 MB, no
network, no keys, ~100 MB RAM) installed once on the jump host, never on
the witnesses. It is the free tier of the judgment stack: needle extracts
and compares offline, Laya judges, the LLM reasons.

Two scripts ship in `scripts/`:

- `needle_extract.py` — typed field extraction from a witness fragment
  (`count`, `source_ip`, …). Rigid tokens (numbers, IPs) are reliable;
  semantic fields are not, so the wrapper validates what it can (`:ip`,
  `:int`) and blanks anything it cannot trust — never a guess.
  ```bash
  echo "<attest answer>" | scripts/needle_extract.py user count:int source_ip:ip --json
  ```
- `needle_drift.py` — baseline-drift detection via needle's 3072-dim
  embeddings: record what an answer normally looks like, score today's
  answer against it (similar / drifted / changed, thresholds calibrated
  empirically). Separates shape and topic, not field values — value drift
  stays the job of the field rules and correlate joins.
  ```bash
  echo "<routine answer>" | scripts/needle_drift.py record <host>-<question>
  echo "<today's answer>" | scripts/needle_drift.py score <host>-<question>
  ```

The engine runs in-process on the jump host (the wrapper finds a Python
with `cactus-needle` — set `NEEDLE_PYTHON` if it lives elsewhere). No port
is opened, nothing is installed on any witness, and the baselines are
kilobyte holes under `~/.rmagent/needle-drift/`, not a lake. On an
air-gapped estate this tier keeps working — and the judgment tier with it: Laya is offline too (pre-seed its HF-cache checkpoint on air-gapped hosts), so no matrix judgment waits for a connected session.

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

## Laya-assisted triage and hunt routing

Recurring judgment calls can be made by a fast, typed decision model (Laya, via
the `use-laya` skill) so they are consistent across sessions and honest about
uncertainty. Two matrices live in `decisions/` — review and edit them like any
other allowlist:

- `triage.json` — score a witnessed finding (suspicious / severity / next).
- `hunt_route.json` — pick the next witness question from this skill's
  allowlisted set (or hand the hunt to the LLM when unsure). It can never
  introduce a question outside the allowlist, and it changes nothing about
  watch-only.

```bash
echo "<finding fragment>" | scripts/laya_decide.py triage
scripts/laya_decide.py hunt_route --state-file hunt.json
```

Policy (in each matrix): confidence below 0.5 is flagged ESCALATE — route those
to the LLM or the operator instead of acting on them. Verdicts are advisory;
the standing rules (blind check, capped answers, watch-only) are unchanged.

## Scripts

| Job | Script | Notes |
|---|---|---|
| Census | `scripts/census.py` | SSH door; 2 misses = Critical; history in `~/.rmagent` |
| Walk | `scripts/hunt.py` | identity grain only; writes `~/.rmagent/cases` |
| Drift | `scripts/drift.py` | baseline + diff for sudoers / suid / blind_count |
| Allowlisted payloads | `scripts/questions/linux/*.sh` | attest / sketch / edges / explain / attackmap |

The engine (`lib.py`) is shared with rmagent-windows — only the door differs
(`ssh` instead of `winrm`) and the payload directory (`questions/linux/`).

## What this skill will NOT do

- No `actuate` — no service restarts, user changes, firewall edits.
- No journal export. No `tar` of `/var/log`. No packet capture.
- No witness for a box you do not administer.
- No replacement for auditd/EDR — this is the pull-based witness, not the sensor.

## Enterprise scope & sizing (Linux/macOS estate)

- **Fleet shape:** one jump host fans out over SSH; witnesses need nothing
  installed (POSIX sh + coreutils only — `journalctl`, `last`, `getent`).
  Budget ~1 SSH round-trip per witness per question; a 100-host sweep at 8 s
  connect budget is ~15 min serialized — parallelize 8–10 wide for ~2 min.
- **journald sizing (the retention dial):** `SystemMaxUse=` governs how far
  back `edges`/`explain` can see. Recommendation for app servers:
  `SystemMaxUse=2G` + `MaxRetentionSec=30day` (a journald vacuum mid-incident
  is a hole you chose). Check with `journalctl --disk-usage`.
- **auth.log vs journal:** Debian-family splits SSH auth into `/var/log/auth.log`
  (logrotate: weekly default → raise to `rotate 8` for 8 weeks) while
  RHEL-family uses journald. Payloads read both; know which your estate keeps.
- **Sudo escalation watch:** `sudo_accounts` from `attest` is your baseline —
  a growth of 2+ between sweeps is a drift finding, wire `sweep` output into
  your diff/review.
- **macOS:** attest/sketch/edges work via `log show`/`last`; treat `attackmap`
  as experimental until validated on your fleet.

### No-Python operation (bash-native kit)

`scripts/ops/rmagent-ops.sh` runs the attest probe over plain SSH from any
bash 3.2+ jump host — **no Python on jump host or witness**:

```bash
# one witness
SINCE_HOURS=2 ops/rmagent-ops.sh watch web01.corp deploy      # JSON, exit 1 if blind
# whole fleet (inventory: "host[:port] [user]" per line)
ops/rmagent-ops.sh sweep estate.txt | column -t -s$'\t'       # TSV board
# cron it (5-min heartbeat, page on non-zero exit)
*/5 * * * * /opt/rmagent/ops/rmagent-ops.sh watch db01.corp >> /var/log/rmagent/db01.jsonl
```

Exit codes: 0 = attest ok · 1 = BLIND/unreachable (page) · 2 = usage error.
The remote probe needs only `sh` + coreutils — enterprises that mandate
PowerShell on the jump host can drive Linux witnesses via
`plink`/OpenSSH-for-Windows the same way (the probe body is portable POSIX sh).

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
