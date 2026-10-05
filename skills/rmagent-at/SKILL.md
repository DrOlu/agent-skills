---
name: rmagent-at
description: >
  The App Tracing skill — resident, on-device application tracing using
  Windows' built-in ETW (Event Tracing for Windows). Enterprise-scale ring
  buffers (512 MB default, tunable) that start at boot and live in kernel
  memory: circular, bounded, old events overwritten — no lake, no agent
  install, no SDK. Captures .NET EventSource, HTTP.sys, IIS, kernel network
  (every TCP connection with PID), and process lifecycle (create/exit with
  full command line) — all providers already on every Windows box. Pull
  questions read the ring on demand: apptrace (events), appslow (slow
  requests), apperrors (errors/warnings), appnet (connections), appproc
  (process lifecycle). The AutoLogger setup is a MOP-level persistent
  change, reversible via teardown. Use for application-level observability
  on Windows boxes you administer, with the same pull-only, capped,
  holes-not-dumps constitution as the rest of the observatory.
---

# rmagent-at — The App Tracing skill

Resident, on-device application tracing using Windows' built-in ETW.
**No SDK, no agent install, no lake — the data is already being written;
this skill just asks for it.**

The application-tracing sibling of `rmagent-so` (security questions) and
`rmagent-fr` (the Flight Recorder). Same constitution: pull-only, named
questions, capped answers, holes instead of dumps.

## The architecture

```
┌─────────────────────────────────────────────────────┐
│  APPLICATION (.NET, IIS, HTTP.sys, anything)         │
│  Already emitting into ETW — zero code change        │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│  ETW KERNEL RING BUFFER (AutoLogger session)        │
│  • Starts at BOOT, resident in kernel memory       │
│  • 512 MB default (enterprise scale, tunable)       │
│  • Circular: old events overwritten — no lake      │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│  THE PULL (rmagent pattern — on demand, capped)     │
│  • apptrace / appslow / apperrors / appnet / appproc│
│  • Writes to the case file                         │
└─────────────────────────────────────────────────────┘
```

## Enterprise scale — the ring buffer

The default is **512 MB** for the AppTrace session (256 MB for NetTrace,
128 MB for ProcTrace). At typical event rates that gives **hours to days**
of retention instead of minutes. Everything is tunable:

```bash
# default (512/256/128 MB)
python3 autologger.py --inventory estate.yaml --setup

# grow everything to 1 GB
python3 autologger.py --inventory estate.yaml --setup --resize 1024
```

**Why this is not a lake:** the buffer is *circular*. When it fills, the
oldest events are overwritten. Nothing is retained forever, nothing is
shipped anywhere, and the total footprint is bounded by the buffer size you
chose. It is a ring, not a warehouse.

## The sessions

| Session | Purpose | Ring | Providers (LIVE-VERIFIED 2026-09-04) |
|---|---|---|---|
| `RMAgent-AppTrace` | Application events | 512 MB circular | DotNETRuntime `{E13C0D23-CCBC-4E12-931B-D9CC2EEE27E4}`, HTTP.sys `{DD5EF90A-6398-47A4-AD34-4DCECDEF795F}` |
| `RMAgent-NetTrace` | TCP connections with PID | 256 MB circular | Kernel-Network `{7DD42A49-5329-4832-8DFD-43D979153A88}` |
| `RMAgent-ProcTrace` | Thread/image activity | 128 MB circular | Kernel-Process `{22FB2CD6-0E7B-422B-A0C7-2FAD1FD0E716}` |

**The ring is REAL now (Rev 18).** The original config set `LogFileMode 0x1004`
= APPEND mode — a file that grows to its cap and then the session DIES (found
live: all three sessions Stopped with zero bytes recorded, 4 of 5 provider
GUIDs wrong). Rev 18 uses `logman update -f bincirc -max <MB> -r` — a true
circular file that overwrites oldest-first and restarts into new segments
continuously. Verified live on WS1: sessions Running, `Circular: On`,
ring files at `C:\etw\<name>_000001.etl`.

