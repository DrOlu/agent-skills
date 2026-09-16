# reactorpro-agentd — the headless worker, in full

A single static Go binary that signs into a `reactorpro-gateway` over the same `/ws/v2/agent`
WebSocket the desktop app uses and serves remote chat turns with real tool use, several at
once. From the gateway's point of view it is indistinguishable from a desktop: a row in the
local agent directory, addressed by `target` or `capability`, behind the same gates, tasks,
streaming, webhooks and audit trail. **No gateway, mesh, or protocol change is needed to adopt
it.** Ships alongside the gateway in every release since v1.5.20.

The division of labour it preserves: the gateway stays the policy point (no model keys, ever);
the agentd is an execution point — it holds its **own provider key**, runs a curated sandboxed
tool set, and speaks the v2 wire contract exactly (ClientHello with `CHAT_INGRESS_V1`,
application-layer ping/pong, `chat.submit`/`chat.cancel`, and the reliable chat ingress with
zstd-compressed projections).

## Why not "headless mode of the desktop"?

The desktop's entire runtime — model client, tools, agent loop — lives in a platform WebView,
which cannot run as a boot-time service (WKWebView/WebView2 require a logged-in GUI session),
and a hidden desktop stays serial. The agentd is a purpose-built server worker: parallel,
service-shaped, honestly narrower.

## Install

Binaries are published per release for five targets (pure-Go SQLite: genuinely static,
~10 MB, no runtime dependencies):

| Platform | Asset |
|---|---|
| Linux x86-64 | `reactorpro-agentd-linux-amd64` |
| Linux ARM64 | `reactorpro-agentd-linux-arm64` |
| macOS Intel | `reactorpro-agentd-darwin-amd64` |
| macOS Apple silicon | `reactorpro-agentd-darwin-arm64` |
| Windows x86-64 | `reactorpro-agentd-windows-amd64.exe` |

```bash
BASE=https://github.com/DrOlu/ReactorPro/releases/latest/download
curl -fsSLO "$BASE/reactorpro-agentd-$(uname -s | tr A-Z a-z)-$(uname -m | sed 's/arm64/arm64/;s/x86_64/amd64/')"
curl -fsSLO "$BASE/SHA256SUMS"
sha256sum -c --ignore-missing SHA256SUMS      # macOS: shasum -a 256 -c
install -m 0755 reactorpro-agentd-*-*/usr/local/bin/reactorpro-agentd   # adjust to the downloaded name
```

Or use `../scripts/install-agentd.sh`, which detects the platform, verifies the checksum, and
installs. Pin a version by replacing `latest/download` with `download/v1.5.22`. You can confirm
the server-computed digest without downloading: `gh api repos/DrOlu/ReactorPro/releases/tags/<tag>
--jq '.assets[]|{name,digest}'`.

## Credential and identity

The agentd authenticates to the gateway like a desktop agent. Two options:

1. **Per-agent token (recommended)** — revocable independently of everything else. The agent
   id MUST be the canonical form **`agent-<uuidv4 lowercase>`** (the gateway's rule); anything
   else is refused with *"agent id must be a canonical agent UUID v4"*:

   ```bash
   AGENT_ID="agent-$(uuidgen | tr 'A-Z' 'a-z')"
   curl -s -X POST -H "Authorization: Bearer $GATEWAY_TOKEN" \
        http://127.0.0.1:3000/api/agents/$AGENT_ID/token
   # -> {"agent_id":"agent-…","token":"agt_…"}   — store it; the full token is shown once

   curl -s -X PATCH -H "Authorization: Bearer $GATEWAY_TOKEN" -H 'Content-Type: application/json' \
        -d '{"name":"ReactorPro Agentd (server 1)"}' \
        http://127.0.0.1:3000/api/agents/$AGENT_ID
   # The friendly name is what peers see in the published directory — set it.
   ```

2. **The gateway token** — works, but couples the worker's credential to every other client.

The id is the worker's address inside the site (`target` in invoke input, the `agent` field in
replies). It is NOT a mesh identity — the edge signs everything; the worker never appears on the
bus as itself.

## Configuration

Every flag has an environment-variable twin (`LIVEAGENT_AGENTD_*`); flags win.

