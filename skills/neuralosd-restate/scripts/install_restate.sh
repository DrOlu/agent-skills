#!/usr/bin/env bash
# Install Restate server + CLI (macOS and Linux). Windows: use WSL2 (see
# references/platforms.md). Idempotent: re-running upgrades in place.
set -euo pipefail

RESTATE_HOME="${RESTATE_HOME:-$HOME/restate}"
BASE="https://github.com/restatedev/restate/releases/latest/download"

OS=$(uname -s)
ARCH=$(uname -m)
case "$OS/$ARCH" in
  Darwin/arm64)   TARGET="aarch64-apple-darwin" ;;
  Darwin/x86_64)  TARGET="x86_64-apple-darwin" ;;
  Linux/aarch64|Linux/arm64) TARGET="aarch64-unknown-linux-gnu" ;;
  Linux/x86_64)   TARGET="x86_64-unknown-linux-gnu" ;;
  *) echo "unsupported: $OS/$ARCH"; exit 1 ;;
esac

echo "== downloading restate-server + cli ($TARGET) =="
mkdir -p "$RESTATE_HOME/bin"
curl -sL --max-time 600 "$BASE/restate-server-$TARGET.tar.xz" | tar xJ -C "$RESTATE_HOME"
curl -sL --max-time 600 "$BASE/restate-cli-$TARGET.tar.xz" | tar xJ -C "$RESTATE_HOME"
SERVER_BIN=$(find "$RESTATE_HOME" -name restate-server -type f | head -1)
CLI_BIN=$(find "$RESTATE_HOME" -name restate -type f | head -1)
[ -x "$SERVER_BIN" ] || { echo "server binary missing"; exit 1; }

echo "== start the server (foreground) =="
echo "  $SERVER_BIN"
echo "  ingress :8080  admin+UI :9070/ui/"
echo "  CLI: $CLI_BIN invocations list --all"
echo "== background + service hints: references/platforms.md =="
