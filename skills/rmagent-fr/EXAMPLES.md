# rmagent-fr

Grain: ticket. Does not knock. Cases under ~/.rmagent/cases/.

python3 case.py open --title "x" --ticket PAY-1 --principal Administrator

---

## Worked case: WS2 performance incident through the Flight Recorder lens (2026-10-04)

The App Tracing skill (`rmagent-at`) owns the ring capture; this example
shows the same incident the way the Flight Recorder should carry it — a
ticket-led walk whose questions happen to land on the app plane. Use it as
the template for "app feels slow / errors spiked" intakes.

### 1. Intake (Laya: `intake_triage`)

Symptom: "clients seeing 1.5–2.0s SLOWs, connect-timeouts, and resets against
WS2:18111; server self-churning". Verdict: worth walking, urgency high,
plane=service. `case.py open --title "WS2 churn+slow-requests" --ticket
OPS-4419 --principal svc_badapp` — the ticket flows into every later
question via `case.json`.

### 2. The walk (questions are still Phase 0 — read-only, capped)

| Hop | Question | What it returned | Join key it produced |
|---|---|---|---|
| service | `apperrors` (2h, 150) | 0 CLR errors/warnings — **app logs disagree with the ring** (boom-\* exceptions were app-text, not CLR Level≤3 events) | the discrepancy itself is a finding |
| service | `apptrace` (2h, 150) | CLR:158 code-ranges ×28, CLR:20 GC samples ×12, threadpool ramp | `ClrInstanceID=9` + second CLR instance |
| service | `appproc` (2h, 200) | 115 process events / 81 thread-starts, burst concentrated at 22:05:29, PID 8028 dominating | PIDs + the 22:05 burst minute |
| platform | `ringhealth` | (pre-Rev19) all Running, ok | — |
| files | host logs `C:\badapp\*.log` | 19,400 reqs, boom-\* every 500, leak 375 MB / 161 threads, SLOWs 1.5–2.0s | timestamps ↔ ring bursts |

Cross-host/time note: the ring is on-box; there is no second host in this
case, so `trace_merge` isn't needed — but the STC carried the window
(22:36→22:47Z) that made every later pull a bounded question instead of a
guess.

### 3. The hole that changed the case

`ringhealth` said healthy while the box was provably degraded — and later,
the ring files froze at cap with `Running` status (Rev 19 freeze; full story
in rmagent-at EXAMPLES). The reliability lesson recorded on the trajectory:
**a healthy answer from a capture plane must be cross-checked against one
independent signal** (here, the app's own logs). An unverified "quiet" is
exactly how an incident gets called a non-event.

### 4. Synthesis (what `trace.py OPS-4419` reconstructs)

- **Root cause:** self-inflicted load — the app's design (churn + leak +
  spin) is the fault, not an external attack. Client failures are the
  symptom of the server's listen backlog filling (`127.0.0.1:18111`
  connect-timeouts).
- **Blast radius:** single host, no lateral anything (Sysmon corroboration
  was lost to log rotation — recorded as a hole, not assumed clean).
- **Timeline:** boot 21:53 → baseline quiet 22:05–22:15 → storm 22:36–22:47
  → rings freeze 23:02 → detection 23:41 → revive 23:43.
- **Follow-ups:** watchdog install (done), sizing review (SKILL.md), Sysmon
  off-box shipping (open), deep decode server-side (open).

### 5. What made this a Flight Recorder case and not just a log read

- The ticket (`OPS-4419`) would join future questions from any other skill —
  census, so, at — against the same host/window.
- The trajectory recorded the **discrepancy findings** (app-log vs CLR
  error counts; healthy ringhealth vs frozen file), which are the parts a
  human reviewer actually needs.
- Holes were written as holes (Sysmon window lost; NetTrace empty; decode
  pending) — the case file is honest about what it cannot say.
