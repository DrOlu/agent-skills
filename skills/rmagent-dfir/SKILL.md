---
name: rmagent-dfir
description: >
  Digital Forensics & Incident Response for the Windows estate — the
  acquisition and analysis layer of the RMAgent family. Pull-based, read-only,
  allowlisted DFIR questions over WinRM: process volatility, live connections,
  deep persistence, Security-log triage, exfiltration surface (staged archives,
  cloud-sync, SMB/RDP transfer), USN journal, Prefetch program-run, Recycle Bin,
  browser artifacts, mailstores/Outlook traces, Shimcache, Amcache probe, USB
  history, and a bounded 15s live ETW window on PowerShell activity
  (livewindow — built-in logman/Get-WinEvent, with its temp-write carve-out
  disclosed in every answer) — plus parameterized chunked file acquisition with
  SHA256 chain-of-custody on every artifact. Browser/sqlite and Amcache
  artifacts are parsed OFFLINE from pulled copies, never on the witness. A
  super-timeline merges everything into one sorted tape; a one-page IR report
  is generated from the case directory with the chain verified. Laya (offline
  System One) routes each collection step; needle extracts fields offline. Use
  when a finding needs forensic response — process triage, persistence sweeps,
  exfil/browsing/email artifact collection, short-lived script capture, timeline
  building, IR reporting — on boxes you administer. Nothing is ever written to
  the witness except livewindow's small, disclosed, self-cleaning trace file;
  full memory acquisition is out of scope by design.
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
  (Single documented exception: `livewindow`'s temp trace file — see the
  carve-out section below.)
- **Allowlisted questions only** — sixteen named DFIR questions; no arbitrary shell.
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

## The write carve-out (livewindow only)

Every question in this skill is read-only **except one**: `livewindow` opens a
bounded live ETW tap (the Model-1 prototype for real-time capture). Its write
is small, deliberate, and disclosed *in the answer itself*:

1. **What is written:** one `.etl` trace file under `$env:TEMP` (`rwLW*.etl`),
   created by the built-in `logman.exe` — no directories, no other paths.
2. **For how long:** 15 seconds (the ask holds the window open in-band).
3. **How it ends:** `logman stop` in-band, the file deleted, `removed` and
   `session_stopped` booleans reported in `carve_out`. Stale `rwLW*` sessions
   from a previous timed-out run are reaped at the start (`stale_stopped`).
4. **What never happens:** no installs, no services, no persistence, no writes
   outside `%TEMP%`, no providers beyond the one allowlisted GUID
   (Microsoft-Windows-PowerShell).

If `carve_out.removed` is false, the carve-out FAILED and the answer says so —
a hole, not a shrug. The test suite enforces this contract (`test_dfir.py`,
section 3) instead of pretending the payload is read-only.

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
| `exfil` | recent archives (zip/7z/rar/tar/gz) under user-writable paths within `$SinceHours`, cloud-sync roots, SMB sessions/opens, RDP session events | file contents; a recursive whole-disk walk |
| `procrun` | Prefetch run evidence — recent .pf names + last-run times, LOLBins flagged | binary .pf parse (names/times only) |
| `recyclebin` | `$I` records parsed on-box: original path, size, deletion time (v1 + v2) | file contents from the bin |
| `browser` | browser-artifact discovery — Chrome/Edge/Brave/Vivaldi + Firefox profile files with kind/size/mtime | history rows on-box (sqlite) — pull the file, parse OFFLINE |
| `email` | PST/OST/NST mailstore inventory, Outlook profile registry traces (001f6700 = PST path), loose .msg/.eml | mail content; deep mailbox walks |
| `amcpull` | Amcache.hve probe — existence/size/mtime/SHA256/readability | on-box hive parse — pull via ircollect, parse OFFLINE |
| `livewindow` | 15s live ETW tap on the PowerShell provider (logman + Get-WinEvent, built-in): event rows with LOLPattern flags, plus full carve-out disclosure | trace files kept, standing sessions, providers outside the one allowlisted GUID |
| `ircollect` | ONE chunk of ONE file: base64 + per-chunk SHA256 + whole-file SHA256 + size/mtime/chunks | anything but the asked path |
| `irhash` | SHA256 + size + mtime for a semicolon-separated file list | directory walks |

`ircollect`/`irhash` are **parameterized** (they take a validated path); every
other question is fixed. `dfir.py` validates witness paths against injection
before templating, and the payload re-validates.

## Laya tier 1 — offline decision routing

`decisions/collect_scope.json` routes each collection step — `next_collection`
returns a TIER (volatility order enforced: vol/conn before persist/logtriage/
exfil before fsartifacts/usertifacts before deepreg before ircollect; a group
choice means run its named questions) and `artifact_focus` picks one artifact
family (browser/email/exfil/procrun/recyclebin/amcpull) when a deep dive is
warranted. `decisions/ir_priority.json` reads the collected evidence
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
| `scripts/questions/windows/*.ps1` | The fifteen payloads (budget-checked ≤2.4 KB each) |
| `scripts/chain.py` | Append-only chain-of-custody; `verify` recomputes every hash |
| `scripts/timeline.py` | Merge answers + acquisitions + chain into timeline.jsonl/CSV |
| `scripts/report.py` | IR_REPORT.md skeleton — known / holes / open actions |
| `scripts/laya_decide.py` | Offline decision matrices (Laya System One model) |
| `scripts/needle_extract.py`, `needle_drift.py` | Offline tier-0 helpers |
| `scripts/browser_parse.py` | Offline sqlite reader for ircollect'd Chromium History / Firefox places copies |
| `scripts/amcache_parse.py` | Offline tolerant regf reader for an ircollect'd Amcache.hve copy |
| `scripts/test_dfir.py` | Pure-logic test suite (no witness needed; includes synthetic sqlite + regf fixtures) |

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
dfir skills it answers (`skills: [vol, conn, persist, logtriage, exfil, usn,
procrun, recyclebin, browser, email, appcompat, amcpull, usbhist, livewindow]` —
`ircollect`/`irhash` go through dfir.py directly).

Offline parse workflow (sqlite/hive artifacts never parse on the witness):

```bash
python3 scripts/dfir.py collect --inventory estate.yaml --witness ws1 \
  --path "C:\\Users\\a\\AppData\\Local\\Microsoft\\Edge\\User Data\\Default\\History" --case cases/ir-001
python3 scripts/browser_parse.py cases/ir-001/collected/ws1__History --out cases/ir-001/browser.json
python3 scripts/dfir.py collect --inventory estate.yaml --witness ws1 \
  --path "C:\\Windows\\appcompat\\Programs\\Amcache.hve" --case cases/ir-001
python3 scripts/amcache_parse.py cases/ir-001/collected/ws1__Amcache.hve --out cases/ir-001/amcache.json
```

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
- Amcache: the hive is never loaded on-box. `amcpull` probes it read-only;
  the pull goes through `ircollect` (large hives over slow links may be
  impractical — the probe reports size/hash so the operator decides), and
  `amcache_parse.py` is a tolerant offline regf reader — unknown `f`-value
  layouts are reported as strings + version, never guessed fields.
- Browser history/downloads are parsed OFFLINE from ircollect'd copies;
  a locked or absent browser on the witness is just an empty list.
- `email` mailstore discovery is bounded (Outlook dir + Documents depth 2);
  mailstores on other drives or deeper trees are holes by design.
- The USN journal tail is a *sample* (last filtered rows), not the journal.
- `ircollect` reads files the WinRM principal can read; protected files are
  holes with the reason.
- Registry hives are never loaded/modified on-box.
