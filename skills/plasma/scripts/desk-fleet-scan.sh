#!/usr/bin/env bash
# Desk-side fleet scan: pull both nodes, correlate, report.
# Usage: ./desk-fleet-scan.sh <inventory.json> <case-name>
# Requires: plasma CLI (pip install plasma-edr[desk]) + WS2PW-style env vars
set -euo pipefail
INVENTORY="${1:?inventory json required}"
CASE="${2:?case name required}"
ROOT="${ROOT:-$HOME/.plasma-desk}"
WINDOW="${WINDOW:-21600}"

plasma fleet pull --inventory "$INVENTORY" --case "$CASE" --root "$ROOT" \
  --cap 300 --window "$WINDOW"

plasma fleet correlate --case "$CASE" --root "$ROOT" --window "$WINDOW"

plasma fleet report --case "$CASE" --root "$ROOT"
echo
echo "dossier: $ROOT/fleet-cases/$CASE/report.md"
