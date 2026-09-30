#!/usr/bin/env bash
# Backup — timestamped archive export with retention.
#
# usage: backup.sh --name chinook-1gb [--keep 5] [--dir ~/boxlite-lab/backups]
#        (BoxLite: export_box; MSB: msb snapshot create --full -o)
set -euo pipefail
RUNTIME="boxlite"; NAME=""; KEEP=5
DIR="${MSB_LAB_HOME:-$HOME/boxlite-lab}/backups"
while [ $# -gt 0 ]; do
  case "$1" in
    --name) NAME="$2"; shift 2;;
    --keep) KEEP="$2"; shift 2;;
    --dir) DIR="$2"; shift 2;;
    --runtime) RUNTIME="$2"; shift 2;;
    *) echo "unknown arg $1"; exit 1;;
  esac
done
[ -z "$NAME" ] && { echo "--name required"; exit 1; }
mkdir -p "$DIR"
TS=$(date +%Y%m%d-%H%M%S)
OUT="$DIR/${NAME}-${TS}.$([ "$RUNTIME" = "msb" ] && echo msb || echo boxlite)"

if [ "$RUNTIME" = "msb" ]; then
  export PATH="$HOME/.local/bin:$PATH"
  msb snapshot create --sandbox "$NAME" --full -o "$OUT" 2>&1 | tail -1
else
  SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  "$SKILL_DIR/scripts/export_box.py" --name "$NAME" --dest "$OUT"
fi

echo "== retention (keep $KEEP newest for $NAME) =="
ls -t "$DIR"/${NAME}-* 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do
  rm -f "$old"; echo "pruned $old"
done
echo "backup: $OUT"
