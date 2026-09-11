# Protocol v2 — WebSocket + Protobuf

Since protocol v2, **all** realtime traffic is WebSocket + Protobuf over a single HTTP port.

## Endpoints

| Endpoint | Role | Purpose |
|---|---|---|
| `/ws/v2` | `BROWSER` | Controller link — local ops, pass-through, broadcasts |
| `/ws/v2/agent` | `AGENT` | Desktop envelope stream |
| `/ws/v2/terminal` | both | Terminal byte stream (role from hello) |

## Handshake

1. Open the WebSocket with subprotocol **`liveagent.v2.pb`**.
2. Send `ClientHello` as the **first** binary frame.
3. Receive `ServerHello`.
4. On failure the server closes with code **4401**.

One binary WS frame = one protobuf message. **Text frames are ignored.**

### ClientHello

| # | Field | Notes |
|---|---|---|
| 1 | `protocol_version` | must be `2` |
| 2 | `role` | `0` unspecified, `1` BROWSER, `2` AGENT |
| 3 | `token` | gateway token, or `agt_…` for the AGENT role |
| 4 | `agent_id` | **required** for the AGENT role |
| 5 | `agent_version` | optional |
| 6 | `client_name` | optional |
| 7 | `client_version` | optional |
| 8 | `capabilities` | repeated string |

### ServerHello

| # | Field |
|---|---|
| 1 | `ok` (bool) |
| 2 | `message` |
| 3 | `session_id` |
| 4 | `server_time` |
| 5 | `heartbeat_period_seconds` |
| 6 | `max_message_bytes` |
| 7 | `capabilities` |

A mismatched role returns *"unexpected client role"* — a browser hello on `/ws/v2/agent` is refused.

## Browser frames

### WebClientFrame (you → gateway)

| # | Field |
|---|---|
| 1 | `request_id` |
| 2 | `hello` |
| 3 | `agent_request` (GatewayEnvelope) |
| 4 | `status_get` |
| 5 | `chat_command` |
| 6 | `chat_prepare` |
| 7 | `chat_subscribe` |
| 8 | `chat_unsubscribe` |
| 9 | `chat_activities` |
| 10 | `workspace_subscribe` |
| 11 | `workspace_unsubscribe` |
| 12 | `pong` |
| 13 | `agent_id` |
| 14 | `agent_list` |

### WebServerFrame (gateway → you)

| # | Field |
|---|---|
| 1 | `request_id` |
| 2 | `hello` |
| 3 | `agent_response` (AgentEnvelope) |
| 4 | `local_error` |
| 5 | `ping` |
| 6 | `status` |
| 7 | `chat_subscribed` |
| 8 | `chat_accepted` |
| 9 | `chat_activities` |
| 10 | `chat_event` |
| 11 | `chat_command_update` |
| 12 | `chat_subscription_reset` |
| 13 | `chat_activity` |
| 14 | `ack` |
| 15 | `chat_cancelled` |
| 16 | `agent_id` |
| 17 | `agent_list` |
| 20 | `history_event` |
| 21 | `settings_event` |
| 22 | `terminal_event` |
| 23 | `sftp_event` |
| 24 | `chat_queue_event` |
| 25 | `tunnel_state` |
| 26 | `process_state` |
| 27 | `workspace_activity` |

**Responses echo `request_id`. Broadcast frames carry an empty `request_id`.** Use that to distinguish a reply from a broadcast.

## StatusEvent

| # | Field |
|---|---|
| 1 | `online` |
| 2 | `agent_ready` |
| 3 | `chat_runtime_ready` |
| 4 | `agent_id` |
| 5 | `agent_version` |
| 6 | `session_id` |
| 7 | `connected_since` |
| 8 | `last_heartbeat` |
| 9 | `runtime_state` |
| 10 | `runtime_last_heartbeat` |
| 11 | `runtime_worker_id` |
| 12 | `runtime_visible` |
| 13 | `runtime_active_run_count` |
| 14 | `name` |

## Pass-through: GatewayEnvelope

The browser sends `agent_request` carrying a `GatewayEnvelope`; the gateway validates it against a whitelist, namespaces the `request_id` per connection, forwards it to the target desktop, and returns that desktop's `AgentEnvelope` — near-verbatim.

```
GatewayEnvelope{ request_id = 1; timestamp = 2; <one arm> }
```

Arms not on the whitelist are **rejected**. Internal push arms, `ping`, and `chat_command` (which must go through gateway orchestration) are not pass-through.

### Whitelisted arms (48)

| Name | # | Name | # |
|---|---|---|---|
| `ChatFileOpen` | 94 | `HistoryBranch` | 92 |
| `ChatQueue` | 73 | `HistoryDelete` | 33 |
| `Checkpoint` | 98 | `HistoryGet` | 31 |
| `ClarifyTurn` | 101 | `HistoryList` | 30 |
| `CronManage` | 20 | `HistoryPin` | 35 |
| `CuaDriver` | 102 | `HistoryPrefix` | 34 |
| `FileMentionList` | 46 | `HistoryRename` | 32 |
| `FsCreateDir` | 58 | `HistorySetCwd` | 95 |
| `FsCreateProjectFolder` | 54 | `HistoryShareGet` | 36 |
| `FsDelete` | 60 | `WorkspaceRootGrants` | 96 |
| `FsList` | 56 | `HistoryShareSet` | 37 |
| `FsListDirs` | 49 | `HistoryWorkdirs` | 39 |
| `FsReadEditableText` | 62 | `InstalledAppsList` | 100 |
| `FsReadWorkspaceImage` | 63 | `ManagedProcessRequest` | 91 |
| `FsRename` | 59 | `MemoryManage` | 52 |
| `FsRoots` | 48 | `ProviderList` | 40 |
| `FsWriteText` | 57 | `ProviderModels` | 65 |
| `GitRequest` | 61 | `ProviderUsage` | 93 |
| `SettingsGet` | 41 | `SettingsResetSshKnownHost` | 72 |
| `SettingsUpdate` | 42 | `SftpRequest` | 64 |
| `SkillFilesList` | 43 | `SkillManage` | 53 |
| `SkillMetadataRead` | 44 | `SkillTextRead` | 45 |
| `TerminalRequest` | 55 | `TrajectoryFetch` | 99 |
| `TunnelMutation` | 81 | `UploadedImagePreview` | 51 |

`HistoryShareResolve` (#38) exists in the protocol but is **not** browser-whitelisted; public shares resolve via `GET /api/public/history-shares/{token}` instead.

The same map ships as `scripts/envelope_arms.json`.

### Server-side clamping

Even whitelisted arms are bounded on arrival: history list `limit` ≤ 200, `page` default 1, `page_size` default 80 / max 200, workspace root grants ≤ 64.

## Multi-agent addressing

- Multiple desktops coexist, keyed by `agent_id`.
- Targeted requests **must** carry a non-empty `agent_id`, or you receive `local_error: "agent_id is required"`.
- The official WebUI calls `agent_list` on connect, auto-selects an online agent, and persists the choice.
- Broadcast frames are tagged with their source `agent_id` — filter out other agents.
- A same-id reconnect replaces only that agent's old connection.

## Heartbeats

The server pings every **15s** on the browser link (agent link defaults to 30s). Idle eviction ≈ `3 × period + grace`. The server also sends an application-level `PingFrame`; reply with a `PongFrame` carrying a timestamp, or you will be evicted. Treat `3 × period` with no inbound traffic as a broken link.
