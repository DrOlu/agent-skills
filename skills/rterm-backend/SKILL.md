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
| `settings.json` | connections (ssh/winrm/serial), automation (groups/scripts/schedules/templates/playbooks), model profiles (incl. `reviewModelId`/`reviewMode`), command policy, gateway policy |
| `gyshell-history.sqlite` | chat + UI history |
| `gyshell-agent-runs.sqlite` | agent run ledger (audit + token cost) |
| `gyshell-changes.sqlite` | change ledger (MOP records + step events) |
| `session-logs/` | recorded terminal sessions (plain files) |
| `skills/` | agent skills |
| `plugins/` | user-installed plugins (auto-discovered on startup; the 6 official plugins ship in the npm package / desktop app bundle) |
| `policy.yaml` | optional custom AGT policy document (overrides the built-in default policy) |
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

## 6. Observability & SRE features (v2.0.0–v2.3.1)

The backend boots with a full **observability** stack wired in (`createObservability`), fed live by monitor snapshots. All of it is callable over the gateway (see the `rterm-gateway` skill).

### SRE core
- **MetricsLedger** — time-series store for resource snapshots (cpu/mem/disk/load/net/gpu) per host, with trend slope + **days-to-threshold forecasting** ("disk full in N days").
- **UptimeWatchdog** — liveness probes (tcp/ssh/http/command) per host, up/degraded/down, with state transitions firing alerts.
- **SloService** — SLO/SLI definitions, error budget, **burn rate**, fast-burn alerting.
- **AlertService** — alertmanager-style routing: grouping, dedupe, silences, severity channels.
- **IncidentLedger** — auto-incidents with timelines, AI **RCA**, **postmortems**, runbook links.
- **GoldenSignals** — saturation/traffic/latency/errors per host + capacity forecast.
- **SyntheticChecks** — blackbox probes feeding the SLO SLI + golden latency/error.
- **DriftDetector** — template-vs-live config diff + MOP auto-remediation.

### APM / DEM / Infra / ETW
- **SpanLedger (APM)** — OTLP distributed-trace store + analysis (per-service p50/95/99, error rate, slowest traces, bottleneck services).
- **RumLedger (DEM)** — Core Web Vitals (LCP/INP/CLS/TTFB) per page + error rate, slowest/poor pages.
- **InfraMonitor (k8s/cloud)** — cluster health (running/notReady/CrashLoop/restarts/nodes + cpu/mem % of limit), unhealthy instances.
- **EtwService (Windows)** — built-in ETW diagnostics (network/file/registry/process providers, logman sessions, Get-WinEvent/Get-Counter) — agentless, no install.

### Predictive + behavioral + evals
- **AnomalyDetector** — z-score / robust z-score (median±MAD) anomaly detection over metric series.
- **EarlyWarningService** — predictive failure alerts (trend forecast + anomaly) + optional MOP auto-remediation.
- **BehaviorLedger** — UEBA-style baselines (runs/day, tokens/run, error rate, models) + deviations (run-spike, token-blowout, error-spike, unusual-model).
- **EvalHarness** — embedded evals measuring the agent's **accuracy, tool selection, safety/policy, determinism/replay** with an aggregate reliability report.

### Notifications (Slack / Teams / SMTP / Telegram)
Wire alert channels into the AlertService with vaulted webhook URLs / SMTP creds (rich, severity-colored payloads):

```bash
# via the gateway (rterm-gateway skill) — add a Slack channel
# (see examples/notify-channels.mjs)
```

### Unified live dashboard
A single `dashboard:state` object aggregates **every** ledger (fleet health, SLO board, uptime map, incident feed, APM bottleneck+slowest, DEM slowest/poor, k8s clusters, capacity forecast) — broadcast over the gateway for rich, live, cross-linked dashboards. A `renderDashboardHtml` renderer produces a **browser-viewable HTML dashboard** from that state (Aurora-themed, auto-refreshing) — serve it over HTTP to view the live dashboard in any browser.

