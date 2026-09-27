# Butler Architecture — the agentd-free reference deployment (v1.7.5+)

The reference architecture for a neuralOS edge that serves data over the mesh
**without an agentd**: a gateway (the only network-facing component) plus a
**butler harness** (a small local skill server that runs ask.py → needle →
database, read-only by construction, **needle-grounded by mandate**). Verified live on Windows Server 2022+
and macOS; Linux uses the systemd variant below.

> Deployed and proven 2026-09-27 on two edges (macOS ARM + Windows Server):
> Coronation balance ₦5,628,348.97 (Mac→WS2) and Chinook revenue $2,328.60
> (WS2→Mac), both over fully signed lanes. This document is the distilled,
> reproducible version of that build.



> ⚠️ **MANDATORY: Every butler.query MUST go through the needle engine.**
> The butler's serving path routes every question through ask.py → needle
> engine (on-device 121M inference) for probe grounding. There is no
> deterministic keyword-only fallback. The needle engine (needle.exe / neural.exe / neural.exe +
> needle3.cact / neuralOS.engine / neuralOS.engine) is a **required deployment artifact** on every edge — the
> butler will not start without it, and butler.query will return an honest
> hole rather than bypassing inference.
>
> This is enforced in the butler code: `butler.query` always spawns
> chinook_ask.py which invokes the needle engine binary. There is no
> code path that skips inference.


---

## 1. Architecture

```
        COMPANY A (any OS)                       COMPANY B (any OS)
  ┌──────────────────────────┐          ┌──────────────────────────┐
  │ GATEWAY v1.7.5+          │          │ GATEWAY v1.7.5+          │
  │ signs · verifies ·       │          │ signs · verifies ·       │
  │ skillproxy · roster      │          │ skillproxy · roster      │
  └────────┬─────────────────┘          └────────┬─────────────────┘
           │ loopback / own conn                 │
  ┌────────▼─────────────────┐          ┌────────▼─────────────────┐
  │ BUTLER HARNESS           │          │ BUTLER HARNESS           │
  │ read-only skill server   │          │ read-only skill server   │
  └────────┬─────────────────┘          └────────┬─────────────────┘
           │ ask.py → needle                     │ ask.py → needle
  ┌────────▼─────────────────┐          ┌────────▼─────────────────┐
  │ LOCAL INSTANCES          │          │ LOCAL INSTANCES          │
  │ (databases, live probes) │          │ (databases, live probes) │
  └──────────────────────────┘          └──────────────────────────┘
                    ╲                          ╱
                     ─── shared NATS bus ───
```

**Layer contract:**

| Layer | Holds | Never holds |
|---|---|---|
| Gateway | mesh identity (Ed25519), trust pins, skill router | data tools, provider keys |
| Butler | ask.py/needle execution, instance menus | mesh identity, secrets, write paths |
| Instances | the data | any mesh awareness |

## 2. Prerequisites (all OSes)

- **Gateway v1.7.5+** on the edge (contains the `skillproxy` skill — v1.7.4 and
  older do not serve it; `describe` the edge first to check). Install:
  `scripts/install-gateway.sh` (SHA256 verified).
- **Python 3.10+** with `nats-py` (`pip install nats-py`).
- **neuralOS instances on local disk** — each a directory containing
  `needle_menu.json`, `ask.py`, `bridge.py`, `models.py` and a needle engine
  (`needle` / `needle.exe / neural.exe / neural.exe` + `needle3.cact / neuralOS.engine / neuralOS.engine`), with `NEEDLE_ENGINE_DIR` set or a
  default baked in.
- **Mutual trust**: each edge's gateway fingerprint pinned in the peer's
  `LIVEAGENT_GATEWAY_MESH_TRUSTED_PEERS`.


### Binary Names

The needle engine ships under two names depending on the distribution:

| Distribution | Binary | Model |
|---|---|---|
| neuralOS release (`neuralOS.zip`) | `neural.exe` / `neural` | `neuralOS.engine` |
| needle skill (`needle3.cact`) | `needle.exe` / `needle` | `needle3.cact` |

They are the **same engine** — either works. Set `NEEDLE_ENGINE_DIR` to
whichever directory contains the binary and model. The ask.py scripts resolve
the binary at runtime via `NEEDLE_ENGINE_DIR`.

## 3. Gateway-side configuration (the edge that will *serve*)

