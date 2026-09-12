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
# file or the environment. Assigning with a default keeps this safe under
# `set -u` and avoids relying on `export` succeeding only when a value is set.
export LIVEAGENT_GATEWAY_MESH_ENABLED="${LIVEAGENT_GATEWAY_MESH_ENABLED:-}"
export LIVEAGENT_GATEWAY_MESH_URL="${LIVEAGENT_GATEWAY_MESH_URL:-}"
export LIVEAGENT_GATEWAY_MESH_AGENT_ID="${LIVEAGENT_GATEWAY_MESH_AGENT_ID:-}"
export LIVEAGENT_GATEWAY_MESH_IDENTITY_PATH="${LIVEAGENT_GATEWAY_MESH_IDENTITY_PATH:-}"
export LIVEAGENT_GATEWAY_MESH_TOKEN="${LIVEAGENT_GATEWAY_MESH_TOKEN:-}"
export LIVEAGENT_GATEWAY_MESH_USER="${LIVEAGENT_GATEWAY_MESH_USER:-}"
export LIVEAGENT_GATEWAY_MESH_PASSWORD="${LIVEAGENT_GATEWAY_MESH_PASSWORD:-}"
export LIVEAGENT_GATEWAY_MESH_NAME="${LIVEAGENT_GATEWAY_MESH_NAME:-}"
export LIVEAGENT_GATEWAY_DATA_DIR="${LIVEAGENT_GATEWAY_DATA_DIR:-}"

exec "$GATEWAY_BIN" --http-addr="$HTTP_ADDR"
