---
name: rmagent-pack
description: >
  Artifact recipes and detection rule packs as CODE, run one-shot and
  lake-less. Borrows the facts from collector/rule libraries (Velociraptor
  artifacts, Sigma, ATT&CK) and runs them the rmagent way: a named question
  executed on the box, a capped JSON answer, holes instead of dumps. Two
  halves — collection recipes (prefetch, amcache, usb, shimcache) and pure
  rule logic (events -> filters -> thresholds -> finding). No server, no
  agent, no central store. Answers "what actually executed?" and "does this
  pattern mean abuse?", never "ship everything to a warehouse".
---

# rmagent-pack — artifact recipes & rule packs, as code

A **pack** is a named set of rules. A **rule** is events + filters +
thresholds + meaning. Both live in git, both have tests, both stay small.

This is how the rmagent observatory borrows the *ideas* in Velociraptor's
artifact library and the community rule packs **without taking their
architecture**. It keeps pull-only, capped answers, holes, and no lake.

## The two halves (deliberately separate)

| Half | Question | Where | Network |
|---|---|---|---|
| **Collection** | "give me what's on the box" | `scripts/questions/windows/*.ps1` | one knock, capped |
| **Rule logic** | "what does it mean" | `scripts/packs/*.py` | none — pure, testable |

Collection is a `ask()` question like any other. Rule logic is a function
over rows you already pulled. Neither needs a server.

## Collection recipes (one-shot, no agent)

| Question | Recipe | What it proves |
|---|---|---|
| `prefetch` | `art.prefetch` | a binary EXECUTED, even if the file is gone |
| `amcache` | `art.amcache` | first-seen path/time of an executed binary |
| `usb` | `art.usb` | USB mass-storage insertion (physical-access timeline) |
| `shimcache` | `art.shimcache` | weak execution corroboration when prefetch is off |

Every one returns `blind: true` when its artifact is absent — a disabled
prefetch is **"execution proof unavailable"**, never "nothing ran".

## Rule packs (the ideas)

`kerberos_ad` — Kerberoasting (RC4 TGS sweep), AS-REP roasting, pre-auth
spray, **DCSync** (4662 + DRS replication GUIDs), DCShadow, privileged-group
adds, audit cleared.

`artifact_recipes` — the collection ideas above, as rules with thresholds.

### The rule shape, in code

```python
Rule(
    id="krb.kerberoast",
    events=[4769],
    source="dc.krb",
    filters={"TicketEncryptionType": {"in": ["0x17","23"]},   # RC4 only
             "TargetUserName": {"regex": r"[^$]$"}},          # not machine accts
    thresholds={"distinct": "ServiceName", "count": 3},        # 3+ distinct SPNs
    severity="high", technique="T1558.003",
    why="the classic Kerberoast sweep",
)
```

## The ethos, carried into the logic

- **A blind source cannot fire.** `run(..., blind_sources={"dc.krb"})` turns
  any rule on that source into a **hole**, never a finding.
- **Thresholds have a floor.** A ratio needs a denominator of ≥ 30 (same
  floor as the thinker) or the ratio is reported as a hole.
- **Findings carry a count and ≤ 3 example rows** — enough to act, never the lake.
- **Facts borrowed, execution ours.** The event IDs / GUIDs / thresholds come
  from public rule packs; the pull, the cap, and the holes are rmagent's.

## Run it

```bash
cd ~/.agents/skills/rmagent-pack/scripts

python3 test_pack.py                       # 19 assertions, no network
python3 packs_cli.py list                  # packs and rule counts
python3 packs_cli.py show kerberos_ad      # every rule: events/filters/thresholds
python3 packs_cli.py run kerberos_ad --rows rows.json
python3 packs_cli.py run kerberos_ad --rows rows.json --blind dc.krb   # hole, not finding
```

`rows.json` is just `[{"eid":4769,"TicketEncryptionType":"0x17","ServiceName":"MSSQLSvc/a"}, …]`
— the output of a `so` `krb`/`dcsync` pull, or any event rows you have.

## What this is NOT

- **Not a Velociraptor server.** No server, no agent, no reporting home.
- **Not a lake.** Rules return counts and 3 examples; collection is capped at 32 KB.
- **Not a collection framework.** It is a place to *put the ideas* as code,
  with the few one-shot payloads needed to feed them.

## Relationship to the other skills

| Skill | Role |
|---|---|
| `rmagent-so` | pulls the events (krb/dcsync/dirchange) these packs reason over |
| `rmagent-fr` | files the case the findings land in (same ticket) |
| `rmagent-core` | the engine + the grain firewall that keeps this a separate grain |
| `rmagent-actuate` | response, only after a rule fires on a source that can SEE |

## Scripts

| File | Role |
|---|---|
| `scripts/rulepack.py` | Rule/Pack dataclasses, predicate engine, thresholds, blind-hole rule |
| `scripts/packs/kerberos_ad.py` | the DC/Kerberos rule pack |
| `scripts/packs/artifact_recipes.py` | the collection recipes |
| `scripts/packs/__init__.py` | pack registry |
| `scripts/lib.py` | `ask()` (via rmagent-core) + `run_pack()` |
| `scripts/packs_cli.py` | list / show / run |
| `scripts/test_pack.py` | 19 fixture tests |
| `scripts/questions/windows/{prefetch,amcache,usb,shimcache}.ps1` | one-shot collection |
