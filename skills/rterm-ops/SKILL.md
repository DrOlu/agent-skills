---
name: rterm-ops
description: >
  Install, start, and fully operate neuralOS / rterm-backend (gybackend daemon)
  and rterm-cli from any agent harness (CyberAgent/Pi, Claude Code, Codex,
  OpenCode, Hermes, Cursor, …). Use when a task needs SSH, WinRM, PSRP,
  serial, fleet commands, playbooks, Windows/AD, Cisco, or the RTerm agent
  over the WebSocket gateway. Also use when rterm ping fails or neuralos is
  missing. Configure the daemon (model, API key, model profile, agent-settings
  slot, gateway access, command policy) via settings:get / settings:set.
---

# rterm-ops — neuralOS + rterm-cli for any harness

**RTerm desktop** is the GUI. **neuralOS** (`neuralos` / `rterm-backend` npm, bin **`gybackend`**) is the same engine as a headless daemon. **`rterm-cli`** (bins `rterm` / `rterm-cli`) is the client. You talk to the daemon over **WebSocket JSON-RPC** (default `ws://127.0.0.1:17888`).

This skill is **harness-agnostic**: CyberAgent (Pi runtime), Pi standalone, Claude Code, Codex, OpenCode, Hermes, Cursor, or a raw shell.

```
Harness (Pi / Claude / …)
    → this skill
        → rterm-cli  (or POST /api/v1/rpc)
            → gybackend / neuralos
                → SSH / WinRM / PSRP / serial / playbooks / agent
```

Do **not** use interactive `rterm chat` for unattended tickets (CyberAgent issues, CI). Use `rterm call` / `rterm run` / `rterm fleet`.

---

## 0. First action every session (mandatory)

**Preferred (Windows, macOS, Linux — same command):** from the skill root:

```bash
node scripts/ensure-rterm.mjs
```

Windows PowerShell (Pi skill path):

```powershell
node "$env:USERPROFILE\.pi\agent\skills\rterm-ops\scripts\ensure-rterm.mjs"
```

Windows cmd:

```bat
node "%USERPROFILE%\.pi\agent\skills\rterm-ops\scripts\ensure-rterm.mjs"
```

Unix bash fallback (Git Bash / macOS / Linux):

```bash
bash scripts/ensure-rterm.sh
```

What `ensure-rterm.mjs` does:

1. Requires **Node ≥ 18** (exit **2** if not).
2. If `rterm-cli` / `rterm` missing → `npm install -g rterm-cli` (retries with a temp cache on EACCES).
3. If `gybackend` missing → `npm install -g neuralos`.
4. If ping fails and `ENSURE_RTERM_START` is not `0` → start `gybackend` detached (Windows: `windowsHide`; Unix: `detached`).
5. Exit **0** = ping OK. **1** = gateway still down. **2** = Node too old.

Skip auto-start: `ENSURE_RTERM_START=0` (Unix) or `set ENSURE_RTERM_START=0` (cmd) then re-run.

**Windows PATH:** after `npm i -g`, open a **new** terminal if `where rterm-cli` fails. Global bins are usually `%AppData%\npm`. Add that folder to PATH if needed.

**Foolproof order:** (1) `node -v` ≥ 18 (2) `node scripts/ensure-rterm.mjs` (3) `node scripts/show-config.mjs` — if `hasApiKey` is false or `model` is empty, set `OPENROUTER_API_KEY` and run `node scripts/set-api-key.mjs` (4) then `rterm ping` / `open` / `run`. Full copy-paste: `examples/README.md`.

Helpers (all OS):

| Script | Purpose |
|---|---|
| `scripts/ensure-rterm.mjs` | Install + start + ping |
| `scripts/ensure-rterm.sh` | Same, bash-only |
| `scripts/show-config.mjs` | Model/profile **without** printing apiKey |
| `scripts/set-api-key.mjs` | `settings:set` apiKey from env |

---

## 1. Environment