```bash
# which local harnesses the skillproxy may reach (exact mesh ids; empty = off)
export LIVEAGENT_GATEWAY_MESH_SKILL_PROXY_TARGETS="reactorpro/coronation-ws2,reactorpro/neuralos-mac-001"
# make sure skillproxy is a routable invoke operation
export LIVEAGENT_GATEWAY_MESH_INVOKE_OPERATIONS="task,skillproxy"
```

Environment placement per OS:

| OS | Where the gateway service reads env |
|---|---|
| macOS (launchd) | `~/.config/reactorpro/gateway.env`, sourced by the launcher; use `export VAR=…` lines |
| Windows (NSSM service) | Machine environment: `[Environment]::SetEnvironmentVariable(name, value, 'Machine')`, then restart the service |
| Linux (systemd) | `Environment=` lines in the unit or an `EnvironmentFile=` |

Restart the gateway after changing env. Verify:

```bash
curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/mesh/status | \
  jq '{connected, skills}'      # "skillproxy" must appear in skills
```

## 4. Butler harness installation

The generic harness is `scripts/neuralos-butler.py` in the
**reactorpro-gateway-client** skill. Configure by environment:

| Env | Meaning |
|---|---|
| `BUTLER_AGENT_ID` | mesh id, e.g. `reactorpro/coronation-ws2` |
| `BUTLER_MESH_URL` | NATS URL (`nats://127.0.0.1:4222` for a local bus, or the shared bus) |
| `BUTLER_INSTANCE_DIR` | single-instance mode: one instance dir (has `needle_menu.json`) |
| `BUTLER_INSTANCES_DIR` | multi-instance mode: dir of instance subdirs |
| `BUTLER_PYTHON` | interpreter that runs ask.py (must have pydantic/yaml) |
| `BUTLER_ASK_TIMEOUT` | seconds per probe (default 120) |

Served skills: `butler.list` (menu digest) and
`butler.query {instance?, question, k?}` (probe answer). Read-only: the harness
contains no write paths at all.

### 4.1 macOS — launchd

```bash
# env + runner
cat > ~/butler.env <<'EOF'
export BUTLER_AGENT_ID="reactorpro/coronation-ws2"
export BUTLER_MESH_URL="nats://52.3.242.251:4222"
export BUTLER_INSTANCE_DIR="/path/to/coronation"
export NEEDLE_ENGINE_DIR="/path/to/needle"
EOF
cat > ~/run_butler.cmd <<'EOF'
#!/bin/bash
source "$HOME/butler.env"
exec /usr/bin/env python3 /path/to/neuralos-butler.py
EOF
chmod +x ~/run_butler.cmd
```

`~/Library/LaunchAgents/com.<you>.butler.plist`:

```xml
<plist version="1.0"><dict>
  <key>Label</key><string>com.<you>.butler</string>
  <key>ProgramArguments</key><array><string>~/run_butler.cmd</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>~/Library/Logs/butler.log</string>
  <key>StandardErrorPath</key><string>~/Library/Logs/butler.log</string>
</dict></plist>
```
`launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.<you>.butler.plist`

### 4.2 Windows — scheduled task (SYSTEM, on-start) or NSSM

```powershell
# deps
python -m pip install --quiet nats-py pydantic pyyaml

# runner script (C:\butler\run_butler.cmd):
#   @echo off
#   set NEEDLE_ENGINE_DIR=C:\path\to\needle
#   set BUTLER_AGENT_ID=reactorpro/coronation-ws2
#   set BUTLER_MESH_URL=nats://127.0.0.1:4222
#   set BUTLER_INSTANCE_DIR=C:\path\to\coronation
#   python C:\butler\neuralos-butler.py > butler.log 2>&1

schtasks /Create /F /TN ButlerHarness /TR "C:\butler\run_butler.cmd" `
  /SC ONSTART /RU SYSTEM
schtasks /Run /TN ButlerHarness
```

(NSSM alternative: `nssm install ButlerHarness <python> <script>` — same env,
auto-restart.)

### 4.3 Linux — systemd

```ini
# /etc/systemd/system/butler.service
[Unit]
Description=neuralOS butler harness
After=network-online.target