**⚠️ Rev 19 correction (live-verified on WS2, 2026-10-04): the "-r wraps
forever" promise FAILS at sustained load.** A fault-injection storm filled the
512 MB AppTrace segment in ~26 minutes, and the file then **FROZE IN PLACE**
— mtime stuck, logman still reporting `Running` (a zombie that accepts
nothing), ProcTrace dying outright. Evidence inside the frozen segment is
*preserved* (the wrap never happened), but capture is dead and `Running`
status lies about it. Consequences baked into this skill:

- `ringhealth` now reports the **real segment file** (`<name>_*.etl` glob —
  the old `File Name:` grep returned the base path, so `bytes` was always 0),
  plus `cap_mb`, `mtime_age_min`, `stale`, and a `frozen` verdict
  (Running + segment ≥ 98% of cap). **Frozen counts as blind.**
- `autologger.py --doctor` detects FROZEN/STOPPED rings (`--apply` restarts
  them: `logman stop <n> -ets` — the `-ets` form releases the zombie's ETL
  handle — then `start`).
- `autologger.py --watchdog --apply` installs the same check server-side as a
  5-minute SYSTEM scheduled task (`C:\etw\watchdog.ps1`, 200-line bounded log
  at `C:\etw\watchdog.log`). `--watchdog-status` / `--watchdog-remove`
  manage it. A frozen ring self-heals within 5 minutes instead of silently
  blinding the box for hours.

**Six logman/registry facts learned live** (the setup payload encodes all of
them): Impacket's `reg.py` shadows `reg.exe` (absolute paths mandatory);
`logman create`'s own DCS config SHADOWS the AutoLogger registry values;
providers added via `-p` default to Level 0 / Keywords 0x0 = capture NOTHING
(every provider needs an explicit keyword mask + level); a circular session
without `-r` fills one segment and stops; kernel providers engage their flags
only at trace start; and a teardown must poll for stop before delete or the
next setup hits "Data Collector already exists".

## The questions

| Question | Returns | Must NOT return |
|---|---|---|
| `apptrace` | Recent application events from the ring (provider, id, level, message) | full event dumps |
| `appslow` | Requests/operations over 500ms, sorted slowest-first | all events |
| `apperrors` | Errors and warnings (Level ≤ 3) with counts | full error dumps |
| `appnet` | TCP connections (src → dst), deduplicated | full netflow |
| `appproc` | Process start/end events with command lines | full process list |
| `appsysmon` | Sysmon security telemetry: image SHA256s, LSASS access, image loads, registry sets, Guid-keyed connections | raw Sysmon dump |

### `appsysmon` — the security layer, read not installed

Sysmon is a **separate telemetry plane** from the ETW ring. The ring sessions
(`ProcTrace`, `NetTrace`) capture process and connection *events* from the
kernel. Sysmon adds the **security context** the kernel providers do not emit:

| Sysmon event | What it adds over the ring |
|---|---|
| Event 1 (hashes) | SHA256 of every binary executed — "did this binary ever run here?" is answerable without the file still being present |
| Event 3 (ProcessGuid) | Connections keyed by ProcessGuid, not PID — PIDs are reused, Guids are not |
| Event 7 (image loads) | DLL loads — injection and LOLBin abuse |
| Event 10 (LSASS) | Credential-access attempts the process provider does not see |
| Event 13 (registry) | Registry value sets — the persistence channel ProcTrace misses entirely |

**This skill does not install Sysmon.** It reads the log that is already
running. If Sysmon is absent, the answer carries `sysmon: 'not-installed'`
and empty lists — a hole, not an error, and not a reason to install anything.
Installation is an EDR decision, not a tracing one.

The honest overlap: process create/exit and network connections appear in both
planes. Where they duplicate, the ETW ring is the application view (what ran,
what connected) and Sysmon is the security view (what it was, its hash, its
Guid). Use `appproc`/`appnet` for volume; use `appsysmon` when you need to
tie an action to a specific binary identity.

## Setup (MOP-level — this is a persistent change)

The AutoLogger sessions start at **boot** and run resident. That is a
persistent change to the witness, so it is a MOP-level action, not a Phase 0
question. Everything is reversible:

