#!/usr/bin/env bash
# agentmodels — query local model servers through their own APIs.
# Ollama /api/tags + /api/ps, LM Studio /v1/models, vLLM /v1/models.
# Read-only GETs, capped. Emits ONE JSON object.
# Engine injects: $Track, $SinceHours, $Limit

now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
host=$(hostname)

ollama_installed=""; ollama_running=""
if curl -s -m 3 http://localhost:11434/api/tags 2>/dev/null | grep -q '"models"'; then
  ollama_installed=$(curl -s -m 3 http://localhost:11434/api/tags 2>/dev/null | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    ms=[m.get('name') for m in (d.get('models') or [])]
    print(';'.join(ms[:20]))
except: print('parse-error')" 2>/dev/null)
  ollama_running=$(curl -s -m 3 http://localhost:11434/api/ps 2>/dev/null | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    ms=[m.get('name') for m in (d.get('models') or [])]
    print(';'.join(ms[:10]))
except: print('')" 2>/dev/null)
fi

lmstudio=""
if curl -s -m 3 http://localhost:1234/v1/models 2>/dev/null | grep -q '"data"'; then
  lmstudio=$(curl -s -m 3 http://localhost:1234/v1/models 2>/dev/null | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    ms=[m.get('id') for m in (d.get('data') or [])]
    print(';'.join(ms[:20]))
except: print('parse-error')" 2>/dev/null)
fi

vllm=""
if curl -s -m 3 http://localhost:8000/v1/models 2>/dev/null | grep -q '"data"'; then
  vllm=$(curl -s -m 3 http://localhost:8000/v1/models 2>/dev/null | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    ms=[m.get('id') for m in (d.get('data') or [])]
    print(';'.join(ms[:20]))
except: print('parse-error')" 2>/dev/null)
fi

# any other OpenAI-compatible server on common ports
other=""
for port in 8080 5000 9997; do
  if curl -s -m 2 http://localhost:$port/v1/models 2>/dev/null | grep -q '"data"'; then
    other="$other;port-$port-openai-compatible"
  fi
done

printf '{"skill":"agentmodels","host":"%s","utc":"%s","ollama_installed":"%s","ollama_running":"%s","lmstudio":"%s","vllm":"%s","other":"%s"}\n' \
  "$host" "$now" \
  "$(echo "$ollama_installed" | sed 's/"/\\"/g')" \
  "$(echo "$ollama_running" | sed 's/"/\\"/g')" \
  "$(echo "$lmstudio" | sed 's/"/\\"/g')" \
  "$(echo "$vllm" | sed 's/"/\\"/g')" \
  "$(echo "$other" | sed 's/"/\\"/g')"
