#!/usr/bin/env bash
# Spin up a job sandbox from a neuralOS template snapshot and verify.
#
# usage: spin_up.sh --from neuralos-template --name job-001 [--forked] [--disk-only]
#        [--archive /path/to.msb] [--port 8878:8877] [--suite] [--ask "question"]
#
# --from can be a snapshot GROUP name (installed snapshot) or an archive path
# (pass via --archive). --forked = CoW RAM restore (live machine, boot-free);
# --disk-only = cold boot from captured disk (clean process state).
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

FROM=""; NAME=""; MODE="--forked"; PORTMAP=""; SUITE=0; ASK=""; ARCHIVE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --from) FROM="$2"; shift 2;;
    --name) NAME="$2"; shift 2;;
    --forked) MODE="--forked"; shift;;
    --disk-only) MODE="--disk-only"; shift;;
    --archive) ARCHIVE="$2"; shift 2;;
    --port) PORTMAP="$2"; shift 2;;
    --suite) SUITE=1; shift;;
    --ask) ASK="$2"; shift 2;;
    *) echo "unknown arg $1"; exit 1;;
  esac
done
[ -z "$NAME" ] && { echo "--name required"; exit 1; }
[ -z "$FROM" ] && [ -z "$ARCHIVE" ] && { echo "--from or --archive required"; exit 1; }

SRC="${ARCHIVE:-$FROM}"
echo "== restore $SRC -> $NAME ($MODE) =="
t0=$(date +%s)
if [ -n "$PORTMAP" ]; then
  msb snapshot restore "$SRC" --name "$NAME" $MODE -p "$PORTMAP" 2>&1 | tail -1
else
  msb snapshot restore "$SRC" --name "$NAME" $MODE 2>&1 | tail -1
fi
echo "   restored in $(( $(date +%s) - t0 ))s"

msb start "$NAME" >/dev/null 2>&1 || true
sleep 3

if [ -n "$ASK" ]; then
  echo "== ask: $ASK =="
  msb exec "$NAME" -- sh -c "cd /opt/chinook 2>/dev/null && python3 ask.py /opt/chinook \"$ASK\" 2>/dev/null || python3 - <<'EOF'
import json, os
os.environ.setdefault('NEEDLE_TELEMETRY','0'); os.environ.setdefault('DO_NOT_TRACK','1')
import needle
@needle.tool(triggers=['add two numbers','add numbers','sum'])
def add(a: int, b: int) -> int:
    'Add two numbers.'
    return a + b
print(json.dumps(needle.Needle(tools=[add]).run('''$ASK''').get('results')))
EOF"
fi

if [ "$SUITE" = "1" ]; then
  echo "== verification suite (in-guest, demo server :8877) =="
  msb copy "$SKILL_DIR/scripts/suite.py" "$NAME:/root/suite.py" >/dev/null
  if msb exec "$NAME" -- python3 /root/suite.py 2>&1 | tail -12; then :; fi
fi

echo
echo "job sandbox '$NAME' is running. stop: msb stop $NAME | remove: msb remove $NAME"
