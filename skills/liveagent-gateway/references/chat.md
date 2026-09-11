# Chat over the gateway

Chat is strictly orchestrated; it never travels as a raw pass-through arm.

## Message fields

### ChatCommandRequest (inside `chat_command`)

| # | Field |
|---|---|
| 1 | `type` — `chat.submit`, `chat.edit_resend`, `chat.cancel` |
| 2 | `request` (ChatRequest) |
| 3 | `base_message_ref` (for edit_resend) |
| 4 | `cancel` (CancelChatRequest) |

### ChatRequest

| # | Field |
|---|---|
| 1 | `conversation_id` |
| 2 | `message` |
| 3 | `selected_model` |
| 4 | `execution_mode` |
| 5 | `workdir` |
| 7 | `uploaded_files` (repeated) |
| 8 | `client_request_id` |
| 9 | `runtime_controls` |
| 10 | `queue_policy` |
| 11 | `command_safety_mode` |
| 12 | `referenced_conversations` (repeated) |

Field 6 is reserved. **Set `client_request_id` on every submit** — it is the idempotency key.

### CancelChatRequest

| # | Field |
|---|---|
| 1 | `conversation_id` |
| 2 | `run_id` |

## Lifecycle

### 1. Wake the runtime (`chat_prepare`)

`ChatPrepareRequest{ reason = 1 }`, targeted at an agent. The gateway sends a correlated Ping down the agent stream; the desktop wakes its chat runtime and returns a Pong. The gateway only answers `status` after a **real round trip**.

Freshness is bound to the agent session epoch and kept ~**2 seconds** — a command immediately after a successful prepare reuses it. Always prepare before a cold submit; a sleeping or half-open desktop link otherwise swallows the command.

### 2. Submit (`chat_command` type `chat.submit`)

Response: `chat_accepted{ run_id = 1, conversation_id = 2, accepted_seq = 3, deduped = 4 }`.

Keep the returned `run_id`. If the ACK is lost, retry **once** with the identical payload **and** the same `client_request_id` — the gateway returns the same canonical run and will not double-execute. `deduped: true` means your retry matched an existing run.

### 3. Subscribe (`chat_subscribe`)

`ChatSubscribeRequest{ conversation_id = 1; after_seq = 2; stream_epoch = 3 }`

Result `ChatSubscribeResult`: `conversation_id`, `stream_epoch`, `latest_seq`, `reset`, `activity`, `snapshot`, `events_json[]`.

Events then arrive as `chat_event`: `{ conversation_id = 1, seq = 2, payload_json = 3 }`.

### 4. Cancel (`chat_command` type `chat.cancel`)

The gateway marks `cancelling`; the desktop's real terminal state wins, with a watchdog fallback to `run_finished(cancelled)`.

### 5. Edit and resend (`chat.edit_resend`)

Carries `base_message_ref{ segment_index, message_index, segment_id, message_id, role, content_hash }`. The gateway publishes `rebased` plus the new user message; the desktop truncates atomically and runs the new turn.

## Events and normalization

Low-level desktop events (`TOKEN`, `THINKING`, `TOOL_CALL`, `TOOL_RESULT`, `DONE`, `ERROR`, `TOOL_STATUS`, `HOSTED_SEARCH`) receive a per-conversation monotonic `seq` and are normalized into control events: `run.accepted`, `user.message.appended`, `conversation.rebased`, `projection.updated`, `run.completed`, `run.failed`, `run.cancelled`.

Inspect `payload.type` to detect completion. `DONE` maps to `run.completed`.

## Recovery and idempotency

| Mechanism | Behaviour |
|---|---|
| Event window | Last **10 minutes** per conversation, hard cap **4096 events / ~8 MiB** |
| Active runs | Not time-evicted until the hard cap is reached |
| Idle conversations | Reclaimed after ~30 min |
| Resume | `chat_subscribe` with `after_seq` replays from the window |
| Reset | Epoch change, cursor ahead, or evicted events → `reset`; rebuild from the desktop history snapshot |
| Overflow | `chat_subscription_reset` tells you to re-subscribe by cursor |
| Dedupe | `client_request_id` → canonical run, **24 h**, atomic |
| Command ACK | Client waits ≤ **4 s**, retries once with an identical payload |

**Process-local only.** The event window and dedupe map do **not** survive a gateway restart. Exactly-once is *not* promised across restarts — reconciliation comes from the desktop history snapshot and run-ledger republish.

## Watchdogs

| Stage | Default |
|---|---|
| `chat.prepare` native Ping/Pong | 2 s |
| Delivery of an accepted command to the desktop stream | 5 s |
| Waiting for the remote command to start | 5 s |
| Additional render-start window | 10 s |
| Stale run, agent online | 10 min |
| Stale run, agent offline | 30 min |
| Run report lost | 15 s → `failed/desktop_run_lost` |

A run that never starts receives `run.failed` rather than hanging forever. Treat a timeout as a real failure, not as "still working".

## Practical recipe

```bash
python3 scripts/lag_ws.py send "summarise the open incidents" --timeout 180
```

This performs: handshake → `chat_prepare` → `chat.submit` (with `client_request_id`) → stream `chat_event` until `DONE`.

To follow an existing conversation instead:

```bash
python3 scripts/lag_ws.py watch --conversation <id> --after-seq 0
```

To cancel whatever is running:

```bash
python3 scripts/lag_ws.py cancel --conversation <id> --run-id <run>
```

## Related arms

| Arm | # | Purpose |
|---|---|---|
| `ChatQueue` | 73 | Prompt queue; events as `chat_queue_event` (frame 24) |
| `ClarifyTurn` | 101 | Answer an agent's clarifying question (delta via `clarify_turn_delta`) |
| `ChatFileOpen` | 94 | Open a file referenced in a chat message |
| `Checkpoint` | 98 | History checkpoint / rewind |
| `TrajectoryFetch` | 99 | Fetch the reasoning trajectory of a run |
