# HTTP API

Base: `$LAG_GW` (e.g. `http://localhost:3000`). Responses are JSON unless noted.

## Authentication

```
Authorization: Bearer $LAG_TOKEN
```

`/healthz` is the only unauthenticated endpoint. Everything else returns **401** without a valid token.

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/healthz` | none | Liveness — returns `{"ok":true}` |
| GET | `/api/status` | token | Agent online states + `protocol_usage` counters |
| GET | `/api/agents` | token | Paged agent directory (admin) |
| POST | `/api/agents/{id}/token` | token | Issue or rotate a per-agent credential |
| PATCH | `/api/agents/{id}` | token | Set or clear the agent's display name |
| DELETE | `/api/agents/{id}` | token | Delete record + credential, drop live session |
| POST | `/api/files/import` | token | Upload readable files (multipart) |
| GET | `/api/public/history-shares/{token}` | public token | Read-only shared transcript |
| GET | `/image-proxy` | varies | Proxied image with URL safety checks |
| GET | `/` | none | Embedded WebUI (SPA) |

## Directory pagination

`GET /api/agents?page=1&page_size=50&status=all|online|offline`

Defaults: `page=1`, `page_size=50`, **max 200**.

```json
{ "agents": [], "has_more": false, "page": 1, "page_size": 50, "total": 0 }
```

Each entry carries `agent_id`, optional `name`, `online`, and timestamps. Agents register automatically the first time they connect with **either** a gateway token or a per-agent token.

## Credential administration

**Issue / rotate** — the plaintext is returned **once**:

```bash
curl -sS -X POST "$LAG_GW/api/agents/$LAG_AGENT/token" \
  -H "Authorization: Bearer $LAG_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"office-pc"}'
```

Rotating **immediately disconnects** the current session; the old credential cannot reconnect. The new credential is reusable for that agent indefinitely.

**Rename** (`name` may be empty to clear):

```bash
curl -sS -X PATCH "$LAG_GW/api/agents/$LAG_AGENT" \
  -H "Authorization: Bearer $LAG_TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"office-pc"}'
```

**Delete** (removes the record, the credential, and drops the live session):

```bash
curl -sS -X DELETE "$LAG_GW/api/agents/$LAG_AGENT" \
  -H "Authorization: Bearer $LAG_TOKEN"
```

## File upload

```bash
curl -sS -X POST "$LAG_GW/api/files/import" \
  -H "Authorization: Bearer $LAG_TOKEN" \
  -F "files=@./report.pdf" -F "agent_id=$LAG_AGENT"
```

Flow: the gateway reads the bytes → registers a request stream → sends `UploadReadableFilesRequest` to the desktop → the desktop writes to `~/.liveagent/uploads/<batch>/` (outside the workspace) → returns an uploaded/skipped list. The gateway never writes to an arbitrary local path itself.

Upload is **not** available through the WebSocket pass-through — use HTTP multipart for files.

## Public shares

The desktop resolves the share token; the gateway maps the returned error code to HTTP status:

| Desktop code | HTTP | Meaning |
|---|---|---|
| 400 | Bad Request | Empty or malformed share token |
| 404 | Not Found | Share missing, disabled, or conversation gone |
| other | Bad Gateway | Desktop-side failure |

Sharing is **read-only** and can redact tool content.

## PowerShell equivalents

```powershell
$H = @{ Authorization = "Bearer $env:LAG_TOKEN" }
Invoke-RestMethod "$env:LAG_GW/healthz"
Invoke-RestMethod "$env:LAG_GW/api/status" -Headers $H
Invoke-RestMethod "$env:LAG_GW/api/agents?page=1&page_size=50" -Headers $H
Invoke-RestMethod "$env:LAG_GW/api/agents/$env:LAG_AGENT/token" -Method Post `
  -Headers ($H + @{'Content-Type'='application/json'}) -Body '{"name":"office-pc"}'
```

## Notes

- LiveAgent provides **no hosted gateway**; operators self-deploy. See `deployment.md`.
- Credentials and names persist in the gateway's SQLite DB. A container recreated **without its data volume** loses every issued credential.
