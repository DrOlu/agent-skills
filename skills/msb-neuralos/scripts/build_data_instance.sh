#!/usr/bin/env bash
# Build the chinook data-source instance inside a Microsandbox sandbox:
# MariaDB + neuralOS chinook instance + web service (:8877), self-installing
# on first boot. Verifies data truth + runs the full Q&A suite in-guest.
#
# usage: build_data_instance.sh [--name chinook-ms] [--cpus 1] [--memory 1G]
#        [--instance-dir ~/boxlite-lab/chinook] [--port 8877] [--skip-suite]
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

NAME="chinook-ms"; CPUS=1; MEM="1G"; PORT=8877
INSTANCE_DIR="${CHINOOK_INSTANCE_DIR:-$HOME/boxlite-lab/chinook}"; SKIP_SUITE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --name) NAME="$2"; shift 2;;
    --cpus) CPUS="$2"; shift 2;;
    --memory) MEM="$2"; shift 2;;
    --instance-dir) INSTANCE_DIR="$2"; shift 2;;
    --port) PORT="$2"; shift 2;;
    --skip-suite) SKIP_SUITE=1; shift;;
    *) echo "unknown arg $1"; exit 1;;
  esac
done
[ -d "$INSTANCE_DIR" ] || { echo "instance dir not found: $INSTANCE_DIR"; exit 1; }
[ -f "$INSTANCE_DIR/chinook_mysql.sql" ] || { echo "chinook_mysql.sql missing in $INSTANCE_DIR"; exit 1; }

echo "== [1] create sandbox '$NAME' (if missing) =="
if msb list | awk 'NR>1{print $1}' | grep -qx "$NAME"; then
  echo "   exists — reusing (state persists)"
else
  msb create --name "$NAME" --hostname chinook -c "$CPUS" -m "$MEM" python:3.12-slim >/dev/null
fi
msb start "$NAME" >/dev/null 2>&1 || true
sleep 2

echo "== [2] copy instance files (contents land flat in /opt/chinook) =="
msb exec "$NAME" -- mkdir -p /opt/chinook
msb copy "$INSTANCE_DIR/." "chinook-placeholder" >/dev/null 2>&1 || true
msb copy "$INSTANCE_DIR/." "$NAME:/opt/chinook" 2>/dev/null || msb copy "$INSTANCE_DIR" "$NAME:/opt/chinook"
msb exec "$NAME" -- chmod +x /opt/chinook/start.sh
msb exec "$NAME" -- ls /opt/chinook | head -4

echo "== [3] launch self-installing start.sh in background =="
msb exec "$NAME" -- sh -c 'nohup /opt/chinook/start.sh >/var/log/chinook-outer.log 2>&1 & echo launched'

echo "== [4] poll until the demo server serves correct data =="
t0=$(date +%s); UP=0
for i in $(seq 1 80); do
  sleep 15
  R=$(msb exec "$NAME" -- python3 -c "
import json, urllib.request
try:
    req = urllib.request.Request('http://127.0.0.1:$PORT/ask', data=json.dumps({'question':'how many tracks are in the database'}).encode(), headers={'Content-Type':'application/json'})
    blob = urllib.request.urlopen(req, timeout=60).read().decode()
    print('SERVING' if '3503' in blob else 'WRONG-DATA')
except Exception as e:
    print('DOWN')
" 2>/dev/null | tail -1)
  echo "   t=$(( $(date +%s) - t0 ))s: $R"
  [ "$R" = "SERVING" ] && UP=1 && break
done
[ "$UP" = "1" ] || { echo "service did not come up — check /var/log/chinook.log in the sandbox"; exit 1; }

echo "== [5] SQL truth check =="
msb exec "$NAME" -- sh -c 'mysql -uadmin -padmin -N -e "SELECT (SELECT COUNT(*) FROM chinook_mysql.Track),(SELECT ROUND(SUM(Total),2) FROM chinook_mysql.Invoice)"' 2>&1 | tail -1

if [ "$SKIP_SUITE" = "0" ]; then
  echo "== [6] full Q&A suite =="
  msb copy "$SKILL_DIR/scripts/suite.py" "$NAME:/root/suite.py" >/dev/null
  msb exec "$NAME" -- python3 /root/suite.py 2>&1 | tail -11 || true
fi

echo
echo "chinook instance live in sandbox '$NAME' (web :$PORT in-guest)."
echo "Snapshot it: msb snapshot create --sandbox $NAME --full -o ${NAME}.msb"
