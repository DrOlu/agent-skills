# rmagent-at

Grain: request-ish. Questions: apptrace appslow apperrors appnet appproc appsysmon ringhealth.

`ringhealth` Stopped **or frozen-at-cap** AutoLogger = witness_blind, not a quiet app.

---

## Worked case: the WS2 BadApp storm (2026-10-04, live)

A fault-injection app ran on WS2 (EC2AMAZ-C69VULQ) for 11 minutes and the
rings recorded the whole story — then exposed two real defects in the
capture plane. What follows is exactly what each question saw, in order.

### The workload (from the app's own logs — ground truth)

| Fault injected | Peak evidence |
|---|---|
| Self-connect churn | 19,400+ requests, burst every 50 |
| Worker exceptions | `InvalidOperationException: boom-19330` every ~500 reqs |
| Memory leak | 375 MB leaked, **161 threads** at termination |
| Slow requests | client-logged SLOW 1.5–2.0 s |
| Client failures | 132 IOExceptions, 63 connect-timeouts, 58 server resets |
| CPU spin ×2 + lock storm | two `while(true)` threads + a 1 ms lock hammer |

### What the rings did

- **AppTrace (512 MB):** filled to cap at 23:02 (~26 min of mixed load
  including the storm) and **FROZE IN PLACE** — mtime stuck, logman still
  said `Running`. The old `ringhealth` reported `bytes=0` (its `File Name:`
  grep matched the base path, not the `_000001.etl` segment) and
  `blind_check=ok` — a clean bill from a dead ring.
- **ProcTrace (128 MB):** died at cap outright.
- **NetTrace:** 8 KB — the known Server-2022 kernel-net hole; `appnet`
  answered `source='none'` honestly.
- **Sysmon:** running the whole time, but its 64 MB operational log rotated
  and only reached back to 23:37 — the 22:36–22:47 incident window is
  **unrecoverable from Sysmon**. A second rotating ring, same failure shape.

### What the questions saw (before vs after the storm)

- `apperrors` before: `errors=0 warnings=0` (genuinely quiet box).
- `apptrace` before: healthy CLR — threadpool `WorkerThreadCount=4`,
  JIT warm-up code ranges, a handful of induced GCs.
- `apptrace` at the storm's edge: `CLR:158` code-range events ×28,
  GC sampling `CLR:20` ×12 — JIT + allocation churn from 161 threads.
- After the rings froze, a 2h-window pull returned only 22:58+/23:42+
  events: **the frozen files still held the 22:05+ history** (freeze
  preserved evidence), but nothing newer was landing.

### The diagnosis chain (how it was found)

1. `ringhealth` said all-Running/ok → contradicted by ring files at exactly
   512 MB/128 MB with mtimes stuck at 23:02.
2. Direct `logman query` showed `Running` + `Circular: On` — while a start
   attempt on ProcTrace failed with "Data Collector Set is already in use"
   (zombie ETL handle).
3. `logman stop <n> -ets` (releases the handle) + `start` revived all three;
   each restart opened a fresh segment (`_000003.etl`).
4. The `-r` wrap promise from Rev 18 was disproven at sustained load →
   Rev 19 freeze detection + watchdog.

### Enterprise fixes shipped in this skill (Rev 19)

- `ringhealth`: real segment file + `cap_mb` + `mtime_age_min` + `stale` +
  `frozen` verdict; frozen counts into `blind_count`/`blind_check=BLIND`.
- `autologger.py --doctor [--apply]`: detect + restart frozen/dead rings
  (`logman stop -ets` is the part that actually releases a zombie).
- `autologger.py --watchdog --apply`: 5-minute SYSTEM scheduled task doing
  the same server-side, bounded 200-line log at `C:\etw\watchdog.log`.
- Sizing math + drill procedure: see SKILL.md "Enterprise sizing &
  operations".

### Holes disclosed

- The deep decode (per-minute exception histogram, thread ramp timeline
  from the 512 MB ETL) requires a server-side job (10+ min) — not streamed;
  a remote full-scan attempt died at the WinRM 30 s timeout with zero output.
- Sysmon could not corroborate the process history (log rotated past it).
- NetTrace captured nothing (kernel-net AutoLogger hole), so connection
  counts come from the app's logs, not the ring.
