# Verification — the exhaustive battery, and why sampled checks lie

The founding incident: a 4-record image instance shipped with two records
content-swapped, three wrong figures, and one record that crashed its
details probe — while selection suites, conformance gates and coverage
checks all reported green. Every check that RAN passed. The failure was in
what was chosen to be checked.

## The battery (run all; partial green is not green)

1. **Per-record parse** — for EVERY catalog filename, ask the instance for
   its details and assert a parsed record returns. Catches strict-model
   rejects (flattened empty dicts, over-fit bounds) on the specific records
   that carry them. `run_truth_checks.py --instance .` Layer 1.
2. **Trigger lint** — 0 HARD collisions required; soft ones noted.
3. **Selection suite** — golden bank (one question per probe, minimum 2
   phrasings for semantic probes) + trap bank (MUST-refuse questions:
   imperative actions, unknown subjects, unheld qualifiers). Through
   ask.py, ONE PROCESS PER QUESTION (stale-buffer contract).
4. **Truth checks** — declared expectations vs ask.py output for EVERY
   record plus every headline number (see examples/truth_checks.json).
   The catalog is the oracle for the instance; the IMAGES are the oracle
   for the catalog (via the zoom reads).
5. **Gate/envelope conformance** — the refusal-gate suite, exit 0.
6. **Cache hygiene** — after ANY data change, clear `.ask_cache.json`.
   The cache keys on menu version only; data changes do NOT invalidate it.
7. **Semantic sanity** — the discovery queries you actually care about
   must rank the right file first. 3–5 canonical queries, checked by
   filename, not vibes.

## Two-oracle rule

- **Instance vs catalog**: run_truth_checks.py. Deterministic, re-runnable.
- **Catalog vs images**: the zoom reads (vision-transcription.md). This is
  a human/agent judgment layer — record it in verification.txt as the
  transcription provenance, with the correction history.

Never let (1) substitute for (2): a perfectly-transcribed-then-verified
instance of a WRONG catalog is the founding incident.

## Writing verification.txt

Structure (keep superseded passes — the delta IS the audit trail):

```
== v2 RE-EXAMINATION (date, trigger) ==
trigger: user flagged field X on file Y
findings: bullet list of corrections (mapping swap, figure fixes)
battery: per-record parse 4/4 · selection 20/20 · truth 8/8 ·
         conformance 17/17 exit 0 · embeddings rebuilt · cache cleared
== v1 record (superseded) ==
...what ran, what it missed and why...
```

## Cost discipline

The full battery on a 4-image instance is ~40 ask.py invocations ≈ under
two minutes. Scale it, don't sample it: 400 images → per-record parse stays
mandatory for all 400 (it's cheap); selection/trap suites stay menu-sized;
truth checks target every record's key fields plus every aggregate.