| Setting | Flag | Env twin | Default | Notes |
|---|---|---|---|---|
| Gateway link | `-gateway` | `LIVEAGENT_AGENTD_GATEWAY` | `ws://127.0.0.1:3000/ws/v2/agent` | `ws://` or `wss://`; the agent endpoint, not the base URL |
| Agent id | `-agent-id` | `LIVEAGENT_AGENTD_ID` | *(required)* | `agent-<uuidv4>` |
| Token | `-token` | `LIVEAGENT_AGENTD_TOKEN` | *(required)* | gateway or per-agent token |
| Friendly name | `-name` | `LIVEAGENT_AGENTD_NAME` | "ReactorPro Agentd" | shown in the directory |
| Provider base URL | `-provider-url` | `LIVEAGENT_AGENTD_PROVIDER_URL` | *(required)* | OpenAI-compatible `/v1`; the client appends `/chat/completions` |
| Provider key | `-provider-key` | `LIVEAGENT_AGENTD_PROVIDER_KEY` | *(required)* | held by the worker; put it in the env, never the command line |
| Model | `-provider-model` | `LIVEAGENT_AGENTD_PROVIDER_MODEL` | *(required)* | any id the endpoint accepts |
| Completion cap | `-max-tokens` | `LIVEAGENT_AGENTD_MAX_TOKENS` | 4096 | per request; reasoning models need headroom |
| Tool rounds | `-max-rounds` | `LIVEAGENT_AGENTD_MAX_ROUNDS` | 16 | bounds one turn's tool loop |
| Sandbox root | `-workdir` | `LIVEAGENT_AGENTD_WORKDIR` | *(required)* | every file tool + shell cwd confined here |
| Skills library | `-skills-dir` | `LIVEAGENT_AGENTD_SKILLS_DIR` | *(off)* | directory of `<skill>/SKILL.md` collections |
| Parallelism | `-concurrency` | `LIVEAGENT_AGENTD_CONCURRENCY` | 4 | turns at once; extra commands queue |
| Shell tool | `-shell` | `LIVEAGENT_AGENTD_SHELL` | true | `run_command`; set `0` for a read-only worker |
| Fetch tool | `-fetch` | `LIVEAGENT_AGENTD_FETCH` | true | `fetch_url`; GET only, size-capped |
| Command timeout | `-command-timeout` | `LIVEAGENT_AGENTD_COMMAND_TIMEOUT` | 60s | one shell command |
| Provider timeout | `-request-timeout` | `LIVEAGENT_AGENTD_REQUEST_TIMEOUT` | 120s | one provider call |

Run `reactorpro-agentd -help` for the authoritative list.

### The tools it offers the model

`read_file`, `write_file`, `list_dir` (always) · `run_command` (shell, flag) · `fetch_url`
(flag) · `read_skill`, `read_skill_file` (when `-skills-dir` is set). File paths are refused if
they escape the workdir — including via `..`, absolute paths, or symlinks pointing outside; the
refusal message tells the model the rule so it can retry correctly. Tool outputs are capped
(64 KiB per tool result; fetches 256 KiB) with an explicit truncation note.

### The skills library

`-skills-dir` points at a directory of `<name>/SKILL.md` collections (the same layout as
`~/.agents/skills`). At start-up the worker scans it, lists every skill (frontmatter name +
description, capped) in each turn's system prompt, and serves the files read-only through
`read_skill {skill}` and `read_skill_file {skill, path}` — only scanned names are servable, and
reads are confined to that skill's directory. Skills are exposure, not execution: anything a
skill instructs the model to run goes through the sandboxed shell like any other command.

### Provider, API key and model — the parameterised form

Given a provider base URL, an API key and a model, a worker is three settings:

```bash
LIVEAGENT_AGENTD_GATEWAY=ws://gw.internal:3000/ws/v2/agent \
LIVEAGENT_AGENTD_ID=agent-<uuidv4> \
LIVEAGENT_AGENTD_TOKEN=agt_… \
LIVEAGENT_AGENTD_PROVIDER_URL=https://api.superagent.ng/v1 \
LIVEAGENT_AGENTD_PROVIDER_KEY=sk-or-v1-… \
LIVEAGENT_AGENTD_PROVIDER_MODEL=z-ai/glm-5.3 \
LIVEAGENT_AGENTD_WORKDIR=/srv/agentd-work \
LIVEAGENT_AGENTD_SKILLS_DIR=/opt/agent-skills \
reactorpro-agentd
```

Any OpenAI-compatible `/v1` endpoint works (OpenAI, OpenRouter-style proxies, GLM, local
vLLM/ollama gateways). The key lives in the environment of the service, read from a `0600` file
— same rule as the gateway token.

## Run it as a service

### Linux — systemd

