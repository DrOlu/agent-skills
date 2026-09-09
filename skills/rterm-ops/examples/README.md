# rterm-ops examples (Windows + Unix)

Run **ensure** first so `rterm-cli` and `gybackend` exist.

## Bootstrap (pick one)

**Any OS (preferred):**

```bash
node scripts/ensure-rterm.mjs
```

Windows cmd:

```bat
node "%USERPROFILE%\.pi\agent\skills\rterm-ops\scripts\ensure-rterm.mjs"
```

Windows PowerShell:

```powershell
node "$env:USERPROFILE\.pi\agent\skills\rterm-ops\scripts\ensure-rterm.mjs"
```

Unix bash fallback:

```bash
bash scripts/ensure-rterm.sh
```

Install only, do not start daemon:

Unix: `ENSURE_RTERM_START=0 node scripts/ensure-rterm.mjs`

Windows cmd:

```bat
set ENSURE_RTERM_START=0
node scripts\ensure-rterm.mjs
```

## Show config (never prints apiKey)

```bash
node scripts/show-config.mjs
```

## Set API key from environment

Unix:

```bash
export OPENROUTER_API_KEY='…'
node scripts/set-api-key.mjs --model moonshotai/kimi-k3 --base-url https://openrouter.ai/api/v1
```

Windows cmd:

```bat
set OPENROUTER_API_KEY=your-key-here
node scripts\set-api-key.mjs --model moonshotai/kimi-k3 --base-url https://openrouter.ai/api/v1
```

Windows PowerShell:

```powershell
$env:OPENROUTER_API_KEY = 'your-key-here'
node scripts\set-api-key.mjs --model moonshotai/kimi-k3 --base-url https://openrouter.ai/api/v1
```

## Ping / version / methods

```bash
rterm ping
rterm version
rterm methods --category terminal
```

Windows: `rterm-cli ping` if `rterm` is not on PATH.

## Open a saved connection and run a command

```bash
rterm connections
rterm open CORP-DC1
rterm run CORP-DC1 hostname
```

WinRM/PSRP: command/response only. Do not start vim.

## Unattended agent (CyberAgent ticket)

```bash
rterm call gateway:createSession "{}"
```

Then use the session id from JSON with `agent:startTask`. Do **not** use `rterm chat` on tickets.

## HTTP health (v3.7.7+)

```bash
curl -s http://127.0.0.1:17888/api/v1/health
```

Windows without curl:

```powershell
Invoke-RestMethod http://127.0.0.1:17888/api/v1/health
```

## Foolproof checklist

1. Node 18+ (`node -v`)
2. `node scripts/ensure-rterm.mjs` exits 0
3. `node scripts/show-config.mjs` shows `hasApiKey: true` and a non-empty `model`
4. If not, set env key and run `set-api-key.mjs`
5. For Pi/CyberAgent: `commandPolicyMode` = `smart` (SKILL.md §1b)
6. Then `rterm open` / `rterm run` / `rterm call`
