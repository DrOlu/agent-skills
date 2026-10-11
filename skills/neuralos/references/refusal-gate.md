# The refusal gate & the ask envelope (GATE_VERSION 1)

Every ask of a neuralOS instance ends in exactly one of two honest outcomes:
a **confident answer**, or a **refusal**. A confident wrong number is worse
than an honest "I cannot answer this" — in a regulated deployment the first
is a silent lie, the second is a work item. The gate is what makes the
second outcome systematic instead of heroic.

The gate is a **pure function of the menu and the question**: no probe runs,
no model is called, no network is touched, microseconds. It exists in three
independent implementations that must satisfy the same observable contract:

| Implementation | Where | Runs |
|---|---|---|
| Python (`ask_gate` in the generated `ask.py`) | every factory-generated instance | **before** a probe executes |
| TypeScript (`askGate` in SuperAgent's `neuralosRuntime.ts`) | SuperAgent's MCP server | before the engine on ask-less instances; backstop on gateless hand-authored ask.py |
| Python (`router.py::_gate`) | neuralOSd | before probe execution |

Conformance across all three is enforced black-box by
`scripts/gate_conformance.py` (below) — the fleet fixture set proposed in
DrOlu/ReactorPro#107.

## The envelope contract

Every `ask.py` run prints **exactly one JSON envelope** on stdout:

```json
{
  "ask_id": "a-3f9c", "ts": 1760123456.7,
  "question": "which pages mention risk management",
  "normalized": "which pages mention risk management",
  "probe": "search_report", "confidence": 0.9, "latency_ms": 12,
  "menu_version": "b7e2a1c90d44", "mode": "retrieval",
  "refused": false, "refusal_reason": null, "gate_version": 1,
  "results": [ {"page": 19, "matches": 27} ]
}
```

| Field | Answered | Refused / nothing produced |
|---|---|---|
| `refused` | `false` | `true` |
| `refusal_reason` | `null` | one of the four reasons (below) |
| `gate_version` | `1` | `1` |
| `probe` | probe name | `null` |
| legacy keys `probe` / `confidence` / `latency_ms` / `mode` / `results` | present | `results: null` on refusal |

**Exit codes** (the machine contract — the envelope is the finer one):

| Exit | Meaning |
|---|---|
| `0` | answered — envelope carries results |
| `2` | nothing produced — refusal, or an answer that produced zero results (never print stale data) |

Additive-only evolution: new fields may appear (consumers must ignore
unknowns); `gate_version` bumps only when a refusal REASON's semantics
change. `stderr` is for human diagnostics only — never parse it.

## The four refusal reasons

Checked in this order. First hit wins.

### 1. `action_intent`

The question's FIRST word is an imperative action verb (`play erase delete
remove drop wipe purge send execute restart shutdown kill exploit deploy
cancel`) **and no probe claims that verb as a capability**. A probe named
`delete_records` or triggered on "delete records" legitimately knows the
verb and the carve-out does not fire.

- Checked first, **never bypassed** — not even by a cleanly extracted enum
  argument. "play the rock music" extracts `genre=Rock` perfectly; the
  extracted enum proves the SUBJECT, but the user asked for an action no
  probe can perform, and answering with the nearest data would be a
  confident wrong answer about what the system just did.
- **Capability ≠ data**: the carve-out weighs triggers, probe names and
  descriptions only — NOT enum values. Enum values are data. A bucket
  literally named `do-not-delete-ssm-diagnosis-…` must not teach the menu
  the verb "delete" (this exact false negative shipped in the router's
  shared vocabulary; the generators fix it, the TS gate fixes it, router.py
  is tracked in DrOlu/ReactorPro#107).

### 2. `no_probe_matches`

A domain noun of the question is unknown to **every** probe (triggers +
names + descriptions + enum values, plural-insensitive both ways:
"incidents" counts as knowing "incident"). The nearest-probe answer to an
unknown subject is a guess wearing a confidence score.

### 3. `dropped_filter:<qualifier>`

The question carries a status/time qualifier (`blocked overdue rejected
closed resolved pending escalated cancelled archived "on hold" "last week"
"last month" "last year" "this week" "this month" yesterday today
unassigned`) that the winning probe's vocabulary lacks. Executing the winner
would silently DROP the filter the user named — an answer that looks right
and is wrong. The reason names the dropped qualifier
(`dropped_filter:blocked`).

### 4. `low_coverage`

The winner knows fewer than half (`MIN_QUESTION_COVERAGE = 0.5`) of the
question's **domain nouns** — content words minus generic intent ("how
many", "show me", "top"…) and bare numbers. A probe that wins on generic
words alone doesn't understand the question.

### The one bypass: cages vouch

An enum or pattern **cage** that the question literally satisfies — the
question contains an exact enum value, or matches the argument's extraction
pattern — is the strongest possible evidence the question is understood.
A visible cage hit bypasses reasons 2–4 for the winner. It **never**
bypasses `action_intent`.

Pattern/integer cages must actually BIND: `load_cages` registers every
required enum, pattern and integer argument, and `extract_args` extracts
from that registry (a pre-2026-10 template registered enums only, so
pattern-caged arguments like `page\s+(\d{1,3})` silently fell through to
the model — fixed and pinned by tests; regenerate old instances).

## Menu shapes

`needle_menu.json` may be a **bare probe array**, `{"menu": [...]}` or
`{"probes": [...]}` — all three are accepted by the generated ask.py, the
TS gate and `gate_conformance.py`. Anything else (e.g. an object carrying
only metadata keys) is a hard error naming the offending shape.

## The audit trail & the gap loop

Every ask — answered, refused, or empty — appends one JSON line to
`ask_audit.jsonl` in the instance directory:

```json
{"ts": 1760123456.7, "ask_id": "a-3f9c",
 "question": "frobnicate the widget sanctuary",
 "probe": null, "mode": "refused",
 "refused": true, "refusal_reason": "no_probe_matches",
 "gate_version": 1, "results": null,
 "candidates_retrieved": ["count_rows"]}
```

- `candidates_retrieved` is what retrieval *almost* picked — the seed of
  the fix (right family, missing trigger phrasing).
- Refusals decided **inside SuperAgent** (ask-less instances, and the
  action backstop on gateless hand-authored ask.py) are appended by the TS
  gate in the same shape, marked `"via": "superagent-ts"`. ask.py's own
  records carry no `via` field. ask.py refusals are never double-written.
- Mine the log with `scripts/mine_gaps.py` (Phase 5): trigger proposals for
  the probe retrieval ranked first, new-probe candidates for questions that
  retrieved nothing. Review, apply, `lint_triggers.py`, full selection
  suite.

## Conformance — `scripts/gate_conformance.py`

Black-box: it drives the instance's `ask.py` as a subprocess and asserts
the observable contract (exit code + envelope), so it works identically on
macOS, Linux and Windows and against ANY GATE_VERSION 1 implementation.

```bash
# built-in matrix derived from the instance's own menu
python scripts/gate_conformance.py --instance /path/to/instance --verbose

# with an explicit fleet matrix (the shared fixture set)
python scripts/gate_conformance.py --instance . --cases cases.json
```

The built-in matrix derives, from the menu itself:

1. **False-refusal sweep** — every probe's first trigger must answer, routed
   to that probe;
2. an `action_intent` case (skipped when a probe legitimately claims the
   verb);
3. a `dropped_filter` case for the first qualifier the winner lacks
   (skipped when the winner knows them all);
4. an `unknown-subject` case.

A case whose precondition this menu violates is **SKIPPED, never failed** —
conformance never asks a menu to be something it is not. Exit `0` all
passed, `1` any failed. Wire it into CI next to `lint_triggers.py`; re-run
after EVERY menu edit (menu changes can flip any pick).

Explicit case schema:

```json
[
  {"question": "count rows",              "expect": "answered", "probe": "count_rows"},
  {"question": "delete all the rows",     "expect": "refused",  "reason": "action_intent"},
  {"question": "show blocked pages",      "expect": "refused",  "reason": "dropped_filter:blocked"},
  {"question": "frobnicate the widget",   "expect": "refused",  "reason": "no_probe_matches"},
  {"question": "shut it all down",        "expect": "exit",     "code": 2}
]
```

`refused` reason matching is by FAMILY: a parameterized
`no_probe_matches(unknown=widget)` satisfies `"reason": "no_probe_matches"`.

## Rules for implementers (all three implementations)

1. Gate on **menu + question only** — no probe, no model, no network, no
   clock-dependent behavior on the refusal path.
2. `action_intent` first, against the whole menu, **even when retrieval
   found nothing** — "delete all orders" must be refused, not reported as a
   retrieval miss.
3. Tokenize consistently: `[a-z0-9_]+` on lowercased text, drop stop words,
   strip plural `s` from tokens longer than 3 chars.
4. Coverage denominators use domain nouns, not all content words — "how
   many worklog entries exist" measures over `{worklog, entries, exist}`,
   not the five raw tokens.
5. Refusal envelopes are answers: `exit 2`, `refused: true`, named reason,
   `results: null`, `candidates_retrieved` filled. Never an empty stdout.
6. A refused question is a WORK ITEM: audit it, mine it, extend the menu —
   the gate is the beginning of the learning loop, not a dead end.
