---
name: rterm-gateway
description: Remotely drive any RTerm instance over its WebSocket gateway — run AI agent tasks, open/control SSH/WinRM/Serial/local terminals, transfer files, manage settings & scheduled automation, fully headless. Use when an agent needs to call an RTerm gateway to execute commands on remote servers, run playbooks, orchestrate fleets, or schedule jobs from another program or agent (e.g. Pi, CI pipelines, other LLM agents).
---

# RTerm Gateway — Remote Control Skill

RTerm can run as a **headless service**. When its gateway is enabled, it opens a
**WebSocket JSON-RPC** endpoint. Any program or agent that can open a WebSocket can
drive the full RTerm feature set — no UI, no human.

Use this skill to:
- Run AI agent tasks on the gateway (`agent:startTask` / `agent:startTaskAsync`).
- Open and control terminals on **SSH / WinRM / Serial / local** targets and run commands.
- Transfer and edit files on any connected host.
- Manage settings, command policy, skills, memory, and scheduled automation.
- Orchestrate fleets and scheduled jobs (cron) completely headlessly.

---

## 1. How the gateway works (mental model)

```
Your agent / program ──WebSocket JSON-RPC──> RTerm Gateway (ws://host:17888)
                                                │
                       ┌────────────────────────┼─────────────────────────┐
                       │                        │                         │
                 AgentService            TerminalService            AutomationManager
                 (run AI tasks)          (SSH/WinRM/Serial/local)   (playbooks, cron, change MOP)
                       │                        │                         │
                 LLM + tools            run commands, files        scheduler, ledgers
```

- **Requests** are JSON-RPC: `{ "id": "1", "method": "<name>", "params": { ... } }`.
- **Responses** echo the `id` wrapped in a `gateway:response` envelope:
  - success → `{ "type": "gateway:response", "id": "1", "ok": true, "result": { ... } }`
  - error   → `{ "type": "gateway:response", "id": "1", "ok": false, "error": { "code", "message" } }`
- **Events** stream to you asynchronously as `{ "type": "gateway:event" | "gateway:raw" | "gateway:ui-update", "channel"?, "payload": ... }`.

Default endpoint: **`ws://<host>:17888`** (default port `17888`, configurable).

### Auth

- **Token auth** via `Authorization: Bearer <token>` header (or a token provided per deployment).
- **Localhost bypass:** connections from `127.0.0.1` / `::1` skip the token by default
  (`allowLocalhostWithoutToken: true`). If you are on the same machine as RTerm, you usually
  need no token.
- Optional **IP allow-list (CIDR)** may restrict which hosts can connect.

If a connection is rejected, you'll get a close frame with a reason — treat that as an
auth/IP problem, not a protocol problem.

---

## 2. The 30-second start

1. **Verify the gateway is up and reachable:**
   ```bash
   node scripts/rterm-gw.mjs --url ws://127.0.0.1:17888 ping
   # -> { "pong": true, "ts": ... }
   ```
2. **List terminals / sessions:**
   ```bash
   node scripts/rterm-gw.mjs terminal-list
   node scripts/rterm-gw.mjs session-list
   ```
3. **Run a command on a saved WinRM/SSH connection** (the headline use case):
   ```bash
   node scripts/rterm-gw.mjs exec-winrm \
     --name "AWS-Windows-Server-1" \
     --command "powershell -NoProfile -Command \"Update-MpSignature; (Get-MpComputerStatus).AntispywareSignatureVersion\""
   ```

The bundled helper `scripts/rterm-gw.mjs` wraps the whole protocol (connect, RPC, events,
waits) into subcommands. Use it directly or read it as a reference client.

---

## 3. Choosing the right method (decision guide)

