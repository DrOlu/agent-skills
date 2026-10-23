#!/usr/bin/env bash
# Serve a neuralosd instance on the Synapse mesh.
# Usage: bash serve_mesh.sh <instance-dir> [gateway] [port]
set -euo pipefail

DIR="${1:?usage: serve_mesh.sh <instance-dir> [gateway] [port]}"
GATEWAY="${2:-http://127.0.0.1:8090}"
PORT="${3:-8877}"

# Check prerequisites
command -v neuralosd >/dev/null 2>&1 || { echo "error: neuralosd not on PATH"; exit 1; }
[ -f "$DIR/probes.py" ] || { echo "error: no probes.py in $DIR"; exit 1; }

# Check the gateway
echo "checking Synapse gateway at $GATEWAY ..."
curl -sf -m 5 "$GATEWAY/health" >/dev/null 2>&1 \
  || { echo "warning: gateway not responding (NATS may be down)"; }

# Start serving
echo "serving '$(basename "$DIR")' on the mesh ..."
exec neuralosd mesh serve --instance-dir "$DIR" --gateway "$GATEWAY" --port "$PORT"
