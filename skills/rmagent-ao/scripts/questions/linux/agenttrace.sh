#!/usr/bin/env bash
# agenttrace — recent activity for agents found on this box, from their own
# disk artifacts (transcripts, logs). Read-only, capped by $Limit.
# Tier 1 agents (CLI agents with disk transcripts) return rich detail.
# Tier 3/4 return boundary-only (the census already found them).
# Emits ONE JSON object.

now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
host=$(hostname)
lim=${Limit:-20}
sh=${SinceHours:-2}
# handle sub-hour values: 0.5h -> 1800s, not 0s (the old ${sh%.*} gave 0)
case "$sh" in
  *.*) whole=${sh%.*}; frac=${sh#*.}
       case "$frac" in
         5)  since_s=$(( whole * 3600 + 1800 ));;
         25) since_s=$(( whole * 3600 + 900 ));;
         75) since_s=$(( whole * 3600 + 2700 ));;
         *)  since_s=$(( whole * 3600 ));;
       esac;;
  *)   since_s=$(( sh * 3600 ));;
esac
[ "$since_s" -lt 60 ] && since_s=60
cutoff=$(( $(date +%s) - since_s ))

# --- helper: newest files under a dir, filtered by mtime ---
recent() {
  find "$1" -type f -newermt "@$cutoff" 2>/dev/null | head -"$lim"
}

sessions=""; files_touched=""; commands=""

# --- Claude Code (~/.claude/projects/*/*.jsonl) ---
if [ -d "$HOME/.claude/projects" ]; then
  n=$(find "$HOME/.claude/projects" -name '*.jsonl' -newermt "@$cutoff" 2>/dev/null | wc -l | tr -d ' ')
  newest=$(find "$HOME/.claude/projects" -name '*.jsonl' -newermt "@$cutoff" 2>/dev/null | head -3 | tr '\n' ';')
  sessions="claude-code: $n session file(s) in window"
  files_touched="$newest"
fi

# --- OpenCode (~/.local/share/opencode or ~/.opencode) ---
for d in "$HOME/.local/share/opencode" "$HOME/.opencode"; do
  if [ -d "$d" ]; then
    n=$(find "$d" -type f -newermt "@$cutoff" 2>/dev/null | wc -l | tr -d ' ')
    sessions="$sessions|opencode: $n file(s) in window"
  fi
done

# --- Aider (.aider.chat.history.md etc) ---
for f in "$HOME/.aider.chat.history.md" "$HOME/.aider.input.history"; do
  if [ -f "$f" ] && find "$f" -newermt "@$cutoff" 2>/dev/null | grep -q .; then
    sessions="$sessions|aider: history active in window"
  fi
done

# --- Ollama logs (macOS/Linux) ---
for d in "$HOME/.ollama/logs" "/usr/local/var/log/ollama" "/var/log/ollama"; do
  if [ -d "$d" ]; then
    n=$(find "$d" -type f -newermt "@$cutoff" 2>/dev/null | wc -l | tr -d ' ')
    [ "$n" -gt 0 ] && sessions="$sessions|ollama: logs active in window"
  fi
done

# --- RTerm / gybackend (this estate's own agent) ---
for d in "$HOME/.gybackend-data/logs" "$HOME/Library/Application Support/rterm"; do
  if [ -d "$d" ]; then
    n=$(find "$d" -type f -newermt "@$cutoff" 2>/dev/null | wc -l | tr -d ' ')
    [ "$n" -gt 0 ] && sessions="$sessions|rterm/gybackend: $n log file(s) in window"
    # pull recent commands from the agent-run ledger if present
    if [ -f "$HOME/.gybackend-data/logs/gybackend.out.log" ]; then
      commands=$(tail -200 "$HOME/.gybackend-data/logs/gybackend.out.log" 2>/dev/null | grep -oE '\[AgentService[^]]*\][^"]{0,80}' | tail -"$lim" | tr '\n' ';' | cut -c1-600)
    fi
  fi
done

printf '{"skill":"agenttrace","host":"%s","utc":"%s","window_s":%s,"sessions":"%s","files":"%s","commands":"%s"}\n' \
  "$host" "$now" "$since_s" \
  "$(echo $sessions | sed 's/"/\\"/g' | cut -c1-500)" \
  "$(echo $files_touched | sed 's/"/\\"/g' | cut -c1-500)" \
  "$(echo $commands | sed 's/"/\\"/g' | cut -c1-600)"
