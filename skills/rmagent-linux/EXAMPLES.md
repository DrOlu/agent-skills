# rmagent-linux worked questions

Grain: `(host, principal)`. Door: SSH. Cases: `~/.rmagent/cases/`.

```bash
python3 scripts/census.py --inventory examples/estate.example.yaml
python3 scripts/hunt.py --inventory examples/estate.example.yaml --since 2h
python3 scripts/drift.py --inventory examples/estate.example.yaml
```

`attest` must carry `blind_check` + `blind_count`. Empty + `blind_count>0` is
**not** clean.

macOS (`os=darwin`): `journald` reports `macos-experimental` — a hole, not a
fake sighted box.

Distro cron (`anacron`, `logrotate`, `sysstat`) is shed by the attackmap FP
allowlist — same lesson as Windows netsh×17.
