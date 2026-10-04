---
name: neuralos-ollama
description: "Replace the needle 3 engine in neuralOS/neuralOSd with Ollama-hosted qwen3.5:9b using format-constrained JSON (thinking disabled), keeping every deterministic code gate (lexical floor, caged args, results gate, audit). Covers constrained probe selection, the reason loop, think-disabled text generation, setup verification, and a graded 10-question benchmark. Use when swapping needle 3 for Ollama models, tuning think:false defaults, or benchmarking fallback models."
---

# neuralOS-ollama — replace needle 3 with a constrained Ollama model

Run a neuralOS / neuralOSd instance with **no needle 3 engine at all**: every
model call goes to an Ollama-hosted instruct model (default `qwen3.5:9b`)
with **thinking disabled**, while every deterministic code gate stays intact.

## The contract (do not break these)

1. **Code gate first.** The lexical router / `ask.py` floor answers everything
   it can. The model is consulted ONLY when the router is unsure. Never call
   the model for a question a probe already answers.
2. **Think off, always.** All model calls send `"think": false`. Qwen3.5-family
   models default to thinking and silently burn the token budget (verified:
   empty `content` with 100-500 `num_predict`). Set `NEURALOSD_THINK=1` only
   when deep reasoning is explicitly wanted.
3. **Guaranteed valid, not guaranteed correct.** Ollama `format` (JSON schema)
   makes malformed output impossible; it does NOT make wrong picks impossible.
   Always include `"none_of_these"` in the enum, verify with the existing
   regex cages, and keep the score floor in charge.
4. **The model never computes numbers.** It picks tools and fills args from
   the question; code executes and verifies.

## Setup

```bash
ollama pull qwen3.5:9b            # 6.6GB, ~24-45 tok/s on M1 Pro GPU
export NEURALOS_OLLAMA_MODEL="qwen3.5:9b"
export NEURALOSD_REASON_MODEL="qwen3.5:9b"   # reason-loop default
python3 scripts/verify_setup.py   # health-checks everything below
```

Verified on Ollama 0.35.1. Ollama has NO server-wide think default — enforce
`think: false` per request (this skill's client does it for you). In neuralosd
itself, apply the reasoning-loop patch or set the env (see
`references/migration-needle3.md`).

## Workflows

### A. Constrained probe selection (replaces needle 3 selection)

```bash
python3 scripts/pick_probe.py --instance-dir ./wema-bmc \
    --question "how many worklog entries exist"
# -> {"probe": "...", "args": {...}} — or none_of_these for honest refusal
```

The client offers the model only a top-K shortlist from a lexical pre-scorer
plus `none_of_these`. Small enum = small grammar = fast constrained decode
(full-menu enums on qwen3.5:4b are pathologically slow; shortlists are not).

### B. Reason loop (replaces the fallback model seat)

```bash
export NEURALOSD_REASON_MODEL="qwen3.5:9b"
neuralosd reason --instance-dir ./wema-bmc --force \
    "what is the ratio of open work orders to open incidents"
```

Certified live: installs the derived metric, 14/14 neighbours unchanged, loop
closed. Use `--model` to override; models that reject `think` get an automatic
retry without it.

### C. Text generation (thinking disabled)

```python
from ollama_client import chat
out = chat("qwen3.5:9b", [{"role": "user", "content": "Write a Python function..."}])
print(out["message"]["content"])   # direct answer, no think-budget burn
```

### D. Benchmark before you trust it

```bash
python3 scripts/bench_stress.py --instance-dir ./wema-bmc --model qwen3.5:9b
```

Runs the 10-question graded set (7 answerable + 3 traps) that produced the
measured table in `references/model-benchmarks.md`. A candidate must score
>= 9/10 with honest refusals on the traps to be considered a needle-3
replacement.

## Files

- `scripts/ollama_client.py` — shared client: `chat()` with think:false,
  schema-constrained `pick()`, 400-retry for models without think support
- `scripts/pick_probe.py` — CLI constrained selection against any instance menu
- `scripts/bench_stress.py` — 10-question graded benchmark (model parameterized)
- `scripts/verify_setup.py` — verifies Ollama, model, think-off, format works
- `scripts/install_think_defaults.sh` — pulls models, writes env defaults
- `scripts/test_neuralos_ollama.py` — offline unit tests (schema, refusal, cage)
- `references/model-benchmarks.md` — measured 6-model comparison (2026-10-03)
- `references/migration-needle3.md` — needle 3 removal checklist + trade-offs

## Measured baseline (2026-10-03, wema-bmc, 10-question set)

| Model | Score | Gap refusal | Warm speed | RAM |
|---|---|---|---|---|
| qwen3.5:9b + format | 9-10/10 | yes | 2.4-8.1s | 6.6GB |
| deepseek-r1:7b + format | 10/10 (3q set) | yes | 8.7-10.7s | 4.7GB |
| LFM2.5:8b + format | 2/3 | no | 0.9s | 5.2GB |
| SmolLM2:1.7b + format | 1/3 | no + fabricated args | 0.4s | 1.8GB |
| needle 3 (replaced) | 1/3 | no | 1.6s | 0.1GB |

qwen3.5:4b + format scores 3/3 but is pathologically slow (25-80s) — a
build-specific grammar x prompt interaction, NOT a family trait (9b is fast).
