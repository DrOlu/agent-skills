# Platforms - install, run as a service, upgrade, backup

## macOS

1. `bash scripts/install_restate.sh` (auto-detects arm64/x64)
2. Foreground: `~/restate/restate-server-*/restate-server`
3. launchd service `~/Library/LaunchAgents/ng.restate.server.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>ng.restate.server</string>
  <key>ProgramArguments</key><array>
    <string>/Users/YOU/restate/restate-server-aarch64-apple-darwin/restate-server</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>WorkingDirectory</key><string>/Users/YOU/restate</string>
</dict></plist>
```

Load: `launchctl load ~/Library/LaunchAgents/ng.restate.server.plist`

## Linux (Ubuntu/Debian/RHEL, x64 or arm64)

1. `bash scripts/install_restate.sh`
2. systemd unit `/etc/systemd/system/restate-server.service`:

```ini
[Unit]
Description=Restate durable execution server
After=network-online.target

[Service]
User=YOURUSER
WorkingDirectory=/home/YOURUSER/restate
ExecStart=/home/YOURUSER/restate/restate-server-x86_64-unknown-linux-gnu/restate-server
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Enable: `sudo systemctl daemon-reload && sudo systemctl enable --now restate-server`

## Windows

No native server build - use WSL2 (see `scripts/install_restate_windows.ps1`):
WSL2 Ubuntu + systemd=true + the Linux systemd unit, optionally an NSSM
wrapper so Windows starts WSL at boot. Ingress :8080 and UI :9070 are
forwarded to Windows localhost automatically.

## Upgrade

1. Stop the service (systemctl stop / launchctl unload)
2. Back up the server working directory (contains the embedded journal)
3. Install the new binaries (rerun the installer)
4. Start, then `restate invocations list --all` - history must be intact

## Backup

Copy the server working directory while stopped (it holds the embedded
RocksDB journal). For production, snapshot on a schedule; the journal is
the only state that matters - handlers are stateless code.

## Troubleshooting

- `:8080 refused` - server not running; check the service / log
- invocations stuck IN_PROGRESS - handler server (:9090) down; Restate
  retries with backoff and PAUSES on max attempts; fix and `restate
  invocations resume <id>` (or restart the handler and wait)
- port conflicts - set bind addresses in the service file / env
- deployment revision mismatch - re-POST :9070/deployments after editing
  handlers; old invocations keep replaying against their original revision
