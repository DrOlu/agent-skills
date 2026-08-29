#!/usr/bin/env bash
# agentnet — endpoint attribution for agents on this box. Which LLM APIs are
# being called, by which PID, at what volume. Read-only, capped.
# Engine injects: $Track, $SinceHours, $Limit

now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
host=$(hostname)
lim=${Limit:-30}

# known LLM endpoint hosts
EP="api.anthropic.com api.openai.com openrouter.ai api.groq.com \
generativelanguage.googleapis.com api.cohere.com api.mistral.ai \
api.deepseek.com api.together.xyz api.x.ai api.moonshot.ai api.z.ai \
api.superagent.ng api.monid.ai"

# local model server ports
PORTS="11434 1234 8000 8080 5000 17888"

# --- DNS cache probe (macOS/Linux) ---
dns_hits=""
if [ "$(command -v log)" ] && [ "$(uname)" = "Darwin" ]; then
  dns_hits=$(log show --last "${SinceHours:-2}h" --predicate 'process == "mDNSResponder"' 2>/dev/null | grep -oE "$(echo $EP | tr ' ' '|')" | sort | uniq -c | head -10)
elif [ -f /var/log/dns.log ]; then
  dns_hits=$(grep -E "$(echo $EP | tr ' ' '|')" /var/log/dns.log 2>/dev/null | tail -20)
fi

# --- active connections to known endpoints ---
conns=""
if [ "$(command -v lsof)" ]; then
  for e in $EP; do
    m=$(lsof -i -P -n 2>/dev/null | grep "$e" | grep -v grep | head -3)
    [ -n "$m" ] && conns="$conns$m\n"
  done
  for p in $PORTS; do
    m=$(lsof -i :$p -P -n 2>/dev/null | grep LISTEN | head -2)
    [ -n "$m" ] && conns="$conns$m\n"
  done
fi

# --- volume: bytes per connection (from lsof if available) ---
vol=""
if [ "$(command -v netstat)" ]; then
  vol=$(netstat -ib 2>/dev/null | head -10)
fi

printf '{"skill":"agentnet","host":"%s","utc":"%s","dns_hits":"%s","conns":"%s","interfaces":"%s"}\n' \
  "$host" "$now" \
  "$(echo "$dns_hits" | sed 's/"/\\"/g' | tr '\n' ';' | cut -c1-400)" \
  "$(echo "$conns" | sed 's/"/\\"/g' | tr '\n' ';' | cut -c1-500)" \
  "$(echo "$vol" | sed 's/"/\\"/g' | tr '\n' ';' | cut -c1-300)"
