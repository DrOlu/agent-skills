#!/usr/bin/env bash
# Ask any mesh peer through a ReactorPro gateway's REST API — no NATS client,
# no identity, no Python. The gateway signs and sends on YOUR behalf, so you
# are the gateway as far as peers are concerned. Bearer-token auth.
#
# Configuration (env vars or defaults):
#   REACTORPRO_GATEWAY_URL     default http://127.0.0.1:3000
#   REACTORPRO_GATEWAY_TOKEN   default: read from ~/.config/reactorpro/gateway.env
#
# Usage:
#   ask_peer.sh agents [capabilities,cap2]        # peer directory (the phonebook)
#   ask_peer.sh status                            # this gateway's mesh bridge
#   ask_peer.sh trust                            # identities this gateway has pinned
#   ask_peer.sh health
#   ask_peer.sh ask <peer-id> "prompt" [timeout_ms]
#   ask_peer.sh skill <peer-id> <skill> '<input-json>' [timeout_ms]
#   ask_peer.sh leave <peer-id> <skill> '<input-json>'   # durable mailbox, 202
#
# Examples:
#   ask_peer.sh agents
#   ask_peer.sh ask grip-001 "Summarise today's build status" 120000
#   ask_peer.sh skill reactorpro/bionic-01 ping '{}'
#   ask_peer.sh leave agentspan-001 status '{}'
#
# Notes:
#   - ask = skill "invoke" with input {text}: exactly what the desktop's
#     MeshSend tool sends. Text prompts are also mirrored to payload.text for
#     text-based Synapse peers.
#   - Real agent turns take 10-60s+; pass a generous timeout_ms (default 120000).
#   - leave returns 202 "queued" — there is NO reply by design.
set -euo pipefail

GATEWAY_URL="${REACTORPRO_GATEWAY_URL:-http://127.0.0.1:3000}"
GATEWAY_TOKEN="${REACTORPRO_GATEWAY_TOKEN:-}"
ENV_FILE="${REACTORPRO_GATEWAY_ENV:-$HOME/.config/reactorpro/gateway.env}"

if [ -z "$GATEWAY_TOKEN" ] && [ -f "$ENV_FILE" ]; then
  GATEWAY_TOKEN=$(grep -E '^LIVEAGENT_GATEWAY_TOKEN=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"')
fi
if [ -z "$GATEWAY_TOKEN" ]; then
  echo "no gateway token: set REACTORPRO_GATEWAY_TOKEN or create $ENV_FILE" >&2
  exit 2
fi

api() { # api METHOD PATH [JSON_BODY]
  local method="$1" path="$2" body="${3:-}"
  local args=(-sS -X "$method" "$GATEWAY_URL$path"
              -H "Authorization: Bearer $GATEWAY_TOKEN"
              -w '\nHTTP %{http_code}')
  if [ -n "$body" ]; then args+=(-H 'Content-Type: application/json' -d "$body"); fi
  curl "${args[@]}" | python3 -c '
import json, sys
raw = sys.stdin.read()
body, _, status = raw.rpartition("\nHTTP ")
try:
    print(json.dumps(json.loads(body), indent=2, ensure_ascii=False))
except ValueError:
    print(body or "(empty body)")
print(status.strip() or "HTTP 000", file=sys.stderr)
'
}

command="${1:-}"; shift || true
case "$command" in
  agents)
    query=""
    [ "${1:-}" != "" ] && query="?capabilities=$1"
    api GET "/api/mesh/agents$query" ;;
  status)  api GET /api/mesh/status ;;
  trust)   api GET /api/mesh/trust ;;
  health)  api GET /api/mesh/health ;;
  register) api POST /api/mesh/register ;;
  ask)
    [ $# -ge 2 ] || { echo "usage: ask_peer.sh ask <peer-id> \"prompt\" [timeout_ms]" >&2; exit 2; }
    target="$1"; prompt="$2"; timeout_ms="${3:-120000}"
    body=$(python3 -c 'import json,sys; print(json.dumps({"target":sys.argv[1],"skill":"invoke","input":{"text":sys.argv[2]},"timeoutMs":int(sys.argv[3])}))' "$target" "$prompt" "$timeout_ms")
    api POST /api/mesh/dispatch "$body" ;;
  skill)
    [ $# -ge 3 ] || { echo "usage: ask_peer.sh skill <peer-id> <skill> '<input-json>' [timeout_ms]" >&2; exit 2; }
    target="$1"; skill="$2"; input="$3"; timeout_ms="${4:-60000}"
    body=$(python3 -c 'import json,sys; print(json.dumps({"target":sys.argv[1],"skill":sys.argv[2],"input":json.loads(sys.argv[3]),"timeoutMs":int(sys.argv[4])}))' "$target" "$skill" "$input" "$timeout_ms")
    api POST /api/mesh/dispatch "$body" ;;
  leave)
    [ $# -ge 3 ] || { echo "usage: ask_peer.sh leave <peer-id> <skill> '<input-json>'" >&2; exit 2; }
    target="$1"; skill="$2"; input="$3"
    body=$(python3 -c 'import json,sys; print(json.dumps({"target":sys.argv[1],"skill":sys.argv[2],"input":json.loads(sys.argv[3])}))' "$target" "$skill" "$input")
    api POST /api/mesh/mailbox "$body" ;;
  *)
    sed -n '2,30p' "$0" | grep '^#' | sed 's/^# \{0,1\}//'
    exit 2 ;;
esac