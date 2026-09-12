#!/usr/bin/env bash
#
# Install the ReactorPro gateway from a GitHub release.
#
# Downloads the binary for this platform, verifies it against the release's
# SHA256SUMS, and installs it. Optionally writes a systemd unit and an
# environment file containing a freshly generated token.
#
# The checksum is verified before anything is installed. These binaries are not
# code-signed, so the checksum is the only integrity signal available.
#
# Usage:
#   install-gateway.sh [options]
#
#   --version <tag>     Release tag to install (default: latest), e.g. v1.3.9
#   --prefix <dir>      Install directory (default: /usr/local/bin as root,
#                       otherwise ~/.local/bin)
#   --data-dir <dir>    Data directory (default: /var/lib/reactorpro-gateway
#                       for a system install, otherwise
#                       ~/.local/share/reactorpro-gateway)
#   --env-file <path>   Where to write the token (default: /etc/reactorpro-gateway.env
#                       for a system install, otherwise <data dir>/gateway.env)
#   --with-systemd      Also install and start a systemd service (needs root)
#   --http-addr <addr>  Listen address for the systemd unit (default 127.0.0.1:3000)
#   --force             Reinstall even if the binary is already present
#   -h | --help         Show this help
#
# Exit codes: 0 success, 1 failure, 2 usage error.

set -euo pipefail

REPO="DrOlu/ReactorPro"
ASSET_BASE="reactorpro-gateway"

VERSION="latest"
PREFIX=""
DATA_DIR=""
ENV_FILE=""
WITH_SYSTEMD=0
HTTP_ADDR="127.0.0.1:3000"
FORCE=0

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

usage_error() {
  printf 'error: %s\n\n' "$*" >&2
  sed -n '3,30p' "$0" | sed 's/^# \{0,1\}//' >&2
  exit 2
}

while [ $# -gt 0 ]; do
  case "$1" in
    --version)     [ $# -ge 2 ] || usage_error "--version needs a value"; VERSION="$2"; shift 2 ;;
    --prefix)      [ $# -ge 2 ] || usage_error "--prefix needs a value"; PREFIX="$2"; shift 2 ;;
    --data-dir)    [ $# -ge 2 ] || usage_error "--data-dir needs a value"; DATA_DIR="$2"; shift 2 ;;
    --env-file)    [ $# -ge 2 ] || usage_error "--env-file needs a value"; ENV_FILE="$2"; shift 2 ;;
    --http-addr)   [ $# -ge 2 ] || usage_error "--http-addr needs a value"; HTTP_ADDR="$2"; shift 2 ;;
    --with-systemd) WITH_SYSTEMD=1; shift ;;
    --force)       FORCE=1; shift ;;
    -h|--help)     sed -n '3,30p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)             usage_error "unknown option: $1" ;;
  esac
done

# --- platform detection -------------------------------------------------------

os_raw="$(uname -s)"
arch_raw="$(uname -m)"

case "$os_raw" in
  Linux)  os="linux" ;;
  Darwin) os="darwin" ;;
  *)      die "unsupported operating system: $os_raw. On Windows, download ${ASSET_BASE}-windows-amd64.exe from the release page." ;;
esac

case "$arch_raw" in
  x86_64|amd64) arch="amd64" ;;
  aarch64|arm64) arch="arm64" ;;
  *) die "unsupported architecture: $arch_raw" ;;
esac

case "${os}/${arch}" in
  linux/amd64|linux/arm64|darwin/amd64|darwin/arm64) : ;;
  *) die "no published build for ${os}/${arch}" ;;
esac

asset="${ASSET_BASE}-${os}-${arch}"

# --- resolve install locations ------------------------------------------------

is_root=0
[ "$(id -u)" -eq 0 ] && is_root=1

if [ -z "$PREFIX" ]; then
  if [ "$is_root" -eq 1 ]; then PREFIX="/usr/local/bin"; else PREFIX="$HOME/.local/bin"; fi
fi

if [ -z "$DATA_DIR" ]; then
  if [ "$is_root" -eq 1 ]; then
    DATA_DIR="/var/lib/reactorpro-gateway"
  else
    DATA_DIR="$HOME/.local/share/reactorpro-gateway"
  fi
fi

if [ -z "$ENV_FILE" ]; then
  if [ "$is_root" -eq 1 ]; then ENV_FILE="/etc/reactorpro-gateway.env"; else ENV_FILE="$DATA_DIR/gateway.env"; fi
fi

if [ "$WITH_SYSTEMD" -eq 1 ] && [ "$os" != "linux" ]; then
  die "--with-systemd is only available on Linux"
fi
if [ "$WITH_SYSTEMD" -eq 1 ] && [ "$is_root" -ne 1 ]; then
  die "--with-systemd needs root. Re-run with sudo, or install without it and write a unit yourself."
fi

dest="$PREFIX/reactorpro-gateway"

if [ -e "$dest" ] && [ "$FORCE" -ne 1 ]; then
  die "$dest already exists. Re-run with --force to replace it (your data directory and token are not touched)."
fi

# --- fetch ---------------------------------------------------------------------

if [ "$VERSION" = "latest" ]; then
  release_url="https://github.com/${REPO}/releases/latest/download"
