#!/usr/bin/env bash
# ensure-rterm.sh — detect / install neuralos (gybackend) + rterm-cli, optionally start daemon.
# Harness-agnostic. No secrets in argv. Exit 0 = ready, 1 = failed, 2 = Node missing.
set -euo pipefail

PORT="${GYBACKEND_WS_PORT:-${RTERM_PORT:-17888}}"
HOST="${GYBACKEND_WS_HOST:-127.0.0.1}"
URL="${RTERM_URL:-ws://${HOST}:${PORT}}"
DATA_DIR="${GYBACKEND_DATA_DIR:-}"
START_DAEMON="${ENSURE_RTERM_START:-1}"

log() { printf '%s\n' "$*" >&2; }

need_node() {
  if ! command -v node >/dev/null 2>&1; then
    log "Node.js >= 18 is required. Install Node, then re-run."
    exit 2
  fi
  local major
  major="$(node -p 'process.versions.node.split(".")[0]')"
  if [ "${major}" -lt 18 ]; then
    log "Node $(node -v) is too old (need >= 18)."
    exit 2
  fi
}

npm_global() {
  npm install -g "$@" --prefer-online
}

has_cli() {
  command -v rterm-cli >/dev/null 2>&1 || command -v rterm >/dev/null 2>&1
}

has_backend() {
  command -v gybackend >/dev/null 2>&1
}

rterm_bin() {
  if command -v rterm-cli >/dev/null 2>&1; then echo rterm-cli
  elif command -v rterm >/dev/null 2>&1; then echo rterm
  else echo rterm-cli
  fi
}

gateway_up() {
  local bin
  bin="$(rterm_bin)"
  if ! command -v "${bin}" >/dev/null 2>&1; then return 1; fi
  RTERM_URL="${URL}" "${bin}" ping >/dev/null 2>&1
}

need_node

if ! has_cli; then
  log "Installing rterm-cli@latest …"
  npm_global rterm-cli
fi
if ! has_backend; then
  log "Installing neuralos@latest (bin: gybackend) …"
  npm_global neuralos
fi

if [ "${START_DAEMON}" = "1" ] && ! gateway_up; then
  log "Gateway not answering at ${URL} — starting gybackend …"
  mkdir -p "${DATA_DIR:-${HOME}/.gybackend-data}"
  export GYBACKEND_WS_ENABLE=1
  export GYBACKEND_WS_HOST="${GYBACKEND_WS_HOST:-0.0.0.0}"
  export GYBACKEND_WS_PORT="${PORT}"
  if [ -n "${DATA_DIR}" ]; then export GYBACKEND_DATA_DIR="${DATA_DIR}"; fi
  nohup gybackend >>"${HOME}/.gybackend-data/gybackend.log" 2>&1 &
  echo $! >"${HOME}/.gybackend-data/gybackend.pid"
  sleep 2
  i=0
  while [ "${i}" -lt 15 ]; do
    if gateway_up; then break; fi
    sleep 1
    i=$((i + 1))
  done
fi

BIN="$(rterm_bin)"
if ! gateway_up; then
  log "rterm-cli is installed but the gateway is down."
  log "Start it: gybackend   (or: GYBACKEND_WS_PORT=${PORT} gybackend)"
  log "Then: RTERM_URL=${URL} ${BIN} ping"
  exit 1
fi

log "OK  cli=$(command -v "${BIN}")  url=${URL}"
RTERM_URL="${URL}" "${BIN}" version || RTERM_URL="${URL}" "${BIN}" ping
exit 0
