# Scenarios — how a cloned skill should behave

These are **acceptance stories**, not payload specs. A new skill is done when
an operator can read the case aloud in two minutes.

## S1 — Sighted empty vs blind empty

Given a live door and no smoke in the window,
when `attest.blind_check` is `ok`,
then “no findings” on sketch/edges is believable.

Given the same emptiness and `blind_check=BLIND`,
then the case records a **hole**, not a clean bill.
(WS2 Failure-only Logon is the teaching incident.)

## S2 — One grain localizes a hop

Given grain G seen on two sensors,
when `hops` / `trace` runs,
then exactly one hop is slowest or `last_seen` names the last sensor,
and unseen segments are **holes** (not zeros).

Payments: STAN 123456, D=2375 ms, A=hole.
Timeout: last_seen=cba_0200, total=null.

## S3 — Cap does not become a liar

Given an answer > 32 KB,
when `ask()` returns,
then `{hole: true, reason: capped}` (or a signal-aware trim **flagged**
`capped: true`). Never a quiet subset that looks complete.

## S4 — Actuate is not a question

`ask("actuate")` → not-allowlisted. Forever.

## S5 — Baseline refuses small n

`baseline` with n=8 → hole `baseline-n-too-small`. Never “normal = 12 ms.”

## S6 — Recycled ids

PID / STAN / LogonId without a second key or window → reject or hole.
Join on NAT IP → forbidden (document as anti-pattern).

## S7 — Off-estate

A partner IP in inventory → operator must not add it. If asked, hole
`not-your-estate`.

## S8 — Ring overwrite = retention-boundary

Grain older than the ring → `not-in-ring` hole, not “never happened.”

## S9 — Side tape, not grain creep

Hop math says Finacle waited. Do not add Windows 4624 to the ISO skill.
Open `rmagent-linux` attest on the Finacle host; join via `rmagent-fr` ticket.

## S10 — Drill (optional)

Stage prefixed artifacts, score the watch skill, clean, `--confirm`.
Misses are documented (audit off → no 4688), not hidden.