| Variable | Default | Meaning |
|---|---|---|
| `RTERM_URL` | `ws://127.0.0.1:17888` | Gateway |
| `RTERM_HOST` / `RTERM_PORT` | `127.0.0.1` / `17888` | Used if `RTERM_URL` unset |
| `RTERM_TOKEN` | (none) | Bearer; **required off-localhost** |
| `GYBACKEND_WS_HOST` | `0.0.0.0` | Daemon bind |
| `GYBACKEND_WS_PORT` | `17888` | Daemon port |
| `GYBACKEND_DATA_DIR` | `./.gybackend-data` or `~/.gybackend-data` | Settings, SQLite, tokens |
| `GYBACKEND_WS_ENABLE` | `1` | Must be on for the gateway |

Remote example:

```bash
export RTERM_URL=ws://10.0.0.5:17888
export RTERM_TOKEN=gys_at_…
rterm ping
```

`rterm-cli` ≥ 3.7.4 sends the token as **header + `?access_token=`**. Loopback often skips the token.

HTTP overlay (same port, v3.7.7+): `GET http://127.0.0.1:17888/api/v1/health`, `GET /api/v1/openapi.json`, `POST /api/v1/rpc`. Prefer `rterm-cli` unless you only have curl.

---

## 1b. Configure neuralos (model, API key, profile, gateway, policy)

Settings live in `$GYBACKEND_DATA_DIR/settings.json` (often `~/.gybackend-data/settings.json`). **`settings:set` deep-merges, persists, and live-reloads** — no daemon restart for model/key/profile. Always **`settings:get` first**, then patch. **Never print `apiKey` or tokens in tickets or chat.**

### Inspect (redact secrets)

```bash
rterm call settings:get '{}'
# If jq is available, show model config without dumping the key:
rterm call settings:get '{}' | jq '{model, baseUrl, active: .models.activeProfileId, profiles: [.models.profiles[]? | {id, name, model, baseUrl, hasKey: ((.apiKey // "") | length > 0)}]}'
```

### What actually drives the agent

| Field | Role |
|---|---|
| Top-level `model`, `baseUrl`, `apiKey` | **Live** values the agent uses. Copied from the **active model profile** on load/save. |
| `models.profiles[]` | Named presets (`id`, `name`, `model`, `baseUrl`, `apiKey`, optional `reviewModelId` / `reviewMode`). |
| `models.activeProfileId` | Which profile is active. If set, keep **top-level** `model`/`baseUrl`/`apiKey` in sync with that profile. |
| `models.items[]` | Catalog of model ids (picker), not the live key. |
| `agentSettings.activeProfileId` | **Agent-settings slot** (memory.md path, etc.). Different from `models.activeProfileId`. |

OpenRouter-style: `baseUrl` = `https://openrouter.ai/api/v1` (or your proxy), `model` = `moonshotai/kimi-k3` / `openai/gpt-4o`, `apiKey` = `sk-or-v1-…`.

### Set live model + base URL (no key in the command line if you can avoid it)

Prefer env for the key so it stays out of shell history. **Use the helper (Windows + Unix):**

```bash
# 1) model + base (safe to log)
rterm call settings:set "{\"settings\":{\"model\":\"moonshotai/kimi-k3\",\"baseUrl\":\"https://openrouter.ai/api/v1\"}}"

# 2) key from env — never echo the key
node scripts/set-api-key.mjs --model moonshotai/kimi-k3 --base-url https://openrouter.ai/api/v1
```

Windows cmd: `set OPENROUTER_API_KEY=...` then the same `node scripts\set-api-key.mjs ...`.  
PowerShell: `$env:OPENROUTER_API_KEY = '...'`.  
**Do not** write `sk-…` into SKILL.md or git. See `examples/README.md`.

### Create or switch a **model profile**

```bash
# Read current profiles (ids/names only)
rterm call settings:get '{}' | jq '.models.profiles[]? | {id, name, model, baseUrl}'

# Activate an existing profile by id (also set top-level to match — live-reload uses both)
rterm call settings:set '{"settings":{"models":{"activeProfileId":"<profile-id>"},"model":"<same-model-as-profile>","baseUrl":"<same-baseUrl>"}}'
```

Add a profile by merging into `models.profiles` (keep existing entries). Generate a unique `id` (e.g. `model-<timestamp>`):

