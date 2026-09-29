# Troubleshooting — connection, trust, gateway, butler, engine

Work **top-down**: transport → trust → gateway → butler → engine → data. Every
layer has a specific signature; do not jump to the engine when the failure is a
pin.

## 0. First move: the doctor

```bash
bash scripts/doctor.sh          # macOS/Linux  (pwsh -File scripts\doctor.ps1 on Windows)
```

It checks each layer and prints PASS/FAIL with the exact command that failed.
Use its output to jump to the right section below.

## 1. Transport (NATS)

| Symptom | Cause | Fix |
|---|---|---|
| `connection refused` | wrong host/port, server down | `nc -vz $HOST $PORT`; check `$NATS_MON/varz` |
| TLS handshake error | `nats://` used for a TLS server, or missing CA | use `tls://`; provide the CA or `--tls-ca` |
| connect ok but everything times out | wrong account, or subject permissions denied | check server logs; see §3 |
| `permissions violation for publish to "mesh.agent.x.inbox"` | the agent's role lacks the subject | apply the per-role template (the `synapse-client` skill's `config.md`, plus `references/parameters.md` §A) |
| JetStream API errors from an edge | leaf node not isolated / wrong account | dedicated `LOCAL` account with `jetstream: enabled`; `curl $NATS_MON/jsz` → `api.errors == 0` |
| Reconnects every few minutes | flaky link or wrong `max_payload` | check `$NATS_MON/connz`; raise `max_payload` only if large payloads are expected |
| Envelope refused: stale/fresh | clock drift | sync NTP on both edges; window is ±5 min |
| Duplicate edge id | two hosts share `-mesh-agent-id` | ids are unique and immutable; re-mint the duplicate |

## 2. Trust and identity

| Symptom | Cause | Fix |
|---|---|---|
| `3004 IDENTITY_MISMATCH` / "caller did not present a verified identity" | unsigned caller, wrong key, or the fingerprint is not pinned | pin the caller's fingerprint on the receiver (`MESH_TRUSTED_PEERS`) and restart |
| Works from A→B but not B→A | only one side pinned | **mutual** pins: each side lists the other's fingerprint |
| Peer shows in discovery but invoke is refused | discovery is data, not identity | pinning is what grants action; re-read `architecture.md` §4 |
| Signature valid but refused | id inside the fingerprint changed | restore the original `-mesh-agent-id` (changing it mints a new identity) |
| Replay refused | duplicate `id` within ~10 min | expected; the guard is working |

## 3. Gateway

| Symptom | Cause | Fix |
|---|---|---|
| `401` on `:3000` | missing/expired bearer token | send `Authorization: Bearer $LIVEAGENT_GATEWAY_TOKEN` |
| `/healthz` ok, `describe` empty | mesh disabled or registry TTL expired | enable mesh; wait ≤1 heartbeat (~30 s) |
| `3001 operation "" is not served by this edge` | used MeshSend/agent-turn against a headless edge | headless gateways serve `ping/describe/status/invoke/skillproxy` only — use `skillproxy` for butlers |
| `3002 no such agent` | target offline or name mismatch | check the peer's published directory |
| Task stuck `working` then failed at 10 min | desktop peer was busy (queue policy) | retry when the machine is idle |
| Mailbox work never runs | mailbox disabled or idempotency | enable mailbox; mailbox delivery is at-least-once → probes must be idempotent |

## 4. Butler (skillproxy)

