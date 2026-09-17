#!/bin/sh
#
# ReactorPro Gateway — launcher for launchd (macOS) and other service managers
# that cannot read an environment file.
#
# Why this exists: launchd plists are world-readable, so putting the gateway
# token in EnvironmentVariables would expose it to every local user. systemd has
# EnvironmentFile for this; launchd does not. This script reads secrets from
# 0600 files at start time, exports them, and execs the binary so the secret
# never appears in a plist or in the process table.
#
# Install to /usr/local/bin/reactorpro-gateway-launch.sh (mode 0755) and point
# the plist's ProgramArguments at it.
#
# Layout it expects:
#   /etc/reactorpro-gateway.env        or  ~/.config/reactorpro/gateway.env
#       LIVEAGENT_GATEWAY_TOKEN=...
#       LIVEAGENT_GATEWAY_DATA_DIR=...
#   /etc/nats/nats.conf                or  ~/.config/nats/nats.conf   (only if mesh is used)
#       authorization { user: ...; password: "..." }
#
# Override any value by exporting it before the script runs.

set -eu

GATEWAY_BIN="${REACTORPRO_GATEWAY_BIN:-/usr/local/bin/reactorpro-gateway}"
HTTP_ADDR="${REACTORPRO_GATEWAY_HTTP_ADDR:-127.0.0.1:3000}"

# Where the token lives. Root installs use /etc; per-user installs use the
# user's config directory.
if [ -z "${REACTORPRO_GATEWAY_ENV:-}" ]; then
  if [ -f /etc/reactorpro-gateway.env ]; then
    REACTORPRO_GATEWAY_ENV=/etc/reactorpro-gateway.env
  else
    REACTORPRO_GATEWAY_ENV="${HOME:-/root}/.config/reactorpro/gateway.env"
  fi
fi

if [ ! -x "$GATEWAY_BIN" ]; then
  echo "reactorpro-gateway not found or not executable at: $GATEWAY_BIN" >&2
  exit 1
fi

if [ ! -f "$REACTORPRO_GATEWAY_ENV" ]; then
  echo "missing credentials file: $REACTORPRO_GATEWAY_ENV" >&2
  exit 1
fi

# shellcheck disable=SC1090
. "$REACTORPRO_GATEWAY_ENV"

if [ -z "${LIVEAGENT_GATEWAY_TOKEN:-}" ]; then
  echo "LIVEAGENT_GATEWAY_TOKEN is empty in $REACTORPRO_GATEWAY_ENV" >&2
  exit 1
fi

# Strip surrounding quotes if the file used them. The gateway does not do this
# itself, and a quoted token produces a 401 on every request that is very hard
# to diagnose from the client side.
LIVEAGENT_GATEWAY_TOKEN="$(printf '%s' "$LIVEAGENT_GATEWAY_TOKEN" | sed 's/^"//; s/"$//')"
export LIVEAGENT_GATEWAY_TOKEN

# --- optional mesh ------------------------------------------------------------
# The bridge is off unless explicitly enabled. Enable it by adding
# LIVEAGENT_GATEWAY_MESH_ENABLED=true and LIVEAGENT_GATEWAY_MESH_URL=... to the
# credentials file, plus either a token or a user/password pair.

if [ "${LIVEAGENT_GATEWAY_MESH_ENABLED:-false}" = "true" ] &&
   [ -z "${LIVEAGENT_GATEWAY_MESH_PASSWORD:-}" ] &&
   [ -z "${LIVEAGENT_GATEWAY_MESH_TOKEN:-}" ]; then
  NATS_CONF="${NATS_CONF:-}"
  if [ -z "$NATS_CONF" ]; then
    for candidate in /etc/nats/nats.conf "${HOME:-/root}/.config/nats/nats.conf"; do
      if [ -f "$candidate" ]; then
        NATS_CONF="$candidate"
        break
      fi
    done
  fi

  if [ -n "$NATS_CONF" ] && [ -f "$NATS_CONF" ]; then
    NATS_USER="${LIVEAGENT_GATEWAY_MESH_USER:-admin}"
    password="$(
      awk -v user="$NATS_USER" '
        $0 ~ "^[[:space:]]*user:[[:space:]]*" user "[[:space:]]*$" { found = 1; next }
        found && /^[[:space:]]*password:/ {
          sub(/^[[:space:]]*password:[[:space:]]*/, "")
          print
          exit
        }
      ' "$NATS_CONF" | sed 's/^"//; s/"$//'
    )"
    if [ -n "$password" ]; then
      LIVEAGENT_GATEWAY_MESH_USER="$NATS_USER"
      LIVEAGENT_GATEWAY_MESH_PASSWORD="$password"
    else
      echo "warning: no password for NATS user '$NATS_USER' in $NATS_CONF" >&2
    fi
  fi
