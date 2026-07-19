---
name: rterm-backend
description: Install, configure, run, administer, and manage the standalone RTerm backend (rterm-backend / gybackend) completely headlessly on macOS, Linux, and Windows. Use when an agent needs to set up RTerm-as-a-service — install the daemon, configure its data dir and gateway, run it as a service, manage saved connections/automation/schedules, and drive it over its WebSocket JSON-RPC gateway. Pair with the rterm-gateway skill for the RPC method reference and client examples.
---

# RTerm Backend — Headless Install & Operations Skill

The **RTerm backend** (`rterm-backend` on npm, CLI `gybackend`) is the full RTerm
runtime as a standalone Node daemon — **no desktop UI**. It boots the AI agent,
SSH/WinRM/Serial/local terminals, fleet orchestration, scheduled automation, and
change management, and serves them over a **WebSocket JSON-RPC gateway**
(default `ws://<host>:17888`).

Use this skill to install, configure, run, and administer it **completely
headlessly** on **macOS, Linux, or Windows** — then drive it with the
[`rterm-gateway`](../rterm-gateway/SKILL.md) skill for the actual RPC calls.

---

## 1. The 60-second path (any OS)

```bash
# 1. install (Node >= 18 required)
npm install -g rterm-backend

# 2. run it
gybackend
# -> [gybackend] WebSocket RPC endpoint: ws://0.0.0.0:17888

# 3. verify (in another shell)
echo '{"id":"1","method":"gateway:ping"}' | websocat -n1 ws://127.0.0.1:17888
# -> {"type":"gateway:response","id":"1","ok":true,"result":{"pong":true,...}}
```

The bundled **`scripts/rterm-backend.mjs`** CLI wraps every lifecycle step
(install, start, stop, status, logs, config, service) into one cross-platform
command. Run any of these with `node scripts/rterm-backend.mjs <cmd>`.

---

## 2. What runs inside (mental model)

```
┌──────────────┐  WebSocket JSON-RPC   ┌────────────────────────────────┐
│ your agent / │ ◄──────────────────► │ gybackend (rterm-backend)      │
│ program / CI │                       │  AgentService  (LLM + tools)   │
└──────────────┘                       │  TerminalService SSH/WinRM/    │
                                       │    Serial/local PTY          │
                                       │  AutomationManager + cron    │
                                       │  ChangeManagement (MOP)      │
                                       │  Ledgers (SQLite)            │
                                       └────────────────────────────────┘
                  Data dir: settings.json + *.sqlite + session-logs/
```

- **Requests:** `{ "id": "1", "method": "<name>", "params": {...} }`
- **Responses:** `{ "type": "gateway:response", "id": "1", "ok": true|false, "result"|"error" }`
- **Events (progress):** `{ "type": "gateway:event" | "gateway:raw" | "gateway:ui-update", ... }`

---

## 3. Install

### 3.1 Requirements

| Need | Notes |
|---|---|
| **Node.js ≥ 18** | Native deps (`better-sqlite3`, `node-pty`, `ssh2` crypto, tree-sitter wasm) ship prebuilt binaries for macOS x64/arm64, Linux x64/arm64, Windows x64. Unusual platforms compile from source → install a C/C++ toolchain (Xcode CLT / build-essential / MSVC Build Tools). |
| npm registry access | or your internal mirror (`npm config set registry <mirror>`). |
| Optional | `websocat` (ad-hoc calls), an LLM provider key for the agent. |

### 3.2 Install from npm (recommended)

```bash
npm install -g rterm-backend
gybackend --version 2>/dev/null || which gybackend || where gybackend
```

Or without a global install: `npx -y rterm-backend`.

### 3.3 Install from a repo checkout (development)

```bash
git clone https://github.com/DrOlu/RTerm.git && cd RTerm
npm install
npm run build:backend-standalone      # dist-standalone/gybackend.js
npm run start:backend                 # or: node apps/gybackend/dist-standalone/gybackend.js
```

### 3.4 OS-specific service install (run as a daemon/service)

Use the bundled helper, or the unit files in `service/`:

```bash
node scripts/rterm-backend.mjs install-service     # prints the right unit + enable cmd for this OS
```