```bash
# create the sessions (admin)
python3 autologger.py --inventory estate.yaml --setup

# check what's running
python3 autologger.py --inventory estate.yaml --status

# grow the buffers
python3 autologger.py --inventory estate.yaml --setup --resize 1024

# detect frozen-at-cap / stopped rings (dry-run by default)
python3 autologger.py --inventory estate.yaml --doctor
python3 autologger.py --inventory estate.yaml --doctor --apply      # + restart them

# install the self-healing watchdog (5-min SYSTEM task, server-side)
python3 autologger.py --inventory estate.yaml --watchdog --apply
python3 autologger.py --inventory estate.yaml --watchdog-status
python3 autologger.py --inventory estate.yaml --watchdog-remove --apply

# remove everything (stops sessions, deletes registry keys, removes files)
python3 autologger.py --inventory estate.yaml --teardown
```

## Pulling (Phase 0 — the questions are read-only)

```bash
# from hunt.py or the agent
lib.ask(row, "apptrace", since_hours=2, limit=50)
lib.ask(row, "appslow", since_hours=24, limit=20)
lib.ask(row, "apperrors", since_hours=1, limit=30)
```

## Laya-assisted signal triage

Trace excerpts pulled from the rings can be scored by a fast, typed decision
model (Laya, via the `use-laya` skill): is this a real performance or failure
pattern rather than noise, and which subsystem should the next pull focus on?
One matrix lives in `decisions/`:

- `signal_triage.json` — real_pattern (noul) / subsystem (choice) / next
  (choice: hand to the Flight Recorder with a work id, refine the capture, or
  record as noise).

```bash
scripts/laya_decide.py signal_triage --state-file excerpt.json
```

Policy: confidence below 0.5 is flagged ESCALATE — route those excerpts to the
LLM or the operator. Verdicts are advisory; pulling stays read-only and capped,
and the ring configuration is untouched.

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

## Non-negotiables

- **The setup is MOP; the questions are Phase 0.** Creating the sessions
  changes the witness. Reading them does not.
- **The ring is bounded.** You chose the size; the kernel enforces it.
  Nothing is retained beyond the ring.
- **Pull-only questions.** Named, allowlisted, capped, read-only.
- **Never trust a quiet ring.** `ringhealth` is the attest/blind_check of this plane: Stopped AutoLogger → `witness_blind`, not a quiet app.
- **Fully reversible.** `--teardown` stops the sessions, deletes the
  registry keys, and removes the files.
- **Your estate only.**

## Honest limits

1. **The ring overwrites — until it freezes.** A busy box will cycle a 512 MB
   buffer in hours of normal load (or ~26 minutes under a churn storm,
   measured live on WS2 2026-10-04). Under sustained fill the bincirc segment
   FROZE at cap instead of wrapping (Rev 19 correction above): evidence is
   preserved but capture stops silently. Run the watchdog; treat `Running` +
   at-cap as blind. Increase the buffer if you need longer retention — the
   cost is disk (bincirc) rather than kernel memory.
2. **Structured parsing, name-keyed.** `appnet`/`appproc` parse the event's
   XML payload by PROPERTY NAME (Message is null for ETL-file events — the
   original prose-regex parsing saw volume with zero findings and reported
   it as a quiet box). `parse_failures` in every answer makes "N events, 0
   parsed" a hole, not a clean bill.
3. **NetTrace's kernel limitation (found live 2026-09-04).** The
   Kernel-Network provider config verifies correct (Level 255, all keywords,
   Running/Circular) yet Server 2022's AutoLogger delivers no kernel-network
   events to the ring. `appnet` therefore PREFERS the ring and FALLS BACK to
   Sysmon EID 3 (same pull, same box, better source — it also carries the
   process name). If both sources are empty the answer says `source='none'`
   — an honest hole, not a fake clean bill.
4. **ProcTrace carries thread events, not command lines.** The Kernel-Process
   AutoLogger ring delivers thread-start/stop (ProcessID, ThreadID,
   Win32StartAddr) — process command lines and binary hashes live in Sysmon
   Event 1 via `appsysmon`. Stated in the payload itself.
5. **No LLM token counts / prompt text.** This is application tracing, not
   OpenLLMetry. Different layer.
6. **The AutoLogger is a persistent change.** `--setup` is MOP-level:
   dry-run by default, `--apply` required, `--teardown --apply` reverses
   everything (verified: teardown removes DCS + registry keys + ring files).