[Service]
User=butler
Environment=BUTLER_AGENT_ID=reactorpro/coronation-linux
Environment=BUTLER_MESH_URL=nats://127.0.0.1:4222
Environment=BUTLER_INSTANCE_DIR=/opt/neuralos/coronation
Environment=NEEDLE_ENGINE_DIR=/opt/neuralos/needle
ExecStart=/usr/bin/python3 /opt/butler/neuralos-butler.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
`systemctl daemon-reload && systemctl enable --now butler`

### 4.4 Verification (from any mesh citizen)

```python
import asyncio, json, nats
async def main():
    nc = await nats.connect("nats://<bus>:4222")
    env = {"v":"1.0.0","type":"request","from":"verifier",
           "payload":{"skill":"butler.query","task_id":"t1",
                      "input":{"question":"what is my investment balance?"}}}
    m = await nc.request("mesh.agent.<butler-id>.inbox",
                         json.dumps(env).encode(), timeout=120)
    print(m.data.decode())
    await nc.close()
asyncio.run(main())
```
Expect `payload.result.ok == true` with live data and an `elapsed_s`.

## 5. Calling a butler on another edge (the signed lane)

Two supported paths:

**A. Gateway skillproxy (recommended — signed both hops).** From the caller's
host, POST to its own gateway:

```bash
curl -s -X POST http://127.0.0.1:3000/api/mesh/dispatch \
  -H "Authorization: Bearer $LIVEAGENT_GATEWAY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"target":"<peer-gateway-id>","skill":"skillproxy","timeoutMs":180000,
       "input":{"target":"<butler-id>","skill":"butler.query",
                "args":{"question":"…"}}}'
```

Requirements: the caller's gateway must list the butler id in
`MESH_SKILL_PROXY_TARGETS`; the *peer* gateway must (a) pin the caller's
fingerprint and (b) include `skillproxy` in `MESH_INVOKE_OPERATIONS`.

**B. Direct NATS (unsigned, same bus).** Any NATS client publishing the synapse
envelope to `mesh.agent.<butler-id>.inbox`. Fine for read-only probes on a
trusted bus; no identity.

> ⚠️ Do **not** route skillproxy calls through an agentd-turn (`operation:
> task` with a prompt asking the agent to "relay to…"). It works, but it costs
> an LLM turn, needs the agentd's env token, and adds a fragile quoting layer.
> With no agentd installed, the edge is simpler and the butler is the only
> data path.

## 6. Operations

| Task | How |
|---|---|
| Butler alive? | bus `/connz` shows its connection; or `butler.list` request |
| Butler wedged? | watchdog self-probes every 60 s; 2 misses → self-exit → service manager restarts it |
| Gateway mesh status | `/api/mesh/status` (Bearer token): `connected`, `skills` (must include `skillproxy`), `mailbox.running` |
| Peer liveness | dispatch `ping` to the peer gateway id |
| Logs | macOS `~/Library/Logs/butler.log` · Windows `butler.log` · Linux `journalctl -u butler` |

## 7. Gotchas (all hit live)

1. **Args keys**: gateway dispatches carry args under `payload.input`;
   synapse-client under `payload.message`. Butlers accept both.
2. **Reply envelopes must carry `id` and `to`** — the gateway refuses
   envelope-less replies ("reply is not a mesh envelope").
3. **`skillproxy` is a top-level skill**, not an invoke `operation`. Calling it
   as an operation hits `3001`; calling it as an operation routed to an agentd
   hits "the desktop transport serves only the task operation".
4. **Elevated service restarts on Windows**: an unelevated shell cannot
   `net start` a stopped gateway. Deploy via WinRM-as-Administrator or RDP.
5. **Deploy-copy sync**: the service runs the *deployed* script (e.g.
   `~/.local/bin/`, `C:\reactorpro\workdir\`); patching a workspace copy does
   nothing until synced + restarted.
6. **Loaded hosts starve on-device inference**: timeouts become honest holes;
   the watchdog covers zombie subscriptions, load spikes just need patience.
7. **Never route butler calls through an agentd-turn** — an LLM quoting a JSON
   payload inside CMD is the most fragile hop in the entire chain.
8. **PII on the bus**: whatever the probes return rides the NATS transport. Put
   NKeys + TLS on the bus before serving anything more sensitive than these
   read-only probes.

## 8. Rollback

Every element is additive: remove the butler service/task, unset
`MESH_SKILL_PROXY_TARGETS`, restart the gateway. Gateway binaries are swapped
alongside a `.bak-vX` copy; the pre-migration state is one file-restore + one
service restart away.
