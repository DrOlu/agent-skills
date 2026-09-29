# Butler harness — the serving edge

A butler is a small service that serves **one named skill** over the gateway's
signed `skillproxy` lane, with **no model key**: it grounds every question
through the on-device neuralOS/needle engine against read-only probes.

## 1. The serving path (no fallback, ever)

```
question ──► ask.py retrieval (trigger scoring, top-K=8) ──► needle engine
                                                              │  picks ONE probe
                                                              ▼
                        harness executes the probe READ-ONLY  ──► capped digest
                                                              │
                          honest hole ◄── no probe selected ───┘
```

1. **Shortlist deterministically** — tokenize the question (stop-words
   removed), score each menu probe (≈3× trigger overlap + 1× name + 0.3×
   description), keep the top K=8. This is what keeps a 121M model reliable on
   a large menu.
2. **Ground with the engine** — `needle --model <weights> --tools <ctx>
   --prompt <question>` (60 s timeout). The engine returns one call, or none.
3. **Execute read-only** — `getattr(bridge, probe_name)(**args)`, cap the
   output (32 KB), return JSON.
4. **Honest hole** — no call ⇒ `{"ok": false, "hole": true, "error": "needle
   engine did not select a probe", "response": <engine telemetry>}`. Upstream
   failure ⇒ relay the upstream error verbatim.

> Never add a keyword router as a fallback. The benchmark rule is
> **never-seen-before questions** precisely so a keyword matcher could not
> masquerade as grounding.

## 2. The harness

`scripts/butler_template.py` is a complete, cross-platform harness. Minimum
config via environment:

| Env var | Meaning |
|---|---|
| `NEEDLE_ENGINE_DIR` | folder with the engine + weights |
| `BUTLER_SKILL` | the skill name it serves, e.g. `butler.query` |
| `BUTLER_MENU` | path to `needle_menu.json` (default: beside the script) |
| `BUTLER_BRIDGE` | python module providing the probes (default `bridge`) |
| `BUTLER_K` | retrieval K (default 8) |
| `BUTLER_CAP_BYTES` | digest cap (default 32768) |
| `BUTLER_ENGINE_TIMEOUT` | seconds for one engine call (default 60) |

It reads a question from argv (local test) or from the gateway's skillproxy
call, executes the selected probe, and prints the reply envelope
`{"ok": true, "reply": {"result": …, "elapsed_s": …}}`.

**It never returns a traceback.** Menu, engine, bridge and probe failures all
become structured holes — a misconfigured butler answers diagnosably instead of
dying, so the gateway sees a fixable error rather than a dead skill.

## 3. Designing the menu

A probe declares name, description, parameter schema, triggers and a read-only
implementation:

```json
{
  "name": "sales_by_country",
  "description": "Revenue, invoices and customers per country, ranked.",
  "parameters": {"type": "object", "properties": {}},
  "triggers": ["revenue by country", "sales by country", "country breakdown",
               "which country earns the most", "revenue breakdown by country"]
}
```

Rules that make the tiny model reliable:

- **Every probe gets triggers** whose words the operator actually says.
- **One probe, one question shape.** Split overlapping probes.
- **Constrain arguments** in the grammar (`enum`, `ge/le`, `pattern`); an
  unconstrained string will be filled with nonsense.
- **Return small digests.** Cap rows (e.g. 25) and bytes; keep big payloads
  server-side.
- **Two asks per turn, maximum.** A three-part compound drops the third.
- **Describe the tool as a prompt**: put the vocabulary in the description.

## 4. Adding a probe (the extension recipe)

1. Edit the bridge: add a function `def <probe_name>(...) -> dict` that runs a
   single read-only query and returns a small dict.
2. Append the menu entry (name, description, parameters, triggers).
3. Re-export the menu if it is generated from an instance definition.
4. Verify selection with **three never-seen phrasings**; confirm the number
   against a direct source query.
5. Restart the butler service.
6. Re-run the selection suite — new entries can degrade existing picks.

Worked example (monthly revenue): see `references/examples.md` §5. The
pattern there — one read-only query in the bridge, a bounded series with no
row cap when the series is small, and triggers carrying the operator's own
vocabulary — applies to any time-series probe.

## 5. Multi-butler edges

One edge can serve several butlers (different skills, different data). Give
each its own service name, its own menu, and its own `BUTLER_SKILL`. The
gateway's `skillproxy` lane resolves the inner `target` to the right one.

## 6. What a butler must never do

- write to its data source, or shell out beyond the probe implementation
- handle credentials as tool arguments (bake them into the bridge)
- return unbounded output
- invent an answer when the engine selects nothing
- hardcode the engine path instead of using `NEEDLE_ENGINE_DIR`