- **Linux (systemd):** `service/rterm-backend.service` → `/etc/systemd/system/`, then `systemctl enable --now rterm-backend`.
- **macOS (launchd):** `service/ng.hyperspace.rterm-backend.plist` → `~/Library/LaunchAgents/`, then `launchctl load <plist>`.
- **Windows (Task Scheduler):** `service/install-windows-service.ps1` → registers an at-logon task (`schtasks`). Native deps install via `npm i -g` first.

---

## 4. Configure

### 4.1 Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `GYBACKEND_WS_ENABLE` | `1` | enable the gateway (0/false disables) |
| `GYBACKEND_WS_HOST` | `0.0.0.0` | bind host (`127.0.0.1` = local-only) |
| `GYBACKEND_WS_PORT` | `17888` | gateway port |
| `GYBACKEND_DATA_DIR` | `./.gybackend-data` | settings, ledgers, skills, session logs |
| `GYBACKEND_BOOTSTRAP_LOCAL_TERMINAL` | `true` | open a local shell tab on boot |
| `GYBACKEND_TERMINAL_ID` | `local-main` | bootstrap terminal id |
| `GYBACKEND_TERMINAL_TITLE` | `Local` | bootstrap terminal title |
| `GYBACKEND_TERMINAL_CWD` | — | bootstrap terminal cwd |
| `GYBACKEND_TERMINAL_SHELL` | — | bootstrap terminal shell |

### 4.2 The data directory

| Path | Contents |
|---|---|
| `settings.json` | connections (ssh/winrm/serial), automation (groups/scripts/schedules/templates/playbooks), model profiles, command policy, gateway policy |
| `gyshell-history.sqlite` | chat + UI history |
| `gyshell-agent-runs.sqlite` | agent run ledger (audit + token cost) |
| `gyshell-changes.sqlite` | change ledger (MOP records + step events) |
| `session-logs/` | recorded terminal sessions (plain files) |
| `skills/` | agent skills |
| `access-tokens.json` | gateway access tokens |

### 4.3 Reuse desktop-app settings

```bash
# macOS
GYBACKEND_DATA_DIR="$HOME/Library/Application Support/rterm" gybackend
# Linux
GYBACKEND_DATA_DIR="$HOME/.config/rterm" gybackend
# Windows (cmd)
set GYBACKEND_DATA_DIR=%APPDATA%\rterm && gybackend
:: Windows (PowerShell)
$env:GYBACKEND_DATA_DIR="$env:APPDATA\rterm"; gybackend
```

> **Warn:** two instances sharing one data dir should not run the same scheduled
> tasks at once (duplicate execution). For a dedicated automation server, give it
> its own data dir and recreate only what it needs.

### 4.4 Command policy (autonomy)

| Mode | Unrecognized commands | Use for |
|---|---|---|
| `smart` | run (unless denylisted) | unattended / headless |
| `standard` | ask for approval | interactive / supervised |
| `safe` | deny | locked-down |

Pre-allowlist what a headless job needs, then run `smart`:

```bash
settings:addCommandPolicyRule {list:"allowlist", rule:"Update-MpSignature*"}
settings:addCommandPolicyRule {list:"allowlist", rule:"systemctl *"}
```

### 4.5 Securing the gateway

- **Local-only:** `GYBACKEND_WS_HOST=127.0.0.1` when callers are on the same host.
- **Token:** non-localhost clients need `Authorization: Bearer <token>` (manage in `access-tokens.json`).
- **CIDR allow-list:** `settings → gateway.allowedCidrs`.
- **Localhost bypass:** `127.0.0.1`/`::1` skip the token by default.

---

## 5. Run & administer

The bundled **`scripts/rterm-backend.mjs`** handles the lifecycle cross-platform
(uses only Node built-ins — no dependencies):

```bash
node scripts/rterm-backend.mjs doctor          # check Node, npm pkg, data dir, port
node scripts/rterm-backend.mjs install         # npm i -g rterm-backend
node scripts/rterm-backend.mjs start [--port N] [--host H] [--data DIR] [--daemon]
node scripts/rterm-backend.mjs stop
node scripts/rterm-backend.mjs restart
node scripts/rterm-backend.mjs status
node scripts/rterm-backend.mjs logs [--lines N]
node scripts/rterm-backend.mjs ping [--url ws://...]
node scripts/rterm-backend.mjs config-show     # effective env + data dir
node scripts/rterm-backend.mjs install-service # print service unit + enable cmd for this OS
node scripts/rterm-backend.mjs uninstall       # stop + npm uninstall -g
```