```bash
rterm call settings:set '{"settings":{"models":{"activeProfileId":"model-openrouter","profiles":[{"id":"model-openrouter","name":"OpenRouter Kimi","model":"moonshotai/kimi-k3","baseUrl":"https://openrouter.ai/api/v1","apiKey":""}]},"model":"moonshotai/kimi-k3","baseUrl":"https://openrouter.ai/api/v1"}}'
```

Then set `apiKey` via the env snippet above (and on that profile if you persist keys in profiles). Empty `apiKey` in the example is intentional — fill from env.

Optional review (maker/checker): on a profile set `reviewModelId` + `reviewMode` (`strict` / `advisory` / `auto-approve`).

### Agent-settings **slot** (memory / slot pointer)

```bash
rterm call settings:get '{}' | jq '.agentSettings'
rterm call settings:set '{"settings":{"agentSettings":{"activeProfileId":"agent-setting-slot-1"}}}'
```

That pointer selects which slot’s `memory.md` the agent loads. It does **not** change the LLM.

### Gateway access (so other machines / CyberAgent can connect)

```bash
# Inspect (no secrets)
rterm call settings:get '{}' | jq '.gateway'

# Allow non-localhost (token required). Valid access: localhost | lan | internet | disabled | custom
rterm call settings:set '{"settings":{"gateway":{"ws":{"access":"internet","port":17888}}}}'
```

Tokens: `$GYBACKEND_DATA_DIR/access-tokens.json` (hashed). Create via RTerm UI or a hashed record — **never** invent a plaintext token in settings.json. Remote clients: `export RTERM_TOKEN=…`.

### Command policy (unattended vs ask)

```bash
rterm call settings:getCommandPolicyLists '{}'
rterm call settings:set '{"settings":{"commandPolicyMode":"smart"}}'   # unattended: run unless denylisted
# rterm call settings:set '{"settings":{"commandPolicyMode":"standard"}}'  # ask
# rterm call settings:set '{"settings":{"commandPolicyMode":"safe"}}'      # deny unknown
rterm call settings:addCommandPolicyRule '{"list":"allowlist","rule":"hostname"}'
```

CyberAgent / Pi tickets: **`smart`** plus an allowlist, or runs stick on `command_ask`.

### Backup / export / import

```bash
rterm call settings:listBackups '{}'
rterm call settings:export '{}'          # JSON string — redact apiKey before saving to git
rterm call settings:restoreBackup '{"name":"<backup-name>"}'
```

### After configure

```bash
rterm ping
rterm version
# optional: one-shot agent (needs a session)
rterm call gateway:createSession '{}'
# then startTask with userInput "Reply with pong" — do not log apiKey if the error dumps settings
```

If the model is empty, the agent will fail or use a useless default — **configure before** `startTask`.

---

## 2. Mental model

| Piece | npm | Bin | Job |
|---|---|---|---|
| Engine | `neuralos` (alias `rterm-backend`) | `gybackend` | Daemon: terminals, agent, playbooks, WS |
| Client | `rterm-cli` | `rterm`, `rterm-cli` | One-shot + interactive chat |
| GUI | RTerm.app | — | Same engine + windows |

`neuralos` and `rterm-backend` are the **same** program. Install **one**. Keep versions aligned (`npm view neuralos dist-tags.latest`).

Discover **all** RPCs (do not guess names):

```bash
rterm methods
rterm methods --category terminal
rterm methods --category agent
rterm call gateway:describe
```

Escape hatch for anything not wrapped as a subcommand:

```bash
rterm call <method> '<json-params>'
```

---

## 3. CLI map (full capabilities)

Use `rterm` or `rterm-cli` interchangeably.

### Liveness & discovery

```bash
rterm ping
rterm version                          # backend version + method count
rterm methods [--category agent] [--prefix terminal:]
rterm call gateway:describe
```

### Terminals (SSH / WinRM / PSRP / serial / local)

```bash
rterm terminals
rterm connections                      # saved SSH/WinRM/Serial
rterm open <saved-connection-name>
rterm close <tabIdOrName>
rterm run <tabIdOrName> <command>      # wait for output
rterm fleet <tab1,tab2,...> <command>  # same command, many tabs
```

Open **saved** names only (`CORP-DC1`, `CORP-WS2`). `terminal:createTab` does **not** resolve names by itself; `rterm open` builds the config.

