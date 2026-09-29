#!/usr/bin/env bash
# One-time environment for the msb-neuralos skill: install/update the msb CLI,
# verify host virtualization, and (optionally) prepare a python env for suites.
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "== msb-neuralos env setup =="

OS="$(uname -s)"
echo "host: $OS $(uname -m)"

if ! command -v msb >/dev/null 2>&1; then
  if [ "$OS" = "Windows_NT" ] || grep -qi microsoft /proc/version 2>/dev/null; then
    echo "Windows: run in PowerShell:  irm https://install.microsandbox.dev/windows | iex"
    exit 1
  fi
  curl -fsSL https://install.microsandbox.dev | sh
else
  echo "msb already installed: $(msb --version 2>/dev/null | head -1)"
fi

echo "== msb version =="
msb --version 2>&1 | head -1

echo "== host virtualization check (msb doctor) =="
msb doctor 2>&1 | tail -15 || true

if [ "$OS" = "Darwin" ]; then
  echo "HVF support: $(sysctl -n kern.hv_support 2>/dev/null || echo 0) (1 = ok)"
elif [ "$OS" = "Linux" ]; then
  [ -e /dev/kvm ] && echo "/dev/kvm present" || echo "WARN: /dev/kvm missing (enable KVM)"
fi

echo "== python helper env (optional, for in-guest suites) =="
LAB="${MSB_LAB_HOME:-$HOME/boxlite-lab}"
if [ ! -x "$LAB/venv/bin/python" ]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv "$LAB/venv" --python 3.12
    uv pip install --python "$LAB/venv" neuralos
  else
    python3.12 -m venv "$LAB/venv" 2>/dev/null || python3 -m venv "$LAB/venv"
    "$LAB/venv/bin/pip" install --upgrade pip >/dev/null
    "$LAB/venv/bin/pip" install neuralos
  fi
fi
"$LAB/venv/bin/python" -c "import needle; print('host neuralOS/needle', needle.__version__)" || true

echo
echo "Done. Ensure PATH contains: $HOME/.local/bin"