| I want to… | Use |
|---|---|
| Have the **AI agent** figure out & run a multi-step task | `agent:startTask` (block) / `agent:startTaskAsync` (fire-and-forget) |
| **Run one command** on an SSH/WinRM/local/Serial host | `terminal:createTab` → `terminal:write` → `terminal:getBufferDelta` (PTY) **or** route via the agent for WinRM |
| **WinRM command/response** execution | Prefer the **agent path** (`agent:startTask`) — WinRM has no live stdin; the agent's `exec_command` uses the structured `executeCommand` path that returns output. |
| Read/write/transfer **files** on a host | `filesystem:*` |
| Manage **saved connections**, **settings**, **policy** | `settings:*`, `settings:addCommandPolicyRule`, `agentSettings:*` |
| Create/modify **scheduled cron jobs** | `settings:set` (automation section) — scheduler runs them headless |
| Orchestrate a **fleet** or a **playbook** | `agent:startTask` ("run the X playbook on group Y") |
| Watch **live progress** | subscribe to events (`gateway:event` / `gateway:raw`) |

> **Key gotcha — WinRM is command/response, not a PTY.** `terminal:write` to a WinRM tab is a
> no-op (returns `ok` but runs nothing). For WinRM, drive commands through the **agent**
> (`agent:startTask`), whose tools route through the structured `executeCommand` path and
> return real output. SSH/local PTY tabs work fine with `terminal:write` + `getBufferDelta`.

---

## 4. RPC method reference (72 methods)

Params are passed as a JSON object under `params`. `…` = see source for full shape.

### Gateway / session lifecycle
| Method | Params | Returns | Notes |
|---|---|---|---|
| `gateway:ping` | — | `{pong:true, ts}` | liveness |
| `gateway:isSameMachine` | — | `{sameMachine}` | true if client is co-located |
| `gateway:createSession` | — | `{sessionId}` | new agent/chat session |
| `session:list` | — | `{sessions:[…]}` | session summaries |
| `session:get` | `{sessionId}` | `{session}` | one session snapshot |

### Agent (AI task execution)
| Method | Params | Returns | Notes |
|---|---|---|---|
| `agent:startTask` | `{sessionId, userInput, options?}` | `{ok:true}` | **blocks** until the task completes; `userInput` = string or `{text, images?}` |
| `agent:startTaskAsync` | `{sessionId, userInput, options?}` | `{ok:true}` | fire-and-forget; watch events for progress |
| `agent:stopTask` | `{sessionId}` | `{ok:true}` | abort a running task |
| `agent:replyMessage` | `{messageId, payload}` | … | answer an agent prompt |
| `agent:replyCommandApproval` | `{approvalId, decision}` | … | `decision`: `"allow"` or `"deny"` |
| `agent:getUiMessages` | `{sessionId}` | `{messages:[…]}` | transcript for a session |
| `agent:getAllChatHistory` | — | `[…]` | all chat history |
| `agent:exportHistory` | `{sessionId, mode?}` | … | `mode`: `"simple"` or `"detailed"` |
| `agent:loadChatSession` | `{id}` | … | load a session into the agent |
| `agent:renameSession` | `{sessionId, title}` | … | rename |
| `agent:deleteChatSession` | `{sessionId}` | `{ok:true}` | delete one |
| `agent:deleteChatSessions` | `{sessionIds:[…]}` | … | delete many |
| `agent:branchFromMessage` | `{sessionId, messageId}` | … | branch a session at a message |
| `agent:rollbackToMessage` | `{sessionId, messageId}` | … | roll a session back |

### Terminals (SSH / WinRM / Serial / local)
| Method | Params | Returns | Notes |
|---|---|---|---|
| `terminal:list` | — | `{terminals:[…]}` | all tabs with `runtimeState` |
| `terminal:createTab` | `{config}` | `{id}` | config = a `TerminalConfig` (see §5) |
| `terminal:write` | `{terminalId, data}` | `{ok:true}` | write to PTY (SSH/local); **no-op for WinRM** |
| `terminal:writePaths` | `{terminalId, …}` | … | write file paths (drop) |
| `terminal:resize` | `{terminalId, cols, rows}` | … | resize PTY |
| `terminal:kill` | `{terminalId}` | … | close tab |
| `terminal:reconnect` | `{terminalId}` | … | reconnect an exited tab |
| `terminal:setSelection` | `{terminalId, selectionText}` | … | set selection text |
| `terminal:getBufferDelta` | `{terminalId, fromOffset}` | `{…}` | read accumulated output (PTY) |
| `terminal:generateCommandDraft` | `{terminalId, …}` | … | AI command draft |