```ini
# /etc/systemd/system/reactorpro-agentd.service
[Unit]
Description=ReactorPro Agentd (headless worker)
After=network-online.target reactorpro-gateway.service
Wants=network-online.target

[Service]
User=reactorpro
EnvironmentFile=/etc/reactorpro-agentd.env
ExecStart=/usr/local/bin/reactorpro-agentd
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
install -d -m 0750 -o reactorpro -g reactorpro /srv/agentd-work
cat > /etc/reactorpro-agentd.env <<'EOF'
LIVEAGENT_AGENTD_GATEWAY=ws://127.0.0.1:3000/ws/v2/agent
LIVEAGENT_AGENTD_ID=agent-0f0f0f0f-0f0f-4f0f-8f0f-0f0f0f0f0f0f
LIVEAGENT_AGENTD_TOKEN=agt_…
LIVEAGENT_AGENTD_NAME=ReactorPro Agentd (server 1)
LIVEAGENT_AGENTD_PROVIDER_URL=https://api.openai.com/v1
LIVEAGENT_AGENTD_PROVIDER_KEY=sk-…
LIVEAGENT_AGENTD_PROVIDER_MODEL=gpt-5
LIVEAGENT_AGENTD_WORKDIR=/srv/agentd-work
EOF
chmod 0600 /etc/reactorpro-agentd.env
systemctl daemon-reload && systemctl enable --now reactorpro-agentd
journalctl -u reactorpro-agentd -f        # expect: "agentd signed into the gateway"
```

### macOS — launchd

Same shape as the gateway's plist (`ng.reactorpro.gateway`): a `~/Library/LaunchAgents/`
plist with `RunAtLoad` + `KeepAlive` whose ProgramArguments is a small launcher script that
sources a `0600` env file and `exec`s the binary. See `references/service-managers.md` and the
gateway's plist template — only the names and env keys change.

### Docker

One container per worker, or `docker run` beside the gateway on the same network. Mount the
workdir (and skills dir) as volumes, and pass the settings as `-e`. The agentd only needs to
reach the gateway — point `-gateway` at the gateway's container name.

## Behaviour notes an operator should know

- **Honest lifecycle**: exactly one terminal record per turn no matter the path; cancel frees
  the worker immediately; a dropped gateway link cancels local runs (the gateway fails them at
  their budget); reconnect is bounded exponential backoff. A restart mid-run = the run dies;
  peers retry with one call.
- **Streaming by construction**: each checkpoint the worker emits is a content snapshot, so
  mesh task chunks, state events and webhooks all work against it unchanged.
- **Browser surface**: switching the web UI to the worker does not hang — desktop-surface
  requests (`settings_get`, providers, fs, …) answer instantly with a typed 501 ("an executor,
  not a desktop"), and `history_list` returns an honest empty list. Chat works on the live
  conversation view; persisted history does not exist.
- **One run per conversation**, same rule as the desktop; the queue is per-worker and FIFO
  beyond `-concurrency`.
- **Sandbox honesty**: the shell tool is a real shell with the workdir as cwd — a command can
  still address absolute paths outside the workdir, same as any shell on that host. If that
  matters, run the worker as a dedicated low-privilege user/container; the file tools are
  strictly confined, the shell tool is shell.

## Verify, upgrade, limits

**Verify** (beyond the SKILL.md quick checks): `journalctl` shows `"agentd signed into the
gateway"` with a session id; `/api/status` lists the agent id with `agent_version` of the
agentd (a `0.1.x` line, distinct from desktop `1.5.x`); a mesh dispatch returns the model's
answer inside `timeoutMs`.

**Upgrade**: replace the binary, restart the service, confirm the sign-in line. The wire
contract is the gateway's v2 protocol — an agentd of any release works with a gateway of any
release; upgrade them independently.

**Known limits (state plainly before promising them)**: no persisted conversation history;
chunks arrive per tool round, not per token; a link drop mid-run kills the run (no resume);
one OpenAI-compatible provider shape; the shell tool is a real shell.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Start-up refusal "an agent id is required" / "a provider base URL and model are required" | `Validate()` refusing an unrunnable config — fill `-agent-id`, `-provider-url`, `-model`, `-workdir` |
| "handshake refused: unauthorized" | Bad token; per-agent tokens must be issued for the exact `agent-<uuid>` id |
| Token issuance refused: "agent id must be a canonical agent UUID v4" | The id needs the `agent-` prefix and a lowercase v4 UUID |
| Gateway link drops, reconnect storms | `-gateway` points at the wrong path (it must be `…/ws/v2/agent`) or the gateway is restarting |
| Turns fail with "provider request: …" | Wrong `-provider-url` (must include `/v1`), bad key, or the model id is rejected — curl the endpoint directly to see which |
| The web UI hangs on the worker | It should not since v1.5.22 — upgrade the agentd; the typed 501 answers arrive in milliseconds |
| Peers do not see the worker in `describe` | The **gateway** publishes the directory — upgrade the gateway to ≥ v1.5.24 and allow one heartbeat (~30s) |