WinRM/PSRP: **command/response**, not a TTY. No vim/top. Drive with `rterm run` / agent `exec_command`, not raw `terminal:write` (no-op on WinRM).

### Agent (unattended)

```bash
rterm sessions
rterm call gateway:createSession '{}'
rterm call agent:startTask '{"sessionId":"<id>","userInput":"<task>"}'
# long jobs:
rterm call agent:startTaskAsync '{"sessionId":"<id>","userInput":"<task>"}'
```

Then watch `gateway:event` (desktop / `rterm chat`) or poll session messages.

```bash
rterm call agent:stopTask '{"sessionId":"<id>"}'
rterm call agent:getUiMessages '{"id":"<sessionId>"}'
```

### Interactive chat (humans only)

```bash
rterm chat
rterm chat --session <id>
```

Slash: `/new` `/sessions` `/rename` `/branch` `/export` `/search` `/stop` `/verbose` `/exit`. Approvals: `allow? [y/N]`. **Not for CyberAgent tickets.**

### Observability / dashboard

```bash
rterm dashboard
rterm metrics
rterm metrics --format prometheus
rterm call observability:apmSummary
rterm call list_gateway_methods
```

Browser: `http://127.0.0.1:17888/dashboard`

---

## 4. RPC categories (use `rterm call`)

After `rterm methods`, typical groups:

| Category | Examples |
|---|---|
| terminal | list, createTab, write, getBufferDelta, kill |
| agent | startTask, startTaskAsync, stopTask, getUiMessages |
| session | list, get |
| settings | get, set — connections, playbooks, schedules |
| skills | getAll |
| observability | metrics, dashboard, APM ingest/summary, DEM |
| filesystem | read/write via agent tools on a tab |
| playbooks / change | manage_playbook, run_playbook, manage_change (MOP) |

**Compounding (v3.7.6+):** `ops_experiment`, `manage_goal`, `estate_facts`. Gated mutations (`Add-Computer`, `Install-ADDSForest`, `djoin /provision`, SG ingress, …) **refuse** until `ops_experiment` recorded a matching tag **this session**.

**PSRP (v3.7.4+):** WinRM `transport: psrp` — script in message body, no 8191-char cap. v3.8+ can keep a **persistent runspace** (`$x` survives). Auth: basic / ntlm / negotiate / kerberos (Negotiate = NTLMv2 on the wire unless a real TGT exists).

---

## 5. CyberAgent + Pi (recommended)

CyberAgent’s runtime is **Pi**. Do **not** add a `rterm` protocol_family.

1. Machine running **`multica daemon`** = machine running **gybackend** (same user/`PATH`).
2. This skill visible to Pi (`~/.pi/agent/skills/rterm-ops` and/or workspace skill import).
3. Assign issues to the **Pi** agent. Ticket text:

> Use **rterm-ops**. Run `ensure-rterm.sh` (or `rterm ping`). Then open **CORP-DC1** and …

4. Pi may only edit git unless the issue **names this skill** and the estate.

Sandbox: allow `rterm`, `rterm-cli`, `gybackend`, `npm`, loopback **17888**.

Other harnesses: copy this folder into that product’s skills dir (`~/.agents/skills`, Cursor, Codex, …). Same SKILL.md.

---

## 6. Estate notes (corp.local lab)

If connections exist:

| Name | Role | Transport / auth |
|---|---|---|
| CORP-DC1 | Forest root `corp.local` | psrp + negotiate, `CORP\Administrator` |
| CORP-WS2 | Domain member | psrp + negotiate |
| AWS-Windows-Server-* | Often still **local** Administrator / http basic | Do not confuse with CORP-* (same IP ≠ same identity) |

- After DC promo, **Basic to the DC may 401**; use Negotiate + domain.
- **Do not** retry `Add-Computer` if `NetUseAdd \\DC\IPC$` = 64. Use **offline join** (`djoin /provision` on DC, `djoin /requestODJ` on member).
- `estate_facts` is keyed by **connection name**, not IP (`CORP-DC1` ≠ `neuralos-win1`).
- WinRM `$` in `powershell -Command "..."` gets mangled — prefer PSRP / `rterm run` / files.

