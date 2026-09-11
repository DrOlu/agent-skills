# Remote operations (pass-through)

Every call here is a `GatewayEnvelope` arm sent over `/ws/v2` with a **non-empty `agent_id`**, answered by the desktop's `AgentEnvelope`.

```bash
python3 scripts/lag_ws.py req <ArmName> --json '{"<field>": <value>}'
```

`--json` keys are **protobuf field numbers**, not names. Numbers below come from `proto/v2/gateway.proto`. Integer values are encoded as varints, booleans as bools, everything else as strings.

---

## Filesystem

### Discovery

| Arm | # | Notes |
|---|---|---|
| `FsRoots` | 48 | Available roots |
| `FsListDirs` | 49 | List directories |
| `FsList` | 56 | List a path (recursive/depth/limit supported) |
| `FileMentionList` | 46 | @-mention candidates |

### Read-only content

| Arm | # | Purpose |
|---|---|---|
| `FsReadEditableText` | 62 | Read a file for editing |
| `FsReadWorkspaceImage` | 63 | Read an image inside the workspace |
| `UploadedImagePreview` | 51 | Preview an uploaded image |

### Mutation — **confirm before calling**

| Arm | # | Purpose |
|---|---|---|
| `FsWriteText` | 57 | Write a text file |
| `FsCreateDir` | 58 | Create a directory |
| `FsCreateProjectFolder` | 54 | Create a project folder |
| `FsRename` | 59 | Rename / move |
| `FsDelete` | 60 | **Delete — irreversible** |

---

## Git (`GitRequest` #61)

A single arm multiplexing status, diff, log, stage, commit, branch, and checkout.

Workspace activity is **push-based**: the desktop watches each workdir (250 ms debounce, `.git` internal noise filtered, changed paths capped at 64 plus a `truncated` flag) and emits `WorkspaceActivityEvent` (#90).

**Semantics:** a best-effort *invalidation* signal — events are **not** guaranteed. On (re)subscribe, channel rebuild, or revision rollback, **mark dirty and refetch**. `revision` is a per-workdir monotonic counter local to the agent process. Fetch actual data with `FsList` / `GitRequest` after invalidation.

Subscribe with `workspace_subscribe` (frame field 10), unsubscribe with field 11.

---

## Terminal (`TerminalRequest` #55)

The main link carries only the **control plane**: list / create / close / rename sessions, SSH prompts, and SSH tab state.

High-frequency I/O uses a **separate data plane** so typing never queues behind chat:

- Endpoint `/ws/v2/terminal`, carrying `TerminalStreamFrame`.
- `kind` ∈ `attach | input | resize | detach | output | snapshot | error`
- Fields: `stream_id`, `session_id`, `project_path_key`, `seq`, `start_offset`, `end_offset`, `cols`, `rows`, `max_bytes`, `truncated`, `error`, `data`

Rules:

- `attach` returns a `snapshot` frame with tail bytes; `start_offset` / `end_offset` let clients deduplicate.
- `input` is fire-and-forget bytes.
- `resize` sends only the latest `cols`/`rows`.
- `output` is delivered only to attached connections.
- Terminal metadata (`created`, `exit`, `closed`, `renamed`, SSH prompts) is broadcast on the main link as `terminal_event` (frame 22) — but **output bytes never enter the main link**. Slow clients block only their own terminal stream.

---

## SFTP (`SftpRequest` #64)

Listing, transfer, and upload through the desktop's SFTP client. Events arrive as `sftp_event` (frame 23).

---

## Tunnels (`TunnelMutation` #81)

Expose a local service publicly through the gateway. State arrives as `tunnel_state` (frame 25) or `TunnelDesiredState`; results as `TunnelMutationResult`; probing via `TunnelProbeReport`. Tunnel traffic is proxied under `/t/` paths — **reverse proxies must allow WebSocket upgrades on those paths too.**

Tunnel frames validate `stream_id` ownership and **reject cross-agent forgery**.

---

## Managed processes (`ManagedProcessRequest` #91)

Start, stop, and inspect long-running processes on the desktop. Snapshots arrive as `process_state` (frame 26).

---

## Memory (`MemoryManage` #52)

Read and write the desktop's persistent memory (Markdown + SQLite FTS). **Mutations are durable — confirm intent first.**

---

## Cron (`CronManage` #20)

List, create, update, and delete scheduled tasks (`bash`, `http`, `prompt`). These are the tasks shown in the desktop's Settings → Cron. **Always confirm before deleting**, and never silently rewrite a schedule that was not requested.

---

## Skills

| Arm | # | Purpose |
|---|---|---|
| `SkillFilesList` | 43 | List installed skill files |
| `SkillMetadataRead` | 44 | Read name/description metadata |
| `SkillTextRead` | 45 | Read skill text |
| `SkillManage` | 53 | Install / create / package / delete |

`SkillManage` is mutating — treat it like a filesystem write and confirm intent first.

---

## Settings

| Arm | # | Purpose |
|---|---|---|
| `SettingsGet` | 41 | Read the settings snapshot |
| `SettingsUpdate` | 42 | Update settings |
| `SettingsResetSshKnownHost` | 72 | Clear stored SSH host keys |
| `ProviderList` | 40 | Configured providers |
| `ProviderModels` | 65 | Available models |
| `ProviderUsage` | 93 | Usage accounting |

**Provider secrets never travel in the normal settings snapshot.** The WebUI sees only redacted provider data plus an `apiKeyConfigured` flag; secrets use a dedicated one-way update channel. Do not expect to read an API key back — and never attempt to exfiltrate one.

---

## History

| Arm | # | Purpose |
|---|---|---|
| `HistoryList` | 30 | Paged conversation summaries |
| `HistoryGet` | 31 | Conversation detail (`max_messages` returns a tail window) |
| `HistoryRename` | 32 | Rename |
| `HistoryPin` | 35 | Pin / unpin |
| `HistoryDelete` | 33 | **Delete a conversation** |
| `HistoryPrefix` | 34 | Prefix search |
| `HistoryBranch` | 92 | Branch a conversation |
| `HistorySetCwd` | 95 | Set the working directory |
| `HistoryWorkdirs` | 39 | List workdirs |
| `HistoryShareGet` | 36 | Read share settings |
| `HistoryShareSet` | 37 | Set share token / redaction |

```bash
python3 scripts/lag_ws.py req HistoryList --json '{"1": 1, "2": 20}'
```

The **desktop is the source of truth** for history; the gateway only forwards requests and broadcasts `history_sync` (AgentEnvelope #34) events.

---

## Other arms

| Arm | # | Purpose |
|---|---|---|
| `InstalledAppsList` | 100 | Installed applications (for @-mentions) |
| `CuaDriver` | 102 | Browser / computer-use driver control |
| `WorkspaceRootGrants` | 96 | Workspace root grants (≤ 64) |

---

## Reading a response

The desktop's answer arrives as `agent_response` (WebServerFrame field 3) containing an `AgentEnvelope`. Its arms mirror the request (e.g. `history_list_resp` = #30), plus:

| # | Field |
|---|---|
| 70 | `chat_control` |
| 71 | `runtime_status` |
| 99 | `error` (ErrorResponse) |

A response with a large byte count but no readable content usually means the payload is protobuf beyond the helper's printer — dump raw bytes and decode with the field table in `protocol-v2.md`.
