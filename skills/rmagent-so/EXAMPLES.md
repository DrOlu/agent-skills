# rmagent-so — identity questions only

Grain: `(host, principal, logonid)`. Cases: `~/.rmagent/cases/`.

```bash
python3 ~/.agents/skills/rmagent-windows/scripts/census.py --inventory estate.yaml
python3 ~/.agents/skills/rmagent-so/scripts/hunt.py --inventory estate.yaml --since 2h
```

`attest` returns `domain_role` (`dc|member|workgroup`) + `blind_check`.
App ETW questions (`apptrace` …) are **not** on this skill — use `rmagent-at`.

## Enterprise usage patterns

**Sizing:** one census knock ≈ 2 s/witness; a 15-question hunt ≈ 30 s/witness
capped at 32 KB each. A 100-witness estate: census sweep ~4 min serialized
(parallelize by groups), full hunt ~1 h — or scope `--since` tighter and let
drift tell you which hosts deserve the deep pull.

**Cadence that works:**
- `census` every 5 min (cron) — the minute-watch; 2 misses = Critical.
- `drift` per shift or per day — the "witness got weird" baseline.
- full `hunt` on trigger (drift finding, canary hit, or human request).

**Blindness is a finding, not a footnote:** `blind_check` in every attest —
audit-subcategory off, log rolled, or clock skew all surface as BLIND and the
census marks the host silent. Never accept a clean-looking answer from a
blind witness; re-enable the subcategory or record the hole.

**Watch-only:** this skill never changes a witness. Response belongs to
`rmagent-actuate` (named, journaled, reversible) after a human approves.