fi

# Export the settings the gateway reads, whether they came from the credentials
# file or the environment.
#
# This is a sweep over everything the file defined, not a hand-maintained list,
# and that is deliberate. A hand-written list acts as an *allowlist*: sourcing the
# file sets the variables, but only explicitly exported ones reach the binary. So
# a setting added later — a mesh trust pin, a registry mode, an invocation gate —
# would look like it was configured while having no effect at all, which is one of
# the most confusing ways this can fail.
#
# It covers the mesh settings that matter in practice: agent id and identity path,
# capabilities, verify mode, trusted peers, first-use learning, served skills,
# the discovery registry (mode, bucket, TTL), and the remote-invocation gates
# (allow / require-verified / operations / timeout), along with any other
# LIVEAGENT_* value the operator sets.
for _name in $(set | sed -n 's/^\(LIVEAGENT_[A-Za-z0-9_]*\)=.*/\1/p'); do
  export "$_name"
done
unset _name

# Gatekeeper can stall an adhoc GitHub-downloaded binary for minutes on the
# first exec after login. launchd reports the job as "running" while dyld is
# still in xpcproxy / cond-wait — no listen socket, no logs. Do not exec:
# start, wait until HTTP answers, kill-and-retry if it does not. KeepAlive
# then only has to cover a real crash, not a frozen first load.
READY_TIMEOUT="${REACTORPRO_GATEWAY_READY_TIMEOUT:-45}"
MAX_ATTEMPTS="${REACTORPRO_GATEWAY_START_ATTEMPTS:-8}"

listen_port="${HTTP_ADDR##*:}"
[ -n "$listen_port" ] || listen_port=3000

http_ready() {
  code=$(curl -sS -o /dev/null --max-time 2 -w '%{http_code}' \
    "http://127.0.0.1:${listen_port}/api/status" 2>/dev/null || true)
  case "$code" in
    200|401|403) return 0 ;;
  esac
  code=$(curl -sS -o /dev/null --max-time 2 -w '%{http_code}' \
    "http://[::1]:${listen_port}/api/status" 2>/dev/null || true)
  case "$code" in
    200|401|403) return 0 ;;
  esac
  return 1
}

child=""
term_child() {
  if [ -n "$child" ]; then
    kill "$child" 2>/dev/null || true
    sleep 1
    kill -9 "$child" 2>/dev/null || true
    wait "$child" 2>/dev/null || true
    child=""
  fi
}
trap 'term_child; exit 143' TERM INT HUP

attempt=1
while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
  echo "starting reactorpro-gateway (attempt ${attempt}/${MAX_ATTEMPTS})" >&2
  "$GATEWAY_BIN" --http-addr="$HTTP_ADDR" &
  child=$!

  t=0
  while [ "$t" -lt "$READY_TIMEOUT" ]; do
    if http_ready; then
      echo "reactorpro-gateway ready on ${HTTP_ADDR} after ${t}s (attempt ${attempt})" >&2
      wait "$child"
      exit $?
    fi
    if ! kill -0 "$child" 2>/dev/null; then
      wait "$child" || true
      echo "reactorpro-gateway exited before listen (attempt ${attempt})" >&2
      child=""
      break
    fi
    sleep 1
    t=$((t + 1))
  done

  if [ -n "$child" ]; then
    echo "reactorpro-gateway did not serve HTTP within ${READY_TIMEOUT}s; killing stuck process (attempt ${attempt})" >&2
    term_child
  fi
  attempt=$((attempt + 1))
  sleep 2
done

echo "reactorpro-gateway failed to become ready after ${MAX_ATTEMPTS} attempts" >&2
exit 1
