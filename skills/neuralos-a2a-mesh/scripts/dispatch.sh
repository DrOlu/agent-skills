#!/usr/bin/env bash
# dispatch.sh — call a remote butler through the signed skillproxy lane and
# measure wall time. macOS / Linux.
# Usage: dispatch.sh <target-edge> <target-butler> <skill> "<question>" [timeoutMs]
set -u
TARGET="${1:?usage: dispatch.sh <edge> <butler> <skill> \"question\" [timeoutMs]}"
BUTLER="${2:?target butler required}"
SKILL="${3:?skill required, e.g. butler.query}"
QUESTION="${4:?question required}"
TIMEOUT="${5:-120000}"
: "${LIVEAGENT_GATEWAY_TOKEN:?set LIVEAGENT_GATEWAY_TOKEN}"
GW="${GATEWAY_URL:-http://127.0.0.1:3000}"

BODY=$(python3 - "$TARGET" "$BUTLER" "$SKILL" "$QUESTION" "$TIMEOUT" <<'PY'
import json, sys
target, butler, skill, question, timeout = sys.argv[1:6]
print(json.dumps({
  "target": target, "skill": "skillproxy", "timeoutMs": int(timeout),
  "input": {"target": butler, "skill": skill, "args": {"question": question}},
}))
PY
)

T0=$(python3 -c 'import time;print(time.time())')
RESP=$(curl -s --max-time $(( TIMEOUT/1000 + 10 )) -X POST "$GW/api/mesh/dispatch" \
  -H "Authorization: Bearer $LIVEAGENT_GATEWAY_TOKEN" \
  -H 'Content-Type: application/json' -d "$BODY")
T1=$(python3 -c 'import time;print(time.time())')

echo "$RESP" | python3 - "$T0" "$T1" <<'PY'
import json, sys
t0, t1 = float(sys.argv[1]), float(sys.argv[2])
try:
    d = json.load(sys.stdin)
except Exception:
    print("UNPARSEABLE REPLY — run doctor.sh and check the gateway log"); sys.exit(2)
out = (d.get("payload") or {}).get("output") or {}
r = out.get("reply") or {}
wall = round(t1 - t0, 2)
if r.get("ok"):
    print(f"OK  grounded={r.get('grounding')}  engine_elapsed={r.get('elapsed_s')}s  wall={wall}s")
    print(r.get("result"))
else:
    print(f"HOLE/FAIL  wall={wall}s")
    print(json.dumps({k: r.get(k) for k in ("ok", "hole", "error", "response")}, indent=1))
    sys.exit(1)
PY