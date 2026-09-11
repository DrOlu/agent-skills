# Deploying and operating a gateway

LiveAgent provides **no hosted gateway**. Operators self-host.

## Docker (recommended)

```bash
docker run -d \
  --name liveagent-gateway \
  --restart unless-stopped \
  -p 3000:8080 \
  -v liveagent-gateway-data:/var/lib/liveagent \
  -e LIVEAGENT_GATEWAY_TOKEN=$(openssl rand -hex 32) \
  ghcr.io/stack-cairn/liveagent-gateway:latest
```

Inside the image: the binary is at `/usr/local/bin/liveagent-gateway` and is the `ENTRYPOINT`; `PORT=8080`; data dir `/var/lib/liveagent`; it runs as non-root **uid 10001**.

**Mount the volume.** It holds the agent-credential SQLite DB (`gateway.db`). Recreating the container without it destroys every issued credential and machine name.

### Upgrading

Pull → remove → recreate **with the same arguments**, or credentials and configuration drift:

```bash
docker pull ghcr.io/stack-cairn/liveagent-gateway:latest \
  && docker rm -f liveagent-gateway \
  && docker run -d --name liveagent-gateway --restart unless-stopped \
       -p 3000:8080 -v liveagent-gateway-data:/var/lib/liveagent \
       --env-file ~/.liveagent-gateway/gateway.env \
       ghcr.io/stack-cairn/liveagent-gateway:latest
```

Prefer `--env-file` over `-e` so the token stays out of the process list. It remains visible via `docker inspect` — inherent to the image's env-var design.

### Pin versions

Match the gateway to the desktop app version where possible; both ends speak protocol v2, and a version mismatch is a real compatibility risk.

```bash
T=$(curl -s "https://ghcr.io/token?service=ghcr.io&scope=repository:stack-cairn/liveagent-gateway:pull" \
    | python3 -c 'import json,sys;print(json.load(sys.stdin)["token"])')
curl -s -H "Authorization: Bearer $T" \
  https://ghcr.io/v2/stack-cairn/liveagent-gateway/tags/list
```

## Reverse proxy (Nginx)

All traffic rides one port, and WebSocket upgrades occur on several paths (`/ws/v2`, `/ws/v2/agent`, `/ws/v2/terminal`, tunnels under `/t/`). Enable the upgrade on the **whole vhost**:

```nginx
location / {
    proxy_pass http://127.0.0.1:3000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header Authorization $http_authorization;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
    proxy_buffering off;
}
```

`Host` and `X-Forwarded-Proto` are **required** — the gateway's same-origin check compares the browser `Origin` against them. Set `client_max_body_size` (~`100m`) for uploads, and `listen 443 ssl;`.

When behind a proxy, configure the desktop with the **HTTPS URL and port 443**.

## Runtime configuration

| Variable | Default | Purpose |
|---|---|---|
| `LIVEAGENT_GATEWAY_TOKEN` | — | **Required.** Browser, REST, and agent link |
| `PORT` | 8080 | Listen port |
| `LIVEAGENT_GATEWAY_AGENT_DB` | auto | Per-agent credential DB path |
| `LIVEAGENT_GATEWAY_DATA_DIR` | `/var/lib/liveagent` | Parent dir for the auto DB |
| `LIVEAGENT_GATEWAY_CHAT_PREPARE_TIMEOUT` | 2s | Native Ping/Pong probe |
| `LIVEAGENT_GATEWAY_CHAT_DELIVERY_TIMEOUT` | 5s | Deliver an accepted command |
| `LIVEAGENT_GATEWAY_CHAT_START_TIMEOUT` | 5s | First watchdog stage |
| `LIVEAGENT_GATEWAY_CHAT_RENDER_START_TIMEOUT` | 10s | Additional render window |
| `LIVEAGENT_GATEWAY_MAX_MESSAGE_BYTES` | 64 MiB | Agent-link message cap |
| `LIVEAGENT_GATEWAY_MAX_{AGENT,BROWSER,TERMINAL}_CONNECTIONS` | 256 / 128 / 512 | Concurrency caps |
| `LIVEAGENT_GATEWAY_WS_HEARTBEAT_PERIOD` | 15s | Browser ping interval |
| `LIVEAGENT_GATEWAY_TLS_CERT` / `_TLS_KEY` | — | Direct TLS (else terminate at the proxy) |

Flags mirror these (`-token`, `-agent-db`, `-http-addr`, `-tls-cert`, `-tls-key`, …). Removed v1/gRPC flags (`-grpc-addr`, `-command-queue-timeout`) now fail loudly rather than being silently ignored.

## Connecting a desktop

In the desktop app: **Settings → Remote**, then set the Gateway URL, port (`443` behind a proxy), and the access token. The agent id appears at **Settings → Remote → Agent ID** and auto-registers on first connect.

Remote settings persist in `~/.liveagent/config.sqlite` (domain `remote`); the token is **redacted** before syncing to the WebUI.

## Health checks

```bash
curl -sS "$LAG_GW/healthz"                                        # {"ok":true}
curl -sS -H "Authorization: Bearer $LAG_TOKEN" "$LAG_GW/api/status"
```

Startup logs read: *agent registry db ready* → *agent authentication accepts gateway token or per-agent token* → *HTTP listening*.

## Hardening

- Prefer **per-agent credentials** over sharing the gateway token; that caps a leak to a single machine.
- Terminate TLS at the proxy; do not expose plain HTTP beyond localhost.
- Anyone holding the gateway token can drive a desktop that runs shell commands and reads files. Treat it like an SSH private key.
- Rotate a credential if it was ever pasted somewhere untrusted — and warn the operator first, since rotation disconnects that machine.
- Back up the data volume before upgrades.