else
  release_url="https://github.com/${REPO}/releases/download/${VERSION}"
fi

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

printf 'Downloading %s (%s) from %s\n' "$asset" "${VERSION}" "$release_url"

fetch() {
  # curl is present on macOS and virtually every Linux; fall back to wget.
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL --retry 3 --retry-delay 2 -o "$2" "$1"
  elif command -v wget >/dev/null 2>&1; then
    wget -q -O "$2" "$1"
  else
    die "neither curl nor wget is available"
  fi
}

fetch "${release_url}/${asset}" "${workdir}/${asset}" \
  || die "download failed: ${release_url}/${asset}
Check the version exists: https://github.com/${REPO}/releases"
fetch "${release_url}/SHA256SUMS" "${workdir}/SHA256SUMS" \
  || die "could not download SHA256SUMS; refusing to install an unverified binary"

# --- verify --------------------------------------------------------------------

expected="$(awk -v name="$asset" '$2 == name { print $1 }' "${workdir}/SHA256SUMS")"
[ -n "$expected" ] || die "$asset is not listed in SHA256SUMS; refusing to install"

if command -v sha256sum >/dev/null 2>&1; then
  actual="$(sha256sum "${workdir}/${asset}" | awk '{ print $1 }')"
elif command -v shasum >/dev/null 2>&1; then
  actual="$(shasum -a 256 "${workdir}/${asset}" | awk '{ print $1 }')"
else
  die "no sha256sum or shasum available; cannot verify the download"
fi

if [ "$expected" != "$actual" ]; then
  die "checksum mismatch for $asset
  expected $expected
  actual   $actual
Do not install this file. Re-download, and treat the network path as untrusted."
fi

printf 'Checksum verified (%s)\n' "${actual:0:16}..."

# --- install -------------------------------------------------------------------

install -d -m 0755 "$PREFIX"
install -m 0755 "${workdir}/${asset}" "$dest"
printf 'Installed %s\n' "$dest"

# --- data directory and token --------------------------------------------------

install -d -m 0750 "$DATA_DIR"

token_state="kept"
if [ -s "$ENV_FILE" ] && grep -q '^LIVEAGENT_GATEWAY_TOKEN=' "$ENV_FILE" 2>/dev/null; then
  # Never silently rotate a token that clients already use.
  token_state="existing"
else
  install -d -m 0755 "$(dirname "$ENV_FILE")" 2>/dev/null || true
  umask 077
  {
    printf 'LIVEAGENT_GATEWAY_TOKEN=%s\n' "$(openssl rand -hex 32)"
    # Quoted because a data directory may contain spaces, and both systemd's
    # EnvironmentFile parser and a shell `source` strip surrounding quotes, so
    # the gateway receives the bare path either way.
    printf 'LIVEAGENT_GATEWAY_DATA_DIR="%s"\n' "$DATA_DIR"
  } > "$ENV_FILE"
  chmod 0600 "$ENV_FILE"
fi

if [ "$token_state" = "existing" ]; then
  printf 'Kept existing token file %s\n' "$ENV_FILE"
else
  printf 'Wrote %s (mode 0600) with a new gateway token\n' "$ENV_FILE"
fi

# --- systemd ------------------------------------------------------------------

if [ "$WITH_SYSTEMD" -eq 1 ]; then
  unit=/etc/systemd/system/reactorpro-gateway.service
  service_user="reactorpro"

  if ! id "$service_user" >/dev/null 2>&1; then
    useradd --system --home "$DATA_DIR" --shell /usr/sbin/nologin "$service_user" \
      || die "could not create the $service_user user"
    printf 'Created system user %s\n' "$service_user"
  fi

  chown -R "$service_user:$service_user" "$DATA_DIR"

  cat > "$unit" <<EOF
[Unit]
Description=ReactorPro Gateway
Documentation=https://github.com/${REPO}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${service_user}
Group=${service_user}
EnvironmentFile=${ENV_FILE}
ExecStart=${dest} --http-addr=${HTTP_ADDR}
Restart=always
RestartSec=5
StateDirectory=reactorpro-gateway
WorkingDirectory=${DATA_DIR}

NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=${DATA_DIR}
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
MemoryDenyWriteExecute=true
SystemCallArchitectures=native

LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

  chmod 0644 "$unit"
  systemctl daemon-reload
  systemctl enable --now reactorpro-gateway

  printf '\nService installed and started.\n'
  printf '  Logs:    journalctl -u reactorpro-gateway -f\n'
  printf '  Status:  systemctl status reactorpro-gateway\n'
else
  printf '\nStart it with:\n'
  printf '  set -a; . %s; set +a\n' "$ENV_FILE"
  printf '  %s --http-addr=%s\n' "$dest" "$HTTP_ADDR"
fi

printf '\nVerify (the token is in %s):\n' "$ENV_FILE"
printf '  curl -s localhost:%s/healthz\n' "${HTTP_ADDR##*:}"
printf '  curl -s -H "Authorization: Bearer $LIVEAGENT_GATEWAY_TOKEN" localhost:%s/api/status\n' "${HTTP_ADDR##*:}"
printf '\nBack up %s/mesh/reactorpro-identity.json once it exists — it is not reproducible.\n' "$DATA_DIR"
