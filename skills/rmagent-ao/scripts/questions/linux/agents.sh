#!/usr/bin/env bash
# agents — the agent census. Find every agent / agent harness / model server
# on this box by fusing four probes: process, network, filesystem, packages.
# Read-only. Emits ONE JSON object, capped by $Limit.
# Engine injects: $Track, $SinceHours, $Limit

now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
host=$(hostname)
# Limit=0 would mean head -0 = empty; clamp to at least 1
lim=${Limit:-50}; [ "$lim" -lt 1 ] && lim=1

# --- known agent process names ---
# NOTE: keywords must be specific enough to avoid FPs. Removed: "roo" (matches
# every root-owned process), "amp" (matches AMPDevices.framework), "gpt" (too
# short), "jan" (matches January), "continue" (common word), "llama" (generic).
# Kept only names specific enough that a match is almost certainly an agent.
KNOWN="claude-code opencode aider cursor-agent goose codex copilot \\
cline windsurf kilocode crush gemini-cli ollama lmstudio llamafile \\
vllm sglang anythingllm open-webui gpt4all koboldcpp \\
autogen crewai langchain llamaindex semantic-kernel agentgpt \\
superagent cyberagent rterm gybackend neuralos"

# --- known LLM endpoints (host substrings) ---
EP="api.anthropic.com api.openai.com openrouter.ai api.groq.com \
generativelanguage.googleapis.com api.cohere.com api.mistral.ai \
api.deepseek.com api.together.xyz api.x.ai api.moonshot.ai api.z.ai \
api.superagent.ng api.monid.ai"

# --- local model server ports (matched as :PORT at word end, not substring) ---
# NOTE: grep -E ":11434\b" so :111434 does NOT match. Checked: localhost:18080
# does not match localhost:8080 because the colon anchors it.
PORTS="11434 1234 8000 8080 17888"

# --- known agent config/transcript dirs (relative to $HOME) ---
DIRS=".claude .continue .aider .config/continue .config/opencode \
.aider.conf.yml .codex .cursor .gemini .opencode .config/ollama \
.ollama .lmstudio .goose .config/goose .claude.json \
.agents .config/agents .cursor-server"

# --- 1. PROCESS probe ---
procs=""
[ "$(command -v ps)" ] && procs=$(ps -eo pid,ppid,user,comm,args 2>/dev/null | head -400)

# --- 2. NETWORK probe ---
net=""
if [ "$(command -v lsof)" ]; then
  net=$(lsof -i -P -n 2>/dev/null | grep -E 'ESTABLISHED|LISTEN' | head -200)
elif [ "$(command -v ss)" ]; then
  net=$(ss -tunp 2>/dev/null | head -200)
elif [ "$(command -v netstat)" ]; then
  net=$(netstat -an 2>/dev/null | head -200)
fi

# --- 3. FILESYSTEM probe ---
files=""
for d in $DIRS; do
  [ -e "$HOME/$d" ] && files="$files$d;"
done

# --- 4. PACKAGE probe ---
pkgs=""
if [ "$(command -v pip3)" ]; then
  pkgs="$pkgs$(pip3 list 2>/dev/null | grep -iE 'langchain|autogen|crewai|llama-index|llamaindex|semantic-kernel|openai|anthropic|litellm|chromadb' | head -15 | tr '\n' ';')"
fi
if [ "$(command -v npm)" ]; then
  pkgs="$pkgs$(npm ls -g --depth=0 2>/dev/null | grep -iE 'claude|opencode|aider|anthropic|openai|llm' | head -10 | tr '\n' ';')"
fi

# --- fuse: known-name processes (build JSON array properly) ---
proc_json=""
while IFS= read -r line; do
  [ -z "$line" ] && continue
  pid=$(echo "$line" | awk '{print $1}')
  ppid=$(echo "$line" | awk '{print $2}')
  user=$(echo "$line" | awk '{print $3}')
  comm=$(echo "$line" | awk '{print $4}' | sed 's/"/\\"/g')
  args=$(echo "$line" | cut -c1-100 | sed 's/"/\\"/g')
  [ -n "$proc_json" ] && proc_json="$proc_json,"
  proc_json="$proc_json{\"name\":\"match\",\"pid\":$pid,\"ppid\":$ppid,\"user\":\"$user\",\"comm\":\"$comm\",\"args\":\"$args\"}"
done <<EOF
$(for k in $KNOWN; do echo "$procs" | grep -i "$k" | grep -v grep | head -2; done | awk '!seen[$1]++' | head -"$lim")
EOF

# --- fuse: endpoint connections (hosts by substring, ports by :PORT\b) ---
ep_json=""
while IFS= read -r line; do
  [ -z "$line" ] && continue
  pid=$(echo "$line" | awk '{print $2}' | tr -dc '0-9')
  desc=$(echo "$line" | sed 's/"/\\"/g' | cut -c1-100)
  [ -n "$ep_json" ] && ep_json="$ep_json,"
  ep_json="$ep_json{\"endpoint\":\"match\",\"pid\":${pid:-0},\"line\":\"$desc\"}"
done <<EOF
$( { for e in $EP; do echo "$net" | grep -i "$e" | head -2; done
     for p in $PORTS; do echo "$net" | grep -E ":$p\b" | head -2; done
   } | awk '!seen[$1]++' | head -"${lim:-50}")
EOF

np=$(echo "$proc_json" | grep -o '"pid"' | wc -l | tr -d ' ')
ne=$(echo "$ep_json" | grep -o '"pid"' | wc -l | tr -d ' ')
nf=$(echo "$files" | tr ';' '\n' | grep -c '.' || echo 0)
nkp=$(echo "$pkgs" | tr ';' '\n' | grep -c '.' || echo 0)

printf '{"skill":"agents","host":"%s","utc":"%s","n_procs":%s,"n_endpoints":%s,"n_paths":%s,"n_pkgs":%s,"procs":[%s],"endpoint_conns":[%s],"paths":"%s","pkgs":"%s"}\n' \
  "$host" "$now" "${np:-0}" "${ne:-0}" "${nf:-0}" "${nkp:-0}" \
  "$proc_json" "$ep_json" \
  "$(echo "$files" | sed 's/"/\\"/g' | cut -c1-400)" \
  "$(echo "$pkgs" | sed 's/"/\\"/g' | cut -c1-400)"
