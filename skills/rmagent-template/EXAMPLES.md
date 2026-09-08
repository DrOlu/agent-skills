# rmagent-template — factory examples

This skill does not hunt. It **stamps** and **lints**.

## Lint an existing family member

```bash
cd ~/.agents/skills/rmagent-template/scripts
python3 check_constitution.py --dir ~/.agents/skills/rmagent-iso
python3 check_constitution.py --dir ~/.agents/skills/rmagent-so
python3 check_constitution.py --dir ~/.agents/skills/rmagent-template
```

## Stamp a netops skill (does not replace `netops`)

```bash
python3 new_skill.py \
  --name rmagent-net \
  --title "Circuit Flight Recorder" \
  --grain "circuit_id + time window" \
  --sensor "SNMP allowlisted GETs + syslog JSONL ring" \
  --plane netops \
  --scope "PE routers we administer" \
  --out /tmp/rmagent-net-demo

python3 /tmp/rmagent-net-demo/scripts/test_net.py
python3 check_constitution.py --dir /tmp/rmagent-net-demo
```

Then fill the question table (`examples/question-table.md`) **before** SNMP
payloads. See COOKBOOK.md § NetOps.

## Skeleton ask() behaviour (lib_skeleton)

```python
from lib_skeleton import ask
ask("actuate")   # hole not-allowlisted
ask("baseline", n=3)  # hole baseline-n-too-small
ask("attest")    # skeleton, blind_check=unknown — do not trust emptiness
```

## After clone — order of work

1. One-sentence test in SKILL.md (must still be true).
2. Question table with Must-NOT column.
3. Real door in lib.py (copy patterns from rmagent-iso or rmagent-so).
4. Fixtures + tests that never need the live estate.
5. check_constitution.py exit 0.
6. One S2 scenario (hop localization) in EXAMPLES.md.
7. Live knock on boxes you administer.

Do not skip to a dashboard.
