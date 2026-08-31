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

| Session | Purpose | Default buffer | Providers |
|---|---|---|---|
| `RMAgent-AppTrace` | Application events | 512 MB | .NET CLR, HTTP.sys, ASP.NET |
| `RMAgent-NetTrace` | TCP connections with PID | 256 MB | Kernel-Network |
| `RMAgent-ProcTrace` | Process create/exit + cmdline | 128 MB | Kernel-Process |

All providers are **built into Windows**. .NET apps, IIS, and anything
using HTTP.sys emit into them with zero code changes. For non-.NET apps,
one line of `EventWriteString` (or a Python ctypes call) joins the party.

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

## Non-negotiables

- **The setup is MOP; the questions are Phase 0.** Creating the sessions
  changes the witness. Reading them does not.
- **The ring is bounded.** You chose the size; the kernel enforces it.
  Nothing is retained beyond the ring.
- **Pull-only questions.** Named, allowlisted, capped, read-only.
- **Fully reversible.** `--teardown` stops the sessions, deletes the
  registry keys, and removes the files.
- **Your estate only.**

## Honest limits

1. **The ring overwrites.** A busy box will cycle a 512 MB buffer in hours,
   not days. Increase the buffer if you need longer retention — the cost
   is kernel memory.
2. **Message-shape parsing.** `appslow` and `appnet` parse the human-readable
   event message for durations and tuples. Providers with structured
   payloads (via `tdh` or manifests) would be more robust — a future
   improvement, noted honestly.
3. **No LLM token counts / prompt text.** This is application tracing, not
   OpenLLMetry. Different layer.
4. **The AutoLogger is a persistent change.** This is stated in every
   place it matters, because it is the one thing in the observatory that
   leaves a footprint on the witness.

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