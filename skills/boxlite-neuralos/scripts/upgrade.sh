#!/usr/bin/env bash
# Upgrade runbook — snapshot rollback point, upgrade in place, re-verify.
#
# usage: upgrade.sh [--name chinook-1gb] [--packages "neuralos"] \
#          [--suite-script /path/to/suite.py]
# Steps: export rollback archive -> pip upgrade -> health check -> suite ->
#        on failure: restore rollback automatically.
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

NAME="chinook-1gb"; PACKAGES="neuralos"; SUITE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --name) NAME="$2"; shift 2;;
    --packages) PACKAGES="$2"; shift 2;;
    --suite-script) SUITE="$2"; shift 2;;
    *) echo "unknown arg $1"; exit 1;;
  esac
done
TS=$(date +%Y%m%d-%H%M%S)
ARCHIVE="${MSB_LAB_HOME:-$HOME/boxlite-lab}/archives/${NAME}-rollback-${TS}.boxlite"
mkdir -p "$(dirname "$ARCHIVE")"

echo "== [1] rollback archive =="
$SKILL_DIR/export_box.py --name "$NAME" --dest "$ARCHIVE" 2>/dev/null \
  || { echo "export failed — aborting upgrade"; exit 1; }

echo "== [2] upgrade in place =="
python3 - "$NAME" "$PACKAGES" <<'PY'
import asyncio, sys
import boxlite
name, pkgs = sys.argv[1], sys.argv[2].split()
async def main():
    rt = boxlite.Boxlite.rest(boxlite.BoxliteRestOptions(
        url="http://localhost:8100",
        credential=boxlite.ApiKeyCredential("chinook-demo-key")))
    box = await rt.get(name)
    await box.start()
    ex = await box.exec("sh", ["-c", "pip install --upgrade --no-cache-dir " + " ".join(pkgs)],
                        timeout_secs=900)
    out = []
    async for line in ex.stdout(): out.append(line)
    await ex.wait()
    print("".join(out).strip().splitlines()[-1] if out else "(no output)")
asyncio.run(main())
PY

echo "== [3] health + suite gate =="
if [ -n "$SUITE" ]; then
  python3 - "$NAME" "$SUITE" <<'PY'
import asyncio, sys, json
import boxlite
name, suite = sys.argv[1], sys.argv[2]
async def main():
    rt = boxlite.Boxlite.rest(boxlite.BoxliteRestOptions(
        url="http://localhost:8100",
        credential=boxlite.ApiKeyCredential("chinook-demo-key")))
    box = await rt.get(name)
    await box.copy_in(suite, "/root/suite.py")
    ex = await box.exec("python3", ["/root/suite.py"], timeout_secs=600)
    out = []
    async for line in ex.stdout(): out.append(line)
    r = await ex.wait()
    print("".join(out).strip()[-400:])
    raise SystemExit(r.exit_code)
try:
    asyncio.run(main())
except SystemExit as e:
    sys.exit(e.code)
PY
  SUITE_RC=$?
  if [ "$SUITE_RC" != "0" ]; then
    echo "SUITE FAILED after upgrade — ROLLBACK"
    python3 - "$NAME" "$ARCHIVE" <<'PY'
import asyncio, sys
import boxlite
name, archive = sys.argv[1], sys.argv[2]
async def main():
    rt = boxlite.Boxlite.rest(boxlite.BoxliteRestOptions(
        url="http://localhost:8100",
        credential=boxlite.ApiKeyCredential("chinook-demo-key")))
    await rt.remove(name)
    await rt.import_box(archive, name=name)
    print(f"rolled back {name} from {archive}")
asyncio.run(main())
PY
    exit 1
  fi
  echo "suite PASSED"
else
  echo "(no --suite-script given — run the suite manually before trusting this box)"
fi
echo "upgrade complete. rollback archive: $ARCHIVE"