### Filesystem (per terminal/host)
| Method | Params | Notes |
|---|---|---|
| `filesystem:list` | `{terminalId, dirPath?}` | list a directory |
| `filesystem:readTextFile` | `{terminalId, filePath}` | read a text file |
| `filesystem:readFileBase64` | `{terminalId, filePath}` | read binary as base64 |
| `filesystem:writeTextFile` | `{terminalId, filePath, content}` | write text |
| `filesystem:writeFileBase64` | `{terminalId, filePath, contentBase64}` | write binary |
| `filesystem:createDirectory` | `{terminalId, dirPath}` | mkdir |
| `filesystem:createFile` | `{terminalId, filePath}` | touch |
| `filesystem:deletePath` | `{terminalId, targetPath}` | delete |
| `filesystem:renamePath` | `{terminalId, oldPath, newPath}` | rename/move |
| `filesystem:transferEntries` | `{…}` | multi-entry transfer plan |
| `filesystem:startTransfer` | `{…}` | start an upload/download |
| `filesystem:getTransfer` | `{transferId}` | transfer status |
| `filesystem:listTransfers` | — | list transfers |
| `filesystem:cancelTransfer` | `{transferId}` | cancel |
| `filesystem:cancelTransferTask` | `{transferId}` | cancel a task |

### Settings, policy, skills, memory, models
| Method | Params | Notes |
|---|---|---|
| `settings:get` | — | full settings (incl. `connections`, `automation`) |
| `settings:set` | `{settings}` | patch settings (e.g. add scheduled task) |
| `settings:getCommandPolicyLists` | — | allow/ask/deny lists |
| `settings:addCommandPolicyRule` | `{list, rule}` | add rule to `allowlist`/`asklist`/`denylist` |
| `settings:deleteCommandPolicyRule` | `{list, rule}` | remove rule |
| `agentSettings:get` | — | agent settings |
| `agentSettings:saveCurrent` | `{…}` | save a profile slot |
| `agentSettings:apply` | `{…}` | apply a profile |
| `agentSettings:overwrite` | `{…}` | overwrite |
| `agentSettings:delete` | `{…}` | delete profile |
| `skills:getAll` / `skills:list` / `skills:getEnabled` | — | list skills |
| `skills:setEnabled` | `{name, enabled}` | toggle a skill |
| `skills:create` / `skills:delete` / `skills:reload` | `{…}` | manage skills |
| `memory:get` | — | global memory |
| `memory:setContent` | `{content}` | set memory |
| `models:getProfiles` | — | model profiles |
| `models:setActiveProfile` | `{profileId}` | switch model |
| `models:probe` | `{…}` | probe a model |
| `tools:getMcp` / `tools:reloadMcp` / `tools:setMcpEnabled` | `{…}` | MCP tools |
| `tools:getBuiltIn` / `tools:setBuiltInEnabled` | `{name, enabled}` | built-in tools |
| `system:saveImageAttachment` | `{…}` | attach an image |

### Observability / SRE (v2.0.0–v2.3.1) — driven via the agent
The observability modules are wired into the backend and driven through `agent:startTask` (the agent reads/writes them via its built-in tools). Key capabilities to ask for:

| Area | Example `userInput` |
|---|---|
| **Unified dashboard** | "Build the dashboard:state — fleet health, SLO, uptime, incidents, APM, DEM, capacity" |
| **SRE metrics** | "Report golden signals + capacity forecast for all hosts; days-to-disk-full" |
| **Uptime watchdog** | "Add an uptime watchdog for web-01 (tcp 443) and report its state" |
| **SLO** | "Create an SLO api-uptime 99.9% over 30d and evaluate burn rate" |
| **Incidents** | "List open incidents and generate the postmortem for the latest one" |
| **APM (OTLP)** | "Ingest these OTLP spans and report the slowest traces + bottleneck services" |
| **DEM (RUM)** | "Report p75 LCP/INP and error rate per page; which pages are poor on Core Web Vitals?" |
| **k8s/cloud** | "Collect cluster health (pods, restarts, node readiness, cpu/mem % of limit)" |
| **ETW (Windows)** | "Run a network ETW trace on AWS-Windows-Server-1 for 60s and summarize connections" |
| **Predictive** | "Detect anomalies in cpu/disk for all hosts and any forecast breaches within 7 days" |
| **Behavioral** | "Flag any run-spikes, token-blowouts, error-spikes, or unusual models vs the baseline" |
| **Evals** | "Run the embedded eval harness on the golden set and report accuracy/tool/safety/replay %" |
| **Notify (Slack/Teams/SMTP/Telegram)** | "Wire a Slack alert channel (webhook …) and fire a test alert" |

