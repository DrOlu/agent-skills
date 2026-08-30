#!/usr/bin/env bash
# agentstate — one agent's config on this box: versions, models, env-var NAMES.
# Read-only. Env var VALUES are never read — names only, for key-presence.
# Emits ONE JSON object.
# Engine injects: $Track, $SinceHours, $Limit

now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
host=$(hostname)

# --- env var NAMES that signal agent presence (never values) ---
ENVN="ANTHROPIC_API_KEY OPENAI_API_KEY OPENROUTER_API_KEY GROQ_API_KEY \
MISTRAL_API_KEY DEEPSEEK_API_KEY TOGETHER_API_KEY XAI_API_KEY GOOGLE_API_KEY \
CLAUDE_CODE OPENCODE AIDER CURSOR GOOSE OLLAMA_HOST LMSTUDIO \
AGENT_SETTINGS RTERM_SECRETS_MASTER_KEY"
found=""
for n in $ENVN; do
  if [ -n "$(printenv "$n" 2>/dev/null)" ]; then
    found="$found$n;"
  fi
done

# --- claude config (names only, no oauth tokens) ---
cc=""
if [ -f "$HOME/.claude.json" ]; then
  cc=$(python3 -c "
import json
try:
    d=json.load(open('$HOME/.claude.json'))
    print('primaryModel=%s; mcp=%d; hasOAuth=%s' % (d.get('primaryModel'), len(d.get('mcpServers') or {}), bool(d.get('oauthAccount'))))
except: print('parse-error')" 2>/dev/null)
fi

# --- opencode config ---
oc=""
for p in "$HOME/.opencode.json" "$HOME/.config/opencode/opencode.json"; do
  [ -f "$p" ] && oc="config at $p" && break
done

# --- versions (cheap, capped) ---
ver=""
for cmd in claude opencode ollama aider cursor-agent; do
  v=$($cmd --version 2>/dev/null | head -1)
  [ -n "$v" ] && ver="$ver$cmd=$v;"
done

# --- skills present (count only) ---
nskills=0
[ -d "$HOME/.agents/skills" ] && nskills=$(ls "$HOME/.agents/skills" 2>/dev/null | wc -l | tr -d ' ')

printf '{"skill":"agentstate","host":"%s","utc":"%s","env_names":"%s","claude_config":"%s","opencode_config":"%s","versions":"%s","n_skills":%s}\n' \
  "$host" "$now" \
  "$(echo "$found" | sed 's/"/\\"/g' | cut -c1-300)" \
  "$(echo "$cc" | sed 's/"/\\"/g' | cut -c1-200)" \
  "$(echo "$oc" | sed 's/"/\\"/g' | cut -c1-120)" \
  "$(echo "$ver" | sed 's/"/\\"/g' | cut -c1-300)" \
  "${nskills:-0}"