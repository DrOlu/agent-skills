# Needle instance standards

The generated instance is only as reliable as its menu. These rules come from
the needle skill and are enforced by the generator; carry them into any manual
extension.

## Menu rules

1. **Triggers on every entry**, disjoint between entries. Generated pattern:
   `<table>_count` → ["how many <t>", "count <t>", ...]; shared verbs like
   "how many" are fine only when the object noun disambiguates.
2. **Arguments constrained in the grammar**: enum columns become `enum`
   properties (the decode grammar then cannot emit an unobserved value),
   limits get `minimum/maximum`, identifiers get `pattern`s.
3. **Results small**: probes return at most ROW_CAP (25) rows plus counts; the
   full truth stays in the source. Aggregate probes return numbers only.
4. **Secrets baked in the bridge only**: DSNs/API keys are constants or env
   lookups in bridge.py. Never a model-facing argument — grounding refuses
   them anyway, and executors are the right home.
5. **Read-only first**: write/update probes are added only after the user
   approves, behind an explicit flag, and always with identity checks.
6. **Errors are data**: a failed retrieval returns {"error": …} to the model,
   which may retry within the step bound.

## Bridge rules

- Every record passes through the Pydantic model before it reaches a probe's
  return value; parse failures are counted into `_VALIDATION` and surfaced by
  `instance.py --coverage` / `verify.py`.
- Identifiers (table/column names) are whitelisted against the profile before
  interpolation into SQL — the model may fill arguments, the executor validates.
- Row caps in the bridge, not just in prompts: a "limit 10000" request still
  returns at most ROW_CAP rows plus a total count.

## Runtime rules

- Python runtime: `instance.py` defines the same menu as `@needle.tool`
  functions (triggers included) so the agentic loop can execute probes itself;
  `response["results"]` is the success signal.
- Engine runtime: `needle_menu.json` feeds the standalone binary; the engine
  selects, the bridge executes. Selection is deterministic across runs.

## Verification (Phase 4) contract

1. Coverage: ≥95% of fetched records parse through the models.
2. Selection: three phrasings of one intent all select the same probe.
3. Truth: one relayed number equals a direct source query.
Record all three in `verification.txt` next to the instance.
