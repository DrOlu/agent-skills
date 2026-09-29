# Install — cross-platform, per host

One host at a time. Order: **engine → menu+harness → gateway → services →
verify**. Every value comes from `references/parameters.md`.

---

## 0. Common prerequisites

| Requirement | macOS | Linux | Windows |
|---|---|---|---|
| CPU/RAM | any x86-64/arm64, ~100 MB free RAM | same | same |
| Disk | ~40 MB (engine + weights) + data | same | same |
| Python (for the harness) | 3.11+ (framework or system) | 3.11+ | 3.11+ (`C:\Python3xx\python.exe`) |
| Service manager | launchd | systemd | NSSM or `sc.exe` |
| Time sync | `sudo sntp -sS time.apple.com` | `chrony`/`systemd-timesyncd` | `w32tm /resync` |
| Network | outbound to `NATS_URL` | same | same |

Install the engine (three interchangeable channels):

```bash
pip install neuralos            # PyPI — bundles engine + weights
curl -fsSL https://neuralos.ng/install.sh | sh
```

```powershell
py -m pip install neuralos
irm https://neuralos.ng/install.ps1 | iex
```

Or drop the standalone bundle so the harness can call the raw binary:
`https://neuralos.ng/download/neuralOS.zip` → extract to `NEEDLE_ENGINE_DIR`
(defaults: `/opt/neuralos/needle` on Linux, `~/neuralos/needle` on macOS,
`C:\reactorpro\needle` on Windows). The folder must contain the engine binary
(`needle`/`needle.exe` or `neural`/`neural.exe`) and the weights
(`needle3.cact` or `neuralOS.engine`) — **never hardcode the path**; resolve it
through `NEEDLE_ENGINE_DIR`.

Verify the engine:
```bash
"$NEEDLE_ENGINE_DIR/needle" --model "$NEEDLE_ENGINE_DIR/needle3.cact" \
  --tools tools.json --prompt "hello"        # expects JSON with function_calls
```

---

## 1. macOS (launchd)

```bash
export GATEWAY_MESH_ID="reactorpro/edge-darwin-01"
export NEEDLE_ENGINE_DIR="$HOME/neuralos/needle"
export LIVEAGENT_GATEWAY_TOKEN="$(openssl rand -hex 32)"
bash scripts/bootstrap_edge.sh          # engine check, gateway install, butler, launchd units
```

The bootstrap writes two plists under `~/Library/LaunchAgents/`:
`ng.reactorpro.gateway.plist` and `com.neuralos.butler.plist`, each with
`RunAtLoad=true` and `KeepAlive=true`, and `EnvironmentVariables` carrying
`NEEDLE_ENGINE_DIR`, the mesh id, the trusted peers and the token.

```bash
launchctl load -w ~/Library/LaunchAgents/ng.reactorpro.gateway.plist
launchctl kickstart -k gui/$(id -u)/ng.reactorpro.gateway
curl -s localhost:3000/healthz
```

---

## 2. Linux (systemd)

```bash
export GATEWAY_MESH_ID="reactorpro/edge-linux-01"
export NEEDLE_ENGINE_DIR="/opt/neuralos/needle"
bash scripts/bootstrap_edge.sh
```

Units written to `/etc/systemd/system/`:

```ini
# /etc/systemd/system/reactorpro-gateway.service
[Unit]
Description=ReactorPro gateway (mesh edge)
After=network-online.target
[Service]
Type=simple
User=reactorpro
EnvironmentFile=/etc/reactorpro/gateway.env
ExecStart=/usr/local/bin/reactorpro-gateway
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now reactorpro-gateway neuralos-butler
systemctl status reactorpro-gateway --no-pager
```

---

## 3. Windows (NSSM, or `sc.exe`)

```powershell
$env:GATEWAY_MESH_ID = "reactorpro/edge-win-01"
$env:NEEDLE_ENGINE_DIR = "C:\reactorpro\needle"
$env:LIVEAGENT_GATEWAY_TOKEN = -join ((1..64) | % { '{0:x}' -f (Get-Random -Max 16) })
pwsh -File scripts\bootstrap_edge.ps1
```

NSSM is the reference; equivalent `sc.exe` commands are printed by the script.

```powershell
nssm install ReactorProGateway C:\reactorpro\gateway.exe
nssm set ReactorProGateway AppEnvironmentExtra "LIVEAGENT_GATEWAY_MESH_ID=$env:GATEWAY_MESH_ID" "NEEDLE_ENGINE_DIR=$env:NEEDLE_ENGINE_DIR"
nssm set ReactorProGateway Start SERVICE_AUTO_START
nssm set ReactorProGateway AppStdout C:\reactorpro\logs\gateway.log
Restart-Service ReactorProGateway

nssm install NeuralosButler C:\Python314\python.exe C:\butler\butler.py
nssm set NeuralosButler AppDirectory C:\butler
nssm set NeuralosButler Start SERVICE_AUTO_START
```

> Remote Windows edges: drive them with PowerShell Remoting / PSRP from a
> workstation (see `references/troubleshooting.md` §6 for the PSRP gotchas —
> notably: move files as base64, and never call `[Console]::OutputEncoding`
> inside PSRP).

---

## 4. Wire trust (all platforms)

1. Read each edge's fingerprint:
   `curl -s -H "Authorization: Bearer $TOKEN" localhost:3000/api/mesh/status`.
2. Exchange fingerprints out of band (contract, signed email, phone).
3. On every edge set, in the service environment:
   - `-mesh-verify-mode=require`
   - `-mesh-trust-on-first-use=false`
   - `LIVEAGENT_GATEWAY_MESH_TRUSTED_PEERS=sha256:<peer1>,sha256:<peer2>`
4. Restart the gateway and confirm `describe` shows the pins.

---

## 5. Install a butler

Copy `scripts/butler_template.py` to the host as `butler.py` beside its
`needle_menu.json`, set the data source env vars, then install it as a service
(as above). Read `references/butler-harness.md` for the menu and the grounding
contract.

---

## 6. Verify the install (do not skip)

```bash
bash scripts/doctor.sh          # or: pwsh -File scripts\doctor.ps1
bash scripts/dispatch.sh reactorpro/peer-01 reactorpro/peer-01-butler butler.query \
     "never-seen question #1"
```

A pass means: engine resolves · menu loads · probe selection works on a fresh
phrasing · the digest is capped · the peer answers over the signed lane ·
and the wall time is recorded from at least two origins.