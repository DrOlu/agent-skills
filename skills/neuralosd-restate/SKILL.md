---
name: neuralosd-restate
description: "Durable execution for neuralOS/neuralOSd on Restate — single-binary engine, no Docker/JVM/DB, CLI + Python only, all platforms (macOS/Linux/Windows-WSL2). Covers architecture and design (journal/replay, ctx.run, retries, awakeable approvals), install per OS, a durable Python service wrapping any neuralosd instance HTTP door (ask/triage/nightly-report handlers), deployment registration and invocation, verification, benchmarking, and integration with the neuralos-ollama skill. Use when adding durable execution to neuralosd workflows, replacing Conductor with Restate, or deploying crash-resilient neuralosd pipelines without Docker."
---

# neuralosd-restate — durable execution for neuralosd on Restate

Run neuralOS / neuralOSd workloads on **Restate** (single-binary durable
execution engine, no Docker/JVM/external DB) with **CLI + Python only**, on
macOS, Linux, and Windows (WSL2). The deterministic code gates stay intact:
Restate owns the pipeline and its journal, neuralosd owns the answers,
the model (optional, qwen3.5:9b via Ollama, `think:false`) owns judgment.

## The contract

1. **Code gate first** — the lexical router / `ask.py` floor answers ~90%+.
   Restate handlers wrap neuralosd calls; they never replace the router.
2. **Durable by journal** — every handler step runs inside `ctx.run(...)` so
   results are journaled and replayed on retry. Side effects ALWAYS go
   through `ctx.run`, never bare.
3. **Honest refusals** — a gap question maps to a logged refusal, never a
   guessed answer. Keep `none_of_these` semantics at the probe layer.
4. **One model seat** — optional qwen3.5:9b via Ollama, `think:false`
   (see the `neuralos-ollama` skill) whenever generation is required.

## Setup (per machine)

```bash
bash scripts/install_restate.sh          # macOS + Linux (auto arch/OS)
python3 scripts/verify_restate.py        # server up, service registered, invoke OK
```

Start the server: `<install-dir>/restate-server` (ingress :8080, admin/UI
:9070 — web UI at http://localhost:9070/ui/). Storage is embedded
(no external DB). Windows: WSL2 Ubuntu, same Linux steps (see
`references/platforms.md` — official server binaries are macOS + Linux).

## Run the durable service

```bash
export NEURALOSD_URL="http://127.0.0.1:8878/ask"   # the instance HTTP door
python3 scripts/restate_neuralosd_service.py &     # serves :9090
curl -s -X POST localhost:9070/deployments \
     -H 'content-type: application/json' \
     -d '{"uri": "http://127.0.0.1:9090"}'
```

Invoke (durable — journaled, retried, resumable):

```bash
curl -s -X POST localhost:8080/WemaTriage/triage
curl -s -X POST localhost:8080/WemaAsk/ask -d '"how many worklog entries exist"'
```

View in the UI: http://localhost:9070/ui/ (per-invocation journal, timings,
retries). CLI: `restate invocations list --all`, `restate sql -q "..."`.

## Certification checklist

```bash
python3 scripts/bench_durable.py --runs 3        # latency + correctness
python3 scripts/test_neuralosd_restate.py        # offline unit tests
```

Acceptance: triage returns overview + critical + busiest-group with live
numbers; a gap question refuses honestly; journal visible in the UI.

## Files

- `scripts/install_restate.sh` — macOS/Linux binary installer + service hints
- `scripts/install_restate_windows.ps1` — Windows: WSL2 setup + service notes
- `scripts/restate_neuralosd_service.py` — durable service (ask / triage /
  nightly report) over the instance HTTP door
- `scripts/register_and_invoke.py` — register deployment, start + poll runs
- `scripts/verify_restate.py` — preflight health checks
- `scripts/bench_durable.py` — timing benchmark
- `scripts/test_neuralosd_restate.py` — offline unit tests
- `references/architecture.md` — design: seats, journaling/replay, retry
  policy, awakeables (approvals), Conductor comparison
- `references/platforms.md` — macOS/Linux/Windows service install, upgrade,
  backup, troubleshooting
- `references/recipes.md` — worked recipes: nightly report, date-range asks,
  approval flow, multi-instance, Ollama think:false generation

## Design rules (see references/architecture.md)

- Restate does NOT replace the code gates — it wraps them with durability.
- Side effects inside handlers always use `ctx.run`; handler bodies stay
  deterministic between journal entries.
- Approvals use awakeables (durable promises), never sleeping loops.
- Keep one Restate service per neuralosd instance; name handlers after
  probe families.
