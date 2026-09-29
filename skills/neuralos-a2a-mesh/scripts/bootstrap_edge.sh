#!/usr/bin/env bash
# bootstrap_edge.sh — install neuralOS engine + ReactorPro gateway + butler on
# macOS (launchd) or Linux (systemd) and wire them to survive reboot.
# Requires the parameters in references/parameters.md section B.
# Usage: bash bootstrap_edge.sh
set -euo pipefail

require() { [ -n "${!1:-}" ] || { echo "MISSING: $1 ($2)"; MISSING=1; }; }
MISSING=0
require NATS_URL            "central NATS endpoint, e.g. tls://hub.example:4222"
require GATEWAY_MESH_ID     "this edge's id, e.g. reactorpro/lagos-01"
require NEEDLE_ENGINE_DIR   "folder holding the engine binary + weights"
require LIVEAGENT_GATEWAY_TOKEN "gateway bearer token"
[ "$MISSING" = "1" ] && { echo; echo "Ask the operator for the missing values (references/parameters.md)."; exit 2; }

OS="$(uname -s)"
NAME="${GATEWAY_MESH_ID##*/}"
ROOT="${EDGE_ROOT:-$HOME/neuralos-edge}"
BIN_DIR="$ROOT/bin"; BUTLER_DIR="$ROOT/butler"
GATEWAY_BIN="${GATEWAY_BIN:-$BIN_DIR/reactorpro-gateway}"
BUTLER_PYTHON="${BUTLER_PYTHON:-python3}"
SB="${SKILL_BASE:-$(dirname "$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")")}"

echo "== install layout =="
mkdir -p "$BIN_DIR" "$BUTLER_DIR" "$ROOT/logs"
echo "  root=$ROOT  os=$OS"

echo "== 1. engine =="
if [ -x "$NEEDLE_ENGINE_DIR/needle" ] || [ -x "$NEEDLE_ENGINE_DIR/neural" ]; then
  echo "  engine found in $NEEDLE_ENGINE_DIR"
else
  echo "  no engine in $NEEDLE_ENGINE_DIR - installing via pip"
  python3 -m pip install --quiet neuralos || echo "  (pip install failed - install neuralOS manually)"
fi

echo "== 2. gateway binary =="
if [ -x "$GATEWAY_BIN" ]; then
  echo "  gateway: $GATEWAY_BIN"
else
  echo "  gateway binary not found at $GATEWAY_BIN (set GATEWAY_BIN=...)"
fi

echo "== 3. butler harness + menu =="
if [ -f "$SB/scripts/butler_template.py" ]; then
  cp -n "$SB/scripts/butler_template.py" "$BUTLER_DIR/butler.py"
  echo "  harness copied to $BUTLER_DIR/butler.py"
fi
if [ ! -f "$BUTLER_DIR/needle_menu.json" ]; then
  echo '[]' > "$BUTLER_DIR/needle_menu.json"
  echo "  placeholder menu written - replace it with the real probe menu"
fi

echo "== 4. gateway env file =="
ENVF="$ROOT/gateway.env"; umask 077
cat > "$ENVF" <<EOF
LIVEAGENT_GATEWAY_MESH_ID=$GATEWAY_MESH_ID
LIVEAGENT_GATEWAY_MESH_URL=$NATS_URL
LIVEAGENT_GATEWAY_MESH_VERIFY_MODE=require
LIVEAGENT_GATEWAY_MESH_TRUST_ON_FIRST_USE=false
LIVEAGENT_GATEWAY_MESH_TRUSTED_PEERS=${MESH_TRUSTED_PEERS:-}
LIVEAGENT_GATEWAY_TOKEN=$LIVEAGENT_GATEWAY_TOKEN
NEEDLE_ENGINE_DIR=$NEEDLE_ENGINE_DIR
EOF
[ -n "${NATS_CREDS:-}" ] && echo "LIVEAGENT_GATEWAY_MESH_CREDS=$NATS_CREDS" >> "$ENVF"
[ -n "${NATS_NKEY:-}" ]  && echo "LIVEAGENT_GATEWAY_MESH_NKEY=$NATS_NKEY"  >> "$ENVF"
chmod 600 "$ENVF"
echo "  wrote $ENVF (0600)"

if [ "$OS" = "Darwin" ]; then
  echo "== 5. launchd units (macOS) =="
  LA="$HOME/Library/LaunchAgents"; mkdir -p "$LA"
  sed -e "s#__GATEWAY_BIN__#$GATEWAY_BIN#g" -e "s#__ROOT__#$ROOT#g" \
      -e "s#__MESH_ID__#$GATEWAY_MESH_ID#g" > "$LA/ng.reactorpro.gateway.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>ng.reactorpro.gateway</string>
  <key>ProgramArguments</key><array><string>__GATEWAY_BIN__</string></array>
  <key>EnvironmentVariables</key><dict>
    <key>LIVEAGENT_GATEWAY_MESH_ID</key><string>__MESH_ID__</string>
  </dict>
  <key>StandardOutPath</key><string>__ROOT__/logs/gateway.log</string>
  <key>StandardErrorPath</key><string>__ROOT__/logs/gateway.err</string>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/><key>ThrottleInterval</key><integer>5</integer>
</dict></plist>
PLIST
  cat > "$LA/com.neuralos.butler.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.neuralos.butler</string>
  <key>ProgramArguments</key><array>
    <string>$BUTLER_PYTHON</string><string>$BUTLER_DIR/butler.py</string></array>
  <key>EnvironmentVariables</key><dict>
    <key>NEEDLE_ENGINE_DIR</key><string>$NEEDLE_ENGINE_DIR</string>
    <key>BUTLER_SKILL</key><string>${BUTLER_SKILL:-butler.query}</string>
  </dict>
  <key>WorkingDirectory</key><string>$BUTLER_DIR</string>
  <key>StandardOutPath</key><string>$ROOT/logs/butler.log</string>
  <key>StandardErrorPath</key><string>$ROOT/logs/butler.err</string>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
</dict></plist>
EOF
  echo "  wrote launchd plists in $LA"
elif [ "$OS" = "Linux" ]; then
  echo "== 5. systemd units (Linux) =="
  sudo tee /etc/systemd/system/reactorpro-gateway.service >/dev/null <<EOF
[Unit]
Description=ReactorPro gateway (mesh edge) - $NAME
After=network-online.target
[Service]
Type=simple
EnvironmentFile=$ENVF
ExecStart=$GATEWAY_BIN
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
EOF
  sudo tee /etc/systemd/system/neuralos-butler.service >/dev/null <<EOF
[Unit]
Description=neuralOS butler - $NAME
After=network-online.target
[Service]
Type=simple
WorkingDirectory=$BUTLER_DIR
Environment=NEEDLE_ENGINE_DIR=$NEEDLE_ENGINE_DIR
Environment=BUTLER_SKILL=${BUTLER_SKILL:-butler.query}
ExecStart=$BUTLER_PYTHON $BUTLER_DIR/butler.py
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
EOF
  sudo systemctl daemon-reload
  sudo systemctl enable --now reactorpro-gateway neuralos-butler
else
  echo "== 5. unsupported OS $OS - use the PowerShell bootstrap on Windows =="
  exit 3
fi

echo
echo "== next =="
echo "  1) exchange fingerprints out of band; set MESH_TRUSTED_PEERS on every edge"
echo "  2) bash scripts/doctor.sh"
echo "  3) bash scripts/dispatch.sh <peer-edge> <peer-butler> butler.query \"never-seen question\""