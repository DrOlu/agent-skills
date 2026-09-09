---
name: rmagent-core
description: >
  Shared lake-less engine for every rmagent-* skill — grain ALLOWED maps,
  case paths under ~/.rmagent, and the thin loader other skills import so they
  do not vendor a second lib.py. Not a witness. Load rmagent-so / linux / at
  to ask boxes.
---

# rmagent-core — shared engine, not a witness

This skill is the **one engine** the family imports. It has no door and no
payloads. Questions live in the grain skills. Cases, baselines, census
history, silent-host book, actuate journal, and drill history live under
`~/.rmagent/` — never inside a skill checkout.

## Constitution

1. Watch only (Phase 0) in question skills. Actuate is a separate skill.
2. Allowlisted questions only. Grain firewall: a skill may only ask its grain.
3. Capped answers (32 KB). Oversized → hole.
4. A hole is an answer.
5. Never trust “no findings” until attest/blind_check can see.
6. On-device rings, not shipped lakes. Jump host stores **cases** (megabytes).
7. Context propagates; data does not.
8. Credentials never in inventory / skill / case.
9. Your estate only.
10. No tight retry on a silent host.
11. Secrets / PAN / prompt text never stored unless masked.
12. Persistent rings are MOP, dry-run default, `--apply` + `--teardown`.
13. Honest fidelity gaps.
14. Keep the existing sensor.

## Grain firewall (`scripts/grains.py`)

| Skill | Grain | ALLOWED |
|---|---|---|
| rmagent-so / windows | principal + LogonId | identity questions |
| rmagent-linux | principal (root) | attest sketch edges explain attackmap |
| rmagent-at | request-ish | apptrace appslow apperrors appnet appproc appsysmon |
| rmagent-ao | host, agent, session | agents agentstate agenttrace agentnet agentmodels agentdrift agentdeep |
| rmagent-fr | ticket | **none** — records cases, does not ask boxes |
| rmagent-iso | STAN+RRN wire | txnattest txntrace txnhops txnslow txnfail txnbaseline |
| rmagent-pay | STAN+RRN diary | pay_attest switch_txn core_auth pay_sketch hop_delta |

App questions are **not** legal on so. Identity questions are **not** legal on at.
fr has an empty allowlist.

## Paths (`scripts/paths.py`)

```
~/.rmagent/cases/
~/.rmagent/baselines/
~/.rmagent/census_history.jsonl
~/.rmagent/silent.json
~/.rmagent/actuate.jsonl
~/.rmagent/drill/
~/.rmagent/creds.json
```

## Loader (`scripts/loader.py`)

Other skills load the canonical so engine with `spec_from_file_location`
(never `sys.path` + `import lib`). Then they **replace `ALLOWED`** with their
grain set.

## Will not do

- Ask a box.
- Copy Security.evtx / pcap / ETL home.
- Grow without bound. Cases prune raw answers on close.