### Boot output (healthy)

```
[WebSocketGatewayAdapter] Listening on ws://0.0.0.0:17888
[gybackend] Started.
[gybackend] WebSocket RPC endpoint: ws://0.0.0.0:17888
[gybackend] Data directory: /var/lib/rterm-backend
```

### Foreground vs background

- **Foreground:** `gybackend` (Ctrl+C to stop) — good for first-run debugging.
- **Background/service:** systemd / launchd / Task Scheduler, or `... start --daemon` (uses `nohup`/`Start-Process` and writes a pidfile + log).

---

## 6. Manage connections, automation & schedules

Once running, manage it over RPC (see the `rterm-gateway` skill). Highlights:

- **Saved connections** — `settings:get` / `settings:set` → `connections.{ssh,winrm,serial}`; or ask the agent (`agent:startTask`) to "create an SSH connection X".
- **Automation** — groups, scripts, **scheduled tasks** (5-field cron), config templates, playbooks (validation + automatic rollback).
- **Scheduler** — runs inside the daemon on a per-minute tick; create/edit tasks via `settings:set` (automation.scheduledTasks).
- **Change (MOP)** — plan → approve → run → status, with a durable change ledger.

Create a cron task headlessly:

```jsonc
// settings:set -> automation.scheduledTasks +=
{
  "id": "friday-cleanup",
  "name": "Friday Night Cleanup",
  "cron": "0 0 * * 5",
  "enabled": true,
  "groupId": "cleanup-targets",
  "command": "find /var/app/cache -type f -mtime +30 -delete; journalctl --vacuum-time=7d"
}
```

---

## 7. Use cases

1. **CI/CD gate** — after deploy, `agent:startTask` → "health-check the fleet and report unhealthy nodes" → fail the pipeline on DEGRADED.
2. **Scheduled patch/AV** — cron task runs `Update-MpSignature` across a Windows fleet weekly; versions recorded to the run ledger.
3. **Multi-vendor change** — Jinja-render a Cisco BGP config, apply via `algorithmsPreset=cisco` + `vt100`, then update an AWS SG — with validation + rollback.
4. **Sub-agent** — an orchestrator LLM delegates ops tasks to RTerm's agent and reads transcripts.
5. **Audit** — run ledger + change ledger + session logs = complete command-and-output trail.

See `examples/` for runnable programs.

---

## 8. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| close on connect | token missing/invalid or IP not in CIDR allow-list (localhost bypasses token) |
| `METHOD_NOT_FOUND` | RPC not in this build; use a supported method |
| `BAD_JSON`/`BAD_REQUEST` | malformed frame or wrong param type |
| WinRM "ready" but no output | you used `terminal:write` on WinRM (a no-op) — drive via the agent |
| task stalls awaiting approval | policy is `standard` — answer `agent:replyCommandApproval`, allowlist, or use `smart` |
| blocking `startTask` times out | long task — use `agent:startTaskAsync` + watch events |
| SSH "All configured authentication methods failed" | supply a credential (password **or** privateKey) — authMethod is inferred |
| native module load error | no prebuilt binary for your platform — install a C/C++ toolchain and reinstall |
| port already in use | another gybackend/RTerm app holds it — `... stop` or use a different `GYBACKEND_WS_PORT` |

**Artifacts to collect:** the run-ledger entry (status+error), the session log for
the terminal, the gateway boot log, and a minimal RPC repro (a websocat one-liner).

---

## Supporting files

- `scripts/rterm-backend.mjs` — cross-platform lifecycle CLI (install/start/stop/restart/status/logs/ping/config-show/install-service/uninstall/doctor). No dependencies.
- `service/rterm-backend.service` — systemd unit (Linux).
- `service/ng.hyperspace.rterm-backend.plist` — launchd plist (macOS).
- `service/install-windows-service.ps1` — Task Scheduler registration (Windows).
- `examples/fleet-health-gate.mjs` — CI/CD post-deploy gate.
- `examples/schedule-weekly-av.mjs` — create a weekly AV-update cron task headlessly.
- `examples/mop-approved-change.mjs` — approval-gated change (plan → approve → run).
