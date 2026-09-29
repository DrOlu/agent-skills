#!/usr/bin/env bash
# One-time environment for the boxlite-neuralos skill.
# Creates ~/boxlite-lab/venv (Python 3.12) with boxlite + neuralos.
set -euo pipefail

LAB="${BOXLITE_LAB_HOME:-$HOME/boxlite-lab}"
PYVER="${BOXLITE_PYTHON:-3.12}"

echo "== boxlite-neuralos env setup =="
echo "   lab dir : $LAB"
echo "   python  : $PYVER"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found — installing via pip venv fallback"
  PYBIN="$(command -v python3.12 || command -v python3)"
  "$PYBIN" -m venv "$LAB/venv"
  "$LAB/venv/bin/pip" install --upgrade pip >/dev/null
  "$LAB/venv/bin/pip" install boxlite neuralos
else
  uv venv "$LAB/venv" --python "$PYVER"
  uv pip install --python "$LAB/venv" boxlite neuralos
fi

echo "== verify =="
"$LAB/venv/bin/python" - <<'EOF'
import boxlite, needle
print("boxlite", boxlite.__version__)
print("neuralos/needle", needle.__version__)
EOF

if [ "$(uname)" = "Darwin" ]; then
  HV=$(sysctl -n kern.hv_support 2>/dev/null || echo 0)
  echo "hypervisor.framework support: $HV (1 = ok)"
fi

echo
echo "Done. Use: $LAB/venv/bin/python <script>"