> The observability ledgers feed the unified dashboard and are driven by the agent's
> built-in tools — no separate RPC methods are needed beyond `agent:startTask` /
> `agent:getUiMessages` for these areas.

---

## 5. TerminalConfig shapes (for `terminal:createTab`)

```jsonc
// SSH
{ "type": "ssh", "id": "t1", "title": "web-01", "cols": 120, "rows": 32,
  "host": "10.0.0.5", "port": 22, "username": "deploy",
  "password": "…",                       // or "privateKey" / "privateKeyPath" / "agent"
  "algorithmsPreset": "modern|legacy|cisco", "termType": "xterm-256color|vt100" }

// WinRM (command/response — drive commands via the AGENT, not terminal:write)
{ "type": "winrm", "id": "w1", "title": "win-01", "cols": 140, "rows": 40,
  "host": "44.197.31.152", "port": 5985, "username": "Administrator",
  "password": "…", "transport": "http", "auth": "basic", "domain": "" }

// Serial
{ "type": "serial", "id": "s1", "title": "switch-console", "cols": 120, "rows": 32,
  "path": "/dev/ttyUSB0", "baudRate": 9600, "dataBits": 8, "parity": "none",
  "stopBits": 1, "flowControl": "none" }

// Local
{ "type": "local", "id": "l1", "title": "local", "cols": 120, "rows": 32,
  "cwd": "/work", "shell": "/bin/zsh" }
```

Saved connections already known to RTerm can be opened by asking the agent to
"open the saved connection named X" (see §6), or by reading `settings:get` →
`connections.{ssh,winrm,serial}` and passing the same fields to `terminal:createTab`.

---

## 6. Events (watching progress live)

You do **not** subscribe explicitly — events stream to every connected client.

| Wire type | Meaning | Payload |
|---|---|---|
| `gateway:event` | A structured `GatewayEvent` | `{id, timestamp, type, sessionId?, payload}` where `type` ∈ `agent:event` \| `session:update` \| `ui:action` \| `system:notification` |
| `gateway:raw` | Raw channel data | `{channel, payload}` — e.g. `channel:"terminal:data"` carries `{terminalId, data, offset}` |
| `gateway:ui-update` | UI action broadcast | action object |

For `agent:startTask`, watch for `agent:event` payloads (tool calls, streamed model text,
completion). The bundled client prints events to stderr so you can observe them.

---

## 7. Command policy & autonomy

Every command the agent runs is evaluated against the **command policy**:

- **`smart`** — run autonomously (unless explicitly denylisted). Headless-friendly.
- **`standard`** — **asks** for approval on unrecognized commands. A remote client must
  answer with `agent:replyCommandApproval` (`{approvalId, decision:"allow"|"deny"}`).
- **`safe`** — denies unrecognized commands.

Check the mode with `settings:get` → `commandPolicyMode`. For unattended operation, either
use `smart` mode or pre-allowlist the commands your workflow needs
(`settings:addCommandPolicyRule {list:"allowlist", rule:"Update-MpSignature*"}`).

---

## 8. Bundled helper: `scripts/rterm-gw.mjs`

A dependency-light reference client (Node ≥18, uses `ws`). Subcommands:

