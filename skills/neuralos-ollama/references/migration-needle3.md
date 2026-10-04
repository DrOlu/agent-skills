# Migrating an instance off needle 3 (checklist)

## What stays EXACTLY as-is (the code gates)

- `probes.py` / `bridge.py` — probes, triggers, caged args, bridge
- `needle_menu.json` — still the menu of record (exported, consumed by the
  shortlist builder and descriptions)
- lexical router / `ask.py` score floor — decides IF the model is consulted
- regex cages, results gate, audit JSONL, cache, PII masking
- truth oracles and lint

## What is removed

- the needle 3 binary, `needle3.cact`, `--model` engine-fallback invocations
- any 0.1GB/100MB footprint assumptions (the Ollama model is GB-class)

## Steps

1. `bash scripts/install_think_defaults.sh` (pulls qwen3.5:9b, writes env)
2. `python3 scripts/verify_setup.py` — all checks must pass
3. `python3 scripts/bench_stress.py --instance-dir <dir>` — must score
   >= 9/10 with trap refusals and zero fabricated args
4. Reason loop: `NEURALOSD_REASON_MODEL` env is now the model seat; if your
   neuralosd build predates think:false in reasoning.py, apply the patch:
   add `"think": False` to the /api/chat payload with an HTTP-400 retry
   without it (see `scripts/ollama_client.py::chat` for the pattern)
5. Custom apps that used `Instance(model_fallback=...)` with the engine:
   point the fallback callable at `ollama_client.constrained_pick` instead —
   the callable contract (question in, envelope out) is unchanged
6. Rerun lint and the truth oracle — unchanged and still mandatory

## Trade-offs to state out loud

- RAM: ~100MB (needle 3) -> 3.3-6.6GB (Ollama model resident). Edge boxes
  and no-Python deployments lose the needle path entirely.
- Latency: warm constrained picks 0.9-11s depending on model; needle 3 was
  1.6s. Mitigation: the unsure band is 10-30% of traffic and cached.
- Cold start: 5-15s model load; use `ollama keep_alive` / long-running serve.
- deepseek-r1 models ignore think:false (always think) — prefer qwen3.5:9b
  for latency-sensitive seats; reasoning.py strips think blocks regardless.

## Rollback

Everything is additive: reinstall needle 3, restore the `--model` engine
fallback, delete the env exports. The gates never changed, so rollback is a
model-seat swap, not a rewrite.