### dagu workflows (v2.4.0+)
Run declarative [dagu](https://github.com/dagucloud/dagu) YAML DAG workflows natively on RTerm's orchestrated playbook engine — **no dagu server required**. The `daguParser` compiles dagu YAML into a playbook:
- **Steps** — `id`/`name`, `run`/`command`/`cmd`/`script`/`call` (all forms) → step commands.
- **Dependencies** — `depends` (string or array) → `dependsOn` (fan-out/fan-in DAG waves).
- **Failure handling** — `continue_on` → `onError: continue`; `retry_policy` noted.
- **Guards** — `preconditions` → a `desiredState` skip-when-satisfied guard.
- **Runbook params** — `params` (string or object with `default`) → playbook params with defaults.

Paste a dagu YAML workflow to the agent ("run this dagu workflow") or compile it via `parseDaguYaml` and run the resulting playbook with `run_playbook` — it executes on RTerm's orchestrated DAG runner across your hosts with validation and rollback.

### AWS APerf deep-dive (v2.6.0+)
Deploy the [AWS APerf](https://github.com/aws/aperf) CLI to any Linux host via SSH, record deep system performance metrics (CPU, memory, disk, network, PMU counters, processes, hotspot data), generate the aperf analysis report, and parse the findings into structured results that feed the metrics ledger + agent RCA. Combines aperf's deep profiling with RTerm's agent reasoning.

Ask the agent: *"Run an APerf deep-dive on web-01 and report the top performance issues"* — the agent installs aperf on the host (if needed), records for the sampling period, parses the report, and returns findings with severity thresholds (critical ≥90%, warning ≥75%, process ≥50% CPU).

### Plugin system (v2.5.0+)
Anyone can develop a custom plugin and have it auto-integrate. A plugin is a folder with a `plugin.json` manifest (name, version, entry, tools, triggers, panels, permissions) and an `index.mjs` entry module exporting `register(ctx)`. The `PluginRegistry` discovers plugins in:
1. `~/.gybackend-data/plugins` (user-installed)
2. `./plugins` (repo/dev)
3. `{bundle}/../plugins` (npm package)
4. `{resourcesPath}/plugins` (desktop app)

The backend **ships with 6 official plugins** out of the box (21 tools, 10 triggers, 6 panels):

| Plugin | What it does |
|---|---|
| **patch-manager** | Autonomous patch management — `patch_status`/`patch_plan`/`patch_apply` tools, `patch_failure`/`patch_completion` triggers, patch-compliance dashboard. Supports yum/apt/Windows Update. |
| **request-router** | Automated request handling — `submit_request`/`approve_request`/`list_requests`/`request_status` tools. Risk classification (low/med/high) → auto-approve/queue/MOP routing. |
| **sop-assistant** | IAM Knowledge & SOP Assistant — `sop_search`/`sop_get`/`sop_execute`/`iam_lookup` tools. 8 built-in SOPs (restart-service, disk-cleanup, reset-password, database-failover, ssl-cert-renewal, user-offboarding, backup-restore, incident-response) + 4 IAM policies. |
| **iam-connector** | IAM integration — `iam_user_info`/`iam_user_groups`/`iam_disable_user`/`iam_access_review` tools. Privileged access identification, access review. Linux (id/groups/usermod) + Windows (Get-LocalUser). |
| **fraudops** | FraudOps operational layer — `fraudops_pipeline_status`/`fraudops_str_assign`/`fraudops_str_status`/`fraudops_decision_summary` tools. Flink/NATS/Kafka health, STR workflow (7-day CBN deadline), decision summary. |
| **netdata-rterm** | Netdata integration — `netdata_alert_summary`/`netdata_correlate` tools. Ingests Netdata Cloud alert webhooks, correlates with RTerm metrics/incidents for RCA. Triggers for auto-remediation + MOP changes. |

### Audit trail + evidence sealing (v2.7.1)
Hash-chained, tamper-evident audit ledger — every audit-relevant event (agent runs, command evaluations, approvals, MOP changes, playbook steps, trigger firings, alert ingestions) is appended with the SHA-256 hash of the previous record. Any tampering breaks the chain and is detectable via `verify()`. The **evidence sealer** computes a Merkle-tree root over records → sealed, independently-verifiable evidence bundles (KLA audit framework domain 11). 18 event kinds recorded.

### Monitor diagnostics (v2.7.6)
`monitorStatus` diagnostic — reports exactly why monitor stats aren't displaying per terminal: publisher wired? session exists? collection stuck in-flight? terminal connected? platform detected? last-collect time? Diagnoses: `terminal_not_connected`, `no_monitor_session`, `collection_stuck_in_flight`, `never_collected`, `stale_collection (>30s)`, `publisher_not_wired`.

Ask the agent: *"Run monitor status diagnostics"* — instantly shows which terminals aren't collecting and why.

### AGT policy engine (v2.7.7)
Microsoft AGT-style policy engine — evaluates every consequential action against a YAML policy before execution. Decisions: `allow` / `deny` / `escalate` (route to approval). Features: glob-style action patterns (`"read"` matches `"read /etc/passwd"`), target wildcards (`prod-*`), first-match-wins, case-insensitive matching, agent identity + sponsoring principal for zero-trust. Built-in default policy: allow read/status/list; deny delete/drop/format; escalate restart/patch/deploy on `prod-*`. Drop a custom `policy.yaml` in the data dir to override.

### Review model / maker-checker (v2.7.8)
The **review model** (a second LLM, the "checker") independently verifies the action model's (the "maker's") output on **5 dimensions**: correctness, completeness, safety, compliance, and accuracy.

- **Verdicts:** `approved` / `needs_revision` / `escalate`.
- **Modes:** `strict` (block on any issue), `advisory` (flag but allow), `auto-approve` (skip review for low-risk actions).
- **Fast output mode:** if no `reviewModelId` is set in the model profile, reviews are skipped entirely (zero added latency).

Configure in `settings.json` → `models.profiles[].reviewModelId` + `reviewMode` — or in the desktop Settings UI (v2.7.9+).

### v2.9.x platform capabilities

v2.9.0 added 9 backend modules; **v2.9.2 exposed them as 41 `observability:*` gateway RPC methods + 9 agent tools** (see the `rterm-gateway` skill §4b); **v2.9.3 made the tools visible in the Tools section**. All are wired into `createObservability` and live on a stock install.

| Capability | Module | How you use it |
|---|---|---|
| **Prometheus /metrics + OTel push** | `sre/prometheusExporter`, `sre/otelExporter` | Scrape `observability:metricsPrometheus`, or set `OTEL_EXPORTER_OTLP_ENDPOINT` to push OTLP to a collector |
| **Secrets vault** | `secrets/secretsVault` | AES-256-GCM store; set `RTERM_SECRETS_MASTER_KEY` at boot; `observability:secrets*` (metadata only, never values) |
| **Incident escalation & on-call** | `oncall/escalationService` | Multi-level policies, ack deadlines, paging via `observability:oncall*` |
| **AI cost & budgets** | `cost/costBudgetService` | Per-model USD attribution + warn/throttle/deny budgets via `observability:cost*` |
| **Live dashboard hub** | `liveui/liveDashboardHub` | Push-based multi-client dashboard via `observability:liveDashboard*` |
| **Session recording/replay** | `recording/sessionRecorder` | asciinema `.cast` v2 via `observability:recording*` |
| **GitOps** | `gitops/gitOpsService` | Desired-state manifest, drift, reconcile via `observability:gitops*` |
| **Playbook versioning + lint** | `automation/playbookVersioning` | History/diff/rollback + static lint via `observability:playbook*` |
| **Cloud inventory (AWS/GCP/Azure)** | `cloud/cloudInventory` | Normalized instance inventory via `observability:cloud*` (inject fetchers) |

Agent tools (visible in the Tools section since v2.9.3): `get_metrics`, `manage_secret`, `manage_oncall`, `get_cost`, `manage_recording`, `manage_gitops`, `manage_playbook_version`, `get_cloud_inventory`, `get_live_dashboard`. Ask the agent: "add this API key to the vault", "show my AI spend today", "page the on-call", "lint this playbook", "list my AWS instances".

**v2.9.5 — APM/DEM/Infra/ETW ingestion.** The observability ledgers are now genuinely fed out of the box via `observability:apmIngestSpans` (OTLP spans → trace store), `observability:demIngestBeacon` (Core Web Vitals RUM beacons → per-page p75), `observability:infraCollect` (k8s cluster health from kubectl), and `observability:etwStartTrace/etwStopTrace/etwParse` (Windows ETW diagnostics) — plus the matching agent tools `ingest_apm_spans`/`get_apm_summary`, `ingest_dem_beacon`/`get_dem_summary`, `collect_infra`, `manage_etw`.

**New env vars:** `OTEL_EXPORTER_OTLP_ENDPOINT` / `RTERM_OTLP_METRICS_ENDPOINT` (OTel push), `RTERM_SECRETS_MASTER_KEY` (unlock the secrets vault).

---

## 7. Manage connections, automation & schedules

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
2. **Scheduled patch/AV** — cron task runs `Update-MpSignature` across a Windows fleet weekly; versions recorded to the run ledger. Or use the **patch-manager plugin**: `patch_status` → `patch_plan` → MOP approve → `patch_apply`, with a fleet-wide compliance dashboard.
3. **Multi-vendor change** — Jinja-render a Cisco BGP config, apply via `algorithmsPreset=cisco` + `vt100`, then update an AWS SG — with validation + rollback.
4. **Sub-agent** — an orchestrator LLM delegates ops tasks to RTerm's agent and reads transcripts.
5. **Audit** — run ledger + change ledger + session logs + **hash-chained audit ledger (v2.7.1)** + **evidence sealing (Merkle tree)** = complete, tamper-evident, independently-verifiable command-and-output trail.
6. **Autonomous patching** — patch-manager plugin discovers patches, builds deployment plans, executes with MOP approval, alerts on completion/failure, reports fleet compliance.
7. **Request handling** — request-router plugin receives operational requests, classifies risk, routes for approval (auto-approve/queue/MOP), executes end-to-end, audits every step.
8. **SOP-guided ops** — sop-assistant plugin answers "how do I X?" with relevant SOPs and executes them step-by-step with variable substitution + confirmation.
9. **IAM governance** — iam-connector plugin reviews user access, identifies privileged accounts, disables users (with approval), runs access reviews.
10. **FraudOps** — fraudops plugin monitors the fraud detection pipeline (Flink/NATS/Kafka), manages STR workflow with CBN deadlines, summarizes decisions.
11. **Performance deep-dive** — AWS APerf integration deploys aperf to any Linux host, records CPU/PMU/flamegraph metrics, parses findings into the metrics ledger + agent RCA.
12. **Governance** — AGT policy engine evaluates every consequential action against a YAML policy (allow/deny/escalate); the **review model (maker/checker)** independently verifies the action model's output on 5 dimensions (correctness, completeness, safety, compliance, accuracy).

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
