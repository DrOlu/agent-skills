---
name: rmagent-dfir
description: >
  Digital Forensics & Incident Response for the Windows estate — the
  acquisition and analysis layer of the RMAgent family. Pull-based, read-only,
  allowlisted DFIR questions over WinRM (process volatility, live connections,
  deep persistence, Security-log triage, USN journal, Shimcache, USB history)
  plus parameterized chunked file acquisition with SHA256 chain-of-custody on
  every artifact. A super-timeline merges everything into one sorted tape; a
  one-page IR report is generated from the case directory with the chain
  verified. Laya (offline System One) routes each collection step; needle
  extracts fields offline. Use when a finding needs forensic response —
  process triage, persistence sweeps, artifact acquisition, timeline building,
  IR reporting — on boxes you administer. Nothing is ever written to the
  witness; full memory acquisition is out of scope by design.
---

# rmagent-dfir — pull-based DFIR for the Windows estate

The **acquisition and analysis layer** of the RMAgent observatory. `rmagent-so`
detects, `rmagent-actuate` contains — this skill **acquires evidence and
builds the case**: process volatility, live connections, deep persistence,
log triage, USN journal, Shimcache, USB history, timeline, and hashed
file acquisition — all pulled over the same WinRM door, all read-only,
all chained.

## The constitution (same as the family, plus forensics)

- **Pull-only, read-only.** Every question runs built-in read-only tools.
  The witness never sees a write. Nothing is installed. Nothing deleted.
- **Allowlisted questions only** — nine named DFIR questions; no arbitrary shell.
- **Capped answers** (32 KB, signal-aware) — oversized pulls become holes.
- **Every artifact is hashed and chained.** Per-chunk + full-file SHA256 on
  acquisition; an append-only chain-of-custody journal whose verification is
  the court-readiness test.
- **Parameterized acquisition is validated twice** — Python-side (drive-absolute,
  no metacharacters, ≤260 chars) and again inside the payload.
- **Your estate only.** No tight retry on a silent host. Credentials via
  scrt/env/`~/.rmagent/creds.json` — never in the inventory.
- **An empty answer is a hole, not a clean answer.** Blank field beats a guess
  (needle tier included).

## The DFIR lifecycle this skill serves

```
DETECT (rmagent-so) → TRIAGE (Jev collect_scope) → ACQUIRE (dfir sweep/collect)
  → ANALYZE (timeline + report) → CONTAIN (rmagent-actuate) → REPORT
```

## The questions

| Question | Returns | Must NOT return |
|---|---|---|
| `vol` | process snapshot (pid/ppid/name/cmd/start) + suspicious indicators (orphan, user-writable path, masquerade) + lsass foreign-module count | a full process dump with all modules |
| `conn` | established/bound TCP with owning process, external endpoints, UDP count; loopback pairs counted not listed | the whole connection table |
| `persist` | Run/RunOnce values, non-Windows services, non-Microsoft tasks, WMI filter names, IFEO debuggers, Winlogon, BITS jobs | every autostart on the box unfiltered |
| `logtriage` | counts for 4624/4625/4648/4672/4688/4698/7045/4720/4726/4732/1102, failed-logon top users+sources, new services/users/groups | raw event rows beyond the cap |
| `usn` | USN journal tail filtered to interesting reasons (new/delete/rename) under user-writable paths | the entire journal |
| `appcompat` | Shimcache (AppCompatCache) blob, base64, capped — parsed on the jump host | parsed rows on-box |
| `usbhist` | USBSTOR device + serial history, MountedDevices | vendor blobs |
| `ircollect` | ONE chunk of ONE file: base64 + per-chunk SHA256 + whole-file SHA256 + size/mtime/chunks | anything but the asked path |
| `irhash` | SHA256 + size + mtime for a semicolon-separated file list | directory walks |

`ircollect`/`irhash` are **parameterized** (they take a validated path); every
other question is fixed. `dfir.py` validates witness paths against injection
before templating, and the payload re-validates.

## Laya tier 1 — offline decision routing