7. **Big-ring decode cannot be streamed.** Full enumeration of a full
   512 MB ETL takes 10+ minutes — longer than any WinRM/SSH command timeout
   (30 s class). Deep analysis must run SERVER-SIDE (scheduled task /
   persistent session) writing a small JSON summary to disk, which is then
   pulled. A remote full-scan attempt dies mid-flight with nothing produced
   (verified: the WS2 2026-10-04 scanner burned 673 CPU-s and left zero
   output). Cap pulls to bounded `MaxEvents` windows, as the questions do.
8. **Sysmon's own log is a rotating ring too.** 64 MB active file, no
   archives by default → the storm window was UNRECOVERABLE from Sysmon
   50 minutes after it ended (live-verified). `appsysmon` answers near a
   rotation boundary are holes. Enterprise fix: raise retention AND ship
   events off-box (WEF/Splunk/Sentinel) — out of this skill's scope.

## Enterprise sizing & operations (Rev 19)

Everything below is calibrated against the WS2 2026-10-04 fault-injection
storm (BadApp: CPU spin ×2, lock storm, 375 MB leak / 161 threads,
self-connect churn to 19,400 requests, `boom-*` exceptions every ~500 reqs,
client SLOWs 1.5–2.0 s) — the worst-case this design has been measured
against.

### Buffer sizing: measure the rate, size for the retention you need

```
ring_mb = (events_per_sec × avg_event_bytes × retention_seconds) / 1MB × 2
```

Measured anchor points: a churn storm writes AppTrace at **≈20 MB/min**
(512 MB ≈ 26 min); a quiet production box writes **≈1 MB/min or less**
(hours-days per 512 MB). Worked examples:

| Workload class | Events/sec est. | 4 h retention | 24 h retention |
|---|---|---|---|
| Quiet service box (≤1 MB/min) | <50 | 512 MB | 1.5–2 GB |
| Busy app server (5–10 MB/min) | 200–500 | 1.5–2.5 GB | 8–15 GB (don't — see below) |
| Storm/test host (≈20 MB/min) | ~1000 | 5 GB | run tests against a scratch ring |

Practical rules: **(a)** 24 h retention on a busy box is the wrong goal —
the evidence you need within minutes of an incident lives in the newest
10%; **(b)** size for 2–4 h of *your measured* worst case; **(c)** for
tests, accept wrap/loss, or point the session at a scratch directory;
**(d)** disk cost is the bound, not kernel memory.

### The watchdog is mandatory in production

Install it on every witness that runs the rings. Without it the freeze-at-cap
failure is silent (logman says Running; ringhealth's old `bytes=0` bug hid it
completely). With it, worst-case blindness is the task interval (5 min) plus
restart time (~5 s). Enterprise adds: forward `C:\etw\watchdog.log` entries
into your monitoring (a watchdog restart is a *symptom* worth a ticket —
"why did the ring fill?"), and alert on `ringhealth frozen_count > 0`.

### Evidence preservation: freeze is a feature if you copy first

A frozen segment is closed evidence — perfect for copying before restart.
The right sequence on a busy box: **detect at-cap → copy the segment
somewhere durable → restart the session.** The watchdog does detect+restart;
if you need the copy step, run `--doctor` manually (dry-run first) so you can
archive `C:\etw\<name>_*.etl` in between. For incidents, remember:

```
server-side decode (10+ min for a full 512 MB ETL) → JSON summary → pull the
kilobytes. NEVER stream a big ETL over WinRM/SSH. (Honest limit 7.)
```

### Drills

Run a BadApp-style fault injection quarterly (CPU spin + leak + churn +
exceptions for 15 min) and verify: rings fill, watchdog restarts within one
interval, `ringhealth` shows `frozen`/`blind_check=BLIND` if the watchdog is
down, and the decode summary answers "what happened, per minute". An
observability stack that has never been tested under load is a hope, not a
control.

## Relationship to the other skills

| Skill | Plane |
|---|---|
| `rmagent-so` | Security questions (identity-led) |
| `rmagent-fr` | The Flight Recorder (ticket-led tracing of the investigation) |
| `rmagent-at` | **This skill — application tracing (ETW, resident)** |
| `rmagent-ao` | The Agent Observatory (agent census) |
| `rmagent-windows` | The complete Windows skill (so + fr) |
| `rmagent-redteam` | The drill |
| `rmagent-actuate` | Phase 1 response |
| `rmagent-linux` | The Linux/macOS sibling |