```bash
# liveness + discovery
node scripts/rterm-gw.mjs ping
node scripts/rterm-gw.mjs terminal-list
node scripts/rterm-gw.mjs session-list
node scripts/rterm-gw.mjs settings-get

# generic RPC (escape hatch — any method)
node scripts/rterm-gw.mjs rpc --method models:getProfiles

# open a saved WinRM/SSH connection and run one command
node scripts/rterm-gw.mjs exec-winrm --name "AWS-Windows-Server-1" --command "<powershell>"

# run an AI agent task (blocking or async)
node scripts/rterm-gw.mjs agent-task --text "Update AV signatures on AWS-Windows-Server-1 and report the version"
node scripts/rterm-gw.mjs agent-task --async --text "Run the Friday cleanup playbook on group prod-web"

# read a file on a connected host
node scripts/rterm-gw.mjs fs-read --terminalId <id> --path C:\Temp\log.txt
```

Flags: `--url` (default `ws://127.0.0.1:17888`), `--token` (or `RTERM_GW_TOKEN`), `--timeout`.

See `examples/` for ready-made programs.

---

## 8a. Shell one-liners with `websocat` (no Node, no Python)

You don't need Node or Python — the gateway is plain WebSocket + JSON, so
[`websocat`](https://github.com/vi/websocat) drives it from any shell. A prebuilt
binary is in **DrOlu/agent-tools**
([`websocat.exe` v1.14.1](https://raw.githubusercontent.com/DrOlu/agent-tools/main/websocat.exe)),
or install from your package manager (`brew install websocat`, `cargo install websocat`).

**One-shot RPC** (reconnects each call; good for quick reads — use `-n1` = close after one reply):

```bash
# ping
echo '{"id":"1","method":"gateway:ping"}' | websocat -n1 ws://127.0.0.1:17888
# -> {"type":"gateway:response","id":"1","ok":true,"result":{"pong":true,"ts":...}}

# list terminals
echo '{"id":"2","method":"terminal:list"}' | websocat -n1 ws://127.0.0.1:17888
```

**With `jq` for scripting:**

```bash
echo '{"id":"2","method":"terminal:list"}' \
  | websocat -n1 ws://127.0.0.1:17888 \
  | jq -r '.result.terminals[] | "\(.title) [\(.type)] \(.runtimeState)"'
```

**Persistent session** (required for `agent:startTask*` and for streaming `gateway:event`s):

```bash
websocat ws://127.0.0.1:17888
# then paste JSON-RPC lines; responses + live events arrive on the same socket:
{"id":"1","method":"gateway:createSession"}
{"id":"2","method":"agent:startTaskAsync","params":{"sessionId":"<sid>","userInput":"Update AV signatures on AWS-Windows-Server-1 and report the version"}}
```

**With a token** (when not connecting from localhost):

```bash
websocat -H="Authorization: Bearer <token>" ws://rterm-host:17888
```

> **Note:** `websocat` is line-oriented — perfect for request→response RPC and `jq`
> pipelines. For long agent tasks you must keep the socket open and read the streaming
> `gateway:event` messages yourself (or use the Node/Python client which manages that loop).

---

## 8b. Python client (`websockets`, no Node)

Any Python ≥3.9 agent can drive the gateway with the `websockets` library
(`pip install websockets`). This is a minimal, complete client covering connect,
RPC, an agent task, and event streaming:

```python
import asyncio, json, sys
import websockets  # pip install websockets

URL = "ws://127.0.0.1:17888"   # localhost skips token auth
TOKEN = None                   # or "..."  -> Authorization: Bearer <token>

class RTermGW:
    def __init__(self):
        self._seq = 0
        self._pending = {}   # id -> asyncio.Future
        self.events = []     # async events (gateway:event / gateway:raw / ...)

    async def connect(self):
        # `websockets` renamed extra_headers -> additional_headers in v14/v15
        headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else None
        try:
            self.ws = await websockets.connect(URL, additional_headers=headers)
        except TypeError:
            self.ws = await websockets.connect(URL, extra_headers=headers)
        self._reader = asyncio.create_task(self._read_loop())

    async def _read_loop(self):
        async for raw in self.ws:
            msg = json.loads(raw)
            if msg.get("type") == "gateway:response" or ("id" in msg and ("result" in msg or "error" in msg or "ok" in msg)):
                fut = self._pending.pop(msg.get("id"), None)
                if fut and not fut.done():
                    if msg.get("ok") is False or "error" in msg:
                        err = msg.get("error") or {}
                        fut.set_exception(RuntimeError(f"{err.get('code')}: {err.get('message')}"))
                    else:
                        fut.set_result(msg.get("result", msg))
            else:
                self.events.append(msg)

    async def rpc(self, method, params=None, timeout=60):
        self._seq += 1
        rid = f"c{self._seq}"
        fut = asyncio.get_event_loop().create_future()
        self._pending[rid] = fut
        await self.ws.send(json.dumps({"id": rid, "method": method, "params": params or {}}))
        return await asyncio.wait_for(fut, timeout)

async def main():
    gw = RTermGW()
    await gw.connect()
    print("ping:", await gw.rpc("gateway:ping"))

    # Run an AI agent task (blocking) and print the transcript tail
    sess = await gw.rpc("gateway:createSession")
    sid = sess["sessionId"]
    await gw.rpc("agent:startTask", {
        "sessionId": sid,
        "userInput": "Update AV signatures on the saved WinRM connection "
                     "AWS-Windows-Server-1 and report AntispywareSignatureVersion."
    }, timeout=180)
    ui = await gw.rpc("agent:getUiMessages", {"sessionId": sid})
    for m in (ui.get("messages") or [])[-3:]:
        print(f"[{m.get('role','?')}] {(m.get('text') or m.get('content') or '')[:400]}")

asyncio.run(main())
```

For **fire-and-forget** tasks, use `agent:startTaskAsync` and then read `gw.events`
(or keep the connection open and consume the `gateway:event` stream in `_read_loop`).

---

## 9. Use cases

1. **CI/CD post-deploy checks.** A pipeline calls `agent:startTaskAsync` → "run the
   post-deploy health playbook on web nodes and report unhealthy ones" → gate the deploy
   on the returned transcript.
2. **Remote patch/signature management.** On a schedule, a controller agent runs
   `Update-MpSignature` (or `yum update`/`apt`) across a fleet of WinRM/SSH servers via
   `agent:startTask` per host, then collects versions.
3. **Scheduled ops with zero humans.** Create cron scheduled tasks via `settings:set`; the
   RTerm scheduler executes them on the targets at the right time. A remote agent adds or
   adjusts schedules on the fly.
4. **Approval-gated change (MOP).** `agent:startTask` → "plan the X change" → a human
   approves in RTerm → `agent:startTask` → "run change chg-…". Rollback is automatic.
5. **Fleet inventory.** `agent:startTask` → "collect facts on all open tabs" → parse the
   structured inventory for a CMDB.
6. **File distribution.** `filesystem:writeFileBase64` / `filesystem:startTransfer` to push
   a config or artifact to many hosts.
7. **Another AI agent as a sub-agent.** Your orchestrator LLM treats RTerm as a tool:
   dispatch a complex ops task and read the result — RTerm's agent does the multi-step work.

---

## 10. Error handling & troubleshooting

- **Close frame on connect** → auth token missing/invalid, or your IP is not in the
  allow-list. Fix credentials or connect from an allowed host (localhost bypasses token).
- **`METHOD_NOT_FOUND`** → that RPC isn't implemented by this gateway build; use a supported path.
- **`BAD_JSON` / `BAD_REQUEST`** → malformed frame or wrong param type; check the param table.
- **WinRM tab "ready" but no output** → you used `terminal:write`; switch to the agent path.
- **Task stalls awaiting approval** → policy is `standard`; answer `agent:replyCommandApproval`
  or switch to `smart`.
- **Timeouts** → long tasks: use `agent:startTaskAsync` + events instead of blocking `startTask`.

---

## Supporting files

- `scripts/rterm-gw.mjs` — reference CLI client (all subcommands).
- `examples/python-client.py` — Python (`websockets`) client; no Node required.
- `examples/ci-post-deploy.mjs` — CI/CD post-deploy gate.
- `examples/fleet-av-update.mjs` — update AV signatures across a WinRM fleet.
- `examples/scheduled-cleanup.mjs` — create a cron scheduled task remotely.
- `examples/mop-change.mjs` — approval-gated change (plan → approve → run).
