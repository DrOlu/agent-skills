---
name: liveagent-gateway
description: Drive a LiveAgent instance remotely through its gateway from any agent, shell, or script. Covers the HTTP API, the v2 WebSocket+Protobuf protocol, chat submission and streaming, the multi-agent directory, per-agent credentials, and whitelisted pass-through for filesystem, git, terminal, SFTP, tunnels, memory, cron, skills, settings, history, uploads, and public shares. Use when controlling, querying, automating, scripting, or troubleshooting LiveAgent over its gateway, or when diagnosing gateway connectivity and authentication.
---

# LiveAgent Gateway

Drive a LiveAgent instance remotely over its gateway — from any agent, shell, or program.

**The gateway is a relay, not an execution environment.** It never runs shell commands, never touches a filesystem, and never stores credentials. It authenticates the caller, applies a whitelist, forwards the request to a desktop *agent*, and relays the answer back. Every privileged action happens on the desktop machine.

## 1. Required parameters

Collect these three before anything else. If the caller did not supply them, ask rather than guess.

| Parameter | Env var | Meaning | How to obtain |
|---|---|---|---|
| Gateway URL | `LAG_GW` | Base URL, with scheme | Deployment output, e.g. `http://localhost:3000`, `https://gw.example.com` |
| Token | `LAG_TOKEN` | Gateway token **or** `agt_…` per-agent token | `LIVEAGENT_GATEWAY_TOKEN` at deploy time, or issued via the admin API |
| Agent ID | `LAG_AGENT` | Which desktop to target | `scripts/lag.sh agents`, or desktop Settings → Remote → Agent ID |

Port conventions: direct container access uses the mapped host port (commonly `3000`); **behind a reverse proxy use the HTTPS URL and port `443`**.

If `LAG_AGENT` is unknown, run the `agents` command first — every targeted request needs a non-empty agent id.

## 2. Which transport to use

Decide by what the task needs. Most failures come from choosing the wrong one.

| Need | Transport | Reference |
|---|---|---|
| Health, agent status, credential administration, file upload, public share | **HTTP** (`curl` / PowerShell) | `references/http-api.md` |
| Chat, live events, agent switching | **WebSocket v2** | `references/chat.md` |
| Filesystem, git, terminal, SFTP, tunnels, memory, cron, skills, settings, history | **WebSocket v2 pass-through** | `references/remote-operations.md` |

HTTP cannot send chat or reach a desktop. WebSocket cannot administer credentials. Use both.

## 3. Quick start

```bash
export LAG_GW="http://localhost:3000"
export LAG_TOKEN="<gateway token>"
export LAG_AGENT="agent-<uuid>"

# HTTP: health, status, directory
bash scripts/lag.sh health
bash scripts/lag.sh status
bash scripts/lag.sh agents

# WebSocket: handshake, chat, pass-through
python3 scripts/lag_ws.py probe
python3 scripts/lag_ws.py send "list the files in the workspace"
python3 scripts/lag_ws.py req HistoryList --json '{"1":1,"2":20}'
```

```powershell
$env:LAG_GW="http://localhost:3000"; $env:LAG_TOKEN="<gateway token>"
.\scripts\lag.ps1 health
.\scripts\lag.ps1 agents
.\scripts\lag.ps1 issue-token -Agent "agent-<uuid>" -Name "office-pc"
```

Both CLIs read `LAG_GW` / `LAG_TOKEN` / `LAG_AGENT`, or accept explicit flags. `lag.sh` uses only `curl`; `lag_ws.py` uses only the Python 3 standard library.

## 4. Roles and credentials

Two connection roles exist, and they are not interchangeable:

| Role | Endpoint | Purpose |
|---|---|---|
| `BROWSER` | `/ws/v2` | The controller — you |
| `AGENT` | `/ws/v2/agent` | The desktop being controlled |

| Credential | Browser link | Agent link | Admin REST |
|---|---|---|---|
| Gateway token | yes | yes | yes |
| `agt_…` per-agent token | **no** | **only its bound agent** | **no** |

- A leaked `agt_` token can impersonate **one** machine — never the browser, never the admin API, never other agents.
- `agt_` plaintext is shown **once** at issue time; only a SHA-256 hash is stored.
- **Rotating a credential immediately disconnects that agent.** Warn the operator before rotating.
- Prefer per-agent tokens over sharing the gateway token across machines.

## 5. Workflow

1. Confirm `LAG_GW`, `LAG_TOKEN`, and (for desktop work) `LAG_AGENT`.
2. Verify reachability and auth: `lag.sh health`, then `lag.sh status`.
3. If the agent id is unknown, run `lag.sh agents` and pick the intended machine.
4. Select the transport from section 2 and open the matching reference.
5. Execute the smallest request that answers the question; widen only if needed.
6. Report the raw result. Never claim an action succeeded unless a response confirmed it.

## 6. Guardrails

- **Never print or log the token.** Pass it by environment variable or an env file with `600` permissions. Avoid command lines where `ps` can read it.
- **`agt_` tokens are bound to one agent.** They cannot reach another machine.
- **Confirm before destructive or mutating calls** — `FsDelete`, `FsRename`, `FsWriteText`, credential rotation/deletion, `MemoryManage`, `CronManage`, `SkillManage`.
- **Never target a host you do not administer.**
- **Do not treat an empty result as a safe result.** Zero agents or an empty event window means *no data returned*, which is not the same as *nothing is wrong*. Confirm `online=true` first.
- **Respect the relay boundary.** If a task needs a tool the gateway does not whitelist, say so instead of improvising.
- **Report failures verbatim.** `401`, close code `4401`, and `local_error` mean different things; see `references/limits-and-errors.md`.

## 7. References

- `references/http-api.md` — HTTP endpoints, auth header, admin API, uploads, public shares.
- `references/protocol-v2.md` — handshake, frames, message fields, envelope arm numbers.
- `references/chat.md` — chat submit/edit/cancel, streaming, resume, idempotency, watchdogs.
- `references/remote-operations.md` — filesystem, git, terminal, SFTP, tunnels, memory, cron, skills, settings, history.
- `references/limits-and-errors.md` — size caps, concurrency, close codes, failure modes, recovery.
- `references/deployment.md` — deploying, upgrading, reverse-proxying, hardening a gateway.

## 8. Scripts

| File | Language | Purpose |
|---|---|---|
| `scripts/lag.sh` | bash / zsh | HTTP operations via `curl` |
| `scripts/lag.ps1` | Windows PowerShell | HTTP operations via `Invoke-RestMethod` |
| `scripts/lag_ws.py` | Python 3 (stdlib only) | WebSocket v2: handshake, status, agents, chat, pass-through |
| `scripts/envelope_arms.json` | data | Pass-through arm name → protobuf field number |

`lag_ws.py` requires `envelope_arms.json` to sit beside it; it is used by the `req` command.
