#!/usr/bin/env bash
# Check the health of every deployed door.
# Usage: bash fleet_status.sh
set -euo pipefail

DOORS_FILE="$HOME/.neuralosd/doors.json"

if [ ! -f "$DOORS_FILE" ]; then
  echo "no doors registered ($DOORS_FILE)"
  exit 0
fi

echo "════ FLEET STATUS ════"
echo

python3 - "$DOORS_FILE" <<'PY'
import json, sys, urllib.request

doors = json.load(open(sys.argv[1], encoding="utf-8"))
if not doors:
    print("  no doors registered")
    sys.exit(0)

alive = dead = 0
for name, info in sorted(doors.items()):
    port = info.get("host_port", "?")
    url = f"http://127.0.0.1:{port}/healthz"
    try:
        resp = urllib.request.urlopen(url, timeout=5)
        body = json.loads(resp.read())
        status = "✓ alive"
        alive += 1
    except Exception:
        status = "✗ dead"
        dead += 1
    print(f"  {name:24} :{port:<6} {status}")

print(f"\n  {alive} alive, {dead} dead, {len(doors)} total")
if dead:
    sys.exit(1)
PY
