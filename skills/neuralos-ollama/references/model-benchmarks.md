# Measured model comparison — wema-bmc, 10-question graded set (2026-10-03)

All runs: Ollama 0.35.1, `format` JSON-schema constraint, temperature 0,
`think: false`. Set = 7 answerable questions + 3 traps where the only correct
behaviour is `none_of_these`.

| Model | Score | Gap refusal | Warm speed | RAM | Notes |
|---|---|---|---|---|---|
| qwen3.5:9b + format | 9-10/10 | YES | 2.4-8.1s (think:false) | 6.6GB | CURRENT DEFAULT. With think on: 26.8s+ on gaps. |
| deepseek-r1:7b + format | 10/10 (3q subset) | YES | 8.7-10.7s | 4.7GB | Accepts think flag but ignores it (template-intrinsic). Weak at code WRITING — picking only. |
| qwen3.5:4b + format | 3/3 quality | YES | 25-55s PATHOLOGICAL | 3.3GB | Build-specific grammar x prompt interaction (9b same family = fast). Retired. |
| LFM2.5:8b + format | 2/3 | no — fabricated SQL-ish args | 0.9s | 5.2GB | Best speed/arg-fidelity on answerables; no refusal judgment. |
| SmolLM2:1.7b + format | 1/3 | no — fabricated args | 0.4s | 1.8GB | 27% BFCL per its own model card. |
| needle 3 (121M, 2-bit, REPLACED) | 1/3 | no | 1.6s | 0.1GB | Stripped INC arg prefix; crossed domains on traps. |

## Sibling discrimination — the decisive test (chinook, 2026-10-04)

Question: "How many Tracks have a song length greater than the Average song
length." — with a COUNT probe and a LIST probe both in the menu (siblings).

| Selector | Pick |
|---|---|
| needle 3 (python runtime, rebuilt tool index, exact trigger phrasing) | LIST probe — count never given |
| qwen3.5:9b (Ollama native tool-calls, think:false) | COUNT probe → 494, avg 6.6 min |

Reverse direction also correct: list-phrasing picked the LIST probe with
`limit=5` extracted. Warm ~4s, cold ~30s. The 121M selector cannot
discriminate near-identical sibling tools; a mid-size instruct model can —
and the code floor still owns refusals. Full recipe:
`scripts/instance_ollama_runtime.py` (uses Ollama native tool-calls — 48
schemas, no grammar slowness).

## Key findings

1. **Format guarantees valid, never correct.** Every model, including 0.99-
   confidence wrong picks, emitted perfectly legal JSON. SmolLM2 fabricated
   an argument VALUE inside perfectly valid schema-shaped output.
2. **The refusal lever must be offered AND earned.** `none_of_these` in the
   enum is necessary but not sufficient: only qwen3.5:9b and deepseek-r1:7b
   used it on a genuine gap. Smaller models ignore it.
3. **think:false is not optional for qwen3.5.** Default thinking silently
   consumed 100-500 token budgets (empty content) and roughly tripled
   constrained latency (26.8s -> 2.4-8.1s warm).
4. **qwen3.5:4b + format is pathologically slow (25-80s)** — reproducible to
   within 1s across runs; NOT a family trait (9b same family = 2.4-8.1s);
   grammar x prompt-size interaction. Retired from constrained duty.
5. **Lexical floor (code gate) refuses what no model refused**: the only
   honest "no probe matched" refusal in round 1 came from ask.py's
   score<=0 rule, before any model was consulted.

## Acceptance bar for a needle-3 replacement

- >= 9/10 on the graded set
- honest `none_of_these` on all traps (zero fabricated args)
- warm constrained pick < 30s with think:false
- works behind the lexical floor without changing the router
