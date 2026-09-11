#!/usr/bin/env bash
# lag.sh - LiveAgent Gateway HTTP CLI (bash / zsh; requires only curl)
#
#   export LAG_GW="http://localhost:3000"
#   export LAG_TOKEN="<gateway token>"
#   export LAG_AGENT="agent-<uuid>"      # only agent-scoped commands need this
#
#   bash lag.sh health
#   bash lag.sh agents
#   bash lag.sh issue-token --name office-pc
#   bash lag.sh upload ./report.pdf
#
# Commands: health status agents issue-token rename-agent delete-agent upload share help
set -uo pipefail

GW="${LAG_GW:-http://localhost:3000}"
TOKEN="${LAG_TOKEN:-}"
AGENT="${LAG_AGENT:-}"

usage() {
  printf '%s\n' \
    "LiveAgent Gateway HTTP CLI" \
    "" \
    "Usage: lag.sh <command> [args]" \
    "       lag.sh --gw URL --token T --agent ID <command> [args]" \
    "" \
    "Environment: LAG_GW  LAG_TOKEN  LAG_AGENT" \
    "" \
    "Commands" \
    "  health                        Liveness check (no auth needed)" \
    "  status                        Agent online states + protocol usage" \
    "  agents [page] [size] [state]  Agent directory (state: all|online|offline)" \
    "  issue-token [--name N]        Issue or rotate the credential for LAG_AGENT" \
    "  rename-agent [--name N]       Set or clear the agent display name" \
    "  delete-agent                  Delete the agent record, credential and live session" \
    "  upload <file> [file...]       Upload readable files to the agent workspace" \
    "  share <share-token>           Resolve a public history share" \
    "  help                          This text" \
    "" \
    "WARNING: issue-token (rotation) and delete-agent disconnect that agent immediately."
}

# --- flags may appear anywhere in argv -------------------------------------
args=()
while [ $# -gt 0 ]; do
  case "$1" in
    --gw)    GW="$2"; shift 2 ;;
    --token) TOKEN="$2"; shift 2 ;;
    --agent) AGENT="$2"; shift 2 ;;
    *)       args+=("$1"); shift ;;
  esac
done
if [ ${#args[@]} -gt 0 ]; then set -- "${args[@]}"; else set --; fi
CMD="${1:-help}"
[ $# -gt 0 ] && shift

need_token() { [ -n "$TOKEN" ] || { echo "ERROR: set LAG_TOKEN or pass --token" >/dev/stderr; exit 2; }; }
need_agent() { [ -n "$AGENT" ] || { echo "ERROR: set LAG_AGENT or pass --agent" >/dev/stderr; exit 2; }; }

get()  { curl -sS --max-time 30 -H "Authorization: Bearer $TOKEN" "$GW$1"; }
send() { curl -sS --max-time 30 -X "$1" -H "Authorization: Bearer $TOKEN" \
           -H 'Content-Type: application/json' -d "$3" "$GW$2"; }

# Build {"name":"..."} (or {}) for the two name-taking commands.
name_body() {
  if [ "${1:-}" = "--name" ] && [ -n "${2:-}" ]; then
    printf '{"name":%s}' "$(printf '%s' "$2" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))')"
  else
    printf '{}'
  fi
}

case "$CMD" in
  health)
    curl -sS --max-time 15 "$GW/healthz"; echo
    ;;

  status)
    need_token
    out="$(get /api/status)"
    printf '%s' "$out" | python3 -m json.tool 2>/dev/null || printf '%s\n' "$out"
    ;;

  agents)
    need_token
    page="${1:-1}"; size="${2:-50}"; st="${3:-all}"
    out="$(curl -sS --max-time 30 -G "$GW/api/agents" \
             --data-urlencode "page=$page" \
             --data-urlencode "page_size=$size" \
             --data-urlencode "status=$st" \
             -H "Authorization: Bearer $TOKEN")"
    if command -v python3 >/dev/null 2>&1; then
      printf '%s' "$out" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print(sys.stdin.read()); raise SystemExit
print(f\"total={d['total']} page={d['page']} size={d['page_size']} has_more={d['has_more']}\")
for a in d.get('agents', []):
    print(f\"  {a['agent_id']}  online={a['online']}  name={a.get('name') or '(none)'}\")
"
    else
      printf '%s\n' "$out"
    fi
    ;;

  issue-token|rotate-token)
    need_token; need_agent
    echo "WARNING: rotation immediately disconnects agent $AGENT." >/dev/stderr
    send POST "/api/agents/$AGENT/token" "$(name_body "$@")"; echo
    ;;

  rename-agent)
    need_token; need_agent
    send PATCH "/api/agents/$AGENT" "$(name_body "$@")"; echo
    ;;

  delete-agent)
    need_token; need_agent
    echo "WARNING: deletes the record, revokes the credential and drops the live session." >/dev/stderr
    curl -sS --max-time 30 -X DELETE -H "Authorization: Bearer $TOKEN" \
      "$GW/api/agents/$AGENT"; echo
    ;;

  upload)
    need_token
    [ $# -gt 0 ] || { echo "ERROR: upload needs at least one file" >/dev/stderr; exit 2; }
    ff=(); for f in "$@"; do
      [ -f "$f" ] || { echo "ERROR: no such file: $f" >/dev/stderr; exit 2; }
      ff+=(-F "files=@$f")
    done
    curl -sS --max-time 120 -X POST -H "Authorization: Bearer $TOKEN" \
      "${ff[@]}" -F "agent_id=$AGENT" "$GW/api/files/import" \
      | (python3 -m json.tool 2>/dev/null || cat)
    echo
    ;;

  share)
    [ -n "${1:-}" ] || { echo "ERROR: share needs a share token" >/dev/stderr; exit 2; }
    curl -sS --max-time 30 -w '\nHTTP %{http_code}\n' "$GW/api/public/history-shares/$1"
    ;;

  help|-h|--help|"")
    usage
    ;;

  *)
    echo "ERROR: unknown command '$CMD'" >/dev/stderr
    echo >/dev/stderr
    usage >/dev/stderr
    exit 2
    ;;
esac
