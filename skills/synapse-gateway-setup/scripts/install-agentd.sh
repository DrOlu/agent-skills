#!/usr/bin/env bash
#
# Install the ReactorPro agentd (headless worker) from a GitHub release.
#
# Downloads the binary for this platform, verifies it against the release's
# SHA256SUMS, and installs it. The checksum is verified before anything is
# installed — these binaries are not code-signed, so the checksum is the only
# integrity signal available.
#
# This script installs the binary only. Configuration (gateway URL, agent id,
# per-agent token, provider settings, workdir) is documented in
# references/agentd.md — none of it is guessed here.
#
# Usage:
#   install-agentd.sh [options]
#
#   --version <tag>     Release tag to install (default: latest), e.g. v1.5.22
#   --prefix <dir>      Install directory (default: /usr/local/bin as root,
#                       otherwise ~/.local/bin)
#   --force             Reinstall even if the binary is already present
#   -h | --help         Show this help
#
# Exit codes: 0 success, 1 failure, 2 usage error.

set -euo pipefail

VERSION="latest"
PREFIX=""
FORCE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --version) VERSION="${2:?--version needs a value}"; shift 2 ;;
    --prefix)  PREFIX="${2:?--prefix needs a value}"; shift 2 ;;
    --force)   FORCE=1; shift ;;
    -h|--help) sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
done

# Platform -> asset suffix. The published matrix:
#   linux-amd64, linux-arm64, darwin-amd64, darwin-arm64, windows-amd64.exe
OS="$(uname -s)"
ARCH="$(uname -m)"
case "$OS" in
  Linux)  platform="linux" ;;
  Darwin) platform="darwin" ;;
  *) echo "unsupported platform: $OS (download the matching asset manually)" >&2; exit 1 ;;
esac
case "$ARCH" in
  x86_64|amd64) platform="$platform-amd64" ;;
  arm64|aarch64) platform="$platform-arm64" ;;
  *) echo "unsupported architecture: $ARCH" >&2; exit 1 ;;
esac

if [ -z "$PREFIX" ]; then
  if [ "$(id -u)" -eq 0 ]; then PREFIX="/usr/local/bin"; else PREFIX="$HOME/.local/bin"; fi
fi
mkdir -p "$PREFIX"

DEST="$PREFIX/reactorpro-agentd"
if [ -e "$DEST" ] && [ "$FORCE" -ne 1 ]; then
  echo "already installed: $DEST (use --force to replace)" >&2
  exit 0
fi

if [ "$VERSION" = "latest" ]; then
  BASE="https://github.com/DrOlu/ReactorPro/releases/latest/download"
else
  BASE="https://github.com/DrOlu/ReactorPro/releases/download/$VERSION"
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT   # shellcheck disable=SC2115

echo "downloading reactorpro-agentd-$platform from $BASE …"
curl -fsSL -o "$TMP/reactorpro-agentd-$platform" "$BASE/reactorpro-agentd-$platform"
curl -fsSL -o "$TMP/SHA256SUMS" "$BASE/SHA256SUMS"

echo "verifying checksum …"
expected="$(grep "reactorpro-agentd-$platform" "$TMP/SHA256SUMS" | awk '{print $1}')"
if [ -z "$expected" ]; then
  echo "no checksum found for reactorpro-agentd-$platform in SHA256SUMS — refusing to install" >&2
  exit 1
fi
if command -v sha256sum >/dev/null 2>&1; then
  actual="$(sha256sum "$TMP/reactorpro-agentd-$platform" | awk '{print $1}')"
else
  actual="$(shasum -a 256 "$TMP/reactorpro-agentd-$platform" | awk '{print $1}')"
fi
if [ "$actual" != "$expected" ]; then
  echo "checksum mismatch: expected $expected, got $actual — refusing to install" >&2
  exit 1
fi

install -m 0755 "$TMP/reactorpro-agentd-$platform" "$DEST"
echo "installed: $DEST"
echo
echo "next steps (see references/agentd.md for the full walkthrough):"
echo "  1. issue a per-agent token:  POST /api/agents/agent-<uuidv4>/token"
echo "  2. set the friendly name:    PATCH /api/agents/<id>  {\"name\": …}"
echo "  3. run: reactorpro-agentd -gateway ws://…/ws/v2/agent -agent-id … -token … \\"
echo "            -provider-url … -provider-model … -workdir …"