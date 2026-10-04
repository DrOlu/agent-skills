# Golden + trap banks — behavioral regression protection for instances

Structural tests (menu lint, caged-arg hygiene, read-only checks) protect the
menu's *shape*. They do NOT protect its *behavior*: one probe edit can silently
re-break a routing and nothing screams. Behavioral banks close that gap.

## The two banks

### 1. `golden.json` — positive bank (questions that MUST be answered)

```json
{"items": [
  {"q": "how many open incidents", "expect_probe": "open_incidents"},
  {"q": "what is the ratio of open problems to open incidents",
   "expect_probe": "open_problems_to_incidents_ratio"},
  {"q": "how many worklog entries exist", "expect_probe": "worklog_count"}
]}
```

Replay after every menu change:

```bash
neuralosd golden --instance-dir ./wema-bmc
```

Source the cases from verified sessions only: every `expect_probe` must have
been live-verified (routing confirmed AND the answer truth-checked against the
source). Never add a case whose answer you have not independently confirmed —
a bank entry with a wrong expectation is a time bomb that fails every future
correct change.

### 2. Trap bank — questions that MUST be refused

**SCHEMA TRAP (verified):** `golden_run` counts a case as PASS when
`expect_probe is None` and *any* probe returns non-empty results. Encoding
traps as `expect_probe: null` silently passes everything — the trap asserts
nothing. Until the schema gains `expect_refusal`, carry traps as explicit
unit tests in the instance's test file:

```python
def test_traps_are_refused(self):
    for q, why in [("how many worklog entries exist", "no probe (pre-worklog_count)"),
                   ("are there more open problems or open work orders",
                    "comparison - no probe")]:
        env = ask(q)          # instance ask path, real routing
        self.assertTrue(env.get("probe") is None or env.get("error"),
                        f"trap answered confidently: {q} ({why})")
```

A trap answered confidently fails the build even if 100 positives pass.

## The ask.py floor — what it does and does not catch (measured)

The instance-local `ask.py` refuses when the best lexical score is ≤ 0
("no probe matched"). This is a real refusal path and in live testing it was
the ONLY flow of six that refused an unanswerable question. Its limits:

- catches **zero-overlap** misses (unrelated vocabulary)
- does **not** catch **confident-wrong overlaps** ("are there more problems
  or work orders" shares tokens with quantity probes and scores high)
- has no confidence gates, no margin rule, no dropped-filter detection —
  those live in the neuralosd Router (`--strict`, unconsumed-filter penalty,
  out-of-range refusal)

So: floor in `ask.py`, gates in the Router, banks in CI. Layers, not one check.

## Worked example — wema-bmc (2026-10-03/04)

Everything below was live-verified and is bank-ready:

| q | expect_probe | truth |
|---|---|---|
| how many open incidents | open_incidents | 34 (independent pagination) |
| how many incidents were submitted in the last 7 days | incidents_in_last_days | 2521 (independent pagination) |
| what is the ratio of open problems to open incidents | open_problems_to_incidents_ratio | 8/34 = 0.235294 |
| what is the ratio of open changes to open incidents | open_changes_to_incidents_ratio | 12/34 = 0.352941 |
| how many worklog entries exist | worklog_count | 20000 capped-honest |
| which support group has the most open incidents | open_incidents_by_group | IAM 11 / Core Banking 9 |

Traps (must refuse): per-group task filter questions, vendor-escalation
counts, any compound phrasing with no matching probe family.

## Process rule

Every gap-queue resolution (probe added to close a logged failure) adds one
golden positive AND one trap variant to the banks in the same change. Banks
grow with the menu or they rot.
