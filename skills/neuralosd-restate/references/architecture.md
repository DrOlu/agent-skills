# Architecture - Restate + neuralosd

## Seats (do not shuffle)

1. **Code gates (neuralosd)** - lexical floor, caged args, results gate,
   audit, PII masking. Unchanged. The instance HTTP door (`neuralosd serve`)
   exposes them over HTTP.
2. **Restate** - durable execution: journals every `ctx.run` step, retries
   with exponential backoff (default 70 attempts, pause on max), replays on
   crash, keeps per-invocation history, exposes a web UI.
3. **Model (optional)** - qwen3.5:9b via Ollama, `think:false`, ONLY where
   generation is needed (see the `neuralos-ollama` skill).
4. **Humans** - approvals via awakeables (durable promises).

## Why Restate fits neuralosd

- **Single static binary** (~45MB) with embedded storage - no JVM, no
  Elasticsearch/Postgres/Redis, no Docker. Matches the "CLI + Python only"
  constraint on macOS and Linux (Windows via WSL2).
- **Code-first workflows** - a workflow is a Python function; branches,
  loops and error handling are real code, not JSON. Ideal for the
  instance-build pipeline (recon -> bridge -> probes -> lint -> verify).
- **Journal/replay** - each `ctx.run` result is persisted; on crash the
  handler re-executes from the top but completed steps REPLAY from the
  journal instead of re-running (that is what makes side effects safe).
- **Free durability defaults** - retry policy (70 attempts, exponential,
  pause on max), journal retention, idempotency keys - visible in the
  deployment registration response.
- **Awakeables** - a durable promise a human (or another workflow) can
  resolve later: the clean primitive for confirm-gated operations.

## vs Conductor/AgentSpan

| | Conductor/AgentSpan | Restate |
|---|---|---|
| Workflow style | JSON definitions + HTTP tasks | Python functions |
| Ops footprint | JVM server (SQLite ok on AgentSpan) | single Rust binary |
| Human approval | human task + approve API | awakeables |
| Maturity | older, enterprise features | newer, fast-moving |
| Our integration cost | already certified | small rewrite of handlers |

Decision rule: JSON-config pipelines and managed dashboards -> Conductor.
Python-code pipelines and minimal ops -> Restate. Both keep the code gates.

## Request flow (triage example)

```
curl POST :8080/WemaTriage/triage
  -> Restate ingress journals the invocation
  -> handler starts; overview = ctx.run(...)  journaled
  -> critical = ctx.run(...)                  journaled
  -> bygroup  = ctx.run(...)                  journaled
  -> returns JSON; journal retained (default 1d)
```

If the process dies after `overview`, the retry replays `overview` from the
journal and only executes `critical`/`bygroup` fresh.

## Ports and storage

- :8080 ingress (invoke), :9070 admin + UI (`/ui/`), :9090 handler server
- State: embedded RocksDB under the server working directory
- Upgrade: stop server, swap binary, restart - journal is compatible within
  a major version (verify on a copy first)
