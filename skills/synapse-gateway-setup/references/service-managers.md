# Running the gateway as a service

Templates for every supported platform ship in the skill's `scripts/` directory:

- `scripts/reactorpro-gateway.service` — systemd unit
- `scripts/ng.reactorpro.gateway.plist` — launchd job
- `scripts/gateway-launch.sh` — launcher that reads secrets from files at start time
- `scripts/install-gateway.sh` — download, verify, install, optionally enable the service

## Contents

- [Principles](#principles)
- [Linux — systemd](#linux--systemd)
- [macOS — launchd](#macos--launchd)
- [Windows](#windows)
- [Docker](#docker)
- [Kubernetes and Nomad](#kubernetes-and-nomad)
- [Reverse proxy](#reverse-proxy)

## Principles

Three rules apply on every platform, and they are what make the difference between a
gateway that stays up and one that quietly misbehaves:

1. **Keep the token out of the command line.** Arguments are world-readable via `ps`.
   Every service manager here has a way to pass environment variables instead; use it.
2. **Keep the data directory stable and persistent.** It holds the mesh identity. If the
   service starts with a different data dir after a reboot, the gateway silently becomes a
   different agent.
3. **Restart on failure, but verify after restart.** `Restart=always` / `KeepAlive` keeps
   the process alive; it does not tell you the mesh reconnected. Check
   `/api/mesh/status` after deploys.

## Linux — systemd

### Unit

```ini
# /etc/systemd/system/reactorpro-gateway.service
[Unit]
Description=ReactorPro Gateway
Documentation=https://github.com/DrOlu/ReactorPro
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=reactorpro
Group=reactorpro
EnvironmentFile=/etc/reactorpro-gateway.env
ExecStart=/usr/local/bin/reactorpro-gateway --http-addr=127.0.0.1:3000
Restart=always
RestartSec=5
StateDirectory=reactorpro-gateway
WorkingDirectory=/var/lib/reactorpro-gateway

# Hardening. The gateway needs to write only its own state directory.
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=/var/lib/reactorpro-gateway
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
MemoryDenyWriteExecute=true
SystemCallArchitectures=native

# See the connection-limit note below before changing this.
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

`EnvironmentFile` is read by systemd **as root**, before dropping to `User=`, so the file
can be `0600 root:root` and the service still receives the values. That is the safest
arrangement.

`WorkingDirectory` and `StateDirectory` agree with
`LIVEAGENT_GATEWAY_DATA_DIR=/var/lib/reactorpro-gateway` in the environment file, so a
relative path can never resolve somewhere unexpected.

`MemoryDenyWriteExecute=true` is safe for a Go binary (no JIT). If you ever add a
dependency that JITs, this is the line to relax.

### Install

```bash
useradd --system --home /var/lib/reactorpro-gateway --shell /usr/sbin/nologin reactorpro
install -d -m 0750 -o reactorpro -g reactorpro /var/lib/reactorpro-gateway

umask 077
{
  echo "LIVEAGENT_GATEWAY_TOKEN=$(openssl rand -hex 32)"
  echo "LIVEAGENT_GATEWAY_DATA_DIR=/var/lib/reactorpro-gateway"
} > /etc/reactorpro-gateway.env
chmod 0600 /etc/reactorpro-gateway.env
chown root:root /etc/reactorpro-gateway.env

systemctl daemon-reload
systemctl enable --now reactorpro-gateway
journalctl -u reactorpro-gateway -f
```

Note the values are written **without quotes** — the gateway does not strip them, and a
quoted token produces a 401 on every request.

`LimitNOFILE`: each connected agent consumes more than one descriptor (the control
connection plus terminal data plane). The default 1024 is comfortable for a handful of
agents and not for hundreds. Raise it before raising
`--max-agent-connections`/`--max-browser-connections`/`--max-terminal-connections`, or
connections will be refused with `503` for reasons that look like a limit being hit and
are actually fd exhaustion.

### Hardening and the mesh

`ProtectHome=true` is fine with an explicit data dir under `/var/lib`. If you leave
`LIVEAGENT_GATEWAY_DATA_DIR` unset, the gateway resolves the *service user's* home and
`ProtectHome` may block it — another reason to always set the data dir.

## macOS — launchd

Two placements, and the difference matters:

| Location | Starts | Runs as |
|---|---|---|
| `~/Library/LaunchAgents/ng.reactorpro.gateway.plist` | At **login** | The logging-in user |
| `/Library/LaunchDaemons/ng.reactorpro.gateway.plist` | At **boot** | `root`, or `UserName` if set |

Use a LaunchAgent for a workstation (no `sudo`, starts when you log in). Use a
LaunchDaemon for a machine that must serve before anyone logs in.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>ng.reactorpro.gateway</string>

    <!-- The launcher reads the token from a 0600 file at start time, so no
         secret is stored in this plist, which is world-readable. -->
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/reactorpro-gateway-launch.sh</string>
    </array>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>

    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>

    <key>WorkingDirectory</key>
    <string>/Users/CHANGEME/Library/Application Support/reactorpro-gateway</string>

    <key>StandardOutPath</key>
    <string>/Users/CHANGEME/Library/Logs/reactorpro-gateway.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/CHANGEME/Library/Logs/reactorpro-gateway.err.log</string>

    <key>ProcessType</key>
    <string>Background</string>
</dict>
</plist>
```

`RunAtLoad` starts it; `KeepAlive` restarts it after any exit. launchd logs to the files
above rather than to a journal, so `tail -f` them.

Load, reload, and manage:

```bash
plutil -lint ~/Library/LaunchAgents/ng.reactorpro.gateway.plist   # always lint first
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/ng.reactorpro.gateway.plist
launchctl print "gui/$(id -u)/ng.reactorpro.gateway" | grep -E 'state|pid|last exit'
launchctl kickstart -k "gui/$(id -u)/ng.reactorpro.gateway"       # restart
launchctl bootout "gui/$(id -u)/ng.reactorpro.gateway"            # stop and unload
```

For a LaunchDaemon use the `system` domain instead of `gui/$(id -u)`.

The launcher pattern exists because plists are world-readable. `gateway-launch.sh` reads
the token from a `0600` file and exports it, so the secret never appears in the plist.
It does **not** `exec` the binary: after login, Gatekeeper can stall an adhoc
GitHub-downloaded gateway for minutes (`xpcproxy` / dyld cond-wait) while launchd
still reports the job as running and nothing listens. The launcher starts the
binary, waits until `/api/status` answers (200/401/403), and kill-and-retries if
it does not (`REACTORPRO_GATEWAY_READY_TIMEOUT`, default 45s;
`REACTORPRO_GATEWAY_START_ATTEMPTS`, default 8). `KeepAlive` then covers a real
crash, not a frozen first load.

## Windows

**The binary is not a Windows service.** It has no service control handler, so
`sc.exe create` will report success and the service will then fail to start with error
1053. Two workable approaches:

### NSSM or WinSW (recommended)

```powershell
# Elevated PowerShell
nssm install ReactorProGateway "C:\Program Files\ReactorPro\reactorpro-gateway.exe"
nssm set ReactorProGateway AppParameters "--http-addr=:3000"
nssm set ReactorProGateway AppDirectory "C:\ProgramData\ReactorPro"
nssm set ReactorProGateway AppEnvironmentExtra `
  "LIVEAGENT_GATEWAY_DATA_DIR=C:\ProgramData\ReactorPro" `
  "LIVEAGENT_GATEWAY_TOKEN=<token>"
nssm set ReactorProGateway Start SERVICE_AUTO_START
nssm start ReactorProGateway
```

WinSW is the same idea with an XML config and a single signed executable, which is often
preferable in managed environments.

### Task Scheduler

No third-party software, and adequate for a single host:

```powershell
$action  = New-ScheduledTaskAction -Execute "C:\Program Files\ReactorPro\reactorpro-gateway.exe" `
             -Argument "--http-addr=:3000" -WorkingDirectory "C:\ProgramData\ReactorPro"
$trigger = New-ScheduledTaskTrigger -AtStartup
$set     = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "ReactorPro Gateway" -Action $action -Trigger $trigger `
  -Settings $set -User "SYSTEM" -RunLevel Highest
```

Set the token as a machine-wide variable so it is not in the task arguments:

```powershell
setx /M LIVEAGENT_GATEWAY_TOKEN "<token>"
setx /M LIVEAGENT_GATEWAY_DATA_DIR "C:\ProgramData\ReactorPro"
```

(The task must be re-registered or the service restarted after `setx /M`; the environment
is captured at process start.)

### Windows Firewall

If desktop apps connect from other machines:

```powershell
New-NetFirewallRule -DisplayName "ReactorPro Gateway" -Direction Inbound `
  -Protocol TCP -LocalPort 3000 -Action Allow
```

## Docker

An image is published as `ghcr.io/drolu/liveagent-gateway`. The name is a legacy internal
identifier kept deliberately for compatibility — it **is** the ReactorPro gateway.

```bash
docker run -d --name reactorpro-gateway \
  --restart unless-stopped \
  -p 3000:3000 \
  -e LIVEAGENT_GATEWAY_TOKEN="$TOKEN" \
  -e LIVEAGENT_GATEWAY_DATA_DIR=/data \
  -e LIVEAGENT_GATEWAY_MESH_ENABLED=true \
  -e LIVEAGENT_GATEWAY_MESH_URL=nats://host.docker.internal:4222 \
  -v reactorpro-gateway-data:/data \
  ghcr.io/drolu/liveagent-gateway
```

Three things that trip people up:

- **Bind inside the container to `:3000`**, not `127.0.0.1:3000`. A container listening on
  loopback is unreachable through a published port.
- **Mount a volume for the data directory.** Without it, every container replacement mints
  a new mesh identity.
- **`host.docker.internal`** reaches the host on Docker Desktop; on Linux use the bridge
  gateway address or `--network host`.

For secrets, prefer `--env-file` with a `0600` file over `-e`, which exposes the value in
`docker inspect` and in the process table on some setups.

## Kubernetes and Nomad

Two points that matter more than the manifest itself:

- **The identity file must live on a PersistentVolume.** On ephemeral storage every pod
  restart creates a new agent identity. Better still, mount only the `mesh/` subdirectory
  if you want the database to stay ephemeral.
- **Probe `/healthz`** for liveness (unauthenticated, cheap). For readiness, probe an
  authenticated endpoint only if the token is present in the pod — otherwise a healthy
  gateway will be pulled out of rotation by a `401`.

```yaml
livenessProbe:
  httpGet: { path: /healthz, port: 3000 }
readinessProbe:
  httpGet:
    path: /api/status
    port: 3000
    httpHeaders:
      - name: Authorization
        value: Bearer <token>
```

## Reverse proxy

The gateway serves its own web UI and holds long-lived WebSocket connections. A proxy in
front of it must:

1. **Upgrade WebSockets** on `/ws/v2`, `/ws/v2/agent`, `/ws/v2/terminal`.
2. **Not impose a short idle timeout.** The gateway's own HTTP idle timeout is 120s and
   browser sockets are kept alive by a 15s heartbeat; a proxy that closes idle connections
   at 30s will cause constant reconnects.
3. **Not buffer** streaming responses (file downloads, tunnels, chat streams).

nginx:

```nginx
server {
    listen 443 ssl http2;
    server_name reactorpro.example.com;

    ssl_certificate     /etc/letsencrypt/live/reactorpro.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/reactorpro.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        proxy_buffering off;
    }
}
```

Caddy needs almost nothing, since it handles upgrades and long timeouts by default:

```
reactorpro.example.com {
    reverse_proxy 127.0.0.1:3000
}
```

With a proxy terminating TLS, bind the gateway to `127.0.0.1` and leave `-tls-cert` /
`-tls-key` unset.

One caveat: some proxies cap request body size below the gateway's 64 MiB message limit.
If large file uploads fail through the proxy but work locally, that is the cause —
raise `client_max_body_size` in nginx or the equivalent.