`decisions/collect_scope.json` routes each collection step (volatility order
enforced: vol/conn before persist/logtriage before usn/appcompat before
ircollect) and `decisions/ir_priority.json` reads the collected evidence
(exfiltration risk, lateral movement, response verdict). Both run **offline
through Laya** (`scripts/laya_decide.py`) — the air-gapped estate keeps its
judgment tier. Confidence below 0.5 is flagged ESCALATE; verdicts are advisory;
watch-only rules unchanged.

## Needle tier 0 — offline extraction

`scripts/needle_extract.py` normalizes rigid fields out of fragments
(`count:int`, `source_ip:ip` — validated, blanked when untrustworthy);
`scripts/needle_drift.py` scores today's answers against recorded baselines
(`record`/`score`/`list` under `~/.rmagent/needle-drift/`).

## Scripts

| Script | Role |
|---|---|
| `scripts/lib.py` | Grain wrapper over rmagent-core — ALLOWED = the DFIR grain, no others |
| `scripts/dfir.py` | CLI: ask / sweep / collect / hash / scope / timeline / chain / report |
| `scripts/questions/windows/*.ps1` | The nine payloads (budget-checked ≤3.5 KB each) |
| `scripts/chain.py` | Append-only chain-of-custody; `verify` recomputes every hash |
| `scripts/timeline.py` | Merge answers + acquisitions + chain into timeline.jsonl/CSV |
| `scripts/report.py` | IR_REPORT.md skeleton — known / holes / open actions |
| `scripts/laya_decide.py` | Offline decision matrices (Laya System One model) |
| `scripts/needle_extract.py`, `needle_drift.py` | Offline tier-0 helpers |
| `scripts/test_dfir.py` | Pure-logic test suite (no witness needed) |

## Usage

```bash
# one question
python3 scripts/dfir.py ask --inventory estate.yaml --witness ws1 --question vol --case cases/ir-001
# full sweep — every question, chained
python3 scripts/dfir.py sweep --inventory estate.yaml --witness ws1 --case cases/ir-001
# what to collect next (Laya, offline)
python3 scripts/dfir.py scope --finding "new local admin + SYSTEM task on ws1" --case cases/ir-001
# acquire a suspicious file — chunked, hashed, receipted, chained
python3 scripts/dfir.py collect --inventory estate.yaml --witness ws1 \
  --path "C:\\Users\\svc\\AppData\\Roaming\\s.exe" --case cases/ir-001
# timeline + report + chain verification
python3 scripts/dfir.py timeline --case cases/ir-001
python3 scripts/dfir.py report  --case cases/ir-001
python3 scripts/dfir.py chain   --case cases/ir-001 --verify
```

Inventory: same format as rmagent-windows; the witness must advertise the
dfir skills it answers (`skills: [vol, conn, persist, logtriage, usn,
appcompat, usbhist]` — `ircollect`/`irhash` go through dfir.py directly).

## Non-negotiables

- **Read-only on the witness.** Acquisition copies; it never quarantines,
  never cleans, never edits. Response belongs to rmagent-actuate.
- **Chain before claim.** Evidence with a broken chain is *not court-ready*;
  `chain --verify` failing invalidates the case.
- **No full memory acquisition.** Over WinRM at a 32 KB cap that would be
  theater. `vol` gives indicators; a real memory image needs a proper
  acquisition tool and is explicitly out of scope.
- **Holes are honest.** A Shimcache blob past the cap is truncated *and
  labeled*; a field needle cannot trust is blank; a silent witness is a hole.
- **Validate, then validate again.** Witness paths are rejected in Python and
  re-checked in PowerShell.
- **Laya verdicts are advisory.** The operator reads IR_REPORT.md and decides.

## Limits (documented, not hidden)

- Shimcache parsing is a tolerant pure-Python reader — formats vary by build;
  a parse failure is a hole, not zero findings.
- The USN journal tail is a *sample* (last filtered rows), not the journal.
- `ircollect` reads files the WinRM principal can read; protected files are
  holes with the reason.
- Registry hives are never loaded/modified on-box; Amcache-style parsing
  needs offline hive processing (out of scope by design).
