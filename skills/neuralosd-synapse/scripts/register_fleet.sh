#!/usr/bin/env bash
# Register all instances in a directory on the Synapse mesh.
# Usage: bash register_fleet.sh <instances-dir> [gateway]
set -euo pipefail

DIR="${1:?usage: register_fleet.sh <instances-dir> [gateway]}"
GATEWAY="${2:-http://127.0.0.1:8090}"

# Check the gateway
curl -sf -m 5 "$GATEWAY/health" >/dev/null 2>&1 \
  || { echo "warning: gateway not responding at $GATEWAY"; }

echo "════ REGISTERING FLEET ════"
count=0
for inst_dir in "$DIR"/*/; do
  name=$(basename "$inst_dir")
  [ -f "$inst_dir/probes.py" ] || { echo "  skip $name (no probes.py)"; continue; }
  [ -f "$inst_dir/needle_menu.json" ] || { echo "  skip $name (no needle_menu.json)"; continue; }
  echo "  registering $name ..."
  neuralosd mesh register --instance-dir "$inst_dir" --gateway "$GATEWAY" 2>&1 | sed 's/^/    /'
  count=$((count + 1))
done
echo "\n  registered $count instances on $GATEWAY"
