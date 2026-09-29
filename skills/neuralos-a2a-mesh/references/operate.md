# Operate — day-2 runbook

## 1. Daily / per-shift checks

```bash
bash scripts/doctor.sh                     # env + connectivity + engine + menu
curl -s "$NATS_MON/varz" | jq '{version,connections,uptime}'
curl -s "$NATS_MON/jsz"  | jq '{api:.api.errors,memory:.memory,storage:.storage}'
curl -s -H "Authorization: Bearer $LIVEAGENT_GATEWAY_TOKEN" \
     localhost:3000/api/mesh/status | jq
```

Watch: `mesh_inbound_total` (peers talking to you), `mesh_invoke_denied_total`
rising with flat `mesh_invoke_total` (policy holding a peer off — that is the
floor working), `mesh_task_input_required_total` (paused tasks).

## 2. Benchmark discipline

- Questions must be **never-seen-before** (fresh phrasings).
- Measure **wall time end to end** from at least **two origins**, through each
  origin's own gateway.
- Record the engine's own telemetry when available (`prefill_tps`,
  `decode_tps`, `peak_ram_mb`) — it separates engine health from network/db
  slowness.
- Keep a results table in the deployment record; re-run after every change.

Reference numbers from a proven three-edge deployment (Mac + 2 Windows
servers, one grounded question each): engine ~161 tok/s prefill, ~62 tok/s
decode, ~79 MB peak RAM; cross-edge wall 0.2–9.7 s depending on path.

## 3. Adding an edge

1. Intake its parameters (`references/parameters.md` §B).
2. Install engine + gateway + butler (`references/install.md`).
3. Exchange fingerprints with **every** existing edge (out of band).
4. Add the new fingerprint to each existing edge's `MESH_TRUSTED_PEERS`;
   give the new edge the full peer list. Restart gateways.
5. Benchmark new-edge → one existing edge (both directions).
6. Add it to the monitoring/audit inventory.

## 4. Adding or changing a skill

Follow `references/butler-harness.md` §4 (add probe → verify → restart).
If several peers call it, announce the new capability: peers re-read the
manifest from `mesh.registry`.

## 5. Upgrade and rollback

- **Engine**: swap the weights/binary file in `NEEDLE_ENGINE_DIR`; the next
  invocation loads the new file. Keep the previous file beside it for instant
  rollback. Re-run the selection suite after every engine change.
- **Gateway**: stop service → replace binary → start → verify `/healthz` and
  `describe` (pins intact) → benchmark one question. Keep the previous binary.
- **Harness/menu**: backup the file (`.bak-<timestamp>`), edit, syntax-check,
  restart the service, verify with a fresh phrasing.
- Never upgrade all edges at once; stage one edge, verify, then roll.

## 6. Reboot survival

Confirm on every edge that a machine restart brings everything back with no
human action: launchd `RunAtLoad`+`KeepAlive`, systemd `Restart=always`,
NSSM `AUTO_START`. Test it once per edge and record the result.

## 7. Security maintenance

- **Pins**: adding/removing a peer means editing `MESH_TRUSTED_PEERS` on
  **both** sides and restarting. A pin change invalidates nothing else.
- **Gateway token**: rotate by generating a new token, updating every caller
  and the service env, then restarting. Callers only need the token, not a pin.
- **NATS credentials**: rotate per-agent NKeys/creds centrally; the server
  reloads on SIGHUP without dropping connections.
- **Secrets**: keep credentials in `0600` files or a secret store; never in
  unit files, scripts committed to git, or chat.
- **Audit**: ship each instance's write-audit log and the gateway task records
  to central logging; they are the evidence trail.

## 8. Capacity and cost

- One engine serves sequential tool calls. Busy edges run **one engine per
  butler** rather than sharing (isolation is trivial, ~79 MB each).
- Grounded answers cost a few KB of bandwidth plus the round trip; the model
  share is a fraction of a second. Budget for the NATS round trip and the
  database, not the model.
- JetStream storage grows with mailbox/task retention; set retention to the
  audit requirement, not to "forever".

## 9. Incident record (keep per deployment)

| Field | Value |
|---|---|
| Edges and identities | |
| Fingerprints and pins | |
| NATS endpoint + account | |
| Skills exposed per edge | |
| Benchmark table (origin → target, wall) | |
| Reboot-survival test result | |
| Known holes / accepted trade-offs | |