| Symptom | Cause | Fix |
|---|---|---|
| `{"ok": false, "hole": true}` | engine selected no probe (menu gap) | extend the menu (add a probe with the right triggers) — do **not** add a keyword fallback |
| Reply `elapsed_s` high but result correct | database/upstream slow | profile the query; the engine share is a fraction of a second |
| Upstream API error echoed back | upstream genuinely failing | this is the honest-hole behaviour working; fix the upstream |
| Connection resets mid-answer | timeout shorter than the work | raise `timeoutMs` (gateway edge cap is 3 min by default) |
| Works locally, fails over the mesh | service not running as a service / bound to a different menu | check the NSSM/launchd/systemd status and `BUTLER_MENU` |
| `"error": "menu not found at … (set BUTLER_MENU)"` | harness cannot see its menu | set `BUTLER_MENU` to `needle_menu.json`; the harness answers with this hole instead of dying |
| `"error": "menu is not valid JSON: …"` | malformed menu (trailing comma, unquoted key) | validate the JSON: `python3 -c "import json;json.load(open('needle_menu.json'))"` |
| `"error": "NEEDLE_ENGINE_DIR is unset or missing"` | engine folder not exported to the service | add it to the unit/plist/NSSM env — never hardcode the path |
| `"error": "engine binary and/or weights not found in …"` | folder exists but has no `needle`/`neural` + `needle3.cact`/`neuralOS.engine` | unzip the neuralOS bundle into that folder |
| `"error": "bridge module 'x' could not be imported"` | `BUTLER_BRIDGE` wrong or the module has a syntax error | fix the name/`PYTHONPATH`; import it by hand once |
| `"error": "probe 'x' failed: …"` | the probe's own read-only query raised | read the relayed upstream message; fix the data source |
| `"error": "needle engine returned unparseable output"` | the binary is not the neuralOS engine, or its stdout was polluted | check `NEEDLE_ENGINE_DIR` points at the real engine; keep stdout clean |

> A butler **never** returns a traceback: menu, engine, bridge and probe failures all become structured holes (verified, 11-case suite). If the skill is silent or the service is stopped, it is a service problem — not a harness crash.

## 5. Engine (neuralOS/needle)

| Symptom | Cause | Fix |
|---|---|---|
| `needle: command not found` / engine path error | path hardcoded or `NEEDLE_ENGINE_DIR` unset | set the env var; put the binary + weights in the folder; never hardcode |
| `ModuleNotFoundError: neuralos` | wrong interpreter | install via that interpreter (`pip show neuralos`) or use the standalone binary |
| Model fills nonsense args (`host='mysql'`) | unconstrained string arg | add triggers + grammar constraints (`enum`/`pattern`) |
| Same probe called repeatedly | tool result too large fed back | return a digest, cap rows/bytes |
| Third part of a compound ask ignored | 2-ask limit | split into follow-up questions |
| Refusal with high confidence | missing triggers / drifting date fact | add triggers; pass a fixed system prompt and disable auto-date |
| Garbled unicode in results | charset on the wrapped CLI or mojibake source data | wrap stdout/stderr as UTF-8 in the harness |
| Weights mismatch | `needle3.cact` vs `neuralOS.engine` assumed different | they are interchangeable; both names are valid on every platform |

## 6. Cross-platform / remote-admin gotchas

| Gotcha | Detail |
|---|---|
| **Windows over PSRP** | never call `[Console]::OutputEncoding` inside a PSRP session (no console host → the pipeline dies and returns empty); wrap encoding changes only for interactive shells |
| **File transfer to Windows** | move files as base64 (`[Convert]::ToBase64String` / `FromBase64String`); heredoc/here-string writes can land as 0 bytes |
| **cPanel/panel file writes** | upload endpoints often refuse to overwrite; move the old file aside first, then upload; verify by fetching the public URL and comparing a hash |
| **Service restarts remotely** | a Windows service restart needs an elevated session; do not rely on an unelevated agent shell |
| **`cmd /c` vs `sh -c`** | the gateway's shell tool uses `cmd /c` on Windows, `sh -c` elsewhere — scripts must be written for the right one |
| **Line endings** | keep shell scripts LF; PowerShell scripts CRLF is fine |
| **`%USERPROFILE%` vs `~`** | expand the right form per platform in scripts |

## 7. Escalation checklist (attach when raising)

1. `doctor.sh` full output.
2. `curl $NATS_MON/varz` and `/jsz` (redact creds).
3. `localhost:3000/api/mesh/status` and `/api/mesh/agents`.
4. The exact dispatch envelope and the full reply (including `error`/`hole`).
5. Engine telemetry from the reply (`confidence`, throughput) if present.
6. Which layer the doctor says is failing.