#!/usr/bin/env bash
# Cook a neuralOS template sandbox + capture a FULL snapshot archive.
#
# usage: cook_template.sh [--name neuralos-template] [--image python:3.12-slim]
#        [--cpus 1] [--memory 1G] [--packages "pymysql pydantic"]
#        [--archive ~/boxlite-lab/microsandbox-archives/NAME.msb]
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"

NAME="neuralos-template"; IMAGE="python:3.12-slim"; CPUS=1; MEM="1G"
PACKAGES=""; ARCHIVE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --name) NAME="$2"; shift 2;;
    --image) IMAGE="$2"; shift 2;;
    --cpus) CPUS="$2"; shift 2;;
    --memory) MEM="$2"; shift 2;;
    --packages) PACKAGES="$2"; shift 2;;
    --archive) ARCHIVE="$2"; shift 2;;
    *) echo "unknown arg $1"; exit 1;;
  esac
done
[ -z "$ARCHIVE" ] && ARCHIVE="${MSB_LAB_HOME:-$HOME/boxlite-lab}/microsandbox-archives/${NAME}.msb"
mkdir -p "$(dirname "$ARCHIVE")"

echo "== [1] create sandbox '$NAME' ($IMAGE, $CPUS cpu, $MEM) =="
if msb list | awk 'NR>1{print $1}' | grep -qx "$NAME"; then
  echo "   exists — reusing"
else
  msb create --name "$NAME" -c "$CPUS" -m "$MEM" "$IMAGE" >/dev/null
fi

echo "== [2] pip install neuralos $PACKAGES =="
t0=$(date +%s)
msb exec "$NAME" -- sh -c "pip install --upgrade --no-cache-dir neuralos $PACKAGES 2>&1 | tail -1"
echo "   done in $(( $(date +%s) - t0 ))s"

echo "== [3] verify: import + real tool call (add 4 and 5 -> 9) =="
VERIFY='import json, os
os.environ.setdefault("NEEDLE_TELEMETRY","0"); os.environ.setdefault("DO_NOT_TRACK","1")
import needle
@needle.tool(triggers=["add two numbers","add numbers","sum"])
def add(a: int, b: int) -> int:
    "Add two numbers."
    return a + b
agent = needle.Needle(tools=[add])
r = agent.run("add 4 and 5")
res = r.get("results")
ok = (res == [9]) or (isinstance(res, list) and res and isinstance(res[0], dict) and 9 in [v for v in res[0].values() if isinstance(v,int)])
print(json.dumps({"version": needle.__version__, "tool_result": res, "ok": bool(ok)}))'
msb copy /dev/null "$NAME:/root/.keep" >/dev/null 2>&1 || true
echo "$VERIFY" > /tmp/msb_verify.py
msb copy /tmp/msb_verify.py "$NAME:/root/msb_verify.py" >/dev/null
OUT=$(msb exec "$NAME" -- python3 /root/msb_verify.py 2>&1 | tail -1)
echo "   $OUT"
echo "$OUT" | grep -q '"ok": true' || { echo "VERIFY FAILED"; exit 1; }

echo "== [4] full snapshot archive (disk+RAM+processes) =="
t0=$(date +%s)
msb snapshot create --sandbox "$NAME" --full -o "$ARCHIVE" 2>&1 | tail -1
echo "   archive: $ARCHIVE ($(( $(date +%s) - t0 ))s, $(du -h "$ARCHIVE" | cut -f1))"
echo
echo "Template '$NAME' cooked. Fork it:"
echo "  msb snapshot restore $ARCHIVE --name job-1 --forked"