---

## 7. Playbooks, fleet, MOP

```bash
rterm call manage_playbook '{"action":"list"}'
rterm call run_playbook '{"name":"<playbook>"}'
```

Fleet = **same shell command** on **open** tabs. Subagents (inside RTerm agent) = **independent reasoning** jobs. Don’t use interactive chat to fan out; use `rterm fleet` or `agent:startTask` with a prompt that says `spawn_subagents`.

MOP: `manage_change` plan → **human** approve → run. Do not self-approve.

---

## 8. HTTP `/api/v1` (v3.7.7+)

Same auth as WS. Parameterized routes work. Streaming still WS.

```bash
curl -s http://127.0.0.1:17888/api/v1/health
curl -s http://127.0.0.1:17888/api/v1/openapi.json | head
curl -s -X POST http://127.0.0.1:17888/api/v1/rpc \
  -H 'Content-Type: application/json' \
  -d '{"method":"gateway:ping","params":{}}'
```

Off-localhost: `Authorization: Bearer $RTERM_TOKEN`.

---

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `rterm ping` fails | `gybackend` not running; port; `RTERM_URL` |
| npm `EACCES` / root-owned cache | `npm i -g … --cache /tmp/npm-fresh` (neuralos.mjs retries this) |
| Remote close / 1008 missing token | Set `RTERM_TOKEN`; upgrade rterm-cli ≥ 3.7.4 |
| `METHOD_NOT_FOUND` | `rterm methods`; upgrade neuralos |
| WinRM ready, empty output | Don’t `terminal:write`; use `rterm run` / agent |
| Task stuck on approval | Policy `standard` — not for unattended; use allowlist / `smart` / reply RPC |
| `history:search` missing | Optional history bridge |
| Desktop freeze (old) | neuralos ≥ 3.7.7 (SQLite cache + 32k tool cap) |
| PSRP `InvalidSelectors` | neuralos ≥ 3.7.4 (dest byte + INIT_RUNSPACEPOOL objects) |
| Plugin tools missing on standalone | Known gap on some daemons — use CLI/RPC; plugins still load for triggers/panels |
| Agent errors / empty replies after ping works | `model` / `apiKey` unset — §1b `settings:get` then `settings:set`; never log the key |
| `settings:set` seems ignored | Deep-merge; `models.activeProfileId` can overwrite top-level on next load — set profile **and** top-level `model`/`baseUrl`/`apiKey` together |
| Windows: `rterm-cli` not found after npm i -g | New terminal; add `%AppData%\npm` to PATH; use `rterm-cli.cmd` / `gybackend.cmd` |
| Windows: `bash: ensure-rterm.sh` | Use `node scripts\ensure-rterm.mjs` — do not require Git Bash |

Logs: `~/.gybackend-data/gybackend.log` or `$GYBACKEND_DATA_DIR`.

---

## 10. Safety

- Never put tokens/passwords in skill files, tickets, or `rterm call` JSON in git.
- Use env `RTERM_TOKEN`, vault `secretRef`, or localhost bypass.
- Destructive AD/network: `ops_experiment` first; prefer MOP.
- This skill **installs npm globals** when missing — only on machines you administer.

---

## 11. Install this skill

| Harness | Location |
|---|---|
| GyShell / RTerm agent | `~/.agents/skills/rterm-ops/` |
| Pi (CyberAgent daemon user) | `~/.pi/agent/skills/rterm-ops/` |
| Catalog | `~/work/agent-skills/skills/rterm-ops/` (push to DrOlu/agent-skills) |

Keep all three copies in sync. Pair with **neuralos** skill for daemon lifecycle (`setup`/`verify`/`install-service`). This skill is the **client + bootstrap** path.

### CyberAgent issue template

```text
Runtime: Pi
Skill: rterm-ops

1. node ~/.pi/agent/skills/rterm-ops/scripts/ensure-rterm.mjs
   (Windows: node %USERPROFILE%\.pi\agent\skills\rterm-ops\scripts\ensure-rterm.mjs)
2. rterm ping && rterm connections
3. (task-specific rterm open / run / call …)
4. Paste command output in the issue comment. Do not use rterm chat.
```
