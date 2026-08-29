---
name: rmagent-fr
description: >
  The Flight Recorder — follow one work id (a ticket, a payment, an incident)
  across the estate without a span warehouse. The tracing half of the RMAgent
  security observatory: a Security Trace Context (STC) carries case, principal,
  window, depth, ticket and trigger through every hop; the trajectory records
  the reasoning chain as an append-only DAG; the hop index remembers whether a
  principal has appeared before; the causal graph computes blast radius from
  kilobytes; OTel spans land in Grafana/Jaeger next to application traces. Use
  when a payment is slow, an incident needs a timeline, or security and
  reliability must read the same tape. Pull-based, capped, case-filed — not a
  lake.
---

# rmagent-fr — The Flight Recorder

Follow one work id without a span warehouse. The reliability half of the
RMAgent security observatory: **security asks who walked, reliability asks why
it felt slow — same ticket, two questions, one case file.**

This is the Flight Recorder engine, split out of `rmagent-windows` so the
tracing half can be reasoned about (and loaded) on its own. `rmagent-windows`
remains the complete, runnable skill; `rmagent-so` is the witness-question
half. The three skills share one constitution.

## Non-negotiables

- **The ticket is a grain, not a tag.** It propagates through every hop, every
  span, every index record — and is queryable back.
- **A case file, not a lake.** Megabytes. Adaptive sampling keeps join keys on
  every walk and full detail only when something was found.
- **The budget belongs to the identity.** Depth ≤ 8, fan-out 3, 32 KB pull cap.
  An unconstrained hunter is a worm.
- **Context propagates, data does not.** The STC carries identifiers; the
  answers stay on the machine that produced them.
- **Clock skew is detected on every walk.** Cross-host timelines you can trust.

## The scripts

| Script | Role |
|---|---|
| `scripts/stc.py` | Security Trace Context — `case; principal; window; depth; ticket; trigger`. The distributed circuit breaker. Immutable; `child()` returns depth+1. Rejects `;`/`=` in fields (injection fix). |
| `scripts/traj.py` | The trajectory — append-only DAG of observations, thoughts, actions, results, holes, forks, merges. The recorder's reasoning chain, replayable. |
| `scripts/hop_index.py` | Cross-case memory — keyed `(host, principal, logonid, kind, case)`. `by_principal()`, `by_logonid()`, `seen_before()`. Adaptive sampling: full detail when smoke, join keys when clean. |
| `scripts/causal.py` | Causal graph — nodes `(host, principal, logonid)`, edges hops. `blast_radius()` computes everything reachable from the compromise. |
| `scripts/dthinker.py` | Distributed thinker — `temporal_cluster`, `cross_host_chain`, `session_correlation`, `repeat_offender` across the hop index. |
| `scripts/thinker.py` | Persistent reasoning between knocks — acceleration, cliffs, persistence, correlation, silence, DNS tunneling over census history. |
| `scripts/trace.py` | Trace query API — `trace.py CASE-X`, `--ticket PAY-4419`, `--principal Admin`, `--list`. Merges trajectory + hops + holes + causal graph. `get_trace()` for the gateway. |
| `scripts/trace_merge.py` | Pull-merge multi-jump-host — fan out over SSH, dedup, merge. Two-site estates without shared state. |
| `scripts/otel_emit.py` | Every trajectory entry becomes one OTel span → RTerm gateway → Grafana/Jaeger/Splunk. |
| `scripts/census.py` | The minute watch — attest on all witnesses, 2 misses = Critical → Telegram. Writes the history the thinker reasons over. |

## The ticket join — one tape, two questions

```
case.py open --ticket PAY-4419
hunt.py   --ticket PAY-4419
trace.py  --ticket PAY-4419
```

The ticket propagates through the whole trace: every question, every hop, every
span, every index record. Query it back from either side of the house. That is
the Flight Recorder's actual product.

## The honest limit

The business side must emit events carrying the ticket. The security half is
done — a ticket given at case-open flows through everything. The reliability
half needs the payment system to stamp `PAY-4419` into its own events, which is
an integration with whatever runs the payments, not a feature of this skill.

## Relationship to the other skills

| Skill | Half |
|---|---|
| `rmagent-windows` | The complete skill — both halves, fully runnable |
| `rmagent-fr` | This skill — the Flight Recorder (tracing) half |
| `rmagent-so` | The witness-question (Security Observatory) half |
| `rmagent-redteam` | The drill — stages artifacts, scores detection |
| `rmagent-actuate` | Phase 1 response — named, journaled, reversible |
| `rmagent-linux` | The Linux/macOS sibling of `rmagent-so` |