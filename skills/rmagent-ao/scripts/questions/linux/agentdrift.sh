#!/usr/bin/env bash
# agentdrift — the agent census digest for the drift baseline.
# Emits the same shape as agents.sh but compact, for diffing.
# The Python drift driver stores the baseline and computes the diff.
# Engine injects: $Track, $SinceHours, $Limit

now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
host=$(hostname)

# reuse the census logic but emit only the join keys (stable for diffing)
KNOWN="claude-code opencode aider cursor-agent goose codex copilot \\
cline windsurf kilocode crush gemini-cli ollama lmstudio llamafile \\
vllm sglang anythingllm open-webui gpt4all koboldcpp \\
autogen crewai langchain llamaindex semantic-kernel agentgpt \\
superagent cyberagent rterm gybackend neuralos"

EP="api.anthropic.com api.openai.com openrouter.ai api.groq.com \\
generativelanguage.googleapis.com api.cohere.com api.mistral.ai \\
api.deepseek.com api.together.xyz api.x.ai api.moonshot.ai api.z.ai \\
api.superagent.ng api.monid.ai"
PORTS="11434 1234 8000 8080 17888"

DIRS=".claude .continue .aider .config/continue .config/opencode \\
.aider.conf.yml .codex .cursor .gemini .opencode .config/ollama \\
.ollama .lmstudio .goose .config/goose .claude.json \\
.agents .config/agents .cursor-server"

procs=""
[ "$(command -v ps)" ] && procs=$(ps -eo pid,comm,args 2>/dev/null | head -400)
net=""
if [ "$(command -v lsof)" ]; then
  net=$(lsof -i -P -n 2>/dev/null | grep -E 'ESTABLISHED|LISTEN' | head -200)
fi

# stable keys: which keywords matched, which paths exist, which pkgs
kw_hits=""
for k in $KNOWN; do
  echo "$procs" | grep -qi "$k" && kw_hits="$kw_hits$k;"
done
ep_hits=""
for e in $EP; do
  echo "$net" | grep -qi "$e" && ep_hits="$ep_hits$e;"
done
for p in $PORTS; do
  echo "$net" | grep -qE ":$p\b" && ep_hits="$ep_hitslocal:$p;"
done
paths=""
for d in $DIRS; do
  [ -e "$HOME/$d" ] && paths="$paths$d;"
done

printf '{"skill":"agentdrift","host":"%s","utc":"%s","kw_hits":"%s","ep_hits":"%s","paths":"%s"}\n' \
  "$host" "$now" \
  "$(echo "$kw_hits" | sed 's/"/\\"/g' | cut -c1-300)" \
  "$(echo "$ep_hits" | sed 's/"/\\"/g' | cut -c1-300)" \
  "$(echo "$paths" | sed 's/"/\\"/g' | cut -c1-300)"