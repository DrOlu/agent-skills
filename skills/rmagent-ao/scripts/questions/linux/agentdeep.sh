#!/usr/bin/env bash
# agentdeep — deep per-agent detail on Linux/macOS: child processes (the
# tool-call log), resource usage, open files count. Read-only, capped.
# macOS has no eBPF, so this is process-tree depth, not syscall depth.
# Emits ONE JSON object.
# Engine injects: $Track, $SinceHours, $Limit

now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
host=$(hostname)
lim=${Limit:-20}; [ "$lim" -lt 1 ] && lim=1

KNOWN="claude-code opencode aider cursor-agent goose codex copilot \
cline windsurf kilocode crush gemini-cli ollama lmstudio llamafile \
vllm sglang anythingllm open-webui gpt4all koboldcpp \
autogen crewai langchain llamaindex semantic-kernel agentgpt \
superagent cyberagent rterm gybackend neuralos"

procs=""
[ "$(command -v ps)" ] && procs=$(ps -eo pid,ppid,user,comm,args 2>/dev/null | head -400)

# find agent PIDs
agent_pids=""
for k in $KNOWN; do
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    p=$(echo "$line" | awk '{print $1}')
    agent_pids="$agent_pids$p "
  done <<EOF
$(echo "$procs" | grep -i "$k" | grep -v grep | head -3)
EOF
done
# dedupe, cap
agent_pids=$(echo $agent_pids | tr ' ' '\n' | sort -un | head -10 | tr '\n' ' ')
np=$(echo $agent_pids | wc -w | tr -d ' ')

# children of each agent PID (the tool-call log)
children=""
for p in $agent_pids; do
  [ -z "$p" ] && continue
  kids=$(echo "$procs" | awk -v pp="$p" '$2 == pp {print $1, $4}' | head -5)
  while IFS= read -r kline; do
    [ -z "$kline" ] && continue
    [ -n "$children" ] && children="$children,"
    kpid=$(echo "$kline" | awk '{print $1}')
    kname=$(echo "$kline" | awk '{print $2}' | sed 's/"/\\"/g')
    children="$children{\"parent\":$p,\"pid\":$kpid,\"name\":\"$kname\"}"
  done <<< "$kids"
done

# resource usage per agent PID
activity=""
for p in $agent_pids; do
  [ -z "$p" ] && continue
  info=$(ps -p "$p" -o comm=,pcpu=,rss= 2>/dev/null | head -1)
  [ -n "$info" ] && activity="$activity$(echo "$info" | awk '{printf "%s:cpu=%s%%,mem=%sMB; ", $1, $2, int($3/1024)}')"
done

printf '{"skill":"agentdeep","host":"%s","utc":"%s","n_agent_pids":%s,"agent_pids":"%s","children":[%s],"activity":"%s"}\n' \
  "$host" "$now" "${np:-0}" \
  "$(echo $agent_pids | sed 's/"/\\"/g' | cut -c1-100)" \
  "$(echo "$children" | cut -c1-400)" \
  "$(echo "$activity" | sed 's/"/\\"/g' | cut -c1-400)"