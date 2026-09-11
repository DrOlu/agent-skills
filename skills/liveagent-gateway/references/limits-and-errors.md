# Limits, errors, and failure modes

## Authentication failures

| Symptom | Meaning |
|---|---|
| HTTP **401** | Missing or invalid bearer token on a REST call |
| WS close **4401** | Hello rejected (bad token, or wrong role for the endpoint) |
| `ServerHello.ok = false` | Same, with a `message` such as `unauthorized` |
| *"unexpected client role"* | A browser hello on `/ws/v2/agent`, or vice versa |
| *"agent_id is required"* | Target the request at a specific agent |

Credential failures return a uniform `unauthorized` to prevent agent-id enumeration. An `agt_` token used against a different agent, or on the browser link, is rejected **by design** — not a bug.

## `local_error`

Gateway-originated errors arrive as WebServerFrame field **4** = `ErrorResponse{ code = 1, message = 2 }`. These are gateway-level (bad request, missing agent) and never reached a desktop. If you see one, the request never executed.

## Size limits

| Link | Max message |
|---|---|
| `/ws/v2` browser | 4 MiB |
| `/ws/v2/agent` | 64 MiB default (uploads need it) |
| `/ws/v2/terminal` browser | 1 MiB |
| `/ws/v2/terminal` agent | 16 MiB |

The negotiated value arrives in `ServerHello.max_message_bytes`. Exceeding it fails the send.

## Concurrency

| Link | Default cap | Configuration |
|---|---|---|
| agent | 256 | `LIVEAGENT_GATEWAY_MAX_AGENT_CONNECTIONS` |
| browser | 128 | `LIVEAGENT_GATEWAY_MAX_BROWSER_CONNECTIONS` |
| terminal | 512 | `LIVEAGENT_GATEWAY_MAX_TERMINAL_CONNECTIONS` |

Over the cap you receive **503 before the upgrade**. The browser link additionally allows 16 in-flight dispatches per connection and an inbound token bucket of **100 frames/s (burst 200)**.

## Heartbeats

Browser ping every **15s**, agent link **30s**, grace 5s. Idle eviction ≈ `3 × period + grace`. Reply to application-level `PingFrame`s with `PongFrame`, or you will be evicted.

## Failure modes

| Failure | What you observe | Handling |
|---|---|---|
| Desktop offline | `online=false`; requests return agent-offline | Surface it; do not retry in a tight loop |
| WebSocket drops | You disconnect | Reconnect, re-send `chat_subscribe` with `after_seq` |
| Window insufficient | `reset` or `chat_subscription_reset` | Re-subscribe from 0; rebuild from the history snapshot |
| Agent stream drops | Session closes | The desktop auto-reconnects and republishes its run ledger; the gateway adopts it idempotently |
| First message after long idle | A half-open socket swallows it | Always `chat_prepare` first; failure then returns fast |
| Terminal signal lost | Run finished but activity lingers | The desktop ledger re-sends terminal states every 5s |
| Stuck run | No progress | `staleRunTimeout` 10 min online / 30 min offline |
| Command never enters run state | Only `accepted`/`delivered` | Watchdogs write `run.failed` after 5s + 10s |
| Duplicate submit | Same `client_request_id` | 24 h process-local dedupe returns the canonical run |
| Gateway restart | Event window + dedupe lost | Reconcile from the history snapshot; no exactly-once across restart |
| Shutdown | Container stops | Graceful HTTP shutdown on SIGINT |

## Interpreting an empty result correctly

Zero agents, zero conversations, or an empty event window means **no data was returned** — not that nothing is wrong.

Before reporting "nothing found":

1. Confirm `online=true` and `agent_ready=true` for the target agent.
2. Confirm `chat_runtime_ready=true` before expecting chat events.
3. Confirm the request reached a desktop (an `agent_response` frame, not just `local_error`).

An unparseable or absent answer is a **hole**, not a clean result.

## Quick diagnostics

```bash
# 1. Is the gateway alive?
curl -sS "$LAG_GW/healthz"

# 2. Does auth work, and is any agent online?
curl -sS -H "Authorization: Bearer $LAG_TOKEN" "$LAG_GW/api/status"

# 3. Which agents exist?
bash scripts/lag.sh agents

# 4. Can I handshake (protocol-level)?
python3 scripts/lag_ws.py probe

# 5. Is the runtime awake?
python3 scripts/lag_ws.py status --agent "$LAG_AGENT"
```

Work down that list: a failure at step 1 is networking, at 2 is credentials, at 3 is registration, at 4 is protocol/version, at 5 is the desktop itself.
