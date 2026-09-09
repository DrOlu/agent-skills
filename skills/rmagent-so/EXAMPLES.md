# rmagent-so — identity questions only

Grain: `(host, principal, logonid)`. Cases: `~/.rmagent/cases/`.

```bash
python3 ~/.agents/skills/rmagent-windows/scripts/census.py --inventory estate.yaml
python3 ~/.agents/skills/rmagent-so/scripts/hunt.py --inventory estate.yaml --since 2h
```

`attest` returns `domain_role` (`dc|member|workgroup`) + `blind_check`.
App ETW questions (`apptrace` …) are **not** on this skill — use `rmagent-at`.
